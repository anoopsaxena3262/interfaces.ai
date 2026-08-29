# Design plan

This is the overall plan for the sandbox: what problem it is solving, what we chose to build, and what we deliberately left out.

If you are new to the repo, read [GUIDE.md](GUIDE.md) first. This document is the “why,” not the file-by-file map. Runtime details live in [ARCHITECTURE.md](ARCHITECTURE.md).

## Problem

Community banks and credit unions do not share a data model. One core exports a nested household tree with balances as strings. Another exports credit-union suffixes in integer cents. A third looks like a 1990s inquiry screen with one-letter keys.

An automation layer that wants to “move $40 from checking to savings” cannot speak those three languages at once. It needs:

1. A **shared snapshot** so intents and policy are written once.
2. A way to **discover** what a given bank UI and extract actually contain.
3. A way to **replay** a shared intent as that bank’s own request body.
4. A way to **stop** when the write is too large, the account is on hold, or mapping failed.

This repo is a local, fully runnable sketch of that stack. Three TypeScript portals stand in for online banking. Python owns mapping and the three modules.

## Goals

| Goal | How we meet it |
| --- | --- |
| Make schema mismatch visible | Each portal renders **native** JSON keys, not the snapshot |
| One transfer vocabulary | `TransferIntent` + `CanonicalSnapshot` in Pydantic |
| Isolate bank quirks | One adapter class per institution, including `apply_transfer` |
| Show discovery is not “just parse JSON” | Locators (`data-iai-*`) plus extract coverage score |
| Show replay is inspectable | Ordered steps even when the write is blocked |
| Show holds are reviewable | Enum reason codes, not a free-text LLM guess |
| Run on a laptop | No API keys, no browser worker, `make dev` |

## Non-goals (this sandbox)

- Real login, MFA, session cookies
- Playwright / Chromium crawling of the live DOM
- An LLM in the loop
- ACH, wires, cards, or multi-customer datasets
- Postgres or any durability across process restart
- Pixel-perfect copies of real bank sites

Those are listed so a later increment does not get mistaken for a missing requirement.

## Design principles

1. **Native stays native.** Adapters are the only place units, names, and nesting change. If a portal started showing `accounts[].available`, you could no longer see that Redwood stores that value as a string under `position.avail`.
2. **One write path.** The bank UI and the console both POST `/api/v1/agents/replay`. There is no second “just mutate JSON” endpoint that bypasses policy.
3. **Policy is data plus enum codes.** Dollar limits and discovery floors live in settings. Why a case opened lives on `EscalationReason`.
4. **Adapters own mutations.** Replay compiles steps and calls `adapter.apply_transfer`. It must not grow a per-bank `if institution_id == ...` posting tree.
5. **Seeds are files; working ledgers are memory.** `data/native/*.json` is git-stable. Replay copies live in process memory so demos and tests do not dirty the tree.

## System shape

```text
Operator / member
        |
        v
 TypeScript portals (Vite :5173)
   redwood | northstar | calloway | console
        |
        |  /api  (proxied)
        v
 FastAPI (:8000)
        |
        +-- registry + in-memory extract
        +-- adapter.to_canonical / to_native_transfer / apply_transfer
        |
        +-- DiscoveryAgent  --> DiscoveryReport  --> maybe hold
        +-- ReplayEngine    --> ReplayResult     --> maybe hold
        +-- EscalationAgent --> EscalationCase
```

Two processes on purpose: the UI is a stand-in for “someone else’s website”; the API is the control plane we would ship.

## Module plan

### Shared snapshot

The snapshot is the contract the three modules are allowed to think in:

- `Party` — opaque id, display name, optional contact, `native_id_field` for trace-back
- `Account` — type enum, available/current as `Money` (Decimal + currency), status
- `Transaction` — posted date, direction, amount
- `TransferIntent` — institution + two account ids + money + memo

JSON Schema in `data/schemas/canonical.schema.json` must stay aligned with `canonical.py`.

### Adapters (anti-corruption, one class each)

| Institution | Inbound oddity | Outbound transfer body |
| --- | --- | --- |
| Redwood | Household tree; `position.avail` is a **string** | `debitInstance`, `majorUnits` (string) |
| Northstar | `nmLine` is `LAST, FIRST`; cents; suffix ids | `fromSfx`, `cents` |
| Calloway | Short keys; sign on `hist[].s`; `HOLD` on LOC | `from_n`, `p` (cents) |

Each adapter implements:

- `to_canonical` — extract → snapshot
- `to_native_transfer` — intent → bank body
- `apply_transfer` — mutate that bank’s working extract and append native-shaped history

### Discovery

Discovery answers: “Can we bind this bank well enough to automate a transfer?”

It does **not** mutate ledgers. It produces a `DiscoveryReport` (field map, actions, leftover native keys, confidence). The API then asks the hold module whether that report is good enough to proceed unattended.

Because Vite’s first HTML response is an empty `#app`, published locator HTML lives in `data/contracts/`. That is a plan choice: deterministic discovery without a headless browser.

### Replay

Replay answers: “Given this snapshot-level intent, what did we actually try on that bank?”

Planned step sequence:

1. `navigate` — institution UI path
2. `fill` — bind from/to/amount (locators from latest discovery when present)
3. `assert` — hold rules (amount, status, same-account, insufficient funds)
4. `submit` — adapter-built native body
5. `post` — `apply_transfer` + persist working copy

If step 3 fails, step 5 never runs. The step list is still stored.

### Hold / review (escalation module)

This module is a gate, not a chatbot. It opens an `EscalationCase` with:

- one or more `EscalationReason` values
- a severity
- enough `context` to debug (intent, statuses, missing paths)

Default limits (overridable via env):

- amount ≥ $5,000 → `amount_threshold`
- discovery confidence < 0.72 → `low_discovery_confidence`
- account status not `open` (Calloway `HOLD` maps to `hold`) → `account_status`

## Data plan

| Store | Lifetime | Contents |
| --- | --- | --- |
| `data/native/*.json` | Git | Seed extracts |
| `_working` in `registry.py` | Process | Mutable ledgers after first load / replay |
| `Store` in `agents/base.py` | Process | Discovery reports, replay runs, hold cases |
| `data/contracts/*.html` | Git | Locator contract for discovery |
| `data/schemas/canonical.schema.json` | Git | Snapshot contract for humans and later tooling |

Reset = drop `_working` (console **Reset ledgers** or API restart). Run history dies with the process by design.

## Data sensitivity (PCI-DSS and PII)

This sandbox is **not** a card processor. Cards, ACH, and wires are non-goals. Fixtures contain no PAN, expiry, CVV, or track data, so **PCI DSS is out of scope** unless a later extract introduces cardholder data. `AccountType.CREDIT` on the schema is the quiet way that could happen — adapters must reject PAN/SAD at ingest, not encrypt them into the snapshot.

What we *do* handle is **banking PII**: name, email, phone, customer ids, balances, Calloway-style full account numbers (`acct_rel[].n`), ABA routing on Redwood (leftover, not mapped). That is a GLBA/privacy problem, not a PCI one.

**Processing vs copies.** Policy and posting need account id, type, status, available/current, and the transfer amount. Discovery needs presence and type, not live samples. Replay needs native posting keys **inside** `apply_transfer`, not a second copy on every `ReplayStep`. Email, phone, routing leftovers, and free-text memo do not belong on run/hold records.

**Encryption.** Do not encrypt `CanonicalSnapshot` wholesale — agents must read it in process. Encrypting logs that still contain email and DDA numbers does not shrink scope. Minimize and redact first. Field encryption (or a vault) is for durable full account numbers / contact fields **after** that cut, plus TLS when anything leaves localhost. Laptop disk encryption covers the demo seeds; it is not a control once `Store` is Postgres.

How we will change the snapshot, discovery samples, and run logs is a separate increment: [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md).

## Jobs: ad-hoc vs scheduled, async pull

Getting data from banks is the critical path. Transfers are occasional; **extract refresh** (balances, posted activity, discovery) will run all day. The sandbox today is synchronous: `POST /agents/replay` and `POST /agents/discover` block the HTTP worker until the adapter finishes. That is fine for three fixtures. It is not how you talk to a core.

**Two ways to start a job**

| Mode | When | Who |
| --- | --- | --- |
| **Ad-hoc** | Operator needs a snapshot or a transfer now (console, CLI, support) | Human or API client |
| **Scheduled** | Standing pull: e.g. Redwood extract every 15 minutes, discovery nightly, Calloway after core batch | Scheduler (cron expression per institution + job kind) |

Same job record either way: `kind` (`extract_refresh` \| `discover` \| `transfer_replay`), `institution_id`, payload, `idempotency_key`, `trigger` (`adhoc` \| `schedule:<id>`). Replay (money movement) stays hold-gated. Extract refresh is read-mostly and should be the default scheduled kind.

**Async so we do not choke the bank or ourselves**

```text
  ad-hoc API 202          scheduler (tick)
         \                    /
          v                  v
              job queue
          (per-FI + global caps)
                  |
                  v
         worker pool (bounded)
                  |
        +---------+---------+
        v                   v
   bank connector      our processors
   (rate limit,        (map → snapshot →
    min interval)       store → downstream)
```

- HTTP returns **202** + `job_id`; poll `GET /jobs/{id}` (or a webhook). Do not run discovery/replay on the request thread in product.
- **Per-institution concurrency** (usually 1–2) and **min interval** between calls to that core. A burst of ad-hoc must not stack on top of the scheduled pull.
- **Our side:** bounded workers and a queue with a max depth. If extracts arrive faster than we can map and persist, wait or shed — do not spawn a task per payload. Backpressure belongs in front of the snapshot/Store writers, not after they have already parsed a 50 MB dump.
- Reads (extract, discovery) and writes (transfer) use **separate queues or priorities** so a reporting backfill cannot delay a member-initiated transfer, and a transfer storm cannot starve the nightly pull.
- Scheduled extract jobs reuse the same **idempotency** story: tick `2026-08-28T16:00Z` + institution → one key; a late retry of that tick is a no-op if the pull already succeeded.

Not built in the sandbox. See the Later table for the approach.

## UI plan

Four TypeScript routes, no React, so the dependency surface stays small:

- `/` hub — explains the mismatch
- `/redwood`, `/northstar`, `/calloway` — bank-specific layout and native labels
- `/console` — discovery, replay form, snapshot preview, hold table

Bank pages must keep looking different. Sameness would hide the schema mismatch this sandbox is meant to show.

## Test plan (what “done” means)

| Claim | Test |
| --- | --- |
| Three extracts describe the same person after mapping | `test_schema.py` — name, email, checking $2190.40 |
| Calloway HOLD survives mapping | status `hold`, type loan |
| A posting replay changes the working extract | Redwood string balances drop by $40 |
| Policy blocks before write | Calloway → LOC; Northstar $9000 |
| Amount and status are separate reason codes | `test_escalation.py` |
| Empty SPA HTML still yields locators | published contract fallback |
| API lists the three ids | `test_api.py` |

No network and no model keys required.

## Phased delivery (what is in vs later)

**Built now**

- Three extracts + three portals + console
- Snapshot + adapters + registry
- Discovery, replay, hold
- FastAPI + CLI + in-memory working copies
- Docs and pytest

**Later, if this became a product** (not required in this sandbox)

Idempotency, durable ledgers, real DOM, **ad-hoc vs scheduled jobs**, **async backpressure**, and **snapshot/log minimization** are called out under [Risks and choices](#risks-and-choices). This table is the **how** if we left the laptop sandbox. `Store` (run history / holds) and working ledgers (balances) are two stores; the job queue is a third concern in front of both. PII redaction must land **before** Store is durable, or every hold case becomes a long-lived copy of the extract.

| Increment | Why | In risks? | Approach |
| --- | --- | --- | --- |
| Versioned mapping files instead of Python classes only | FI onboarding without shipping adapter code for every field rename | Mapping triples drift; replay `if` pile | One YAML/JSON map per FI (`native_path`, `canonical_path`, `unit`, transfer body template), versioned. Adapter becomes an interpreter. Discovery hints generated from the file. Golden tests: extract → snapshot snapshot file. |
| Durable **working ledgers** | Restart must not rewind balances; two API workers must see the same money | Demos rewrite git JSON | Seed vs working tables (or blob-per-institution). `load_native` reads working; `apply_transfer` commits in a transaction. Reset = `INSERT … SELECT` from seed → working. SQLite for `make dev`; Postgres when there is more than one Uvicorn worker. |
| Durable **`Store`** (discoveries, replays, hold queue) | Operators must still see yesterday’s holds after a deploy | Run history vanishes on restart *(added below)* | Separate tables: `discovery_report`, `replay_run` (steps as JSONB), `escalation_case`. Persist **redacted** copies only ([PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md) Phase 1). Do not store these on the ledger row. Query the hold queue with `status = open`. Same SQLite/Postgres as ledgers, different schema. |
| Real DOM for discovery | Published `data/contracts/` is a fixture we wrote, then parsed | Discovery finds locators the live SPA never sent | Replace HTML GET with a browser worker (Playwright): open `ui_path`, wait for `[data-iai-page]`, scrape `data-iai-*`. Keep contract files as CI **oracle**: fail if live locators ≠ contract. Tests keep `html_loader` injection so pytest stays headless. Production worker holds FI session cookies. |
| Idempotency keys on replay | Double-click / retry must not post twice | Double-submit / retry posts twice | Client sends `idempotency_key` (UUID from console and bank form). Unique `(institution_id, idempotency_key)`. Same key + same intent → return original `ReplayResult` (no second `apply_transfer`). Same key + different body → `409`. Persist the key on the run row, not only in memory. |
| Optional model assist on unknown markup | Cores change class names; a map file will lag | Holds un-reviewable *(gate stays)* | Model proposes locators or a mapping patch. Output is a *draft* `DiscoveryReport`. Hold module still blocks if coverage is incomplete. Human accepts the patch into the versioned map. No model call on the money-movement path. |
| AuthN to the mock banks | Real connectors are sessionful | Bank portal is not someone else’s site | Banks expose native transfer + login. Replay is an HTTP (or browser) client with a stored session. Policy still runs *before* the outbound call. Console remains our API. |
| Ad-hoc **and scheduled** jobs | Operators need a pull now; standing extracts must run without someone clicking Console | Sync HTTP chokes the bank and our processors *(added below)* | One `job` row: `kind`, institution, payload, `trigger` (`adhoc` \| schedule id). Scheduler emits ticks into the **same queue** as `POST /jobs`. Console “Run now” is ad-hoc. Do not fork a second code path. |
| Async workers + backpressure | Cores rate-limit; a 15-minute pull of 100 FIs must not melt our mapper/Store | Sync HTTP chokes the bank and our processors | FastAPI **202** + `job_id`. Bounded worker pool. **Per-FI semaphore** + min interval. Separate queues (or priorities) for `extract_refresh` / `discover` vs `transfer_replay`. If the ingest queue hits max depth, reject or delay new scheduled ticks; never unbounded `asyncio.create_task` per extract. Downstream processors consume from a buffer with a high-water mark. |
| Snapshot and run-log minimization (PII; PCI guard) | Discovery samples, replay steps, and holds copy live customer and ledger values; email/phone sit on `Party` unused by agents | Logs and snapshot copies expand privacy scope *(added below)* | Redact samples; mask/hash ids on stored runs; drop contact PII from agent-facing views; reject PAN at ingest. Do **not** encrypt the working snapshot. See [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). |

The module boundaries above are meant to survive those increments. Persistence splits **ledger** (how much money) from **Store** (what we attempted and why we held). Idempotency sits on replay **and** on scheduled extract ticks. Real DOM sits on discovery, not on posting. The **job queue** sits in front of discovery and replay so neither the bank nor our processors see a synchronous burst.

## Risks and choices

These are the **right choices for this sandbox** (clone, `make dev`, no keys, no browser farm). They are not the production end-state. Each row is a deliberate stopgap: keep the module boundary, replace the mechanism later.

How to read the table: **Choice now** is what the repo does. **Verdict** is whether we would keep that *idea* in a real platform. **Ideal** is what that row should become if this were onboarding real FIs — not work that has to land in this repo today.

| Risk | Choice now | Verdict | Ideal solution |
| --- | --- | --- | --- |
| Snapshot becomes a dumping ground (“just add a field”) | Small `CANONICAL_REQUIRED` list; leftover native keys listed, not copied into the snapshot | **Keep the idea, tighten the mechanism.** Leftovers are a hardcoded extras dict (`routing`, `header`, `sys`), so they do not actually detect dump-growth. | Versioned canonical schema (JSON Schema is source of truth → generated models). Institution-namespaced `extensions` for FI-only fields. CI fails if a required path is added without every adapter and a golden-file test. |
| Replay becomes a pile of bank `if`s | `apply_transfer` lives on each adapter; ReplayEngine only compiles steps | **Keep.** This is the correct boundary. Residual drift: `NATIVE_HINTS` in discovery is a *second* map of the same extract and can disagree with the adapter. | One mapping artifact per FI (versioned YAML/JSON: native path ↔ snapshot path, units, transfer body). Adapter is a thin interpreter. Replay, discovery, and posting all read that file. Contract tests per FI, plus idempotency keys on submit. |
| Discovery “finds” locators that the live SPA never sent | Published HTML under `data/contracts/` plus a test for empty `#app` | **Keep for local/dev; do not call it discovery in production.** We wrote the contract we then parse — tests catch empty DOM, not *drift* between page TS and the HTML file. | Page publishes a machine-readable contract the UI itself loads (single source). CI: Playwright against the running portals, fail if live `data-iai-*` ≠ contract. Production: authenticated browser worker; confidence from live locators + extract coverage, not a fixture. |
| Holds become un-reviewable (“the model said no”) | `EscalationReason` enum; dollar/confidence floors in settings | **Keep enums and settings.** Too coarse today: `policy` covers both same-account and insufficient funds; account status is a free string; limits are global, not per FI. | One reason code per condition. `AccountStatus` enum. Per-institution policy table (amount cap, product types allowed) with version + who changed it. Case lifecycle (open → assigned → resolved) and an append-only audit log. LLM may *propose*; this module still gates. |
| Demos rewrite git JSON (working **ledgers**) | `_working` dict in `registry.py`; seeds stay in git | **Keep seeds-vs-working.** Memory-only breaks as soon as two workers or a restart matter. This is *balances*, not the hold queue. | Seed vs working in SQLite (local) / Postgres (prod). Reset = copy seed → working inside a transaction. Posts append a ledger row; current balances are a projection (or an updated working blob in the same transaction as the replay row). |
| Run history and hold queue vanish (`Store`) | In-process lists on `agents/base.py` `Store` | **Gap if this is an operator tool.** Distinct from ledgers: you can reset money and still need last week’s cases. | Persist `discovery_report`, `replay_run`, `escalation_case`. Hold inbox = `WHERE status = 'open'`. Survives deploy; reset-ledgers does **not** wipe cases unless an operator says so. |
| Mapping triples drift (adapter vs hints vs contract) | Three places to update when a field changes (not called out in the original table) | **Improve now if we extend the sandbox; must fix in product.** | Single mapping file (see replay row). Discovery hints generated from it. Locator names in the contract must appear in that file or CI fails. |
| Bank portal is not really “someone else’s site” | Portal transfer forms POST our `/agents/replay` | **Acceptable for the demo** (one write path, policy always runs). Misleading if read as a connector to a third-party bank. | Mock banks expose *their* native transfer URL. Replay is an HTTP client against that URL (still using adapter-built bodies). Policy runs *before* the client call. Console stays on our API. |
| Discovery confidence is a made-up 0–1 | Weighted coverage + locator/action bonuses | **Fine as a demo signal.** Not a calibrated probability; do not use it as a credit/compliance control. | Separate *coverage* (deterministic % of required paths) from *locator health* (live DOM check). Hold on coverage gaps; treat “confidence” as ops telemetry, or replace with evals on labeled pages. |
| Double-submit / retry posts twice | No idempotency key on replay | **Gap.** Easy to hit from the UI. | Client-supplied `idempotency_key`; working ledger unique on `(institution, key)`. Replay of the same key returns the original receipt. |
| Sync HTTP pull chokes the core **or** our mapper | `POST /agents/*` runs discovery/replay on the request thread | **Fine for three fixtures. Wrong once extracts are on a timer.** Ad-hoc and scheduled must share one queue or the console will stampede the 15-minute job. | Job queue; **202** + poll. Per-FI concurrency and min interval. Bounded workers. Backpressure when ingest depth is high. Reads and writes isolated by priority. See [Jobs](#jobs-ad-hoc-vs-scheduled-async-pull). |
| Snapshot and logs copy more PII than agents need | Full `Party` (email/phone) on `/canonical`; live `DiscoveryField.sample`; native transfer body + memo on FILL/SUBMIT/receipt/hold context; Calloway DDA used as `Account.id` | **Gap if Store is ever durable or shared.** Fine as fictional laptop data; wrong as an operator audit trail. PCI is out of scope until PAN appears. | Working snapshot stays plaintext for policy. Logs get redaction + hashed ids, not encrypt-in-place. Contact fields display-only or omitted. PAN/SAD rejected at adapter. Field encryption only for residual durable DDA/contact. [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). |

What we would **not** change even in the ideal column: native portals (do not render the snapshot), one policy gate in front of money movement, adapters (or their mapping files) as the only place units change, and enum hold reasons instead of prompt text.

## Success for this sandbox

Someone can clone, `make setup && make dev`, open three banks that *disagree* on JSON, run discovery, post a small Redwood transfer, and see Calloway HOLD and a large Northstar amount land on the hold queue — without reading the adapter source first. The source then explains *why* those three outcomes differ.
