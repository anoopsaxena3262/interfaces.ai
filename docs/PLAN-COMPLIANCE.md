# Plan: snapshot and log minimization (PII, PCI guard)

This is the increment that follows the [data-sensitivity section in PLAN.md](PLAN.md#data-sensitivity-pci-dss-and-pii). Overall design stays there. This file is the **how** for redaction, what stays on `CanonicalSnapshot`, and encryption. Operator console **Operator copies** and `GET /api/v1/runs` go through `redact_operator_screen`. Doc index: [README.md](../README.md#docs).

PCI DSS is **out of scope** for the current fixtures (no PAN/SAD). Banking PII is **in** the snapshot and every run copy. Do not encrypt the working snapshot to “solve” that.

## Problem

Three modules (discovery, replay, hold) are supposed to think in a small shared snapshot. They currently **re-copy live values** into places that look like audit logs:

| Surface | What leaks | Needed for processing? |
| --- | --- | --- |
| `GET …/canonical` and console preview | Full `Party` including email/phone | No (agents never read contact) |
| `DiscoveryField.sample` | Live customer.id, account id, balances, txn amounts | No (coverage is presence + type) |
| `ReplayStep` FILL / SUBMIT `payload` | from/to, amount, full native body, memo | Write path yes; **stored** copy no |
| `ReplayResult.native_receipt` | Receipt plus `native_payload` again | Receipt id yes; body no |
| `EscalationCase.context` | Full `TransferIntent`, failed step dump, `customer_id` | Reason codes + masked ids + amount band yes |
| `GET …/native` | Entire extract (email, phone, routing, DDA) | Portals yes; unauthenticated dump is a demo choice |
| Calloway `Account.id` = `acct_rel[].n` | Full-looking DDA (`900210001`) | Adapter posting yes; UI/logs should use `masked_number` |

Encrypting those blobs would still leave decryptable PII in `Store`. Minimizing what we persist is the control.

## Goals

| Goal | How we meet it |
| --- | --- |
| Agents keep enough to gate and post | Working snapshot in process still has ids, status, `Money`, native posting keys inside the adapter call |
| Run history is not a second extract | Stored discovery/replay/hold records are redacted |
| Contact PII is not an agent contract | Email/phone optional on `Party` for portals only; omitted from console preview and required discovery paths |
| PCI cannot arrive by accident | Adapter ingest rejects PAN-shaped and SAD fields; never persist CVV even encrypted |
| Encryption is a later, narrow tool | TLS off-localhost; field encryption only for residual durable DDA/contact if we keep them |

## Non-goals (this increment)

- Wholesale encryption of `CanonicalSnapshot` or of `Store`
- AuthN / TLS termination (still laptop HTTP; called out when we leave localhost)
- Removing email/phone from **native** portal JSON (native stays native)
- Tokenizing working ledgers so `apply_transfer` cannot see native ids
- A formal PCI ROC or QSA program
- Changing hold reason codes or dollar limits

## Design principles

1. **Working set vs copies.** Plaintext snapshot in RAM for one discover/replay call. Anything that outlives the call (Store, CLI stdout, `/runs`) is a copy and must be minimized.
2. **Presence, not samples.** Discovery scores “path mapped and typed.” A sample is `kind: decimal_money` or a constant mask (`••••`), never `2190.40` or `jordan.hale@example.net`.
3. **Native posting keys stay inside the adapter.** `ReplayStep.payload` records locators and masked ids, not the bank body. The body is built, used, discarded.
4. **Do not encrypt what you should not store.** PAN/SAD: reject. Email/phone on run logs: drop. Full DDA on hold context: hash or last-4.
5. **Portals still show native keys.** Redaction is on **our** snapshot preview, discovery reports, and replay history — not on Redwood’s household JSON.

## Field plan (keep / drop / transform)

| Field | Working snapshot | Stored run / hold | Console preview |
| --- | --- | --- | --- |
| `accounts[].id`, type, status | Keep | Hash or last-4 + institution | Masked + type/status |
| `accounts[].available` / `current` | Keep (policy) | Omit or coarse band (e.g. below/above limit) | Available only if we still demo policy |
| `accounts[].masked_number` | Keep | Keep | Keep |
| `customer.id` | Keep | HMAC | Keep (id is the demo correlation) |
| `customer.display_name` | Keep (hold UI) | Omit from discovery samples | First name or omit |
| `customer.email`, `phone` | Drop from agent views; allow on Party for portal mapping tests **or** stop mapping | Never | Never |
| `transactions[]` | Keep for portals via `/canonical` or native only | Do not sample amounts | Omit from console preview |
| `intent.amount`, from/to | Keep on in-flight intent | Amount + masked ids; drop memo | Form inputs only |
| Native transfer body | Adapter only | Never on `ReplayStep` | Never |
| Redwood `routing` | Do not map | Do not sample | Native page only |
| PAN / CVV | Reject | Never | Never |

Calloway posting can keep using `acct_rel[].n` **inside** `apply_transfer`. Public `Account.id` in logs should be the mask (`1104`) or a stable opaque token, not `900210001`, if we change the id scheme. Prefer **not** renaming ids in this increment (breaks demo scripts and tests); prefer masking in **copies**. Changing `Account.id` is a follow-on if we want UI to stop showing full DDA.

## Module plan

### Discovery (`discovery.py`)

- Stop `_sample_for` from writing live values. Store `value_kind` (string / money / id) and `present: true`.
- Remove customer display name from `CANONICAL_REQUIRED` if we decide it is display-only (keep `customer.id`).
- Leftovers (`routing`, `header`, `sys`) stay names only — never dump the routing number into the report.

### Replay (`replay.py`)

- FILL step: locators + masked from/to + amount (amount is the intent; it is also financial PII — keep for the demo audit of “what we tried,” or replace with `amount_usd >= threshold` boolean plus exact amount only on succeeded post). **Choice:** keep exact amount on the run (needed to explain a hold); mask account ids.
- SUBMIT step: locator + `ok`; **no** `native_payload`.
- POST step: `receipt_id` only (already close).
- `native_receipt`: `{ receipt_id }` plus masked from/to. Drop nested `native_payload`.

### Hold (`escalation.py`)

- `context` for transfers: institution, reason codes, statuses, amount, masked account ids. No `intent.model_dump()`, no failed step `payload`.
- `customer_id` in replay-failure context: HMAC or omit.

### Snapshot / adapters (`canonical.py`, `adapters.py`)

- Keep mapping email/phone for schema tests **or** move contact to a `PartyContact` that `/canonical` can omit via a query flag (`?view=agent`). Prefer a **response filter** on `/canonical` used by console vs a second model, so adapters stay one mapping.
- Ingest guard: if a native string matches PAN (Luhn, 13–19 digits) or keys named like `cvv`/`cvc`/`pan`, fail the adapter with a clear error. Do not copy into `native_ref`.

### API / CLI / console

- `/runs` and `/escalations` return already-redacted Store objects (redact at write time, not only at GET).
- CLI `iai canonical` is a debug dump of the working snapshot — document as **not** an audit log; optional `--agent-view` that strips contact and transactions.
- Console preview: customer id + display name, accounts as id/type/status/available — **no** email/phone (today it dumps `snapshot.customer`).

### Encryption (later, not this PR)

Only after Store is durable:

- TLS in front of the API.
- Application-level AES-GCM (or KMS) for columns that still hold full DDA or contact if product requires them.
- Log pipelines: structured fields only; deny-list PAN regex at the logger.

Not in this increment’s code.

## Phased delivery

**Phase 1 — copies (implemented)**

1. Discovery samples are kind tokens (`<id>`, `<money>`, …), not live extract values. `_sample_for` is a presence check only.
2. Replay SUBMIT payload is empty; stored receipt is `{receipt_id}` only. Hold context has last-4 ids, amount, statuses — not `intent.model_dump()`.
3. Console snapshot preview omits email/phone. **Operator copies** panel shows discovery samples and hold context from `redact_operator_screen` (GET `/runs`).
4. Tests: `test_discovery_samples_are_kinds_not_live_values`, replay JSON has no `majorUnits` / `fromSfx` / `native_payload`, hold context has no `memo` / `mail` / `eml`.

**Phase 2 — agent view of the snapshot (implemented)**

1. `GET /canonical?view=agent` omits `customer.email`, `customer.phone`, and `transactions`. Default GET is still the full in-process snapshot (schema tests and debug dumps).
2. Console fetches `?view=agent`. `iai canonical --agent-view` is the same filter. Full `iai canonical` is **not** an audit log.
3. `/native` remains the portal contract (full extract). Unauthenticated `/native` is demo-only.

**Phase 3 — ingest guard (implemented)**

1. Shared detector in `cardholder.py`: SAD keys (`pan`, `cvv`, `cvc`, …) and 13–19 digit strings that pass **Luhn**. Short DDA/routing (Calloway `900210001`, ABA) are not PANs.
2. `NativeAdapter.to_canonical` and first `load_native` of a seed both call `reject_cardholder_data`. HTTP maps that to `422`.
3. Tests use a published Visa **test** PAN in a throwaway dict (`tests/test_cardholder.py`). Never commit PAN into `data/native/`.

**Phase 4 — only if Store becomes durable** (see PLAN later table)

1. HMAC secret for account ids in logs (env, not git).
2. Field encryption for residual DDA/contact.
3. TLS.

## Test plan

| Claim | Test |
| --- | --- |
| Discovery does not echo live PII | `test_discovery.py` — sample is kind/presence; body has no email, no `510-555` |
| Successful replay history has no native body | `test_replay.py` — SUBMIT payload empty or locators only; receipt has `receipt_id` |
| Hold context has no full intent dump | `test_escalation.py` — no `memo` key, no email |
| Operator `/runs` is redacted | `test_api.py` — discover + Calloway HOLD, then GET `/runs` |
| Unknown id / bad amount | `test_api.py` — 404 and 422 |
| Console/agent canonical omits contact | `test_api.py` — `?view=agent` on all three banks; `test_redact.py` `agent_snapshot_view`; `test_cli.py` `--agent-view` |
| PAN-shaped native field is rejected | `test_cardholder.py` — published test PAN + `cvv`/`cvc` keys; non-Luhn 16-digit allowed; `test_api.py` 422 on dirty working extract |
| Mapping still works | Existing `test_schema.py` name + checking $2190.40 on **in-process** snapshot |

## Files to touch

| File | Change |
| --- | --- |
| `src/interfaces_ai/redact.py` | `agent_snapshot_view`; kinds / last-4 |
| `src/interfaces_ai/cardholder.py` | Luhn + SAD/PAN walk |
| `src/interfaces_ai/schema/adapters.py` | `to_canonical` calls ingest guard then `map_to_canonical` |
| `src/interfaces_ai/schema/registry.py` | `load_native` rejects cardholder data on first read |
| `src/interfaces_ai/api/routes.py` | `view=agent`; 422 on ingest reject |
| `banks-ui/src/pages/console.ts` | Preview via `?view=agent` |
| `tests/test_discovery.py`, `test_replay.py`, `test_escalation.py`, `test_api.py`, `test_cardholder.py` | Assertions above |
| `docs/DESIGN.md` | Note hold `context` is redacted |
| `docs/SCENARIOS.md` | Console preview no longer shows email |

Do not add a crypto dependency in Phase 1–3. Phase 1–3 are in the agents, `cardholder.py`, `?view=agent`, console, and tests listed above.

## Success

Someone can `GET /api/v1/runs` after discovery + a blocked Northstar $9000 replay and **not** retrieve Jordan’s email, phone, or a bank-shaped transfer body. `GET /canonical?view=agent` has no contact or transactions. A Luhn-valid test PAN in a throwaway extract is rejected, not mapped. Policy still blocks. Redwood $40 still posts. Native portals still show `mail` / `eml` / `voice` on the bank pages. No encryption theater on the in-memory snapshot.

## Relationship to PLAN.md

- Principles in PLAN (native portals, one write path, adapters own mutation) **do not change**.
- Later row **Snapshot and run-log minimization** is this document. [PLAN.md now vs later](PLAN.md#now-vs-later-sandbox-vs-product): Phase 1–3 **in repo**; Phase 4 **product** (after durable Store).
- Durable `Store` in PLAN must not ship without Phase 1, or holds become a PII warehouse.
