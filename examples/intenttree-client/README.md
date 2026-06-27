# CCDash IntentTree / LAN Agent Example Client

Demonstrates the CCDash `/api/v1` external API: capability discovery, session
list, session search, and cross-project session detail.

No third-party dependencies — stdlib only.

## Quick start

### Dry run (no live server)

```bash
python examples/intenttree-client/client.py --dry
```

### Live run

```bash
# Start CCDash
npm run dev:backend

# Run the client
python examples/intenttree-client/client.py \
    --base-url http://localhost:8000 \
    --project-id <your-project-id>
```

### LAN agent (different machine on the same network)

```bash
python examples/intenttree-client/client.py \
    --base-url http://192.168.1.50:8000 \
    --project-id <your-project-id>
```

### With bearer auth (when `CCDASH_API_TOKEN` is set on the server)

```bash
python examples/intenttree-client/client.py \
    --base-url http://192.168.1.50:8000 \
    --project-id <your-project-id> \
    --token my-secret-token
```

## Flow

1. **Capability discovery** (`GET /api/v1/capabilities`)  
   Checks for `sessions:cross-project` and `sessions:detail` before using
   those endpoints.  Prints a warning (does not fail) if a capability is
   absent.

2. **Session list** (`GET /api/v1/sessions`)  
   Returns the first page of session rollups.  Empty `data: []` is valid —
   the server may have no sessions yet.

3. **Session search** (`GET /api/v1/sessions/search?q=...`)  
   Full-text search across transcripts.  Results are gracefully handled when
   empty.

4. **Session detail** (`GET /api/v1/sessions/{id}/detail?project_id=...`)  
   Requires `project_id` (HTTP 400 if absent).  Redacted fields are reported
   via `redactedFieldCount`; a non-zero count is a contract state, not a bug.

## Redacted payloads

The Phase 1 redaction layer scrubs secrets before serialisation.
`redactedFieldCount > 0` in a detail response means the server applied
redaction rules.  Consumers MUST handle this gracefully — do not error on
missing fields.

## Auth

If the server has `CCDASH_API_TOKEN` set, pass `--token <value>` or set the
`Authorization: Bearer <value>` header on every `/api/v1` request.  Missing
token → 401; wrong token → 403.

See `docs/guides/external-api-lan-deployment.md` for full operator guidance.
