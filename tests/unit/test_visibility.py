"""The sensor model, row by row — SDD §5.5, criterion A9."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from frontier.application.visibility import (
    Quality,
    ViewerContext,
    observation_quality,
    render_for,
    resolve_audience,
)
from frontier.domain.events.model import Event, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import Axial, HexAddr

SYSTEM = HexAddr((Axial(0, 0), Axial(1, 0), Axial(4, 2)))


def at(q: int, r: int) -> HexAddr:
    return SYSTEM.child(Axial(q, r))


ORIGIN = SYSTEM.child(Axial(0, 0))


def event(
    origin: HexAddr,
    *,
    type_=EventType.SHIP_ENTERED,
    participants=(),
    visibility=Visibility.PUBLIC,
    scope=Scope.LOCAL,
) -> Event:
    return Event(
        id=uuid4(),
        world_day=1,
        occurred_at=datetime(2026, 8, 27, tzinfo=UTC),
        type=type_,
        origin=origin,
        scope=scope,
        visibility=visibility,
        severity=Severity.MINOR,
        participants=frozenset(participants),
        payload={"ship_id": "s", "actor_kind": "player", "from": str(at(0, 0)), "to": str(origin)},
        ruleset_version="test",
    )


def viewer(position: HexAddr | None = ORIGIN, sensor: int = 4, radio: int = 5) -> ViewerContext:
    return ViewerContext(player_id=uuid4(), position=position, sensor_range=sensor, radio_range=radio)


def test_a_participant_always_sees_everything():
    me = viewer(position=None)
    assert observation_quality(me, event(at(9, 9), participants=[me.player_id])) is Quality.FULL


def test_close_contacts_are_identified():
    assert observation_quality(viewer(sensor=4), event(at(2, 0))) is Quality.FULL


def test_distant_contacts_are_unidentified():
    assert observation_quality(viewer(sensor=4), event(at(3, 0))) is Quality.PARTIAL


def test_beyond_sensors_the_event_does_not_exist():
    assert observation_quality(viewer(sensor=4), event(at(5, 0))) is Quality.NONE


def test_messages_carry_over_radio_not_sensors():
    far = event(at(5, 0), type_=EventType.MESSAGE)
    assert observation_quality(viewer(sensor=1, radio=6), far) is Quality.FULL


def test_a_viewer_with_no_ship_sees_nothing_they_did_not_do():
    assert observation_quality(viewer(position=None), event(at(0, 0))) is Quality.NONE


def test_a_partial_contact_is_redacted_and_its_position_fuzzed():
    view = render_for(viewer(sensor=4), event(at(3, 0)))
    assert view is not None
    assert view.quality is Quality.PARTIAL
    assert view.payload == {"contact": "unidentified", "actor_kind": "player"}
    assert "ship_id" not in view.payload
    assert view.origin == str(SYSTEM)


def test_nothing_is_rendered_for_an_unentitled_viewer():
    assert render_for(viewer(sensor=1), event(at(9, 0))) is None


def test_a_system_scope_event_reaches_everyone_in_the_system():
    quality = observation_quality(viewer(position=at(8, 8)), event(at(0, 0), scope=Scope.SYSTEM))
    assert quality is Quality.FULL


@pytest.mark.parametrize(
    ("visibility", "narrow"),
    [(Visibility.PARTICIPANTS, True), (Visibility.TEAM, True), (Visibility.PUBLIC, False)],
)
def test_only_narrow_audiences_fan_out_on_write(visibility, narrow):
    player, team = uuid4(), uuid4()
    spec = resolve_audience(event(at(0, 0), visibility=visibility, participants=[player]), {player: team})
    assert spec.is_narrow is narrow
