# Data-Domain Ownership Matrix

This guide freezes the Phase 1 DPM-003 ownership contract for CCDash persisted concerns.
`backend/data_domains.py` is the code-owned source of truth, and this document mirrors it for humans.
Phase 3 schema grouping, ownership-primitives placement, and repository readiness now live in `backend/data_domain_layout.py` and are summarized in `docs/guides/data-domain-schema-layout.md`.

## Ownership Postures

| Posture | Meaning |
| --- | --- |
| `scope-owned` | The row is governed by a workspace, project, tenant, or enterprise scope and should not reserve direct owner columns. |
| `directly-ownable` | The row is canonical and may later support direct `user`, `team`, or `enterprise` ownership. These are the only rows that reserve `tenant_id`, `enterprise_id`, `owner_subject_type`, `owner_subject_id`, and `visibility`. |
| `inherits-parent-ownership` | The row inherits ownership from a governing canonical entity and should not store direct ownership primitives on the row. |

## Domain Summary

| Domain | Durability | Local owner | Enterprise owner |
| --- | --- | --- | --- |
| Workspace and project metadata | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata |
| Observed product entities | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| Ingestion and cache state | Derived | Profile-local storage adapter | Profile-local storage adapter |
| Integration snapshots | Refreshable | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store |
| Operational and job data | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| Identity and access | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home |
| Audit and security records | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home |

## Frozen Concern Matrix

### Workspace and project metadata

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `projects.json` | Artifact | Canonical | `scope-owned` | None | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | Filesystem-backed workspace metadata remains local-first. |
| `workspace_registry_state` | Artifact | Canonical | `scope-owned` | None | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | Filesystem-backed workspace metadata remains local-first. |
| `app_metadata` | Table | Canonical | `scope-owned` | None | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | App metadata is governed by the workspace/project scope. |
| `alert_configs` | Table | Canonical | `directly-ownable` | `user`, `team`, `enterprise` | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | Shareable alert policies may later require direct ownership. |

### Observed product entities

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sessions` | Table | Mixed | `directly-ownable` | `user`, `team`, `enterprise` | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Root session records may later be user/team/enterprise owned. |
| `documents` | Table | Mixed | `directly-ownable` | `user`, `team`, `enterprise` | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Canonical document roots may later be directly owned. |
| `tasks` | Table | Mixed | `directly-ownable` | `user`, `team`, `enterprise` | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Canonical task roots may later be directly owned. |
| `features` | Table | Mixed | `directly-ownable` | `user`, `team`, `enterprise` | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Canonical feature roots may later be directly owned. |
| `tags` | Table | Mixed | `scope-owned` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Tags remain scope-governed taxonomy rows. |
| `entity_links` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Link rows inherit ownership from the governing entity. |
| `external_links` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Link rows inherit ownership from the governing entity. |
| `entity_tags` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Join rows inherit ownership from the governing entity and tag. |
| `session_logs` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Log projections inherit from `sessions`. |
| `session_messages` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Message-level transcript rows inherit from `sessions`. |
| `session_tool_usage` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Tool usage rows inherit from `sessions`. |
| `session_file_updates` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | File-update rows inherit from `sessions`. |
| `session_artifacts` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Artifact rows inherit from `sessions`. |
| `session_usage_events` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Usage events inherit from `sessions`. |
| `session_usage_attributions` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Attribution rows inherit from `sessions`. |
| `session_relationships` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Relationship rows inherit from the governing session lineage. |
| `document_refs` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Reference rows inherit from `documents`. |
| `feature_phases` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Phase rows inherit from `features`. |
| `commit_correlations` | Table | Mixed | `inherits-parent-ownership` | None | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | Correlation rows inherit from the governing feature/session context. |

### Ingestion and cache state

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sync_state` | Table | Derived | `scope-owned` | None | Profile-local storage adapter | Profile-local storage adapter | Filesystem sync state is adapter-owned rather than canonical shared data. |

### Integration snapshots

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `external_definition_sources` | Table | Refreshable | `scope-owned` | None | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store | Snapshot roots stay scope-governed. |
| `pricing_catalog_entries` | Table | Refreshable | `scope-owned` | None | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store | Snapshot roots stay scope-governed. |
| `external_definitions` | Table | Refreshable | `inherits-parent-ownership` | None | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store | Definitions inherit from the governing snapshot source. |

### Operational and job data

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `metric_types` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `analytics_entries` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `telemetry_events` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `outbound_telemetry_queue` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `effectiveness_rollups` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `execution_runs` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `test_runs` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `test_definitions` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `test_domains` | Table | Operational | `scope-owned` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Scope-aware only. |
| `analytics_entity_links` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from the governing analytics scope/root. |
| `session_stack_observations` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from the governing session/scope root. |
| `session_stack_components` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from the governing observation. |
| `execution_run_events` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from `execution_runs`. |
| `execution_approvals` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from `execution_runs`. |
| `test_results` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from `test_runs`/`test_definitions`. |
| `test_feature_mappings` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from the governing test/feature roots. |
| `test_integrity_signals` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from the governing test scope/root. |
| `test_metrics` | Table | Operational | `inherits-parent-ownership` | None | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | Inherits from the governing test scope/root. |

### Identity and access placeholders

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `principals` | Placeholder | Canonical | `scope-owned` | None | Not part of the local-first storage contract | Enterprise Postgres canonical home | Identity roots are governed by tenant/enterprise scope. |
| `scope_identifiers` | Placeholder | Canonical | `scope-owned` | None | Not part of the local-first storage contract | Enterprise Postgres canonical home | Scope roots are governed by tenant/enterprise scope. |
| `memberships` | Placeholder | Canonical | `inherits-parent-ownership` | None | Not part of the local-first storage contract | Enterprise Postgres canonical home | Membership rows inherit from the governing principal and scope roots. |
| `role_bindings` | Placeholder | Canonical | `inherits-parent-ownership` | None | Not part of the local-first storage contract | Enterprise Postgres canonical home | Binding rows inherit from the governing principal and scope roots. |

### Audit and security record placeholders

| Concern | Kind | Durability | Posture | Direct owner subjects | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `privileged_action_audit_records` | Placeholder | Canonical | `scope-owned` | None | Not part of the local-first storage contract | Enterprise Postgres canonical home | Audit rows stay scope-governed unless a later plan proves they are independently shareable. |
| `access_decision_logs` | Placeholder | Canonical | `scope-owned` | None | Not part of the local-first storage contract | Enterprise Postgres canonical home | Audit rows stay scope-governed unless a later plan proves they are independently shareable. |

## Enforcement Notes

- The migration-owned set currently contains 44 tables and is expected to stay identical between `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`.
- `backend/tests/test_data_domain_ownership.py` enforces that every concern now has an explicit ownership posture and that only the currently reserved directly ownable concerns advertise direct owner subjects.
- This matrix intentionally includes non-table persisted concerns (`projects.json`, `workspace_registry_state`) so future storage work does not regress filesystem ownership assumptions.
