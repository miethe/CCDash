# Worknote — `/sessions` live sessions + subagent threading

**Date:** 2026-08-12
**Branch:** `fix/sessions-live-and-subagent-threading`
**Reported symptoms (NUC web app):** (1) live sessions don't appear on `/sessions`;
(2) child sessions spawned by a root orchestrator aren't linked to their parent — all render as parents.
**Verdict:** presentation layer. Backend data and API contract are both correct.

## Evidence the backend is healthy

Queried the operative DB directly (node Postgres `10.42.10.76:5440`, schema `public` — note:
NOT schema `ccdash` despite `storageSchema: "ccdash"` in `/api/health`; only
`session_embeddings` lives in schema `app`).

| Check | Result |
|---|---|
| `max(updated_at)` | 2 min old — Mac relay alive, not the hung-zombie failure mode |
| Total sessions | 21,814 |
| Subagent rows | 5,761 (`session_type='subagent'`, `thread_kind='subagent'`) |
| `subagent_parent_id` / `parent_session_id` / `root_session_id` | all populated |
| Parent IDs resolving to real rows | 5,720 / 5,761 = **99.3%** |
| `root_session_id` populated | 21,814 / 21,814 = **100%** (resolves 100% for non-subagents) |
| API list DTO fields | `parentSessionId`, `subagentParentId`, `rootSessionId`, `threadKind` all present |
| Node deploy currency | `65b14d2`, ~5 commits behind main (routing-rollup + docs only); containers rebuilt 2026-08-12 10:40 |

`started_at` is a **TEXT** column (ISO-8601, so lexical sort == chronological). Cast before
comparing to `timestamptz` or Postgres raises `operator does not exist: text > timestamp with time zone`.

## Root cause 1 — session filter panel wired to a no-op stub

`contexts/DataContext.tsx` (~286):

```ts
const sessionFilters: SessionFilters = {};
// eslint-disable-next-line @typescript-eslint/no-empty-function
const setSessionFilters = useCallback((_filters: SessionFilters) => {}, []);
```

`components/SessionInspector.tsx` calls `useSessionsQuery({ projectId })` at **two** sites
(~4125, ~5782) with **no `filters` argument**. So `getSessions({})` sends no
`include_subagents`; `backend/routers/api.py:637` applies its default `False`; and
`backend/db/repositories/sessions.py:847-848` adds
`(session_type IS NULL OR session_type != 'subagent')`.

**Every subagent is excluded from `/sessions`.** Measured against the node API:

```
CCDash      total=2104 (vs 2411)  subagents_on_page=0  →  307 hidden
intenttree  total=1505 (vs 2128)  subagents_on_page=0  →  623 hidden
skillmeat   total=3075 (vs 4754)  subagents_on_page=0  → 1679 hidden
```

The `include_subagents: filters.include_subagents ?? true` at ~4080 is only the filter panel's
**local** state — checking the box writes into the no-op setter. The entire filter panel on
`/sessions` is inert (status, thread_kind, date ranges, model — all dead), not just this field.

## Root cause 2 — orphaned children promoted to roots

`buildSessionThreadForest` (~1200-1237) resolves parents **only within loaded pages**:

```ts
const parentId = candidateParents.find(id => !!id && nodes.has(id));
if (!parentId || parentId === session.id) return;            // gives up silently
...
sessions.forEach(s => { if (!attached.has(s.id)) roots.push(...) });  // becomes a ROOT
```

Latent even after fixing RC1, because the list is `started_at desc` with `limit=50` and parents
are routinely far from their children — e.g. subagent `S-agent-a4fe76d807aa117d2` started
`2026-08-12T15:56`, its parent root started `2026-08-11T20:40`, **19 hours earlier**.

**Fix chosen:** group the forest by `rootSessionId` (100% populated), preserving real multi-level
nesting via `parentSessionId`/`forkParentSessionId` when that parent is loaded; otherwise attach
under the family root (placeholder node if the root itself isn't loaded). A session with a
`parentSessionId`, `forkParentSessionId`, or non-self `rootSessionId` must never become a root.

## Root cause 3 — Live In-Flight derived from page position, not liveness

`isSessionLiveInFlight` (~186) is correct in isolation — replayed against the node's real page 1 it
correctly returned 2 live CCDash sessions. But `activeSessions` / `activeSessionThreadRoots`
(~6100-6118) apply it only to loaded pages. Two failure modes:

- **Live subagents are structurally invisible** (excluded by RC1). During orchestration the
  in-flight work *is* the subagents — at 15:22 today `intenttree` had 4 live subagent sessions
  that could never appear.
- **Long-running orchestrators age off page 1.** Churn is 70–77 root sessions/24h on
  `intenttree` / `skillmeat` / `agentic-meta-dev` against a 50-row page, so anything running
  longer than ~16h drops out of the loaded window while still live. `S-724fa4e8` (started
  `08-11 20:43`, still updating at `16:28`) sits at rank 7 and drifting.

**Fix chosen (operator decision 2026-08-12):** client-side live slice now
(`status=active&include_subagents=true`, limit 200, merged deduped by id, existing 10-min
freshness gate retained), backend freshness-gated live-list endpoint as a follow-up.

## Follow-ups (not in this branch)

1. **Zombie active sessions — backend.** 613 of 617 `status='active'` rows are stale; only 4 are
   fresh within 15 min. The UI is safe because it freshness-gates, but the worker is not closing
   sessions, so `status` alone is unreliable for any consumer that trusts it.
2. **Backend live-list endpoint.** Today only `/api/agent/live/active-count` exists (count only,
   freshness-gated per `sessions.py:count_active_sessions`). The list endpoint supports `status`
   but has no freshness gate, so `status=active` alone returns the 617 zombies. Add a
   freshness-gated live list or an `updated_since` filter.
3. **ICA gateway system-prompt append (unproven).** This session's system prompt contained
   `Do not call the AgentTool unless the user requested it`, which is not present in any local
   config (`~/.claude/settings*.json`, output styles, either CLAUDE.md, `~/ica-claude.sh`,
   `~/sub-claude.sh`, `~/.claude/ica-settings.json`, env). Likeliest source is a server-side
   append at the ICA gateway — which would suppress delegation in every ICA-carried session.
   Needs an out-of-session probe to confirm.

## Reproduction recipe

```bash
# operative DB is the NUC PG; local .env already points at it
set -a; . ~/.config/aos/secrets.env; set +a
# FE default (no include_subagents) — subagents absent
curl -s -H "Authorization: Bearer $CCDASH_TOKEN" \
  "http://10.42.10.76:8090/api/sessions?offset=0&limit=50&sort_by=started_at&sort_order=desc&project_id=ccp-2a984316f63a" \
  | jq '[.total, ([.items[]|select(.sessionType=="subagent")]|length)]'
# → [2104, 0]

# with the flag the FE never sends
curl -s -H "Authorization: Bearer $CCDASH_TOKEN" \
  "http://10.42.10.76:8090/api/sessions?offset=0&limit=50&sort_by=started_at&sort_order=desc&include_subagents=true&project_id=ccp-2a984316f63a" \
  | jq '[.total, ([.items[]|select(.sessionType=="subagent")]|length)]'
# → [2411, 2]
```
