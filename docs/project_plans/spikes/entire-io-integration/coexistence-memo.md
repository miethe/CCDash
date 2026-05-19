---
schema_version: 2
doc_type: spike
title: "Coexistence & Dedup Policy — Entire Sessions Alongside Native Source-of-Truth (SPIKE-B / RQ-8)"
status: completed
created: 2026-05-11
updated: 2026-05-11
completed_date: 2026-05-11
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/entire-io-integration-charter.md
parent_spike: docs/project_plans/spikes/entire-io-integration.md
related_documents:
  - docs/project_plans/adrs/adr-012-entire-session-identity-unification.md
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
---

# Coexistence & Dedup Policy — Entire Sessions Alongside Native Source-of-Truth

## 1. Problem

A developer running Claude Code (or any of the seven Entire-supported agents) inside an `entire`-enabled repo produces **two** artifacts for the same work:

1. The native agent transcript (e.g., Claude Code JSONL under `~/.claude/projects/<proj>/sessions/...`) — already ingested by CCDash via `FilesystemSource`.
2. An Entire checkpoint at `entire/checkpoints/v1/<xx>/<id>.json` — would be ingested by `EntireCheckpointSource`.

Unmanaged, this creates two CCDash session rows for the same underlying work. The user perceives this as a duplicate.

## 2. Policy: Provenance Over Dedup

**CCDash does not automatically dedup `fs:`-keyed and `entire:`-keyed sessions.** Each is a distinct artifact with distinct provenance:

- `fs:<rel-path>` is the **agent-native** record. It is the most complete record of what the agent did (it is what the agent itself wrote).
- `entire:<12-hex>` is the **Entire-curated** record. It carries the git-linkage trailer, the cross-agent normalized lifecycle, and the cross-session view that Entire constructs (e.g., session-to-commit-to-PR chains).

These views can disagree (Entire may elide tool outputs that the native JSONL keeps; the native JSONL doesn't carry Entire's commit trailer linkage). Forcibly merging them loses information. Two rows with clear provenance preserves both.

## 3. UI Provenance Surface

The `source_ref` chip already specified in SPIKE-A RQ-7 carries this provenance directly:

| `source_ref` prefix | Chip label | Tooltip |
|---|---|---|
| `fs:` | "Local" | "Parsed from agent transcript on disk" |
| `remote:` | "Daemon" | "Streamed from local daemon on `<hostname>`" |
| `entire:` | "Entire" | "Captured by Entire CLI, linked to commit `<short-sha>`" |

In the session list, when two rows share an obvious correspondence (same `sessionId` agent-side OR same `(agent, started_at±5s, project)` tuple), the list view stacks them under a single "Related" group with a disclosure caret. The grouping is **purely presentational** — both rows remain queryable independently.

## 4. Soft-Dedup Heuristics (for the Grouping UI Only)

Two sessions are "related" if **all** of the following hold:

- Same `project_id` and `workspace_id`.
- `agent.kind` (from Entire) matches `platform_type` (from native).
- `|started_at_fs - started_at_entire| < 5s`.
- `git_commit_hash` (when both populated) matches OR the Entire-side `repo.commits[]` contains the `git_commit_hash` of the fs-side row.

This is a UI affordance, not a uniqueness constraint. Heuristic failures (false negatives) result in two ungrouped rows — which is correct, since they may genuinely be different work. False positives are recoverable by the user via "ungroup" in the disclosure.

A future enhancement (out of v1 scope): teach `EntireCheckpointSource` to surface a `relates_to_fs_session_id` hint when the upstream agent emits the native session ID into a checkpoint field (Claude Code does this via `cwd` + transcript path; the schema permits storing it under `agentSpecific.claude-code.transcriptPath`).

## 5. Dual-Source Configuration Modes

Three deployment modes, controlled by env vars (additive to SPIKE-A's `CCDASH_REMOTE_INGEST_ENABLED`):

| Mode | `CCDASH_ENTIRE_INGEST_ENABLED` | `FilesystemSource` active | Effect |
|---|---|---|---|
| **Native only** (default) | `false` | yes | Today's behavior. No Entire ingest. |
| **Entire only** | `true` | no (operator sets `CCDASH_FILESYSTEM_SOURCE_ENABLED=false`) | Useful when the operator wants Entire to be the single source of agent truth. |
| **Both** | `true` | yes | Default for opt-in. Two rows per session; UI groups them. |

The "both" mode is the recommended default for opt-in, mirroring SPIKE-A's dual-source posture for `remote` + `fs`. Operators who care about row count flip to "Entire only" once they've validated parity.

## 6. Filter & Query Implications

The session-listing query already accepts a `source_ref` predicate per ADR-009. Adding `entire:` requires no schema change, but the UI filter dropdown grows:

- "All sources" (default)
- "Local only" (`source_ref LIKE 'fs:%'`)
- "Daemon only" (`source_ref LIKE 'remote:%'`)
- "Entire only" (`source_ref LIKE 'entire:%'`)

Saved filters from before this change continue to work — the new filter values are additive.

## 7. Migration & Cutover Posture

Operators who already trust their `FilesystemSource` may want to backfill from Entire **without** creating duplicates. This is a one-time admin operation, not a steady state:

1. Disable `FilesystemSource` temporarily.
2. Run `EntireCheckpointSource` backfill.
3. Re-enable `FilesystemSource` if running in "both" mode, or leave it off for "Entire only".

This is the same pattern SPIKE-A documented for `CCDASH_DUAL_SOURCE_INGEST` — the policy generalizes cleanly.

## 8. Open Items

- A future v2 may add a `session_correspondence` table that hard-links related rows (instead of soft-grouping by heuristic). Out of scope for v1.
- Cross-source merge of transcripts (one canonical transcript view aggregating both records) is the right long-term UX but is out of scope per SPIKE-B charter §5.
