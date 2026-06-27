---
schema_version: 2
doc_type: report
report_category: investigations
title: "CCDash Enterprise Edition Planning Bundle — Index"
status: draft
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# CCDash Enterprise Edition Planning Bundle — Index

This bundle is the planning/analysis output of a **12-domain forensic investigation** (2026-05-30) into making
CCDash's **enterprise/containerized edition** production-usable, performant, and multi-project-scalable.
**Container + Postgres is the primary target; local mode is a dev mode.** The investigation answers two headline
questions — *why does the containerized build pull no live data?* and *why is it slow at `skillmeat` scale (a
9.5 GB DB)?* — and converts the answers into a Phase 0–6 roadmap and a 118-task backlog. No application code was
modified; this is a planning phase.

## Manifest

| Doc | Path | What it answers |
|-----|------|-----------------|
| **00 — Executive Summary** | [00-executive-summary.md](00-executive-summary.md) | The entry point: top-5 findings (container live-data failure + 10 GB DB anatomy), root causes, top gaps, target arch, Phase 0, open decisions |
| **01 — Current-State Architecture** | [01-current-state-architecture.md](01-current-state-architecture.md) | What exists *now* — FE/BE/DB/workers/ingestion/cache/multi-project/container baseline with file:line evidence (no recommendations) |
| **02 — Performance Forensics** | [02-performance-forensics.md](02-performance-forensics.md) | Why it is slow — 10 GB DB anatomy, N+1 query catalog with counts, cache cost/correctness, FE fetch storms, quick wins vs deep refactors |
| **03 — Enterprise Edition Gap Analysis** | [03-enterprise-edition-gap-analysis.md](03-enterprise-edition-gap-analysis.md) | What works / what is broken / what is missing; the compounding container-failure chain; gap tables by area |
| **04 — Planning Command Center UX & Data Spec** | [04-planning-command-center-ux-data-spec.md](04-planning-command-center-ux-data-spec.md) | Multi-project control-plane IA, modal + deep-link drill-down, new/changed endpoints, data availability matrix, component plan |
| **05 — Target Architecture Proposal** | [05-target-architecture-proposal.md](05-target-architecture-proposal.md) | Enterprise-primary target topology and the backend/DB/worker/cache/FE/container target design with tradeoffs |
| **06 — Implementation Roadmap** | [06-implementation-roadmap.md](06-implementation-roadmap.md) | Phase 0–6: goal, scope, key changes, dependencies, risks, measurable validation, acceptance, rollback, effort per phase |
| **07 — Issue & Task Backlog** | [07-issue-task-backlog.md](07-issue-task-backlog.md) | 130 issues → 118 executable tasks; Top 12 P0 quick-start; phase×area counts; critical-issue coverage check |

## Recommended reading order

1. **00 — Executive Summary** — start here; it frames everything and links out.
2. **01 — Current-State Architecture** — the runtime-truth baseline; read before any proposal.
3. **02 — Performance Forensics** — the measured "why it is slow" diagnosis.
4. **03 — Gap Analysis** — what is missing/broken for enterprise.
5. **05 — Target Architecture** — the proposed end state (read 04 alongside if working on the command center).
6. **06 — Roadmap** then **07 — Backlog** — to plan and execute (07's Top 12 P0 is the quick-start).
7. **04 — Command Center UX & Data Spec** — for Phase 4–5 frontend/command-center work specifically.

**Critical path for execution:** 00 → 06 (Phase 0) → 07 (Top 12 P0). Phase 0 (Enterprise Liveness Hotfix)
unblocks all enterprise use and is mostly default flips + path-alias derivation + a fail-loud `readyz` + a CI
`docker compose up` e2e smoke gate.

## Evidence base (worknotes)

The detail docs above are grounded in the forensic worknotes — consult these for raw evidence:

- **Steering / decisions:** `.claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md` — authoritative
  root-cause framing, Phase 0–6 boundaries, target-architecture decisions, and open human decisions (§8).
- **Issue ledger:** `.claude/worknotes/ccdash-enterprise-edition-v1/issue-ledger.md` — 130 issues with
  severity / complexity / area.
- **Completed & gaps:** `.claude/worknotes/ccdash-enterprise-edition-v1/completed-and-gaps.md` — what is already
  shipped vs missing, per domain.
- **Per-domain findings:** `.claude/worknotes/ccdash-enterprise-edition-v1/investigation/*.md` — detailed
  file:line evidence per domain (container-deploy, ingestion-fs, database, caching, backend-api, frontend-core,
  planning-frontend, workers-runtime, multi-project, perf-evidence, data-contracts, completed-work).

> **Note for agents:** the code is the contract — plans drift. Verify behavior from runtime truth
> (`backend/application/services/agent_queries/`, `backend/routers/`, `types.ts`) before relying on any
> historical plan. Confidence ratings and open decisions are tracked in the synthesis brief §8–9.
