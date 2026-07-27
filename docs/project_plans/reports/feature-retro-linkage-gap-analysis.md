---
title: Feature Retro Linkage — Gap Analysis
description: Why CCDash-derived retros return empty telemetry for real features, and what must change so every session-linked datum is reachable from a Feature
audience: operators,developers,architects
tags: [retro, aar, entity-links, session-linkage, telemetry, cross-harness]
created: 2026-07-26
updated: 2026-07-26
category: analysis
status: draft
related: ["../../guides/aar-review-loop.md", "../../guides/feature-session-linkage.md", "../../guides/launch-time-capture-convention.md"]
---

# Feature Retro Linkage — Gap Analysis

## Purpose

This document exists to answer one question: **when we run a retro for a real feature, does CCDash actually give us everything it knows about that feature's execution?**

The answer today is **no** — and not marginally. For the feature used as the probe here, the shipped retro surfaces reported *zero* sessions, *zero* tokens and *zero* cost while ~$1,191 of measured spend across 24 sessions sat in the same database, one join away.

This is a gap register intended to feed remediation planning. It is not a remediation plan.

**Scope note.** The stated goal is that *every piece of data linkable to a Session — and thus up to a Feature — should be available to a retro*, even if not in the immediate metrics pack (i.e. a "drill deeper" affordance for important retros). Gaps below are graded against that goal, not against current documented behaviour.

---

## 1. Executive summary

| # | Gap | Severity | Nature |
|---|---|---|---|
| G-1 | Feature→session link derivation yields almost nothing (29 links / 14,399 sessions) | **Critical** | Design scope, not a bug |
| G-2 | Subagent sessions are structurally unreachable from their feature | **Critical** | Design gap |
| G-3 | Remote-ingested sessions can never link to a feature | **High** | Missing write path |
| G-4 | Codex sessions carry zero token/cost telemetry (2,713 sessions) | **High** | Missing parser logic |
| G-5 | A feature spanning multiple repos cannot be aggregated at all | **High** | Model constraint |
| G-6 | Parent/orchestrator session cost is null while children are priced | **Medium** | Roll-up gap |
| G-7 | Launch-capture columns are write-path dead (0/14,399) | **Medium** | Dead feature |
| G-8 | Retro DTOs omit most session-attached data | **Medium** | Surface scope |
| G-9 | No explicit "drill deeper" affordance on any retro surface | **Medium** | Missing contract |
| G-10 | Several DTO fields are hardcoded empty/zero | **Low–Medium** | Dead fields |
| G-11 | Node CCDash disk-exhaustion doom loop (**resolved**) + broken container healthcheck | **Ops** | Incident + latent defect |

The headline is G-1 + G-2. Everything else compounds them.

---

## 2. The probe case: Dynamic Artifact Provisioning P2 ("asm-p2")

### 2.1 What actually happened

The `asm-p2` execution ran as a Claude Code orchestrator session fanning out to ~23 `Task()` subagents, recorded as nested JSONLs:

```
~/.claude/projects/-Users-...-skillmeat/
  5111539d-….jsonl                                    ← orchestrator
  5111539d-…/subagents/agent-asm-p2-<name>-<hash>.jsonl ← 23 subagents
```

Discovery of these files is **not** a gap: `sync_engine.py:4838` uses `_rglob(sessions_dir, "*.jsonl")` and `claude_code/parser.py:1733` explicitly detects `path.parent.name == "subagents"`. They are ingested correctly.

### 2.2 What CCDash holds (recovered by walking the session family directly)

| Metric | Value |
|---|---|
| Sessions in family | **24** (1 orchestrator + 23 subagents) |
| `tokens_in` | **388,695,211** |
| `tokens_out` | **1,442,629** |
| Summed `display_cost_usd` | **$1,191.38** |
| Models | 15× `claude-sonnet-5`, 9× `claude-opus-4-8` |
| Rows missing cost | 1 (the orchestrator — see G-6) |
| `session_file_updates` rows | 459 |
| `session_artifacts` rows | 424 |
| `session_logs` rows | 1,675 |

Individual subagents are expensive and well-measured — e.g. `agent-asm-p2-merge` at 62.3M in / 172k out / $220.76.

### 2.3 What the retro surfaces returned

`ccdash feature report dynamic-artifact-provisioning-p2-engine-v1`:

```json
"telemetry_available": { "tasks": false, "documents": true, "sessions": false },
"linked_sessions": []
```

`ccdash report aar --feature dynamic-artifact-provisioning-p2-engine-v1`:

```
key_metrics.total_cost     = 0.0        (reality: $1,191.38)
key_metrics.total_tokens   = 0          (reality: 388.7M in / 1.44M out)
key_metrics.session_count  = 0          (reality: 24)
timeline.started_at        = ""
timeline.duration_days     = 0.0
turning_points             = []
workflow_observations      = []
bottlenecks                = []
successful_patterns        = []
lessons_learned            = ["Insufficient execution evidence was available to derive strong lessons"]
```

**The AAR reports insufficient evidence about a feature whose execution evidence it is storing.** That single line is the clearest statement of the problem: the retro is not evidence-limited, it is *join*-limited.

---

## 3. Gap register

### G-1 — Feature→session link derivation yields almost nothing

**Severity: Critical.**

Measured across the whole corpus:

| Link pair | Rows |
|---|---|
| `feature → task` (child) | 12,021 |
| `document → task` (child) | 8,847 |
| `document → document` (related) | 6,916 |
| `document → feature` (related) | 4,465 |
| **`feature → session` (related)** | **29** (27 `auto`, 1 `manual`, 1 `test`) |

29 links across **14,399 sessions** — 0.2%. Every other entity pair links in the thousands. Sessions are the outlier.

**Root cause (from `_rebuild_entity_links`, `backend/db/sync_engine.py:5491–6389`).** There are exactly two producers of `feature→session` rows:

- **Producer A — task-frontmatter back-reference** (`sync_engine.py:5953–5973`). Requires a `ProjectTask` row carrying a non-empty `session_id`. Confidence fixed at 1.0.
- **Producer B — session evidence** (`sync_engine.py:6157–6376`), with two evidence channels:
  - **B1 file-path**: a `session_file_updates.file_path` matching `feature_ref_paths[feature_id]` via `_path_matches` (`sync_engine.py:5589`).
  - **B2 command-path/slug**: a parsed slash-command event whose `featureSlug` resolves to the feature (weight 0.96).

**The scoring gate is permissive.** `if base_confidence <= 0: continue` (`sync_engine.py:6270–6272`) is the only *post-signal numeric* rejection — there is no minimum-confidence threshold, and no feature flag gates this inner block. Once any evidence weight exists, a row is written.

But it is not the only rejection. B1 rejects earlier, twice: a non-matching path (`6170`) and **alias disagreement** (`6172–6180`); and task-bound `(feature, session)` pairs are skipped outright (`6195–6196`). The rebuild *dispatch* is also feature-flagged even though this inner block is not (see G-2).

The real constraint is the **evidence surface**:

`feature_ref_paths` is built at `sync_engine.py:5866–5941` from the feature's `linkedDocs[].filePath`, `relatedRefs`, `prdRef`, and linked tasks' `source_file`. Precisely: a `linkedDocs` path is admitted when its derived slug is absent *or* matches the feature (`5881–5889`), and a `relatedRefs` entry is admitted when it looks path-like and its slug matches (`5896–5910`).

**The code does not restrict this set to planning documents** — an implementation source file *can* enter it, if it appears in the feature's linked-document catalogue. The limitation is upstream: that catalogue is populated by the document scanner from planning artifacts, so in practice the set is planning paths. The accurate framing is therefore:

> The link surface is bounded by the feature's *document catalogue*, not by any map of the code the feature owns. A session that spends $220 writing the feature's actual implementation — but never edits a catalogued document and never carries a slash-command tag — has no path to that feature. B1 has nothing to match; B2 has nothing to parse.

This is the design as implemented, and it is the primary reason retros are empty.

**Corollary — `load_session_mappings()` is not the culprit.** A zero-config project still receives the full default marker set (`backend/session_mappings.py:1036–1080`, defaults at `41–347`); `workflow_command_markers()` never returns empty. Configuration is not the missing ingredient.

---

### G-2 — Subagent sessions are structurally unreachable from their feature

**Severity: Critical.** This is where the actual work — and the actual spend — lives.

All 24 asm-p2 sessions have `command_slug = ''`. That is expected: the slash command was invoked in the *orchestrator*'s context; `Task()`-spawned subagents do not emit `<command-name>` tags or `type="command"` log rows of their own. **B2 is therefore unavailable to every subagent session, by construction.**

Producer A does not rescue them either: `task_bound_feature_sessions` is keyed on the task's recorded `session_id`, which is the orchestrator's ID, not the subagent's (`sync_engine.py:5973`).

That leaves B1 — and here the evidence *does* exist. **41 `session_file_updates` rows in this family write the feature's own canonical plan file**, attributed to the subagents' own session IDs (e.g. `S-agent-a3eb222753ceb1cdc`):

```
/Users/…/skillmeat/docs/project_plans/implementation_plans/features/
  dynamic-artifact-provisioning-p2-engine-v1/phase-*.md
```

`_path_matches` handles the absolute-vs-relative case via suffix matching (`sync_engine.py:5589–5600`), and `feature_slug_from_path` resolves that path shape back to the feature (`backend/document_linking.py:601–633`). B1 *should* have fired at weight 0.95.

It produced zero links.

**Open question — the single highest-value next diagnostic.** Two candidate explanations remain, and they imply very different fixes:

1. **The rebuild ran but the alias gate rejected.** After `_path_matches` succeeds, B1 additionally requires the path-derived slug to agree with the feature's alias set (`sync_engine.py:6172–6180`, via `_feature_slug_matches_feature`). The feature ID is `dynamic-artifact-provisioning-p2-engine-**v1**` while its plan documents carry `feature_slug: dynamic-artifact-provisioning-p2-engine` — observed directly in the `feature report` output's `linked_documents[]`. If the alias set does not reconcile the `-v1` suffix, every one of the 41 signals is silently rejected. → Fix is *slug normalization*.
2. **The feature's document catalogue was empty or unmatched at rebuild time**, so `feature_ref_paths` never contained the plan path to match against (see the G-1 correction above — the set is catalogue-bounded). → Fix is *catalogue population/ordering*.

**Note on the "sweep never ran" hypothesis — largely ruled out.** `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` (default **true**) routes the watcher hot path to `rebuild_links_for_entities` (`sync_engine.py:4389–4407`). But that method's Phase 2 calls `_rebuild_entity_links(project_id, operation_id=…)` with **no ID filter** (`sync_engine.py:3690–3697`) — i.e. it runs the *full* derivation anyway, only omitting `docs_dir`/`progress_dir`. So the feature→session derivation almost certainly did execute; hypothesis 1 or 2 is the live explanation.

*(Separate observation worth a ticket: `rebuild_links_for_entities` does a **scoped delete** followed by a **global re-derive**, then reports the global `created` count as `auto_links_rebuilt`. The in-code comment claims it "naturally skips entities not in the working set" — it does not. That is misleading at best and a performance trap on the hot path.)*

This was not settled empirically because the local cache DB was relocated out from under the analysis mid-session (see §5). **Resolving it is remediation Step 0** — see §4.

---

### G-3 — Remote-ingested sessions can never link to a feature

**Severity: High.**

`RemoteSessionIngestService.process` upserts the flat `sessions` row (`backend/application/services/ingest/session_ingest.py:128–135`) and advances the ingest cursor (`136–142`) — but it never calls `upsert_logs` / `upsert_file_updates` / `upsert_artifacts`, precisely the three child tables the evidence loop reads (`sync_engine.py:6037–6039`).

A remote-ingested session is therefore visible in the DB and in `session_detail`'s token block, but contributes **zero** link candidates. It can only reach a feature if an independently-synced task file names its exact `session_id` (Producer A), which the ingest transport does not guarantee.

This matters directly for the agentic-node deployment, which is `filesystemSourceOfTruth: false` and fed by ingest.

---

### G-4 — Codex sessions carry zero token and cost telemetry

**Severity: High.** Measured, whole corpus:

| Platform | Sessions | With tokens > 0 | With cost > 0 |
|---|---|---|---|
| Claude Code | 11,686 | 11,246 | 10,936 |
| **Codex** | **2,713** | **0** | **0** |

19% of all ingested sessions have no telemetry whatsoever. `tokens_in`/`tokens_out` are initialised at `backend/parsers/platforms/codex/parser.py:481–482` and never incremented — no `usage` parsing exists — and `totalCost` is the literal `0.0` at `parser.py:1266`.

Two further Codex-specific reachability holes:
- Sessions whose `cwd` does not resolve are stored with `project_id=""` (`sync_engine.py:4764–4766`). `_rebuild_entity_links` is always invoked scoped to a registered project, so these are permanently outside every sweep. *(Measured 0 such rows in the local snapshot — the hole is latent, not currently firing.)*
- `CCDASH_CODEX_INGEST_ENABLED` defaults to `False` (`backend/config.py:172`), so out of the box Codex sessions never arrive at all. *(It is enabled on this Mac — hence the 2,713.)*

Codex file-update evidence is also narrower: `updated_files` derives from shell-command regex heuristics applied only when the invoking tool name is in `_COMMAND_TOOL_NAMES = {"exec_command","shell_command","shell"}` (`codex/parser.py:30, 897`). A native `apply_patch`-style edit not wrapped in one of those yields no file-update row — which starves B1 for Codex the same way missing command tags starve B2 for subagents. *(Whether real Codex transcripts always wrap edits this way is UNVERIFIED.)*

---

### G-5 — A feature spanning multiple repos cannot be aggregated

**Severity: High.**

`dynamic-artifact-provisioning` is not one repo's feature. It has artifacts in **three**:

- `agentic_meta_dev` — PRD, `-p2-fleet-v1` plan, progress, worknotes, findings
- `skillmeat` — `-p2-engine-v1` plan, progress
- `skillmeat-ce-parity` — `-p2-engine-v1` plan

But `features` rows are project-scoped. Both feature rows resolve to the SkillMeat project only. Meanwhile **52 distinct sessions touch `agentic_meta_dev` paths**, and `agentic_meta_dev` is not a registered project in the local registry at all; `skillmeat-ce-parity` has **0** sessions locally while being registered on the node as `ce-parity`.

Consequences:
- The fleet half of this feature's execution can never roll up to the engine half's feature row.
- A complete retro would have to span **two databases** (Mac cache + node Postgres) with no mechanism to join them.

Even with G-1/G-2 fully fixed, this feature's retro would remain structurally partial.

---

### G-6 — Orchestrator session cost is null while children are priced

**Severity: Medium.**

The parent session carries 71,276,393 `tokens_in` / 486,787 `tokens_out` but `display_cost_usd = None`, while all 23 children are priced (`cost_provenance = 'recalculated'`). Any consumer summing `display_cost_usd` across a family silently under-reports by the orchestrator's entire share.

The parent also shows `git_branch = 'development'` — the workspace root name, not the actual feature branch — which would misattribute branch-scoped analytics.

---

### G-7 — Launch-capture columns are write-path dead

**Severity: Medium.** Measured population across all 14,399 sessions:

| Column | Populated |
|---|---|
| `launcher` | **0** |
| `profile` | **0** |
| `effort_tier` | **0** |
| `model_variant` | **0** |
| `model_slug` | 2,894 (20%) |
| `workflow_id` | 2,958 (21%) |
| `skill_name` | 767 (5%) |
| `git_branch` | 11,666 (81%) |

The four launch-capture columns documented in `docs/guides/launch-time-capture-convention.md` have never been written. The Codex parser never imports the capture sidecar at all (zero references). Retro questions of the form *"did high-effort runs actually go faster?"* are unanswerable — not sparsely, but categorically.

`model_slug` at 20% and `skill_name` at 5% also make model-mix and skill-attribution analysis unreliable rather than merely incomplete.

---

### G-8 — Retro DTOs omit most session-attached data

**Severity: Medium.** None of the five retro surfaces expose, as typed fields:

- Full token breakdown — `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_input_tokens`, `tool_reported_tokens` (all available in `session_detail._extract_token_telemetry`, `session_detail.py:187–205`). Only a collapsed `total_cost`/`total_tokens` pair, or a 4-bucket model-family rollup, escapes. **For an orchestration-heavy workload this is the wrong summary** — cache-read vs cache-creation is the main cost lever and it is invisible.
- **Per-phase breakdown** — no surface offers one, at any granularity.
- Subagent hierarchy — read internally by `aar_review_enrichment.gather_session_metadata` for a single `subagent_type` string, never returned as a list. For a 23-subagent fan-out this discards the entire structure.
- Session↔phase/batch/task correlation (`session_correlation.py`) — explicitly consumed only by the planning session board, by none of the retro surfaces.
- Git provenance (`git_branch`, `git_commit_hash`) — present on `PlanningAgentSessionCardDTO` (`models.py:959–960`), absent from all five retro DTOs.
- Transcript entries, tool-call-level detail (counts, per-tool error rates, timestamps), context-window telemetry as structured fields, general entity links, AOS cross-tool correlation, redaction metadata.

---

### G-9 — No explicit "drill deeper" affordance

**Severity: Medium.** This is the specific capability the retro goal calls for.

Handoffs from a retro surface to `ccdash_session_detail` / `ccdash_session_transcript` exist only as **bare string IDs** that a caller must know to reuse. No retro DTO carries a typed ref, `href`, or `next_tool` field. The pattern already exists elsewhere in the codebase — `PlanningAgentSessionCardDTO.transcript_href` / `.planning_href` (`models.py:948–949`) — it is simply not used by any retro surface.

`feature-evidence-summary` is worse: it exposes only `session_count` and no session IDs whatsoever, so **no drill-down is possible from that surface at all**.

Notably, `aar_review.py` already calls `session_detail.get_session_detail()` per session with `include={tokens, subagents, artifacts, links}` (`aar_review_enrichment.py:311–340`) — it fetches the rich bundle server-side and then discards it into free-text evidence strings. The data is already being retrieved; it is thrown away at the DTO boundary.

---

### G-10 — Hardcoded-empty DTO fields

**Severity: Low–Medium.** Fields that exist in the contract but can never carry a value:

| Field | Site | State |
|---|---|---|
| `AARReportDTO.workflow_observations[].evidence_refs` | `reporting.py:186` | hardcoded `[]` |
| `WorkflowDiagnostic.representative_sessions[].total_cost` / `.total_tokens` / `.model` | `workflow_intelligence.py:35–51` | hardcoded `0.0`/`0`/`""`; upstream `workflow_registry.py:509–531` never selects the columns |
| `FeatureEvidenceSummary.workflow_mix` | `feature_evidence_summary.py:117, 287–294` | always `{}` |
| `FeatureEvidenceSummary.telemetry_available.documents` / `.tasks` | `feature_evidence_summary.py:309–310` | hardcoded `False` |
| `WorkflowSummary.representative_session_ids` | `project_status.py:79` | hardcoded `[]` |
| `WorkflowDiagnostic.success_count` / `.failure_count` / `.cost_efficiency` | `workflow_intelligence.py:182–208` | conditionally zero — workflows discovered only via registry or failure-pattern paths keep model defaults |

**Correction to prior belief:** a `success_rate` field on `WorkflowDiagnostic` was previously suspected of being unpopulated. **No such field exists.** `success_rate` lives on `WorkflowSummary` (`models.py:75`) and *is* correctly populated from `successScore` (`project_status.py:73–78`). The real always-empty neighbour is `representative_session_ids`. Any remediation ticket carrying the old claim should be corrected.

---

### G-11 — Node disk-exhaustion doom loop (resolved) + broken container healthcheck

**Severity: Ops / blocker for node-side work.**

`rocket-fedora` root filesystem is **100% full** (99 G, <1 MB free). `ccdash_postgres_1` is in a crash loop — it cannot complete WAL recovery:

```
FATAL: could not write blocks … No space left on device
LOG: startup process exited with exit code 1
```

58 restarts before intervention. A self-amplifying loop was active: the `ccdash_worker` / `worker-watch` containers retried against the dead Postgres and streamed tracebacks into journald, which grew **2.3 G → 2.7 G in ~40 minutes** and consumed the remaining free space — threatening every other service on the node (skillmeat, meatywiki, artifact-atlas, intenttree, ollama).

**Actions taken:** pruned dangling podman images (870 → 483 images, 55.3 GB → 36.4 GB reclaimable in podman's accounting); stopped the entire ccdash stack to halt the log flood. Disk is now stable rather than actively degrading.

**Additional finding — the node's container healthcheck is broken and reports false negatives.**

After recovery, `ccdash_api_1`, `ccdash_worker_1` and `ccdash_worker-watch_1` all report `unhealthy` while being fully functional. The cause is a malformed healthcheck command in the image definition — the shell quoting is mangled:

```
Test: ["CMD-SHELL", "/bin/sh -c python' '-c' ''import os, urllib.request; ..."]
→ /bin/sh: 1: Syntax error: word unexpected (expecting ")")  [exit 1]
```

It fails on a shell syntax error on every invocation and has **never succeeded** (`FailingStreak: 15` and climbing from container start). Meanwhile the endpoint it targets, `/api/health/ready`, returns `state: ready, status: pass, ready: true, degraded: false`, and the API serves real authenticated queries (20 projects).

This is a pre-existing deploy defect, independent of the disk incident, and an operational trap: **the node's container health signal is unusable** — it cannot distinguish a real outage from its own quoting bug, and it will mask a genuine failure the same way it currently masks success. Worth fixing before any automated restart/alerting keys off container health.

**Resolution — recovered, no operator action outstanding.**

The unlock was clearing `~/.cache` (2.6 GB of uv/playwright/pnpm caches — regenerable by definition), which restored enough headroom for podman to function again; the image prune that had been failing with I/O errors then succeeded (870 → 255 images). With ~4 GB free, Postgres completed WAL recovery cleanly on restart (`database system is ready to accept connections`, checkpoint complete) and **all 20 projects survived intact** — no data loss despite the corruption warning. The `sudo journalctl --vacuum-size` step proved unnecessary.

**The durable lesson is the failure shape, not the full disk.** This was a self-amplifying loop: Postgres died of no space → the workers retried against dead Postgres → tracebacks flooded journald at ~10 MB/min → that consumed the very space Postgres needed to finish recovery. Freeing space alone would have been re-consumed; **breaking the loop (stopping the stack) was the precondition for recovery.** Two follow-ups worth tickets: a backoff/circuit-breaker on worker DB-connection retries so a dead dependency cannot exhaust the disk, and a disk-headroom guard on the node.

---

## 4. What remediation has to cover

Grouped by theme, sequenced by dependency. Sizing deliberately omitted.

**Step 0 — Resolve the G-2 open question first.** Re-run a full `_rebuild_entity_links` sweep for the SkillMeat project and observe whether the 41 file-path signals produce links. This single experiment discriminates between "the sweep never ran" (operational fix) and "the slug alias gate rejected" (normalization fix) and should gate the design of everything below. It is cheap and decisive.

**Theme 1 — Make sessions link (G-1, G-2).**
- Widen the evidence surface beyond the document catalogue. Note the code already *permits* implementation paths in `feature_ref_paths` — the gap is that nothing populates them. Feeding the feature's owned code paths into that set may be a smaller change than it appears. Branch/commit correlation is another candidate: `commit_correlations` is already computed but is not used as a link producer.
- Give subagents a linkage path. The cheapest correct answer is probably **lineage inheritance**: if an orchestrator links to a feature, its `subagent_parent_id` family should inherit that link with a derived confidence. This alone would have attached all 23 asm-p2 subagents and their $1,191.
- Normalize feature-slug aliases so version suffixes (`-v1`) cannot silently break matching.

**Theme 2 — Close ingestion holes (G-3, G-4).**
- Make `RemoteSessionIngestService` persist the evidence child tables, or route remote sessions through `SessionIngestService.persist_envelope`.
- Parse `usage` in the Codex parser so 2,713 sessions stop reporting zero.
- Verify Codex `apply_patch` file-update capture against a real transcript.

**Theme 3 — Fix roll-ups and dead columns (G-6, G-7).**
- Price orchestrator sessions, or define family-level cost as the contract and compute it explicitly.
- Either wire the launch-capture sidecar read path or retire the four dead columns. Shipping columns that are structurally never written is worse than not having them.

**Theme 4 — Widen the retro surface and add drill-down (G-8, G-9, G-10).**
- Add per-phase and cache-token breakdowns; surface the subagent tree.
- Adopt the existing `*_href` ref pattern on retro DTOs so drill-down is a contract, not a convention.
- `aar_review` already fetches the full bundle — stop discarding it.
- Delete or populate the hardcoded-empty fields.

**Theme 5 — Cross-repo features (G-5).** The hardest and most architectural. Needs an explicit decision: either a feature-federation concept spanning projects, or an accepted documented limitation. Worth deciding deliberately rather than by default.

**Theme 6 — Node resilience (G-11).** The outage itself is resolved and needs nothing further. Two hardening follow-ups remain: a backoff/circuit-breaker so worker DB-retry storms cannot exhaust the disk, and a fix for the malformed container healthcheck that currently makes the node's health signal unusable in both directions.

---

## 5. Method and caveats

**How the figures were obtained.** Direct read-only SQL against the local SQLite cache (`data/ccdash_cache.db`, 14 GB, 14,399 sessions), plus live invocation of the shipped CLI surfaces (`ccdash feature report`, `ccdash report aar`) against the SkillMeat project. Code claims were produced by three parallel bounded audit legs and then **spot-verified against the database** rather than accepted as written — which is how the `success_rate` correction in G-10 and the Codex 2,713/0/0 figure in G-4 were established.

**Adversarial validation.** A subsequent independent pass (gpt-5.6, read-only, instructed to treat "only"/"exactly"/"never" as claims needing direct evidence) returned **MAJOR-ERRORS** against the first draft and forced three corrections, all applied above:
1. G-1 overstated `feature_ref_paths` as planning-documents-only — the code admits any catalogued path (`5881–5910`); the limitation is upstream, in what populates the catalogue.
2. G-1 called the confidence check "the only reject gate" — it is the only *post-signal numeric* one; B1's path and alias gates and the task-bound skip reject earlier.
3. G-3 said remote ingest writes "only the sessions row" — it also advances the ingest cursor.

Claims 1, 4, 5, 7 and 8 of that pass were confirmed unchanged. Readers should weight the corrected G-1 causal framing accordingly: the *practical* conclusion (code-only sessions do not link) survived, but the mechanism is catalogue-bounded rather than kind-restricted.

**Caveats.**
- Figures are from the pre-relocation snapshot: sessions through 2026-07-21, DB mtime 2026-07-22. A storage relocation to `/Volumes/SKNVME/ccdash` was in progress during this analysis and the cache was moved out from under it mid-session; the numbers were captured before that and are internally consistent, but should be re-confirmed after the migration settles.
- Node-side figures are from the deployment in its failed state.
- The G-2 root cause is **not** resolved — two candidate explanations remain (see §3/G-2). Everything else in this document is directly evidenced.
- Two items remain explicitly UNVERIFIED and are marked as such in G-4.

**What was not done.** No repository code was modified and no linkage remediation was attempted. The only mutating actions taken anywhere were on the agentic node, to contain and then recover an active disk-exhaustion incident (§3/G-11): pruning dangling/unused podman images, clearing `~/.cache`, and stopping and restarting the ccdash stack. No database was written to — the local cache was opened read-only throughout.
