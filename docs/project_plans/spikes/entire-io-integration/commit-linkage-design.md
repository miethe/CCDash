---
schema_version: 2
doc_type: spike
title: "Session ↔ Commit Linkage Design — session_commit_links (SPIKE-B / RQ-6)"
status: completed
created: 2026-05-11
updated: 2026-05-11
completed_date: 2026-05-11
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/entire-io-integration-charter.md
parent_spike: docs/project_plans/spikes/entire-io-integration.md
related_documents:
  - docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md
---

# Session ↔ Commit Linkage Design

## 1. Why this matters

Entire commits carry a trailer `Entire-Checkpoint: <12-hex-id>` pointing back at the checkpoint that produced them (charter §2). This gives CCDash a **free join** between agent sessions and git commits — and through git, to PRs. Concrete UX wins:

- "Which agent sessions produced PR #123?"
- "What was the model thinking when this regression landed?"
- "Show me every commit by Claude Code that touched `auth.py`."

CCDash today has `features` and `progress` models but no first-class session-to-commit join table. Adding one unlocks the questions above without changing existing models.

## 2. Schema sketch

```sql
CREATE TABLE session_commit_links (
    session_id    TEXT NOT NULL,
    commit_sha    TEXT NOT NULL,   -- 40-hex
    project_id    TEXT NOT NULL,
    workspace_id  TEXT NOT NULL,
    link_source   TEXT NOT NULL,   -- 'entire-trailer' | 'mtime-heuristic' | 'manual'
    detected_at   TEXT NOT NULL,   -- ISO-8601
    PRIMARY KEY (session_id, commit_sha, link_source),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX ix_session_commit_links_commit ON session_commit_links (commit_sha, project_id);
CREATE INDEX ix_session_commit_links_workspace ON session_commit_links (workspace_id);
```

Notes:
- `link_source` discriminates how the link was discovered. `entire-trailer` is the high-confidence path (deterministic from the trailer). `mtime-heuristic` is the existing CCDash inference (session ended ~at the time of the commit; same project). `manual` is reserved for future user-curated links.
- The `(session_id, commit_sha, link_source)` composite PK allows the **same** session-commit pair to appear from multiple sources without conflict (and lets the UI prefer the higher-confidence source).
- `ON DELETE CASCADE` on `session_id` keeps the table consistent if a session row is deleted.

## 3. No conflict with `session_mappings`

The existing `session_mappings` table (`backend/parsers/sessions.py` neighborhood) maps sessions to **features/tasks**, not to commits. The two are orthogonal — `session_commit_links` is purely the session ↔ git-commit join, while `session_mappings` is the session ↔ planning-artifact join.

Verified absence of overlap:
- `session_mappings` uses task/feature IDs, not commit SHAs.
- No existing repository method exists named `link_session_to_commit` or equivalent.
- `git_commit_hash` on `sessions` is a single-commit cache (the "ended-on" commit), not a many-to-many surface.

## 4. Population paths

| Source | When populated | `link_source` value |
|---|---|---|
| `EntireCheckpointSource` | At ingest, from `repo.commits[]` in the checkpoint (each commit listed there is linked to the session) | `entire-trailer` |
| Post-ingest backfill job | Sweeps the repo's commit log for `Entire-Checkpoint:` trailers and back-links to any session_id that matches; useful when CCDash starts ingesting Entire AFTER commits already exist | `entire-trailer` |
| Existing `mtime-heuristic` inference (already in CCDash but not persisted into a join table) | On `FilesystemSource` ingest, persist the inferred link into this table | `mtime-heuristic` |

The backfill job is a Phase 5 implementation task (`backend/scripts/backfill_session_commit_links.py`). It is idempotent (PK includes `link_source`; re-runs no-op).

## 5. UI affordances (top 3, prioritized)

1. **"Sessions for this commit" panel** (high value, low cost). In any UI that renders a commit (the new session inspector's commit chip, future PR view), surface a small list of related sessions. One query: `SELECT s.* FROM sessions s JOIN session_commit_links l ON s.id = l.session_id WHERE l.commit_sha = ? AND l.project_id = ?`.

2. **"Commits from this session" sidebar** (high value, low cost). On the session inspector, list all commits produced during the session. Renders the existing `git_commit_hashes_json` if present (already in `sessions` schema) OR the linked commits from `session_commit_links` if more authoritative.

3. **"Agent attribution" on commit hover** (medium value, medium cost). In any commit-list view, a small chip indicating which agent produced the commit (drawn from the linked session's `platform_type`). Useful for review workflows: "this PR is 80% Claude Code, 20% human."

Deferred to v2:
- PR-level rollups ("session X spans commits a..b which are PR #123") — requires GitHub/GitLab integration, out of v1 scope.
- Cross-project linkage ("this session shows up in two projects via shared dependencies") — niche.

## 6. Indexing & query cost

The two indexes above cover the dominant query patterns:
- `commit_sha → session_ids` (commit-centric views): primary key prefix.
- `session_id → commit_shas` (session-centric views): primary key suffix.
- `workspace_id` filtering: dedicated index.

Expected table size: one row per session-commit pair. A typical project has ~5k sessions over a year with ~3 commits per session = ~15k rows. Two SQLite indexes on a 15k-row table is negligible.

## 7. Hard gates

| Gate | Target |
|---|---|
| `EntireCheckpointSource` populates `session_commit_links` from `repo.commits[]` on every ingest | Integration test |
| Backfill job is idempotent (two runs ≡ one run) | Integration test |
| Cross-source dedup (same pair from both `entire-trailer` and `mtime-heuristic` results in two rows, both queryable) | Integration test |
| Cascade-delete behavior when a session is deleted | Integration test |
| Query latency for "sessions for commit X" on a 15k-row table | < 5ms | Micro-benchmark |

## 8. Out of scope for v1

- A `commits` first-class table (today commits live as opaque SHAs on session rows). RQ-6 explicitly does not propose one; the link table is sufficient for the three UI affordances above.
- Bidirectional cascade (deleting a commit removes its links) — git commits are immutable; no cascade needed.
- A `pull_requests` table — covered by future GitHub-integration scope.
