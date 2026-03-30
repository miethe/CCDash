---
feature: data-platform-modularization-v1
phase: 2
date: 2026-03-30
status: in_progress
tasks:
  - id: DPM-101
    title: Explicit Storage Adapters
    status: completed
    notes:
      - Added LocalStorageUnitOfWork and EnterpriseStorageUnitOfWork implementing existing port.
      - Kept factory-backed adapter as internal bridge with clear deprecation note.
  - id: DPM-102
    title: Composition Root Wiring
    status: completed
    notes:
      - backend/runtime_ports.py now composes adapters explicitly by storage profile.
      - Removed FactoryStorageUnitOfWork from composition path.
  - id: DPM-103
    title: Compatibility Sunset Plan
    status: completed
    notes:
      - Bounded compatibility: FactoryStorageUnitOfWork remains in backend.adapters.storage.local only.
      - Package exports switched to explicit adapters.
validation:
  tests:
    - backend/tests/test_runtime_bootstrap.py
    - backend/tests/test_request_context.py
    - backend/tests/test_live_router.py
    - backend/tests/test_documents_router.py
    - backend/tests/test_storage_adapter_composition.py
  result: all_passed
  run_command: backend/.venv/bin/python -m pytest backend/tests/test_runtime_bootstrap.py backend/tests/test_request_context.py backend/tests/test_live_router.py backend/tests/test_documents_router.py -q
  local_run:
    - python -m pytest backend/tests/test_runtime_bootstrap.py backend/tests/test_request_context.py backend/tests/test_live_router.py backend/tests/test_documents_router.py -q
    - python -m pytest backend/tests/test_storage_adapter_composition.py -q
residual_blockers:
  - Enterprise adapters still delegate to repository factory; Phase 3+ will move to owned Postgres repositories and schemas.
  - Migrations governance and identity/audit domains are pending later phases.
---

Phase 2 completed: storage adapter selection is profile-aware and explicit.

