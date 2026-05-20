---
schema_version: 2
doc_type: design_spec
title: "System Metrics Widget API Hardening - Design Spec"
status: draft
maturity: idea
feature_slug: system-wide-metrics
prd_ref: docs/project_plans/PRDs/features/system-wide-metrics-v1.md
plan_ref: docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md
created: 2026-05-20
updated: 2026-05-20
category: features
tags: [metrics, widget, api, auth, deferred]
related_documents:
  - .claude/worknotes/system-wide-live-metrics-spike/spike.md
---

# System Metrics Widget API Hardening

## Problem Statement

`GET /api/agent/system/active-count` is widget-friendly by accident — the payload is small, the cache header is set to `max-age=30`, and the DTO is stable. But it is not yet *intentionally* a public surface. If a desktop widget feature is built on top of this endpoint, the API contract has to harden along several axes: stable versioning, auth scoping appropriate for a non-browser client, possibly delta updates instead of full snapshot polling, and explicit rate limiting.

Promotion trigger (from plan §Deferred Items DEF-003): a desktop widget feature enters planning.

## Known Constraints

- The endpoint is currently unauthenticated (CCDash is local-first). A widget API consumer is, by definition, a separate process — it may run with a different identity than the dashboard.
- The DTO is stable for v1, but adding fields without a versioning policy will break any external widget on every minor bump.
- `Cache-Control: max-age=30` matches the chip's 30s poll; a widget on a different cadence (e.g., menu-bar 60s, BTT widget 10s) may want a different value.
- The endpoint returns *all* projects. A widget showing only the active project would do well with a `?project_id=` filter that bypasses the fan-out entirely.

## Open Questions

- Versioning: do we mount a `/api/v1/agent/system/active-count` alias, or use a header-based version negotiation?
- Auth: is a per-widget token model needed, or does the v1 widget assume localhost trust like the dashboard?
- Delta protocol: WebSocket / SSE push for sub-second freshness, or stick with polling?
- Rate limiting: what is reasonable for a multi-widget host (5 widgets × 1 poll/sec = 5 RPS)?
- Field expansion: do widget consumers need session breakdowns by model / agent type, or just the total?

## Notes

The simplest first step when this spec is promoted is to freeze the current DTO as the v1 widget contract (matching the chip's consumed surface) and add a `?include=` query param for optional new fields. That keeps the chip and the widget on the same wire format while letting the widget opt-in to extensions.
