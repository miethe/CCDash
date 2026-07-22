---
schema_version: 2
doc_type: report
report_category: feasibility
leg: tech
title: "CCDash Automated AAR Review — Tech Leg Findings"
status: draft
created: 2026-07-21
feature_slug: ccdash-automated-aar-review
exploration_charter_ref: docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-charter.md
feasibility: feasible-with-constraints
confidence: 0.82
dealkiller_correlation: exists
---

# Tech Leg — CCDash Data & Query-Surface Feasibility

## Verdict (one line)

**GO on the tech leg.** The AAR↔session correlation key already exists as a materialized
`entity_links` table (deal-killer cleared, `exists`). 2 of the ~5 surface flags are
computable now from DB columns; 3 need bounded deterministic derivation. No new ingestion
pipeline is required for the MVP; the one constraint is that the strongest linkage tier wants
a `session:` frontmatter ref on AAR docs (a cheap producer-side increment, with a two-hop
fallback that needs nothing).

---

## 1. Deal-Killer: AAR↔Session Correlation — `EXISTS`

CCDash **already materializes document→session links** in the `entity_links` table during
sync. There are three independent, layered strategies, all persisted as rows an automated
reviewer can query directly (no LLM, no recall-path model call):

| Strategy | Link created | Confidence | Source | Requires |
|----------|-------------|-----------|--------|----------|
| `explicit_session_ref` | `document → session` | 1.0 | `sync_engine.py:6592-6621` | AAR frontmatter carries `session:`/`session_id:`/`linkedSessions:` |
| `task_session_ref` | `document → session` (via progress-doc task) | 0.96 | `sync_engine.py:6574-6590` | progress doc with task→session_id |
| doc→feature→session (two-hop) | `document → feature` + `feature → session` | 0.64–1.0 | `sync_engine.py:6635-6656`; `reporting.py:79-91` | doc frontmatter has a feature ref; feature has linked sessions |

- Frontmatter session keys are parsed by `document_linking.py:72` (`_SESSION_KEYS = ("session",
  "session_id", "sessionid", "sessions", "linked_sessions", ...)`) via
  `extract_frontmatter_references` (`document_linking.py:954`, emits `sessionRefs` at :1076);
  the documents parser lifts them into `linked_session_refs` (`parsers/documents.py:629`).
- The read path is already built: `session_correlation.py:correlate_session` (:317) walks
  `entity_links` (`_correlate_explicit_link` :160) plus 4 heuristic fallbacks (phase/task hints,
  command tokens, lineage). `reporting.py:generate_aar` (:64) already resolves
  feature→session→document→task for a feature and emits evidence refs.

**Concrete key**: `entity_links(source_type='document', source_id=<doc_id>, target_type='session',
target_id=<session_id>)`. `doc_id` is a deterministic hash of the doc path
(`document_linking.py:make_document_id` :518). Given an AAR markdown path, its sessions are one
indexed query away.

**Constraint (bounded)**: `op story`-authored AARs may not currently emit a `session:` frontmatter
field, so the 1.0-confidence tier may be empty. Fallbacks (two-hop via feature ref, command-token
matching on `feature_slug`) degrade gracefully but at lower confidence. This is the charter's
`conditional` lever: a one-line producer increment (AAR emits the session id it describes) upgrades
every correlation to confidence 1.0. It is not a blocker — the two-hop path needs nothing new.

---

## 2. Surface-Flag Computability

| Flag | Verdict | Data source (cited) | Notes |
|------|---------|--------------------|-------|
| **Context ballooning** | `computable-now` | `types.ts:631-635` (`currentContextTokens`, `contextWindowSize`, `contextUtilizationPct`), `sqlite_migrations.py:175` (`context_window_size`), `tokensIn/Out` + cache token columns (`types.ts:617-629`); alert rule precedent `sqlite_migrations.py:1648` (`total_tokens > 600`) | Threshold on utilization pct or token-growth slope. Deterministic. |
| **Missing artifacts** | `needs-derivation` | Produced side computable-now: `session_artifacts` table (`sqlite_migrations.py:368-379`, `source_tool_name`, `type`), `updatedFiles`/`linkedArtifacts` (`types.ts:653-654`), `output_artifacts_json` (:1301). | "Missing" = cross-check AAR-claimed artifacts vs `session_artifacts`. The claim side must be extracted from AAR body (deterministic regex or a cheap parse), then diffed. |
| **Generic-agent-where-specialist-fit** | `needs-derivation` | "Used" side computable-now: `agentName`/`agentsUsed`/`subagentType` (`types.ts:600,607,673`), `skill_name` (`sqlite_migrations.py:233`), `subagent_parent_id` (:232). | Detecting `general-purpose` usage is trivial. Judging whether a *specialist fit* requires a task-domain→specialist map — a deterministic ruleset can flag candidates; the final judgment is a synthesis call that belongs to `op`/ARC (seam). |
| **Tech-stack ineffectiveness** | `needs-derivation` | `workflow_effectiveness.get_workflow_effectiveness` + `detect_failure_patterns` (consumed in `reporting.py:15,124,135`); tool-error patterns (`feature_forensics.py:190-191`), `tool_summary`/`toolSummary` (`session_correlation.py:120`, `types.ts:602`). | Success-score + failure-pattern aggregation exists per-workflow. "Stack ineffectiveness" (framework/language-specific) needs a new derivation mapping tool/file signatures → stack, then correlating with failure/retry density. |
| **(Bonus) Retry/failure churn** | `computable-now` | `detect_failure_patterns` already returns `patternType`, `sessionIds`, `averageRiskScore` (`reporting.py:135-201`) | Already surfaced in the AAR generator's `bottlenecks`. |

**Summary**: 2 computable-now, 3 needs-derivation (none `not-feasible`). Every "needs-derivation"
flag has its raw signal already in the DB; the derivation is deterministic feature-engineering, not
a model call — consistent with the AOS "cheap-extract, expensive-synthesize" constraint.

---

## 3. Integration Points (transport-neutral `agent_queries` pattern)

The build follows the exact shape of `reporting.py` / `session_correlation.py`:

| Layer | File | Action |
|-------|------|--------|
| Query service | `backend/application/services/agent_queries/aar_review.py` (new) | New `AARReviewQueryService`: given an AAR doc id/path, resolve sessions via `entity_links` (reuse `session_correlation`), pull session rows + `session_artifacts`, compute the flag set. Reuse `@memoized_query` (`reporting.py:63`). |
| Ports | `backend/application/ports` (`CorePorts`) | Reuse existing `storage.entity_links()`, `storage.sessions()`, `storage.documents()`, `storage.features()` — all already consumed by `generate_aar` (`reporting.py:75-113`). No new port needed for MVP. |
| Models | `agent_queries/models.py` | New `AARReviewDTO` (flags[], evidence_refs, triage_decision, confidence) alongside `AARReportDTO`. |
| REST | `backend/routers/agent.py` | New `GET /agent/aar-review/{document_id}` mirroring `/reports/aar` (:403) and `/feature-forensics/{feature_id}` (:254). |
| CLI | `backend/cli/commands/report.py` | New `report aar-review` subcommand mirroring `report aar` (:15-26). |
| MCP | `backend/mcp/server.py` | Expose the same service as a tool (transport-neutral rule). |

**Correlation reuse is total**: `session_correlation.correlate_session` and the
`entity_links` read in `reporting.py` are the load-bearing primitives — the new service is
mostly a flag-computation layer over data the AAR generator already assembles.

**Seam (defer to reuse leg)**: CCDash owns *evidence + deterministic triage flags*; the triage
*decision to escalate to a full ARC swarm* and any *model-driven synthesis / writeback* belong to
`op`/ARC. The tech leg confirms CCDash can emit a structured, evidence-backed flag bundle as the
input to that decision — it should not host the swarm.

---

## 4. Effort Estimate (H5-anchored)

**Anchor**: RF run telemetry (`9594fcc`, Tier 3, ~26 pt) — ingest + entity + analytics tab + FE.

| Slice | Est. | Delta vs anchor |
|-------|------|-----------------|
| AAR-review query service + flag computation (2 computable-now flags + churn) | 5–8 pt | Smaller: no new ingest, correlation + artifacts already in DB |
| 3 needs-derivation flags (artifact diff, generic-agent ruleset, stack map) | 5–8 pt | The variable cost; each is deterministic feature-engineering |
| Transport wiring (REST + CLI + MCP) + DTOs + tests | 3–5 pt | H6 plumbing; direct precedent in `reporting.py` wiring |
| (Conditional) AAR `session:` frontmatter producer increment | +1–2 pt | Cross-repo (`op story`), optional — two-hop fallback works without it |

**CCDash-native MVP total: ~13–21 pt (Tier 2 lower / Tier 3 upper).** Materially cheaper than the
RF telemetry anchor because the correlation substrate, session signals, artifacts table, and the
deterministic AAR generator already exist — this feature is predominantly a *new read/derivation
surface over existing data*, not new ingestion. FE is optional for the MVP (CLI/MCP/REST suffice for
the `op`/ARC consumer).

---

## Confidence & Residual Unknowns

- **Confidence 0.82.** High on correlation (verified in code, materialized table) and on the two
  computable-now flags. Lower on the exact derivation cost of the "fit" and "stack-ineffectiveness"
  flags, whose value hinges on a task-domain/stack mapping not yet in the repo.
- **Verified in code**: `entity_links` doc→session materialization, frontmatter session parsing,
  `session_correlation` read path, `generate_aar` feature-scoped join, session signal columns,
  `session_artifacts`, transport precedent.
- **Not verified (out of tech-leg scope)**: whether `op story` AARs today carry any session/feature
  frontmatter in practice (sampling real AAR docs would tighten confidence — hand to reuse/scope
  legs); whether the two-hop confidence (0.64) is high enough for autonomous triage or needs the
  frontmatter increment gate.
