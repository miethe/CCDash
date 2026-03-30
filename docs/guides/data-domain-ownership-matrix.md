# Data-Domain Ownership Matrix

This guide freezes the Phase 1 DPM-003 ownership contract for CCDash persisted concerns.
`backend/data_domains.py` is the code-owned source of truth, and this document mirrors it for humans.
Phase 3 schema grouping and repository ownership now live in `backend/data_domain_layout.py` and are summarized in `docs/guides/data-domain-schema-layout.md`.

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

| Concern | Kind | Durability | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- |
| `projects.json` | Artifact | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | Filesystem-backed workspace metadata remains local-first, but the hosted target owner is canonical app metadata. |
| `workspace_registry_state` | Artifact | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | Filesystem-backed workspace metadata remains local-first, but the hosted target owner is canonical app metadata. |
| `app_metadata` | Table | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | |
| `alert_configs` | Table | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | |

### Observed product entities

| Concern | Kind | Durability | Local owner | Enterprise owner |
| --- | --- | --- | --- | --- |
| `entity_links` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `external_links` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `tags` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `entity_tags` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `sessions` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_logs` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_messages` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_tool_usage` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_file_updates` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_artifacts` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_usage_events` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_usage_attributions` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `session_relationships` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `documents` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `document_refs` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `tasks` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `features` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `feature_phases` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |
| `commit_correlations` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage |

### Ingestion and cache state

| Concern | Kind | Durability | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- |
| `sync_state` | Table | Derived | Profile-local storage adapter | Profile-local storage adapter | Filesystem sync state is adapter-owned rather than canonical shared data. |

### Integration snapshots

| Concern | Kind | Durability | Local owner | Enterprise owner |
| --- | --- | --- | --- | --- |
| `external_definition_sources` | Table | Refreshable | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store |
| `external_definitions` | Table | Refreshable | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store |
| `pricing_catalog_entries` | Table | Refreshable | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store |

### Operational and job data

| Concern | Kind | Durability | Local owner | Enterprise owner |
| --- | --- | --- | --- | --- |
| `schema_version` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `metric_types` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `analytics_entries` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `analytics_entity_links` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `telemetry_events` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `outbound_telemetry_queue` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `session_stack_observations` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `session_stack_components` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `effectiveness_rollups` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `execution_runs` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `execution_run_events` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `execution_approvals` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_runs` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_definitions` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_results` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_domains` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_feature_mappings` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_integrity_signals` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |
| `test_metrics` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode |

### Identity and access placeholders

| Concern | Kind | Durability | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- |
| `principals` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | Planned auth-era tables reserved for future enterprise identity and scope management work. |
| `memberships` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | Planned auth-era tables reserved for future enterprise identity and scope management work. |
| `role_bindings` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | Planned auth-era tables reserved for future enterprise identity and scope management work. |
| `scope_identifiers` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | Planned auth-era tables reserved for future enterprise identity and scope management work. |

### Audit and security record placeholders

| Concern | Kind | Durability | Local owner | Enterprise owner | Notes |
| --- | --- | --- | --- | --- | --- |
| `privileged_action_audit_records` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | Planned audit/security records reserved for future privileged-action and access-decision tracking. |
| `access_decision_logs` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | Planned audit/security records reserved for future privileged-action and access-decision tracking. |

## Enforcement Notes

- The migration-owned set currently contains 44 tables and is expected to stay identical between `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`.
- `backend/tests/test_data_domain_ownership.py` enforces that every current migration table is classified and that the auth/audit placeholders stay frozen as enterprise-owned canonical concerns.
- This matrix intentionally includes non-table persisted concerns (`projects.json`, `workspace_registry_state`) so future storage work does not regress filesystem ownership assumptions.
