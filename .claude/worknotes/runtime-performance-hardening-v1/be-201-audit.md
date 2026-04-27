# BE-201 Audit: EntityLinksRepository — rebuild_for_entities existence check

**Date**: 2026-04-27
**Auditor**: Data Layer agent (BE-201, Phase 2 of runtime-performance-hardening-v1)

---

## Files Examined

- `backend/db/repositories/links.py` — compatibility shim only; re-exports from two modules
- `backend/db/repositories/entity_graph.py` — actual `SqliteEntityLinkRepository` implementation
- `backend/db/sync_engine.py` — `SyncEngine.rebuild_links()` and `SyncEngine._rebuild_entity_links()`

---

## Existing Method Signatures

### `SqliteEntityLinkRepository` (entity_graph.py)

```python
async def upsert(self, link_data: dict) -> int
async def get_links_for(self, entity_type: str, entity_id: str, link_type: str | None = None) -> list[dict]
async def get_tree(self, entity_type: str, entity_id: str) -> dict
async def delete_auto_links(self, source_type: str, source_id: str) -> None
async def delete_link(self, source_type, source_id, target_type, target_id, link_type="related") -> None
async def delete_all_for(self, entity_type: str, entity_id: str) -> None
```

No `rebuild_for_entities`, no bulk/batch rebuild, no method that accepts a list of IDs.

### `SyncEngine` (sync_engine.py) — related but not on the repository

```python
async def rebuild_links(
    self,
    project_id: str,
    docs_dir: Path | None = None,
    progress_dir: Path | None = None,
    *,
    operation_id: str | None = None,
    trigger: str = "api",
    capture_analytics: bool = False,
) -> dict[str, Any]

async def _rebuild_entity_links(
    self,
    project_id: str,
    docs_dir: Path | None = None,
    progress_dir: Path | None = None,
    operation_id: str | None = None,
) -> dict
```

Both operate project-wide with no entity-ID scoping; neither accepts an `ids: list[str]` parameter.

---

## Decision

**BE-203 MUST add `rebuild_for_entities(ids: list[str])`** — the method does not exist in any form.

### Classification: YES (full addition required)

There is no partial equivalent. The closest existing primitives are:

| Primitive | Gap |
|-----------|-----|
| `delete_auto_links(source_type, source_id)` | Single entity delete, not rebuild |
| `SyncEngine.rebuild_links(project_id)` | Full project-wide rebuild, no ID scoping |
| `_rebuild_entity_links(project_id, ...)` | Private, project-wide, no entity filter |

### Minimum extension needed for BE-203

1. Add `rebuild_for_entities(entity_type: str, ids: list[str]) -> dict` to `SqliteEntityLinkRepository`.
   - Should delete existing auto-links for each entity in `ids` (reuse `delete_auto_links` per ID)
   - Then upsert newly discovered links scoped to those IDs
   - Return `{"created": int, "deleted": int}` stats dict consistent with `_rebuild_entity_links`

2. Optionally expose a thin `SyncEngine.rebuild_links_for_entities(project_id, entity_type, ids)` wrapper
   if callers need operation tracking, span emission, and invalidation fan-out (same pattern as
   `rebuild_links` wrapping `_rebuild_entity_links`).

---

<!--
BE-201 audit findings — do not modify production code per task acceptance criteria.
-->
