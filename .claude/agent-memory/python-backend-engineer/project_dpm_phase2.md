---
name: DPM Phase 2 storage adapter state
description: Status of DPM-101/102 explicit storage adapters and composition root wiring as of 2026-03-30
type: project
---

DPM-101 and DPM-102 are complete. The storage adapter split is fully landed.

**Why:** Replace factory-backed connection-type inspection with explicit profile-aware adapters composed at the runtime layer.

**How to apply:** When working on storage concerns, expect these types:
- `LocalStorageUnitOfWork` (backend/adapters/storage/local.py) — explicit SQLite repos, no isinstance checks
- `EnterpriseStorageUnitOfWork` (backend/adapters/storage/enterprise.py) — explicit Postgres repos
- `FactoryStorageUnitOfWork` (same file) — compat alias, subclass of LocalStorageUnitOfWork; used only by existing tests (test_live_router, test_documents_router) that have not been migrated yet
- `RepositoryBackedStorageUnitOfWork` (backend/adapters/storage/base.py) — shared base class for both

`runtime_ports._build_storage_unit_of_work` branches on `storage_profile.profile` ("local" → Local, "enterprise" → Enterprise). No `isinstance(db, ...)` check in the runtime path.

`FactoryStorageUnitOfWork` should not appear in new composition paths — the factory is a deprecated transitional bridge scheduled for removal in DPM-103.
