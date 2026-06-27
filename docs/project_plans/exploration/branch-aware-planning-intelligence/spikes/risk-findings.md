---
schema_version: 2
doc_type: spike_findings
title: "Branch-Aware Planning Intelligence — Risk Findings (Leg: risk)"
status: complete
confidence: 0.85
created: 2026-06-04
feature_slug: branch-aware-planning-intelligence
assigned_to: backend-architect
charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
deal_killer_verdict: NOT TRIGGERED — partial
partial: false
---

# Risk Findings: Branch-Aware Planning Intelligence

## Deal-Killer Assessment — Primary Finding

**VERDICT: NOT TRIGGERED for the display-from-existing-data phase. TRIGGERED for the multi-branch scanning phase.**

Evidence supports a split verdict, which maps cleanly to a conditional go:

### What is already in the DB (display phase — deal-killer NOT triggered)

**`gitBranch` in session JSONL → parsed → stored in DB:**

- The Claude Code parser (`backend/parsers/platforms/claude_code/parser.py`, lines 2419, 2426–2427, 4338, 4388) extracts `gitBranch` from every JSONL entry where the `gitBranch` key is present. The parser accumulates the first non-empty value across the session and emits `gitBranch=git_branch or None` on the final `AgentSession` model.
- The `AgentSession` model (`backend/models.py`, line 222) carries `gitBranch: Optional[str] = None`.
- `SqliteSessionRepository.upsert()` (`backend/db/repositories/sessions.py`, lines 38, 71, 127) writes `git_branch` as a direct column in the `sessions` table, not inside a JSON blob. It is updated on every upsert.
- The `sessions` table has a `git_branch TEXT` column confirmed in `backend/db/sqlite_migrations.py` lines 194, 1712, 2485.
- `backend/routers/api.py` lines 832 and 1210 surface `gitBranch=s["git_branch"]` to the REST API.
- The frontend `AgentSession` type (`types.ts`, line 477) declares `gitBranch?: string`.

**`commitRefs`/`prRefs` from frontmatter → parsed → stored in `document_refs` table:**

- `backend/parsers/documents.py` lines 634–660 extract `commitRefs` and `prRefs` from document frontmatter.
- `backend/document_linking.py` line 88 lists `commit_refs` as a tracked frontmatter key; lines 956, 1051–1052 normalize and expose `commitRefs`/`prRefs`.
- `SqliteDocumentRepository._extract_document_refs()` (`backend/db/repositories/documents.py`, lines 84–92, 112–117) inserts rows into `document_refs` with `ref_kind='commit'` and `ref_kind='pr'`.
- The `document_refs` table schema (`backend/db/sqlite_migrations.py`, lines 478–492) has `ref_kind`, `ref_value`, `ref_value_norm` columns and appropriate indexes.

**`workingDirectories` (cwd) in session JSONL:**

- The Claude Code parser accumulates `cwd` entries per session into `session_context["workingDirectories"]` (parser.py lines 2227–2229, 4065). This is serialized into `sessionForensics` and stored as `session_forensics_json` in the `sessions` table. It is NOT a direct column — it must be extracted from the JSON blob to query.
- This means cwd data is retrievable but not directly filterable/indexable without a migration.

**`planning_worktree_contexts` table already exists:**

- Schema at `backend/db/sqlite_migrations.py` lines 1247–1272 shows `branch TEXT`, `worktree_path TEXT`, `base_branch TEXT`, `base_commit_sha TEXT` columns.
- The `PlanningCommandCenterQueryService` already reads this table and exposes `branch` on `PlanningCommandCenterWorktreeDTO` (`backend/application/services/agent_queries/models.py`, line 677; `planning_command_center.py`, line 348).
- A `WorktreeGitStateProbe` already exists (`backend/application/services/worktree_git_state.py`) that runs `git rev-parse`, `git status --porcelain`, `git stash list`, and `git rev-list` against known worktree paths via subprocess. It has a 5-second in-memory TTL cache and a 0.8-second per-call timeout. This is scoped to *known worktree paths stored in `planning_worktree_contexts`*, not arbitrary multi-branch scanning.
- The `TODO(PCP-Phase5)` comment in `backend/application/live_updates/topics.py` line 137 explicitly notes future `worktree_planning_topic` work.

**Codex sessions do NOT carry `gitBranch`:**

- `backend/parsers/platforms/codex/parser.py` line 1244 hardcodes `gitBranch=None`. For Codex-based sessions, branch must be inferred from worktree context or is unavailable.

### What does NOT exist yet (multi-branch scanning phase — deal-killer TRIGGERED for this scope)

- No mechanism exists to watch or scan session/document files from non-checked-out branches or arbitrary worktrees unless those paths are explicitly registered in `planning_worktree_contexts`.
- The `FileWatcher` and `FileWatcherRegistry` (`backend/db/file_watcher.py`) bind to fixed `sessions_dir`, `docs_dir`, `progress_dir` paths derived from the active project's `sessionsPath` configuration. Session files live at `~/.claude/sessions/` (global, shared across all branches) for Claude Code — so the watcher actually already captures sessions from all branches, since the JSONL files are not branch-scoped at the filesystem level. However, markdown docs (PRDs, progress files) are checked out per-branch and are NOT watched on non-active-checkout paths.
- There is no branch-to-planning-item linkage table. To join `sessions.git_branch` to `features`, a new `branch` column on `features` or a `session_branch_links` join table would be needed, plus a migration.
- Multi-project live updates for branch events have no SSE topic yet (the PCP-Phase5 TODO above).

---

## Risk Register

### R-01: File Watcher — Multi-Branch Path Binding Complexity

**Severity: HIGH | Likelihood: HIGH (if multi-branch doc scanning is in scope)**

The `FileWatcher` is a single asyncio task per project, watching fixed paths. Adding branch-specific doc directories requires:

1. Either changing the project configuration to enumerate worktree paths (one path bundle per worktree), or
2. Registering additional watch paths per branch dynamically.

The `FileWatcherRegistry` (P3-005) supports one watcher per `project_id`. Multi-branch scanning would require either: (a) composite project IDs per branch (breaks ADR-006 registry semantics), or (b) a new `BranchWatcherRegistry` abstraction parallel to the existing one.

**Known hazard (from memory):** uvicorn `--reload` watches the main worktree. During development, every agent file edit in the main repo resets uvicorn and resets all in-process job timers, including watcher registrations. This was confirmed in the Phase 4 progress report. Multi-branch watchers compound this problem: each server reload would drop all branch-watcher registrations.

**Mitigation:** Scope Phase 1 to display-from-existing-data (no new watcher paths). Branch-watcher design needs a dedicated spike before commitment.

---

### R-02: Session JSONL gitBranch — Data Quality / Coverage Gap

**Severity: MEDIUM | Likelihood: HIGH**

`gitBranch` is populated from the Claude Code JSONL format. Coverage depends on whether Claude Code emits `gitBranch` in each entry:

- **Claude Code sessions:** `gitBranch` is populated by the parser where present in JSONL. The field is optional (`gitBranch: Optional[str] = None`) and many sessions may have it as `None` if older Claude Code versions did not emit it.
- **Codex sessions:** `gitBranch=None` hardcoded — no branch provenance.
- **Subagent sessions:** Inherit the branch from the root session's parsing only if the JSONL entries carry it.

Without auditing the actual `.jsonl` files in the operator's dataset, coverage confidence is ~0.65. An operator with a mixed Claude Code + Codex workflow will have significant null-branch session populations.

**Mitigation:** Phase 1 UI must show branch as an optional field with graceful empty-state. Do not gate any planning logic on branch presence.

---

### R-03: DB Write Amplification Under ADR-007 (Multi-Branch Sync)

**Severity: MEDIUM | Likelihood: MEDIUM (if multi-branch doc scanning is in scope)**

If multi-branch doc scanning is enabled, each branch checkout of a markdown file would trigger a separate sync cycle. With N active worktrees each editing progress files or PRDs simultaneously:

- `N × (documents upsert + document_refs upsert + entity_links upsert + planning invalidation)` write operations per sync tick.
- `retry_on_locked` (`backend/db/repositories/base.py`) has `max_retries=3, backoff=0.5s` — a 3-retry exhaustion takes 3 seconds of blocking before failing loudly. Under multi-branch load, contention on the single SQLite WAL writer increases.
- The `busy_timeout=30000ms` (`backend/db/connection.py`, `backend/runtime/bootstrap.py`) is set on startup and provides the first line of defense, but does not protect against sustained write storms from simultaneous watcher syncs.
- ADR-007 (`docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`) requires: `retry_on_locked` on every new write path + a direct-count assertion test. Multi-branch write paths would be new and must comply.

**Mitigation:** Limit Phase 1 to read-only display. Phase 2+ multi-branch writes must: (a) serialize across branch watchers (one asyncio lock at the sync_engine level), (b) ship ADR-007-compliant retry + test coverage, (c) prefer additive migrations (new table) over ALTER TABLE on hot `sessions` or `documents`.

---

### R-04: SQLite `busy_timeout` and WAL Contention Under Multi-Worktree Load

**Severity: MEDIUM | Likelihood: MEDIUM**

The current `busy_timeout=30000ms` is established once per connection. However:

- The sync engine runs `aiosqlite` async — the asyncio event loop serializes most DB calls, reducing contention in the single-project case. Adding multiple watcher tasks (one per branch) means multiple concurrent async DB writers.
- SQLite WAL mode supports one writer at a time. Multi-branch watchers each triggering concurrent write batches will see more lock contention than the current single-project design.
- Independent SQLite connections (CLAUDE.md convention) must each issue `PRAGMA busy_timeout = 30000`. Any new branch-watcher sync path that opens its own connection must comply.

**Mitigation:** Use `retry_on_locked` and confirm `busy_timeout` is issued by any new connection factory. Design branch watchers to funnel writes through the same `sync_engine` instance (single writer) rather than spawning parallel write contexts.

---

### R-05: Query-Cache (`CCDASH_QUERY_CACHE_TTL_SECONDS`) Invalidation Under Live Updates

**Severity: MEDIUM | Likelihood: MEDIUM**

The planning query services use `@memoized_query` with a backend TTL of 600s (default). The frontend TanStack Query hooks use `staleTime: 30_000ms` (30s) across all planning hooks (`services/queries/planning.ts`). The backend SSE invalidation bus (`backend/application/live_updates/`) publishes `project.{id}.planning` and `feature.{id}.planning` topics that trigger TQ invalidation on the frontend.

Risk: Adding branch/session linkage fields to planning item responses changes the memoized query fingerprint requirements. If the `@memoized_query` cache key does not incorporate branch context, stale branch-unaware responses may be served for up to 600s after a branch switch.

Additionally, the `usePlanningCommandCenterQuery` hook accepts an optional `refetchInterval` but does not set one by default — callers must opt in. If live branch updates are expected to drive "active-session chips" on planning cards, a 30s staleTime without a `refetchInterval` means updates arrive only on next user navigation or explicit invalidation.

**Mitigation:** Ensure new branch-aware query methods carry branch context in their cache key (or bypass cache for branch-sensitive reads). Wire SSE invalidation events for branch state changes to existing planning topics. Confirm the frontend invalidation hook (`useLiveInvalidation`) subscribes to the relevant topics.

---

### R-06: ADR-006 Registry — Multi-Branch Projects Not Representable

**Severity: LOW-MEDIUM | Likelihood: LOW (if scoped to display-from-existing-data)**

ADR-006 (`docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`) makes the DB `projects` table authoritative. A project is identified by a single `path`/`sessions_path`/`docs_path` configuration. There is no concept of "branch variant of a project" in the registry.

Multi-branch display using existing `gitBranch` on sessions does NOT require registry changes — sessions already carry branch in the DB column. Only multi-branch doc scanning (watching separate checkout paths) would require registry-level changes.

Risk: If multi-branch scanning is later added by registering separate projects per branch, this multiplies the project count and may confuse the UI's project switcher. Worktree paths should be modeled as attributes of the `planning_worktree_contexts` table (already exists), not as separate project registry entries.

**Mitigation:** Use `planning_worktree_contexts` as the canonical worktree-branch model, not project registry entries.

---

### R-07: Migration Impact for Session–Branch–Feature Linkage Schema

**Severity: MEDIUM | Likelihood: HIGH (if linkage table is needed)**

The existing schema has:

- `sessions.git_branch` (direct column, queryable today)
- `document_refs` with `ref_kind='commit'` (commit hash → document link)
- `planning_worktree_contexts.branch` (operator-declared branch per feature/phase)
- No join table linking `sessions.git_branch` to `features.id` or `planning_items`

A new phase of this feature would need either:
1. An index on `sessions(git_branch, project_id)` — additive, no data migration.
2. A new `session_branch_links` or `feature_session_linkage` table — additive migration.
3. A `branch` column on `features` — additive column migration (requires `_ensure_column` and a migration gate).

All are additive (no destructive ALTER) and must pass through `sqlite_migrations.py` via the `_ensure_column` / `_ensure_index` helpers. The migration runner acquires a 30s `busy_timeout` and uses `IF NOT EXISTS` guards — safe for production.

**ADR-007 compliance for any new write path:** Every new write path must use `retry_on_locked` and ship a direct-count assertion test confirming the write is reflected in a subsequent query.

---

### R-08: Live Planning Board Updates — Transport Already Exists, Coverage Gap

**Severity: LOW | Likelihood: LOW**

The SSE live update infrastructure is already built:

- Backend: `backend/application/live_updates/` (broker, bus, publisher, topics)
- Frontend: `services/live/` (EventSource client, connection manager, `useLiveInvalidation`)
- Planning-specific topics: `project.{id}.planning`, `feature.{id}.planning`, `feature.{id}.phase.{n}`

The gap: `sync_engine.py` already calls `publish_planning_invalidation()` on session and document syncs. No branch-specific topic exists yet (`TODO(PCP-Phase5)`). Adding "branch changed" as a trigger for planning invalidation requires: (a) detecting branch transitions in the watcher (file-level signal is weak — would need a git HEAD read), (b) a new topic or payload field on the existing planning topic.

The 30s `staleTime` on all planning hooks means "live" updates are delayed up to 30s even with SSE invalidation. For session board "active-session chips," this is acceptable. For branch-switch visibility, this means a session on branch `feature/X` would appear in the planning board within 30s of the watcher picking up the new JSONL file.

**Mitigation:** No new transport work needed for Phase 1. Reuse existing planning invalidation. Phase 2 (branch-switch topic) is a low-risk additive change.

---

## Summary Table

| Risk | Severity | Likelihood | Phase 1 (display-only) | Phase 2 (multi-branch scan) |
|------|----------|------------|------------------------|-----------------------------|
| R-01: Watcher multi-branch binding | HIGH | HIGH | NOT applicable | Spike required before commit |
| R-02: gitBranch data coverage | MEDIUM | HIGH | Mitigate with null-safe UI | Same |
| R-03: Write amplification (ADR-007) | MEDIUM | MEDIUM | NOT applicable | ADR-007 compliance required |
| R-04: SQLite busy_timeout contention | MEDIUM | MEDIUM | NOT applicable | Single-writer enforcement |
| R-05: Query-cache stale branch data | MEDIUM | MEDIUM | Low — existing 30s staleTime OK | Add branch to cache key |
| R-06: ADR-006 registry mismatch | LOW-MEDIUM | LOW | NOT applicable | Use planning_worktree_contexts |
| R-07: Migration impact | MEDIUM | HIGH | Low — additive index only | ADR-007 compliant migration |
| R-08: Live update transport gap | LOW | LOW | Reuse existing planning topics | Additive topic, low risk |

---

## Verdict on Charter's Deal-Killer Condition

**Charter deal-killer:** "If session logs and planning artifacts contain no reliable branch/commit identifiers from which branch↔item↔session linkage can be derived without invasive per-branch git checkout scanning, abandon."

**Verdict:** NOT TRIGGERED for Phase 1 (display-from-existing-data).

- `gitBranch` is parsed from Claude Code JSONL, stored as `sessions.git_branch` (direct DB column), and exposed through the REST API and frontend type. This is real provenance, not inferred.
- `commitRefs`/`prRefs` are parsed from document frontmatter, stored in `document_refs` with `ref_kind='commit'|'pr'`, and queryable today.
- `planning_worktree_contexts.branch` provides operator-declared branch linkage to features/phases.
- A `WorktreeGitStateProbe` already runs `git status` against known worktree paths — no new invasive checkout scanning needed.

**TRIGGERED for Phase 2 (multi-branch doc scanning):**

- Markdown docs (PRDs, progress files) live in the checked-out working tree. Watching docs from non-active branches requires either: registering worktree paths in `planning_worktree_contexts` and watching those paths explicitly, or invasive per-branch checkout scanning. The former is tractable; the latter is the deal-killer.
- Therefore: Phase 2 must be gated on a separate named spike for watcher multi-branch binding design (R-01).

---

## Additional Deal-Killer Candidates

1. **`gitBranch` field absent from most existing sessions:** If the operator's session archive predates Claude Code's `gitBranch` JSONL emission (or consists mostly of Codex sessions), the branch column will be NULL for the majority of sessions. Branch-based filtering or grouping on the planning board would show "unknown branch" for most items. This is a UX degradation risk, not a technical deal-killer. The UI must handle null branch gracefully.

2. **`planning_worktree_contexts` is operator-populated, not auto-discovered:** The table requires operators to register worktree paths via the planning control plane launch flow. Passive auto-discovery of git worktrees is not implemented. For operators who do not use the launch control plane, `branch` on planning items will be empty.

3. **SSE live update delivery is in-process only:** The current broker/bus is in-memory per process. Cross-process delivery (e.g., worker process + API process) requires Postgres NOTIFY fanout, which is not enabled by default (SQLite backend). If the operator uses SQLite, live planning updates from the worker only reach the API process if they share the same process — which is the standard dev setup (`npm run dev`). This is a pre-existing constraint, not new to this feature.

---

## Confidence Signals

- **`gitBranch` in DB:** Confirmed by direct code read (parser, model, repo, router, type). Confidence: 0.95.
- **`commitRefs` in `document_refs`:** Confirmed by code read (parser, repo, migration schema). Confidence: 0.90.
- **`workingDirectories` not a direct DB column:** Confirmed — stored in `session_forensics_json` JSON blob. Confidence: 0.95.
- **Multi-branch scan requires separate watcher paths:** Confirmed by watcher architecture. Confidence: 0.90.
- **`gitBranch` coverage in live session data:** Unknown without data audit. Confidence on coverage completeness: 0.50.
- **Overall risk leg confidence:** 0.85 (above the 0.70 go threshold for this leg alone).
