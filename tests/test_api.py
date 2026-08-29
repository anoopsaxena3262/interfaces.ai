"""HTTP: happy list, 404/422 error paths, compliance Phase 1–3, replay idempotency."""

from __future__ import annotations

import json
from copy import deepcopy

from fastapi.testclient import TestClient

from interfaces_ai.api.app import create_app
from interfaces_ai.schema import registry


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


def test_canonical_agent_view_omits_contact_and_transactions() -> None:
    client = TestClient(create_app())
    full = client.get("/api/v1/institutions/redwood/canonical")
    assert full.status_code == 200
    assert full.json()["customer"]["email"] == "jordan.hale@example.net"
    assert full.json()["transactions"]

    for institution_id in ("redwood", "northstar", "calloway"):
        agent = client.get(f"/api/v1/institutions/{institution_id}/canonical?view=agent")
        assert agent.status_code == 200
        payload = agent.json()
        customer = payload["customer"]
        assert "email" not in customer
        assert "phone" not in customer
        assert "transactions" not in payload
        assert payload["accounts"]
        blob = json.dumps(payload)
        assert "jordan.hale@example.net" not in blob
        assert "510-555" not in blob
        assert "510555" not in blob

    native = client.get("/api/v1/institutions/redwood/native").json()
    assert native["household"]["primary"]["mail"] == "jordan.hale@example.net"

    bad = client.get("/api/v1/institutions/redwood/canonical?view=full")
    assert bad.status_code == 422


def test_replay_idempotency_returns_first_result_and_does_not_double_post() -> None:
    client = TestClient(create_app())
    body = {
        "institution_id": "redwood",
        "from_account_id": "CHK-77",
        "to_account_id": "SAV-12",
        "amount": "40.00",
        "idempotency_key": "click-1",
    }
    first = client.post("/api/v1/agents/replay", json=body)
    second = client.post("/api/v1/agents/replay", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert first.json()["succeeded"] is True
    runs = client.get("/api/v1/runs").json()["replays"]
    assert sum(1 for row in runs if row["run_id"] == first.json()["run_id"]) == 1
    native = client.get("/api/v1/institutions/redwood/native").json()
    checking = next(p for p in native["products"]["deposits"] if p["productInstance"] == "CHK-77")
    assert checking["position"]["avail"] == "2150.40"


def test_replay_idempotency_conflict_is_409() -> None:
    client = TestClient(create_app())
    key = {"idempotency_key": "click-2"}
    first = client.post(
        "/api/v1/agents/replay",
        json={
            "institution_id": "redwood",
            "from_account_id": "CHK-77",
            "to_account_id": "SAV-12",
            "amount": "40.00",
            **key,
        },
    )
    clash = client.post(
        "/api/v1/agents/replay",
        json={
            "institution_id": "redwood",
            "from_account_id": "CHK-77",
            "to_account_id": "SAV-12",
            "amount": "10.00",
            **key,
        },
    )
    assert first.status_code == 200
    assert clash.status_code == 409
    native = client.get("/api/v1/institutions/redwood/native").json()
    checking = next(p for p in native["products"]["deposits"] if p["productInstance"] == "CHK-77")
    assert checking["position"]["avail"] == "2150.40"


def test_native_and_canonical_are_422_when_working_extract_has_pan() -> None:
    """Phase 3: ingest guard on every load, not only the seed file read."""
    client = TestClient(create_app())
    dirty = deepcopy(client.get("/api/v1/institutions/redwood/native").json())
    dirty["household"]["primary"]["note"] = "4242424242424242"
    registry._working["redwood"] = dirty
    assert client.get("/api/v1/institutions/redwood/native").status_code == 422
    assert client.get("/api/v1/institutions/redwood/canonical").status_code == 422


def test_reset_restores_seed_and_empty_view_is_full_snapshot() -> None:
    client = TestClient(create_app())
    client.post(
        "/api/v1/agents/replay",
        json={
            "institution_id": "redwood",
            "from_account_id": "CHK-77",
            "to_account_id": "SAV-12",
            "amount": "40.00",
        },
    )
    reset = client.post("/api/v1/dev/reset")
    assert reset.status_code == 200
    native = client.get("/api/v1/institutions/redwood/native").json()
    checking = next(p for p in native["products"]["deposits"] if p["productInstance"] == "CHK-77")
    assert checking["position"]["avail"] == "2190.40"
    empty_view = client.get("/api/v1/institutions/redwood/canonical?view=")
    assert empty_view.status_code == 200
    assert empty_view.json()["customer"]["email"]


def test_discover_response_includes_hold_when_report_is_weak(monkeypatch) -> None:
    from datetime import UTC, datetime

    from interfaces_ai.agents.discovery import DiscoveryAgent
    from interfaces_ai.schema.canonical import DiscoveryReport

    def weak(self, institution_id: str, html: str | None = None):
        return DiscoveryReport(
            institution_id=institution_id,
            ui_url="/redwood",
            discovered_at=datetime.now(UTC),
            fields=[],
            actions=[],
            confidence=0.1,
            missing_canonical_paths=["accounts[].available"],
        )

    monkeypatch.setattr(DiscoveryAgent, "discover", weak)
    client = TestClient(create_app())
    found = client.post("/api/v1/agents/discover", json={"institution_id": "redwood"})
    assert found.status_code == 200
    assert found.json()["escalations"]
