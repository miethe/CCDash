---
created: 2026-05-06
feature: planning-forensics-boundary-extraction-v1
decision: mcp-cli-transport-scope-for-feature-evidence-summary
status: decided
---

# MCP/CLI Transport Scope Decision — FeatureEvidenceSummary

## Context

We are adding a new `FeatureEvidenceSummary` service: a bounded summary of
session/token/workflow evidence for a feature, explicitly scoped away from the
full forensic transcript data that `FeatureForensicsQueryService` returns. The
REST route (`/api/agent/feature-evidence-summary/{feature_id}`) is in scope for
this refactor. The question is whether MCP and CLI transports should be wired in
the same change set or deferred.

---

## Current State of Each Transport

### Agent Query Services (`backend/application/services/agent_queries/`)

Six service classes exist, all transport-neutral:

| Service | Module |
|---|---|
| `ProjectStatusQueryService` | `project_status.py` |
| `FeatureForensicsQueryService` | `feature_forensics.py` |
| `WorkflowDiagnosticsQueryService` | `workflow_intelligence.py` |
| `ReportingQueryService` | `reporting.py` |
| `PlanningQueryService` | `planning.py` |
| `PlanningSessionQueryService` | `planning_sessions.py` |

`FeatureEvidenceSummaryQueryService` does not yet exist; it is the deliverable
of this refactor.

### REST — `backend/routers/agent.py`

Exposes all six services:

- `GET /api/agent/project-status`
- `GET /api/agent/feature-forensics/{feature_id}`
- `GET /api/agent/workflow-diagnostics`
- `POST /api/agent/reports/aar`
- `GET /api/agent/planning/summary`, `/graph`, `/features/{id}`, `/features/{id}/phases/{n}`
- `GET /api/agent/planning/session-board` (+ `/{feature_id}`)
- `GET|POST /api/agent/planning/next-run-preview/{feature_id}`

The planning group (six endpoints) was added together as a deliberate batch and
never back-ported to MCP or CLI, establishing the current precedent that REST
leads, transports follow asynchronously.

### MCP — `backend/mcp/tools/`

Exposes **four** tools, one per non-planning service:

| Tool | Service |
|---|---|
| `ccdash_project_status` | `ProjectStatusQueryService` |
| `ccdash_feature_forensics` | `FeatureForensicsQueryService` |
| `ccdash_workflow_failure_patterns` | `WorkflowDiagnosticsQueryService` |
| `ccdash_generate_aar` | `ReportingQueryService` |

The entire planning group (`PlanningQueryService`, `PlanningSessionQueryService`,
next-run preview) is **absent** from MCP. MCP covers exactly the four
pre-planning services and nothing added since.

### CLI — `backend/cli/commands/`

Mirrors MCP with the same four services mapped to commands:

| Command | Service |
|---|---|
| `ccdash status project` | `ProjectStatusQueryService` |
| `ccdash feature report <id>` | `FeatureForensicsQueryService` |
| `ccdash workflow failures` | `WorkflowDiagnosticsQueryService` |
| `ccdash report aar --feature <id>` | `ReportingQueryService` |

Planning services are likewise absent. The four commands are a strict subset of
what REST exposes.

---

## Decision

**Defer MCP and CLI wiring for `FeatureEvidenceSummary` to a follow-up.**

### Rationale

1. **Established precedent: transports trail REST.** The entire planning group
   (six REST endpoints) was never wired into MCP or CLI. This refactor is not
   responsible for closing that gap; it should not introduce a different rule
   for `FeatureEvidenceSummary`.

2. **Symmetry within this refactor.** The MCP and CLI surfaces are currently
   symmetrical with each other (both cover the same four services). Wiring
   `FeatureEvidenceSummary` into only one of them during this change would break
   that symmetry without a clear consumer forcing it. Wiring both together is
   tidier but adds scope with no current downstream consumer.

3. **No near-term consumer via MCP/CLI.** The primary consumer driving this
   refactor is the frontend planning surface, which reads from REST. The
   standalone CLI (`packages/ccdash_cli/`) talks to the server over HTTP and
   therefore will automatically benefit from the REST route without a CLI
   transport change. There is no identified agent workflow or MCP client that
   requires the new summary surface in this cycle.

4. **Wiring cost is minimal but not zero.** Adding a new MCP tool follows a
   ~15-line pattern (see `backend/mcp/tools/features.py`). Adding a CLI command
   is similarly mechanical. However, each addition requires a formatter path,
   error-handling branch, and test coverage. These are low-risk changes that
   belong in a focused transport-parity pass, not appended to a forensics
   boundary refactor.

5. **Risk isolation.** Keeping this change set narrowly scoped to service +
   REST reduces the blast radius if the `FeatureEvidenceSummary` DTO shape needs
   revision after initial REST validation.

---

## Scope Boundary

| Transport | In scope for this refactor |
|---|---|
| REST (`backend/routers/agent.py`) | Yes — `GET /api/agent/feature-evidence-summary/{feature_id}` |
| MCP (`backend/mcp/tools/`) | No — deferred |
| CLI (`backend/cli/commands/`) | No — deferred |

The existing P1-003 task covers REST wiring only. No changes to
`backend/mcp/tools/__init__.py` or `backend/cli/commands/` are expected from
this refactor.

---

## Follow-up Action

A transport-parity issue should be filed after this refactor ships, covering:

- `ccdash_feature_evidence_summary` MCP tool in `backend/mcp/tools/features.py`
- `ccdash feature evidence <id>` CLI command in `backend/cli/commands/feature.py`
- Corresponding formatter and error-handling branches (consistent with existing
  `feature report` command pattern)
- Test coverage for both transports

This parity work can be batched with any eventual MCP/CLI exposure of the
planning group surfaces, since the transport plumbing is identical.
