# Developer guide — understanding the project

This guide is for someone who just cloned the repo and needs the mental model before changing code. Doc index with one-line descriptions: [README.md](../README.md#docs).

- **File inventory:** [CATALOG.md](CATALOG.md)
- **Runtime diagram and HTTP:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Field-level mapping and hold rules:** [DESIGN.md](DESIGN.md)
- **Step-by-step test scenarios:** [SCENARIOS.md](SCENARIOS.md)
- **How to add a bank or change a limit:** [DEVELOPER.md](DEVELOPER.md) (maintenance)
- **Overall plan:** [PLAN.md](PLAN.md) ([now vs later](PLAN.md#now-vs-later-sandbox-vs-product) — in repo vs not built) · **PII / PCI increment:** [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md) · **Discovery evals:** [PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md)

## First hour

1. `make setup && make dev` (or the two-terminal variant in the README).
2. Open http://127.0.0.1:5173 and click into all three banks. Notice the **labels on screen** still match the JSON (`productInstance`, `sfx`, `acct_rel`), not a cleaned-up “Account ID” everywhere.
3. Open http://127.0.0.1:8000/api/v1/institutions/redwood/native (portal JSON) and then `.../canonical` vs `.../canonical?view=agent`. Same customer; agent view has no email/phone/transactions.
4. Console → Run discovery, then replay $40 Redwood `CHK-77` → `SAV-12`. Check **Operator copies**: discovery samples are kinds (`<id>`, `<money>`), not live values.
5. Replay Calloway `900210001` → `900210099`. That is the HOLD path. Hold context in **Operator copies** is last-4 ids, not a full intent dump.
6. Skim `src/interfaces_ai/schema/canonical.py`, then one adapter in `adapters.py`.

If those six steps make sense, you understand the project. The rest of this file names the ideas you just used.

## Mental model (one sentence)

**Each bank speaks its own JSON; we translate at the edge; discovery / replay / holds only speak the shared snapshot.**

```text
  native extract          shared snapshot           bank-shaped write
  (Redwood / FCU / CSB)  (CanonicalSnapshot)     (adapter payload)
          |                      |                        |
          |  to_canonical()      |   TransferIntent       | apply_transfer()
          +--------------------->+----------------------->+
                                 |
                    discovery scores this
                    holds judge this
                    replay starts from this
```

You never teach replay “Redwood uses strings.” You teach the **Redwood adapter** that. Replay only knows `from_account_id` and `Money`.

## Key concepts

### Institution

A mock financial institution: `redwood`, `northstar`, or `calloway`. The id is the key used in URLs, adapters, seed files, and the TypeScript route.

Registry: `src/interfaces_ai/schema/registry.py`.

### Native extract

The JSON that bank would actually give you. Seeds live in `data/native/<id>.json`. After the API loads them, a **working copy** sits in memory (`load_native` / `save_native`). Restart or **Reset ledgers** reloads from disk.

The portals fetch native JSON and render it as-is.

### Shared snapshot (`CanonicalSnapshot`)

The bank-agnostic view: customer, accounts, transactions, mapping notes. Defined in `canonical.py`. This is what “standardize the schema” means in this repo.

Important properties:

- **Money** is `Decimal` + currency, serialized as a string. Adapters convert cents or numeric strings at the boundary. Do not use float for money inside Python.
- **Account ids stay native.** `CHK-77`, suffix `00`, and `900210001` are different strings on purpose. There is no global “checking id.”
- **`native_id_field` / `native_ref`** record where a snapshot row came from so a reviewer can walk back to the extract.

### Adapter

A Python class per bank: `to_canonical`, `to_native_transfer`, `apply_transfer`. This is the translation layer. If a fourth bank appears, you add a class — you do not teach discovery “about cents.”

### Locator / UI contract (`data-iai-*`)

Attributes on the TypeScript markup that say “this control is the transfer amount” in snapshot language:

```html
<input data-iai-field="amount" data-iai-canonical="transfer.amount" />
<button data-iai-action="transfer.submit" data-iai-canonical="transfer.submit">
```

Discovery parses those into CSS-style locators like `[data-iai-field='amount']`.

The live Vite page is a client-rendered SPA, so the **first** HTML GET does not contain these attributes. Published copies live in `data/contracts/<id>.html`. Discovery falls back to those files. If you add a control to a page, update the contract HTML in the same PR.

### Discovery

“What can we see, and how complete is the mapping?”

Inputs: institution id, optional HTML.  
Output: `DiscoveryReport` — mapped fields, actions, leftover native keys, missing required paths, a confidence score between 0 and 1.

It does not post transfers. A low score or missing required paths can open a **hold**.

Required snapshot paths (the coverage denominator) are `CANONICAL_REQUIRED` in `discovery.py`.

### Replay

“Run this snapshot-level transfer against that bank, and record what we did.”

Inputs: `TransferIntent` (and the latest discovery report if one exists, for locators).  
Output: `ReplayResult` — `run_id`, ordered `ReplayStep`s, `succeeded`, optional `native_receipt`, optional `escalation_id`, optional `idempotency_key`.

Step kinds: `navigate` → `fill` → `assert` (policy) → `submit` → `post`.

If policy fails, there is no `post`. You still get the step list.

### Transfer intent

The only transfer object modules share: institution, from id, to id, `Money`, memo. Account ids must already be that bank’s native ids (the console loads them from the snapshot).

### Hold / review (escalation module)

A local rules engine that may open an `EscalationCase`. Reasons are an enum (`amount_threshold`, `account_status`, `policy`, …). Severity is separate from reason.

Calloway’s personal LOC is the fixture: native `s: "HOLD"` becomes snapshot `status: "hold"`, which is not `open`, so replay stops.

This is **not** an LLM. Changing a dollar limit is an env var, not a prompt.

### Console vs bank portal

- **Bank portal** — looks like that FI’s site; still submits through replay.
- **Console** — operator surface: discovery scores, canonical preview, replay form, hold table.

Same API, different audience.

### In-memory `Store`

Discovery reports, replay runs, hold cases, and replay idempotency keys for this API process only. Not the same dict as working extracts. Both vanish on restart.

## How a successful Redwood transfer moves

1. UI or CLI builds `{ institution_id: "redwood", from_account_id: "CHK-77", to_account_id: "SAV-12", amount: 40 }` (portals also send `idempotency_key`).
2. API wraps that as `TransferIntent`.
3. Replay loads the working extract, adapter builds snapshot, resolves the two accounts.
4. Hold rules run (amount, status, same-account, available). $40 on open accounts passes.
5. `RedwoodAdapter.to_native_transfer` produces `{ debitInstance, creditInstance, majorUnits: "40.00", ... }`.
6. `apply_transfer` subtracts/adds **Decimal strings** on `position.avail` / `ledger` and prepends two `posted` rows.
7. `save_native` updates the working copy. Seed file on disk is unchanged.
8. Portal reload fetches native again; Everyday checking shows $40 less.

## How a blocked Calloway transfer moves

1. Intent: `900210001` → `900210099`, $20.
2. Snapshot maps `900210099` to type `loan`, status `hold`.
3. Hold module returns `account_status` (and `amount_threshold` too if you send ≥ $5,000).
4. Replay records a failed `assert` step, opens a case, **does not** call `apply_transfer`.
5. Console hold table shows the case id and reasons.

## How discovery scores a bank

1. Try to GET the live page; parse `data-iai-*`.
2. If no fields (empty SPA), read `data/contracts/<id>.html`.
3. Load native JSON, run `to_canonical`.
4. For each required snapshot path, look up `NATIVE_HINTS` and a sample value from the snapshot.
5. Confidence ≈ coverage of required paths, plus a small bonus if locators and `transfer.submit` exist, minus a penalty for leftover native keys (`routing`, `header`, `sys`).

You can run this without the UI: `iai discover`.

## Where to read in the code

Read in this order the first time:

| Order | File | What you learn |
| --- | --- | --- |
| 1 | `schema/canonical.py` | The shared vocabulary |
| 2 | `data/native/redwood.json` then `calloway.json` | How far apart two extracts are |
| 3 | `schema/adapters.py` (`RedwoodAdapter`, then `CallowayAdapter`) | Translation and posting |
| 4 | `schema/registry.py` | How an id becomes a file + adapter |
| 5 | `agents/replay.py` | Step machine |
| 6 | `agents/escalation.py` | Why a write is refused |
| 7 | `agents/discovery.py` | Scoring and locators |
| 8 | `api/routes.py` | HTTP wiring |
| 9 | `banks-ui/src/pages/redwood.ts` | Native rendering + `data-iai-*` |

Skip `banks-ui` CSS until you care about layout.

## Two processes

| Process | Port | Role |
| --- | --- | --- |
| Uvicorn | 8000 | Mapping, agents, working extracts |
| Vite | 5173 | Portals; proxies `/api` to 8000 |

If the hub loads but a bank page errors, the API is down. If discovery has JSON mapping but you expected live DOM locators, you are seeing the published-contract fallback — that is expected without a browser worker.

## Tests as executable docs

```bash
make test
```

- `test_schema.py` — mapping correctness (same person, same checking available, HOLD status)
- `test_replay.py` — write vs no-write
- `test_escalation.py` — distinct reason codes on one intent
- `test_discovery.py` — locators and fallback HTML
- `test_api.py` — institution list

`tests/conftest.py` resets working extracts around every test so a posting test cannot leak into the next.

## Vocabulary cheat sheet

| You might say | In this repo |
| --- | --- |
| Canonical model / standard schema | `CanonicalSnapshot` |
| Core export / bank JSON | Native extract |
| Connector / mapper | Adapter |
| RPA selector | Locator (`data-iai-canonical`) |
| Run a flow against a bank | Replay |
| Escalate to a human | Hold / `EscalationCase` |
| Customer | `Party` (id is whatever that core uses) |
| Share draft | Northstar suffix `00`, mapped to `checking` |

## When you are ready to change code

Use [DEVELOPER.md](DEVELOPER.md) for the checklist (fourth bank, new snapshot field, new hold reason). Come back here if a change would break the mental model — especially “portals must keep showing native keys” and “replay must not grow bank-specific posting.”
