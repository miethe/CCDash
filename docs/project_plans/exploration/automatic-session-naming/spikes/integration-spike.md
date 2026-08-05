---
schema_version: 2
doc_type: spike
title: "Session Naming — CCDash Integration Surface & Contract"
status: completed
created: 2026-08-04
feature_slug: automatic-session-naming
leg_id: integration
confidence: 0.82
estimated_points: 8
recommended_tier: 1
---

# Session Naming — CCDash Integration Surface & Contract

Method: derived from `git show --stat 2cb0df4 ad7c70c 5cb8e00` (the real SHAs — the charter's
`ad9a733` does not exist in this repo) plus direct inspection of every file those commits touched,
`backend/parsers/effort_provenance.py`, and every named consumption surface in the charter.

## 1. Enumerated Surface List

The shipped `skill_name_source` precedent (14 files across 2cb0df4 + ad7c70c) is **narrower** than
this charter's full ask: it never touched `session_detail.py`, `planning_sessions.py`,
`_client_v1_sessions.py`, CLI, MCP, `ccdash_cli`, `ccdash_contracts`, capabilities, or NDJSON
ingest. Tracing those surfaces directly (not by analogy) gives the real count below.

**Key architectural finding**: CLI (`backend/cli/`), MCP (`backend/mcp/tools/sessions.py`), the
standalone `packages/ccdash_cli` formatters, and NDJSON remote ingest are **all dynamic
passthrough** — they call `.model_dump()` / render dict keys generically rather than
declaring their own field lists. A field that exists on the underlying DTO or repository row
reaches all four with **zero code change**. This is the single biggest cost reducer versus a naive
read of the charter's surface list.

| Layer | File | Required? | Change |
|---|---|---|---|
| **Schema/DDL** | `backend/db/sqlite_migrations.py` | Required | `session_name TEXT`, `session_name_source TEXT`, `_ensure_column` ALTERs, `SCHEMA_VERSION` 49→50 |
| | `backend/db/postgres_migrations.py` | Required | mirror, same version bump |
| | `backend/db/migration_governance.py` (`COLUMN_PARITY_DRIFT_ALLOWLIST`) | Conditional | 0 entries expected (both nullable TEXT, no type/nullability drift) — verify only |
| **Provenance vocab** | `backend/parsers/session_name_provenance.py` (new) | Required | closed vocabulary module, mirrors `skill_provenance.py`/`effort_provenance.py` |
| **Repositories** | `backend/db/repositories/sessions.py` | Required | INSERT column list, `ON CONFLICT` UPDATE clause, positional bind |
| | `backend/db/repositories/postgres/sessions.py` | Required | mirror |
| | `backend/db/repositories/base.py` (Protocol) | Not needed | no new repo method — session naming has no cross-session inheritance step, unlike skill_name |
| **Parsers** | `backend/parsers/platforms/claude_code/parser.py` | Required | emit `sessionName=`/`sessionNameSource=` kwargs alongside `skillName=` |
| | `backend/parsers/platforms/codex/parser.py` | Required (if tech-codex leg confirms a field) | mirror |
| **Sync orchestration** | `backend/db/sync_engine.py` | Not needed | no inheritance backfill hook required (contrast with `skill_name_inherited` stat added in 2cb0df4) |
| **Backend models/API** | `backend/models.py` (`AgentSession`) | Required | `sessionName`, `sessionNameSource: Optional[str]` |
| | `backend/routers/api.py` (2 serialization sites: `list_sessions`, `get_session`) | Required | same file, 2 edits |
| | `backend/application/services/agent_queries/session_detail.py` | Free | `SELECT * FROM sessions` — raw row passthrough into `SessionDetailBundle.session`; only a doc-comment addition, no logic change |
| | `backend/application/services/agent_queries/models.py` (`PlanningAgentSessionCardDTO`) | Required | add `session_name`/`session_name_source` fields |
| | `backend/application/services/agent_queries/planning_sessions.py` (`build_active_session_card`/`build_session_card`) | Required | map row → card fields |
| | `backend/routers/_client_v1_sessions.py` | Required | `list_sessions_v1`/`search_sessions_v1`/`get_session_family_v1` — at least one path (`title=row.get("title", "")`, line 329) does explicit field selection |
| | `backend/routers/client_v1_models.py` (`SessionFamilyDTO` et al.) | Conditional | only if a v1 DTO other than the opaque `SessionDetailV1.session: dict` needs the field explicitly |
| | `backend/application/services/feature_surface/dtos.py` (`LinkedFeatureSessionDTO`) | Optional/deferred | this DTO already has a `title: str` field of unclear provenance — reusing vs. adding `session_name` is a design decision, not mechanical work (see OQ-1) |
| | `backend/routers/_client_v1_features.py` | Optional/deferred | only if the DTO above changes |
| **Capabilities** | `backend/routers/client_v1.py` (`_V1_CAPABILITIES`) | Recommended | add `"sessions:name"` per the advertise-don't-hardfail convention |
| **CLI (repo-local)** | `backend/cli/commands/session.py` | Free | dumps the same DTOs; zero change |
| **MCP** | `backend/mcp/tools/sessions.py` | Free | `.model_dump()` passthrough; zero change |
| **Standalone CLI** | `packages/ccdash_cli/**` | Free | table/json/markdown formatters derive columns from dict keys dynamically |
| **Contracts pkg** | `packages/ccdash_contracts/src/ccdash_contracts/models.py` | Free (unless DTO above changes) | `SessionDetailV1.session: dict[str, Any]` already opaque |
| **NDJSON ingest** | `backend/application/models/ingest.py`, `backend/application/services/ingest/session_ingest.py` | Free | `IngestSessionEvent.payload: dict[str, Any]` (extra="allow") is passed straight to `session_repo.upsert(event.payload, ...)` — the daemon (`packages/ccdash_cli/src/ccdash_cli/daemon/runner.py`) dumps the same parser model, so the field rides the wire for free once the parser and repository changes above ship |
| **Frontend types** | `types.ts` (`AgentSession`) | Required | `sessionName?: string \| null`, `sessionNameSource?: string \| null` |
| **FE identity render** | `components/SessionInspector.tsx` | Required | header/badge |
| | `components/SessionInspector/SessionInspectorPanels.tsx` (`SessionSummaryCard`) | Required | wire `session.sessionName` into the **already-existing** `deriveTranscriptIntelligenceTitle`/`deriveSessionCardTitle` fallback chain in `components/SessionCard.tsx` — this scaffold predates this feature (built for the flagged, deterministic "transcript intelligence" title system) and already accepts an `explicitTitle` param |
| | `components/SessionCard.tsx` | Required | no new fallback logic needed — just pass `session.sessionName` as `explicitTitle` at call sites |
| | `components/Planning/PlanningAgentSessionBoard.tsx` | Required | card title |
| | `components/Planning/CommandCenter/MultiProjectSessionBoard.tsx` | Required | mirror for multi-project board |
| | `components/FeatureModal/SessionsTab.tsx`, `components/DocumentModal.tsx`, `components/Planning/CommandCenter/PhasePlanTable.tsx`, other session-link renderers | Optional/deferred | today's fallback is the bare UUID, already resilient; upgrading these is polish, not contract-breaking |

**Count**: **16 required files** for the MVP wiring (schema ×2, provenance ×1, repos ×2, parsers ×1–2,
models/routers/services ×6, FE ×5, minus overlaps) + **1 recommended** (capabilities) + **4–6
optional/deferred** (feature-surface DTO reuse decision, secondary FE link renderers) + **1 new test
file** (~250–350 lines, scaled down from `test_skill_name_source_provenance.py`'s 423 lines since no
inheritance-backfill logic is needed). This is smaller in file count than `skill_name_source`'s
14-file precedent per surface touched, but reaches strictly more transport surfaces because the
transport-neutral passthrough layers (CLI/MCP/contracts/NDJSON) absorb the rest for free.

## 2. Provenance Design Decision

**Recommendation: yes, ship `session_name_source`**, following the `skill_name_source` (v49) and
`effort_tier_source` (v44) precedent exactly — a nullable value with no name/no source is a
materially different trust state than a name with unknown provenance.

Candidate closed vocabulary (new module `backend/parsers/session_name_provenance.py`):

| Token | Trust | Meaning |
|---|---|---|
| `provider_persisted` | Strongest | Read verbatim from a provider-written on-disk artifact (Claude Code / Codex own naming store — exact artifact pending tech-claude/tech-codex legs) |
| `derived_deterministic` | Weaker | Computed by CCDash from transcript content with no model call — this tier already has a **shipped precedent**: `backend/models.py:SessionInferredTitle.source` (`Literal["command","skill","workflow","artifact","existing_title","session_id"]`), consumed by the flagged `transcript_intelligence.py` module. `session_name_source` should NOT reuse that literal verbatim (different persistence semantics — one is request-time-computed, the other is a persisted column) but should sit at the same trust tier. |
| `operator_set` | Reserved, out of scope | Manual rename — explicitly out of scope per the charter; reserve the token now so a future rename feature doesn't need a second migration. |

Per CLAUDE.md's binding rule (echoed in the charter and in `skill_provenance.py`'s own docstring):
**consumers MUST treat an unrecognised token as "unknown provenance," never hard-fail** — the same
`KNOWN_SKILL_SOURCES` frozenset + fallback pattern in `skill_provenance.py` is the template.

## 3. Per-Surface Resilience Contract

| Surface | Null `session_name` render |
|---|---|
| `sessions` DB row | `NULL`, `session_name_source` also `NULL` (never a name with no source) |
| `AgentSession` (models.py/types.ts) | `sessionName: null` — explicit contract state, not omitted |
| `SessionDetailV1.session` dict | key absent from the row dict entirely on pre-migration rows (contract: `.get()` not `[]`) |
| `PlanningAgentSessionCardDTO` | `session_name: None` → planning_sessions.py card builder falls back to existing `agent_name`/`session_id` label logic (already the pre-feature baseline) |
| `SessionCard.tsx` / `deriveSessionCardTitle` | **already resilient today** — `explicitTitle` empty → falls through to `sessionTypeLabel` → raw `sessionId`. Zero new fallback code required. |
| `SessionInspector.tsx` header | same fallback chain via `SessionSummaryCard` |
| CLI/MCP JSON output | `null` in JSON, generic table/markdown formatters render `""` for a missing key (existing `table.py` behavior) |
| NDJSON ingest payload | field simply absent from `payload` dict on an old-schema daemon (`extra="allow"` forward/backward compat, ADR-006 F-6) |
| `/api/v1/capabilities` | absence of `"sessions:name"` in the list means "server predates this feature" — consumers must not hard-fail (existing convention, `docs/guides/external-api-lan-deployment.md`) |

## 4. Backfill Analysis

**Case (a) — name lives in the JSONL.** Backfill = re-parse of existing files. At ~16.6K sessions
(the reference cardinality from `ccdash-session-telemetry-capture-reality` memory), a full re-parse
is the same class of operation `sync_engine.py`'s existing `force=True` full-scan path already
performs for schema migrations — no new backfill mechanism needed, just re-running the ordinary
sync with the new parser code deployed. Cost is I/O- and CPU-bound file re-reads, not a new code
path; expect it to run in the same order of magnitude as any other full re-sync (minutes, not
hours, on local SQLite; longer on the node's PG if the lock-convoy hazard in
`ccdash-blank-transcript-diagnosis` memory is present — schedule off-peak).

**Case (b) — name only arrives via a launch-time hook (SessionStart).** Permanently impossible for
the ~16.6K existing rows, identical to `launcher`/`profile`/`model_variant` today (0/14,399 before
2026-08-01 activation, per `ccdash-launch-capture-activated` memory) — a hook cannot retroactively
observe a session that already ended.

**Value implication**: Case (a) is the only branch that yields value on the historical corpus.
Case (b) yields value **only forward** from activation — every session that hasn't started yet.
The two sibling technical legs (tech-claude, tech-codex) determine which case applies; if the name
is written into the JSONL transcript itself (most likely, given both providers show names in their
own UIs sourced from something), (a) applies and the ~16.6K-session backlog gets names on the next
full sync. If it's a live-store-only value (e.g. a SQLite/JSON side-store keyed by session id that
isn't itself JSONL), it may still be re-readable at backfill time even though it isn't inside the
JSONL proper — that's a **third, JSONL-adjacent** case worth flagging to the sibling legs.

## 5. H5 Estimation Anchor

**Anchor: `skill_name_source` end-to-end** (2cb0df4 + ad7c70c) = **5 points shipped** (per this
repo's own sizing convention for a schema-version-bump + dual-repo + FE-badge feature — inferred
from the file/test footprint: 14 files, 423-line dedicated test file, 18 direct-count tests, one new
provenance module).

**Delta drivers (H1: scope size, H2: uncertainty, H6: cross-cutting reach)**:
- **+ (H6, cross-cutting reach)**: this charter's surface is wider — it explicitly requires reaching
  `planning_sessions.py`, `_client_v1_sessions.py`, and the capability advertisement, none of which
  `skill_name_source` touched. That is real, additive work: ~6 more required files.
- **− (H1, scope size)**: no inheritance/backfill mechanism is needed (session naming has no
  parent→child propagation concept), which was ~150 of the 423 test lines and one of the 4
  non-trivial files (`backfill_skill_name_inheritance` on both repos + the `sync_engine.py` hook) in
  the precedent. That subtracts real work.
- **− (H2, uncertainty)**: the transport-neutral passthrough architecture (CLI/MCP/contracts/NDJSON
  all free) removes uncertainty that a naive reading of the charter's "reach every consumption
  point" language would otherwise imply — those are the majority of named surfaces by count, but
  zero-cost by construction.
- **Net**: the two effects roughly cancel (+6 files reached, −1 mechanism/−~150 test lines,
  −passthrough-layer uncertainty). Landing at the same order of magnitude as the precedent, with a
  ~20-30% upward nudge for the genuinely new reach into `planning_sessions.py`/capabilities/DTO
  design decision (OQ-1).

**Estimate: 8 points.** (Precedent 5 + ~30% for net wider reach, held under the charter's own >30%
delta-justification bar.)

**Tier recommendation: Tier 1.** Additive nullable columns, no destructive migration, no
cross-cutting behavioral change to existing routing/rollup logic (unlike `skill_name_source`'s
explicit "NOT a routing-feedback unblocker" scope note — session naming has no such adjacent
system to avoid disturbing). Requires the standard dual-DDL + parity-allowlist review gate but not
Tier 2/3-level architectural sign-off.

## 6. Deploy/Node Risks

**Yes — container rebuild required**, per the standing hazard in `ccdash-node-container-rebuild-required`
memory: the node runs a baked image (`podman-compose up -d` reuses the existing image; a `git reset`
+ restart runs stale code). Any schema/parser/API change needs `podman-compose build` on the node,
not just a restart.

**Compose env-allowlist**: `5cb8e00` establishes the binding pattern — `x-backend-shared-env` in
`deploy/runtime/compose.yaml` is an **explicit allowlist**; a flag set only in `.env` never reaches
the container namespace. Session naming likely needs **no new flag** if it ships unconditionally
(the `skill_name_source` precedent shipped with zero feature flag). If a rollout flag is added
(e.g. to gate the parser-side extraction while the naming source is still unverified by the sibling
legs), it MUST be added to both `deploy/runtime/.env.example` and the compose allowlist in the same
change, or it will silently read as `false` in `api`/`worker`/`worker-watch` while appearing set on
the host — exactly the bug `5cb8e00` fixed for five other flags.

**PG in-place upgrade**: schema-version bump (49→50) follows the same in-place upgrade path already
proven for v29→v35 (`npm run docker:hosted:smoke:seeded-pg`); no new migration risk class introduced.

## 7. Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Cross-session attribution — a name copied from/matching a different session (e.g. a stale value surviving a session-id collision, or a future inheritance feature creeping in without a hop-limit like `skill_name`'s one-hop guard) | High | Low | No inheritance logic in this feature by design (§1); if a future leg adds one, mirror `skill_provenance.py`'s one-hop + `(id, project_id)`-scoped join exactly — this exact join shape "fooled two prior spike legs" per that module's own docstring |
| Migration/column-parity drift (SQLite vs Postgres DDL diverge) | Medium | Low | `COLUMN_PARITY_DRIFT_ALLOWLIST` assertion test catches it mechanically; `skill_name_source` shipped with 0 entries as the template |
| FE null-handling regression (a component that assumes `sessionName` is always present) | Medium | Medium | `deriveSessionCardTitle`'s existing empty-string-falls-through behavior is the guard; new call sites must route through it rather than rendering `session.sessionName` directly |
| Ingest-contract versioning for remote sources (a daemon running an old parser never emits `sessionName`) | Low | Medium | Already handled structurally: `IngestSessionEvent.payload` is `extra="allow"`, and `session_repo.upsert()` treats every field as optional/nullable — an old daemon simply omits the key, no rejection (ADR-006 F-6) |
| Node deploy drift (schema ships to main but node runs stale baked image) | Medium | High (standing hazard) | `podman-compose build` (not just restart) on next node redeploy; verify via `/api/health/detail` schema version, per `ccdash-node-runs-baked-image-not-mounted-source` memory |
| `LinkedFeatureSessionDTO.title` field reuse ambiguity (OQ-1) creates two divergent "name" concepts | Medium | Medium | Resolve OQ-1 before implementation — decide reuse vs. new field in the plan, not mid-execution |

## Open Questions

- **OQ-1**: `LinkedFeatureSessionDTO.title: str = ""` already exists on the feature-linked-sessions
  surface (`backend/application/services/feature_surface/dtos.py`). Is its current population
  source (not traced in this leg) already a name-like value that should be *replaced* by
  `session_name` once available, or is it a distinct concept (e.g. a phase/task title) that should
  stay separate? Needs a targeted read of whatever currently populates it before the plan phase.
- **OQ-2**: Does the tech-claude/tech-codex JSONL evidence land inside the same parser pass that
  already produces `skillName`/`effortTier` (cheap, same file), or in a separate sidecar/store the
  watcher doesn't currently open (a new file-read path, more expensive)? This leg assumed the
  former; the sibling legs must confirm.
- **OQ-3**: Should `"sessions:name"` be added to `_V1_CAPABILITIES` unconditionally at ship time, or
  gated until coverage is proven, given the charter's own conditional-verdict language about
  per-provider coverage possibly landing at different times?

## Confidence Rationale

**0.82.** High confidence on the mechanical surface enumeration (grounded in direct commit diffs and
direct file reads, not inference) and on the resilience/backfill analysis (both follow exact,
already-proven precedents in this codebase). Confidence is capped below 0.9 because: (1) OQ-1 is a
real unresolved design fork that could add or remove a DTO from the required list, and (2) the H5
estimate's parser-layer cost for the Codex side is provisional on the tech-codex leg's finding
(whether Codex needs new extraction logic or can reuse an existing field, per that leg's own
open question about a deterministic derivation).
