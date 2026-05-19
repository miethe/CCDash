---
schema_version: 2
doc_type: spike
title: "Upstream Feedback Memo — Entire.io CLI Items to Raise (SPIKE-B / RQ-7, E5)"
status: completed
created: 2026-05-11
updated: 2026-05-11
completed_date: 2026-05-11
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/entire-io-integration-charter.md
parent_spike: docs/project_plans/spikes/entire-io-integration.md
---

# Upstream Feedback Memo — Items to Raise with entireio/cli

## Scope

Items SPIKE-B identified that warrant either (a) a public upstream discussion, (b) a feature request issue, or (c) deferred consideration. CCDash does not block on any of these; v1 ships with branch-parse + fs-watch and is robust to all of them being declined.

## 1. Read-side Consumer API for Checkpoint Events (Feature Request — Medium Priority)

**Context.** The Agent Hooks system is a write-side integration: external agents register so their sessions are captured into Entire. There is no documented read-side surface for "subscribe to new checkpoints" — third-party tools (like CCDash) currently read by polling the `entire/checkpoints/v1` branch.

**Ask.** A documented hook for "checkpoint written" that fires after `entire` commits to the checkpoints branch. Reasonable shapes:
- A shell exec hook the user configures in `entire configure`, called with the checkpoint ID on each write.
- A local Unix socket / named pipe that emits a one-line JSON event per write.
- A REST/SSE endpoint when running `entire daemon` (if one exists).

**Why CCDash cares.** Polling p50 latency (ADR-013) is ~15s at the default 30s interval. A push event would cut that to <1s and eliminate the polling CPU/network cost in cross-machine deployments.

**Action.** File issue or discussion at `entireio/cli`. Reference: ADR-013 §Why not the upstream-hook path.

## 2. Branch Layout Stability Statement (Documentation Request — Medium Priority)

**Context.** The `entire/checkpoints/v1` branch path is `v1`-versioned, implying schema/layout stability. But there is no public statement of:

- What constitutes a v1-incompatible change (just JSON fields? Or also sharding scheme / branch path / file extension?).
- What the deprecation timeline is when v2 ships.
- Whether v1 will continue to be written in parallel during a v1→v2 transition.

**Ask.** A `BRANCH_LAYOUT.md` or similar doc that commits to:
- The sharding scheme (first-2-chars of 12-hex ID, JSON file extension).
- A semver-style policy on the JSON schema (additive fields are minor; removals/renames are major).
- A 6-month dual-write window during major version bumps.

**Why CCDash cares.** ADR-011 and the checkpoint schema doc commit to forward-compat behavior on unknown fields. A formal stability statement upstream lets CCDash sharpen the dead-letter vs warn-and-strip threshold.

**Action.** Open a `docs:` issue at `entireio/cli`.

## 3. Telemetry Opt-Out Env Var Surfacing (Documentation Request — Low Priority)

**Context.** Per privacy memo §3, the exact name of the telemetry-opt-out env var is not surfaced in `entire --help`. Operators have to dig into upstream source or community docs.

**Ask.** Include the telemetry-opt-out env var name in `entire --help` output and `entire status` output (current state shown).

**Why CCDash cares.** Lets CCDash operator docs link to a canonical surface rather than guessing or pinning to a version-specific blog post.

**Action.** Open a docs-or-UX issue at `entireio/cli`.

## 4. Stable agent.kind Enum (Documentation Request — Low Priority)

**Context.** The seven supported agents (`claude-code`, `codex`, `gemini`, `opencode`, `cursor`, `factoryai-droid`, `copilot-cli`) are documented in marketing materials but not in a canonical enum reference inside the repo (or, if they are, the SPIKE didn't surface it).

**Ask.** A `docs/agents.md` (or equivalent) enumerating the canonical `agent.kind` values and mapping each to its native transcript format / hook source.

**Why CCDash cares.** Drives the mapping table in [checkpoint-schema.md §6](./checkpoint-schema.md#6-ccdash-mapping-crib-sheet). Today CCDash will hard-code based on reverse-engineering.

**Action.** Open a docs issue.

## 5. Shadow-Branch Retention Policy (Documentation Request — Low Priority)

**Context.** Shadow branches `entire/<sessionID>-<worktreeID>` hold ephemeral working state and transcripts. CCDash's lazy transcript resolution (ADR-011) depends on them being present at read time. Their retention policy is not documented.

**Ask.** A documented retention default (e.g., "kept until session ends + 30 days" or "until `entire gc` is run") and an env var to control it.

**Why CCDash cares.** Sets expectations for the "transcript no longer available locally" UI affordance CCDash will surface.

**Action.** Open a discussion thread.

## 6. Items NOT to Raise

To respect upstream's roadmap focus and avoid noise:

- **Cloud-Entire integration.** Out of scope per SPIKE-B charter §5.
- **Bidirectional sync (CCDash writes to Entire).** Out of scope per SPIKE-B charter §5.
- **Schema additions specifically for CCDash's data model.** CCDash adapts to upstream; the reverse is presumptuous.

## 7. Tracking

All filed issues should be linked back here. If issues are filed, add a `## Filed Issues` section with `(issue-url, status, last-updated)` rows. Phase 5 implementation owner is responsible for revisiting this memo before the EntireCheckpointSource lands — any issue closed favorably may shrink the v1 surface.
