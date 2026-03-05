---
doc_type: report
status: active
category: data
title: "Session Mappings Command Coverage Audit"
description: "Audit of command mapping sources, parser behavior, and criteria for adding commands to the Session Mappings page."
author: codex
created: 2026-03-02
updated: 2026-03-02
tags: [session-mappings, commands, parser, linking, claude-code, codex]
---

# Session Mappings Command Coverage Audit (2026-03-02)

## Direct Answer

Yes. Based on current logic, there are workflow commands that should be added to the **Session Mappings** page defaults (or otherwise unified through the same configuration source).

Most important gap:
- Commands treated as key workflow markers in linking/title logic but missing from mapping defaults:
  - `/dev:implement-story`
  - `/dev:complete-user-story`
  - `/fix:debug`
  - `/recovering-sessions`

Also: this thread itself is Codex-based; current mapping extraction logic is mostly Claude command-tag driven for `key_command` metadata, so thread-specific command-type metadata was limited.

## Where Commands Are Set Today

## 1) User-configurable mapping rules (source of truth for Session Mappings page)

- File: `backend/session_mappings.py`
- Storage: `app_metadata` key `session_mappings` (`entity_type='project'`)
- API:
  - `GET /api/session-mappings`
  - `PUT /api/session-mappings`
  - Router: `backend/routers/session_mappings.py`
- UI:
  - Route `/session-mappings`
  - Component: `components/SessionMappings.tsx`

Default rules currently include:
- `bash` mappings: git/test/lint/deploy
- `key_command` mappings:
  - `/dev:execute-phase`
  - `/dev:quick-feature`
  - `/plan:plan-feature`

## 2) Hardcoded workflow command markers used outside Session Mappings config

- `backend/routers/api.py` `_KEY_WORKFLOW_COMMAND_MARKERS`
- `backend/routers/features.py` `_KEY_WORKFLOW_COMMAND_MARKERS`
- `backend/db/sync_engine.py` `_KEY_WORKFLOW_COMMANDS`
- `backend/link_audit.py` command checks

These include commands beyond default Session Mappings rules:
- `/dev:implement-story`
- `/dev:complete-user-story`
- `/fix:debug`
- `/recovering-sessions` (sync engine only)

## 3) Parser extraction of command events

- Claude parser: `backend/parsers/platforms/claude_code/parser.py`
  - Detects `<command-name>...</command-name>` + `<command-args>...</command-args>`
  - Produces `log.type='command'` with `metadata.args` and `metadata.parsedCommand`
- Codex parser: `backend/parsers/platforms/codex/parser.py`
  - Parses tool calls/results and messages, but currently does not produce equivalent slash-command command logs from command-tag format.

## When Commands Should Be Added to Session Mappings

Add a command to Session Mappings when at least one is true:

1. It defines session type semantics users care about.
- Example: planning vs execution vs completion vs debug.

2. Its args carry structured metadata used for linking or display.
- Example: phase token, feature doc path, request ID, feature slug.

3. It is used in workflow ranking/ordering/title logic.
- If it appears in `_KEY_WORKFLOW_COMMAND_MARKERS` / `_KEY_WORKFLOW_COMMANDS`, it should also exist as a `key_command` mapping unless intentionally non-configurable.

4. It is emitted by recommendation systems.
- `backend/services/feature_execution.py` emits multiple `/dev:*` and `/plan:*` commands.

Do not add commands that are intentionally non-semantic/noise controls:
- `/clear`
- `/model`

## Mapping Types, Formatting, and Parsing Behavior

## `bash` mapping type

Purpose:
- Classifies shell commands via regex for transcript/tool labeling.

Fields:
- `pattern`, `category`, `transcriptLabel`, `priority`, `enabled`

How applied:
- In session detail API, only when tool call name is `Bash` (`backend/routers/api.py`), using `classify_bash_command()`.
- A matching rule can relabel displayed tool name and category.

Limits:
- Currently focused on Claude `Bash` tool naming path.
- Codex `exec_command`/`shell_command` are not mapped through this same UI config path yet.

## `key_command` mapping type

Purpose:
- Produces `sessionMetadata` shown in Session Inspector and reused in feature/session linking and titling.

Fields:
- `pattern`, `sessionTypeLabel`, `matchScope`, `fieldMappings`, `priority`, `enabled`

`matchScope` options:
- `command`
- `args`
- `command_and_args`

Supported `fieldMappings.source`:
- `command`
- `args`
- `phaseToken`
- `phases`
- `featurePath`
- `featureSlug`
- `requestId`

How parsing context is derived:
- `_derive_command_context()` in `backend/session_mappings.py` combines:
  - command name
  - args text
  - parser-supplied `parsedCommand`
- It can auto-derive request IDs, paths, feature path/slug, and phase tokens.

Output shape:
- `sessionTypeId`, `sessionTypeLabel`, `mappingId`
- `relatedCommand`, `relatedPhases`, `relatedFilePath`
- `fields[]` (label/value rows)

## Parsed/Linked Data Flow

1. Parser emits command logs (`type='command'`) with args + parsed context.
2. API/Feature routers collect command events and call `classify_session_key_metadata()`.
3. Result is attached as `sessionMetadata` and influences:
- Session title derivation
- Feature session link enrichment (`relatedPhases`, workflow cues)
- Inspector key metadata panel

## Coverage Mismatch Found

Current mismatch between configurable mappings and hardcoded workflow recognition:

- Present in defaults:
  - `/dev:execute-phase`
  - `/dev:quick-feature`
  - `/plan:plan-feature`

- Recognized elsewhere but missing in defaults:
  - `/dev:implement-story`
  - `/dev:complete-user-story`
  - `/fix:debug`
  - `/recovering-sessions`

Impact:
- These commands can influence ranking/link heuristics but may not produce first-class `sessionMetadata` via mapping rules.
- Reduced operator control through Session Mappings UI.

## Thread-Specific Findings

From this thread’s work context:
- We introduced Codex session parsing + new forensics signals.
- Session Mappings (`key_command`) still depends primarily on command-tag style command logs from Claude parser.
- For Codex-heavy sessions, command customization via Session Mappings is currently less effective unless equivalent command events are materialized.

## Recommendations

1. Add missing workflow commands to default `key_command` mappings.
- `/dev:implement-story`
- `/dev:complete-user-story`
- `/fix:debug`
- `/recovering-sessions`

2. Unify command canonical set.
- Replace scattered hardcoded command tuples with a shared command registry derived from session mappings defaults (plus explicit non-consequential list).

3. Extend Codex command normalization into mapping pipeline.
- Option A: emit `log.type='command'` for explicit slash-command patterns when present in Codex logs.
- Option B: allow `key_command` classification over selected Codex tool-call payloads when they contain command-like entries.

4. Add Session Mappings coverage diagnostics.
- UI/API indicator listing:
  - hardcoded workflow commands not represented in mappings
  - mappings never matched in recent sessions

5. Add tests for parity.
- Verify every workflow marker command has either:
  - a matching `key_command` rule, or
  - explicit exemption (`/clear`, `/model`).
