# Entity Linking Developer Reference

Last updated: 2026-02-18

This document is the implementation-level reference for linking across app entities.

## Entity Model

Core entities and storage tables:

- `Project` -> active project config and source paths.
- `Session` -> `sessions`, `session_logs`, `session_file_updates`, `session_artifacts`.
- `Document` -> `documents`.
- `Task` -> `tasks` (from progress frontmatter).
- `Feature` -> `features`, `feature_phases`.
- `EntityLink` -> `entity_links` (auto/manual relationships).

Primary edge types in current system:

- `feature -> task`
- `feature -> session`
- `document -> feature`

## Entity-by-Entity Responsibilities

| Entity | Primary table(s) | Parser/source | Outgoing links | Core resolver |
| --- | --- | --- | --- | --- |
| `Project` | `projects` | configured roots | scope for all parsing | `SyncEngine.sync_project` |
| `Document` | `documents` | `backend/parsers/documents.py` | `document->feature` | frontmatter + `feature_slug_from_path` |
| `Feature` | `features`, `feature_phases` | `backend/parsers/features.py` | `feature->task`, `feature->session` | base slug + constrained aliases |
| `Task` | `tasks` | progress parser/frontmatter tasks | (indirect in UI, direct to feature in links) | progress directory feature slug |
| `Session` | `sessions`, `session_logs`, `session_file_updates`, `session_artifacts` | session JSONL parser | `session<->feature` view relations via `entity_links` | command/file signal scoring |
| `EntityLink` | `entity_links` | rebuild stage | all graph edges | `_rebuild_entity_links` |

## Pipeline Entry Points

- Full sync orchestrator:
  - `backend/db/sync_engine.py:219`
- Link rebuild stage:
  - `backend/db/sync_engine.py:569`
- Feature linked sessions API:
  - `backend/routers/features.py:424`
- Session linked features API/model use:
  - `backend/routers/api.py:158`

## Linking Utilities (Canonical Rules)

Shared utility module:

- `backend/document_linking.py`

Key functions:

- Path normalization:
  - `normalize_ref_path` (`backend/document_linking.py:104`)
- Feature token validation:
  - `is_feature_like_token` (`backend/document_linking.py:145`)
- Feature extraction from path (supports nested plan and progress structures):
  - `feature_slug_from_path` (`backend/document_linking.py:195`)
- Alias extraction from path:
  - `alias_tokens_from_path` (`backend/document_linking.py:272`)
- Frontmatter reference extraction:
  - `extract_frontmatter_references` (`backend/document_linking.py:345`)

Important behavior:

- Frontmatter parsing now rejects noisy free text that only incidentally contains `/`.
- Feature refs are derived from explicit relation keys + valid feature-like tokens.
- Progress feature mapping prefers progress parent directory (`.../progress/{feature}/...`).

## Documents -> Features

Document parsing:

- `backend/parsers/documents.py:78`

Feature discovery and doc augmentation:

- `scan_features` (`backend/parsers/features.py:586`)
- Auxiliary doc scan (`backend/parsers/features.py:497`)
- Feature alias set (`backend/parsers/features.py:547`)
- Doc match predicate (`backend/parsers/features.py:562`)

Current matching strategy:

- Seed features from implementation plans.
- Enrich with PRDs and progress docs.
- Augment with auxiliary docs only when feature base slug/path-derived feature slug aligns.
- No transitive alias snowballing during augmentation.

## Features -> Sessions

Session evidence linking is built in `_rebuild_entity_links`:

- Feature evidence set construction:
  - `backend/db/sync_engine.py:914`
- Candidate signal collection and command/path checks:
  - `backend/db/sync_engine.py:1159`
- Confidence computation:
  - `backend/db/sync_engine.py:688`
- Candidate title derivation from candidate evidence:
  - `backend/db/sync_engine.py:720`

Guardrails now enforced:

- Paths contribute only when their extracted feature slug matches the candidate feature.
- Doc/related/prd alias ingestion is constrained to matching feature base.
- Command path matching rejects command paths that clearly map to another feature.
- `/dev:quick-feature` and `/recovering-sessions` use adjusted weighting for ambiguity handling.
- Global command-hint boosting is disabled (`has_command_hint=False` in scoring).

Session-title guardrail:

- Title derivation prefers feature slug resolved from candidate evidence paths.
- Falls back only when evidence-based slug resolution is unavailable.

## Document -> Feature Links

Document-level auto links are resolved from frontmatter and inferred feature slugs:

- `backend/db/sync_engine.py:1336`

Rules:

- Candidate refs from `linkedFeatures`, parsed `featureRefs`, and `prd`.
- `feature_slug_from_path` is applied when ref is path-like.
- Non feature-like tokens are ignored.
- Base-slug expansion allows versioned variants.

## Title Semantics

Session titles shown in feature/session views are not raw link keys.

- Link metadata title generation:
  - `backend/db/sync_engine.py:720`
- View-layer session metadata title fallback:
  - `backend/routers/features.py:186`
  - `backend/routers/api.py:139`

Design intent:

- Prefer summary/custom titles when present.
- Prefer evidence-resolved feature slug over candidate feature fallback.
- Avoid random feature labels when evidence points elsewhere.

## Why Many Features Can Have Zero Sessions

With stricter mapping, no link is created unless evidence is sufficiently feature-specific.

Common causes:

- No matching command args/path evidence in sessions.
- Planning docs exist but no execution sessions touched those files.
- Generic or unrelated file activity in sessions.
- Ambiguous quick-feature sessions without explicit feature path.

Observed current state: `73/89` features have at least one linked session; `16/89` have none.

## Operational Diagnostics

Audit script:

- `backend/scripts/link_audit.py`

Typical usage:

- Global: `python backend/scripts/link_audit.py --db data/ccdash_cache.db --limit 50`
- Per feature: `python backend/scripts/link_audit.py --db data/ccdash_cache.db --feature <feature-id> --limit 50`

Rebuild workflow:

- Full forced rebuild from Python (`SyncEngine.sync_project(..., force=True)`) or API rescan route.

Observability + control APIs:

- `GET /api/cache/status`
- `GET /api/cache/operations`
- `GET /api/cache/operations/{operation_id}`
- `POST /api/cache/sync`
- `POST /api/cache/rebuild-links`
- `POST /api/cache/sync-paths`
- `GET /api/links/audit` (alias: `GET /api/cache/links/audit`)

Detailed API usage doc:

- `docs/sync-observability-and-audit.md`

## Tests

Relevant test files:

- `backend/tests/test_document_linking.py`
- `backend/tests/test_sync_engine_linking.py`
- `backend/tests/test_features_router_links.py`
- `backend/tests/test_features_router_linked_sessions.py`
- `backend/tests/test_sessions_api_router.py`

Added/validated focus areas:

- Feature slug extraction from nested doc/progress paths.
- Rejection of free-text slash tokens as feature refs.
- Command parsing and prioritization behavior.

## Extension Points

When tuning further, keep these invariants:

- Do not add aliases from non-feature-like tokens.
- Prefer deterministic path-derived feature mapping over fuzzy title heuristics.
- Keep quick-feature logic conservative unless manual mapping exists.
- Add tests for every new heuristic branch.

Suggested future enhancement:

- Add explicit manual mapping table for ambiguous quick-feature sessions.
- Surface “unlinked but likely related” as suggestions (not auto-links).
- Add entity-level link confidence thresholds configurable per command class.

## Link Audit Feedback Loop

Recommended tuning cycle:

1. Run full rebuild.
2. Export audit sample (`backend/scripts/link_audit.py`) for suspicious links.
3. Review with labeling CSV (`KEEP`, `NOISE`, `UNCERTAIN`).
4. Tune only deterministic path/token logic first.
5. Rebuild and compare feature coverage + suspect counts.

This keeps precision high without reintroducing cross-feature alias bleed.
