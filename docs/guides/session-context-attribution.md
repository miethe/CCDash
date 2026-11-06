# Session context evidence

Session Inspector has a **Context** tab alongside Transcript. It shows observed
stages, selectable layer details, provenance and explicit unknowns. A measured
zero remains zero; missing amounts or units remain unmeasured. Characters, bytes
and tokens are displayed separately and are never converted or summed together.
`first_observed_after_sessionstart` is labeled as a first observed input after
SessionStart, without asserting a cold start. `post_compact` requires a recorded
compact boundary. Missing named layers remain visible.

## Read contract

- `GET /api/sessions/{session_id}` includes optional `contextAttribution` in the
  existing session-detail model. Older servers/absent receipts render an
  unmeasured state in the frontend.
- `GET /api/sessions/{session_id}/context-attribution?project_id={project_id}`
  returns the metadata-only contract directly. An explicit project is required
  (400 if absent); nonexistent projects/sessions are 404. The route uses the
  existing authenticated request context and project-scoped session repository.
- Shared links use `/#/sessions?session={id}&project_id={project_id}&tab=context`.
  The explicit project is a per-call scope/cache key; it does not change the
  server's globally active project.

The response has `schemaVersion:1`, `status`, `generatedAt`, `coverage`, `stages`
and `unknowns`. Stages retain source phase, observed timestamp, method, source
version, provenance and unit. Layer attribution preserves the producer's
`measured`, `attributed`, `unattributed` or `missing` state. Unattributed amounts
are known readings with unresolved origin, not automatically waste or cost.

## Producer and deployment

The producer publishes an atomic metadata-only JSON file. Configure
`CCDASH_SESSION_CONTEXT_ATTRIBUTION_PATH` to its **read-only container mount**.
The default is the host account's `.local/share/aos/estate-pulse/`
`session-context-attribution.json`. NUC deployment provides the actual mount;
no database migration, transcript scan, external model call or producer write
occurs in this read service.

Root contract: `{schemaVersion:1,generatedAt,sessions:[...]}`. Each session record
contains SHA-256 `ccdashSessionKey`, `nativeSessionKey`, `projectPathKey`,
`platform`, `stages` and `unknowns`. The consumer requires an exact cached
session ID hash and original-directory hash, then verifies the native alias
against `session_forensics_json.rawSessionId` and the recorded platform. Directory
normalization is lexical `normcase(normpath(cwd))` on an absolute original cwd;
it never resolves a laptop path against the NUC filesystem. Duplicate matches,
missing aliases, platform mismatch and missing project scope remain unmatched
or ambiguous; name/time similarity is never a join.

The file read is bounded to 16 MiB. Responses are bounded to 200 stages and
64 layers per stage, with visible truncation diagnostics. Source metadata is
whitelisted into typed models; native hashes and filesystem paths used for the
join are not returned. File changes invalidate the metadata cache by mtime/size.

## Validation

```sh
backend/.venv/bin/python -m unittest backend.tests.test_session_context_attribution backend.tests.test_sessions_api_router -q
npm test -- components/SessionInspector/SessionContextAttribution.test.tsx components/__tests__/SessionInspectorFilterWiring.test.ts contexts/__tests__/mergeSessionDetail.test.ts services/queries/__tests__/sessions.test.ts
npm run build
```

Synthetic browser fixtures exercise actual product components; they are not
production measurements. A matched production deep link additionally requires
the normal CCDash deployment and the metadata receiver's read-only ingress mount.
Full repository typecheck has the independently reproduced 33-error baseline
tracked by `node_01KZS4AJND5AZBQEG0T820V928`; this feature's normalized diagnostics
match the pinned baseline, rather than claiming that gate passed.
