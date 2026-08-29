"""In-memory run log for local development. Swap for a DB in production.

Discoveries, replays, and holds die with the process. Reset-ledgers does not
clear this store — only restart (or a new Store()) does.
"""

from interfaces_ai.schema.canonical import DiscoveryReport, EscalationCase, ReplayResult


class Store:
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
        """Most recent report for this bank (newest-first list). Used to attach locators to replay."""
        for report in self.discoveries:
            if report.institution_id == institution_id:
                return report
        return None
