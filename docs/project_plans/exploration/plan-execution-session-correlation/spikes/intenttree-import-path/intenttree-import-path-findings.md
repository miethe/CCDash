---
schema_version: 2
doc_type: report
report_category: spike_findings
title: "IntentTree-as-Import-Path — Spike Findings"
status: complete
created: 2026-07-26
feature_slug: plan-execution-session-correlation
updated: 2026-07-28
verdict: conditional
superseded_verdict: no-go
confidence: 0.8
related_documents:
  - docs/project_plans/exploration/plan-execution-session-correlation/intenttree-import-handoff.md
  - docs/project_plans/exploration/plan-execution-session-correlation/plan-execution-session-correlation-feasibility-brief.md
  - docs/project_plans/PRDs/integrations/intenttree-session-correlation-v1.md
  - docs/project_plans/design-specs/rf-intenttree-intent-id-resolution.md
  - docs/project_plans/reports/feature-retro-linkage-gap-analysis.md
---

# IntentTree-as-Import-Path — Spike Findings

> ### ⚠️ VERDICT REVISED 2026-07-28 — was `no-go`, now **`conditional`**. Read §0 and §8 first.
>
> **Architecture A (consume the tree instead of parsing files): still NO** — §4 stands unchanged.
>
> **Architecture B (IntentTree pushes correlation): CONDITIONAL, not rejected.** The original
> write-up established that IntentTree links 1 session per run and concluded that this killed B as
> the Slice-2 attribution vehicle. **That inference was wrong.** CCDash already owns the
> orchestrator→subagent fan-out, so one linked orchestrator session is *sufficient* — see §8.
> B's real blocker is **adoption** (IntentTree has never dispatched), not missing capability.
>
> Parent plan is still unchanged in shape: Slice 1 stays file-based/GO (needed for the 16,658-session
> historical corpus regardless); Slice 2's *mechanism* is now credible and its precondition is named.

## 0. Headline

The handoff's centerpiece argument — **F-2**, "an IntentTree dispatcher knows which node it
dispatched to, so `node_id` dissolves the Slice-2 subagent-attribution gap" — is **half right**, and
the correction matters more than the original finding.

**Measured fact (unchanged):** IntentTree links **one** session per run. An orchestrator that fans
out to five subagents produces **1** linked session, not 6. `AgentRun` has no `parent_run_id`,
`ccdash_session_id` is a single scalar column, and no code path registers a `Task()`-spawned child.

**Correct inference (revised, §8):** that does **not** matter, because CCDash already derives the
full family graph from log fields alone — `workflow_id` is populated on **16,658/16,658** sessions
and `subagent_parent_id` on **3,956/3,956** subagent sessions, with 100% family coherence. A single
`node_id` landed on the orchestrator propagates across its whole `workflow_id` family and reaches
all six sessions. **The fan-out is CCDash's job and CCDash already does it.**

So F-2's conclusion survives — via a different mechanism than the handoff proposed, and one that
requires no IntentTree change at all.

Separately, the `aos-ccdash` node tree is far thinner than F-4/F-5 implied: **3 plans of 132**, last
synced **2026-06-24**, using 2 of 18 node types, with no `wave` or `gate` node type and AC that is
plan-level inheritance rather than per-task authorship.

The importer itself, however, is **more capable than the deployed tree suggests** (§3 OQ-2) — so the
case against architecture A rests on *freshness, coverage, and the AOS constraint*, not on the
importer being weak. Stating that plainly matters, because "IntentTree's importer is bad" would be
the wrong lesson to carry forward.

---

## 1. Adjudication of the handoff's pre-established findings

| ID | Handoff claim | Verdict | Basis |
|----|---------------|---------|-------|
| **F-1** | An unimplemented HIGH-priority PRD specs the seam | ✅ **Confirmed** | PRD is `status: draft`, `implementation_plan_ref: null`; no `session_correlations` table, no `backend/db/repositories/correlations.py`, no `backend/routers/correlations.py` exist |
| **F-2** | `node_id` in the registration payload dissolves the subagent gap ⭐ | ❌ **REFUTED** | 1 session per run, no run hierarchy, no child registration — §3 OQ-5 |
| **F-3** | CCDash backend has no IntentTree data-import path | ✅ **Confirmed** | Only CORS/capability/comment plumbing; also **no IntentTree HTTP client at all**, which is itself the blocker |
| **F-4** | IntentTree holds a live, populated ccdash tree | ⚠️ **Materially overstated** | 271 nodes from **3** plans (2.3% of 132), frozen since 2026-06-24 — §3 OQ-1 |
| **F-5** | Node model is rich; AC modelled per node | ⚠️ **Half-right — right about the model, wrong about the payoff** | The model and importer *are* rich (§3 OQ-2: edges, blockers, validation runs, external links, `--ac-as-steps`). But as deployed for ccdash: `branch`/`repo`/`scores`/`external_refs`/`assignee`/`slug` all **0/271**, and AC is not per-node — 246 nodes share only 4 distinct lists via default container inheritance. The claim "AC as a node field, which CCDash's parsers do NOT extract" does not yield CCDash anything it cannot read from the same frontmatter |
| **F-6** | AOS constraint-#2 tension is the architectural crux | ✅ **Confirmed and decisive** | Reinforced by the empirical fidelity loss — derived-reading-derived would import a *lossier* projection than the files |

The 736 KB depth=2 dump referenced by the handoff was **not** a truncated sample — it is the entire
tree. `GET /api/v1/trees/{id}/nodes` reports `total: 271`.

> **Correction to a mid-spike misreading:** `sync_status` initially appeared to report 1568 bindings
> for the ccdash tree. The bindings endpoint **silently ignores `tree_id`** (its OpenAPI parameter
> list accepts only `node_id`, `source_artifact_id`, `sync_status`, `limit`, `cursor`). 1568 is
> workspace-wide across all 12 trees. Joining bindings to the ccdash node-id set gives **270**.

---

## 2. Environment / access facts (OQ-3)

| Property | Value |
|----------|-------|
| Base URL | `http://10.42.10.76:8032/api/v1` (agentic node `rocket-fedora`, LAN) |
| Auth | Bearer token **required on this deployment** — unauthenticated `GET /api/v1/trees` returns **401**. Note: `require_auth` is a **no-op when no token is configured** (`core/security.py:150-151`; `auth_enabled = bool(api_token)`, default `None`) — so the node is protected only because `INTENTTREE_API_TOKEN` is set there |
| Token location | `~/.claude.json` → mcp server `intenttree` → `INTENTTREE_API_TOKEN` |
| Health | `GET /healthz` (note: `/health` and `/api/health` 404) |
| OpenAPI | `GET /api/v1/openapi.json` — **156 paths** |
| Pagination | Cursor-based keyset (`Page{items,next_cursor,total}`); `DEFAULT_LIMIT` 50, `MAX_LIMIT` 200 (`core/pagination.py:27-28`) |
| Whole-tree read | ✅ `GET /api/v1/trees/{id}/graph` — every node + edge in one flat payload |
| Whole-subtree read | ✅ `GET /api/v1/nodes/{node_id}/subtree` (+`include_ancestors`, `include_siblings`) |
| Node list | `GET /api/v1/trees/{tree_id}/nodes` — filters `type`, `status`, `parent_id`, `updated_after` |
| Bindings | `GET /api/v1/work-item-sync/bindings` — **no `tree_id` filter** |

The read API is genuinely good — this is *not* the reason to reject architecture A. The reasons are
content fidelity, coverage, and the AOS constraint.

---

## 3. Open-question resolutions

### OQ-1 — Node-model fidelity ⚠️ *Capable in principle; thin as deployed*

**No `wave` or `gate` node type exists.** The `NodeType` enum (`models/enums.py:8-27`) is:

```
root, pillar, work_area, work_package, atomic_task, step, milestone, side_quest,
quick_win, shared_work, agent_loop, intent, note, decision, question,
run_request, review_request, document_link
```

Important nuance (established by leg B, and it cuts *against* an over-simple rejection):

- **Wave structure is not lost — it is flattened.** `sync_import` does read `wave_plan.phases[]`, using
  it to build phase containers and to emit `depends_on` DAG edges
  (`work_item_sync.py:1711-1758`, `1120-1157`). There is simply no *wave* containment level; wave
  semantics survive as phase-to-phase edges.
- **Gate criteria are captured but never queryable.** Plan-level `entry_criteria`/`exit_criteria`/
  `success_criteria`/`decision_gates` are copied verbatim into the feature container's `meta` dict
  (`work_item_sync.py:1025-1037`). No gate node type, no gate edge type, and — per leg B's explicit
  NOT-FOUND — **no code path anywhere surfaces them as actionable or queryable objects** distinct
  from generic JSON. For Slice 1's purposes ("gates as first-class entities") this is equivalent to
  not having them, but it is *not* data loss.
- **AC can be materialised as nodes** via the `--ac-as-steps` flag, which projects each AC string as
  a `STEP` child of its task (`work_item_sync.py:2032-2075`). The ccdash tree was **not** imported
  this way — it contains zero `step` nodes.

**Actual ccdash tree shape:**

| Metric | Value |
|--------|-------|
| Total nodes | **271** (`total` from the nodes endpoint) |
| Node types present | `atomic_task` 243, `work_package` 28 — **only 2 of 18** |
| Depth | 3 levels: 4 roots → 25 mid → 242 leaf |
| Bound to a source artifact | 270 / 271 |
| Distinct source artifacts | **3** |
| Level encoding | `feature:` ×3, `phase:` ×25, bare task-id ×242 |
| Status | completed 227, not_started 41, blocked 3 — yet tree `progress` reports **0.0** |
| Last synced | **2026-06-23 → 2026-06-24** (spike run 2026-07-26) |

The three imported plans are `branch-aware-planning-intelligence` (7 phases),
`ccdash-core-remediation` (11 phases), `ccdash-enterprise-edition-v1` (7 phases). CCDash has **132**
implementation plans, 56 PRDs, and 305 progress files on disk — so tree coverage is **2.3%**.

**`acceptance_criteria` is not per-node — and this is deliberate, not a bug.** 246/271 nodes carry
AC, but across those there are only **4 distinct AC lists** — 125 nodes share one, 88 another, 32 a
third.

Leg B identified the mechanism: **DI-152 container-field inheritance**. Per-task AC is authored-wins
(`work_item_sync.py:578-580`), but `_inherit_container_fields` copies the resolved phase-level (else
feature-level) AC array verbatim onto **every task whose own AC is empty**
(`work_item_sync.py:1277-1306`, `_INHERITABLE_LIST_FIELDS` at `:1188`). It is **on by default**
(`Settings.sync_inherit_container_fields = True`, `core/config.py:84`) and covered by a dedicated
integration test (`test_sync_container_inheritance.py:190,217`).

So the observed duplication reflects CCDash's plans not authoring per-task AC, plus an importer that
fills the gap by inheritance. Two consequences for architecture A: (1) a consumer **cannot
distinguish** an authored per-task AC from an inherited one without re-deriving from the source, so
any per-task AC join would be silently wrong; (2) the useful signal (feature/phase-level AC) is
equally available to CCDash directly from the plan frontmatter. Inheritance can be disabled per
request, but that yields *fewer* populated nodes, not better ones.

**The import is lossy.** `ccdash-core-remediation` has phase files on disk for
0, 1‑3, 4, 5‑6, 7‑8, 9, 10, 11, 12 — but produced phase nodes for
0, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12: **Phase 1 and Phase 4 are absent**.

**The "rich node model" is unpopulated** for ccdash: `branch` 0/271, `repo` 0/271, `scores` 0/271,
`external_refs` 0/271, `assignee_actor_id` 0/271, `slug` 0/271, `description` 40/271.
`meta` carries only `{"origin": "imported_plan", "planning_maturity": "shipped"}` — **no source-file
path**, so a node alone cannot be traced back to its plan; that requires the separate bindings table.

### OQ-2 — `sync_import` fidelity ⚠️ *Substantially more capable than the deployed tree implies*

**This is the finding that most complicates a simple rejection, so state it fairly:
`sync_import` is a genuinely capable importer.** It reads far more than `tasks[]`
(`services/work_item_sync.py`):

| Plan-file input | Where it lands |
|---|---|
| `tasks[]` **∪** `wave_plan.phases[].tasks` (unioned) | task nodes — `_flatten_frontmatter_tasks:889-942` |
| `wave_plan.phases[].depends_on` | `depends_on` DAG edges — `_build_edges:1711-1758` |
| per-task `acceptance_criteria`/`ac` | node AC, authored-wins — `:578-580` |
| plan/phase-level `acceptance_criteria` | container node AC, then inherited down — `:1096-1098`, `:1277-1306` |
| `entry_criteria`/`exit_criteria`/`decision_gates` | feature container `meta` only (never queryable) — `:1025-1037` |
| `blockers` | `BLOCKS` edges — `:1804-1837` |
| `validation_commands` | `ValidationRun` rows — `:2155-2216` |
| `prd_ref`/`plan_ref`/`commit_refs`/`pr_refs`/`files_affected` | `ExternalLink` / container `meta` — `:134-181`, `:2123-2153` |

**Node types it can produce**: `work_package` (feature + phase containers, `:1873-1876`),
`atomic_task` (default), `side_quest` (`DI-NNN`-shaped ids), `quick_win` (Tier-0 contracts) via
`infer_node_type:438-501`, and `step` only under `--ac-as-steps`. It never produces `milestone`,
`root`, `pillar`, `work_area`, or the v2 Command-Center types.

**Max depth 4**: Feature (`parent=None`, rootless-safe) → Phase → Task → Step(AC).

**Drift detection is a real 4-way comparison** — `compute_sync_status:847-866` compares two
independently recomputed SHA-256 fingerprints (`source_fingerprint:744-760`,
`node_fingerprint:763-823`) yielding `clean` / `changed_in_source` / `changed_in_intenttree` /
`conflict` / `stale`.

**But as deployed against ccdash, the projection is thin and drift-blind above task level:**

- Only three levels are present via `source_task_id` prefixes: `feature:<slug>` ×3, `phase:<name>`
  ×25, bare task ids ×242. No `step` nodes, no wave level, no gate objects.
- The 28 `feature:`/`phase:` container bindings all carry `source_fingerprint: null` and empty
  `raw_source_task`; only the 242 task bindings are fingerprinted. **A plan whose phase set changes
  can therefore never be reported as drifted** — which is consistent with the observed loss of
  `ccdash-core-remediation` Phase 1 and Phase 4 going unflagged.
- All 270 ccdash bindings report `sync_status: clean`, but nothing has re-run since 2026-06-24.
  Stale-clean and verified-clean are indistinguishable to a consumer reading this API.

**Bearing on the decision:** the importer's *capability* is not the problem. The problem is that
consuming its output means depending on a re-derivation that (a) is only as fresh as the last manual
`sync import`, (b) silently blends authored and inherited AC, and (c) cannot flag container-level
drift — for a hierarchy CCDash can compute directly from the same files it already parses.

### OQ-3 — Read API ✅ *Adequate; see §2*

The API is capable. The disqualifier is that consuming it makes CCDash's plan hierarchy depend at
runtime on a LAN service it has **no HTTP client for** — and building that client is exactly the
prerequisite `rf-intenttree-intent-id-resolution` identified and **deferred** (DF-007), for reasons
that still hold: no client/auth/config in `backend/config.py`, no resilience contract for a
first-ever pull-based dependency on an externally-owned service, and no validated operator pain
signal.

### OQ-4 — Opaque-ID resolution ❌ *Unsolved and unacknowledged*

The PRD's registration payload does carry `node_id`:

```json
"metadata": { "node_id": "node_xyz", "workspace_id": "ws_1" }
```

…but `metadata` is documented only as "arbitrary; returned on lookup" and lands in an opaque
`metadata_json TEXT DEFAULT '{}'` column. There is **no `node_id` column, no schema, and no code path
that reads or interprets it**. The PRD's five Open Questions never raise node_id semantics; its
Non-Goals explicitly scope it to session↔`external_ref` binding. It is pure opaque-in/opaque-out.

Resolving `node_id` → (hierarchy level, feature) is the *same problem class* as
`rf-intenttree-intent-id-resolution` (RF's `intent_id`/`task_node_id`): an opaque string minted by
IntentTree, displayed in CCDash, requiring a live call to a system CCDash cannot reach. That spec's
unblock condition — an IntentTree HTTP client plus a resilience contract — is a hard prerequisite here
too. Note the D2 hard boundary that spec asserts: these ids **must not** become an
`entity_graph.py`/`aos_correlation.py` join key. Slice-2 per-level attribution would require exactly
that, so architecture B collides with an existing architectural constraint.

**CCDash schema today**: `sessions` has no `node_id`, `intent_id`, or `external_ref`. `research_runs`
/`rf_events` do carry `task_node_id`/`intent_id`, but those are Research Foundry's own display-only
strings, explicitly never-a-join-key, and not wired to `sessions`.

### OQ-5 — Does B close the subagent gap? ⚠️ **REVISED 2026-07-28 — YES, via CCDash-side fan-out**

> **The measurements in this subsection are correct; the conclusion originally drawn from them was
> not.** IntentTree does link only 1 session per run — but CCDash propagates it to the family. See
> §8. Retained below for the evidence trail.

**Answer (IntentTree side): 1 session linked, not 6.**

1. `AgentRun.ccdash_session_id` is a single nullable `String(200)` scalar (migration
   `0004_agent_run_ccdash.py`) with no unique index. One run row holds exactly one session;
   re-posting is last-write-wins ("idempotent: re-posting a new session_id refreshes the stored
   metrics").
2. `AgentRun` has `node_id` (indexed, non-unique) but **no `parent_run_id`** and no self-referencing
   FK — there is no run→run hierarchy. `AgentRunStep.run_id` is step-within-run, not run nesting.
3. **No child-registration mechanism exists.** Grepping `subagent|child|fan.?out|parent_run|spawn|nested`
   across IntentTree's `backend/src/` yields only SSE subscriber fan-out and node *decomposition*
   (node→child nodes), neither of which touches session linking. `create_run`/`start_run`/
   `report_run`/`link_session` are all single-run, single-session, and **caller-driven**.
4. Claude Code's `Task()` children do not call IntentTree's MCP server or REST API themselves, and no
   orchestration code issues `create_run`/`link_session` per spawned subagent.

So an IntentTree-dispatched orchestrator links only its own top-level session. The five child
sessions are **invisible to IntentTree entirely** — the same orchestrator-only ceiling as
gap-analysis G-2.

**The one genuinely reusable primitive.** `aos_trace_uuid` is documented as
"Optional AOS trace/root UUID **spanning multi-hop work**" (migration `0036_aos_correlation_aliases.py`,
`docs/DATA_MODEL.md:315-318`), and the migration states duplicates are intentional
("not unique. Duplicate aliases are a resolver conflict surface, not a database integrity failure").
This is the correctly-shaped primitive for grouping an orchestrator with its children. **But nothing
populates it**: every write site is caller-supplied pass-through, and resolution only returns
`resolved`/`unresolved`/`conflict` over existing rows — it never mints session links. Making it work
requires a *dispatcher* that mints one trace id and threads it into every child `Task()` invocation.
That code does not exist, and it belongs to the harness/run-loop owner — not to CCDash and not to
IntentTree. See §5.

### OQ-6 — Coverage of non-dispatched sessions ❌ *B covers 0% of the corpus*

| Metric | Value |
|--------|-------|
| Claude Code session JSONL on disk | **6,348** across 174 project dirs |
| Codex session JSONL on disk | **3,387** |
| Launch-capture sidecars (`*.capture.json`) | **0** (capture write path still dead) |
| IntentTree runs, total instance-wide | **59** |
| …bound to **any** `aos-ccdash` node | **0** |
| …with `harness: claude_code` | **0** (49 `copy_paste`, 6 `simulated`, 4 `llm`) |
| …with any `aos_*_uuid` populated | **0 / 59** |
| …with `tokens_used > 0` | **1 / 59** |
| `external-links` rows (any system) | **0** |

The 49 `copy_paste` runs are smoke fixtures named `postfix0`–`postfix14` and `verify0`–`verify11`.

**IntentTree has never dispatched a real Claude Code run.** Architecture B therefore covers **0%** of
the existing ~9,700-session corpus and would only ever enrich *future* runs — conditional on
IntentTree first becoming the dispatcher, which is a program of work substantially larger than the
correlation feature it would serve.

---

## 4. Architecture decision

| # | Shape | Decision | Governing reason |
|---|-------|----------|------------------|
| **A** | CCDash consumes the IntentTree tree *instead of* parsing files | ❌ **REJECT** | Not because the importer is weak — it is capable (OQ-2). Because: **2.3% coverage, frozen since 2026-06-24** with no automatic refresh; no `wave`/`gate` node type and gate criteria unqueryable in `meta`; AC silently blends authored + inherited, so per-task AC joins would be wrong; container-level drift is undetectable (`source_fingerprint: null`), and the import demonstrably dropped two phases without flagging it; it inverts AOS constraint #2 (derived-reading-derived); and it requires an IntentTree HTTP client + resilience contract CCDash deliberately deferred (DF-007). CCDash already parses the same 132 plans + 56 PRDs + 305 progress files itself |
| **B** | Revive `intenttree-session-correlation-v1` as the Slice-2 vehicle | ⚠️ **CONDITIONAL** *(revised 2026-07-28; was REJECT)* | The attribution mechanism **works** — one orchestrator `node_id` fans out across CCDash's already-populated `workflow_id` family (§8). Blockers are adoption + small build, not capability: IntentTree has never dispatched (0 ccdash-bound runs, 0 `claude_code` harness, 0 external-links); `node_id` resolution needs an IntentTree HTTP client CCDash lacks; the D2 never-a-join-key boundary must be deliberately revisited; and over-attribution needs a rule when one session spans multiple nodes |
| **C** | Hybrid: file-based Slice 1 + IntentTree enriches Slice 2 | ✅ **RECOMMENDED** *(revised)* | With B viable, C is the real answer the handoff was reaching for. Slice 1 must stay file-based regardless — it is the only path that covers the 16,658-session historical corpus, which B can never reach. Slice 2 gains a credible per-level mechanism for *future* IntentTree-dispatched work |

**Net effect on the parent exploration:** Slice 1 unchanged (file-based, GO). **Slice 2's mechanism
is now identified and credible** — it was previously "the plumbing does not exist." Slice 2 stays
deferred, but its gate changes from "unknown attribution mechanism" to a **named, buildable
precondition**: IntentTree dispatching for real + the small CCDash-side wiring in §8.

The "instead vs additionally" question is answered: **additionally, not instead.**

### Why the original one-line dismissal was right for the wrong reason

The `hierarchy-ingestion` leg wrote off `sync_import` reuse with "premise does not hold in this repo,"
reasoning only that CCDash has no import path (F-3 — narrowly true). That is the *weakest* available
argument, because a missing path can simply be built. The dismissal survives on much stronger grounds
it never stated: the node model **cannot represent the target hierarchy**, the projection is
**lossier than the source files**, and the seam has **no operational substrate**. The operator's
instinct to re-investigate was correct — the conclusion is now evidenced rather than asserted.

---

## 5. What is worth salvaging

> **⚠️ Item 1 below is RETRACTED by §8.** CCDash's already-populated `workflow_id`/`subagent_parent_id`
> lineage solves the subagent-grouping problem without any trace-id work. `aos_trace_uuid` retains
> value only for cross-harness multi-hop work (e.g. Codex↔Claude handoffs), not for this. Item 1 is
> preserved below for the reasoning trail; **do not action it as written.**

1. ~~**`aos_trace_uuid` is the right primitive for the subagent problem — record it and move on.**~~
   Per-level subagent attribution needs a *trace id propagated into subagent invocations*, not a
   `node_id` pulled from a dispatcher. IntentTree already has correctly-shaped, duplicate-tolerant
   columns for this on both `nodes` and `agent_runs`; the missing piece is a dispatcher that mints and
   threads the id. **This is harness/run-loop work (Claude Code launcher or Hermes), not CCDash work
   and not IntentTree work.** It is the single highest-leverage unlock for Slice 2 and should be
   routed to the AOS launchpad rather than absorbed into a CCDash plan. Note the dependency: CCDash's
   launch-time capture sidecar path is currently dead (**0** `*.capture.json` on disk), and that
   sidecar is the natural place for a trace id to land.
2. **Report three defects upstream to `intenttree`** (all are real bugs, independent of this verdict):
   - **Container bindings are drift-blind.** Feature/phase bindings carry `source_fingerprint: null`
     and empty `raw_source_task`, so `compute_sync_status` can never return anything but `clean` for
     them. Two phases (`ccdash-core-remediation` Phase 1, Phase 4) are missing from the tree and this
     was never flagged — the two facts are plausibly the same bug.
   - **`sync_status` reports `clean` for bindings untouched for a month**, making stale-clean
     indistinguishable from verified-clean to any API consumer. A `last_verified_at` distinct from
     `last_synced_at`, or a `stale` status on age, would fix this.
   - **`GET /work-item-sync/bindings` silently ignores `tree_id`** rather than rejecting it, while the
     MCP `sync_status` tool advertises that filter. This produced a wrong intermediate result during
     this spike (1568 workspace-wide bindings read as ccdash-scoped) and would mislead any consumer.

   Note explicitly: the AC duplication is **not** a defect — it is DI-152 container inheritance
   working as designed and as tested. Do not report it as one.
3. **Do not build the CCDash→IntentTree push seam yet.** It is fully scaffolded on IntentTree's side
   (`ExternalSystem` has `ccdash` first-class; `AgentRunStartRequest` already accepts
   `ccdash_session_id`/`ccdash_transcript_path`; `EvidenceKind` has `ccdash_session`;
   `POST /nodes/{id}/external-links` attaches evidence to a node) and has **0 rows**. But it is a
   *reporting* seam, not an attribution seam — it still requires knowing which node a session belongs
   to, which is the unsolved problem. Cheap to build, but it would publish nothing until attribution
   exists.
4. **Leave `intenttree-session-correlation-v1` as `draft`.** Do not promote it, do not plan it. Add a
   pointer to this spike so the next reader does not re-derive OQ-5. Its handshake-token binding
   design is sound and worth preserving *if* IntentTree ever becomes a real dispatcher — the PRD is
   not wrong, it is premature.

---

## 6. Reproduction

```bash
export ITT=http://10.42.10.76:8032
# token lives in ~/.claude.json under the intenttree MCP server's env.INTENTTREE_API_TOKEN
export TOK=$(python3 - <<'PY'
import json, os
def find(o):
    if isinstance(o, dict):
        if "INTENTTREE_API_TOKEN" in o: return o["INTENTTREE_API_TOKEN"]
        for v in o.values():
            r = find(v)
            if r: return r
    elif isinstance(o, list):
        for v in o:
            r = find(v)
            if r: return r
print(find(json.load(open(os.path.expanduser("~/.claude.json")))) or "")
PY
)

# tree shape
curl -s -H "Authorization: Bearer $TOK" \
  "$ITT/api/v1/trees/tree_01KVTH95F7P7CXK3QH9ZMECM5T/nodes?limit=1" | jq '.total'   # 271

# node type enum (no wave, no gate)
curl -s -H "Authorization: Bearer $TOK" "$ITT/api/v1/openapi.json" \
  | jq -r '.components.schemas.NodeType.enum[]'

# runs bound to ccdash nodes
curl -s -H "Authorization: Bearer $TOK" "$ITT/api/v1/agent-runs?limit=100" \
  | jq '[.items[] | select(.harness=="claude_code")] | length'                       # 0

# external links (seam usage)
curl -s -H "Authorization: Bearer $TOK" "$ITT/api/v1/external-links?limit=100" | jq '.items | length'  # 0
```

Analysis scripts used for the binding/node joins are ephemeral (job scratch dir); the queries above
reproduce every headline number directly.

---

## 7. Confidence

**0.85.**

High confidence on OQ-1, OQ-3, OQ-5, OQ-6 — these rest on direct live-API measurement and on
file:line reads of IntentTree's models, migrations, and services, which are internally consistent and
corroborated by `DATA_MODEL.md` and migration docstrings.

OQ-2 is source-verified at file:line level in `services/work_item_sync.py` and corroborated by
IntentTree's own integration tests, so the importer-capability claims are not inferences.

Residual uncertainty:
- OQ-5's "1, not 6" is inferred from the **absence** of any child-registration mechanism, not from an
  explicit design statement. No doc in either repo discusses the orchestrator-fan-out scenario by
  name. The absence was verified by targeted grep across `backend/src/`, and
  `api/v1/agent_runs.py` was grepped rather than read line-by-line. This is the single claim most
  worth re-testing empirically if IntentTree ever dispatches a real fan-out run.
- The 2.3% coverage figure compares 3 imported plans against 132 implementation-plan *files*; some of
  those are phase sub-plans rather than top-level plans, so the true denominator of distinct features
  is smaller and real coverage is somewhat higher. The order-of-magnitude conclusion is unaffected.
- Leg B excluded `.claude/worktrees/*` copies in the intenttree repo as non-canonical; a divergent
  branch could in principle contradict the `main`-tree findings.

**What would overturn this verdict:** IntentTree becoming a real dispatcher (non-zero
`harness: claude_code` runs bound to ccdash nodes). This is a prerequisite, not a consequence, of
the correlation work. *(The original text also required trace-id propagation to subagents; §8
retracts that — CCDash's existing lineage makes it unnecessary.)*

---

## 8. Correction (2026-07-28) — the subagent gap is already closed on the CCDash side

**What prompted this**: the operator pushed back that IntentTree "should be enabled in all these
capabilities," and asked whether enhancements could reach a GO. Re-checking against the operative
database showed the original synthesis made a wrong inference from a right measurement.

### The error

§3 OQ-5 correctly established that IntentTree links **1** session per run. From that I concluded B
could not deliver per-level subagent attribution. **That does not follow.** It assumes IntentTree
must enumerate the children — but IntentTree never needed to. CCDash already has the family graph.

### The evidence

CCDash derives subagent lineage **purely from log fields**, explicitly sidecar-independent
(`backend/parsers/platforms/claude_code/parser.py:4491-4502`): `workflowId` = family root,
`subagentParentId`, `conversationFamilyId`, `threadKind`.

Measured on the operative DB (node Postgres `10.42.10.76:5440`, container `ccdash_postgres_1`,
2026-07-28):

| Metric | Value |
|---|---|
| Total sessions | **16,658** |
| `workflow_id` populated | **16,658 / 16,658 (100%)** |
| `thread_kind = 'subagent'` | 3,956 |
| `subagent_parent_id` populated on those | **3,956 / 3,956 (100%)** |
| Distinct workflow families | 10,457 |
| Child→parent joins sharing the parent's `workflow_id` | **4,079 / 4,079 (100% coherent)** |
| Multi-session families | ~770 (277×2, 83×3, 61×4, 55×5, 50×6, 39×7, 32×8, …) |

The lineage graph is live, fully populated, and internally coherent. **A `node_id` landed on an
orchestrator session propagates across its `workflow_id` family and reaches every subagent.**

### Consequences

1. **`aos_trace_uuid` is demoted from "the key unlock" to "optional."** §5 item 1 over-elevated it.
   It would be the right primitive if CCDash had no lineage — but CCDash does, derived from logs it
   already parses, with no dispatcher cooperation required. Do not build trace-id propagation to
   solve *this* problem. (It retains independent value for cross-harness/multi-hop work that is not
   a single Claude Code session family — e.g. Codex↔Claude handoffs.)
2. **Architecture B is capability-viable today.** Its blockers are adoption and a small build.
3. **Slice 1 still must be file-based.** B only ever covers IntentTree-dispatched runs; the 16,658
   historical sessions and all ad-hoc work need the file path. This is unchanged and is why C, not
   B alone, is the recommendation.

### The enhancement path, sized

**IntentTree side — mostly adoption, not new capability:**

| # | Change | Size | Necessary? |
|---|---|---|---|
| I-1 | Actually dispatch with `harness: claude_code` and call `link_session` / `start_run(ccdash_session_id=…)` | wiring only — the API already exists | **Yes — the real blocker** |
| I-2 | Schedule `sync import` so the tree is not frozen; fix container-binding `source_fingerprint: null` so drift is detectable | small | Only for architecture A, which stays rejected |
| I-3 | `parent_run_id` / 1:N run→sessions | small schema change | **No** — CCDash-side fan-out makes it redundant. Build only if IntentTree's own UI wants per-subagent rows |
| I-4 | `wave` / `gate` node types | small | **No** — CCDash has 0 structured gates and `wave_plan` is a scheduling overlay, not a containment level |

**CCDash side — the actual build:**

| # | Change | Size | Notes |
|---|---|---|---|
| C-1 | `session_correlations` table + `POST /api/correlations/register` | as designed | This is the PRD's Phase 1, already specced |
| C-2 | IntentTree HTTP client + config + resilience contract | small | A bearer-token GET; this is exactly DF-007's unblock condition |
| C-3 | Propagate bound `node_id` across the `workflow_id` family | small | Reuses live lineage — this is the piece that dissolves the subagent gap |
| C-4 | Revisit the D2 "never a join key" boundary | decision, not code | `rf-intenttree-intent-id-resolution` §3.3 forbids exactly this join; it must be *deliberately* overturned, not quietly violated |

**Genuine remaining risk — over-attribution.** Family-level propagation assigns the whole family's
tokens/cost to one node. If a single orchestrator session works across multiple nodes, that
over-counts — the same class as the deferred **D-001 correlation over-count**. Needs an explicit
rule (attribute at run boundaries, or require one dispatched run per node) before this ships. This,
not the subagent graph, is now the hard design question for Slice 2.

### Revised bottom line

The operator's instinct was correct: **IntentTree does not need major enhancement.** The dominant
gap is that nothing dispatches through it yet (I-1), and the rest of the work is a small, already-
designed build on the CCDash side. The honest verdict is **conditional**, not no-go — gated on
adoption plus an over-attribution rule, not on missing capability in either system.
