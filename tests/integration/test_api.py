"""A token can move a ship — SDD §15 task 0.7."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from frontier.adapters.api.app import create_app
from frontier.config.container import build
from frontier.worldgen.fixture import HEXES, SYSTEM, starting_position


@pytest.fixture
def client(settings):
    return TestClient(create_app(build(settings=settings)))


@pytest.fixture
def token(client):
    response = client.post(
        "/v1/auth/register",
        json={
            "email": "cmdr@example.com",
            "password": "correct horse battery",
            "callsign": "Cmdr Smith",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_reports_the_active_ruleset(client):
    assert client.get("/healthz").json() == {"status": "ok", "ruleset": "2026.1"}


def test_a_command_without_a_token_is_refused(client):
    body = {"action": "move", "to": str(SYSTEM.child(HEXES[1])), "idempotency_key": str(uuid4())}
    assert client.post("/v1/commands", json=body).status_code == 401


def test_a_token_can_move_a_ship(client, token):
    body = {"action": "move", "to": str(SYSTEM.child(HEXES[1])), "idempotency_key": str(uuid4())}
    response = client.post("/v1/commands", json=body, headers=auth(token))

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["events"][0]["type"] == "SHIP_ENTERED"
    assert payload["events"][0]["payload"]["from"] == str(starting_position())


def test_an_illegal_move_is_a_409_with_a_stable_code(client, token):
    body = {"action": "move", "to": str(SYSTEM.child(HEXES[2])), "idempotency_key": str(uuid4())}
    client.post("/v1/commands", json=body, headers=auth(token))
    far = {"action": "move", "to": "ga0_0/re1_0/sy4_2/pl9_9", "idempotency_key": str(uuid4())}

    response = client.post("/v1/commands", json=far, headers=auth(token))

    assert response.status_code == 409
    assert response.json()["code"] == "UNKNOWN_DESTINATION"


def test_a_malformed_address_never_reaches_the_domain(client, token):
    body = {"action": "move", "to": "not-an-address", "idempotency_key": str(uuid4())}
    assert client.post("/v1/commands", json=body, headers=auth(token)).status_code == 422


def test_login_returns_a_working_token(client, token):
    response = client.post(
        "/v1/auth/login",
        json={
            "email": "cmdr@example.com",
            "password": "correct horse battery",
        },
    )
    assert response.status_code == 200
    body = {"action": "move", "to": str(SYSTEM.child(HEXES[1])), "idempotency_key": str(uuid4())}
    assert (
        client.post("/v1/commands", json=body, headers=auth(response.json()["access_token"])).status_code
        == 202
    )
