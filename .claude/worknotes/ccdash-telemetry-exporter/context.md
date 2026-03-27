---
type: context
schema_version: 2
doc_type: context
prd: "ccdash-telemetry-exporter"
feature_slug: "ccdash-telemetry-exporter"
status: active
created: 2026-03-24
updated: 2026-03-24
prd_ref: docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
plan_ref: docs/project_plans/implementation_plans/integrations/ccdash-telemetry-exporter-v1.md
---

# Context: CCDash Telemetry Exporter

## Feature Summary

Background worker system that pushes anonymized, aggregated workflow execution telemetry from CCDash's local database to the enterprise SkillMeat Artifact Manager (SAM). Closes the feedback loop between local AI execution forensics and enterprise-level AI ROI tracking.

## Key Architecture Decisions

- **Persistent outbound queue** in the same SQLite/PostgreSQL database as sessions (not an external message broker)
- **Worker-profile-only execution**: TelemetryExporterJob runs only under the `worker` runtime profile, never in the API process
- **Anonymization-first**: AnonymizationVerifier runs before every enqueue, not at push time
- **Batch export**: Default 50 events per push, configurable; not real-time streaming
- **Exponential backoff**: Base 60s, max 4h, max 10 attempts before abandoning

## Critical Files

| File | Role |
|------|------|
| `backend/config.py` | 8 new CCDASH_TELEMETRY_* env vars |
| `backend/db/migrations.py` | outbound_telemetry_queue table |
| `backend/db/repositories/telemetry_queue.py` | Queue CRUD operations |
| `backend/services/telemetry_transformer.py` | Transform + AnonymizationVerifier |
| `backend/adapters/jobs/telemetry_exporter.py` | Scheduled export job |
| `backend/services/integrations/sam_telemetry_client.py` | HTTP push to SAM |
| `backend/runtime/container.py` | Job registration in worker profile |
| `backend/observability/otel.py` | New telemetry export metrics |

## Dependencies

- **Prerequisite**: Deployment Runtime Modularization (worker profile must exist)
- **Prerequisite**: Hexagonal Foundation (job port/adapter interfaces)
- **External**: SAM API at `/api/v1/analytics/execution-outcomes`
- **Library**: aiohttp (already in project for SkillMeat integration)

## Open Questions

1. Per-project vs shared queue? (Recommend shared queue with project_slug column)
2. Does SAM require HMAC-signed payloads beyond bearer token?
3. Max payload size accepted by SAM ingestion endpoint?

## Risk Watch

- Anonymization blind spots: property-based tests recommended
- SAM contract drift: pin schema_version, validate response bodies
- Queue growth during extended outages: cap at 10,000 pending rows
