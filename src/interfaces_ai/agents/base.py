"""In-memory run log for local development. Swap for a DB in production.

Discoveries, replays, and holds die with the process. Reset-ledgers does not
clear this store — only restart (or a new Store()) does.

Replay idempotency is the same lifetime: `(institution_id, idempotency_key)`
maps to the first ReplayResult. A durable unique constraint is product.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from interfaces_ai.observability import get_logger
from interfaces_ai.schema.canonical import DiscoveryReport, EscalationCase, ReplayResult, TransferIntent

log = get_logger("interfaces_ai.store")


class IdempotencyConflict(Exception):
    """Same (institution_id, key) was already used with a different transfer body."""


def intent_fingerprint(intent: TransferIntent) -> tuple[Any, ...]:
    """Compare full request fields. Stored ReplayResult.intent is last-4 / empty memo."""
    return (
        intent.institution_id,
        intent.from_account_id,
        intent.to_account_id,
        intent.amount.amount,
        intent.amount.currency,
        intent.memo,
        intent.actor,
    )


class Store:
    def __init__(self) -> None:
        self.discoveries: list[DiscoveryReport] = []
        self.replays: list[ReplayResult] = []
        self.escalations: list[EscalationCase] = []
        self._idempotency: dict[tuple[str, str], tuple[tuple[Any, ...], ReplayResult]] = {}
        self._idempotency_locks: dict[tuple[str, str], threading.Lock] = {}
        self._idempotency_guard = threading.Lock()

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

    def replay_once(
        self,
        institution_id: str,
        idempotency_key: str | None,
        fingerprint: tuple[Any, ...],
        run: Callable[[], ReplayResult],
    ) -> ReplayResult:
        """Run replay, or return the first result for this key. Serializes same-key overlap."""
        if not idempotency_key:
            result = run()
            self.add_replay(result)
            return result
        slot = (institution_id, idempotency_key)
        with self._idempotency_guard:
            lock = self._idempotency_locks.setdefault(slot, threading.Lock())
        with lock:
            hit = self._idempotency.get(slot)
            if hit is not None:
                stored_fp, result = hit
                if stored_fp != fingerprint:
                    raise IdempotencyConflict()
                log.info(
                    "replay replayed run_id=%s institution=%s",
                    result.run_id,
                    institution_id,
                )
                return result
            result = run()
            self._idempotency[slot] = (fingerprint, result)
            self.add_replay(result)
            return result
