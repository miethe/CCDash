---
title: "ADR-007: Local Daemon Packaging — Subcommand of `ccdash` CLI"
type: "adr"
status: "accepted"
created: "2026-05-10"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/SPIKEs/remote-ccdash-streaming.md"
tags: ["adr", "daemon", "packaging", "cli", "lifecycle"]
---

# ADR-007: Local Daemon Packaging — Subcommand of `ccdash` CLI

## Status

Accepted (SPIKE-resolved 2026-05-10)

## Context

The remote-CCDash architecture (design-spec `remote-ccdash-streaming.md`) introduces a long-running local process on the developer's workstation that:

1. Tails JSONL session files (uses `FilesystemSource` logic extracted from `SyncEngine` in ADR-009).
2. POSTs NDJSON batches to the remote server's ingest endpoint (ADR-006).
3. Buffers to local disk on network failure and resumes idempotently.
4. Reports health to the user via `ccdash daemon status`.

Three packaging options were evaluated: (A) standalone Go binary, (B) subcommand of the existing Python `ccdash` CLI (`packages/ccdash_cli/`), (C) new `daemon` runtime profile reusing `backend/runtime/` bootstrap with HTTP disabled.

## Decision

**Package the daemon as a subcommand of the standalone `packages/ccdash_cli/` package: `ccdash daemon {start,stop,status,logs}`.**

Rationale:

- The CLI is already pip-installable globally via `pipx install ccdash-cli` (per ADR-005 and the `ccdash-standalone-global-cli` work). Users who run remote CCDash already have this installed; daemon mode is a zero-additional-distribution-channel feature.
- The daemon's core logic (tail JSONL, batch, POST) is small (~300 LOC) and reuses the CLI's existing HTTP client (`packages/ccdash_cli/src/ccdash_cli/runtime/client.py`) for auth + retry + version negotiation.
- One language (Python) for the team. No Go/Rust toolchain to learn or CI to maintain.
- Lifecycle is delegated to the host OS's user-space supervisor (launchd on macOS, systemd `--user` on Linux, Task Scheduler on Windows). The CLI ships templated unit files but does **not** reinvent supervision.

The daemon does **not** become a new `RuntimeProfile` in `backend/runtime/profiles.py`. The runtime profile system is a server-side concept — what gets composed inside the FastAPI process. The daemon is a separate process living in the standalone CLI package and never imports `backend.runtime`.

## Decision Drivers

1. **Reuse existing distribution.** Users who care about remote CCDash already use the CLI. Adding a subcommand is one `pipx upgrade` away from being usable.
2. **Reuse existing HTTP client + auth.** The CLI's `client.py` already handles retry, timeout, and version negotiation. The daemon adds a tail loop + a buffered batcher on top of that, not a new HTTP stack.
3. **Single-language ops.** A Go binary would force the team to maintain a second build pipeline, second crash-reporting story, second cross-OS test matrix. Python is sufficient for ≥500 events/sec ingest (ADR-006 target) — `aiofiles` + `httpx` async POST handles this on a 2-core laptop.
4. **OS-native supervision wins.** launchd/systemd-user/Task Scheduler are battle-tested. CCDash should not write its own supervisor; it should ship installable plist/unit/scheduled-task templates.
5. **Smaller resource floor than (C).** Reusing `backend/runtime/` would pull in SQLAlchemy, Alembic, all repositories, OpenTelemetry — none of which the daemon needs. The CLI package is already lean (`httpx` + `typer` + Pydantic models). Target: <50MB RSS at idle; the CLI baseline is ~25MB.

## Alternatives Considered

### A. Standalone Go binary

**Pros**: One file, no Python runtime dependency, easier to ship signed binaries to enterprise users, lower idle RSS (~10MB).

**Cons**: A second language in the codebase. Separate CI for cross-OS builds. Separate crash-reporter integration. New code-signing pipeline (Apple notarization, Authenticode). Duplicates the auth/retry/version-negotiation logic that already exists in the Python CLI.

**Why rejected**: The cross-language burden is enormous for a team that does not yet have Go expertise on staff. The performance ceiling that would justify Go (>10K events/sec, <5MB RSS) is far above the v1 target. Revisit at v2 if scale requires it.

### B. Subcommand of `ccdash` CLI (chosen)

**Pros**: Uses installed CLI; reuses HTTP client; one language; one distribution; native `--help`, completion, JSON output via existing Typer infra; trivial integration tests via `CliRunner`.

**Cons**: Daemon process inherits the CLI's full Python startup (~150ms first run; one-time cost). Higher idle RSS than Go (~30MB vs ~10MB) but well under the 50MB target. Requires `pipx`/`pip` on the workstation (already a CCDash prerequisite).

### C. New `daemon` runtime profile in `backend/runtime/`

**Pros**: Maximum code reuse with the worker runtime — `FilesystemSource` already lives there.

**Cons**: Drags the entire backend dependency closure (SQLAlchemy, Alembic, OTEL exporters) onto every developer workstation. Conflates a server-side composition concept (runtime profile) with a client-side concept (daemon). Tightly couples the daemon's release cycle to the server's, defeating the cleanly separated CLI distribution.

**Why rejected**: This option violates the design-spec's principle that the daemon and server are independently versioned. It also bloats the workstation install footprint by an order of magnitude.

## Lifecycle Design

### Install

```bash
pipx install ccdash-cli            # already supported
ccdash daemon install               # writes platform-specific supervisor unit, prompts for token
```

`ccdash daemon install` will:
1. Read `--server-url`, `--workspace-token`, `--project-id` from flags or prompt.
2. Write config to `~/.config/ccdash/daemon.toml` (XDG-compliant).
3. Generate and install a supervisor unit:
   - **macOS**: `~/Library/LaunchAgents/io.ccdash.daemon.plist` + `launchctl bootstrap gui/$UID`.
   - **Linux**: `~/.config/systemd/user/ccdash-daemon.service` + `systemctl --user daemon-reload && systemctl --user enable --now ccdash-daemon`.
   - **Windows**: scheduled task `CCDash Daemon` registered via `schtasks` to run at logon.
4. Print the supervisor command for the operator to verify.

### Start / Stop / Status / Logs

```bash
ccdash daemon start          # foreground; for debugging only
ccdash daemon stop           # asks supervisor to stop
ccdash daemon status         # supervisor state + last batch ts + cursor lag (queried from server)
ccdash daemon logs           # tails the supervisor's log file (varies per platform)
```

`status` is the single most-used command. It returns: supervisor state (running/stopped/crashed), last successful batch timestamp, cursor lag against the server (from a `GET /api/v1/ingest/cursor/{workspace}` lookup), local buffer depth, and tail of the most recent error if any.

### Update

```bash
pipx upgrade ccdash-cli
ccdash daemon restart        # restart via supervisor; old process drains buffer first
```

A drain-on-shutdown flush attempts a final POST of any buffered events before exit. If the server is unreachable, events remain on disk for the next start.

### Uninstall

```bash
ccdash daemon uninstall      # disables supervisor unit, removes config, preserves on-disk buffer
```

## Resource Floor (Hard Gates from E2)

These are hard gates the implementation must hit; not measured in this SPIKE.

| Metric | Target | Notes |
|---|---|---|
| CPU at idle (no events for 60s) | < 1% on a 2024 M-series Mac | A tight loop is forbidden; daemon must use `inotify`/`fsevents` via `watchfiles`, not poll |
| RSS at idle (10 minutes after start) | < 50 MB | Validates that we did not pull a giant dependency closure |
| Duplicate events after forced network blip | 0 | Idempotency via `event_id`; server is the dedup authority (ADR-006) |
| Lost events after forced daemon restart (kill -9) | 0 | On-disk buffer is a write-ahead log: append-then-fsync-then-ack-flush |
| Cold start to first POST | < 2s | Acceptable for a supervised process |

## Consequences

### Positive

- Zero new distribution channel; users `pipx upgrade ccdash-cli` and gain a daemon.
- One Python codebase to maintain, test, and release.
- OS-native supervision is rock-solid; we do not own crash recovery.
- `ccdash daemon` commands integrate cleanly with the existing CLI help system and JSON output.

### Negative

- Idle RSS is ~3× a Go equivalent. Acceptable but not best-in-class.
- Python startup latency on first invocation is ~150ms (mitigated: daemon is supervised, so this is paid once).
- Windows-as-a-Service is not natively supported; we use Task Scheduler at logon, which means the daemon does not run when no one is logged in. Documented as a known limitation.

### Risks

| Risk | Mitigation |
|---|---|
| pipx not on developer workstation | `npm run setup` already installs Python deps for the repo CLI; stand-alone CLI ships a `make install` shortcut |
| Supervisor unit drift between OS versions | Pin a known-good template per OS major; integration test on the two latest macOS, the two latest Ubuntu LTS, Windows 11 |
| Token leaks in supervisor unit env | Token is **not** written into the unit file; daemon reads from `daemon.toml` (mode 0600) which is `chmod`'d on install. ADR-008 covers the secrets story. |
| Buffer grows unbounded if server is down for days | Daemon enforces a configurable on-disk buffer cap (default 500MB) and emits a desktop notification when 75% full |

## Related

- ADR-006 (transport)
- ADR-008 (auth)
- ADR-009 (sync engine port — daemon reuses the `FilesystemSource` logic)
- Standalone CLI: `packages/ccdash_cli/`, `packages/ccdash_contracts/`
- ADR-005 (CLI framework — Typer)
