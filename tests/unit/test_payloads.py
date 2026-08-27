"""An event type with no payload contract cannot be emitted — SDD §3.5, task 2.1."""

from __future__ import annotations

import pytest

from frontier.domain.events.model import EventDraft, Scope, Visibility
from frontier.domain.events.payloads import (
    REQUIRED_KEYS,
    InvalidPayload,
    UnknownEventType,
    validate,
)
from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import Axial, HexAddr

HERE = HexAddr((Axial(0, 0), Axial(1, 0)))


def draft(type_, payload) -> EventDraft:
    return EventDraft(
        type=type_, origin=HERE, scope=Scope.LOCAL, visibility=Visibility.PUBLIC, payload=payload
    )


def test_every_declared_event_type_has_a_payload_contract():
    assert set(REQUIRED_KEYS) == set(EventType)


def test_a_valid_payload_passes():
    validate(draft(EventType.MESSAGE, {"text": "hi", "channel": "local"}))


def test_a_missing_key_is_refused():
    with pytest.raises(InvalidPayload, match="channel"):
        validate(draft(EventType.MESSAGE, {"text": "hi"}))


def test_an_unregistered_type_is_refused():
    class Rogue:
        pass

    with pytest.raises(UnknownEventType):
        validate(draft(Rogue(), {}))


def test_a_value_jsonb_cannot_hold_is_refused():
    with pytest.raises(InvalidPayload, match="set"):
        validate(draft(EventType.MESSAGE, {"text": "hi", "channel": "local", "extra": {1, 2}}))
