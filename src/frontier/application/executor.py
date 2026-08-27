"""The one path every player action takes — SDD §5.2, ARCH §8.

Every guarantee this template makes (per-player serialisation, atomic state-and-events,
idempotency) comes from doing these steps in this order, which is why handlers never open
their own transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from frontier.application.commands.base import Command, State
from frontier.application.ports import ClockPort, IdPort, RngPort, UnitOfWork
from frontier.domain.decisions import Accepted, Rejected
from frontier.domain.events.model import Event
from frontier.domain.rules.ruleset import RuleSet


class WorldTicking(Exception):
    """The world is mid-tick; the caller should retry shortly."""

    retry_after = 30


@dataclass(frozen=True, slots=True)
class CommandResult:
    status: str
    events: list[Event]
    rejection: Rejected | None = None
    replayed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "replayed": self.replayed,
            "rejection": None
            if self.rejection is None
            else {"code": self.rejection.code.value, "context": self.rejection.context},
            "events": [
                {
                    "id": str(e.id),
                    "type": e.type.value,
                    "world_day": e.world_day,
                    "occurred_at": e.occurred_at.isoformat(),
                    "origin": str(e.origin),
                    "payload": e.payload,
                }
                for e in self.events
            ],
        }


@dataclass(frozen=True, slots=True)
class Executor:
    uow_factory: Any
    clock: ClockPort
    rng: RngPort
    ids: IdPort
    rules: RuleSet

    async def execute(self, command: Command, player_id: UUID) -> CommandResult:
        async with self.uow_factory() as uow:
            prior = await uow.commands.find(player_id, command.idempotency_key)
            if prior is not None:
                return CommandResult(status=str(prior["status"]), events=[], replayed=True)

            if await uow.world.phase() == "ticking":
                raise WorldTicking

            day = await uow.world.world_day()
            state = await self._load(uow, command, player_id)
            decision = command.check(state, self.rules)

            if isinstance(decision, Rejected):
                await self._record(uow, command, player_id, "rejected", decision, day)
                await uow.commit()
                return CommandResult(status="rejected", events=[], rejection=decision)

            drafts = command.apply(state, decision, self.rules, self.rng)
            events = self._stamp(drafts, day)

            await uow.players.debit_ap(player_id, decision.ap_cost, command.id, command.action, day)
            if state.ship is not None:
                await uow.ships.save(state.ship)
            await uow.events.append(events)
            await self._record(uow, command, player_id, "accepted", decision, day)
            await uow.commit()
            return CommandResult(status="accepted", events=events)

    async def _load(self, uow: UnitOfWork, command: Command, player_id: UUID) -> State:
        spec = command.loads()
        player = await uow.players.get_for_update(player_id)
        ship = await uow.ships.of_player(player_id) if spec.ship else None
        known = {str(addr) for addr in spec.resolve if await uow.locations.exists(addr)}
        return State(player=player, ship=ship, known_addresses=frozenset(known))

    def _stamp(self, drafts: list[Any], day: int) -> list[Event]:
        now = self.clock.now()
        return [
            Event(
                id=self.ids.new(),
                world_day=day,
                occurred_at=now,
                type=d.type,
                origin=d.origin,
                scope=d.scope,
                visibility=d.visibility,
                severity=d.severity,
                participants=d.participants,
                payload=d.payload,
                ruleset_version=self.rules.version,
            )
            for d in drafts
        ]

    async def _record(
        self,
        uow: UnitOfWork,
        command: Command,
        player_id: UUID,
        status: str,
        decision: Accepted | Rejected,
        day: int,
    ) -> None:
        outcome: dict[str, object] = (
            {"ap_cost": decision.ap_cost, "fuel_cost": decision.fuel_cost}
            if isinstance(decision, Accepted)
            else {"code": decision.code.value, "context": decision.context}
        )
        await uow.commands.record(
            player_id,
            command.idempotency_key,
            command.action,
            status,
            outcome,
            day,
            self.rules.version,
        )
