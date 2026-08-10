# ICA key + spend capture — operator guide (v51)

Feature: capture per-session **ICA key identity** and **dollar spend** — the two
dimensions the launch sidecar could not carry before. These map to five new
nullable `sessions` columns (v51 schema): `ica_key`, `ica_spend_start`,
`ica_spend_end`, `ica_spend_delta`, `ica_spend_attribution`.

Intent-tree node: `node_01KZKZC4HFBD5188B1SPTBNEZ8`.

## What CCDash captures

| Column | Source | Contract |
| :-- | :-- | :-- |
| `ica_key` | `CCDASH_LAUNCH_ICA_KEY` env at hook time | ICA key NAME (`CC1`..`CC6`). **Never a token.** Unset → NULL; never defaulted to `CC1`. |
| `ica_spend_start` | `x-litellm-key-spend` header on a 1-token gateway probe at **SessionStart** | Raw cumulative-per-key dollars (stored verbatim as TEXT). |
| `ica_spend_end` | Same header on a 1-token probe at **SessionEnd** | Raw cumulative dollars at session end. |
| `ica_spend_delta` | Derived by `backfill_ica_spend_attribution` | `end - start` **only when attributable** (see below). Otherwise NULL. |
| `ica_spend_attribution` | Same backfill | Closed vocab: `attributed` \| `concurrent_shared_key` \| `key_changed` \| `incomplete_readings`. |

The `x-litellm-key-spend` header is a **cumulative-per-key** total shared across
every session that key makes (all machines, all callers). A session's honest
cost is `end - start` only when nothing else used the key in that window. The
backfill checks the cross-session ledger and refuses to divide a shared
counter: contaminated windows land as `concurrent_shared_key` with a **NULL
delta**, never a silently pro-rated number.

Why a message probe, not an admin call: `/key/info`, `/v1/key/info`, and
`/spend/logs` all 404 on the ICA gateway (probed 2026-08-10). The header on
`/v1/messages` responses is the only available read.

The probe is fail-open (any timeout/error → NULL) and never writes, logs, or
stores any token bytes. It uses `ANTHROPIC_AUTH_TOKEN` from the environment
to authorize the call.

## Operator install (one-time)

### 1. Launcher — `~/ica-claude.sh`

Add this line **before** the `exec` line, alongside the existing
`CCDASH_LAUNCH_*` exports:

```bash
export CCDASH_LAUNCH_ICA_KEY="${ICA_KEY:-}"
```

Empty ICA key → empty export → NULL column. The default lane (`ICA_KEY`
unset, `ICA_DOTENV` fallback) leaves this NULL, satisfying AC1.

### 2. Hook registration — `~/.claude/settings.json` **and** `~/.claude/ica-settings.json`

Register the **same** script under both `SessionStart` **and** `SessionEnd`
(or `Stop`) so the closing spend reading is captured:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/CCDash/scripts/hooks/ccdash_capture_session_start.py"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/CCDash/scripts/hooks/ccdash_capture_session_start.py"
          }
        ]
      }
    ]
  }
}
```

The script is idempotent between the two events: SessionEnd reads the sidecar
already written on disk and merges the closing reading in.

### 3. Verify

Launch a new ICA session, then inspect the sidecar next to its JSONL:

```bash
jq '{schemaVersion, icaKey, icaSpendStart, icaSpendEnd}' ~/.claude/projects/*/.../*.capture.json
```

Expect `schemaVersion=3`, `icaKey="CC…"`, and a numeric `icaSpendStart`; the
`icaSpendEnd` populates on session close. After the next CCDash sync pass the
`sessions.ica_spend_*` columns show, and `sessions.ica_spend_attribution` is
one of the four vocabulary tokens.

## Reading the surface

Session-detail responses expose the fields under camelCase names:
`icaKey`, `icaSpendStart`, `icaSpendEnd`, `icaSpendDelta`, `icaSpendAttribution`.
Any of them being `null` means "Not captured" — a contract state, not a bug.
The API contract is set; a frontend surface (SessionInspector row, badge,
column) is intentionally **not shipped in this change** — mirror the existing
"Not captured" fallback pattern used for `launcher` / `profile` / `effortTier`
when adding one. AC4's "exposed with `Not captured` fallback" is met by the
API returning `null` verbatim; the render decision is a UI task, not a
capture task.

Consumers **MUST** treat an unrecognised `icaSpendAttribution` token as
"unknown" rather than hard-failing; the vocabulary may grow.

## Debugging

* No `ica_key` on a session you know launched via ICA → the launcher export
  is missing or the sidecar was written before `_SCHEMA_VERSION` bumped to 3.
  Backfill is impossible (the launcher env is not recorded elsewhere).
* `ica_spend_start` populated but `ica_spend_end` NULL → the SessionEnd hook
  never fired (Claude crashed / user killed it). The delta stays NULL under
  `incomplete_readings`; this is expected behaviour, not a defect.
* `ica_spend_attribution="concurrent_shared_key"` on lots of rows → shared use
  of a single key across concurrent sessions. Delta is intentionally NULL;
  per-session attribution needs a per-session key allocation.
* `x-litellm-key-spend` absent from the response → the gateway version does
  not surface it. Both readings stay NULL; nothing to fix in CCDash.

## References

* Migration: `backend/db/sqlite_migrations.py` (`SCHEMA_VERSION = 51`) +
  `backend/db/postgres_migrations.py`.
* Vocab + pure logic: `backend/parsers/ica_spend.py`.
* Sidecar writer: `scripts/hooks/ccdash_capture_session_start.py`.
* Sidecar reader: `backend/parsers/capture_sidecar.py`.
* Backfill: `SqliteSessionRepository.backfill_ica_spend_attribution` +
  Postgres mirror; wired into `sync_engine.SyncEngine.sync_project` phase 1.
* Session-detail exposure: `backend/application/services/agent_queries/session_detail.py::_apply_launch_capture`.
* Tests: `backend/tests/test_ica_spend.py`.
