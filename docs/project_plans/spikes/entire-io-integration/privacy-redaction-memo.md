---
schema_version: 2
doc_type: spike
title: "Privacy, Redaction & License Memo — Entire.io Integration (SPIKE-B / RQ-9)"
status: completed
created: 2026-05-11
updated: 2026-05-11
completed_date: 2026-05-11
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/entire-io-integration-charter.md
parent_spike: docs/project_plans/spikes/entire-io-integration.md
---

# Privacy, Redaction & License Memo — Entire.io Integration

## 1. License Compatibility

Entire CLI is **MIT-licensed** ([entireio/cli](https://github.com/entireio/cli)). CCDash's runtime is permissive-licensed (see `LICENSE` in repo root). MIT is compatible with CCDash's distribution model. **No license action required.**

CCDash does not bundle or redistribute the `entire` binary; ingest reads on-disk git artifacts that the user has generated themselves. No upstream code is vendored.

## 2. Redaction — Trust-but-Verify

Entire applies best-effort redaction on its side ([Agent Hooks blog](https://entire.io/blog/agent-hooks-the-integration-layer-between-entire-cli-and-your-agent)). Per the checkpoint schema (§3.8), redaction metadata is surfaced via `redaction.{applied, rulesetVersion, matches}`.

**CCDash treats Entire-side redaction as advisory.** A CCDash-side second-pass redactor runs on ingest, applying CCDash's existing redaction rules (the rules used today for `FilesystemSource` already cover this surface). The second pass:

- Logs a metric `ingest_redaction_secondary_hits_total{source_id="entire"}` per hit, so operators can compare Entire's redaction coverage against CCDash's.
- Does not modify the on-disk Entire checkpoint (read-only ingest).
- Records `redaction.secondary_applied: true` and `redaction.secondary_matches: N` on the CCDash session row's `session_forensics_json`.

### Redaction-gap list (likely surfaces requiring second-pass coverage)

| Surface | Entire coverage (best-guess) | CCDash second-pass action |
|---|---|---|
| API keys in prompts | Likely | Re-scan with CCDash's `secrets` ruleset |
| File contents with embedded secrets | Likely | Re-scan |
| Tool outputs containing env-dumps | Variable | Re-scan |
| Git commit messages | Unlikely (Entire doesn't redact commits, only session data) | CCDash doesn't redact commits today either — out of scope |
| Filenames containing sensitive identifiers | Unlikely | Re-scan |

The gap list is approximate until E3-CONFORMANCE corpus is captured (see [checkpoint-schema.md §4](./checkpoint-schema.md#4-per-agent-extension-surface-a-markers)).

## 3. Telemetry Isolation

Entire ships with **PostHog telemetry** with an env-var opt-out (per upstream docs and standard PostHog patterns). This telemetry is the **Entire process's** outbound traffic. CCDash:

- Does not invoke the `entire` binary in the primary read path (per ADR-011, CLI-wrap is opt-in only). PostHog is not triggered by CCDash's read path.
- Does not inherit any PostHog SDK. Parsing checkpoint JSON does not initialize an Entire client, does not import Entire code, and does not produce outbound HTTP. CCDash's existing OTEL/PostHog posture is unchanged.
- Documents the relationship in the operator guide: "If you have set `ENTIRE_TELEMETRY_DISABLED=true` (or whatever upstream variable name is canonical at install time), CCDash will not re-enable Entire's telemetry. CCDash's own telemetry posture is independent."

**Action item for the operator guide (Phase 8 docs):** confirm the exact opt-out env variable name from upstream docs and link it.

## 4. Local-First Posture

CCDash's local-first invariant: no agent-session data leaves the user's machine without explicit opt-in. Entire ingest preserves this:

- Branch-parse reads local git objects only (per ADR-011).
- The `git fetch` polling mode (ADR-013) uses the user's existing git credentials and fetches **from the user's own remote** (i.e., the repo they were already pushing/pulling). No CCDash-controlled endpoint is contacted.
- No data is shipped to Entire's cloud by CCDash. (The user's own `entire` binary may, depending on their configuration; CCDash does not change this.)

## 5. PII / Sensitive-Content Audit Surface

Sessions can contain user names, file contents, commit messages, model responses. CCDash today already stores these for `FilesystemSource` sessions; the Entire integration does not introduce a new sensitive-data category. The audit surface for Entire ingest is therefore:

- The CCDash database (already protected by workspace-scoped auth per ADR-008).
- The transcript blobs resolved lazily via `GitReader` (per ADR-011 §Transcript Resolution).
- The cursor file (`ingest_cursors` row), which records the last-seen checkpoint ID — not sensitive.

## 6. Outstanding Items

- **Phase 8 docs entry**: privacy section additions covering Entire ingest, redaction posture, telemetry isolation, and the explicit "we do not re-export to Entire cloud" statement.
- **E3-CONFORMANCE corpus**: Once captured, validate the redaction-gap list above against actual checkpoint content.
- **Upstream issue (optional)**: file an issue with `entireio/cli` requesting the exact name of the telemetry-opt-out env var be surfaced in `entire --help`. See [upstream-feedback memo](./upstream-feedback-memo.md).
