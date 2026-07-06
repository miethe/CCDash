---
schema_version: 1
status: handoff-ready
updated: 2026-07-06
source_plan: /Users/miethe/dev/homelab/development/agentic_meta_dev/.claude/plans/aos-universal-correlation-ids-v1.md
contract: /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/aos-correlation.md
---

# AOS Correlation Indexing v1 - CCDash Handoff

## Goal

Let CCDash ingest and search AOS IDs from final-turn footers, local sidecar events, and linked
Operator/IntentTree records.

## Required Work

- Add ingestion for `AOS-ID: urn:aos:turn:<uuid>` in session transcripts.
- Add sidecar-event ingestion for `$AOS_ID_HOME/events.jsonl` pointers without storing prompt or
  response bodies.
- Add derived indexes/search for turn, session, run, feature, artifact, app, service, and trace UUIDs.
- Add a session-detail affordance to show/copy the leaf AOS turn ID and navigate to parent
  run/feature/artifact where known.
- Preserve existing transcript intelligence and CCDash session ID behavior.

## Acceptance

- Search by a turn UUID resolves to its session and any linked run/artifact aliases.
- Missing sidecars, stale transcript paths, malformed JSONL, and unknown UUIDs show unresolved
  status rather than crashing ingestion or UI.
- UI copy action exposes only the leaf `AOS-ID` footer unless a user opens details.

## Validation

Add backend ingestion tests, a fixture with duplicate/malformed sidecar lines, and a focused UI/API
test for copyable AOS-ID display.
