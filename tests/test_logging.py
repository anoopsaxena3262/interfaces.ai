"""Discovery and replay logs are enough to troubleshoot without raw PII or PAN."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from interfaces_ai.agents.base import Store
from interfaces_ai.agents.discovery import DiscoveryAgent
from interfaces_ai.agents.escalation import EscalationAgent
from interfaces_ai.agents.replay import ReplayEngine
from interfaces_ai.observability import configure_logging
from interfaces_ai.schema.canonical import Money, TransferIntent

FIXTURE = Path(__file__).parent / "fixtures" / "redwood.html"
_LEAKS = (
    "jordan.hale@example.net",
    "Jordan Hale",
    "510-555-0199",
    "5105550199",
    "900210001",
    "900210099",
    "HH-20441",
)


def _text(caplog: logging.LogCaptureFixture) -> str:
    return " ".join(record.getMessage() for record in caplog.records)


def test_discovery_logs_coverage_without_live_samples(caplog: logging.LogCaptureFixture) -> None:
    configure_logging("INFO")
    with caplog.at_level(logging.INFO, logger="interfaces_ai"):
        report = DiscoveryAgent(html_loader=lambda _url: FIXTURE.read_text()).discover("redwood")
    text = _text(caplog)
    assert "discover start" in text
    assert "discover done" in text
    assert "html_source=" in text
    assert "confidence=" in text
    for leak in _LEAKS:
        assert leak not in text
        assert leak not in str(report.model_dump())
    samples = [field.sample for field in report.fields]
    assert "2190.40" not in samples
    assert "<money>" in samples
    assert "<id>" in samples


def test_replay_logs_steps_with_masked_account_ids(caplog: logging.LogCaptureFixture) -> None:
    configure_logging("INFO")
    engine = ReplayEngine(EscalationAgent(Store()))
    with caplog.at_level(logging.INFO, logger="interfaces_ai"):
        result = engine.replay(
            TransferIntent(
                institution_id="calloway",
                from_account_id="900210001",
                to_account_id="900210099",
                amount=Money(amount=Decimal("20.00")),
                memo="should not post",
            )
        )
    text = _text(caplog)
    assert "replay start" in text
    assert "replay done" in text
    assert "hold opened" in text
    assert result.succeeded is False
    assert "900210001" not in text
    assert "900210099" not in text
    assert "should not post" not in text
    assert result.intent.memo == ""
    assert result.intent.from_account_id == "••••0001"
    dump = result.model_dump_json()
    assert "900210001" not in dump
    assert "should not post" not in dump
