# Data-Domain Ownership Matrix

This guide freezes the Phase 1 DPM-003 ownership contract for CCDash persisted concerns, includes the Phase 3 post-completion ownership-posture delta, and reflects the Phase 4 enterprise-only identity/access and audit/security boundary work now in progress. [backend/data_domains.py](/Users/miethe/dev/homelab/development/CCDash/backend/data_domains.py) is the code-owned source of truth, and [docs/guides/data-domain-schema-layout.md](/Users/miethe/dev/homelab/development/CCDash/docs/guides/data-domain-schema-layout.md) captures the matching schema and repository contract.

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

## Ownership Posture Legend

- `scope-owned`: the row is governed by workspace/project/enterprise scope and should not reserve direct object-ownership primitives.
- `directly-ownable`: the row is a canonical entity root that may later support direct `user`, `team`, or `enterprise` ownership in hosted mode.
- `inherits-parent-ownership`: the row inherits ownership from a governing canonical entity or scope root and should not duplicate direct ownership columns.

## Frozen Concern Matrix

### Workspace and project metadata

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `projects.json`, `workspace_registry_state`, `app_metadata` | Artifact / Table | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | `scope-owned` | None | Workspace metadata remains governed by workspace/project scope. |
| `alert_configs` | Table | Canonical | Local filesystem + SQLite app metadata | Enterprise Postgres canonical app metadata | `directly-ownable` | `user`, `team`, `enterprise` | Alert policies may later support direct sharing; reserve direct ownership primitives only on this root. |

### Observed product entities

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sessions`, `documents`, `tasks`, `features` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | `directly-ownable` | `user`, `team`, `enterprise` | These are the current enterprise-canonical candidate roots that may later support direct user/team/enterprise ownership. |
| `tags` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | `scope-owned` | None | Tags remain workspace/project taxonomy unless a later plan proves they must become independently ownable. |
| `entity_links`, `external_links`, `entity_tags`, `session_logs`, `session_messages`, `session_tool_usage`, `session_file_updates`, `session_artifacts`, `session_usage_events`, `session_usage_attributions`, `session_relationships`, `document_refs`, `feature_phases`, `commit_correlations` | Table | Mixed | SQLite cache + local metadata | Enterprise Postgres canonical or mixed-mode hosted storage | `inherits-parent-ownership` | None | These rows inherit ownership from the governing canonical entity rather than carrying direct ownership primitives themselves. |

### Ingestion and cache state

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sync_state` | Table | Derived | Profile-local storage adapter | Profile-local storage adapter | `scope-owned` | None | Filesystem sync state is adapter-owned rather than canonical shared data. |

### Integration snapshots

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `external_definition_sources`, `pricing_catalog_entries` | Table | Refreshable | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store | `scope-owned` | None | Snapshot roots remain scope-governed and should not reserve direct ownership primitives. |
| `external_definitions` | Table | Refreshable | SQLite refreshable snapshot cache | Enterprise Postgres refreshable snapshot store | `inherits-parent-ownership` | None | Definition rows inherit ownership from the governing snapshot source. |

### Operational and job data

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version`, `metric_types`, `analytics_entries`, `telemetry_events`, `outbound_telemetry_queue`, `effectiveness_rollups`, `execution_runs`, `test_runs`, `test_definitions`, `test_domains` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | `scope-owned` | None | Operational roots stay scope-aware only; they should not gain direct ownership columns. |
| `analytics_entity_links`, `session_stack_observations`, `session_stack_components`, `execution_run_events`, `execution_approvals`, `test_results`, `test_feature_mappings`, `test_integrity_signals`, `test_metrics` | Table | Operational | Local adapter allowed for local mode | Enterprise Postgres preferred for hosted mode | `inherits-parent-ownership` | None | Child operational rows inherit ownership from the governing run, observation, or scope root. |

### Identity and access placeholders

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `principals`, `scope_identifiers` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | `scope-owned` | None | Identity roots are governed by tenant or enterprise scope rather than direct user/team ownership columns. These rows stay enterprise-only until Phase 4 lands the concrete tables. |
| `memberships`, `role_bindings` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | `inherits-parent-ownership` | None | Membership and binding records inherit ownership from the governing principal and scope roots. They do not gain direct ownership primitives. |

### Audit and security record placeholders

| Concern(s) | Kind | Durability | Local owner | Enterprise owner | Ownership posture | Future direct owners | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `privileged_action_audit_records`, `access_decision_logs` | Placeholder | Canonical | Not part of the local-first storage contract | Enterprise Postgres canonical home | `scope-owned` | None | Audit records remain scope-governed and must not reserve direct ownership columns unless a later plan proves they are independently shareable. These are enterprise-only records, not local parity tables. |

## Enforcement Notes

- The migration-owned set currently contains 44 tables and is expected to stay identical between `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`.
- [backend/tests/test_data_domain_ownership.py](/Users/miethe/dev/homelab/development/CCDash/backend/tests/test_data_domain_ownership.py) enforces that every current migration table is classified, that directly ownable concerns reserve the expected future owner subject types, and that the auth/audit placeholders stay frozen as enterprise-owned canonical concerns.
- This matrix intentionally includes non-table persisted concerns (`projects.json`, `workspace_registry_state`) so future storage work does not regress filesystem ownership assumptions.
