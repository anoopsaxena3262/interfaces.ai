"""Shared snapshot and agent DTOs. Keep aligned with data/schemas/canonical.schema.json.

Agents (discovery, replay, hold) speak these types only. Bank JSON never appears
on CanonicalSnapshot except as opaque native_ref / native_path strings.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"  # schema allows it; fixtures have no PAN — reject card data at ingest if it appears
    LOAN = "loan"
    UNKNOWN = "unknown"


class TransactionDirection(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class Money(BaseModel):
    """ISO-style amount: Decimal plus ISO-4217 currency. Never float on the wire."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency: str = "USD"

    def as_float(self) -> float:
        """Policy comparisons only (escalation thresholds). Do not persist this."""
        return float(self.amount)


class Party(BaseModel):
    id: str
    display_name: str
    email: str | None = None  # mapped for portals; unused by replay/policy
    phone: str | None = None
    native_id_field: str = Field(description="Source field path that produced Party.id")


class Account(BaseModel):
    id: str  # native posting key (Calloway n= looks like a full DDA)
    masked_number: str
    name: str
    type: AccountType
    available: Money
    current: Money
    status: str = "open"  # free string today; "hold" blocks replay
    native_ref: dict[str, Any] = Field(default_factory=dict)


class Transaction(BaseModel):
    id: str
    account_id: str
    posted_on: date
    description: str
    amount: Money  # always positive; sign lives on direction
    direction: TransactionDirection
    native_ref: dict[str, Any] = Field(default_factory=dict)


class CanonicalSnapshot(BaseModel):
    """Bank-agnostic customer/account/activity view used by all agents.

    Implied schema 1.0.0 — no schema_version field yet. Versioning mechanism: PLAN.md.
    """

    institution_id: str
    institution_name: str
    as_of: datetime
    customer: Party
    accounts: list[Account]
    transactions: list[Transaction]
    mapping_notes: list[str] = Field(default_factory=list)


class TransferIntent(BaseModel):
    institution_id: str
    from_account_id: str
    to_account_id: str
    amount: Money
    memo: str = ""
    actor: str = "operator"


class ReplayStepKind(StrEnum):
    NAVIGATE = "navigate"
    FILL = "fill"
    SUBMIT = "submit"
    ASSERT = "assert"
    POST = "post"


class ReplayStep(BaseModel):
    kind: ReplayStepKind
    description: str
    locator: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)  # locators/masked ids/amount only — never native bodies
    ok: bool = True
    detail: str = ""


class DiscoveryField(BaseModel):
    canonical_path: str
    native_path: str
    locator: str | None = None
    sample: Any = None  # kind token only (`<id>`, `<money>`), never a live extract value
    value_kind: str = "string"
    confidence: float = 1.0


class DiscoveryAction(BaseModel):
    name: str
    locator: str
    method: str = "click"
    canonical_intent: str | None = None


class DiscoveryReport(BaseModel):
    institution_id: str
    ui_url: str
    discovered_at: datetime
    fields: list[DiscoveryField]
    actions: list[DiscoveryAction]
    unmapped_native_paths: list[str] = Field(default_factory=list)
    missing_canonical_paths: list[str] = Field(default_factory=list)
    confidence: float  # demo 0–1; hold on this vs IAI_DISCOVERY_MIN_CONFIDENCE
    page_contract: dict[str, Any] = Field(default_factory=dict)


class EscalationSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationReason(StrEnum):
    """Stable codes for the hold queue. Add a member instead of stuffing text into summary."""

    LOW_DISCOVERY_CONFIDENCE = "low_discovery_confidence"
    UNMAPPED_FIELDS = "unmapped_fields"
    REPLAY_STEP_FAILED = "replay_step_failed"
    AMOUNT_THRESHOLD = "amount_threshold"
    ACCOUNT_STATUS = "account_status"
    UNRESOLVED_ACCOUNT = "unresolved_account"
    POLICY = "policy"  # same-account *or* insufficient funds — split if you need to filter


class EscalationCase(BaseModel):
    id: str
    created_at: datetime
    institution_id: str
    severity: EscalationSeverity
    reasons: list[EscalationReason]
    summary: str
    context: dict[str, Any] = Field(default_factory=dict)
    status: str = "open"


class ReplayResult(BaseModel):
    run_id: str
    institution_id: str
    intent: TransferIntent
    started_at: datetime
    finished_at: datetime
    steps: list[ReplayStep]
    succeeded: bool
    native_receipt: dict[str, Any] | None = None
    escalation_id: str | None = None
