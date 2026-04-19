---
title: CLI Timeout Debugging Guide
description: Diagnose and fix CLI timeout issues (exit code 4) on slow endpoints
audience: operators, developers
tags: [cli, timeout, troubleshooting, performance]
created: 2026-04-15
updated: 2026-04-15
category: Troubleshooting
status: stable
related: ["query-cache-tuning-guide.md", "CLAUDE.md"]
---

## Symptom

CLI exits with "timed out" error or exit code 4 on slow endpoints.

## Quick Fix

Increase timeout via flag or environment variable:

```bash
# Per-command flag (highest precedence)
ccdash --timeout 120 feature show FEAT-123

# Environment variable
export CCDASH_TIMEOUT=120
ccdash feature show FEAT-123
```

**Precedence order:**
1. `--timeout` CLI flag
2. `CCDASH_TIMEOUT` environment variable
3. Default: 30 seconds

## Diagnose

Check active timeout configuration:

```bash
# Show active timeout and its source (flag / env / default)
ccdash doctor

# Per-target timeout check
ccdash target check local
```

## Eventual-Consistency Note

For `ccdash feature show`, the `linked_sessions` field may lag briefly. The CLI surfaces a `sessions_note` hint. If session linkage appears stale:

- Retry after a few seconds (sync engine catches up)
- Use `ccdash feature sessions <id>` for authoritative linked sessions

## When to Escalate

Consistent timeouts >120s on non-slow endpoints indicate backend/database issues:

```bash
# Inspect worker logs
npm run dev:worker

# Check backend logs for errors
npm run dev:backend

# If OTel is wired, inspect latency metrics
```

**Related:** See `docs/guides/query-cache-tuning-guide.md` for cache and performance tuning.
