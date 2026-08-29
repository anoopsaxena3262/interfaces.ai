# Design plan

This is the overall plan for the sandbox: what problem it is solving, what we chose to build, and what we deliberately left out.

If you are new to the repo, read [GUIDE.md](GUIDE.md) first. This document is the “why,” not the file-by-file map. Runtime: [ARCHITECTURE.md](ARCHITECTURE.md). File inventory: [CATALOG.md](CATALOG.md). PII/PCI copies: [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). Discovery evals (explore only): [PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md). **What is in the repo vs sandbox-next vs product:** [Now vs later](#now-vs-later-sandbox-vs-product). Index of all docs: [README.md](../README.md).

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

JSON Schema in `data/schemas/canonical.schema.json` must stay aligned with `canonical.py`. There is no `schema_version` field yet; the mechanism is in [Canonical schema versioning](#canonical-schema-versioning).

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

## Concurrency

The sandbox is **one Uvicorn process**, `--reload`, sync route handlers. That is a valid laptop demo. It is not a concurrency story.

### What actually races today

`load_native` deep-copies `_working[id]`, `apply_transfer` mutates the copy, `save_native` replaces the dict entry. Two overlapping Redwood posts:

```text
  request A                    request B
  load  avail=2190.40          load  avail=2190.40
  debit 40 → 2150.40
  save  2150.40
                               debit 40 → 2150.40   # lost update; should be 2110.40
                               save  2150.40
```

Handlers are `def`, so FastAPI runs them in a thread pool. CPython’s GIL does **not** serialize this: the window is between deepcopy and `save_native`, and it includes Decimal math and list prepends. `reset_native` vs an in-flight save is the same class of bug. `Store` lists (`insert(0, …)`) are a second in-process race (run history / holds), independent of money.

**Two Uvicorn workers** (`--workers 2`) is worse than a race: `_working` and `Store` are process-local. Worker 1 posts; worker 2 still serves the seed. There is no lock that can fix that.

`--reload` plus a single worker hides all of this. Pytest is serial plus `reset_native` around each test, so CI will not catch it.

### Mechanism when we leave one process

Do not add a process-wide `threading.Lock` on `_working` as the product design. A lock only helps threads in one process; the moment there are two workers or two machines, you need a single writer for that institution’s ledger.

| Layer | Mechanism | What it serializes |
| --- | --- | --- |
| Sandbox (optional hardening) | `asyncio.Lock` / `threading.Lock` **per `institution_id`** around load → `apply_transfer` → save | Same-process overlapping replays only. Document “run one worker.” |
| Product writes | One **DB row per institution working ledger** (or append-only ledger + projection). `BEGIN; SELECT … FOR UPDATE; apply; UPDATE; COMMIT` | Two API workers, two replicas. Lost update becomes a wait, not a silent clobber. |
| Product retries | Idempotency unique on `(institution_id, idempotency_key)` in the **same** transaction as the ledger write | Double-click and worker retry. See Later table. |
| Job queue | **Per-FI concurrency = 1** for `transfer_replay` (and usually for `extract_refresh`) | Ad-hoc + scheduled cannot interleave two mutators for Redwood. Queue is in front of the DB lock, not a substitute for it. |
| `Store` | Same database, not a second in-memory list. Insert run/hold rows in the ledger transaction or immediately after with the `run_id` | Holds survive the worker that opened them. |

Reads (`GET /native`, discovery) can proceed without the write lock if they take a snapshot isolation read (or a deepcopy under the lock in the sandbox). Discovery must not call `save_native`.

Extract refresh vs transfer: an extract job that **replaces** `_working` from a core dump can wipe a post that committed in between. Product rule: refresh merges on native ids or versions the blob (`working.version` / `updated_at`) and rejects a stale refresh (`WHERE version = $expected`). Transfers bump the version.

Not built. The Later rows for durable ledgers and async workers assume this locking story; they are incomplete without it.

## Canonical schema versioning

JSON Schema and `canonical.py` are **hand-aligned** today. There is no `schema_version` on `CanonicalSnapshot`. Adding a required path means touching Pydantic, the JSON file, every adapter, `CANONICAL_REQUIRED`, and tests — by convention, not by mechanism. The risks table already flags “dumping ground”; this is the mechanism that row should become.

### Source of truth

1. **JSON Schema is canonical.** Files: `data/schemas/canonical.v{MAJOR}.json` (or `$id` `…/canonical-snapshot/v1`). Pydantic models are **generated** (or checked) from that file in CI. Drift = fail, not a wiki reminder.
2. Every snapshot, discovery report, and replay result carries `schema_version` (semver string, e.g. `1.2.0`). Stored holds keep the version they were opened with so last week’s case is still readable after a deploy.
3. Per-FI mapping files (Later) pin `canonical_version`. An adapter/interpreter refuses to run if the map’s pin is a major behind the process (or transcodes; see below).

### Compatibility rules

| Bump | Allowed change | Producers (adapters) | Consumers (discovery, replay, policy, console) |
| --- | --- | --- | --- |
| **Patch** `1.2.3` | Descriptions, examples | No code | No code |
| **Minor** `1.3.0` | Additive **optional** field or enum member | May omit; goldens still validate | Must ignore unknown properties (`additionalProperties` false only under `extensions`, not the root if we want minor adds — or use `unevaluatedProperties` carefully). Policy must not require a field that is optional. |
| **Major** `2.0.0` | Rename, type change, new **required** path, remove field | New map + adapter path; dual-write or migrate | Explicit down-mapper `v2 → v1` or “upgrade the client.” No silent drop of a required automation field. |

`CANONICAL_REQUIRED` (discovery coverage) is **not** a second schema. It is a vendor annotation on the JSON Schema, e.g. `x-iai-required-for-transfer: true` on `accounts[].available`. Discovery and CI read that list from the schema file so a new required path without an adapter golden fails the build.

FI-only junk does not get a minor bump: `extensions.<institution_id>` (additionalProperties allowed there only). Leftover native keys stay names in discovery, not new snapshot fields.

### Runtime

- Process serves **one current major**. `GET /canonical` returns `schema_version` of the running major.
- Optional `?schema_version=1.2.0`: if the request is the same major and a **minor or equal**, respond by omitting newer optional fields. If the request is a different **major**, `409` or a dedicated transcode module — do not guess renames.
- TypeScript console types are generated from the same schema (or stay loosely typed and display JSON). They must not invent snapshot fields the Python models do not have.

### Change procedure (major or new required path)

1. Edit JSON Schema; bump semver.
2. Generate models; add adapter mappings (or mapping-file entries) for all three FIs.
3. Add/adjust golden extract → snapshot files; pytest validates goldens against the new schema.
4. Discovery annotations updated only via the schema file.
5. If major: ship down-mapper tests (`v2` fixture → `v1` shape) and keep `v1` schema file in-repo until stored holds and mapping pins have moved.

Until this exists, treat `canonical.py` + `canonical.schema.json` as version `1.0.0` implied, single-writer, laptop-only.

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
| API lists the three ids | `test_api.py` — health + institution list |
| Unknown institution and invalid amount fail at HTTP | `test_api.py` — 404 `not-a-bank`; 422 negative/zero amount |
| Run/hold copies are redacted (compliance Phase 1) | `test_api.py` `/runs` after discover + Calloway HOLD; also `test_discovery.py` / `test_replay.py` / `test_escalation.py` |

No network and no model keys required.

## Phased delivery (what is in vs later)

**In the repo today** (clone, `make dev`, no keys)

- Three extracts + three portals + console
- Snapshot + adapters + registry
- Discovery, replay, hold
- FastAPI + CLI + in-memory working copies
- Docs and pytest (including API 404/422)
- Compliance **Phase 1** copies: discovery kinds, empty SUBMIT, redacted hold context, `redact_operator_screen` / `GET /runs`

**“Now” does not mean shipped.** Rows tagged sandbox-now in [Now vs later](#now-vs-later-sandbox-vs-product) are *appropriate to build in this repo* (still one process, no Postgres, no Playwright, no LLM). Most of them are **not implemented**. Only Phase 1 redaction and the demo stack above are in code.

**Later, if this became a product** (not required in this sandbox)

Durable ledgers, two workers, full schema versioning, real DOM, jobs/async, mapping-file interpreters, and encryption after durable Store are still product. This table is the **how**. `Store` and working ledgers are two stores; the job queue is a third. Phase 1 redaction must stay in front of durable Store. Ledger writes need a **per-institution lock in the database** — see [Concurrency](#concurrency).

| Increment | Why | In risks? | Approach |
| --- | --- | --- | --- |
| Versioned mapping files instead of Python classes only | FI onboarding without shipping adapter code for every field rename | Mapping triples drift; replay `if` pile | One YAML/JSON map per FI (`native_path`, `canonical_path`, `unit`, transfer body template), versioned. Adapter becomes an interpreter. Discovery hints generated from the file. Golden tests: extract → snapshot snapshot file. |
| Durable **working ledgers** | Restart must not rewind balances; two API workers must see the same money | Demos rewrite git JSON; `_working` races *(below)* | Seed vs working tables (or blob-per-institution). `load_native` reads working; `apply_transfer` commits in a **transaction** with `SELECT … FOR UPDATE` (or equivalent) on that institution’s row. Reset = `INSERT … SELECT` from seed → working. SQLite for `make dev`; Postgres when there is more than one Uvicorn worker. Per-FI job concurrency 1 for transfers. Version the blob so extract refresh cannot clobber a newer post. See [Concurrency](#concurrency). |
| Canonical **schema versioning** | Snapshot is a contract; additive fields and breaking changes will happen | Snapshot dumping ground *(below)* | JSON Schema is source of truth; `schema_version` on every snapshot/report/run; semver compatibility table; generate Pydantic from schema in CI; `x-iai-required-for-transfer` drives discovery; `extensions.<fi>` for leftovers. Minor = optional add; major = transcode or 409. See [Canonical schema versioning](#canonical-schema-versioning). |
| Durable **`Store`** (discoveries, replays, hold queue) | Operators must still see yesterday’s holds after a deploy | Run history vanishes on restart *(added below)* | Separate tables: `discovery_report`, `replay_run` (steps as JSONB), `escalation_case`. Persist **redacted** copies only ([PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md) Phase 1). Do not store these on the ledger row. Query the hold queue with `status = open`. Same SQLite/Postgres as ledgers, different schema. |
| Real DOM for discovery | Published `data/contracts/` is a fixture we wrote, then parsed | Discovery finds locators the live SPA never sent | Replace HTML GET with a browser worker (Playwright): open `ui_path`, wait for `[data-iai-page]`, scrape `data-iai-*`. Keep contract files as CI **oracle**: fail if live locators ≠ contract. Tests keep `html_loader` injection so pytest stays headless. Production worker holds FI session cookies. |
| Idempotency keys on replay | Double-click / retry must not post twice | Double-submit / retry posts twice | Client sends `idempotency_key` (UUID from console and bank form). Unique `(institution_id, idempotency_key)`. Same key + same intent → return original `ReplayResult` (no second `apply_transfer`). Same key + different body → `409`. Persist the key on the run row, not only in memory. |
| Optional model assist on unknown markup | Cores change class names; a map file will lag | Holds un-reviewable *(gate stays)* | Model proposes locators or a mapping patch. Output is a *draft* `DiscoveryReport`. Hold module still blocks if coverage is incomplete. Human accepts the patch into the versioned map. No model call on the money-movement path. |
| AuthN to the mock banks | Real connectors are sessionful | Bank portal is not someone else’s site | Banks expose native transfer + login. Replay is an HTTP (or browser) client with a stored session. Policy still runs *before* the outbound call. Console remains our API. |
| Ad-hoc **and scheduled** jobs | Operators need a pull now; standing extracts must run without someone clicking Console | Sync HTTP chokes the bank and our processors *(added below)* | One `job` row: `kind`, institution, payload, `trigger` (`adhoc` \| schedule id). Scheduler emits ticks into the **same queue** as `POST /jobs`. Console “Run now” is ad-hoc. Do not fork a second code path. |
| Async workers + backpressure | Cores rate-limit; a 15-minute pull of 100 FIs must not melt our mapper/Store | Sync HTTP chokes the bank and our processors | FastAPI **202** + `job_id`. Bounded worker pool. **Per-FI semaphore** + min interval. Separate queues (or priorities) for `extract_refresh` / `discover` vs `transfer_replay`. If the ingest queue hits max depth, reject or delay new scheduled ticks; never unbounded `asyncio.create_task` per extract. Downstream processors consume from a buffer with a high-water mark. |
| Snapshot and run-log minimization (PII; PCI guard) | Discovery samples, replay steps, and holds copy live customer and ledger values; email/phone sit on `Party` unused by agents | Logs and snapshot copies expand privacy scope *(added below)* | **Phase 1 is in the repo.** Phase 2 (`/canonical?view=agent`), Phase 3 (PAN ingest), Phase 4 (HMAC/TLS/encrypt after durable Store) are not. See [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). |
| Discovery evals and judges | Unit tests only cover three happy banks; `confidence` is a formula, not a labeled score | Discovery confidence is a made-up 0–1 *(below)* | **Not built.** Exploration only: [PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md). Programmatic corpus is sandbox-now; LLM judges are product (and only with a proposer). |

The module boundaries above are meant to survive those increments. Persistence splits **ledger** (how much money) from **Store** (what we attempted and why we held). Idempotency sits on replay **and** on scheduled extract ticks. Real DOM sits on discovery, not on posting. The **job queue** sits in front of discovery and replay so neither the bank nor our processors see a synchronous burst. **Schema version** sits on the snapshot, not in adapter `if` trees. **Write serialization** sits in the ledger transaction (and per-FI queue depth 1), not in `_working`.

## Now vs later (sandbox vs product)

This section is the evaluation overlay on the Later table and [Risks](#risks-and-choices). It answers: *should this land in the laptop sandbox, or only if we onboard real FIs?*

**Do not read “now” as “already implemented.”** Status is a separate column. “Now” means: still one Uvicorn worker, no new services, no API keys, no browser farm — and it makes the demo honest (two clicks, reviewable holds, copies that are not a second extract).

### How to decide

| Tag | Meaning | Rationale |
| --- | --- | --- |
| **In repo** | Code and tests exist | Demo stack + compliance Phase 1. |
| **Sandbox now** | Fit this repo; **not built** unless Status says so | Fixes a gap you can hit on `make dev` without pretending we have Postgres or Playwright. |
| **Product later** | Needs a single writer, a queue, a connector, or a real operator tool | Doing it in a dict in RAM is busywork or a lie (two workers, yesterday’s holds, live DOM). |

Keep even in the ideal column: native portals, one write path through policy, adapters (or mapping files) as the only place units change, enum holds, plaintext working snapshot, `confidence` not a credit/compliance control.

### Closed (in the repo)

| Item | Rationale it is done here |
| --- | --- |
| Three banks, adapters, discovery, replay, holds, API, CLI, in-memory ledgers/`Store` | This *is* the sandbox. |
| Compliance Phase 1 (kinds, empty SUBMIT, last-4 hold context, operator copies, `/runs` tests) | Copies outlive a request; they had to be minimized **before** anyone treats `/runs` as an audit trail. Native `/native` and full in-process snapshot stay full on purpose. |
| API 404 / 422 on unknown institution and bad amount | HTTP contract for the console and OpenAPI, not a product auth story. |

### Sandbox now — appropriate here, **not implemented**

Suggested order if we extend the sandbox: (1) split hold reasons + status enum, (2) hold on missing paths, (3) hint/contract drift tests, (4) compliance Phase 2 + 3, (5) per-FI lock + in-memory idempotency, (6) eval corpus, (7) `schema_version: "1.0.0"` stub.

| Gap | Status | Why now (not later) | Why not “shipped” | Rationale / stop line |
| --- | --- | --- | --- | --- |
| `POLICY` is same-account **and** NSF | Not built | Reviewers filter by enum; tests already separate the paths | Still one `EscalationReason.POLICY` | Split two reasons. **Stop:** do not add case lifecycle or per-FI policy tables (product). |
| Account status is a free string | Not built | Calloway `HOLD` works by convention; a typo would not hold | `Account.status` is `str` | `AccountStatus` enum + adapter map. **Stop:** global limits stay in `IAI_*` until a policy table exists. |
| Discovery hold keyed on a made-up 0–1 | Not built | Bonuses can pass 0.72 with a hole in coverage | Gate is still `confidence` + missing paths together | Hold on **missing required paths**; keep `confidence` as telemetry. **Stop:** do not calibrate the 0–1 or use it as a control. |
| `NATIVE_HINTS` vs adapters | Not built | Second map of the same extract; silent drift | Comment-only alignment | Pytest: hints (or hand-edited goldens) vs adapter output for three seeds. **Stop:** do not rewrite adapters as a YAML interpreter (Later mapping files). |
| Contract HTML vs page `data-iai-*` | Not built | Empty `#app` is tested; TS vs `data/contracts/` is not | Only fallback HTML test | Static grep/diff in CI. **Stop:** Playwright / live DOM is product. |
| Discovery eval corpus | Not built | Three happy banks are regression, not eval | No `data/evals/` | Mutants + programmatic judges ([PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md)). **Stop:** no LLM judge until discovery *proposes* maps. |
| `/canonical?view=agent` (compliance Phase 2) | Not built | Console preview hides contact; the API still dumps email/phone | No `view` query | Filter on GET used by console. Schema tests stay on in-process snapshot. |
| PAN/SAD ingest guard (Phase 3) | Not built | `AccountType.CREDIT` is how PCI could arrive by accident | No Luhn/key reject | Shared detector; fake PAN only in a throwaway test dict. **Stop:** no ROC, no encrypt-PAN. |
| Same-process lost update on `_working` | Not built | Thread-pool overlapping Redwood posts can clobber | No per-FI lock | `threading.Lock` per `institution_id` around load → apply → save. **Stop:** still one Uvicorn worker. A lock is not two-worker safety ([Concurrency](#concurrency)). |
| Double-click posts twice | Not built | Easy from the console | No `idempotency_key` | In-memory key → return first `ReplayResult`. Dies on restart. **Stop:** durable unique constraint is product (same increment as durable ledgers). |
| Implied schema 1.0.0 | Not built | Hand-synced Pydantic + JSON Schema | No `schema_version` field | Add `"1.0.0"` on snapshot/report/run. **Stop:** do not generate models from schema or ship transcode/`409` until [Canonical schema versioning](#canonical-schema-versioning). |

### Product later — do not fake in RAM

| Gap | Why later | Rationale |
| --- | --- | --- |
| Durable working ledgers + `SELECT FOR UPDATE` / blob version | Restart and **two workers** must see the same money | Memory `_working` is the demo. SQLite only pays off when a second process exists. |
| Durable `Store` | Yesterday’s holds after deploy | Distinct from ledgers. Keep Phase 1 redaction; then compliance Phase 4 (HMAC, TLS, field encrypt). |
| `--workers 2` | Process-local dicts = split brain | Thread lock cannot fix this. |
| Job queue, HTTP 202, scheduler, backpressure | Extracts on a timer, 100 FIs | Three fixtures are sync on purpose. |
| Full schema versioning | Additive vs breaking contract | Stub string is sandbox-now; codegen, `x-iai-required-for-transfer`, majors are product. |
| One mapping file per FI (adapter as interpreter) | Fourth core without a Python class | Drift **tests** are sandbox-now; the interpreter is a rewrite. |
| Playwright / authenticated browser worker | Live SPA locators | Against current non-goals. Contracts become the CI oracle when this lands. |
| Banks’ own transfer URL + sessions | Real connector | Demo correctly POSTs *our* API so policy always runs. |
| Per-FI policy tables, case assigned/resolved, audit log | Operator product | Enums stay; tables wait. |
| LLM map proposer + LLM judge | Unknown cores | Useless while reports copy `NATIVE_HINTS`. Programmatic judges first. |
| AuthN to mocks, TLS, KMS | Off localhost | Laptop HTTP is a non-goal to keep. |

### If you only care about one outcome

| Outcome | Enough today? | Next |
| --- | --- | --- |
| Clone and demo three disagreeing banks | **Yes** (in repo) | — |
| Honest holds + no PII in `/runs` | **Partial** (Phase 1 yes; coarse `POLICY`, full `/canonical`) | Sandbox-now: reason split, Phase 2 |
| “Discovery is real” | **No** (we parse a contract we wrote) | Static TS vs HTML now; Playwright later |
| Operator queue after restart | **No** | Durable Store later |
| Two API workers | **No** | Durable ledgers later |
| Fourth core without adapter code | **No** | Mapping files later |

## Risks and choices

These are the **right choices for this sandbox** (clone, `make dev`, no keys, no browser farm). They are not the production end-state. Each row is a deliberate stopgap: keep the module boundary, replace the mechanism later.

How to read the table: **Choice now** is what the repo **does today** (implemented). **Verdict** is whether we would keep that *idea* in a real platform. **Ideal** is product. For *should we build this in the sandbox next*, use [Now vs later](#now-vs-later-sandbox-vs-product) — several Ideal cells have a smaller sandbox-now slice that is **not** in code yet.

| Risk | Choice now | Verdict | Ideal solution |
| --- | --- | --- | --- |
| Snapshot becomes a dumping ground (“just add a field”) | Small `CANONICAL_REQUIRED` list; leftover native keys listed, not copied into the snapshot | **Keep the idea, tighten the mechanism.** Leftovers are a hardcoded extras dict (`routing`, `header`, `sys`), so they do not actually detect dump-growth. JSON Schema and `canonical.py` are hand-synced; no `schema_version`. | Versioned canonical schema (JSON Schema is source of truth → generated models). Semver on the snapshot; minor vs major rules; institution-namespaced `extensions`. CI fails if a required path is added without every adapter and a golden-file test. [Canonical schema versioning](#canonical-schema-versioning). |
| Replay becomes a pile of bank `if`s | `apply_transfer` lives on each adapter; ReplayEngine only compiles steps | **Keep.** This is the correct boundary. Residual drift: `NATIVE_HINTS` in discovery is a *second* map of the same extract and can disagree with the adapter. | One mapping artifact per FI (versioned YAML/JSON: native path ↔ snapshot path, units, transfer body). Adapter is a thin interpreter. Replay, discovery, and posting all read that file. Contract tests per FI, plus idempotency keys on submit. |
| Discovery “finds” locators that the live SPA never sent | Published HTML under `data/contracts/` plus a test for empty `#app` | **Keep for local/dev; do not call it discovery in production.** We wrote the contract we then parse — tests catch empty DOM, not *drift* between page TS and the HTML file. | Page publishes a machine-readable contract the UI itself loads (single source). CI: Playwright against the running portals, fail if live `data-iai-*` ≠ contract. Production: authenticated browser worker; confidence from live locators + extract coverage, not a fixture. |
| Holds become un-reviewable (“the model said no”) | `EscalationReason` enum; dollar/confidence floors in settings | **Keep enums and settings.** Too coarse today: `policy` covers both same-account and insufficient funds; account status is a free string; limits are global, not per FI. | One reason code per condition. `AccountStatus` enum. Per-institution policy table (amount cap, product types allowed) with version + who changed it. Case lifecycle (open → assigned → resolved) and an append-only audit log. LLM may *propose*; this module still gates. |
| Demos rewrite git JSON (working **ledgers**) | `_working` dict in `registry.py`; seeds stay in git | **Keep seeds-vs-working.** Memory-only breaks as soon as two workers or a restart matter. Same-process overlapping `load`/`save` loses updates; two workers split-brain. This is *balances*, not the hold queue. | Seed vs working in SQLite (local) / Postgres (prod). Per-institution row lock in the write transaction. Reset = copy seed → working inside a transaction. Posts append a ledger row; current balances are a projection (or an updated working blob in the same transaction as the replay row). One Uvicorn worker until then. [Concurrency](#concurrency). |
| Run history and hold queue vanish (`Store`) | In-process lists on `agents/base.py` `Store` | **Gap if this is an operator tool.** Distinct from ledgers: you can reset money and still need last week’s cases. Same-process `insert(0)` is also racy; two workers do not share the list. | Persist `discovery_report`, `replay_run`, `escalation_case`. Hold inbox = `WHERE status = 'open'`. Survives deploy; reset-ledgers does **not** wipe cases unless an operator says so. Stamp `schema_version` on stored rows. |
| Mapping triples drift (adapter vs hints vs contract) | Three places to update when a field changes (not called out in the original table) | **Improve now if we extend the sandbox; must fix in product.** | Single mapping file (see replay row). Discovery hints generated from it. Locator names in the contract must appear in that file or CI fails. |
| Bank portal is not really “someone else’s site” | Portal transfer forms POST our `/agents/replay` | **Acceptable for the demo** (one write path, policy always runs). Misleading if read as a connector to a third-party bank. | Mock banks expose *their* native transfer URL. Replay is an HTTP client against that URL (still using adapter-built bodies). Policy runs *before* the client call. Console stays on our API. |
| Discovery confidence is a made-up 0–1 | Weighted coverage + locator/action bonuses | **Fine as a demo signal.** Not a calibrated probability; do not use it as a credit/compliance control. | Separate *coverage* (deterministic % of required paths) from *locator health* (live DOM check). Hold on coverage gaps; treat “confidence” as ops telemetry, or replace with evals on labeled pages. [PLAN-DISCOVERY-EVAL.md](PLAN-DISCOVERY-EVAL.md): programmatic judges yes; LLM-as-judge not until a proposer exists. |
| Double-submit / retry posts twice | No idempotency key on replay | **Gap.** Easy to hit from the UI. | Client-supplied `idempotency_key`; working ledger unique on `(institution, key)`. Replay of the same key returns the original receipt. |
| Sync HTTP pull chokes the core **or** our mapper | `POST /agents/*` runs discovery/replay on the request thread | **Fine for three fixtures. Wrong once extracts are on a timer.** Ad-hoc and scheduled must share one queue or the console will stampede the 15-minute job. | Job queue; **202** + poll. Per-FI concurrency and min interval. Bounded workers. Backpressure when ingest depth is high. Reads and writes isolated by priority. See [Jobs](#jobs-ad-hoc-vs-scheduled-async-pull). |
| Snapshot and logs copy more PII than agents need | Phase 1: stored discovery/replay/hold and `/runs` are redacted. **Still:** full `Party` on `GET /canonical`; Calloway DDA as `Account.id` in working snapshot; no PAN ingest guard | **Phase 1 in repo.** Residual gap on agent-facing canonical and ingest. PCI out of scope until PAN appears. | Phase 2–3 sandbox-now; Phase 4 after durable Store. [PLAN-COMPLIANCE.md](PLAN-COMPLIANCE.md). |

What we would **not** change even in the ideal column: native portals (do not render the snapshot), one policy gate in front of money movement, adapters (or their mapping files) as the only place units change, and enum hold reasons instead of prompt text.

## Success for this sandbox

Someone can clone, `make setup && make dev`, open three banks that *disagree* on JSON, run discovery, post a small Redwood transfer, and see Calloway HOLD and a large Northstar amount land on the hold queue — without reading the adapter source first. The source then explains *why* those three outcomes differ.
