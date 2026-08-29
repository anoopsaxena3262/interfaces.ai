from __future__ import annotations

from interfaces_ai.schema.canonical import DiscoveryReport, EscalationCase, ReplayResult


class Store:
    """In-memory run log for local development. Swap for a DB in production."""

    def __init__(self) -> None:
        self.discoveries: list[DiscoveryReport] = []
        self.replays: list[ReplayResult] = []
        self.escalations: list[EscalationCase] = []

    def add_discovery(self, report: DiscoveryReport) -> DiscoveryReport:
        self.discoveries.insert(0, report)
        return report

    def add_replay(self, result: ReplayResult) -> ReplayResult:
        self.replays.insert(0, result)
        return result

    def add_escalation(self, case: EscalationCase) -> EscalationCase:
        self.escalations.insert(0, case)
        return case

    def latest_discovery(self, institution_id: str) -> DiscoveryReport | None:
        for report in self.discoveries:
            if report.institution_id == institution_id:
                return report
        return None
