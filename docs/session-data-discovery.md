# Session Data Discovery (Platform-Configurable)

CCDash now includes a lightweight discovery script for mining new ingestable signals from large session datasets without loading everything into parser logic first.

## Files

- `backend/parsers/platforms/discovery_profiles.json`
- `backend/scripts/session_data_discovery.py`

The profile file separates platform-specific details (`roots`, globs, known keys, sidecar patterns, global config files) from extraction logic.

## Run

Quick run using project script:

```bash
npm run discover:sessions
```

Direct CLI examples:

```bash
python backend/scripts/session_data_discovery.py \
  --platform claude_code \
  --root /Users/<you>/.claude/projects \
  --max-files 800 \
  --max-jsonl-lines 250 \
  --write /tmp/claude-discovery.json
```

```bash
python backend/scripts/session_data_discovery.py \
  --platform codex \
  --root /Users/<you>/.codex/sessions \
  --max-files 800 \
  --max-jsonl-lines 250 \
  --write /tmp/codex-discovery.json
```

If roots are omitted, the script tries:

- explicit `--root` values
- profile env vars (for example `CCDASH_CLAUDE_PROJECTS_ROOT`)
- profile defaults (for example `${HOME}/.claude/projects`)

## Output

The JSON report includes:

- file inventory (`byExtension`, `pathBuckets`, `sidecarMatches`)
- schema frequencies (`topLevelKeys`, `entryTypes`, `contentBlockTypes`, `progressTypes`, `unknownEntryKeys`)
- command-derived resource signals (`database`, `api`, `docker`, `ssh`, `service`)
- global config summary (for example `~/.claude.json` keys/project MCP fields)
- generated `candidateSignals` suggestions to prioritize parser enhancements

## Multi-Platform

To support a new platform (for example Codex), add/adjust a profile in:

- `backend/parsers/platforms/discovery_profiles.json`

Only the profile should need updates for:

- root directories
- file patterns
- known entry keys
- sidecar conventions
- global config files

The Python script remains generic and can run against all profiles.

## Current CCDash Integration Status

Signals discovered via this workflow are now wired into session ingestion and Session Inspector forensics:

- Claude Code:
  - `resourceFootprint`
  - `queuePressure`
  - `subagentTopology`
  - `toolResultIntensity`
  - `testExecution` (aggregated parsed test-run telemetry from tool commands/results)
  - `entryContext.hookInvocations` (normalized hook invocation records from `hook_progress`)
  - `platformTelemetry`
  - `sidecars.toolResults`
- Codex:
  - `resourceFootprint`
  - `codexPayloadSignals`

Transcript/artifact mapping coverage now also includes:

- structured artifact capture for `agent` and `task` tool invocations
- structured artifact capture for `hook_progress` (`type=hook`)
- default transcript artifact mapping for `.claude/hooks/*` invocation lines

Related implementation files:

- `backend/parsers/platforms/claude_code/parser.py`
- `backend/parsers/platforms/codex/parser.py`
- `backend/parsers/platforms/registry.py`
- `components/SessionInspector.tsx`
