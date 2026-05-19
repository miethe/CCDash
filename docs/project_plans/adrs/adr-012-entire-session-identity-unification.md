---
title: "ADR-012: Entire.io Session Identity — Reuse ADR-009 source_ref with entire: Scheme"
type: "adr"
status: "accepted"
created: "2026-05-11"
parent_prd: "docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md"
depends_on_spike: "docs/project_plans/spikes/entire-io-integration.md"
related_adrs:
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-011-entire-ingest-path-decision.md
tags: ["adr", "schema", "identity", "entire", "migration"]
---

# ADR-012: Entire.io Session Identity — Reuse ADR-009 `source_ref` with `entire:` Scheme

## Status

Accepted (SPIKE-B resolved 2026-05-11)

## Context

The SPIKE-B charter (RQ-4) anticipates a session-identity schema change to accommodate Entire checkpoints, which have no filesystem path. The charter language proposes a `source_type` enum column plus `external_id` plus updated uniqueness constraints.

[ADR-009](./adr-009-session-ingest-source-port-and-cursor-table.md), accepted as part of SPIKE-A, has already resolved this with a different (compatible, simpler) shape: a single `source_ref` column carrying URI-scheme values (`fs:<rel-path>`, `remote:<workspace>:<event-id>`, `entire:<checkpoint-hex>`), with upsert key `(project_id, workspace_id, source_ref)`. ADR-009 is `accepted`.

This ADR's job is to **resolve the charter language vs ADR-009 conflict** and freeze the Entire-side identity contract.

## Decision

**ADR-009 wins. There is no `source_type` enum and no separate `external_id` column.** The Entire integration uses ADR-009's `source_ref` column with the URI scheme:

```
entire:<12-hex checkpoint id>
```

The charter's language about `source_type` and `external_id` is **explicitly superseded** by this ADR. No new columns are added beyond what ADR-009 specifies.

### Why the URI scheme wins over the enum + external_id

| Concern | URI scheme (ADR-009) | Enum + external_id (charter draft) |
|---|---|---|
| Adding a fourth source later (e.g., GitHub Copilot Workspace) | Add a new scheme prefix; one parser change | Add an enum value (migration); decide what `external_id` means for it |
| Querying "all sessions from source X" | `WHERE source_ref LIKE 'entire:%'` | `WHERE source_type = 'entire_checkpoint'` |
| Forgetting to set the source discriminator | Impossible — the prefix IS the discriminator | Easy — `source_type` and `external_id` can drift |
| Forward-compat with hierarchical sources (e.g., `entire:<workspace>:<id>` if Entire ever workspaces checkpoints) | Trivial — add a path segment | Requires schema change |
| Cost in CCDash query code | Zero — single column predicate | Two predicates, both must agree |

The URI shape is also already in use by other tools (Datadog source URIs, OpenTelemetry resource attributes), so reviewers recognize the pattern.

### Sessions row layout for Entire-ingested sessions

| Column | Value |
|---|---|
| `id` | `sessionId` from checkpoint (`YYYY-MM-DD-<UUID>`) — globally unique |
| `source_ref` | `"entire:" + checkpoint.id` (e.g., `entire:a3b2c4d5e6f7`) |
| `source_file` | NULL — column tolerated as nullable for non-fs sources |
| `project_id` | Resolved from `repo.remoteUrl` against `projects.json` mapping; falls back to active request binding |
| `workspace_id` | From `AuthContext.workspace_id` (ADR-008) |
| `platform_type` | Mapped from `agent.kind` (see [checkpoint-schema.md §6](../spikes/entire-io-integration/checkpoint-schema.md#6-ccdash-mapping-crib-sheet)) |
| Remaining columns | Populated per the schema crib sheet |

### `source_file` nullability

ADR-009 preserves `source_file` for backwards compatibility. To accommodate `entire:` (and `remote:`) sources, `source_file` must become **nullable**.

- Migration: `ALTER TABLE sessions ALTER COLUMN source_file DROP NOT NULL;` (SQLite: rewrite via the standard 12-step pattern; PostgreSQL: direct).
- Audit: every call site that reads `source_file` for non-display purposes must tolerate NULL. The grep is small (`backend/db/repositories/sessions.py`, `backend/services/source_identity.py`, a handful of UI render paths). All are display-or-debug uses; no business logic depends on it being non-null.

### Cursor & ingest-source identity

`ingest_cursors` rows for Entire ingestion:

| Column | Value |
|---|---|
| `source_id` | `"entire"` (matches `EntireCheckpointSource.source_id` literal) |
| `project_id` | Per-project (one cursor per project per workspace) |
| `workspace_id` | Per-workspace |
| `last_cursor` | `"<branch-commit-sha>:<checkpoint-id>"` — branch commit advances when `entire/checkpoints/v1` is fetched; checkpoint id disambiguates within a single commit (one commit can produce multiple checkpoint files if multiple sessions ended simultaneously) |
| `last_ingest_at` | RFC3339 timestamp at successful upsert |

The cursor format is opaque to the engine (per ADR-009 contract); only the source parses it. The colon-separated shape is chosen so `cursor.split(":")` is unambiguous (12-hex IDs don't contain colons; 40-hex commit SHAs don't either).

## Migration Strategy (Alembic Sketch)

The migration is **additive to ADR-009's migration** — ADR-009 already adds `source_ref` and the cursor table. ADR-012 adds only:

```python
# Alembic upgrade
def upgrade():
    # Make source_file nullable to accommodate non-fs sources.
    # SQLite: requires table rewrite (12-step pattern); use batch_alter_table.
    with op.batch_alter_table('sessions') as batch:
        batch.alter_column('source_file', existing_type=sa.Text(), nullable=True)

    # Add a partial unique index for source_file when present.
    # Preserves the historical guarantee for filesystem sources without
    # constraining new non-fs sources.
    op.create_index(
        'ix_sessions_source_file_unique',
        'sessions',
        ['project_id', 'workspace_id', 'source_file'],
        unique=True,
        sqlite_where=sa.text('source_file IS NOT NULL'),
        postgresql_where=sa.text('source_file IS NOT NULL'),
    )

def downgrade():
    op.drop_index('ix_sessions_source_file_unique')
    # Backfilling source_file from source_ref for entire: rows is lossy
    # (12-hex id is not a filesystem path); downgrade is best-effort:
    # entire: sessions are deleted on downgrade.
    op.execute("DELETE FROM sessions WHERE source_ref LIKE 'entire:%'")
    with op.batch_alter_table('sessions') as batch:
        batch.alter_column('source_file', existing_type=sa.Text(), nullable=False)
```

### Backfill plan

No backfill is required for existing rows — they all have non-null `source_file` and ADR-009's earlier migration already populated `source_ref = "fs:" + source_file` for them.

### Zero-downtime story

- The migration is single-statement (column nullability + partial index). Lock window is sub-second on SQLite, milliseconds on PostgreSQL.
- No application code change is required at deploy time; the new code paths (`EntireCheckpointSource`) ship behind the existing feature flag `CCDASH_REMOTE_INGEST_ENABLED` and a new `CCDASH_ENTIRE_INGEST_ENABLED` flag. Both default off.
- Rollback is reversible up to the point that the first `entire:` row is written. After that, downgrade deletes Entire rows (as scripted above).

### Impact on existing queries

Audit of read paths that touch `source_file`:

| File | Use of `source_file` | NULL impact |
|---|---|---|
| `backend/db/repositories/sessions.py:84` (upsert) | Excluded from `ON CONFLICT` after this ADR; written as `excluded.source_file` (NULL pass-through) | None |
| `backend/services/source_identity.py` | Used to compute display name | Fallback to `source_ref` already in scope per ADR-009 |
| Frontend session inspector | Renders path when present | Already conditional on truthy value |
| `backend/db/sync_engine.py` | Uses for filesystem cursor only | Not touched by Entire path |

No query needs structural change; one line of source-identity display fallback is the only delta beyond migration.

## Hard Gates

| Gate | Target |
|---|---|
| Pre-existing `sessions` rows: `source_file` populated AND `source_ref = 'fs:' + source_file` | 100% post-migration |
| New Entire rows: `source_ref LIKE 'entire:%'` AND `source_file IS NULL` | 100% |
| `(project_id, workspace_id, source_ref)` is unique | Enforced by ADR-009 index |
| `(project_id, workspace_id, source_file)` is unique WHERE `source_file IS NOT NULL` | Enforced by new partial index |
| All existing session-listing tests pass without modification | 100% — zero diff |
| Cross-source listing query (`WHERE source_ref LIKE 'entire:%' OR source_ref LIKE 'fs:%'`) returns expected sessions | Integration test required |

## Coexistence with Other Sources

A single CCDash project may host sessions from all three source schemes simultaneously:

- `fs:<rel-path>` — local filesystem JSONL parsed by `FilesystemSource`
- `remote:<workspace>:<event-id>` — daemon-streamed by `RemoteIngestSource`
- `entire:<12-hex-id>` — checkpoint by `EntireCheckpointSource`

The same underlying session (e.g., a Claude Code session) may produce rows under both `fs:` and `entire:`. **No automatic dedup.** Each is a distinct artifact with distinct provenance. Soft-dedup heuristics and UI provenance labeling live in the [coexistence memo](../spikes/entire-io-integration/coexistence-memo.md).

## Consequences

### Positive

- One identity contract across three sources. Future sources slot in by registering a new URI scheme; no schema change.
- No conflict with ADR-009; this ADR is purely additive.
- Migration is single-statement; rollback is bounded.
- The charter language is explicitly reconciled — no ambiguity for downstream implementers.

### Negative

- Implementers reading the charter without this ADR may write code expecting a `source_type` column. Mitigated by linking this ADR from the charter (done) and from the deliverables checklist.
- `source_file` becomes nullable, which means a few display paths need a `source_ref`-based fallback. Cost is small (already required by ADR-009 for `remote:` sources).

### Risks

| Risk | Mitigation |
|---|---|
| URI parsing bugs (e.g., a path containing `:`) | Schemes are restricted to `fs|remote|entire`; the colon after the scheme is the only structurally significant one. Document and enforce in a tiny parsing helper. |
| Charter readers miss this reconciliation | Update the charter to flag ADR-009 + ADR-012 as the authoritative identity contract (done as part of SPIKE-B). |

## Alternatives Considered

1. **Add `source_type` enum and `external_id` as the charter draft proposed.** Rejected — it introduces two columns whose values must agree, and ADR-009 already covers the same ground with one column. Re-litigating ADR-009 is out of scope per SPIKE-B charter §8.
2. **Use `id` as the discriminator (Entire checkpoint IDs are unique).** Rejected — `id` already carries the agent-side session ID (`YYYY-MM-DD-<UUID>`), which is the natural primary key. Overloading it with the discriminator loses information.
3. **Add an `entire_checkpoint_id` column to `sessions`.** Rejected — per-source columns proliferate; the same anti-pattern would force a `remote_event_id` column when adding `RemoteIngestSource`. ADR-009's URI scheme avoids this trap.

## Related

- ADR-009 (the identity contract this ADR honors)
- ADR-011 (ingest path; provides the read mechanism)
- ADR-013 (live-update mechanism; provides cursor advancement cadence)
- Checkpoint schema: `docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md`
- Coexistence memo: `docs/project_plans/spikes/entire-io-integration/coexistence-memo.md`
