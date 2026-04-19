---
title: Feature-Session Linkage Guide
description: Understanding eventual consistency in CCDash feature-to-session relationships
audience: operators,developers
tags: [eventual-consistency, sessions, features, troubleshooting]
created: 2026-04-14
updated: 2026-04-14
category: operations
status: active
related: ["cli-user-guide.md", "enterprise-session-intelligence-runbook.md"]
---

# Feature-Session Linkage Guide

## Overview

CCDash links agent sessions to features via an `entity_links` table in its database. This relationship is **eventually consistent**: links are written asynchronously by the background filesystem sync engine, not inline with REST requests or CLI commands. This guide explains how linkage works, why there is lag, and how to troubleshoot missing sessions.

### What Gets Linked

- **Session**: An agent's execution log (`.jsonl` file) parsed into the database
- **Feature**: A project artifact (code, design doc, progress file) or task ID
- **Link**: A database row in `entity_links` with `link_type='related'`, created when the sync engine discovers a reference from session to feature

A session links to a feature when:
1. The session's frontmatter or payload contains a `featureId` or `feature_id` field, OR
2. The sync engine's reference extraction discovers a feature slug in the session transcript

## Why Linkage is Eventually-Consistent

The CCDash architecture separates real-time APIs from background indexing:

1. **Session imported** → Session log file arrives in the filesystem
2. **Next sync pass** → Worker's `SyncEngine` wakes up, scans for changed files
3. **Parse & discover** → Session is parsed; reference extraction runs (feature slugs, links)
4. **Write links** → `entity_links` rows are inserted into the database
5. **APIs read** → REST and CLI queries now see the linked sessions

This design trades immediate consistency for operational simplicity: the worker processes changes on a fixed schedule, avoiding complex distributed transactions or lock contention.

## Expected Behavior

### Local Development

- **Lag**: Typically **seconds to 15 seconds**
  - Worker wakes on a polling interval (usually 5–10 seconds for development)
  - Parse + sync for typical feature may take 1–3 seconds
- **Symptom**: A newly created or updated session doesn't appear in `ccdash feature sessions <id>` until the next poll cycle

### Production Deployment

- **Lag**: Typically **minutes** (depends on volume and infrastructure)
  - Sync intervals are longer to reduce load on shared database
  - High session throughput may defer processing

## Authoritative Session List

Both `ccdash feature show` and `ccdash feature sessions` read the same database field (`entity_links` joined with sessions). **The two commands are incapable of disagreeing** at the API level; if you observe a discrepancy:

1. Verify both commands target the same project and feature ID
2. Check `--target` is consistent between invocations (e.g., `--target local` vs. `--target api`)
3. If still seeing disagreement, the issue lies outside the linkage mechanism (e.g., clock skew, network error)

## Troubleshooting

### Session appears in `ccdash session list` but not in `ccdash feature sessions <id>`

**Likely cause**: The sync engine has not yet run, or link extraction failed.

**Check**:
1. Confirm the session's frontmatter contains the feature ID:
   ```bash
   ccdash session show <session-id> --json | jq '.feature_id'
   ```

2. If `feature_id` is missing, the session wasn't linked. Update the session metadata or manually add a frontmatter entry.

3. If `feature_id` is present, wait for the next sync cycle (typically 5–15 seconds in dev, longer in production).

### How to Force a Refresh

- **`ccdash target check local`** is a read-only health check; it does not trigger a sync.
- **Reliable way**: Wait one sync interval and retry. Most deployments poll every 5–15 seconds.
- **Alternative**: Restart the worker process if sync has stalled:
  ```bash
  npm run dev:worker
  # or
  pkill -f "python.*backend.worker"
  ```

### Verify Linkage After Waiting

```bash
# Fetch the feature's sessions
ccdash feature sessions FEAT-001 --json

# Or get full forensics
ccdash feature show FEAT-001 --json | jq '.linked_sessions'
```

If sessions still don't appear, check the worker logs for parse or database errors.

## API Contract

Both endpoints read the same authoritative field:

- **`GET /v1/features/{id}`** → Returns `linked_sessions` array
- **`GET /v1/features/{id}/sessions`** → Returns the same `linked_sessions` array

Both are sourced from `entity_links.get_links_for("feature", feature_id, "related")` in the database.

## Summary

| Question | Answer |
|----------|--------|
| When are links created? | During the next background sync cycle after a session is imported |
| How long does it take? | 5–60 seconds in dev; minutes in production (depends on sync interval) |
| Are the two feature-sessions endpoints different? | No; both read the same database field |
| How do I force a refresh? | Wait for the next sync, or restart the worker |
| What if linkage is broken? | Check session frontmatter has `featureId`; verify sync logs for errors |
