"""HTTP: happy list, 404/422 error paths, and /runs redaction (compliance Phase 1)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from interfaces_ai.api.app import create_app


def test_health_and_institution_list() -> None:
    client = TestClient(create_app())
    assert client.get("/health").json()["ok"] is True
    names = {row["id"] for row in client.get("/api/v1/institutions").json()}
    assert names == {"redwood", "northstar", "calloway"}


def test_unknown_institution_is_404() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/institutions/not-a-bank/native").status_code == 404
    assert client.get("/api/v1/institutions/not-a-bank/canonical").status_code == 404
    discover = client.post("/api/v1/agents/discover", json={"institution_id": "not-a-bank"})
    assert discover.status_code == 404
    replay = client.post(
        "/api/v1/agents/replay",
        json={
            "institution_id": "not-a-bank",
            "from_account_id": "x",
            "to_account_id": "y",
            "amount": "1.00",
        },
    )
    assert replay.status_code == 404


def test_negative_and_zero_amount_are_rejected() -> None:
    client = TestClient(create_app())
    body = {
        "institution_id": "redwood",
        "from_account_id": "CHK-77",
        "to_account_id": "SAV-12",
        "amount": "-1.00",
    }
    negative = client.post("/api/v1/agents/replay", json=body)
    assert negative.status_code == 422
    zero = client.post("/api/v1/agents/replay", json={**body, "amount": "0"})
    assert zero.status_code == 422


def test_runs_and_escalations_do_not_echo_pii_or_native_bodies() -> None:
    """Operator log surface after discovery + a blocked Calloway transfer."""
    client = TestClient(create_app())
    discovered = client.post("/api/v1/agents/discover", json={"institution_id": "redwood"})
    assert discovered.status_code == 200
    held = client.post(
        "/api/v1/agents/replay",
        json={
            "institution_id": "calloway",
            "from_account_id": "900210001",
            "to_account_id": "900210099",
            "amount": "20.00",
            "memo": "jordan.hale@example.net must not persist",
        },
    )
    assert held.status_code == 200
    payload = held.json()
    assert payload["succeeded"] is False
    assert payload["escalation_id"]

    blob = json.dumps(client.get("/api/v1/runs").json()) + json.dumps(client.get("/api/v1/escalations").json())
    assert "jordan.hale@example.net" not in blob
    assert "900210001" not in blob
    assert "900210099" not in blob
    assert "majorUnits" not in blob
    assert "from_n" not in blob
    assert "fromSfx" not in blob
    assert "native_payload" not in blob
    assert "must not persist" not in blob
    assert "2190.40" not in blob
