# Measured data availability — IntentTree event log as the dashboard's source

**Measured 2026-08-14** against the live IntentTree API (`http://10.42.10.76:8032`, workspace
`ws_01KV8VMWX9EJ6VDQKEBMYQZRXG`, tree `tree_01KVTH95F7P7CXK3QH9ZMECM5T`) while planning
`node_01M009H6DGAKD5VCC8QCM0KP0K`. Every row below is an observed count, not an estimate.
**Do not restate these numbers from memory — re-measure before relying on them.**

## The read surface that exists

`GET /api/v1/events` — workspace-scoped domain event log, most recent first, keyset cursor.
- `workspace_id` **required** (422 without it). Optional ANDed filters: `tree_id`, `node_id`,
  `event_type`, `actor_type`, `limit`, `cursor`.
- Envelope: `{items, next_cursor, total}`. **`limit` is server-capped at 200** — a requested
  `limit=500` silently returned 200 items. Any consumer must page, never trust one call.
- Row shape (`IntentTreeEventRead`): `id, workspace_id, tree_id, node_id, event_type, actor_type,
  actor_id, payload, occurred_at, stream, correlation_id, routing, schema_version, published_at`.
- Live volume in this workspace: **11,867 events**.

Also present: `GET /api/v1/nodes/{node_id}/history` (field-level audit, `old_value`/`new_value`
wrapped as `{"value": …}` or null) and `GET /api/v1/workspaces/{id}/stream` (SSE).

## Per-event-type counts (workspace-scoped, measured)

| `event_type` | count |
|---|---|
| `node.created` | 3,941 |
| `node.updated` | 4,171 |
| `node.completed` | 745 |
| `node.blocked` | 91 |
| `node.deferred` | 3 |

Full `EventType` enum (43 values) includes `node.created/updated/completed/blocked/promoted/deferred`,
`edge.created`, `agent.run.*`, `outcome.attached`, `candidate.promoted/dismissed`, `spend.*`.

## AC1 component-by-component verdict

| AC1 component | Source | Verdict |
|---|---|---|
| weekly **created** trendline | `event_type=node.created` — 3,941 rows, `occurred_at` + `node_id` + `tree_id`, `payload={title,node_type}` | **GO** |
| weekly **completed** trendline | `event_type=node.completed` — 745 rows | **GO** |
| weekly **reopened** trendline | **No `node.reopened` event type exists.** Must be derived. | **GO, but derived** — see below |
| **self-caught ratio** | `actor_type` / `actor_id` | **NOT DERIVABLE TODAY** — see below |
| drill-through to rows | events carry `node_id`; `node.created` carries `title` | **GO** |
| zero model calls on render | pure DB/API read | **GO by construction** |

## Finding 1 — `reopened` is derived, not evented (bounded, tractable)

There is **no `node.reopened` event type**, and `node.updated` **carries no payload**: measured
**0 / 200** sampled `node.updated` events had a non-null `payload` (all 200 had `node_id`, all 200
were `actor_type=system`). So the event log records *that* a node changed, never *what* changed —
a reopen cannot be read off the event stream.

Derivation that does work, and why it is affordable: only a node that was **ever completed** can be
reopened, so the candidate set is the **745** `node.completed` rows, **not** all 3,941 nodes. For
each distinct `node_id` in that set, read `GET /api/v1/nodes/{node_id}/history?field=status` and
count transitions leaving a terminal status. Bound the work by node, not by tree size.

## Finding 2 — the self-caught ratio has no discriminator in the event log

Measured on the exact events the ratio needs:

- `node.created` + `actor_type=user`  → **0**
- `node.created` + `actor_type=agent` → **0**
- `node.created` + `actor_type=system` → **3,941**  (100%)
- `actor_id` was **null on 199 / 200** sampled events (all types).

Every write reaches IntentTree through one shared service token, so the actor collapses to
`system`. (Corroborated independently: `node history` on the subject node attributes every
creation-time field write to `service:system:shared-token`.) Across a 200-event mixed sample
`actor_type` did vary — `system` 171 / `agent` 28 / `user` 1 — but that variation is **not** on
`node.created`, which is the event the ratio is computed from.

Consequences, both load-bearing:
1. **No backfill is possible.** Historical rows are `system`; nothing can recover who filed them.
   This is the same permanence as CCDash's own launch-capture gap (`docs/guides/launch-time-capture-convention.md`).
2. **The real fix is upstream and out of scope here.** IntentTree already supports per-actor bearer
   tokens (`POST /api/v1/actors/{id}/tokens`, SoD auth provisioning DI-195); the shared token is a
   deployment choice, not a capability gap. Provisioning per-actor tokens would make `actor_type` /
   `actor_id` meaningful **from that day forward only**.

Proxy signals available on nodes today, both weak: a `finding` tag (17 of 200 sampled nodes — it
marks *that* something is a finding, not *who* caught it) and `meta.origin` (7 of 200).

**Required posture (house doctrine, not a preference):** report an explicit `unknown` bucket and
never silently divide. CCDash already enforces exactly this shape for
`sessions.ica_spend_attribution` — the closed vocabulary + `decide_attribution` in
`backend/parsers/ica_spend.py`, where a delta is stored *only* for the `attributed` verdict and every
other verdict stores NULL. Mirror that: a ratio computed over an unattributable population must
render as unknown, not as a number.

## Architectural fit in CCDash (no new pattern needed)

- Ingest → derived cache DB → repository → transport-neutral query service → REST → FE is the
  existing spine. New cross-domain reads belong in
  `backend/application/services/agent_queries/` first (per CLAUDE.md), then REST/CLI/MCP.
- The only intent-node surface that exists today is
  `backend/application/services/agent_queries/intent_node_cost.py` + the
  `INTENT_NODE_LINK_*` block in `backend/db/repositories/entity_graph.py`. It reads CCDash's **own**
  declared `entity_links` rows — **CCDash holds no IntentTree lifecycle-event data at all.**
  Acquiring it is net-new work, and it is the largest single piece of this feature.
- Any new column needs **dual DDL** (SQLite + Postgres `_ensure_column`) in the same change set,
  plus a `COLUMN_PARITY_DRIFT_ALLOWLIST` check.
- Constraint 4 (no model call on the read/render path) is satisfied by construction.

## Recipe to re-measure

```bash
set -a; . ~/.config/aos/secrets.env; set +a
U=http://10.42.10.76:8032; WS=ws_01KV8VMWX9EJ6VDQKEBMYQZRXG
curl -s "$U/api/v1/events?workspace_id=$WS&event_type=node.created&actor_type=user&limit=1" \
  -H "Authorization: Bearer $INTENTTREE_API_TOKEN" | python3 -c 'import json,sys;print(json.load(sys.stdin)["total"])'
```

---

## Frontend reuse surface (measured 2026-08-14 — read these before designing a new chart)

An analytics module already exists. **Extend it; do not build a parallel chart stack.**

- `components/Analytics/AnalyticsDashboard.tsx` — the existing dashboard shell
- `components/Analytics/TrendChart.tsx` — **already a trendline chart**; the closest existing
  primitive to this feature's core visual
- `components/Analytics/primitives/InteractiveChartCard.tsx` — the card wrapper, with tests at
  `primitives/__tests__/InteractiveChartCard.test.tsx` and
  `primitives/__tests__/InteractiveChartCardChartConfig.test.tsx`
- Resilience precedent worth copying:
  `components/Analytics/__tests__/AnalyticsDashboardResearchResilience.test.tsx`

Versions in `package.json`: recharts `^3.7.0`, react `^19.2.4`, react-router-dom `^7.13.0`,
`@tanstack/react-query` `^5.100.14`.

### recharts 3.x hazards — three known traps, all previously hit in this repo

These are named risks for any milestone that adds a chart, not hypotheticals:

1. **Pie charts render blank for ~500ms** unless `isAnimationActive={false}`.
2. **Never put a `key` on `ResponsiveContainer`** — it causes an infinite render loop that blanks
   the whole page.
3. **A chart that writes to `searchParams` loops** — this specifically broke `FeatureDetailShell`
   and `SessionInspector`. Drill-through navigation is exactly the feature most likely to reach for
   `searchParams`, so design the drill-through interaction against this constraint from the start
   (route param or local state, or verify no write-on-render).

Consequence for planning: **every chart-touching milestone needs a runtime browser smoke check**
(per CLAUDE.md's runtime smoke gate and plan rule R-P4) — a clean unit-test pass has repeatedly not
caught any of the three failures above.

### Caching tiers to honour

Per `docs/guides/feature-surface-architecture.md`: server-side `@memoized_query` (~600s TTL) plus
client TanStack Query staleTime (30s-5min). Query hooks live in `services/queries/`, keyed via the
registry at `services/queryKeys.ts`.

⚠️ **Postgres-only cache-write hazard**: `PostgresCacheBackend.aset` previously stringified pydantic
return values via an unguarded `json.dumps(default=str)`, 500-ing the whole `@memoized_query` class
on the Postgres backend while local SQLite could not reproduce it (fixed on main `579aaf2`). Any new
`@memoized_query` surface must be exercised against Postgres, not only SQLite.
