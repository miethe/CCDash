# Data-Domain Schema Layout

This guide is the Phase 3 companion to the ownership matrix. `backend/data_domain_layout.py` is the code-owned source of truth for schema groups, ownership-primitive placement, and repository ownership.

## Postgres Schema Groups

| Boundary | Domain | Postgres schema | SQLite equivalent | Directly ownable roots | Ownership primitive placement | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `workspace_metadata` | Workspace and project metadata | `app` | Workspace metadata tables | `alert_configs` | `tenant_id`/`enterprise_id`, `owner_subject_type`, `owner_subject_id`, `visibility` live on directly ownable alert config rows only | `projects.json`, `workspace_registry_state`, and `app_metadata` stay scope-owned. |
| `observed_entities` | Observed product entities | `app` | Observed entity tables | `sessions`, `documents`, `tasks`, `features` | Ownership primitives live on the canonical root rows only; transcript, link, usage, and phase rows inherit ownership | `tags` remains scope-owned taxonomy data. |
| `ingestion_state` | Ingestion and cache state | `ops` | Ingestion adapter state tables | None | No direct ownership primitives | Sync checkpoints stay adapter-owned. |
| `integration_snapshots` | Integration snapshots | `integration` | Refreshable integration snapshot tables | None | No direct ownership primitives | Snapshot roots are scope-owned; child definitions inherit. |
| `operational_state` | Operational and job data | `ops` | Runtime and job state tables | None | No direct ownership primitives | Operational roots are scope-owned; child rows inherit. |
| `identity_access` | Identity and access | `identity` | Not part of the local-first contract | None | Scope keys live here; no direct object ownership fields reserved in Phase 3 | `principals` and `scope_identifiers` are scope-owned; memberships and bindings inherit. |
| `audit_security` | Audit and security records | `audit` | Not part of the local-first contract | None | No direct ownership primitives | Audit rows stay scope-governed unless later proven independently shareable. |

## Ownership Primitive Placement Rules

- Reserve `tenant_id` or `enterprise_id`, `owner_subject_type`, `owner_subject_id`, and `visibility` only on directly ownable canonical roots.
- Supported direct owner subject types are currently `user`, `team`, and `enterprise`.
- Rows classified as `inherits-parent-ownership` must reference the governing canonical entity or scope instead of carrying direct owner fields.
- Derived cache, integration snapshot, operational, and audit rows stay scope-aware only unless a later plan explicitly makes them independently shareable.

## Repository Ownership

| Storage key | Boundary | Ownership mode | Directly ownable roots | Scope-only concerns | Inherited concerns | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `sessions` | `observed_entities` | `owner-aware` | `sessions` | | `session_logs`, `session_relationships`, `session_tool_usage`, `session_file_updates`, `session_artifacts` | Owner-aware repository because the canonical root may later support direct ownership. |
| `session_messages` | `observed_entities` | `scope-aware-only` | | | `session_messages` | Transcript rows inherit ownership from the parent session. |
| `documents` | `observed_entities` | `owner-aware` | `documents` | | `document_refs` | Document refs inherit from the canonical document. |
| `tasks` | `observed_entities` | `owner-aware` | `tasks` | | | Task roots may later support direct ownership and visibility rules. |
| `features` | `observed_entities` | `owner-aware` | `features` | | `feature_phases`, `commit_correlations` | Child rows inherit from the feature root. |
| `entity_links` | `observed_entities` | `scope-aware-only` | | | `entity_links`, `external_links` | Link rows inherit from the governing canonical entity. |
| `tags` | `observed_entities` | `scope-aware-only` | | `tags` | `entity_tags` | Taxonomy rows stay scope-owned; join rows inherit. |
| `sync_state` | `ingestion_state` | `scope-aware-only` | | `sync_state` | | Adapter state only. |
| `alert_configs` | `workspace_metadata` | `owner-aware` | `alert_configs` | | | Shareable alert configs are the only directly ownable rows in this boundary. |
| `analytics` | `operational_state` | `scope-aware-only` | | `analytics_entries`, `metric_types` | `analytics_entity_links` | Operational analytics remain scope-aware only. |
| `session_usage` | `observed_entities` | `scope-aware-only` | | | `session_usage_events`, `session_usage_attributions` | Inherits from the parent session. |
| `pricing_catalog` | `integration_snapshots` | `scope-aware-only` | | `pricing_catalog_entries`, `external_definition_sources` | `external_definitions` | Snapshot children inherit from the governing snapshot source. |
| `test_runs` | `operational_state` | `scope-aware-only` | | `test_runs` | | Operational root. |
| `test_definitions` | `operational_state` | `scope-aware-only` | | `test_definitions` | | Operational root. |
| `test_results` | `operational_state` | `scope-aware-only` | | | `test_results` | Inherits from the governing test run/definition. |
| `test_domains` | `operational_state` | `scope-aware-only` | | `test_domains` | | Operational root. |
| `test_mappings` | `operational_state` | `scope-aware-only` | | | `test_feature_mappings` | Inherits from the governing test scope. |
| `test_integrity` | `operational_state` | `scope-aware-only` | | | `test_integrity_signals`, `test_metrics` | Inherits from the governing test scope/run. |
| `execution` | `operational_state` | `scope-aware-only` | | `execution_runs` | `execution_run_events`, `execution_approvals` | Execution roots are scope-owned; dependent rows inherit. |
| `agentic_intelligence` | `operational_state` | `scope-aware-only` | | `effectiveness_rollups`, `telemetry_events`, `outbound_telemetry_queue` | `session_stack_observations`, `session_stack_components` | Operational intelligence remains scope-aware only. |

## Boundary Rules

- Future enterprise auth work must land in the `identity` schema boundary, not in `ops` or the observed-entity tables.
- Future privileged-action and access-decision records must land in the `audit` schema boundary.
- `session_messages` stays the transcript seam for follow-on canonical session storage, but it inherits ownership from the parent session.
- Owner-aware repositories are limited to the canonical roots that may later support direct `user`, `team`, or `enterprise` ownership.
