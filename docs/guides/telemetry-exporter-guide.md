# Telemetry Exporter Guide

Last updated: 2026-03-27

CCDash's telemetry exporter is a worker-side background flow that transforms finalized session data into anonymized `ExecutionOutcomePayload` records and pushes them to SAM.

## Configuration

Set these environment variables before starting the API and worker runtimes:

- `CCDASH_TELEMETRY_EXPORT_ENABLED` controls whether export is allowed at all. Default: `false`.
- `CCDASH_SAM_ENDPOINT` is the SAM ingestion URL. Required when export is enabled.
- `CCDASH_SAM_API_KEY` is the SAM API key. Required when export is enabled.
- `CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS` controls scheduled export frequency. Default: `900`.
- `CCDASH_TELEMETRY_EXPORT_BATCH_SIZE` controls how many queued events are pushed per run. Default: `50`.
- `CCDASH_TELEMETRY_EXPORT_TIMEOUT_SECONDS` controls the outbound HTTP timeout. Default: `30`.
- `CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE` caps pending rows in the local queue. Default: `10000`.
- `CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS` controls how long synced rows are retained before purge. Default: `30`.
- `CCDASH_TELEMETRY_ALLOW_INSECURE` allows non-HTTPS SAM endpoints for local testing only. Default: `false`.

Validation rules enforced by `backend/config.py`:

- `interval_seconds` must be at least `60`.
- `batch_size` must be between `1` and `500`.
- `timeout_seconds` must be at least `1`.
- `max_queue_size` must be at least `1`.
- `queue_retention_days` must be at least `1`.
- When export is enabled, both the SAM endpoint and API key must be present.

## Enable and Disable Behavior

Exporter state is controlled by both environment configuration and persisted settings:

- If `CCDASH_TELEMETRY_EXPORT_ENABLED=false`, export is disabled regardless of UI settings.
- If the endpoint or API key is missing, the exporter is not configured.
- The settings API and ops panel can toggle the persisted enabled flag when environment configuration allows it.
- `POST /api/telemetry/export/push-now` returns `400` if the exporter is not configured or disabled.

Useful endpoints:

- `GET /api/telemetry/export/status`
- `PATCH /api/telemetry/export/settings`
- `POST /api/telemetry/export/push-now`

## Monitoring

The status endpoint is the primary operator signal today. It returns:

- `enabled`
- `configured`
- `samEndpointMasked`
- queue counts for `pending`, `synced`, `failed`, and `abandoned`
- `lastPushTimestamp`
- `eventsPushed24h`
- `lastError`
- `errorSeverity`

Operational signals also show up in logs:

- queue-cap drops log a warning with the session ID and queue depth
- successful purge runs log the retention window and number of rows removed
- export failures log the run outcome and error text

Prometheus support exists at the backend observability layer, but the exporter does not currently expose dedicated exporter-specific series. In practice, monitor the worker process, the status endpoint, and the existing backend Prometheus export if it is enabled via `CCDASH_PROM_PORT`.

## Operator Workflow

1. Set `CCDASH_TELEMETRY_EXPORT_ENABLED=true`, `CCDASH_SAM_ENDPOINT`, and `CCDASH_SAM_API_KEY`.
2. Start or restart the worker runtime.
3. Confirm `GET /api/telemetry/export/status` reports `configured=true` and `enabled=true`.
4. Watch queue depth while sessions finalize.
5. Use `POST /api/telemetry/export/push-now` for manual delivery during validation or incident response.
6. Treat `failed` and `abandoned` rows as signals to inspect SAM connectivity or payload validation.

## Security Notes

- The queue stores anonymized payload JSON, not raw session logs.
- `TelemetryTransformer` normalizes session data before enqueue.
- `AnonymizationVerifier` rejects payloads containing email addresses, absolute paths, hostnames, usernames, stack traces, and sensitive field names.
- `CCDASH_TELEMETRY_ALLOW_INSECURE=true` should only be used in local or test environments.
- The exporter requires a valid SAM API key when enabled.

## Code References

- `/Users/miethe/dev/homelab/development/CCDash/backend/config.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/routers/telemetry.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/services/integrations/telemetry_exporter.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/services/telemetry_transformer.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/observability/otel.py`
