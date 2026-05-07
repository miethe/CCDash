---
audience: operators, security
scope: artifact-intelligence-privacy-audit
status: signed-off
last_reviewed: 2026-05-07
---

# Artifact Intelligence Privacy Audit

This audit covers the CCDash artifact intelligence snapshot and rollup paths shipped for the SkillMeat exchange.

## Checklist

| Area | Result | Operator note |
| --- | --- | --- |
| `ArtifactUsageRollup` payload | Pass | Export schema contains identifiers, aggregate usage, effectiveness scores, and advisory recommendation metadata only. |
| `SnapshotFetchRequest` assumptions | Pass with assumption | Snapshot fetch is an implicit `GET /api/v1/projects/{project_id}/artifact-snapshot` plus `collection_id`; project and collection IDs must be SkillMeat identifiers, not local paths, emails, or secrets. |
| Recommendation embeds | Pass | Embedded recommendations are advisory fields: type, confidence, rationale code, next action, bounded evidence strings, affected artifact IDs, and scope. |
| Local `user_scope` behavior | Pass | Local mode either emits the configured pseudonym or omits `userScope`; hosted mode preserves the persisted principal scope. |
| Snapshot and rollup logs | Pass | Logs record operational status and counts. They do not include auth headers, API keys, full rollup payloads, content hashes, prompts, transcripts, code, or local paths. |

## Prohibited Fields

These fields must not appear in exported rollups, recommendation embeds, snapshot-fetch logs, or rollup-export logs:

`raw_prompt`, `prompt_text`, `transcript_text`, `message_content`, `source_code`, `code_snippet`, `absolute_path`, `file_path`, `unhashed_username`, `user_email`, `api_key`, `token`, `secret`.

## Findings

- `ArtifactUsageRollup` is protected by an explicit field allowlist before export.
- The verifier rejects non-allowlisted fields and sensitive string values such as absolute paths, email-shaped values, and code-like blocks.
- The snapshot fetch path does not send local project metadata beyond the configured SkillMeat project and collection identifiers.
- The rollup exporter skips payloads that fail the privacy guard instead of posting them to SkillMeat.
- Local user rollups do not expose raw usernames; operators choose pseudonymous scope or omission with `CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE`.

## Sign-off

T6-002 privacy audit is signed off for the current V1 contract on 2026-05-07.

Reopen this audit before adding new recommendation evidence fields, raw snapshot metadata, per-user local identity, or debug logging around snapshot or rollup payloads.
