---
leg_id: tech
confidence: 0.92
conclusion: "RF's 'CCDash telemetry' is real, wired, and schema-validated, but it is a same-repo local-file writeback (YAML mirrored under RF's own workspace root) with zero network/DB/OTEL egress toward CCDash — nothing crosses the process or filesystem boundary today, so CCDash cannot consume it via any existing seam and needs a new transport."
telemetry_state: defined_stubbed
recommended_transport: new_endpoint (POST /api/v1/ingest/rf-events, NDJSON/JSON, workspace-token auth) OR filesystem-watch adapter over RF's ccdash/events/ tree — new_endpoint preferred
---

# Tech Spike: Research Foundry → CCDash Telemetry Transport

## TL;DR

RF ships a real, tested, schema-validated "CCDash event" emission pipeline
(`emit_ccdash_event`, commit `c3a2545`, landed 2026-07-20 — the same day this
exploration started). It runs on every `rf writeback ... --targets ...,ccdash`
invocation and on search-router runs automatically. **But "writeback to CCDash"
writes to a directory named `ccdash/` that lives inside RF's own workspace
root** (`FoundryPaths.root / "ccdash"`), not to any CCDash-owned path, endpoint,
or database. There is no HTTP client, no OTEL exporter, and no shared-DB writer
anywhere in the RF emission path. CCDash has zero code that reads RF's
workspace tree. The two systems are fully disjoint today: RF's telemetry is
schema-defined and locally durable, but **not retrievable by CCDash without new
plumbing on at least one side.** This is the charter's "conditional" branch:
contract-first ingest, defer UI.

## Findings

### 1. RF emission is real, wired, and recently shipped (not aspirational)

- Commit `c3a2545` (`research-foundry`, 2026-07-20, "feat(search-router):
  aos-web/SearXNG discovery lane + P3 CCDash/SkillMeat + P2 MCP finishing")
  added `schemas/ccdash_event.schema.yaml` and extended
  `src/research_foundry/services/telemetry.py` with a `search_metrics`
  passthrough param on `emit_ccdash_event`.
- `emit_ccdash_event()` — `research-foundry/src/research_foundry/services/telemetry.py:132-258`
  — builds a full event dict from on-disk run artifacts (run.yaml, claim
  ledger, verification, swarm_plan/routing_decision) with **zero network
  calls or API keys required** (docstring, line 5-6: "No network or API keys
  are required: every value is derived from on-disk artifacts").
- Called from two writeback code paths in `research-foundry/src/research_foundry/services/writeback.py`:
  - `writeback()` — line 1009-1011 (`if "ccdash" in targets: ccdash_event_id_value = telemetry.emit_ccdash_event(...)`)
  - `approve_and_dispatch`-style path — line 1465-1474, sets `target_status["ccdash"] = "success"|"failed"|"skipped"`.
- Also auto-fires from the search router itself, independent of any explicit
  `rf writeback` call: `research-foundry/src/research_foundry/services/search_router/router.py:363-378`
  — every `run_search()` call ends by calling `emit_ccdash_event(run_id, paths=paths, search_metrics=metrics)`
  and writing the minted `event_id` back into `search_run["writebacks"]["ccdash_event_id"]`
  (line 376) before `search_run.yaml` is persisted — confirming RF spec §11.2's
  `writebacks.ccdash_event_id` field is genuinely populated, not a stub.
- 135 tests cover this (per commit message) — extensively verified in
  `research-foundry/tests/test_telemetry.py`, `test_writebacks.py`,
  `test_search_router_scorecard.py`, `test_writeback_router.py`,
  `test_approve_and_dispatch.py`. This is production-grade for RF's own
  purposes, not scaffolding.
- CLI surface: `rf writeback <run_id> --targets meatywiki,skillmeat,ccdash` and
  `rf ccdash summarize --period daily` — `research-foundry/README.md:131-136`,
  `research-foundry/src/research_foundry/cli_commands.py:719-732`.

**Verdict: emission mechanism is real+wired, not defined-but-stubbed, *from RF's own perspective*.**

### 2. But "CCDash" here means a local mirror directory inside RF's own workspace — not CCDash the application

- `FoundryPaths.ccdash` — `research-foundry/src/research_foundry/paths.py:114-115`:
  ```python
  @property
  def ccdash(self) -> Path:
      return self.root / "ccdash"
  ```
  `self.root` is the RF workspace root (`FoundryPaths.discover()` /
  `find_workspace_root()`), i.e. `research-foundry/`'s own tree — confirmed by
  `research-foundry/foundry.yaml:13: ccdash_path: ccdash/` (a config key that is
  itself relative to the RF workspace).
- `emit_ccdash_event()` writes two on-disk artifacts, both inside RF's tree
  (`telemetry.py:254-256`):
  - `runs/<run_id>/writebacks/ccdash_event.yaml` (per-run copy)
  - `ccdash/events/<event_id>.yaml` (workspace-level mirror)
  - Aggregation (`summarize()`, `telemetry.py:329-369`) writes
    `ccdash/daily/<date>.yaml` and `ccdash/summaries/<period>_<date>.yaml`.
  - Per-provider rollup (`provider_scorecard()`, `telemetry.py:372-456`) writes
    `ccdash/summaries/provider_scorecard.yaml`.
- **No HTTP client exists anywhere in the emission path.** Grep across
  `research-foundry/src/research_foundry/services/telemetry.py` and
  `writeback.py` shows no `requests`/`httpx`/`urllib` calls tied to CCDash;
  the only outbound network call in `telemetry.py` is `push_status()`
  (line 510-561), which PATCHes **IntentTree**, not CCDash, and is explicitly
  scoped to 4 milestone stages unrelated to the ccdash_event.
- No OTEL span/exporter references RF's `ccdash_event` anywhere in either
  repo.
- No shared database: RF has no DB dependency for this path at all — it's
  pure YAML-on-disk.
- The `frontend/runs-viewer/` SPA (`research-foundry/frontend/runs-viewer/public/data/*/run.json`)
  embeds `ccdash_event` as a **trace stage annotation** (`"stage": "ccdash_event"`)
  and lists `ccdash_event.yaml` as a writeback artifact filename with
  `"target": "ccdash"` — this is RF's own internal run-provenance viewer
  showing *that RF attempted the write*, not evidence the data reached CCDash.

**This is the crux of the charter's deal-killer test.** Read literally, RF
"just added CCDash telemetry from runs" is true only in the sense that RF
added a directory literally named `ccdash/` to its own workspace and started
populating it. Nothing about this crosses into the actual CCDash
application, API, or database.

### 3. CCDash has no code path that reads RF's output today

- Repo-wide grep for `research.foundry|research_foundry` in `CCDash/` returns
  only this exploration's own charter/spike files — zero production code
  references.
- `backend/parsers/` (`documents.py`, `progress.py`, `features.py`,
  `status_writer.py`, `sessions.py`, `capture_sidecar.py`,
  `workflow_sidecar.py`, `test_adapters.py`, `test_results.py`) has **no
  standalone-YAML-event parser**. YAML parsing that exists is scoped to
  markdown frontmatter (`documents.py`, `progress.py`, `features.py`,
  `status_writer.py`), not free-standing event files like
  `ccdash_event.yaml`.
- `backend/db/sync_engine.py` + `backend/db/file_watcher.py` walk/watch
  **registered project paths** (DB-authoritative registry per ADR-006) —
  RF's workspace (`research-foundry/`) is not, and would not naturally be, a
  registered CCDash project path; it is a sibling repo, not a project under
  dashboard management.
- `backend/services/integrations/telemetry_exporter.py` is CCDash's
  **outbound** exporter (CCDash → SkillMeat/SAM `SAMTelemetryClient`,
  `telemetry_exporter.py:27-29`) — wrong direction; it pushes CCDash's own
  execution outcomes out, it does not receive external events in.

### 4. `POST /api/v1/ingest/sessions` exists but is semantically the wrong shape

- `backend/routers/ingest.py:1-45` — ADR-006 NDJSON transport,
  `IngestSessionEvent` (`backend/application/models/ingest.py:13-28`) with
  `event_id, batch_id, schema_version, occurred_at, payload: dict[str, Any], source_ref`.
  `payload` uses `extra="allow"` for forward-compat, so *structurally* almost
  anything JSON-serializable can transit the wire format.
- **But the consumer hard-codes session semantics.**
  `backend/application/services/ingest/session_ingest.py:47-80`
  (`RemoteSessionIngestService`) dedupes on `(workspace_id, event_id)` then
  calls `SqliteSessionRepository.upsert(payload, project_id, source_ref=...)`
  (`backend/db/repositories/sessions.py:67`), which upserts into the
  `sessions` table — a table modeled around agent-session transcripts
  (JSONL logs, tool calls, model identity, launcher/profile capture columns
  per root `CLAUDE.md`), not RF's flat `ccdash_event` metric/governance
  object.
- `SessionIngestSource` Protocol (`backend/application/ports/ingest.py:37-47`)
  is transport-neutral in principle (`source_id`, `stream()`, `ack()`) and
  is documented as extensible ("filesystem, remote, Entire") — a plausible
  extension point for a *new* source type, but no code currently
  instantiates it for anything other than session-shaped payloads, and the
  downstream write target (`sessions` table) would need a schema
  mismatch to be papered over (dual-DDL, redaction pipeline
  (`backend/application/services/agent_queries/redaction.py`), correlation
  columns — all assume a transcript-bearing session). Force-fitting RF
  events through this path would pollute the `sessions` table with
  non-transcript rows.
- Health/capability surfaces (`GET /api/v1/capabilities`,
  `/api/health/detail` → `ingest_sources[]`) are keyed per-source
  (`backend/application/services/agent_queries/ingest_sources.py`) and would
  need a new `source_id` registered — feasible, but again assumes
  session-table semantics on the write side.

**Verdict: the existing ingest seam is transport-compatible (NDJSON, workspace
auth) but write-target-incompatible (sessions table, not a metrics/events
table). Reusing it as-is would be a modeling error, not a shortcut.**

### 5. Correlation-key mismatch (context for risk leg, noted here for completeness)

- RF's `ccdash_event` keys on `intent_id` / `task_node_id` / `event_id` /
  `run_id` (`research-foundry/schemas/ccdash_event.schema.yaml`).
- CCDash's existing correlation layer (AOS indexing, commit `676bcca`) keys
  on `aos_run_uuid` / session / trace / work UUIDs
  (`backend/services/aos_correlation.py`,
  `backend/application/services/session_intelligence.py`,
  `backend/application/services/agent_queries/session_detail.py`,
  `backend/routers/api.py`).
- These are disjoint ID namespaces today — no shared UUID exists between an
  RF `intent_id`/`task_node_id` and any CCDash `aos_*_uuid`. Any new ingest
  path lands as an unlinked row unless/until an explicit mapping is added
  (out of scope for this leg; flagged for the `risk` leg).

## Transport options

| Option | Effort | Fit | Notes |
|---|---|---|---|
| **New endpoint** `POST /api/v1/ingest/rf-events` (new NDJSON/JSON route, new `rf_events` table, workspace-token auth reusing ADR-008 pattern) | Medium (new router + model + repository + dual-DDL SQLite/PG + migration + ADR-007 write-failure test) | High — matches RF's already-flat, already-schema-validated `ccdash_event` shape almost 1:1; no session-table pollution; extensible to future non-session external telemetry (RF is unlikely to be the last such producer) | Cleanest long-term seam. RF would need one new emitter change: an HTTP POST instead of (or in addition to) the local YAML mirror — this is RF-side work, out of this exploration's scope per charter, but is a small, additive change on RF's side (RF already computes the full event dict in-memory before `dump_yaml`). |
| **Filesystem-watch adapter**: CCDash watcher registers RF's workspace `ccdash/events/` directory as a special-cased ingest source (new `SessionIngestSource`-style implementation, or a sibling non-session port) and periodically/`inotify`-polls RF's local YAML mirror | Medium-High | Medium — avoids any RF-side code change, but couples CCDash to a **filesystem path on the same host** as RF's workspace (breaks for the on-node/remote-Mac split noted in memory: RF runs data locally per-workspace, CCDash's registered-project model assumes projects it manages, not sibling tool repos) | Fragile: no natural "which RF workspace(s)" registration story, no auth/workspace boundary, and RF's `ccdash/events/*.yaml` files are mutable/re-mintable (event_id collision handling in `telemetry.py:176-187` — a re-emit is idempotent by design, but a filesystem watcher doing polling+diffing is reinventing what NDJSON+cursor already solved for the session case). |
| **Reuse existing `POST /api/v1/ingest/sessions`**, coercing `ccdash_event` into `IngestSessionEvent.payload` | Low (no new endpoint) | Low — semantically wrong; pollutes `sessions` table, trips redaction/correlation logic built for transcripts, requires a lossy adapter shim on the RF side to fake session fields | Rejected: cheapest but architecturally corrosive; violates "Router→Service→Repository" and column-parity conventions since the sessions table has no natural home for `metrics.providers`, `governance.*`, `reuse.*`. |
| **OTEL export** (RF emits OTEL spans/metrics, CCDash's `backend/observability/otel.py` collector-side ingests them) | High | Low-Medium | No OTEL code exists on RF's side today (confirmed: zero OTEL references in RF repo for ccdash_event); would require building an entirely new exporter in RF plus a collector-side consumer in CCDash. Disproportionate for RF's current low-cardinality per-run event volume. |
| **Shared DB** (RF writes directly into CCDash's SQLite/PG) | High, and structurally undesirable | Very Low | Violates the layered-architecture and cross-system-coupling principles called out in the charter's risk leg (dual-DDL ownership across two independently-versioned repos); rejected outright — not evaluated further. |

## Minimal contract recommendation

**Contract-first, ingest-only, no UI (matches charter's "conditional" verdict criterion).**

1. **CCDash side (this repo)**: add `POST /api/v1/ingest/rf-events` accepting
   RF's `ccdash_event` shape near-verbatim (it is already schema-validated
   JSON/YAML-serializable — `research-foundry/schemas/ccdash_event.schema.yaml`
   has `additionalProperties: true` throughout, so it tolerates CCDash-side
   field additions without RF-side changes). Land in a new
   `backend/application/services/agent_queries/rf_events.py` (or similar)
   +  new `rf_events` table (dual DDL, `retry_on_locked`, ADR-007 direct-count
   test, column-parity allowlist entry) rather than the `sessions` table.
   Auth: reuse workspace-token pattern (ADR-008) rather than inventing a new
   scheme.
2. **RF side (out of scope for this exploration, RF's deliverable per charter
   §"Out of Scope")**: add an HTTP POST call at the end of
   `emit_ccdash_event()` (`research-foundry/src/research_foundry/services/telemetry.py:254-258`,
   right after the local YAML mirror is written) — best-effort, matching the
   existing `push_status()` (`telemetry.py:510-561`) pattern of "never raise,
   return bool success." This is additive to the existing local-file
   behavior, not a replacement — RF keeps its local mirror as source of
   truth/audit trail and CCDash becomes a secondary, best-effort receiver.
3. **Correlation**: do NOT attempt UUID-level linkage in the minimal
   contract. Store `intent_id`/`task_node_id`/`run_id`/`event_id` as opaque
   string columns on the new table; defer any `aos_*_uuid` mapping to a
   follow-up once the `risk` leg's linkage-strategy question is resolved.
4. **Defer UI** until real events flow end-to-end through the new endpoint —
   this satisfies the charter's "RF telemetry transport is defined-but-not-yet-wired"
   conditional branch precisely.

## Open questions

- Does RF's maintainer (same operator, cross-repo) intend to add the HTTP
  POST call themselves, or would CCDash need to accept a pull-based model
  (CCDash polls RF's `ccdash/events/` mirror on a schedule, e.g. via a
  worker job under `backend/adapters/jobs/`)? Push (RF calls CCDash) is
  architecturally cleaner and matches RF's existing `push_status()`
  precedent; pull would need CCDash to know RF's workspace filesystem path,
  which reintroduces the fragility noted in the filesystem-watch option.
- Is RF's node deployment (`:7432`, per global CLAUDE.md) and CCDash's LAN
  node deployment the same host? If so, a LAN-local HTTP call
  (`10.42.10.76:<ccdash-port>`) is trivial; if RF and CCDash run on
  different hosts, auth/network-reachability needs explicit design (out of
  scope here).
- Volume/cardinality: RF emits at most one `ccdash_event` per run today
  (plus daily/summary rollups that are locally-aggregated, not
  per-event) — low enough that a naive per-event POST is fine; no batching
  design needed for v1.
- Should the new `rf_events` table also absorb non-search-router RF runs
  (the generic `execution_event`, spec §16.1, distinct from the
  search-router-specific `search_run` metrics passthrough)? The schema
  (`ccdash_event.schema.yaml`) is shared across both, so yes — the minimal
  contract should not special-case search-router events.

## External Resources

- RF spec: `/Users/miethe/dev/homelab/development/research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md`
  (§11.2 `search_run` lines 578-613, §16 CCDash telemetry lines 930-978)
- RF telemetry service: `/Users/miethe/dev/homelab/development/research-foundry/src/research_foundry/services/telemetry.py`
- RF writeback service: `/Users/miethe/dev/homelab/development/research-foundry/src/research_foundry/services/writeback.py`
- RF search router: `/Users/miethe/dev/homelab/development/research-foundry/src/research_foundry/services/search_router/router.py`
- RF paths: `/Users/miethe/dev/homelab/development/research-foundry/src/research_foundry/paths.py`
- RF schema: `/Users/miethe/dev/homelab/development/research-foundry/schemas/ccdash_event.schema.yaml`
- RF CLI: `/Users/miethe/dev/homelab/development/research-foundry/src/research_foundry/cli_commands.py`
- RF README (usage §10-11): `/Users/miethe/dev/homelab/development/research-foundry/README.md`
- RF commit `c3a2545` (2026-07-20) — the telemetry-shipping commit this spike validated
- CCDash ingest router: `/Users/miethe/dev/homelab/development/CCDash/backend/routers/ingest.py`
- CCDash ingest models: `/Users/miethe/dev/homelab/development/CCDash/backend/application/models/ingest.py`
- CCDash ingest service: `/Users/miethe/dev/homelab/development/CCDash/backend/application/services/ingest/session_ingest.py`
- CCDash ingest port: `/Users/miethe/dev/homelab/development/CCDash/backend/application/ports/ingest.py`
- CCDash telemetry exporter (outbound, wrong direction): `/Users/miethe/dev/homelab/development/CCDash/backend/services/integrations/telemetry_exporter.py`
- CCDash AOS correlation: `/Users/miethe/dev/homelab/development/CCDash/backend/services/aos_correlation.py`
