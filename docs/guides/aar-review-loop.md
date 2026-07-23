---
title: "Automated AAR Review Loop Operator Guide"
description: "Configure and operate the CCDash AAR review loop: read endpoint, capability discovery, autonomous worker flags, and self-recursion guards"
category: guides
tags: [api, aar-review, operator, autonomous-worker, guards, scalability]
updated: 2026-07-23
---

# Automated AAR Review Loop Operator Guide

This guide covers operating the CCDash Automated AAR Review Loop for LAN consumers
(op, IntentTree, ARC). The loop is deterministic, model-free, and emit-only; this document
focuses on configuration, capability discovery, and the autonomous worker's safeguards.

> **Architecture reference**: `CLAUDE.md` § Key Conventions for the core invariants.
> For cross-repo consumer routing logic, see the Consumer Contract at
> `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`.

---

## Overview: Deterministic Triage + Optional Autonomous Worker

The AAR Review Loop consists of two layers:

1. **Deterministic Triage** (always on, read-only): Parses ingested AAR documents,
   correlates them to sessions and features, and emits verdicts based on 5 deterministic
   flags. No LLM involved. Verdicts and evidence are available immediately via the v1
   endpoint and persisted in the `aar_reviews` table.

2. **Autonomous Worker** (enabled by default; worker-profile-gated): A background sweep job
   that periodically reviews AAR candidates across **every registered project** and persists
   verdicts to the `aar_reviews` table under quota-gated escalation limits. It runs only under
   the `worker` runtime profile (the dedicated `ccdash_worker` container in the compose stack),
   never under `api`/`local`/`test`. No model calls. No writeback without an op-approved run
   (that seam is staged but unwired). Set `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED=false`
   to disable.

---

## Capability Discovery

All CCDash servers declare the `aar-review` capability via the standard discovery endpoint:

```bash
GET /api/v1/capabilities
```

**Response:**

```json
{
  "status": "ok",
  "data": {
    "api_version": "1",
    "capabilities": ["aar-review", "sessions:detail", "sessions:cross-project", ...],
    "instance_id": "ccdash-local",
    "server_time": "2026-07-22T12:00:00Z"
  },
  "meta": { ... }
}
```

| Capability | Meaning |
|---|---|
| `aar-review` | The v1 `GET /api/v1/project/aar-review` endpoint is available; consumers can query AAR review verdicts for LAN-ingested documents. |

**Consumer rule**: treat an unknown capability string as a future addition — do NOT error
on strings you don't recognise. Absent `aar-review` means the server predates this feature.

---

## Read Endpoint: Project-Wide AAR Review List

### GET /api/v1/project/aar-review

The primary consumer PULL surface for listing all reviews in a project:

```bash
GET /api/v1/project/aar-review?project_id={project_id}&bypass_cache={bool}
```

**Query Parameters:**

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `project_id` | string | yes | — | The CCDash project identifier. |
| `bypass_cache` | bool | no | false | Skip query cache and fetch fresh data. |

**Response Envelope** (ClientV1Envelope[AARReviewListDTO]):

```json
{
  "status": "ok",
  "data": {
    "project_id": "my-project-uuid",
    "total": 3,
    "reviews": [
      {
        "aar_document_id": "aar-doc-001",
        "aar_document_path": "docs/aars/session-abc-summary.md",
        "correlation": {
          "strategy": "explicit_session_ref",
          "confidence": 0.98,
          "session_ids": ["session-abc"],
          "feature_id": "FEAT-123"
        },
        "triage_verdict": "surface_only",
        "flags": [
          {
            "flag_id": "missing_artifacts",
            "triggered": false,
            "severity": null,
            "evidence": []
          }
        ],
        "evidence_refs": ["session-abc-transcript", "feat-123-doc"],
        "generated_at": "2026-07-22T10:30:00Z"
      }
    ]
  },
  "meta": { ... }
}
```

**Triage Verdicts** (three possible values):

| Verdict | Meaning | Action |
|---|---|---|
| `surface_only` | Deterministic flags all clear; AAR aligns with evidence; no further action needed. | Log and discard. |
| `deep_review_recommended` | One or more flags triggered with low/medium severity; a human or lightweight re-scan is advised. | Queue for manual review or light-touch automation. |
| `human_triage_required` | High-severity flag(s) triggered or correlation confidence too low; requires human decision. | Escalate immediately; do not auto-act. |

**Flags** (5 deterministic flags):

| Flag | Triggered When | Severity |
|---|---|---|
| `missing_artifacts` | AAR-claimed artifacts absent from the session's produced artifacts, and (when a task is linked) from the task's acceptance_criteria/files_affected (set-difference). | high |
| `context_ballooning` | Session context/token growth exceeds the deterministic threshold; enriched with the linked task's declared effort/phase when available. | medium |
| `generic_agent_vs_specialist` | A generic agent handled work an extension/stack lookup maps to a specialist, and/or the session's agents/skill don't match the linked task's assigned_to/assigned_model. | medium |
| `stack_ineffectiveness` | Failure/retry patterns detected for a resolved technology stack; correlated with the linked task's phase/effort. | high |
| `new_skill_or_agent_need` | Per-project aggregation of generic_agent_vs_specialist + missing_artifacts triggers over CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS exceeds CCDASH_AAR_NEW_SKILL_THRESHOLD; includes read-only SkillMeat ranking evidence. | medium |

**No pagination in v1**: The entire `reviews` array is returned. For projects with
many reviews, implement client-side filtering and caching.

### Cache Control

| Flag | Behavior |
|---|---|
| `bypass_cache=false` (default) | Return cached data (server cache ~60s TTL, tunable via `CCDASH_QUERY_CACHE_TTL_SECONDS`). |
| `bypass_cache=true` | Force a fresh deterministic recomputation and skip the cache. Use sparingly. |

---

## Autonomous Worker: Flags and Guards

### Enabling / Disabling the Worker

The autonomous worker is **enabled by default** (`CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED=true`).
To disable it, set:

```bash
export CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED=false
```

The periodic sweep is scheduled **only** under the `worker` runtime profile (the dedicated
`ccdash_worker` container in the compose stack). It is constructed under `worker`/`worker-watch`
but scheduled under `worker` alone, so the `worker-watch` container never double-runs it; the
`api`, `local`, and `test` profiles never construct it. Each tick sweeps **every registered
project** (`AARReviewSweepJob._resolve_projects_to_sweep` → `workspace_registry.list_projects()`),
independent of whichever single project the worker's sync engine is bound to.

### Escalation Quota and Window

Two related flags control how many candidates the worker escalates per time window:

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_AAR_ESCALATION_QUOTA` | 5 | Maximum number of candidates escalated per window. |
| `CCDASH_AAR_ESCALATION_WINDOW_HOURS` | 24 | Rolling time window for the quota (in hours). |

**Interpretation**: With defaults, the worker escalates up to 5 AAR candidates per 24-hour
rolling window. Once the quota is exhausted, no further escalation occurs until the window
advances.

**Example tuning:**

```bash
# Conservative: 2 per day
export CCDASH_AAR_ESCALATION_QUOTA=2
export CCDASH_AAR_ESCALATION_WINDOW_HOURS=24

# Aggressive: 10 per 6 hours
export CCDASH_AAR_ESCALATION_QUOTA=10
export CCDASH_AAR_ESCALATION_WINDOW_HOURS=6
```

### New-Skill and Lookback Thresholds

Two flags gate escalation for newly-observed skills/workflows:

| Variable | Default | Notes |
|---|---|---|
| `CCDASH_AAR_NEW_SKILL_THRESHOLD` | 3 | Minimum observations of a skill before automating its AAR reviews. |
| `CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS` | 30 | Window for counting skill observations (rolling days). |

**Interpretation**: A skill must have been observed at least 3 times in the past 30 days
before the worker will escalate its AAR reviews. This prevents automation on untested workflows.

**Example tuning:**

```bash
# More permissive: allow automation after 1 observation
export CCDASH_AAR_NEW_SKILL_THRESHOLD=1

# More conservative: wait 14 days of data
export CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS=14
```

---

## Self-Recursion Guards (Always On)

Three deterministic safeguards prevent the worker from escalating its own prior output:

### Guard 1: Provenance Self-Exclusion

**What it does**: Excludes any AAR document that was generated by a prior AAR review run.

**How**: The worker inspects the `skill_name` and `workflow_id` fields on the session
that authored the AAR. If both match known AAR review tooling, the candidate is rejected.

**Result**: If rejected, `triage_verdict` stays `surface_only` and escalation does not occur.

**How workspace scoping works**: The Guard-1 session fetch resolves `workspace_id` per project
via `resolve_session_workspace_id(project)` — it prefers a materialized `project.workspace_id`
and otherwise falls back to `DEFAULT_WORKSPACE_ID` (`default-local`). A missing/unfetchable
session row still fails CLOSED (the session is excluded — a self-recursion guard must fail
closed). See "Multi-Workspace Deployments (residual)" below for the one remaining limitation.

### Guard 2: Dedup Ledger

**What it does**: Skips `(aar_document_id, session_id)` pairs that were already triaged — the
same composite primary key as the `aar_reviews` table.

**How**: Each tick seeds an in-memory ledger from the persisted `aar_reviews` rows and skips any
pair already present. The composite PK + `ON CONFLICT DO UPDATE` on `upsert` is the correctness
backstop (idempotent across worker restarts); the in-memory ledger is a within-tick optimization.

**Result**: If a pair is already triaged, it is skipped — no duplicate row, no duplicate work.

**Persistence**: There is **no separate ledger table** — the dedup state *is* the persisted
`aar_reviews` rows, re-read each tick.

### Guard 3: Per-Project Escalation Quota

**What it does**: Caps the total number of candidates escalated per project per time window.

**How**: The worker reads the rolling window from `CCDASH_AAR_ESCALATION_QUOTA` and
`CCDASH_AAR_ESCALATION_WINDOW_HOURS`, counts recent escalations for this project, and
rejects new candidates if the quota is exhausted.

**Result**: If rejected (quota full), the candidate is backlogged and retried on the next run.

**Persistence**: Escalation events are logged with timestamps and persisted for auditing.

---

## Autonomous Worker Behavior

### When the Worker Runs

The worker is a scheduled background job on the `worker`-profile container that runs on a fixed
interval:

- **On schedule**: every `CCDASH_AAR_REVIEW_SWEEP_INTERVAL_SECONDS` seconds (default `1800` = 30
  minutes; floored at 60s). The first tick runs shortly after the worker container starts.
- **Incremental + multi-project**: each tick processes new/changed AAR documents since the last
  per-project watermark, across every registered project.

### What the Worker Emits

The worker emits **read-only observability logs** to stderr and structured logs:

```
[aar-review-worker] escalation event: {
  "timestamp": "2026-07-22T12:00:00Z",
  "project_id": "my-project",
  "aar_document_id": "aar-doc-001",
  "verdict": "human_triage_required",
  "flags_triggered": ["missing_artifacts"],
  "escalation_reason": "high-severity flag",
  "quota_status": {"used": 1, "limit": 5, "window_hours": 24}
}
```

**No writeback**: The worker does NOT call any SkillMeat APIs, does NOT modify agent state,
and does NOT submit jobs to op/ARC. It logs only.

### Integration Gating

To integrate the autonomous worker into op's dispatch loop, op must:

1. Call `GET /api/v1/capabilities` and confirm `aar-review` is present.
2. Poll `GET /api/v1/project/aar-review?project_id=...` periodically.
3. Filter verdicts client-side: `human_triage_required` → human only, `deep_review_recommended` → optional light review.
4. For candidates to escalate, op submits an approved run to its own system; CCDash never initiates.

The worker is on by default; an operator may set `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED=false`
to run PULL-only, human-driven integration instead. Either way the writeback seam stays dormant —
CCDash never initiates an escalation to op/ARC.

---

## Hard Invariants (Non-Negotiable)

**Invariant #1 — No LLM on Compute Path**: The deterministic triage layer makes zero
LLM/model calls. The read endpoint computes verdicts synchronously from cached data.
This is enforced by code review and import audit.

**Invariant #2 — Emit-Only, Op-Gated**: CCDash never pushes decisions, never mutates
external state, and never initiates writeback. op-approved runs are the sole trigger.

**Invariant #3 — Redaction-Passed Data Only**: All session detail and evidence is
scrubbed by the existing redaction layer before the AAR review logic sees it.

**Invariant #4 — No New CorePort**: Triage reuses existing session_detail, feature_forensics,
and artifact_intelligence services; zero new storage or network interfaces.

---

## Troubleshooting

### Worker Not Running

**Symptom**: `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED=true` but no escalation logs.

**Checklist**:
- Confirm the process is the `worker`-profile container (the sweep does NOT schedule under
  `api`, `local`, `test`, or even `worker-watch`).
- Check startup logs for `Started periodic AAR review sweep job (profile=worker interval=…s)`.
- Verify `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` is not set to a falsy value (default true).
- Confirm at least one AAR document exists for some registered project (`GET /api/v1/project/aar-review`).

### No Reviews in Endpoint Response

**Symptom**: `GET /api/v1/project/aar-review` returns `reviews: []` even though AAR docs exist.

**Checklist**:
- Confirm the project_id matches the active project (`GET /api/health/detail`).
- Run the backfill script to manually populate the `aar_reviews` table:
  ```bash
  backend/.venv/bin/python backend/scripts/aar_reviews_backfill.py --project {project_id}
  ```
- After backfill, retry the endpoint with `bypass_cache=true`.

### Escalation Quota Exhausted Quickly

**Symptom**: Worker escalates 5 candidates on first run, then nothing for 24 hours.

**Action**: Adjust quota flags:
  ```bash
  export CCDASH_AAR_ESCALATION_QUOTA=10
  export CCDASH_AAR_ESCALATION_WINDOW_HOURS=6
  ```

### Multi-Workspace Deployments (residual)

The sweep now fans out over **every registered project** and resolves `workspace_id` per project
(`resolve_session_workspace_id`). This is correct for the common **single-workspace, multi-project**
node (all projects on `default-local`) — e.g. the LAN node's `ccdash_worker` container.

**Residual**: the triage service `aar_review.py` still uses the `default-local` workspace for the
session lookups that *produce* the correlated `session_ids`, so a genuinely multi-*workspace* node
(projects on non-default workspaces) is not yet fully supported end-to-end. Guard 1 stays
fail-closed either way, so the worst case is "triages nothing for that project," never a wrong
write. Finish end-to-end multi-workspace support before placing projects on non-default workspaces.

---

## Backfill Script: Populating aar_reviews

To manually populate (or repopulate) the persisted `aar_reviews` table from existing AAR documents:

```bash
backend/.venv/bin/python backend/scripts/aar_reviews_backfill.py \
  --project {project_id} \
  [--since {iso_date}] \
  [--force]
```

**Options:**

| Flag | Meaning |
|---|---|
| `--project {id}` | (required) The project ID to backfill. |
| `--since {iso_date}` | (optional) Only process AAR docs modified after this date. |
| `--force` | (optional) Recompute ALL reviews, overwriting existing rows. |

**Example:**

```bash
# Backfill project 'my-project'
backend/.venv/bin/python backend/scripts/aar_reviews_backfill.py --project my-project

# Force a full recomputation
backend/.venv/bin/python backend/scripts/aar_reviews_backfill.py --project my-project --force

# Process only recent AAR docs
backend/.venv/bin/python backend/scripts/aar_reviews_backfill.py --project my-project --since 2026-07-20T00:00:00Z
```

After backfill, the endpoint will return all triaged reviews.

---

## OpenAPI Specification

A pre-generated OpenAPI v3.1 specification for the `/api/v1` surface (including the
`aar-review` endpoint) lives at:

```
docs/openapi/ccdash-v1.json
```

To regenerate (e.g. after adding a new endpoint):

```bash
backend/.venv/bin/python scripts/regen-openapi-v1.py
```

Commit the updated file alongside your code change.

---

## Quick-Start Checklist for LAN Integration

1. **Deploy CCDash**: Ensure HTTP server is running (`npm run dev:backend` or similar).
2. **Discover capability**: Call `GET /api/v1/capabilities` and confirm `aar-review` is present.
3. **Query reviews** (PULL): Call `GET /api/v1/project/aar-review?project_id=<id>` to fetch verdicts.
4. **Optionally backfill**: Run the backfill script if no reviews appear.
5. **Autonomous worker (on by default)**: The `worker`-profile container sweeps all registered projects on an interval and persists verdicts; tune quota flags as needed, or set `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED=false` to disable.
6. **(Optional) Integrate with op**: Set up op polling + client-side filtering of verdicts; op approves escalations, never CCDash.

---

## Reference

- **Consumer Contract**: `docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`
- **Implementation Plan**: `docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md`
- **External API Guide**: `docs/guides/external-api-lan-deployment.md`
- **CLAUDE.md (Key Conventions)**: See the `aar-review` bullet for hardcoded pointer.
