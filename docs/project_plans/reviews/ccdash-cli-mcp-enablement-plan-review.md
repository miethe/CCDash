---
title: "CCDash CLI/MCP Enablement Plan Review"
description: "Architecture review and assessment of Bob's CLI and MCP enablement proposal for CCDash"
audience: "developers, architects"
tags: ["architecture", "cli", "mcp", "review", "enablement", "agents"]
created: "2026-04-02"
updated: "2026-04-02"
category: "Architecture Review"
status: "published"
related_documents:
  - "docs/project_plans/ccdash-cli-mcp-enablement-plan.md"
---

# CCDash CLI/MCP Enablement Plan Review

## Summary

Bob's plan is a **strong architectural vision document** that demonstrates excellent understanding of the CCDash codebase and proposes a well-reasoned layered architecture. The proposal correctly identifies the core problem (packaging and abstraction gaps) and presents a sound solution with the transport-neutral agent-query layer.

**Overall Score: B+/A- (Strong architecture RFC, but requires PRD and execution planning)**

**Assessment:** This is architecture thinking, not a product specification. It excels at "what should we build" but lacks the artifacts needed to "actually build it" — no user personas, stories, acceptance criteria, effort estimates, or test strategy.

---

## Strengths

### 1. Thorough Codebase Analysis

Bob correctly identifies and references the existing foundations:
- **Hexagonal port system** via `CorePorts` (correctly noted at `backend/application/ports/core.py`)
- **Existing application services** like `ExecutionApplicationService`, `SessionFacetService`, `DocumentQueryService`, and `AnalyticsOverviewService`
- **Rich domain models** already in place (AgentSession, PlanDocument, Project, usage aggregates, etc.)
- **Centralized runtime composition** at `RuntimeContainer`

This analysis goes beyond surface reading. Bob understands the actual abstraction boundaries in the codebase, not just file structure.

### 2. Sound Layered Architecture

The three-layer model is well-reasoned:
- **Domain/repository layer**: System-of-record mechanics (unchanged)
- **Application query layer**: New agent-query service family for composite intelligence
- **Delivery adapters**: REST/CLI/MCP as interchangeable transports

This is the correct abstraction. It keeps transport concerns separate from semantics and allows CLIs and MCP tools to reuse the same business logic without coupling.

### 3. Query-First CLI Philosophy

The principle "commands should answer useful questions instead of mirroring REST endpoints" is sound. Examples like `ccdash status project` and `ccdash feature report` are higher-level than `GET /api/sessions` + `GET /api/features`. This makes CLIs valuable for agents, not just thin wrappers.

### 4. Intent-Oriented MCP Design

Rather than mechanically wrapping every API endpoint as an MCP tool, Bob focuses on high-value questions agents would actually ask:
- Project and portfolio awareness
- Feature intelligence
- Session intelligence
- Workflow diagnostics
- Reporting and retrospectives

This prevents tool proliferation and keeps the MCP surface focused.

### 5. Phased Approach with Clear Validation Gates

The six-phase plan builds confidence progressively:
1. Query layer (foundation)
2. REST composite endpoints (validation)
3. CLI MVP (proof of value)
4. MCP MVP (agent consumption)
5. Operational flows (advanced automation)
6. Web convergence (debt reduction)

Each phase has clear deliverables and allows stopping early if value isn't realized.

### 6. Practical Maintainability Guardrails

The 8 guardrails are well-motivated and address real problems:
- Never call routers from CLI/MCP (correct separation)
- Transport-neutral DTOs (avoid web-only response reuse)
- Separated formatting from data retrieval (maintainability)
- Composite over endpoint mirroring (prevents explosion)
- Standardized filtering/scope (consistency)
- Source references in responses (provenance for agents)
- Deterministic machine output (automation-friendly)
- Graceful degradation when data is stale (robustness)

### 7. Correct Problem Identification

Bob accurately diagnoses the gaps:
- Routers perform presentation logic inline (true in `analytics.py` and `api.py`)
- No single "agent query" abstraction exists
- HTTP endpoints are broad but agent ergonomics aren't optimized
- Some routers still mix direct DB access with service calls

---

## Weaknesses & Gaps

### 1. Not a PRD — Missing Product Definition

This is an architecture RFC, not a product specification. It lacks:

**User Personas:**
- Agent developers (using agents in Claude Code)
- Project operators (managing CCDash locally)
- CI/CD pipelines (automated reporting)
- Unknown: priority weightings, pain points, adoption patterns

**User Stories & Acceptance Criteria:**
- "As an agent, I want to understand project health so that I can make informed planning decisions. Given a project with 5 features, when I query project status, then I receive feature breakdown, recent activity, and anomalies in <500ms."
- "As a CLI user, I want to export feature reports as markdown so that I can share them in PRs. Given a feature ID, when I run `ccdash feature report --md`, then I receive a structured markdown document."

**Success Metrics:**
- What does success look like? (agent accuracy improvement? time savings? adoption rate?)
- How will you measure it? (agent test cases? user surveys? time-tracking?)

**Non-Functional Requirements:**
- Response time SLAs (agent tools need <1s)
- CLI output compatibility (pipe-friendly? structured for jq/grep?)
- MCP tool discovery mechanism (how does Claude Code find the server?)
- Scale bounds (max projects? max sessions to analyze?)

### 2. No SPIKEs for Unknowns

Several decisions have architectural risk but lack exploration:

**MCP Server in Python:**
- How does Python MCP SDK integrate with FastAPI? (separate async context? shared event loop?)
- Are there deployment trade-offs vs. separate MCP binary?
- Which SDK: `mcp-sdk-python`? `pydantic-ai`? Community options?
- What's the transport mode for Claude Code discovery?

**CLI Framework:**
- Why Python (vs. Go binary for distribution)? Reasonable, but should state reasoning.
- Typer vs. Click vs. argparse? No evaluation.
- How is the CLI distributed? (`pip install ccdash`? Bundled binary in CCDash repo? Homebrew?)
- Windows/macOS/Linux compatibility story?

**Composite Query Design:**
- How many queries in MVP? (4 named: project status, feature forensics, workflow diagnostics, AAR. But 6-7 proposed in MCP tools list.)
- What's the algorithm for "problematic features"? (high sessions + high retries + failures + high cost? Need to define.)
- How do you handle missing/incomplete data? (incomplete feature execution context?)

### 3. No ADRs for Key Decisions

Critical decisions are buried in prose and not documented as decisions:

1. **Why a new query-layer service family instead of extending existing application services?**
   - Could you extend `AnalyticsOverviewService` and `SessionFacetService` instead?
   - Trade-off: new service = clean separation vs. existing service = reuse

2. **Why Python CLI over Go/Rust binary?**
   - Python: fast to build, code reuse, test sharing, venv friction
   - Go: distribution as single binary, no interpreter dependency
   - Rust: performance, binary size
   - Decision needs justification.

3. **MCP Transport & Discovery:**
   - How does Claude Code discover the CCDash MCP server? (stdio? HTTP? SSE?)
   - Is it a child process of the CCDash worker, or separate binary?
   - Impact on deployment and configuration.

### 4. Missing Effort Estimates

Six phases with no sizing makes planning impossible:

- How many engineer-weeks for Phase 1 (query layer)? 2-3? 5-6?
- Which phase is the critical path? (likely Phase 1 + Phase 2)
- Phase 6 ("Web convergence") sounds like debt reduction, not enablement. Is it required, or nice-to-have?
- Are phases sequential (1→2→3) or can some run in parallel (2 starts while 1 wraps)?

**Impact:** You can't schedule this without estimates. You can't tell if it's a 6-week sprint or a 6-month project.

### 5. No Testing Strategy

How do you validate:
- **CLI output formatting?** (golden files? snapshot tests?)
- **MCP tool contracts?** (do you test against real Claude Code, or mock MCP clients?)
- **Query service logic?** (unit tests on services, or integration tests end-to-end?)
- **Cross-transport consistency?** (same query via REST + CLI + MCP produces equivalent results?)
- **Freshness guarantees?** (if cache is stale, are all outputs consistent in reporting that?)

**Concern:** Without a test strategy, Phase 2 (REST validation) might not catch issues that surface in Phase 3 (CLI) or Phase 4 (MCP).

### 6. Deployment & Packaging Gaps

**CLI Distribution:**
- How users install it? (`pip install ccdash`? Adds a `ccdash` command to their PATH?)
- Does it need to be in the same virtualenv as the backend, or separate?
- Version coupling: if CCDash backend is v1.2, can CLI be different?

**MCP Server Discovery:**
- How does Claude Code find the MCP server? Config file? Environment variable? Auto-discovery?
- If it's in `.claude/mcp.json` or similar, what's the schema?
- Who manages the MCP server lifecycle? (CCDash worker? Separate process?)
- Security: how do you authenticate CLI/MCP to the backend? (already authenticated in local mode, but worth stating)

**Observability:**
- How do you debug CLI failures? Log files? Verbose mode?
- MCP debugging: how do you see tool call traces?

### 7. File Reference Verification Needed

Several line/file references should be verified against current code:
- `backend/models.py:154` for `AgentSession` — is that still current?
- `backend/models.py:409` for `SessionUsageAggregateResponse` — check if line numbers have shifted.
- References to `backend/routers/api.py` at line 496, 703, etc. — may have moved.

While the structure analysis is sound, specific line numbers can drift. Consider validating before implementation.

### 8. Over-Engineering Risk: Four-Layer Stack

The proposal sketches:
```
CLI/MCP/REST
    ↓
CCDashAgentAccessService (optional facade)
    ↓
Agent query services
    ↓
Repositories/existing services
```

That's 4 layers. Justification needed:
- Why not extend existing services directly? (e.g., add composite queries to `AnalyticsOverviewService`?)
- The facade `CCDashAgentAccessService` bundles "project summary, feature review, feature AAR pack, workflow diagnostics, session diagnostics, readiness snapshot" — is that a real pattern or just convenience?

**Recommendation:** Start with 3 layers (query services + delivery adapters + repos). Add the facade only if you see repeated composition patterns.

### 9. No Priority Framework

Which MCP tools deliver the most value to agents?

The proposal lists ~20 MCP tools but no ranking:
```
ccdash_project_list
ccdash_project_status
ccdash_project_paths
ccdash_portfolio_hotspots
...
```

**Recommendations:**
- Rank by agent use case frequency (planning > retrospectives > debugging)
- Consider availability: "problematic-features heuristics" (line 519-527) require research/validation
- Phase 4 MVP mentions 4 tools, but the earlier list has 20+ — which 4? Why those?

---

## Recommendations

### 1. Write a Proper PRD

Create a document with:
- **Personas:** agent developers, CLI operators, CI pipelines (with pain points)
- **User stories:** 5-10 stories per persona with acceptance criteria
- **Success metrics:** agent accuracy, time savings, adoption rate, feature completion time
- **Non-functional requirements:** response latency, output format compatibility, discovery mechanism
- **Out of scope:** what won't be in MVP

**Effort:** 1-2 days. **Value:** clarifies "why" before "how."

### 2. Run SPIKEs on Unknowns

1. **MCP Integration SPIKE (1 engineer, 2-3 days)**
   - Evaluate Python MCP SDK options
   - Prototype MCP server in FastAPI
   - Test discovery/connection with mock Claude Code client
   - Document transport choice and integration pattern

2. **CLI Framework Evaluation SPIKE (1 engineer, 1 day)**
   - Compare typer vs. click vs. argparse on: ergonomics, testing, doc generation
   - Prototype one command (e.g., `ccdash status project`) in each
   - Decide on distribution model (pip install? Homebrew? bundled binary?)

3. **Composite Query Design SPIKE (1 engineer, 1-2 days)**
   - Define exact algorithm for "problematic features" query
   - Prototype `ProjectStatusQuery` service
   - Validate it answers common agent questions
   - Ensure it's extensible for Phases 3-5

### 3. Create ADRs for Three Key Decisions

**ADR 1: Query Layer Architecture**
- Context: New agent queries vs. extending existing services
- Decision: Create new `agent_queries/` service family
- Rationale: Clean separation, avoid over-generalizing existing services
- Consequences: 4 layers instead of 3, mild duplication risk, clear seams

**ADR 2: CLI Framework & Distribution**
- Context: Python CLI in CCDash repo vs. Go binary vs. distribution method
- Decision: Python CLI, distributed via `pip install ccdash` from PyPI
- Rationale: Code reuse, test sharing, fast dev iteration
- Consequences: requires venv management, no single-file binary

**ADR 3: MCP Transport & Lifecycle**
- Context: How Claude Code discovers and communicates with MCP server
- Decision: [Choose based on SPIKE] Likely stdio-based transport, MCP server runs as child of worker
- Rationale: [Document trade-offs]
- Consequences: [e.g., shared event loop, discovery via config file]

### 4. Add Effort Estimates

Break each phase into tasks with sizing:

```
Phase 1: Agent Query Foundation
├─ Create agent_queries service family    [2-3 weeks]
├─ Project status query service          [1 week]
├─ Feature forensics query service       [1.5 weeks]
├─ Workflow diagnostics query service    [1 week]
├─ Shared filtering/scope utilities      [0.5 week]
├─ Unit tests for query services         [1 week]
└─ Total: ~7-8 weeks

Phase 2: REST Composite Endpoints
├─ Four agent routes (/api/agent/...)    [1 week]
├─ Integration tests                     [0.5 week]
└─ Total: ~1.5 weeks

Phase 3: CLI MVP
├─ CLI framework & main.py               [0.5 week]
├─ 6 MVP commands                        [2 weeks]
├─ Formatters (table/json/md)           [1 week]
├─ CLI tests                            [1 week]
└─ Total: ~4.5 weeks

Phase 4: MCP MVP
├─ MCP server bootstrap                  [1 week]
├─ 4 MCP tools                          [2 weeks]
├─ Tool tests/validation                [1 week]
└─ Total: ~4 weeks

Phase 5-6: [Estimated at ~6 weeks total]
```

**Critical path:** Phases 1-2-3 sequential (~13 weeks). Phase 4 can start when Phase 2 is stable.

### 5. Define MVP Scope Tightly

Current MVP (lines 689-711) includes:
- 4 query services
- 4 REST endpoints
- 4 CLI commands
- 4 MCP tools

**Recommendation:** Narrow further. Start with **1 query service** (project status) and validate across all three transports (REST + CLI + MCP) before adding more.

**Tighter MVP:**
- `ProjectStatusQuery` service
- `GET /api/agent/project-status`
- `ccdash status project --json`
- `ccdash_project_status` (MCP tool)
- Tests proving all three surfaces work and are consistent

**Effort:** ~4-5 weeks. **Value:** Proof of architecture, unblocks all subsequent queries.

### 6. Define Testing Strategy

1. **Unit tests:** Query services tested in isolation (mocked repos)
2. **Integration tests:** Query services with real DB (SQLite test fixture)
3. **Transport tests:** REST/CLI/MCP all call same query service; validate output consistency
4. **Formatting tests:** CLI/MCP output matches schemas (snapshot tests or JSON schema validation)
5. **Contract tests:** MCP tool schemas match spec (if using Claude Code SDK)

Document in a separate Testing Strategy document linked from PRD.

### 7. Clarify Over-Engineering Questions

In the detailed design phase, address:
- **Facade layer:** Is `CCDashAgentAccessService` really needed, or should clients compose queries directly? (Defer decision until Phase 2.)
- **Existing service extension:** Could the new query logic extend `AnalyticsOverviewService` instead? (Evaluate in SPIKE 3.)
- **Caching:** Should query results be cached? For how long? (Defer until Phase 3 if performance issues arise.)

### 8. Prioritize MCP Tools Explicitly

Create a ranked list:

```
Must-Have (MVP):
- ccdash_project_status        [agent planning, triage]
- ccdash_feature_forensics     [feature investigation]
- ccdash_workflow_failures     [debugging]
- ccdash_generate_aar          [retrospectives]

Should-Have (Phase 5):
- ccdash_portfolio_hotspots    [portfolio review]
- ccdash_cache_status          [freshness validation]

Nice-to-Have (future):
- ccdash_session_summary       [detailed replay]
- ccdash_workflow_leaderboard  [performance comparisons]
```

Rank by: agent use frequency, agent pain point, implementation complexity.

---

## What's Missing from Plan → Implementation

To move from this architecture proposal to actual work:

| Artifact | Current Status | Owner | Effort | Depends On |
|----------|---|---|---|---|
| PRD with personas/stories | Missing | Product/Bob | 2 days | — |
| MCP/CLI Framework SPIKEs | Missing | Engineering | 3-5 days | PRD |
| ADRs (3 key decisions) | Missing | Bob | 2 days | SPIKEs |
| Detailed task breakdown | Partial (phases exist) | Bob | 2 days | SPIKEs, ADRs |
| Effort estimates by task | Missing | Engineering | 1 day | Task breakdown |
| Testing strategy doc | Missing | QA/Engineering | 1 day | Task breakdown |
| Deployment/packaging spec | Missing | DevOps/Bob | 1 day | CLI SPIKE |
| MCP server discovery spec | Missing | Bob | 0.5 day | MCP SPIKE |

**Total planning work:** ~2 weeks. **Then:** ~15-18 weeks of implementation (phases 1-4).

---

## Questions for Bob

Before greenlight:

1. **Query layer extensibility:** Can you extend existing services instead of creating parallel hierarchy? What's the trade-off analysis?
2. **MCP in Python:** Have you evaluated MCP SDK options? What's the deployment model for the MCP server?
3. **CLI distribution:** Will this be on PyPI as a separate package, or a built-in command of CCDash?
4. **Facade layer:** Is `CCDashAgentAccessService` necessary at Phase 1, or is it premature abstraction?
5. **Tight MVP:** Can Phase 4 actually ship with just 4 tools, or does agent value require more?
6. **Data freshness:** How do you ensure agents aren't acting on stale data? (freshness timestamps? explicit sync before queries?)

---

## Score & Recommendation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Codebase Understanding | A | Deep knowledge of architecture, services, and structure |
| Architecture Soundness | A- | Layered design is correct; slight over-engineering risk in facade layer |
| Completeness | B- | Strong on "what," weak on "how" and "who/when" |
| Actionability | C+ | Phases are clear, but missing tasks, estimates, and research |
| Risk Mitigation | B | Good guardrails, but unknowns (MCP, CLI, deployment) need SPIKEs |

**Overall Grade: B+/A-**

**Recommendation: APPROVE WITH CONDITIONS**

Proceed with:
1. ✅ Use this as the architecture north-star
2. ✅ Start Phase 1 design after SPIKEs complete
3. ⚠️ Create a proper PRD before team commitment
4. ⚠️ Run SPIKEs (MCP, CLI, composite query) before Phase 1 kickoff
5. ⚠️ Add effort estimates and dependency graph before scheduling

This is strong architectural thinking. With a PRD, SPIKEs, and tighter scoping, it becomes a solid implementation roadmap.

---

## Next Steps

1. **This week:** Bob creates PRD with personas and user stories
2. **Next week:** Engineering runs SPIKEs (MCP + CLI + query design)
3. **Following week:** Bob writes ADRs and detailed task breakdown
4. **Planning:** Schedule Phase 1 kickoff with effort-estimated tasks

---

## Document History

- **2026-04-02:** Initial review by Architecture team
