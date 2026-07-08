# Hermes MCP runtime and session-review handoff

Status: handoff
Date: 2026-07-08
Target repo: CCDash
Consumer: Hermes on agentic-nuc

## Problem

Hermes should use CCDash for evals, session reviews, AARs, and AOS-linked session inspection. The
CCDash API is healthy on the NUC, but the current MCP launch path is easy to misconfigure:

- `python ~/dev/CCDash/backend/mcp/server.py` fails outside the repo/package context.
- `python -m backend.mcp.server` with global Python can miss backend dependencies such as
  `aiosqlite`.
- There is no standalone `ccdash` command on the NUC PATH, so Hermes needs either a packaged CLI
  entrypoint or a documented `uv run`/venv MCP command.

The NUC was repaired by running `npm run setup`, then adding Hermes MCP with the repo-managed
backend venv and an explicit cwd:

```bash
hermes mcp add ccdash \
  --command /home/miethe/dev/CCDash/backend/.venv/bin/python \
  --args -m backend.mcp.server \
  --cwd /home/miethe/dev/CCDash
```

This keeps Hermes moving, but CCDash should still own a clearer agent-facing launcher contract.

## Useful Current Surfaces

- MCP session search/detail/transcript tools:
  `backend/mcp/tools/sessions.py`
- MCP AAR tool:
  `backend/mcp/tools/reports.py`
- REST session review fallback:
  `GET /api/v1/sessions/search`
  `GET /api/v1/sessions/{session_id}/detail?project_id=...&include=transcript`
  `GET /api/v1/sessions/{session_id}/transcript?project_id=...`
- AOS correlation helper:
  `backend/services/aos_correlation.py`
- UI route for human/operator proof:
  `/sessions?session=<session_id>&tab=transcript`

## Requested Fix

Provide a robust Hermes/agent launcher contract for CCDash session-review tools.

Preferred shape:

1. Add or document a stable command such as `ccdash mcp serve` or `python -m backend.mcp.server`
   through the project-managed environment.
2. Ensure the command works from a clean shell on the NUC without relying on ambient `PYTHONPATH`.
3. Keep HTTP session/eval fallback documented for agents when MCP stdio is unavailable.
4. Add a small smoke command or test that verifies the MCP server imports and advertises session and
   AAR tools in the same environment Hermes will use.

## Acceptance Criteria

- A documented one-line Hermes MCP install command exists and works from `~/dev/CCDash`.
- The command does not fail with `ModuleNotFoundError: backend` or missing Python dependencies.
- Session review remains available through both MCP and loopback HTTP.
- AOS-ID search remains supported for `urn:aos:turn:<uuid>` values and sidecar-backed correlation.
- The handoff names validation commands for session search/detail, transcript pagination, and AAR
  generation.

## Validation Starting Points

```bash
cd ~/dev/CCDash
npm run setup
backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
npm run docker:hosted:smoke:mcp-contract
curl -fsS http://127.0.0.1:8090/api/health/ready
```
