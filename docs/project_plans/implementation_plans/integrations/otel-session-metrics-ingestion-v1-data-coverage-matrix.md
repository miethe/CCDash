---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: data_coverage_matrix
primary_doc_role: supporting_document
status: draft
category: integrations
title: "OTel Session Metrics Ingestion V1 — Data Coverage Matrix"
description: "Field-level comparison of Claude Code OTel signals, Claude Agent SDK observability, and CCDash session data, identifying coverage, gaps, and enhancement opportunities."
summary: "Validates the OTel ingestion plan by mapping every Claude Code OTel metric/log/span to CCDash AgentSession, SessionLog, session_messages, usage attribution, and intelligence-fact fields. Calls out permanent JSONL-only fields, opt-in-gated coverage, and net-new fields OTel adds."
author: claude-opus-4-7
created: 2026-05-05
updated: 2026-05-05
priority: high
risk_level: medium
complexity: high
track: Integrations
feature_slug: otel-session-metrics-ingestion-v1
feature_family: otel-session-metrics-ingestion
feature_version: v1
lineage_family: otel-session-metrics-ingestion
lineage_parent:
  ref: docs/project_plans/implementation_plans/integrations/otel-session-metrics-ingestion-v1.md
  kind: supports
lineage_type: integration
plan_ref: otel-session-metrics-ingestion-v1
owner: platform-engineering
audience:
  - ai-agents
  - developers
  - backend-platform
  - data-platform
tags:
  - opentelemetry
  - ingestion
  - sessions
  - claude-code
  - data-coverage
  - validation
related_documents:
  - docs/project_plans/implementation_plans/integrations/otel-session-metrics-ingestion-v1.md
  - docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
---

## 1. Purpose & Method

This matrix validates the OTel ingestion implementation plan against the upstream Claude Code OpenTelemetry specification and the existing JSONL-based session data model. All field names are copied verbatim from source specifications, enabling reviewers to cross-reference with upstream documentation and CCDash schema without translation. The matrix serves as the ground-truth artifact for determining which signals OTel adds/supplements and which remain JSONL-only.

## 2. Sources Surveyed

- **Claude Code Monitoring Docs**: https://code.claude.com/docs/en/monitoring-usage (OTel metrics, log events, trace spans, resource attributes, privacy opt-ins, configuration)
- **Claude Agent SDK Observability**: https://code.claude.com/docs/en/agent-sdk/observability (telemetry layer, resource injection, TRACEPARENT propagation, per-call env override semantics)
- **CCDash JSONL Parser & Persistence Layer**:
  - `backend/parsers/sessions.py` — entry parsing, metadata extraction
  - `backend/parsers/platforms/` — platform-specific signal interpretation
  - `backend/models.py` — Pydantic schema (AgentSession, SessionLog, session_messages, SessionUsageEvent, SessionUsageAttribution)
  - `backend/db/repositories/sessions.py` — session row persistence
  - `backend/db/repositories/session_messages.py` — message-level row schema and queries
  - `backend/services/session_transcript_projection.py` — transcript derivation from logs
  - `backend/services/session_usage_attribution.py` — attribution method and weight computation
  - `backend/db/sync_engine.py` — JSONL→DB sync logic
  - `types.ts` — frontend AgentSession shape and invariants

## 3. Legend

| Code | Meaning |
|------|---------|
| `FULL` | Field is supplied by OTel as a native attribute or by existing JSONL parser; no net-new ingestion logic required. |
| `OPT-IN` | Field is supplied only if a specific `OTEL_*` or `CLAUDE_CODE_*` env var is set (e.g., `OTEL_LOG_USER_PROMPTS`). Coverage depends on operator configuration. |
| `BETA` | Field requires beta feature flag (`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` or `ENABLE_BETA_TRACING_DETAILED=1`). Not guaranteed stable. |
| `PARTIAL` | Field is partially supplied by OTel (e.g., categorical error only, not full stack) or requires synthetic enrichment from other signals. |
| `NONE` | OTel does not supply this field; JSONL parsing is the only source. |
| `N/A` | Field is not applicable to this data class or signal type. |

**Source-of-truth priority**: JSONL is canonical for all existing fields. OTel supplements or adds new fields. If both JSONL and OTel report the same fact (e.g., `tokensIn`), JSONL is trusted unless OTel is explicitly designated as the new canonical source (e.g., `prompt.id` correlation).

## 4. Matrix A — Claude Code OTel Metrics → CCDash Fields

Mapping of all eight metrics from the monitoring spec to AgentSession columns and usage tables.

| OTel Metric | Type / Unit | Key Attributes | CCDash Target Field(s) | Coverage | Notes |
|---|---|---|---|---|---|
| `claude_code.session.count` | counter delta, count | `model`, `start_type ∈ {fresh,resume,continue}` | `sessions` row (new session count); `sessionType` inferred from other signals | `FULL` (count), `PARTIAL` (start_type) | `start_type` does not map to existing field; flagged as P0 enhancement for session resumption tracking. Requires new field. |
| `claude_code.lines_of_code.count` | counter delta, count | `model`, `type ∈ {added,removed}` | `updatedFiles[]` aggregate per session | `PARTIAL` | OTel provides type split (added/removed); JSONL parsing via tool_use output provides file-level details. Aggregation must preserve type split. |
| `claude_code.pull_request.count` | counter delta, count | `model` | `toolSummary[]` filter for PR; usage events filtered by tool_name="pull_request" | `PARTIAL` | OTel increments; JSONL contains detailed PR metadata (branch, commits, review state). No conflict. |
| `claude_code.commit.count` | counter delta, count | `model` | `gitCommitHashes[]`, `toolSummary[]` for "commit" tool | `FULL` | OTel count; JSONL provides hash list. Counts should align. |
| `claude_code.cost.usage` | gauge USD | `model`, `query_source ∈ {main,subagent,auxiliary}`, `speed`, `effort` | `totalCost`, `reportedCostUsd`, `usageAttributions[]` with `method ∈ {explicit_subthread_ownership, explicit_agent_ownership}` | `PARTIAL` | Attribute split on `query_source` and `effort` maps to `usageAttributions.method` + `entityType`. Requires enhancement to attribution logic (P3-T1 AC). |
| `claude_code.token.usage` | counter delta, tokens | `type ∈ {input,output,cacheRead,cacheCreation}`, `model`, `query_source`, `speed`, `effort` | `tokensIn`, `tokensOut`, `cacheReadInputTokens`, `cacheCreationInputTokens`; `usageAttributions[]` for `query_source` and `effort` splits | `FULL` | Type split is native to schema. `query_source` / `effort` attribution must be explicit in P3-T1 AC. |
| `claude_code.code_edit_tool.decision` | counter delta, count | `tool_name ∈ {Edit,Write,NotebookEdit}`, `decision ∈ {accept,reject}`, `source`, `language` | `toolSummary[]` with accept/reject tallies; new field for language distribution | `PARTIAL` | Tool acceptance/rejection is synthesized from JSONL tool_results; `source` and `language` are OTel-only enhancements. |
| `claude_code.active_time.total` | gauge seconds | SDK: `type ∈ {user,cli}` (metrics mode is gauge without type split) | `durationSeconds` + new field for user vs CLI attribution | `PARTIAL` | JSONL provides session duration from timestamps. OTel's `type` attribute enables split attribution (not in current schema); flagged as P0 enhancement. |

## 5. Matrix B — Claude Code OTel Log Events → CCDash Fields

Comprehensive mapping of all log events; includes events not mentioned in P3-T2 task.

| OTel Event | Key Attributes | Privacy Gate | CCDash Target | Coverage | Notes |
|---|---|---|---|---|---|
| `user_prompt` | `prompt.id`, `model`, `query_source`, `command_name` (opt-in), `interaction.sequence` | `OTEL_LOG_USER_PROMPTS` | `session_messages` row (role=user); `sessionForensics.otel.events[]` | `OPT-IN` | Prompt text REDACTED by default. With opt-in, maps to message content. `prompt.id` enables OTel-native correlation (see P5-T2). ⚠ Requires privacy gate enforcement in ingester. |
| `api_request` | `request_id`, `client_request_id`, `model`, `query_source`, `speed`, `attempt`, `api_request_timestamp` | none | `sessionForensics.otel.events[]`; new `sessionForensics.otel.apiRetryHistory[]` | `FULL` | Enables request-level tracing across retries. `attempt` and `api_request_timestamp` are net-new fields for retry tracking. |
| `api_response` | `request_id`, `model`, `query_source`, `speed`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `ttft_ms`, `duration_ms`, `stop_reason`, `success` | none | `session_messages` metadata; `sessionForensics.otel.apiMetrics[]` | `FULL` | Maps to existing token fields. `ttft_ms` is net-new (P0 enhancement). |
| `api_error` | `error` (category only), `status_code`, `model`, `query_source` | none | `sessionForensics.otel.apiErrors[]` | `FULL` | Category-only error; stack never included. Status code enables root-cause analysis. |
| `api_request_body` | `request_id`, content 60KB inline or file reference | `OTEL_LOG_RAW_API_BODIES=1` or `=file:<dir>` | external storage (e.g., S3 prefix); `sessionForensics.otel.rawBodiesRef` | `OPT-IN` | Extended-thinking content ALWAYS redacted, even with opt-in. Requires external object store for untruncated bodies. |
| `api_response_body` | `request_id`, content 60KB inline or file reference | `OTEL_LOG_RAW_API_BODIES=1` or `=file:<dir>` | external storage; `sessionForensics.otel.rawBodiesRef` | `OPT-IN` | Same as request_body. Extended-thinking redacted. |
| `tool_result` | `tool_name`, `duration_ms`, `result_tokens`, `file_path`, `full_command`, `skill_name`, `subagent_type`, `mcp_server_scope`, `tool_parameters`, `tool_input` (gated) | `OTEL_LOG_TOOL_DETAILS` (tool metadata), `OTEL_LOG_TOOL_CONTENT` (params + input) | `session_messages` row (tool_result type); `toolSummary[]`; `usageEvents[]` for result tokens | `FULL` (metadata), `OPT-IN` (content) | Result tokens always reported; parameters gated. Maps to existing tool_result parsing. |
| `tool_decision` | `tool_name`, `tool_use_id`, `decision`, `source ∈ {config,hook,user_permanent,user_temporary,user_abort,user_reject}` | none | `session_messages` metadata (decision reason); new `sessionForensics.otel.toolDecisions[]` | `FULL` | Source enum is net-new; enables decision audit trail. |
| `permission_mode_changed` | `from_mode`, `to_mode`, `trigger` | none | new `sessionForensics.otel.permissionModeTransitions[]` | `NONE` | Does not exist in current schema. Flagged as P0 enhancement (P3-T4). |
| `auth` | `action`, `success`, `auth_method`, `error_category`, `status_code` | none | new `sessionForensics.otel.authEvents[]` | `NONE` | Does not exist. Required for security audit. Flagged as P0 (P3-T4). |
| `mcp_server_connection` | `status ∈ {connected,failed,disconnected}`, `transport_type`, `server_scope`, `duration_ms`, `error_code`, `server_name` (gated), `error` (gated) | `OTEL_LOG_TOOL_DETAILS` | new `sessionForensics.otel.mcpConnections[]` or `toolSummary[]` extension | `FULL` (metadata), `OPT-IN` (details) | Complete MCP lifecycle tracking. New structure required (P3-T4). ⚠ NOT IN PLAN. |
| `internal_error` | `error_name` (class only), `error_code` (errno only), never message/stack | none (never on Bedrock/Vertex/Foundry; suppressed if `DISABLE_ERROR_REPORTING=1`) | `sessionForensics.otel.internalErrors[]` | `FULL` | Categorical only; stack never exposed. |
| `plugin_installed` | `marketplace.is_official`, `install.trigger`, `plugin.name`, `plugin.version`, `marketplace.name` (gated) | `OTEL_LOG_TOOL_DETAILS` (third-party) | new `sessionForensics.otel.pluginEvents[]` | `FULL` (official), `OPT-IN` (third-party) | Enables plugin audit trail. New structure. ⚠ NOT IN PLAN. |
| `skill_activated` | `skill.name` (placeholder "custom_skill" without opt-in), `invocation_trigger ∈ {user-slash,claude-proactive,nested-skill}`, `skill.source ∈ {bundled,userSettings,projectSettings,plugin}`, `plugin.name`, `marketplace.name` (conditional) | implicit (name redaction) | `skillsUsed[]` enhancement with invocation_trigger and source; `sessionForensics.otel.skillEvents[]` | `PARTIAL` | Skill name redacted unless opt-in. Trigger and source are net-new. ⚠ NOT IN PLAN. |
| `at_mention` | `mention_type ∈ {file,directory,agent,mcp_resource}`, `success` | none | new `sessionForensics.otel.atMentions[]` | `NONE` | New event type. Enables mention tracking. ⚠ NOT IN PLAN. |
| `api_retries_exhausted` | `model`, `error`, `status_code`, `total_attempts`, `total_retry_duration_ms`, `speed` | none | `sessionForensics.otel.failedRetries[]` | `FULL` | Complement to `api_request` retry tracking. Aggregates failed retry chain. Net-new fields (P0 enhancement). |
| `hook_execution_start` | `hook_event`, `hook_name`, `num_hooks`, `managed_only`, `hook_source`, `hook_definitions` (gated) | `OTEL_LOG_TOOL_DETAILS` | `sessionForensics.otel.hookEvents[]` (start) | `FULL` (metadata), `OPT-IN` (definitions) | Begin hook lifecycle tracking. ⚠ NOT IN PLAN. |
| `hook_execution_complete` | `hook_event`, `hook_name`, `num_success`, `num_blocking`, `num_non_blocking_error`, `num_cancelled`, `total_duration_ms` | none | `sessionForensics.otel.hookEvents[]` (completion counters) | `FULL` | Completes hook audit trail with outcome counts. Net-new. ⚠ NOT IN PLAN. |
| `compaction` | `trigger ∈ {auto,manual}`, `success`, `duration_ms`, `pre_tokens`, `post_tokens`, `error` | none | new `sessionForensics.otel.compactionEvents[]` | `NONE` | Detects context compaction operations. Net-new. ⚠ NOT IN PLAN. |

## 6. Matrix C — Claude Code OTel Trace Spans → CCDash Fields (Beta)

Mapping of span types; requires `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`. Detailed hook-span content also requires `ENABLE_BETA_TRACING_DETAILED=1`.

| Span / Event | Parent | Key Attributes | CCDash Target | Beta Flag | Coverage |
|---|---|---|---|---|---|
| `claude_code.interaction` | root | `user_prompt` (gated), `user_prompt_length`, `interaction.sequence`, `interaction.duration_ms` | `session_messages` root entry; `sessionForensics.otel.interactions[]` | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` | Root span per user turn. Sequence enables message ordering. Duration captures full interaction wall-clock. |
| `claude_code.llm_request` | `interaction` | `model`, `gen_ai.system=anthropic`, `gen_ai.request.model`, `query_source`, `speed`, `llm_request.context`, `duration_ms`, `ttft_ms`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `request_id`, `gen_ai.response.id`, `client_request_id`, `attempt`, `success`, `status_code`, `error`, `response.has_tool_call`, `stop_reason`, `gen_ai.response.finish_reasons` | `session_messages` metadata; detailed retry history in `sessionForensics.otel.llmRequestSpans[]` | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` | Comprehensive LLM request span with semantic convention attrs. Enables precise retry and latency attribution. `ttft_ms` is net-new (P0 enhancement). |
| `claude_code.tool` | `interaction` | `tool_name`, `duration_ms`, `result_tokens`, `file_path`, `full_command`, `skill_name`, `subagent_type` (gated) | `session_messages` tool use span; `toolSummary[]` duration stats | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` | Tool execution span. Duration and token tracking. |
| `claude_code.tool.blocked_on_user` | `tool` | `duration_ms`, `decision`, `source` | new `sessionForensics.otel.toolWaitEvents[]` | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` | Detects user-blocking waits within tool execution. Net-new (P0 enhancement). ⚠ NOT IN PLAN. |
| `claude_code.tool.execution` | `tool` | `duration_ms`, `success`, `error` (gated) | `sessionForensics.otel.toolExecutionMetrics[]` | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` | Execution outcome. Error only if opt-in. ⚠ NOT IN PLAN. |
| `claude_code.hook` | `interaction` | `hook_event`, `hook_name`, `num_hooks`, `hook_definitions` (gated ENABLE_BETA_TRACING_DETAILED), `duration_ms`, `num_success`, `num_blocking`, `num_non_blocking_error`, `num_cancelled` | `sessionForensics.otel.hookSpans[]` | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + conditional `ENABLE_BETA_TRACING_DETAILED=1` for definitions | Hook execution tracing. Second beta flag gates detailed hook definitions. ⚠ NOT IN PLAN. |

## 7. Matrix D — Standard / Resource Attributes → CCDash Provenance

Resource and semantic convention attributes common to metrics, logs, and spans. Cardinality control via attribute inclusion flags.

| OTel Attribute | Always-on? | Cardinality Control | CCDash Target | Coverage |
|---|---|---|---|---|
| `session.id` | yes (default via `OTEL_METRICS_INCLUDE_SESSION_ID`) | — | `sessionForensics.otel.session_id` or `sessionId` link | `FULL` |
| `app.version` | no (via `OTEL_METRICS_INCLUDE_VERSION`) | — | `modelVersion` or `platformVersion` context | `OPT-IN` |
| `organization.id` | auth only | — | new `sessionForensics.otel.organizationId` | `PARTIAL` |
| `user.account_uuid` | yes (default via `OTEL_METRICS_INCLUDE_ACCOUNT_UUID`) | — | existing `userId` or new `sessionForensics.otel.account_uuid` | `FULL` |
| `user.account_id` | yes (default via `OTEL_METRICS_INCLUDE_ACCOUNT_UUID`) | — | existing or new `sessionForensics.otel.account_id` | `FULL` |
| `user.id` | always-on (installation ID) | high cardinality (unique per install) | `sessionForensics.otel.installationId` (never endpoint auth) | `FULL` |
| `user.email` | auth only | none | new `sessionForensics.otel.userEmail` (hash at ingestion per P3-T4) | `OPT-IN` |
| `terminal.type` | always-on (iTerm.app, vscode, cursor, tmux, etc.) | medium | new `sessionForensics.otel.terminalType` | `FULL` |
| `prompt.id` | on log events | UUID per user turn | `sessionForensics.otel.promptId`; new `session_messages.otel_prompt_id` (P5-T2 enhancement) | `FULL` |
| `workspace.host_paths` | desktop app (string array) | high | new `sessionForensics.otel.workspacePaths` (requires PII review per P3-T4) | `FULL` |
| `service.name` | always-on; default "claude-code", renamable | — | `platformType` or `sessionForensics.otel.service_name` (P5-T5: must not hardcode "claude-code" in facets) | `FULL` |
| `service.version` | always-on | — | `platformVersion` | `FULL` |
| `os.type` | always-on (e.g., "linux", "macos", "windows") | — | new `sessionForensics.otel.osType` | `FULL` |
| `os.version` | always-on | — | new `sessionForensics.otel.osVersion` | `FULL` |
| `host.arch` | always-on (e.g., "x86_64", "arm64") | — | new `sessionForensics.otel.hostArch` | `FULL` |
| `wsl.version` | Windows/WSL only | — | new `sessionForensics.otel.wslVersion` | `FULL` |
| meter name `com.anthropic.claude_code` | implicit | — | metric provenance tag | `FULL` |

## 8. Matrix E — CCDash Fields Not Coverable by OTel (Permanent JSONL-Only)

Fields that OTel cannot supply; JSONL parsing remains exclusive source.

| CCDash Field | Source | Why OTel Can't Supply | Implication for Plan |
|---|---|---|---|
| `parentUuid` / `uuid` (entry tree) | JSONL metadata blocks | OTel has no concept of recursive entry hierarchy or fork correlation at parse time. | P5-T3: canonical transcript derives from entry tree, not OTel order. Enforce in plan that fork/subagent nesting is verified JSONL-first. |
| `forkParentSessionId`, `forkPointEntryUuid`, `forkPointParentEntryUuid`, `forkDepth`, `forkCount` | JSONL metadata (uuid/parentUuid correlation + session-boundary events) | OTel metrics/logs/spans do not encode session fork graph. | P5-T3: fork ancestry is JSONL-canonical. OTel can label events with `session.id` but cannot reconstruct tree retroactively. |
| `threadKind ∈ {root,fork,subagent}` | JSONL metadata (uuid/parentUuid + subagent entry markers) | OTel attributes do not distinguish thread type. | P5-T3: must infer from JSONL entry graph, not OTel service.name. |
| `subagentThread` (recursive nesting) | JSONL nested subagent entry blocks | OTel spans are tree-structured but service.name is not a strong thread identity. | P5-T3: subagent nesting is JSONL-exclusive. OTel can trace service.name=subagent-N but should not override JSONL truth. |
| `displayAgentType` (string) | JSONL session metadata or narrative inference | OTel does not classify agent type. | P5-T3: narrative inference or upstream metadata. No OTel enhancement path. |
| Extended-thinking content | JSONL assistant message content (when present) | Extended-thinking is always redacted in OTel logs and spans, even with privacy opt-ins. | P3-T4: update privacy section: extended-thinking content is JSONL-only and permanently unavailable from OTel. Document in user guide. |
| `platformVersionTransitions[]` (mid-session version changes) | JSONL entry metadata (version tags on subsequent entries) | OTel `service.version` is constant per telemetry session; does not capture tool restarts or version bumps mid-session. | P5-T3: transcript projection must detect version changes from JSONL, not OTel. Potential collision if OTel version differs mid-stream; trust JSONL. |
| Sidecars: `todos`, `tasks`, `teams`, `session_env`, `tool_results` (structured) | JSONL sidebar/metadata or separate file formats | OTel does not emit these structures. | P5-T3: JSONL-only. No OTel path. |
| `sessionMetadata.relatedPhases`, structured fields | JSONL metadata frontmatter or narrative extraction | OTel does not understand feature/phase taxonomy. | P5-T3: JSONL-only. OTel can label with linked feature IDs if supplied as resource attrs, but OTel is not the source. |
| `phaseHints[]`, `taskHints[]` (narrative-derived) | JSONL content pattern-matching or upstream metadata | OTel has no semantic understanding of planning domains. | P5-T3: JSONL narrative inference is exclusive. OTel is silent. |
| Sentiment facts, code-churn facts, scope-drift facts | JSONL message content (requires opt-in content parsing) | OTel user_prompt, tool_result, assistant message content is redacted by default or not included in events. Derivation requires unredacted content. | P3-T4: update privacy: sentiment/churn/scope-drift derivation requires OTEL_LOG_USER_PROMPTS + OTEL_LOG_TOOL_CONTENT opt-ins AND extended-thinking redaction caveat. Document as optional intelligence enrichment, not required. |
| Codex platform sessions (Claude 3.5 Sonnet native) | JSONL session metadata (platformType=Codex) | OTel is Claude Code telemetry only. Codex emits separate logs. | P5-T3: out of scope for this plan. Note in overview. |
| `gitAuthor`, `gitBranch` | JSONL metadata from git tool output or entry tags | OTel does not capture git context. | P5-T3: JSONL-only. OTel can label with workspace.host_paths but not git state. |
| `recalculatedCostUsd` (reconciliation) | JSONL aggregation + service-side pricing lookup | OTel cost.usage is real-time; reconciliation requires post-hoc audit against billing. | P5-T3: reconciliation logic is JSONL-driven. OTel cost aligns with reported; recalculation is audit-layer concern. |
| `relayMirrorUsage` (from progress events) | JSONL relay/progress event blocks | OTel does not understand relay mirroring. | P5-T3: JSONL-only. OTel tooling may enrich; progress events are exclusive source. |

## 9. Matrix F — Net-New Fields OTel Adds vs Current CCDash Schema

OTel-enabled enhancements to CCDash data model; not present in JSONL baseline.

| OTel Source | Field | Proposed CCDash Target | Effort | Value |
|---|---|---|---|---|
| `claude_code.session.count` + `start_type` attr | session resumption tracking | `sessionMetadata.startType ∈ {fresh,resume,continue}` | high | high — enables session-resumption analytics and usage anomaly detection. |
| `claude_code.active_time.total` + `type` attr | user vs CLI time split | `durationSeconds` + new `userActiveDurationSeconds` / `cliOnlyDurationSeconds` | medium | high — distinguishes interactive vs automated usage for SLA metrics. |
| `api_response.ttft_ms` | time-to-first-token latency | `sessionForensics.otel.ttftMs` (per-request histogram) | low | high — critical for latency debugging and SLA validation. |
| `api_request` / `api_response` + `attempt` attr | retry history | `sessionForensics.otel.apiRetryHistory[]` with request_id, attempt, timestamps, success | medium | high — enables failure mode analysis and retry-storm detection. |
| `api_error.status_code` | HTTP status codes on failures | `sessionForensics.otel.apiErrors[].statusCode` | low | high — root-cause classification (429, 500, etc.). |
| `tool_decision.source` enum | tool decision audit | `sessionForensics.otel.toolDecisions[]` with source ∈ {config,hook,user_permanent,user_temporary,user_abort,user_reject} | low | medium — compliance audit trail for tool governance. |
| `mcp_server_connection` events | MCP connection lifecycle | `sessionForensics.otel.mcpConnections[]` with status, transport_type, duration_ms, error codes | medium | high — MCP reliability monitoring. |
| `permission_mode_changed` events | permission mode transitions | `sessionForensics.otel.permissionModeTransitions[]` | low | medium — security audit; compliance tracking. |
| `auth` events | authentication lifecycle | `sessionForensics.otel.authEvents[]` with action, success, auth_method, error_category | low | medium — security audit. |
| hook span details | hook execution tracing | `sessionForensics.otel.hookSpans[]` with num_success, num_blocking, num_non_blocking_error, num_cancelled | medium | medium — hook reliability and impact. |
| `claude_code.tool.blocked_on_user` span | user-blocking wait detection | `sessionForensics.otel.toolWaitEvents[]` with duration_ms | low | medium — UX latency attribution. |
| `plugin_installed`, `skill_activated` events | plugin/skill audit trail | `sessionForensics.otel.pluginEvents[]`, `sessionForensics.otel.skillEvents[]` with trigger, source | low | medium — ecosystem adoption and extension audit. |
| `at_mention` events | mention tracking | `sessionForensics.otel.atMentions[]` with mention_type | low | low — optional usage analytics. |
| `api_request_body` / `api_response_body` (raw) | untruncated request/response bodies | external object store (S3, GCS, local) with `sessionForensics.otel.rawBodiesRef` | high | medium — debugging tool; privacy-gated. |
| `prompt.id` attribute | OTel-native message correlation | `session_messages.otel_prompt_id` (P5-T2 schema extension) | low | high — enables OTel-first message ordering and deduplication. |
| `resource.os.type`, `resource.os.version`, `resource.host.arch`, `resource.wsl.version` | platform provenance | `sessionForensics.otel.osType`, `osVersion`, `hostArch`, `wslVersion` | low | low — platform-specific debugging. |
| `resource.terminal.type` | terminal environment | `sessionForensics.otel.terminalType` | low | low — environment context. |
| `resource.workspace.host_paths` (with PII gate) | workspace context | `sessionForensics.otel.workspacePaths` (hashed or redacted per P3-T4) | low | low — workspace correlation for shared systems. |

## 10. Matrix G — Agent SDK Deltas vs Claude Code CLI

Comparison of telemetry behavior between SDK and CLI; identifies plan configuration implications.

| Aspect | CLI | Agent SDK | Plan Implication |
|---|---|---|---|
| **Telemetry layer** | Emits all metrics/logs/spans natively via OTel exporters. | Runs Claude Code as subprocess; emits IDENTICAL telemetry through CLI subprocess. | No separate SDK telemetry adapter required. P3-T1/T2/T3 ingestion logic applies to both. |
| **OTEL_SERVICE_NAME** | Default "claude-code". | Caller can override via env or per-call option. Common: "support-triage-agent", "code-review-agent". | P5-T5 CRITICAL: Do NOT hardcode `service.name == "claude-code"` in facet queries or aggregation. Use `service.name` as-is from resource attrs. Config example in P4-T1 must show OTEL_SERVICE_NAME override. |
| **OTEL_RESOURCE_ATTRIBUTES** | CLI ignores. | SDK caller can inject `enduser.id`, `tenant.id` per call via dict or env var. Python spreads into process.env; TypeScript replaces. | P4-T1 config must document resource attr injection pattern. P5-T5 facet logic should group/filter by `enduser.id` and `tenant.id` if present. Ingester must accept arbitrary `OTEL_RESOURCE_ATTRIBUTES` as bag. |
| **W3C TRACEPARENT** | Interactive CLI ignores inbound TRACEPARENT (avoids CI ambient pollution). | SDK reads TRACEPARENT at session start; auto-injects to subprocesses (tool.execution context propagation). | P4-T1: document TRACEPARENT handling. P5-T1 ingester does not require TRACEPARENT reconstruction; OTel trace context is self-contained. Optional future: use TRACEPARENT to correlate with upstream observability stack. |
| **Per-call env override (Agent SDK)** | N/A | ClaudeAgentOptions.env dict per call. Python merges with parent; TypeScript replaces. | P4-T1 config docs must clarify env semantics per language. |
| **Telemetry export** | Respects OTEL_EXPORTER_OTLP_* config per process. | SDK process inherits; caller can override per call. | P4-T1: SDK users can re-target telemetry via per-call options. Plan must allow operator-level config + per-session override. |

**Conclusion**: No separate SDK adapter is required for ingestion parity. The SDK and CLI emit identical signals. Plan validation: P4-T1 config and P5-T5 facet logic must trust `service.name`, `enduser.id`, and `tenant.id` from resource attributes rather than hardcoding "claude-code" or deriving tenant from session.id.

## 11. Plan Validation Findings

The following gaps in the existing implementation plan are surfaced by this matrix:

- **P3-T2 incompleteness (8 log events)**: Events `mcp_server_connection`, `plugin_installed`, `skill_activated`, `at_mention`, `hook_execution_start`, `hook_execution_complete`, `permission_mode_changed`, and `auth` are omitted from P3-T2 task scope. Matrix recommends P0 inclusion (see Matrix B notes). Reconcile with P3-T2 AC.

- **P3-T3 incompleteness (trace sub-spans + second beta flag)**: Spans `claude_code.tool.blocked_on_user` and `claude_code.tool.execution` are not mentioned. The second beta flag `ENABLE_BETA_TRACING_DETAILED` for hook-span definitions is missing from P3-T3 configuration. Add to P3-T3 AC.

- **P3-T4 privacy gaps**: Extended-thinking content is **permanently redacted** by OTel, even with `OTEL_LOG_RAW_API_BODIES=1`. User guide (P6-T1) must state this explicitly. PII fields `workspace.host_paths` and `terminal.type` require review for cardinality and retention (hashing guidance in P3-T4 AC). `user.id` is always-on installation identifier; clarify that it is not endpoint authentication and is safe for anonymized sessions.

- **P4-T1 config incompleteness**: Missing configurations: mTLS env vars (`CLAUDE_CODE_CLIENT_CERT`, `CLAUDE_CODE_CLIENT_KEY`, `CLAUDE_CODE_CLIENT_PASSPHRASE`, `NODE_EXTRA_CA_CERTS`), `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` (delta vs cumulative), `ENABLE_BETA_TRACING_DETAILED` (gating detailed hook definitions), TRACEPARENT propagation semantics, arbitrary `OTEL_RESOURCE_ATTRIBUTES` acceptance and merge logic. Expand P4-T1 AC.

- **P5-T5 facet logic error**: Code that filters or groups by `service.name == "claude-code"` will fail for Agent SDK users who rename service.name. P5-T5 AC must use resource attributes as-is from ingested events. Add regression test: Agent SDK override of OTEL_SERVICE_NAME must not break faceting.

- **P5-T2 correlation enhancement**: `prompt.id` (UUID per user turn) is OTel-native correlation key that JSONL does not provide. Recommend new field `session_messages.otel_prompt_id` to enable deduplication when both JSONL and OTel report the same turn. Add to P5-T2 AC as optional schema extension.

- **P3-T1 token attribution clarification**: Metrics `claude_code.token.usage` and `claude_code.cost.usage` include attributes `query_source ∈ {main,subagent,auxiliary}` and `effort`. These must map to `usageAttributions.method` and `entityType`. Add explicit AC: "Token events with query_source='subagent' OR cost.usage.effort attribute map to sessionUsageAttribution with entityType='subagent' and method='explicit_subthread_ownership'." (Analogous for main, auxiliary, effort splits.)

- **P3-T4 credential handling**: Plan does not address mTLS client certificate lifecycle for OTEL_EXPORTER_OTLP gRPC. If using mTLS, add guidance: cert/key rotation, expiry handling, fallback strategy. Low priority but required for production hardening.

- **P6 (docs) gap**: User guide must document that sentiment/churn/scope-drift intelligence facts require `OTEL_LOG_USER_PROMPTS=1` + `OTEL_LOG_TOOL_CONTENT=1` opt-ins AND extended-thinking content is unavailable. These are optional enrichments, not guaranteed data. Add section in P6-T1 under "Optional Intelligence Signals."

## 12. Open Questions

1. **Deduplication strategy for `prompt.id` correlation**: When both JSONL and OTel report the same user turn, should CCDash treat them as the same message (merge) or distinct events? How aggressively should deduplication apply — strict UUID match, or time-window heuristic?

2. **Email hashing (user.email PII)**: Should `user.email` be hashed at OTel ingestion time (one-way, per-session), or at storage time (global lookup table enabling cross-session email tracking)? What hash function and salt strategy?

3. **Tenant / organization scoping (`tenant.id`, `organization.id`)**: If Agent SDK injects `OTEL_RESOURCE_ATTRIBUTES=tenant.id=acme-corp`, should CCDash create a top-level scoping construct (e.g., `organizationId` on AgentSession) or treat it as forensic metadata? Implications for multi-tenant query isolation.

4. **Workspace path PII**: `workspace.host_paths` is a string array of filesystem paths (e.g., `["/Users/alice/projects/secret"]`). What is the retention policy? Should paths be normalized, hashed, or cardinality-capped per session?

5. **TRACEPARENT upstream integration**: Is there demand to correlate OTel TRACEPARENT with an upstream observability stack (e.g., Honeycomb, Datadog)? Should P5-T1 ingester preserve TRACEPARENT for forwarding, or is trace context purely OTel-internal?

6. **Extended-thinking redaction scope**: Are there future use-cases where extended-thinking content should be conditionally available (e.g., under strict privacy consent)? Or is permanent redaction a hard constraint? Affects long-term schema design for `sessionForensics.otel`.

---

*Document generated 2026-05-05. Reviewed against Claude Code Monitoring Docs, Agent SDK docs, and CCDash backend schema.*
