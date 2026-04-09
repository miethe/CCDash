---
title: "ADR-001: SSE for Real-time Updates in VSCode Extension"
type: "adr"
status: "accepted"
created: "2026-04-02"
parent_prd: "docs/project_plans/PRDs/features/vscode-ccdash-extension-v1.md"
tags: ["adr", "sse", "realtime", "vscode", "extension"]
---

# ADR-001: SSE for Real-time Updates in VSCode Extension

## Status

Accepted

## Context

The VSCode CCDash extension requires real-time updates for session execution progress, document changes, and task status. The CCDash backend already implements a mature Server-Sent Events (SSE) endpoint at `GET /api/live/stream` with topic-based subscriptions and cursor replay semantics. No WebSocket endpoint currently exists.

The extension must update users immediately when:
- Session execution state changes
- Tools are invoked and complete
- Document content is modified
- Task status transitions occur

## Decision

**Use Server-Sent Events (SSE)** for all real-time updates in the VSCode extension.

### Why SSE

- **Backend alignment**: Existing `/api/live/stream` endpoint requires zero additional backend work
- **Standard HTTP**: Works over HTTP/1.1 and HTTP/2 — no protocol upgrade needed
- **Native reconnection**: EventSource API handles automatic reconnection with exponential backoff
- **Topic subscriptions**: Cursor-based replay allows the extension to catch missed events after reconnection
- **Simplicity**: One-way streaming is sufficient; mutations use REST

## Decision Drivers

1. Existing backend SSE infrastructure is production-ready
2. SSE subscriptions are cheaper than polling for real-time monitoring
3. Built-in browser/Node.js EventSource support (via `eventsource` package)
4. Topic-based filtering matches extension's subscription model

## Alternatives Considered

1. **WebSocket**: Would require new backend WebSocket infrastructure. Bidirectional but adds connection management complexity. Not currently implemented.

2. **Polling**: Simple but scales poorly. 2–5 second intervals create staleness; 500ms intervals waste resources. Not viable for real-time execution tracing.

3. **Long polling**: Hybrid compromise but adds hidden complexity without SSE's automatic reconnection. Harder to test.

## Consequences

- Extension API client must implement SSE client logic using `eventsource` package or native fetch streaming
- Reconnection recovery depends on cursor tracking; lost cursors require full resync
- Mutations still use REST POST/PATCH endpoints; SSE is receive-only
- Extension must gracefully degrade if SSE stream fails (fall back to polling with user notification)
