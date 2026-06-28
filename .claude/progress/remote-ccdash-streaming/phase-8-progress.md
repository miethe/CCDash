---
schema_version: 2
doc_type: progress
prd: remote-ccdash-streaming
feature_slug: remote-ccdash-streaming
phase: 8
status: completed
created: 2026-06-28
updated: 2026-06-28
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
owners: [documentation-writer]
tasks:
  - id: T8-001
    status: completed
    assigned_to: [documentation-writer]
    evidence: ["doc:CHANGELOG.md"]
  - id: T8-002
    status: completed
    assigned_to: [documentation-writer]
    evidence: ["doc:README.md", "doc:CLAUDE.md"]
  - id: T8-003
    status: completed
    assigned_to: [Opus]
    evidence: ["doc:docs/project_plans/adrs/adr-014-remote-session-ingest-transport-ndjson-http.md", "doc:docs/project_plans/adrs/adr-015-local-daemon-packaging-as-ccdash-cli-subcommand.md"]
  - id: T8-004
    status: completed
    assigned_to: [Opus]
    evidence: ["doc:docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md"]
---

# Phase 8 — Documentation Finalization

- **T8-001** CHANGELOG `[Unreleased] ### Added`: remote ingest + daemon, workspace auth +
  multi-project routing, source attribution + ingest health.
- **T8-002** README "Why CCDash" remote-operation bullet; CLAUDE.md "Key Conventions" remote
  session ingest bullet (endpoints, daemon, ADRs, health, guides).
- **T8-003** ADR collision renumber: streaming `adr-006-remote-session-ingest` → **ADR-014**,
  `adr-007-local-daemon` → **ADR-015** (DB ADR-006/007 untouched); all full-stem links +
  in-set bare references updated.
- **T8-004** Plan finalized: `status: completed`, `updated`, `commit_refs`, `files_affected`;
  Phase 5 extracted; deferred items recorded; `plan-completion.md` written.

**Deferred-items policy**: DEF-001..DEF-005 target spec paths remain unauthored (targets, not
blockers) and are carried to `entire-io-checkpoint-ingest-v1.md` per the v1 deferral policy.
