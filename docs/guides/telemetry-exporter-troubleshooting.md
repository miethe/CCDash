# Telemetry Exporter Troubleshooting

Last updated: 2026-03-27

This guide maps the most common telemetry exporter failures to the current CCDash behavior.

## Exporter Reports `disabled` or `not_configured`

Symptoms:

- `GET /api/telemetry/export/status` shows `enabled=false`
- `configured=false`
- `POST /api/telemetry/export/push-now` returns `400`

Checks:

- Confirm `CCDASH_TELEMETRY_EXPORT_ENABLED=true` if you want export active.
- Confirm `CCDASH_SAM_ENDPOINT` and `CCDASH_SAM_API_KEY` are both set.
- Restart the worker after changing environment variables.
- If the UI toggle is off but the environment is disabled, the environment wins.

## Push Now Returns `429`

Symptoms:

- `POST /api/telemetry/export/push-now` returns `429`
- The queue is already being processed

Checks:

- Wait for the current run to finish.
- Re-run the request after the worker finishes its scheduled batch.
- Review the `Telemetry export run complete` log entry for the prior run ID.

## Queue Stops Growing

Symptoms:

- New sessions are not appearing in the export queue
- Logs show `Dropping telemetry enqueue because pending queue is full`

Checks:

- Increase `CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE` if the cap is too low for your workload.
- Inspect `pending` in `GET /api/telemetry/export/status`.
- Check whether SAM is unavailable and the queue is backing up.

The queue cap is a drop-and-warn safeguard. It prevents unbounded growth, so new rows are intentionally skipped once the pending count reaches the configured limit.

## Export Fails With HTTP or Network Errors

Symptoms:

- `lastError` shows an HTTP failure, timeout, or connection error
- queue rows move into `failed`

Checks:

- Verify `CCDASH_SAM_ENDPOINT` is reachable from the worker host.
- Confirm the endpoint uses HTTPS unless `CCDASH_TELEMETRY_ALLOW_INSECURE=true` is set.
- Confirm the SAM API key is valid.
- Check whether a proxy, firewall, or TLS inspection device is interfering with outbound requests.

## Rows Become `abandoned`

Symptoms:

- Queue rows move to `abandoned`
- `errorSeverity` becomes `error`

Checks:

- Inspect the error text in the status endpoint.
- Check whether the payload was rejected by SAM with a permanent 4xx response.
- Look for retry exhaustion after repeated failures.

## Payload Validation Fails

Symptoms:

- Sessions fail during transformation or enqueue
- Logs or tests show anonymization errors

Checks:

- Remove absolute file paths from metadata or session-derived fields.
- Remove email addresses, usernames, hostnames, stack traces, and secret-like field names from telemetry payloads.
- Verify that any custom metadata passed into the transformer is already anonymized.

## Synced Rows Are Not Being Purged

Symptoms:

- Old `synced` rows remain in the queue
- Log output does not show purge activity

Checks:

- Confirm the worker is processing at least one successful export run.
- Check `CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS`.
- Remember that purge is run after a batch export succeeds, not on idle runs.

## What To Look At First

1. `GET /api/telemetry/export/status`
2. Worker logs for queue-cap, export, and purge messages
3. SAM reachability from the worker host
4. Environment values for `CCDASH_TELEMETRY_EXPORT_ENABLED`, `CCDASH_SAM_ENDPOINT`, and `CCDASH_SAM_API_KEY`

## Code References

- `/Users/miethe/dev/homelab/development/CCDash/backend/routers/telemetry.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/services/integrations/telemetry_exporter.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/services/telemetry_transformer.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/db/repositories/telemetry_queue.py`
