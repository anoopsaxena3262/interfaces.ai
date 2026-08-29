"""Walk locators plus the native extract; score coverage. Does not mutate ledgers.

Vite's first HTML is an empty #app, so we fall back to data/contracts/<id>.html.
NATIVE_HINTS must stay aligned with adapters — it is a second map of the same extract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from interfaces_ai.config import Settings, get_settings
from interfaces_ai.observability import get_logger
from interfaces_ai.redact import sample_kind
from interfaces_ai.schema.adapters import get_adapter
from interfaces_ai.schema.canonical import DiscoveryAction, DiscoveryField, DiscoveryReport
from interfaces_ai.schema.registry import ROOT, get_institution, load_native

CONTRACT_DIR = ROOT / "data" / "contracts"
log = get_logger("interfaces_ai.discovery")

CANONICAL_REQUIRED = (
    "customer.id",
    "customer.display_name",
    "accounts[].id",
    "accounts[].type",
    "accounts[].available",
    "accounts[].current",
    "transactions[].id",
    "transactions[].amount",
)

# Parallel to adapters: canonical path → native path. A fourth bank needs a block here.
NATIVE_HINTS: dict[str, dict[str, str]] = {
    "redwood": {
        "customer.id": "household.partyKey",
        "customer.display_name": "household.primary.given+surname",
        "accounts[].id": "products.deposits[].productInstance",
        "accounts[].type": "products.deposits[].kind",
        "accounts[].available": "products.deposits[].position.avail",
        "accounts[].current": "products.deposits[].position.ledger",
        "transactions[].id": "posted[].ref",
        "transactions[].amount": "posted[].signed",
    },
    "northstar": {
        "customer.id": "memberRec.mbrNo",
        "customer.display_name": "memberRec.nmLine",
        "accounts[].id": "suffixList[].sfx",
        "accounts[].type": "suffixList[].cls",
        "accounts[].available": "suffixList[].avail",
        "accounts[].current": "suffixList[].bal",
        "transactions[].id": "actv[].id",
        "transactions[].amount": "actv[].cents",
    },
    "calloway": {
        "customer.id": "cust.cif",
        "customer.display_name": "cust.name1",
        "accounts[].id": "acct_rel[].n",
        "accounts[].type": "acct_rel[].t",
        "accounts[].available": "acct_rel[].a",
        "accounts[].current": "acct_rel[].l",
        "transactions[].id": "hist[].k",
        "transactions[].amount": "hist[].p",
    },
}


class DiscoveryAgent:
    """Walk a bank's published locators plus its native extract.

    The TypeScript pages are client-rendered, so a raw GET of /redwood will not
    contain data-iai attributes. Published HTML under data/contracts/ is the
    contract the agent uses unless a test injects live markup.
    """

    def __init__(self, settings: Settings | None = None, html_loader=None) -> None:
        self.settings = settings or get_settings()
        self._html_loader = html_loader or _default_html_loader

    def discover(self, institution_id: str, html: str | None = None) -> DiscoveryReport:
        inst = get_institution(institution_id)
        ui_url = f"{self.settings.bank_ui_base_url.rstrip('/')}{inst.ui_path}"
        injected = html is not None
        page_html = html if html is not None else self._html_loader(ui_url)
        html_source = "injected" if injected else ("live" if page_html else "live_empty")
        contract = extract_page_contract(page_html) if page_html else {}
        # Empty SPA: published contract is the locator source of truth for this sandbox.
        if not contract.get("fields"):
            snapshot_html = _published_contract_html(institution_id)
            if snapshot_html:
                page_html = snapshot_html
                contract = extract_page_contract(page_html)
                html_source = "published_contract"
        native = load_native(institution_id)
        adapter = get_adapter(institution_id)
        snapshot = adapter.to_canonical(native)

        log.info(
            "discover start institution=%s html_source=%s locator_fields=%s actions=%s",
            institution_id,
            html_source,
            len(contract.get("fields") or []),
            len(contract.get("actions") or []),
        )

        hints = NATIVE_HINTS[institution_id]
        locators = {item["canonical"]: item.get("locator") for item in contract.get("fields", [])}
        fields: list[DiscoveryField] = []
        missing: list[str] = []
        for path in CANONICAL_REQUIRED:
            native_path = hints.get(path)
            sample = _sample_for(snapshot, path)
            if native_path is None or sample is None:
                missing.append(path)
                continue
            kind = sample_kind(path)
            fields.append(
                DiscoveryField(
                    canonical_path=path,
                    native_path=native_path,
                    locator=locators.get(path),
                    sample=kind,
                    value_kind=kind.strip("<>"),
                    confidence=1.0 if locators.get(path) else 0.82,
                )
            )
            log.debug(
                "discover field institution=%s path=%s native_path=%s locator=%s sample=%s",
                institution_id,
                path,
                native_path,
                "yes" if locators.get(path) else "no",
                kind,
            )

        unmapped = _unmapped_native_paths(institution_id, native)
        actions = [
            DiscoveryAction(
                name=item["name"],
                locator=item["locator"],
                method=item.get("method", "click"),
                canonical_intent=item.get("intent"),
            )
            for item in contract.get("actions", [])
        ]

        # Demo 0–1: coverage dominates; locators/submit nudge up; leftover keys nudge down.
        locator_bonus = 0.08 if locators else 0.0
        coverage = len(fields) / max(len(CANONICAL_REQUIRED), 1)
        action_bonus = 0.05 if any(a.canonical_intent == "transfer.submit" for a in actions) else 0.0
        gap_penalty = min(0.15, 0.03 * len(unmapped))
        confidence = round(min(1.0, coverage * 0.9 + locator_bonus + action_bonus - gap_penalty), 3)

        log.info(
            "discover done institution=%s confidence=%s coverage=%s/%s missing=%s unmapped=%s submit=%s",
            institution_id,
            confidence,
            len(fields),
            len(CANONICAL_REQUIRED),
            missing or "none",
            unmapped or "none",
            any(a.canonical_intent == "transfer.submit" for a in actions),
        )

        return DiscoveryReport(
            institution_id=institution_id,
            ui_url=ui_url,
            discovered_at=datetime.now(UTC),
            fields=fields,
            actions=actions,
            unmapped_native_paths=unmapped,
            missing_canonical_paths=missing,
            confidence=confidence,
            page_contract=contract,
        )


def extract_page_contract(html: str) -> dict[str, Any]:
    """Pull data-iai-* marks into a dict. Used for both live GET and published HTML."""
    soup = BeautifulSoup(html, "html.parser")
    page = soup.find(attrs={"data-iai-page": True})
    fields = []
    for node in soup.find_all(attrs={"data-iai-field": True}):
        fields.append(
            {
                "name": node.get("data-iai-field"),
                "canonical": node.get("data-iai-canonical"),
                "locator": f"[data-iai-field='{node.get('data-iai-field')}']",
                "tag": node.name,
            }
        )
    actions = []
    for node in soup.find_all(attrs={"data-iai-action": True}):
        actions.append(
            {
                "name": node.get("data-iai-action"),
                "locator": f"[data-iai-action='{node.get('data-iai-action')}']",
                "method": node.get("data-iai-method", "click"),
                "intent": node.get("data-iai-canonical"),
            }
        )
    return {
        "page": page.get("data-iai-page") if page else None,
        "institution": page.get("data-iai-institution") if page else None,
        "fields": fields,
        "actions": actions,
    }


def _published_contract_html(institution_id: str) -> str:
    path = CONTRACT_DIR / f"{institution_id}.html"
    if path.exists():
        return path.read_text()
    return ""


def _default_html_loader(url: str) -> str:
    import httpx

    try:
        response = httpx.get(url, timeout=3.0)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as exc:
        # No response body — it can contain customer names from the portal.
        log.warning("discover html fetch failed url=%s error=%s", url, type(exc).__name__)
        return ""


def _sample_for(snapshot, path: str):
    """Presence check only. The live value is discarded; DiscoveryField.sample is a kind token."""
    if path.startswith("customer."):
        return getattr(snapshot.customer, path.split(".", 1)[1], None)
    if path.startswith("accounts[].") and snapshot.accounts:
        attr = path.split(".", 1)[1]
        value = getattr(snapshot.accounts[0], attr)
        return value.as_float() if hasattr(value, "as_float") else value
    if path.startswith("transactions[].") and snapshot.transactions:
        attr = path.split(".", 1)[1]
        value = getattr(snapshot.transactions[0], attr)
        return value.as_float() if hasattr(value, "as_float") else value
    return None


def _unmapped_native_paths(institution_id: str, native: dict[str, Any]) -> list[str]:
    """Hardcoded leftovers (not a full dump walk). routing/header/sys are never copied into the snapshot."""
    extras = {
        "redwood": ["routing"],
        "northstar": ["header"],
        "calloway": ["sys"],
    }
    return [path for path in extras.get(institution_id, []) if _has_path(native, path)]


def _has_path(payload: dict[str, Any], path: str) -> bool:
    return path in payload
