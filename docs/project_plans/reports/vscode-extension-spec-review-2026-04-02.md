---
title: "VSCode Extension Technical Spec Review"
type: "review"
status: "complete"
created: "2026-04-02"
reviewed_document: "docs/project_plans/vscode-bob-extension-technical-specification.md"
reviewer: "Senior Architecture Review"
overall_grade: "C+ / Needs Significant Revision"
tags: ["vscode", "extension", "review", "architecture"]
---

# VSCode Extension Technical Spec Review

## Executive Summary

Bob produced a broad feature outline with good surface area coverage, but the document contains **multiple factual errors about CCDash's actual API**, critical architectural omissions, and miscategorization. It reads as a feature roadmap/outline, not a technical specification. The spec requires substantial revision before implementation can begin.

**Grade: C+ — Commendable scope, critical factual errors, significant omissions, wrong format.**

---

## Critical Errors (Must Fix Before Implementation)

### 1. Project-Switch API is Wrong
- **Spec claims**: `POST /api/projects/switch`
- **Actual endpoint**: `POST /api/projects/active/{project_id}`
- **Impact**: Day-one blocker. Code won't compile.

### 2. WebSocket Does Not Exist
- **Spec claim**: Extension uses WebSocket for real-time updates
- **Reality**: CCDash uses **SSE only** (`GET /api/live/stream` with topic-based subscriptions)
- **Impact**: All WebSocket integration code (lines 783-791, MCP server architecture) is based on fiction
- **Fix**: Replace WebSocket with SSE client; retool live update strategy

### 3. Analytics Endpoints Are Wrong
- **Spec claims**: `/api/analytics/sessions`, `/api/analytics/tokens`, `/api/analytics/tools`
- **Actual endpoints**: `/api/analytics/metrics`, `/api/analytics/overview`, `/api/analytics/series`, `/api/analytics/breakdown`, `/api/analytics/correlation`, `/api/analytics/workflow-registry`, `/api/analytics/failure-patterns`, etc.
- **Impact**: Feature 2 (analytics dashboards) cannot be implemented without correct endpoint knowledge

### 4. "Bob" Naming Throughout
- **Issue**: AI tool is "Claude Code," not "Bob"
- **Fictional**: `.bob/modes/` directory doesn't exist; Claude Code uses `.claude/commands/` and MCP servers via a separate process
- **Impact**: Confuses readers, shows misunderstanding of Claude Code architecture
- **Fix**: Replace all "Bob" with "Claude Code"; clarify MCP as a separate process, not extension-internal

### 5. Terminal Execution Design Is Broken
- **Spec approach**: `terminal.sendText()` (line 535) with `monitorExecution` pattern
- **Problem**: VSCode's `terminal.sendText()` is **fire-and-forget**. Cannot capture stdout/stderr. No way to know if command succeeded.
- **Impact**: Phase 3 execution features won't work as designed
- **Fix**: Use `child_process` module (spawn/exec) or propose backend execution API

### 6. CORS Blocker: Webview Origin
- **Spec assumption**: Webview makes requests from localhost
- **Reality**: VSCode webviews use `vscode-webview://` origin, **not** `localhost`
- **Problem**: CCDash backend CORS whitelist (if present) won't include this origin
- **Impact**: All webview API calls fail on day one
- **Fix**: Add CORS mitigation strategy (proxy via extension host, or backend whitelist webview origin)

---

## Significant Omissions

1. **No CCDash-Not-Running UX**: What happens if backend is offline? Graceful degradation? Auto-detect? Retry logic? None specified.

2. **No Multi-Workspace/Multi-Root Handling**: VSCode allows multiple folders. How does project detection work across workspaces?

3. **No API Versioning or Compatibility Contract**: What happens when CCDash backend API changes? No versioning strategy.

4. **No Activation Events**: When does the extension activate? If on `*` (all workspaces), it will slow down every VSCode instance. Should be scoped (e.g., `onWorkspaceContains:.claude/commands`).

5. **No Content Security Policy (CSP) for Webviews**: Chart.js, React require inline scripts/styles. CSP must be configured. Not mentioned.

6. **No "Reuse Frontend Components" Strategy**: Phase 2 claims "reuse React components from CCDash frontend." Webviews have different build context, CSP, can't use `@/` path aliases or React context providers. This is unrealistic without significant refactoring.

7. **Backend Dependencies Not Documented**: Phase 2/3 require new endpoints that don't exist:
   - `/api/files/context` (code context around a session action)
   - `/api/search` (global search)
   - `/api/features/{id}/workflow-guidance` (actionable AI guidance)

---

## API Verification Summary

| Category | Status | Notes |
|----------|--------|-------|
| Core CRUD (sessions, documents, features) | ✅ Mostly correct | Parameter names differ: use `session_id` not `id` |
| Analytics endpoints | ❌ **Wrong** | Completely different structure; no `/sessions`, `/tokens`, `/tools` |
| Project switch | ❌ **Wrong** | Route is `POST /api/projects/active/{project_id}` |
| WebSocket/SSE | ❌ **Wrong** | WebSocket doesn't exist; SSE only at `GET /api/live/stream` |
| Search endpoint | ✅ Correctly marked "proposed" | Not yet implemented |
| File context endpoint | ✅ Correctly marked "proposed" | Not yet implemented |
| Session transcript | ⚠️ No dedicated endpoint | Data included in session detail response |
| Authentication | ✅ Correct | None required (local backend) |

---

## Architecture Concerns

1. **MCP Server Cannot Live Inside Extension Host**: MCP server is a separate process. If Phase 3 commits to "MCP server + extension host communication," clarify how the MCP server is launched, managed, and disposed.

2. **Unbounded State Management**: `Map<string, AgentSession>` (line 710) has no size limit or eviction policy. With thousands of sessions, this will leak memory.

3. **Overly Broad API Error Retries**: Client retries all errors including 4xx (invalid request). Should only retry 5xx + network errors.

4. **No Perf Baseline for Extension Startup**: How long does extension initialization take? Does fetching all projects/sessions on activation cause noticeable lag?

---

## What Bob Did Well

1. **Phased Approach**: Visualization → Context → Execution is sensible
2. **Correct VSCode APIs**: TreeDataProvider, WebviewPanel, CodeLens, Hover are the right tools
3. **Good MCP Tool Schema**: The 4 proposed tools (search, context, execution, metrics) are well-formed
4. **Proper Host/Webview Separation**: Extension host vs webview architecture is sound
5. **Subdirectory Pattern**: `webview-ui/` with separate `package.json` is the right layout

---

## Recommendations

**Priority 1 (Blocking):**
1. Fix all 6 critical errors
2. Add CORS mitigation strategy (choose: proxy or backend whitelist)
3. Replace WebSocket with SSE throughout
4. Fix terminal execution design (use `child_process` or backend API)
5. Clarify MCP as separate process, not internal

**Priority 2 (Before Phase 2):**
6. Add CCDash-offline UX (degraded mode, health checks)
7. Define activation events (scope to CCDash workspaces)
8. Document backend API dependencies for Phase 2/3
9. Add multi-workspace strategy
10. Remove "reuse React components" claim; propose alternatives

**Priority 3 (Before Phase 3):**
11. Design MCP integration spike (can MCP server live in same process as extension host?)
12. Define extension/backend version compatibility contract
13. Add CSP configuration for webviews
14. Benchmark extension startup impact

---

## Next Steps

1. **Create PRD** from spec's feature list: `docs/project_plans/PRDs/features/vscode-ccdash-extension-v1.md`
2. **Create spikes**:
   - Webview CORS + component reuse feasibility
   - MCP server integration (architecture, IPC, lifecycle)
   - SSE client for real-time updates
3. **Create ADRs**:
   - Real-time: SSE vs polling vs WebSocket (settled: SSE)
   - MCP vs direct extension API (architecture decision needed)
   - Activation scope (workspace detection strategy)
4. **Fix spec**: Address all critical errors; convert to per-phase implementation plans
5. **Schedule review** after fixes with lead architect

---

## Bottom Line

The spec demonstrates good product thinking and scope, but conflates a feature roadmap with a technical specification. Before coding begins:

- Verify every API route against actual backend code
- Confirm WebSocket → SSE migration doesn't break realtime architecture
- Resolve CORS blocker (not a minor issue)
- Define how MCP integration works if committing to Phase 3
- Split into PRD, spikes, and phase-specific implementation plans

Current state: **Not yet implementation-ready.**
