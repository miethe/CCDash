---
name: project-cross-project-session-fix
description: Cross-project session detail fix — apiFetch projectScopeOverride param, useSessionDetailQuery wiring, SessionDetail effectiveSession pattern
metadata:
  type: project
---

Cross-project session transcript fix on branch `fix/cross-project-session-read-path` (2026-06-29).

**Why:** Backend `GET /sessions/{id}` scopes by `X-CCDash-Project-Id` header; Multi-Project Command Center session lists span projects but detail fetches used only the global scope, returning 404 for cross-project sessions.

**Changes made:**
- `services/apiClient.ts`: Added optional `projectScopeOverride?: string | null` to `apiFetch` and `apiRequestJson`; updated `ApiClient.getSession(id, projectId?)` interface and impl to forward the override.
- `services/queries/sessions.ts`: `useSessionDetailQuery` now calls `client.getSession(sessionId, projectId ?? undefined)`.
- `components/SessionInspector.tsx`: `SessionDetail` computes `resolvedProjectId = session.projectId || activeProject?.id`, calls `useSessionDetailQuery`, and uses `effectiveSession = sessionDetail ?? session` for all log-dependent views (TranscriptView, ActivityView, FilesView, subagentNameBySessionId, taskArtifacts, sessionTestStatus). All three `linked-features` `apiFetch` calls pass `resolvedProjectId` as 3rd arg.

**Key pattern:** `session.projectId === ''` is the Unattributed sentinel → fall back to `activeProject?.id`. Missing projectId is a contract state, not a crash. Global scope remains unchanged for all other callers.

**How to apply:** When any session-scoped API call needs cross-project support, add `projectScopeOverride` as the 3rd arg to `apiFetch`/`apiRequestJson`. The existing `!headers.has(PROJECT_SCOPE_HEADER)` guard prevents double-setting.

**Pre-existing TS errors:** `SessionInspectorPanels.tsx(321,13)` — "Expected 6 arguments but got 7" — pre-dates this fix; confirmed via stash.
