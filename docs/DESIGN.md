# Design notes

Field-level choices (extract shapes, locators, hold table). For the overall plan see [PLAN.md](PLAN.md). For concepts see [GUIDE.md](GUIDE.md). For step-by-step hold and post checks see [SCENARIOS.md](SCENARIOS.md).

## Why three extracts

The three files are written so a single parser would fail:

| Bank | Identity | Accounts | Money | Dates / signs |
| --- | --- | --- | --- | --- |
| Redwood | `household.partyKey`, given + surname | `products.deposits[]`, `kind` demand/parked | decimal **strings** | ISO date, signed string |
| Northstar | `mbrNo`, `nmLine` = `LAST, FIRST M` | `suffixList[]`, `cls` SD/SV | **integer cents** | `YYYYMMDD`, signed cents |
| Calloway | `cust.cif`, `name1` already FIRST LAST | `acct_rel[]`, `t` CK/SV/LN | cents | ISO date, sign on `hist[].s` |

Shared snapshot fields are in `src/interfaces_ai/schema/canonical.py` and `data/schemas/canonical.schema.json`. Amounts are Decimal, never float, once they leave an adapter.

## Locator attributes

Interactive nodes in the TypeScript pages carry:

- `data-iai-page` / `data-iai-institution`
- `data-iai-field` + `data-iai-canonical`
- `data-iai-action` (transfer submit)

Because Vite serves an empty `#app` on first HTML, discovery also has static copies under `data/contracts/`. If you add a field to a page, add it to that HTML file in the same change.

## Replay

A transfer intent names canonical account ids. The adapter builds the bank body (Redwood `debitInstance` / `majorUnits`, Northstar `fromSfx` / `cents`, Calloway `from_n` / `p`) and mutates only its own structure.

## When a hold opens

| Condition | Reason |
| --- | --- |
| Discovery score below `IAI_DISCOVERY_MIN_CONFIDENCE` (default 0.72) | `low_discovery_confidence` |
| A required snapshot path is missing | `unmapped_fields` |
| Amount ≥ `IAI_TRANSFER_ESCALATION_USD` (default 5000) | `amount_threshold` |
| Either account is not `open` (Calloway HOLD maps to `hold`) | `account_status` |
| Same account or amount above available | `policy` |
| A replay step failed | `replay_step_failed` |

## Out of scope for this sandbox

Login, MFA, a real browser crawler, an LLM, ACH, and durable storage across restarts.
