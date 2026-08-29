"""Discovery: locators, coverage score, empty-SPA fallback to published contract HTML."""

from pathlib import Path

from interfaces_ai.agents.base import Store
from interfaces_ai.agents.discovery import DiscoveryAgent, extract_page_contract
from interfaces_ai.agents.escalation import EscalationAgent

FIXTURE = Path(__file__).parent / "fixtures" / "redwood.html"


def test_extracts_published_ui_contract() -> None:
    html = FIXTURE.read_text()
    contract = extract_page_contract(html)
    assert contract["institution"] == "redwood"
    names = {field["canonical"] for field in contract["fields"]}
    assert "customer.display_name" in names
    assert "transfer.amount" in names
    actions = {item["name"] for item in contract["actions"]}
    assert "transfer.submit" in actions


def test_discovery_scores_complete_mapping() -> None:
    html = FIXTURE.read_text()
    agent = DiscoveryAgent(html_loader=lambda _url: html)
    report = agent.discover("redwood")
    assert report.confidence >= 0.85
    assert not report.missing_canonical_paths
    paths = {field.canonical_path for field in report.fields}
    assert "accounts[].available" in paths
    assert any(action.name == "transfer.submit" for action in report.actions)


def test_discovery_uses_published_contract_when_live_dom_is_empty() -> None:
    agent = DiscoveryAgent(html_loader=lambda _url: "<html><body><div id='app'></div></body></html>")
    report = agent.discover("calloway")
    assert any(action.name == "transfer.submit" for action in report.actions)
    assert report.page_contract["institution"] == "calloway"


def test_discovery_does_not_escalate_when_confident() -> None:
    html = FIXTURE.read_text()
    store = Store()
    agent = DiscoveryAgent(html_loader=lambda _url: html)
    escalation = EscalationAgent(store)
    report = agent.discover("northstar")
    assert escalation.maybe_open_for_discovery(report) is None


def test_discovery_samples_are_kinds_not_live_values() -> None:
    report = DiscoveryAgent(html_loader=lambda _url: FIXTURE.read_text()).discover("redwood")
    blob = report.model_dump_json()
    assert "@" not in blob
    assert "2190.40" not in blob
    assert "HH-20441" not in blob
    assert {field.sample for field in report.fields} <= {"<id>", "<money>", "<string>", "<enum>"}
