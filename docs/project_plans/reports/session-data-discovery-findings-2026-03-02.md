---
doc_type: report
status: active
category: data
title: "Session Data Discovery Findings (Claude Code + Codex)"
description: "Sampled discovery results from platform-configurable session schema extraction."
author: codex
created: 2026-03-02
updated: 2026-03-02
tags: [sessions, discovery, schema, claude-code, codex, forensics]
---

# Session Data Discovery Findings (2026-03-02)

## Scope

Used `backend/scripts/session_data_discovery.py` with platform profiles in `backend/parsers/platforms/discovery_profiles.json` to sample session datasets without full ingestion.

## Claude Code Sample

- Root sampled: `~/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat`
- Processed files: `1200` (`1069` JSONL, `131` tool-result TXT)
- Sidecar matches:
  - `subagents`: `847`
  - `tool_results`: `131`
- Dominant event/message patterns:
  - `entry type`: `progress`, `assistant`, `user`
  - `content blocks`: `tool_use`, `tool_result`, `text`, `thinking`
  - `progress types`: `hook_progress`, `agent_progress`, `bash_progress`, `waiting_for_task`
- Dominant tools:
  - `Read`, `Bash`, `Edit`, `Grep`, `Glob`, `Task`, `Skill`
- Extracted resource categories from command sampling:
  - `database` (mostly local sqlite)
  - `api` (mix of localhost and external hosts)

## Codex Sample

- Root sampled: `~/.codex/sessions`
- Processed files: `215` JSONL
- Dominant top-level entry types:
  - `response_item`, `event_msg`, `turn_context`
- Payload-level types:
  - `token_count`, `function_call`, `function_call_output`, `agent_reasoning`, `reasoning`, `message`
- Tool/function names:
  - `exec_command`, `shell_command`, `shell`, `apply_patch`, `update_plan`
- Extracted resource categories:
  - `database`, `api`, `docker`

## High-Value New Signals

1. Subagent topology metrics (Claude): fan-out count/depth, completion lag per root session.
2. Tool-results artifact indexing (Claude): checksum + line count + tail preview for `tool-results/*.txt`.
3. Queue pressure metrics (Claude): `waiting_for_task` counts and duration approximation.
4. Resource footprint analytics (Claude + Codex): db/api/docker/ssh/service targets derived from command arguments.
5. Global platform telemetry (Claude): `.claude.json` feature gate usage, project MCP server inventory, onboarding/usage counters.
6. Codex payload analytics: `token_count`, `reasoning`, and function-call distributions from wrapped `payload` events.

## Implementation Status (Updated 2026-03-02)

The following discovery outputs have been implemented in CCDash ingestion + Session Inspector:

- Claude:
  - `resourceFootprint`
  - `queuePressure`
  - `subagentTopology`
  - `toolResultIntensity`
  - `platformTelemetry`
  - `sidecars.toolResults`
- Codex:
  - parser integration via platform registry
  - `resourceFootprint`
  - `codexPayloadSignals`

## Platform Distinction Strategy

Keep cross-platform logic in one script/parser and isolate platform-specific assumptions in profiles:

- roots/env roots
- sidecar conventions
- known key lists
- payload wrapping conventions
- global config locations

This enables adding new platforms (or schema revisions) by profile edits rather than parser rewrites.
