---
title: "ADR-011: Entire.io Ingest Path — Branch-Parse Primary, CLI-Wrap Fallback"
type: "adr"
status: "accepted"
created: "2026-05-11"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/spikes/entire-io-integration.md"
related_adrs:
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-012-entire-session-identity-unification.md
  - docs/project_plans/adrs/adr-013-entire-live-update-mechanism.md
tags: ["adr", "ingest", "entire", "git", "pygit2", "dulwich"]
---

# ADR-011: Entire.io Ingest Path — Branch-Parse Primary, CLI-Wrap Fallback

## Status

Accepted (SPIKE-B resolved 2026-05-11)

## Context

CCDash needs to ingest sessions captured by the [Entire.io CLI](https://github.com/entireio/cli) as a third implementation of the `SessionIngestSource` port defined in [ADR-009](./adr-009-session-ingest-source-port-and-cursor-table.md). The charter (RQ-2) enumerates three candidate ingest paths:

1. **Branch-parse** — Read `entire/checkpoints/v1` directly from the local git repo using a Python git library (pygit2 or dulwich). Treats checkpoints as data-at-rest in git objects.
2. **CLI-wrap** — Shell out to the `entire` Go binary (`entire status`, `entire show <id>`, etc.) and parse its stdout.
3. **Hybrid** — Branch-parse as the default; CLI-wrap for operations the parser cannot perform directly (e.g., resolving shadow-branch transcripts that have been pruned locally).

The decision constrains: how robust ingest is to upstream changes, latency, whether a Go binary must be present on the CCDash host, and how much code lives in CCDash vs delegated to upstream.

## Decision

Adopt **branch-parse as the primary path**, with a **CLI-wrap escape hatch** behind a feature flag for the narrow set of operations that branch-parse cannot serve.

- **Library choice for branch-parse:** `pygit2` primary, `dulwich` pure-Python fallback. The `EntireCheckpointSource` exposes a single `GitReader` interface with both implementations registered; selection is per-platform at runtime, controlled by `CCDASH_ENTIRE_GIT_BACKEND=auto|pygit2|dulwich` (default `auto`: try pygit2, fall back to dulwich on import failure).
- **CLI-wrap is opt-in.** Off by default. Enabled via `CCDASH_ENTIRE_CLI_WRAP_ENABLED=true`. Used only when the entire binary is detected on `$PATH` AND a branch-parse operation has surfaced a known fallback condition (e.g., shadow-branch GC). Never used as the primary read path.
- **No hybrid-by-default.** Two code paths with conditional dispatch is more maintenance surface than the rare fallback warrants. Operators who hit fallback conditions flip the flag explicitly.

## Decision Matrix

Scored on 0–5 scale across seven criteria; higher is better. Weights reflect priority for v1 (upstream-resilience and platform-portability dominate; speed is a bounded concern given Phase 5 latency budgets).

| Criterion (weight) | Branch-parse (pygit2) | Branch-parse (dulwich) | CLI-wrap |
|---|---|---|---|
| Upstream-break resilience (w=3) | 4 (depends only on branch layout + JSON shape) | 4 | 2 (depends on CLI output format, which may change without semver) |
| Cross-platform reliability (w=3) | 3 (pygit2 has libgit2 native-build complexity on Windows) | 5 (pure Python) | 3 (Go binary must be installed + on PATH; Windows code-signing) |
| Latency (cold parse 1k checkpoints) (w=2) | 5 (libgit2 C; expected sub-second) | 3 (pure Python; ~3–10× slower) | 2 (process spawn per call dominates) |
| Dependency footprint (w=2) | 3 (libgit2 native dep; install fragility) | 5 (pip install dulwich; nothing else) | 2 (Go binary installed via brew/scoop/install.sh; not pip-installable) |
| Auth surface (w=2) | 5 (none — reads local git objects) | 5 | 4 (binary may itself require config for some ops) |
| Code we own vs delegate (w=1) | 3 (we own the JSON parser and the git read) | 3 | 4 (less code in CCDash; more delegated to upstream) |
| Debuggability (w=2) | 4 (in-process; stack traces in Python) | 4 | 2 (out-of-process; debugging crosses a language boundary) |
| **Weighted total** | **52** | **53** | **34** |

dulwich edges out pygit2 by 1 point on portability, but pygit2 wins decisively on latency. The combined "pygit2 primary, dulwich fallback" approach captures both — pygit2 where libgit2 builds cleanly (macOS Homebrew, most Linux distros), dulwich everywhere else (Windows, locked-down corporate Macs, ARM Linux without prebuilt wheels).

CLI-wrap scores low across the board. It is retained as an escape hatch because the alternatives for shadow-branch pruning recovery (re-fetching the shadow branch ourselves, asking the user to run a CLI command manually, declaring the transcript permanently lost) are all worse than the rare opt-in CLI shell-out.

## Hard Gates (E1 acceptance criteria for Phase 5)

| Gate | Target | Verified by |
|---|---|---|
| Cold-parse for 1,000 checkpoints (pygit2) | < 15s on M-series Mac equivalent | E1-PERF micro-benchmark in Phase 5 |
| Cold-parse for 1,000 checkpoints (dulwich) | < 60s (4× pygit2 budget) | E1-PERF |
| Peak memory for 1k-checkpoint cold parse | < 200 MB (either backend) | E1-PERF |
| Backend auto-selection: import pygit2 → use it; ImportError → dulwich | 100% — no manual config needed | unit test |
| Malformed-JSON checkpoint handling | Dead-lettered (parity with SPIKE-A F-5); other checkpoints in the same batch unaffected | integration test |
| Missing-branch handling (project has no `entire/checkpoints/v1`) | Source reports zero events; no error; cursor unchanged | unit test |
| Partial-fetch handling (shallow clone) | Source detects missing objects, surfaces operator-visible warning, skips affected checkpoints, continues | integration test |
| Windows + dulwich smoke test | Single checkpoint parse succeeds end-to-end | CI matrix |

If pygit2 cold-parse misses the 15s target by >2×, **reassess** at the Phase 5 gate. The fallback options in order: (a) ship dulwich-only if the gap is library-overhead-driven, (b) move to CLI-wrap primary (lower placement on this ADR), (c) descope live-update cadence (ADR-013) to stay within UX target.

## Transcript Resolution Policy (RQ-5)

Transcripts can be MBs per session and live behind `<ref>` objects in the checkpoint schema (see [checkpoint-schema.md §3.6](../spikes/entire-io-integration/checkpoint-schema.md#36-transcript-references)). Three modes were evaluated:

| Mode | Storage cost | First-render latency | Offline UX | Operational complexity |
|---|---|---|---|---|
| **Eager** (fetch all transcripts at ingest, persist into CCDash DB) | High — multi-MB per session × thousands of sessions | None — already in DB | Perfect | Low |
| **Lazy** (store pointer at ingest; fetch on UI open) | Low | Variable — single-digit seconds for git-blob reads, longer for missing-shadow-branch | Degraded if shadow branch is gone | Medium |
| **Git-native** (store pointer; resolve via the same `GitReader` per request) | Low | Comparable to lazy | Same as lazy | Low — reuses the read path |

**Decision: git-native pointer with lazy resolution.** Persist the `<ref>` object verbatim in `session_forensics_json` and resolve transcripts through the `GitReader` on demand. This:

- Avoids the storage blow-up of eager fetch.
- Reuses the read path that already validates the branch and handles missing objects.
- Gives a clear escalation path for the "shadow branch pruned" case: surface a UI affordance ("transcript no longer available locally; rerun `entire fetch <id>` to recover").

A **soft cap**: if a transcript exceeds 5 MB, the lazy fetch streams to a temp file and serves with `Content-Range` support rather than loading into memory. This is a Phase 6 implementation detail, not a SPIKE-gate requirement.

## Consequences

### Positive

- Zero new runtime dependency on a Go binary in the common case.
- pygit2's C speed when available; pure-Python fallback ensures CCDash installs cleanly on every platform CCDash already supports.
- Transcript storage cost is bounded — CCDash DB does not grow with transcript volume.
- The escape hatch exists, but the default path does not invoke it; auditing reveals exactly when CLI-wrap is used (one flag, one metric).

### Negative

- Two library implementations to maintain (pygit2 and dulwich). Mitigated by the shared `GitReader` interface; the actual surface is small (open repo, resolve ref, read blob, list tree).
- Branch-layout drift in upstream (e.g., re-sharding) breaks ingest entirely. Mitigated by the schema versioning policy in [checkpoint-schema.md §5](../spikes/entire-io-integration/checkpoint-schema.md#5-schema-stability--versioning-posture) and the operator-visible metric `ingest_schema_warning_total{event_type="branch-layout"}`.
- Transcript availability depends on shadow-branch retention, which Entire controls. The lazy-with-pointer model degrades gracefully but cannot recover what Entire pruned.

### Risks & Mitigations

| Risk | Mitigation |
|---|---|
| libgit2 wheel unavailable for a user's platform | dulwich fallback via `CCDASH_ENTIRE_GIT_BACKEND=auto` |
| Upstream CLI output format used by escape-hatch changes without notice | Escape hatch is opt-in; failure to invoke surfaces the underlying branch-parse error, not a silent fallback |
| Large transcripts pulled inadvertently into LLM context (UI shows transcript verbatim) | Per-transcript size soft cap (5 MB stream) + UI virtualization; same constraint as today's JSONL viewer |

## Alternatives Considered

1. **CLI-wrap primary.** Rejected. Adds a runtime Go-binary dependency that breaks CCDash's existing "pipx install and go" UX. Out-of-process latency is a hard ceiling on Phase 3's live-ingest cadence (ADR-013).
2. **Hybrid by default.** Rejected. Two code paths with conditional dispatch is a maintenance trap; the rare fallback does not justify always-on dual-implementation cost.
3. **Wait for an upstream consumer API.** Rejected. The grounding brief (charter §2) explicitly notes "no documented third-party consumer API" exists. Branch-parse is the de facto contract upstream is committing to by versioning the branch path `v1`.

## Related

- ADR-009 (port that this source implements)
- ADR-012 (session identity for `entire:` source-ref URIs)
- ADR-013 (live-update mechanism — informs how often we invoke the read path)
- Checkpoint schema: `docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md`
- Charter: `docs/project_plans/spikes/entire-io-integration-charter.md`
