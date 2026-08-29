"""CLI: institutions, canonical views, discover, replay."""

import json
from datetime import UTC, datetime

from interfaces_ai.agents.discovery import DiscoveryAgent
from interfaces_ai.cli import main
from interfaces_ai.schema.canonical import DiscoveryReport


def test_canonical_agent_view_omits_contact(capsys) -> None:
    assert main(["canonical", "redwood", "--agent-view"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "email" not in payload["customer"]
    assert "phone" not in payload["customer"]
    assert "transactions" not in payload
    assert "jordan.hale@example.net" not in json.dumps(payload)


def test_canonical_full_dump_still_has_email(capsys) -> None:
    assert main(["canonical", "redwood"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["customer"]["email"] == "jordan.hale@example.net"
    assert payload["transactions"]


def test_institutions_lists_three_banks(capsys) -> None:
    assert main(["institutions"]) == 0
    out = capsys.readouterr().out
    assert "redwood" in out
    assert "northstar" in out
    assert "calloway" in out


def test_discover_one_bank_prints_report(capsys) -> None:
    assert main(["discover", "redwood"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["institution_id"] == "redwood"
    assert payload["confidence"] > 0


def test_replay_success_and_hold_exit_codes(capsys) -> None:
    assert main(["replay", "redwood", "CHK-77", "SAV-12", "40"]) == 0
    posted = json.loads(capsys.readouterr().out)
    assert posted["succeeded"] is True
    assert main(["replay", "calloway", "900210001", "900210099", "20"]) == 1
    held = json.loads(capsys.readouterr().out)
    assert held["succeeded"] is False


def test_discover_all_banks(capsys) -> None:
    assert main(["discover"]) == 0
    out = capsys.readouterr().out
    assert "redwood" in out
    assert "northstar" in out


def test_discover_prints_escalation_when_held(monkeypatch, capsys) -> None:
    def weak(self, institution_id: str, html: str | None = None):
        return DiscoveryReport(
            institution_id=institution_id,
            ui_url="/x",
            discovered_at=datetime.now(UTC),
            fields=[],
            actions=[],
            confidence=0.1,
            missing_canonical_paths=["accounts[].available"],
        )

    monkeypatch.setattr(DiscoveryAgent, "discover", weak)
    assert main(["discover", "redwood"]) == 0
    assert "escalated:" in capsys.readouterr().out
