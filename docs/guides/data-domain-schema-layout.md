# Data-Domain Schema Layout

This guide is the Phase 3 companion to the ownership matrix. `backend/data_domain_layout.py` is the code-owned source of truth for schema groups and repository ownership.

## Postgres Schema Groups

| Boundary | Domain | Postgres schema | SQLite equivalent | Notes |
| --- | --- | --- | --- | --- |
| `workspace_metadata` | Workspace and project metadata | `app` | Workspace metadata tables | Keeps app metadata separate from runtime state while preserving local-first filesystem ownership. |
| `observed_entities` | Observed product entities | `app` | Observed entity tables | Sessions, documents, tasks, features, links, and message transcripts stay together until a later plan fully canonicalizes enterprise session intelligence. |
| `ingestion_state` | Ingestion and cache state | `ops` | Ingestion adapter state tables | Sync checkpoints are adapter state and should not be treated as hosted canonical data. |
| `integration_snapshots` | Integration snapshots | `integration` | Refreshable integration snapshot tables | Refreshable snapshots remain isolated from canonical app state. |
| `operational_state` | Operational and job data | `ops` | Runtime and job state tables | Runtime health, execution/test tracking, telemetry queues, and intelligence rollups belong to the operational boundary. |
| `identity_access` | Identity and access | `identity` | Not part of the local-first contract | Reserved for future enterprise-only principals, memberships, role bindings, and scope identifiers. |
| `audit_security` | Audit and security records | `audit` | Not part of the local-first contract | Reserved for future enterprise-only privileged-action and access-decision records. |

## Repository Ownership

| Storage key | Boundary | SQLite module | Postgres module | Owned concerns |
| --- | --- | --- | --- | --- |
| `sessions` | `observed_entities` | `backend.db.repositories.sessions` | `backend.db.repositories.postgres.sessions` | `sessions`, `session_logs`, `session_relationships`, `session_tool_usage`, `session_file_updates`, `session_artifacts` |
| `session_messages` | `observed_entities` | `backend.db.repositories.session_messages` | `backend.db.repositories.postgres.session_messages` | `session_messages` |
| `documents` | `observed_entities` | `backend.db.repositories.documents` | `backend.db.repositories.postgres.documents` | `documents`, `document_refs` |
| `tasks` | `observed_entities` | `backend.db.repositories.tasks` | `backend.db.repositories.postgres.tasks` | `tasks` |
| `features` | `observed_entities` | `backend.db.repositories.features` | `backend.db.repositories.postgres.features` | `features`, `feature_phases`, `commit_correlations` |
| `entity_links` | `observed_entities` | `backend.db.repositories.entity_graph` | `backend.db.repositories.postgres.entity_graph` | `entity_links`, `external_links` |
| `tags` | `observed_entities` | `backend.db.repositories.entity_graph` | `backend.db.repositories.postgres.entity_graph` | `tags`, `entity_tags` |
| `sync_state` | `ingestion_state` | `backend.db.repositories.runtime_state` | `backend.db.repositories.postgres.runtime_state` | `sync_state` |
| `alert_configs` | `workspace_metadata` | `backend.db.repositories.runtime_state` | `backend.db.repositories.postgres.runtime_state` | `alert_configs` |
| `analytics` | `operational_state` | `backend.db.repositories.analytics` | `backend.db.repositories.postgres.analytics` | `analytics_entries`, `analytics_entity_links`, `metric_types` |
| `session_usage` | `observed_entities` | `backend.db.repositories.usage_attribution` | `backend.db.repositories.postgres.usage_attribution` | `session_usage_events`, `session_usage_attributions` |
| `pricing_catalog` | `integration_snapshots` | `backend.db.repositories.pricing` | `backend.db.repositories.postgres.pricing` | `pricing_catalog_entries`, `external_definition_sources`, `external_definitions` |
| `test_runs` / `test_definitions` / `test_results` / `test_domains` / `test_mappings` / `test_integrity` | `operational_state` | Matching `backend.db.repositories.*` test modules | Matching `backend.db.repositories.postgres.*` test modules | Operational test execution state |
| `execution` | `operational_state` | `backend.db.repositories.execution` | `backend.db.repositories.postgres.execution` | `execution_runs`, `execution_run_events`, `execution_approvals` |
| `agentic_intelligence` | `operational_state` | `backend.db.repositories.intelligence` | `backend.db.repositories.postgres.intelligence` | `session_stack_observations`, `session_stack_components`, `effectiveness_rollups`, `telemetry_events`, `outbound_telemetry_queue` |

## Boundary Rules

- Future enterprise auth work must land in the `identity` schema boundary, not in `ops` or the observed-entity tables.
- Future privileged-action and access-decision records must land in the `audit` schema boundary.
- `session_messages` is the transcript seam for follow-on canonical session storage; compatibility projections can continue to read from legacy DTOs while the underlying store evolves.
- `sync_state` remains adapter-owned. Enterprise API runtime behavior must not treat it as canonical app state.
