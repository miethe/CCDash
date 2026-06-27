---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash Runtime & Deploy Remediation — Live-Stack Investigation"
status: accepted
source: agent
created: 2026-06-12
updated: 2026-06-12
feature_slug: ccdash-runtime-deploy-remediation
related_documents:
  - .claude/findings/ccdash-core-remediation-findings.md
  - docs/guides/containerized-deployment-quickstart.md
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
prd_ref: null
---

# CCDash Runtime & Deploy Remediation — Live-Stack Investigation

**Method**: Live diagnosis against a fully-healthy enterprise+postgres+live-watch container stack (api :8843, frontend :3843, postgres :5843, worker :9465, worker-watch :9466) on 2026-06-12, immediately after aligning the watcher to the DB-active project. All evidence is from running containers, the Postgres cache DB, and the live API — not from code reading.

## TL;DR

The operator reported "still not seeing any data flowing for sessions" and hypothesized missing volume mounts. **That hypothesis is disproven.** Data ingests correctly and the API serves it. The "no data" symptom is a **registry-authority leak in the read/selection path**: the UI lands on an empty seed/example project instead of the DB-active project. This shares a root theme with the watcher's env-pinned project binding — **the running app does not consistently treat the DB registry as the source of truth (ADR-006)**.

## Confirmed Findings

### I-1 — Volume-mount hypothesis DISPROVEN; ingest is live and correct

Worker-watch mounts are present and correct: `/Users/miethe/.claude → /home/ccdash/.claude (ro)`, `/Users/miethe/dev/homelab/development → same (ro)`, codex home, projects.json. The active project's data in Postgres:

| Table | Rows (project `3df0ff70`) | Freshness |
|-------|---------------------------|-----------|
| `sessions` | 1,167 | `max(updated_at)` ≈ 30s before `now()` — **live** |
| `session_messages` (transcript) | 64,504 | populated |
| `documents` | 2,614 | populated |
| `tasks` | 7,320 | populated |
| `features` | 297 | populated |

The session-list, session-detail, and transcript endpoints all return real data (transcript body verified: actual user-message content). Conclusion: **ingest, storage, and the API read path are all healthy.** The watcher alignment performed earlier this session works.

> Note: `session_logs` = 0 rows is **not** a fault — `session_messages` is the transcript table; `session_logs` is legacy/unused. This briefly looked like a smoking gun and was ruled out.

### I-2 — ROOT CAUSE of "no data": registry-authority leak in project selection

`GET /api/projects` (the app-shell's project source) returns the DB registry list with **seed/example/test projects first** and does **not** prioritize the DB-authoritative `is_active` flag:

```
/api/projects[0] = default-skillmeat  "SkillMeat Example"  path .../examples/skillmeat   (is_active=f, EMPTY)
/api/projects[1] = test-project-1     "Test Project 1"     path /tmp/test-project-1       (is_active=f, EMPTY)
...
registry is_active=true → 3df0ff70 "SkillMeat" (1,167 sessions)   ← the one with data
```

The UI lands on an empty example project (`default-skillmeat` / `examples/skillmeat`), so it appears "no sessions are flowing." Selecting **SkillMeat (`3df0ff70`)** in the switcher immediately shows data — confirming the data is present and the defect is in **default-project resolution**, split across:
- **Backend**: `/api/projects` ordering/selection does not surface the `is_active=true` row authoritatively (does not put it first or flag it for the client).
- **Frontend**: app-shell default-project selection does not honor `is_active` on first load; falls to list order (or a stale stored id).

This is an **ADR-006 violation in the runtime read path**: the DB registry is authoritative for *who is active*, but the running app ignores that on load. Seed/example/test projects (imported from `projects.json`) further pollute the candidate list.

### I-3 — Watcher binds exactly one hardcoded project id per process (= F-DEPLOY-003)

`worker-watch` resolves its target solely from `CCDASH_WORKER_WATCH_PROJECT_ID` in a gitignored env overlay. It ignores the DB registry. Consequences: (1) the watched project must be hand-copied into an env file and kept in sync with the DB-active project — a silent "health-green / UI-empty" drift (exactly the mismatch corrected this session); (2) watching N projects requires N hand-run watcher services with N probe ports. Operator critique, verbatim: *"I don't like needing to set that in a config file. It should really just work based on what's configured in app. Otherwise, what's the point of multiple watchers and projects?"* Same root theme as I-2.

### I-4 — Postgres in-place upgrade path is broken below SCHEMA_VERSION 35 (= F-DEPLOY-002)

`backend/db/postgres_migrations.py:_run_migrations_inner` runs the full `_TABLES` DDL batch **before** the versioned 29→35 ALTERs. `_TABLES` embeds `project_id`-dependent objects (`CREATE INDEX … ON sessions(project_id, status, updated_at)`, composite `PRIMARY KEY (project_id, id)`). On a pre-existing DB below v35 the `sessions` table already exists, so `CREATE TABLE IF NOT EXISTS` no-ops, but the standalone `CREATE INDEX` runs against the old table lacking `project_id` → `UndefinedColumnError`, and the column-adding ALTERs never run. **Only freshly-created PG DBs migrate; in-place upgrades fail.** Worked around this session by wiping the derived-cache volume.

### I-5 — Compose build-target omission (= F-DEPLOY-001, RESOLVED)

The `x-backend-build` anchor set no `target`, so every service built the Dockerfile's last stage (`worker`); the `api` container crashed at boot. Fixed in commit `f5f80ae` by pinning per-service `build.target`. Documented here for completeness; not part of forward remediation scope.

## Unifying Thesis

I-2 and I-3 are the same defect class: **the runtime does not treat the DB registry as authoritative.** Project selection ignores `is_active`; the watcher ignores the registry entirely. The remediation's spine is *"registry-authoritative runtime"* — selection and watch fan-out both derived from the DB registry (ADR-006), env vars demoted to optional scoping overrides. I-4 is independent deploy-stack hardening folded into the same epic.

## Recommended Workstreams (feeds PRD)

| WS | Title | Findings | Owner surfaces | Risk |
|----|-------|----------|----------------|------|
| W1 | Registry-authoritative project resolution (fixes "no data") | I-2 | `/api/projects` (backend) + app-shell default selection (frontend) | Med |
| W2 | Registry-driven watcher fan-out | I-3 | worker/worker-watch runtime, registry read, per-project probe/health rollup | High (arch) |
| W3 | Postgres in-place upgrade-path fix + seeded-old-volume smoke | I-4 | `postgres_migrations.py` ordering; `docker:*:smoke` | High (migrations) |
| W4 | Finding triage & cleanup | F-W3-001/002, F-001/002/003, F-W6-001 | docs, test fixtures, tooling | Low |

## Evidence Appendix (commands)

- Mounts: `docker inspect ccdash-worker-watch-1 --format '{{range .Mounts}}…'`
- Row counts: `psql -c "SELECT project_id,count(*) FROM sessions GROUP BY project_id"`; same for `session_messages`, `documents`, `tasks`, `features`
- Freshness: `psql -c "SELECT max(updated_at),now() FROM sessions WHERE project_id='3df0ff70…'"`
- Active flag: `psql -c "SELECT id,name,is_active FROM projects ORDER BY is_active DESC"`
- Read path: `curl :8843/api/v1/sessions?project_id=3df0ff70… ` (data), `/detail` (data), `/transcript` (transcript body)
- Selection bug: `curl :3843/api/projects` → `default-skillmeat` first; frontend proxy returns 200 with data when given the active id
