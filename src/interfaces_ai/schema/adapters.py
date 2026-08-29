"""Anti-corruption layer: one class per bank.

Replay must not grow `if institution_id == ...` posting trees. Unit conversion
(string dollars vs integer cents) lives here only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from interfaces_ai.schema.canonical import (
    Account,
    AccountType,
    CanonicalSnapshot,
    Money,
    Party,
    Transaction,
    TransactionDirection,
    TransferIntent,
)

# Native product codes → snapshot enum. Keys are bank-specific; values are shared.
KIND_TO_TYPE = {
    "demand": AccountType.CHECKING,  # Redwood
    "SD": AccountType.CHECKING,  # Northstar share draft
    "CK": AccountType.CHECKING,  # Calloway
    "parked": AccountType.SAVINGS,  # Redwood
    "SV": AccountType.SAVINGS,
    "LN": AccountType.LOAN,  # Calloway LOC
}


def as_money(value: float | int | str, currency: str = "USD") -> Money:
    """Redwood-style decimal strings (and numbers) → Money. str() avoids float binary error."""
    return Money(amount=Decimal(str(value)), currency=currency)


def cents_to_money(cents: int, currency: str = "USD") -> Money:
    """Northstar/Calloway integer cents → Money with two decimal places."""
    return Money(amount=(Decimal(int(cents)) / Decimal(100)).quantize(Decimal("0.01")), currency=currency)


def parse_day(value: Any) -> date:
    """ISO date or compact YYYYMMDD (Northstar `day`)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date {value!r}")


def _receipt_id() -> str:
    return f"rcpt-{uuid4().hex[:8]}"


class NativeAdapter(ABC):
    """Inbound extract → snapshot; intent → bank body; mutate that bank's working JSON."""

    institution_id: str
    institution_name: str

    @abstractmethod
    def to_canonical(self, native: dict[str, Any]) -> CanonicalSnapshot: ...

    @abstractmethod
    def to_native_transfer(self, intent: TransferIntent, snapshot: CanonicalSnapshot) -> dict[str, Any]: ...

    @abstractmethod
    def apply_transfer(
        self,
        native: dict[str, Any],
        payload: dict[str, Any],
        intent: TransferIntent,
        source: Account,
        dest: Account,
    ) -> dict[str, Any]: ...

    def account_by_id(self, snapshot: CanonicalSnapshot, account_id: str) -> Account:
        for account in snapshot.accounts:
            if account.id == account_id:
                return account
        raise KeyError(account_id)


class RedwoodAdapter(NativeAdapter):
    """Household + products tree. Balances are decimal strings, not numbers."""

    institution_id = "redwood"
    institution_name = "Redwood Community Bank"

    def to_canonical(self, native: dict[str, Any]) -> CanonicalSnapshot:
        primary = native["household"]["primary"]
        deposits = native.get("products", {}).get("deposits", [])
        accounts = []
        for row in deposits:
            kind = str(row.get("kind", ""))
            pos = row["position"]
            accounts.append(
                Account(
                    id=row["productInstance"],
                    masked_number=row.get("mask", ""),
                    name=row.get("nickname", row["productInstance"]),
                    type=KIND_TO_TYPE.get(kind, AccountType.UNKNOWN),
                    available=as_money(pos["avail"], pos.get("iso", "USD")),
                    current=as_money(pos["ledger"], pos.get("iso", "USD")),
                    # lifecycle active → open; other values pass through as status strings.
                    status="open" if row.get("lifecycle", "active") == "active" else str(row["lifecycle"]),
                    native_ref={"productInstance": row["productInstance"], "kind": kind},
                )
            )
        txns = []
        for row in native.get("posted", []):
            signed = Decimal(str(row["signed"]))
            direction = TransactionDirection.DEBIT if signed < 0 else TransactionDirection.CREDIT
            txns.append(
                Transaction(
                    id=row["ref"],
                    account_id=row["productInstance"],
                    posted_on=parse_day(row["on"]),
                    description=row.get("note", ""),
                    amount=as_money(abs(signed)),
                    direction=direction,
                    native_ref={"ref": row["ref"]},
                )
            )
        # fromisoformat rejects a trailing Z; normalize to offset form.
        as_of = datetime.fromisoformat(native["extractedAt"].replace("Z", "+00:00"))
        return CanonicalSnapshot(
            institution_id=self.institution_id,
            institution_name=self.institution_name,
            as_of=as_of,
            customer=Party(
                id=native["household"]["partyKey"],
                display_name=f"{primary['given']} {primary['surname']}".strip(),
                email=primary.get("mail"),
                phone=primary.get("tel"),
                native_id_field="household.partyKey",
            ),
            accounts=accounts,
            transactions=txns,
            mapping_notes=[
                "household.partyKey is the customer id",
                "products.deposits[].position.avail is a decimal string",
                "posted[].signed is a signed decimal string",
            ],
        )

    def to_native_transfer(self, intent: TransferIntent, snapshot: CanonicalSnapshot) -> dict[str, Any]:
        source = self.account_by_id(snapshot, intent.from_account_id)
        dest = self.account_by_id(snapshot, intent.to_account_id)
        return {
            "debitInstance": source.id,
            "creditInstance": dest.id,
            "majorUnits": str(intent.amount.amount),
            "iso": intent.amount.currency,
            "note": intent.memo,
        }

    def apply_transfer(self, native, payload, intent, source, dest) -> dict[str, Any]:
        # Keep avail/ledger as strings so the next to_canonical still sees Redwood's type.
        amount = Decimal(payload["majorUnits"])
        for row in native["products"]["deposits"]:
            pos = row["position"]
            if row["productInstance"] == payload["debitInstance"]:
                pos["avail"] = str(Decimal(pos["avail"]) - amount)
                pos["ledger"] = str(Decimal(pos["ledger"]) - amount)
            if row["productInstance"] == payload["creditInstance"]:
                pos["avail"] = str(Decimal(pos["avail"]) + amount)
                pos["ledger"] = str(Decimal(pos["ledger"]) + amount)
        today = datetime.now(UTC).date().isoformat()
        rid = _receipt_id()
        # Prepend so portals show the newest activity first (same as the seed).
        native["posted"][:0] = [
            {
                "ref": f"{rid}-cr",
                "on": today,
                "note": intent.memo or "book transfer",
                "signed": str(amount),
                "productInstance": payload["creditInstance"],
            },
            {
                "ref": f"{rid}-db",
                "on": today,
                "note": intent.memo or "book transfer",
                "signed": str(-amount),
                "productInstance": payload["debitInstance"],
            },
        ]
        return {"receipt_id": rid, "native_payload": payload, "from_account_id": source.id, "to_account_id": dest.id}


class NorthstarAdapter(NativeAdapter):
    """Credit-union member record. Suffixes, class codes, amounts in integer cents."""

    institution_id = "northstar"
    institution_name = "Northstar FCU"

    def to_canonical(self, native: dict[str, Any]) -> CanonicalSnapshot:
        member = native["memberRec"]
        # nmLine is "LAST, FIRST M" — snapshot wants FIRST LAST.
        last, _, rest = member["nmLine"].partition(",")
        display = f"{rest.strip()} {last.strip()}".strip()
        accounts = []
        for row in native.get("suffixList", []):
            # Core code A = active; anything else is treated as hold for replay.
            stat = "open" if row.get("stat") == "A" else "hold"
            accounts.append(
                Account(
                    id=str(row["sfx"]),
                    masked_number=f"••••{row['sfx']}",
                    name=row.get("ttl", row["sfx"]),
                    type=KIND_TO_TYPE.get(str(row.get("cls", "")), AccountType.UNKNOWN),
                    available=cents_to_money(int(row["avail"])),
                    current=cents_to_money(int(row["bal"])),
                    status=stat,
                    native_ref={"sfx": row["sfx"], "cls": row.get("cls")},
                )
            )
        txns = []
        for row in native.get("actv", []):
            cents = int(row["cents"])
            direction = TransactionDirection.DEBIT if cents < 0 else TransactionDirection.CREDIT
            txns.append(
                Transaction(
                    id=str(row["id"]),
                    account_id=str(row["sfx"]),
                    posted_on=parse_day(row["day"]),
                    description=row.get("txt", ""),
                    amount=cents_to_money(abs(cents)),
                    direction=direction,
                    native_ref={"id": row["id"]},
                )
            )
        as_of = datetime.fromtimestamp(int(native["header"]["asOfEpoch"]), tz=UTC)
        return CanonicalSnapshot(
            institution_id=self.institution_id,
            institution_name=self.institution_name,
            as_of=as_of,
            customer=Party(
                id=str(member["mbrNo"]),
                display_name=display,
                email=member.get("eml"),
                phone=_phone(member.get("ph10")),
                native_id_field="memberRec.mbrNo",
            ),
            accounts=accounts,
            transactions=txns,
            mapping_notes=[
                "memberRec.nmLine is LAST, FIRST M",
                "suffixList[].avail is integer cents",
                "stat A means open; anything else is treated as hold",
            ],
        )

    def to_native_transfer(self, intent: TransferIntent, snapshot: CanonicalSnapshot) -> dict[str, Any]:
        source = self.account_by_id(snapshot, intent.from_account_id)
        dest = self.account_by_id(snapshot, intent.to_account_id)
        cents = int((intent.amount.amount * 100).to_integral_value())
        return {
            "fromSfx": source.id,
            "toSfx": dest.id,
            "cents": cents,
            "txt": intent.memo,
        }

    def apply_transfer(self, native, payload, intent, source, dest) -> dict[str, Any]:
        cents = int(payload["cents"])
        for row in native["suffixList"]:
            if str(row["sfx"]) == payload["fromSfx"]:
                row["avail"] -= cents
                row["bal"] -= cents
            if str(row["sfx"]) == payload["toSfx"]:
                row["avail"] += cents
                row["bal"] += cents
        today = datetime.now(UTC).date().strftime("%Y%m%d")  # actv.day is compact, not ISO
        rid = _receipt_id()
        next_id = max(int(row["id"]) for row in native["actv"]) + 1 if native["actv"] else 1
        native["actv"][:0] = [
            {
                "id": next_id + 1,
                "day": today,
                "txt": intent.memo or "sfx xfer",
                "cents": cents,
                "sfx": payload["toSfx"],
            },
            {
                "id": next_id,
                "day": today,
                "txt": intent.memo or "sfx xfer",
                "cents": -cents,
                "sfx": payload["fromSfx"],
            },
        ]
        return {"receipt_id": rid, "native_payload": payload, "from_account_id": source.id, "to_account_id": dest.id}


class CallowayAdapter(NativeAdapter):
    """State-bank dump: short keys, separate sign, HOLD status on a line of credit."""

    institution_id = "calloway"
    institution_name = "Calloway State Bank"

    def to_canonical(self, native: dict[str, Any]) -> CanonicalSnapshot:
        cust = native["cust"]
        accounts = []
        for row in native.get("acct_rel", []):
            # s: OK → open; HOLD (and any other flag) → hold so replay stops before post.
            status = "open" if row.get("s") == "OK" else "hold"
            accounts.append(
                Account(
                    id=str(row["n"]),
                    masked_number=row.get("m", ""),
                    name=row.get("d", row["n"]),
                    type=KIND_TO_TYPE.get(str(row.get("t", "")), AccountType.UNKNOWN),
                    available=cents_to_money(int(row["a"])),
                    current=cents_to_money(int(row["l"])),
                    status=status,
                    native_ref={"n": row["n"], "t": row.get("t")},
                )
            )
        txns = []
        for row in native.get("hist", []):
            # Sign is hist[].s; p is always a positive cent amount.
            direction = TransactionDirection.DEBIT if row.get("s") == "-" else TransactionDirection.CREDIT
            txns.append(
                Transaction(
                    id=str(row["k"]),
                    account_id=str(row["n"]),
                    posted_on=parse_day(row["ymd"]),
                    description=row.get("t", ""),
                    amount=cents_to_money(int(row["p"])),
                    direction=direction,
                    native_ref={"k": row["k"]},
                )
            )
        stamp = native.get("extractedAt", "2026-08-28T12:00:00+00:00")
        as_of = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return CanonicalSnapshot(
            institution_id=self.institution_id,
            institution_name=self.institution_name,
            as_of=as_of,
            customer=Party(
                id=str(cust["cif"]),
                display_name=str(cust["name1"]).title(),  # already FIRST LAST; title() for display only
                email=cust.get("email"),
                phone=cust.get("voice"),
                native_id_field="cust.cif",
            ),
            accounts=accounts,
            transactions=txns,
            mapping_notes=[
                "cust.name1 is already FIRST LAST in this dump",
                "hist[].s is the sign; p is always a positive cent amount",
                "acct_rel[].s HOLD is mapped to status=hold",
            ],
        )

    def to_native_transfer(self, intent: TransferIntent, snapshot: CanonicalSnapshot) -> dict[str, Any]:
        source = self.account_by_id(snapshot, intent.from_account_id)
        dest = self.account_by_id(snapshot, intent.to_account_id)
        cents = int((intent.amount.amount * 100).to_integral_value())
        return {
            "from_n": source.id,
            "to_n": dest.id,
            "p": cents,
            "t": intent.memo,
        }

    def apply_transfer(self, native, payload, intent, source, dest) -> dict[str, Any]:
        cents = int(payload["p"])
        for row in native["acct_rel"]:
            if str(row["n"]) == payload["from_n"]:
                row["a"] -= cents
                row["l"] -= cents
            if str(row["n"]) == payload["to_n"]:
                row["a"] += cents
                row["l"] += cents
        today = datetime.now(UTC).date().isoformat()
        rid = _receipt_id()
        native["hist"][:0] = [
            {"k": f"{rid}c", "ymd": today, "t": intent.memo or "XFER", "s": "+", "p": cents, "n": payload["to_n"]},
            {"k": f"{rid}d", "ymd": today, "t": intent.memo or "XFER", "s": "-", "p": cents, "n": payload["from_n"]},
        ]
        return {"receipt_id": rid, "native_payload": payload, "from_account_id": source.id, "to_account_id": dest.id}


def _phone(value: Any) -> str | None:
    """Northstar ph10 is 10 digits with no punctuation."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 10:
        return f"+1-{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return str(value)


ADAPTERS: dict[str, NativeAdapter] = {
    adapter.institution_id: adapter
    for adapter in (RedwoodAdapter(), NorthstarAdapter(), CallowayAdapter())
}


def get_adapter(institution_id: str) -> NativeAdapter:
    try:
        return ADAPTERS[institution_id]
    except KeyError as exc:
        raise KeyError(f"Unknown institution '{institution_id}'") from exc
