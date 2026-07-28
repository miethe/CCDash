---
schema_version: 2
doc_type: report
report_category: handoff
title: "IntentTree-as-Import-Path — New-Session Handoff"
status: complete
created: 2026-07-26
completed: 2026-07-26
outcome: conditional
feature_slug: plan-execution-session-correlation
related_documents:
  - docs/project_plans/exploration/plan-execution-session-correlation/spikes/intenttree-import-path/intenttree-import-path-findings.md
  - docs/project_plans/exploration/plan-execution-session-correlation/plan-execution-session-correlation-feasibility-brief.md
  - docs/project_plans/PRDs/integrations/intenttree-session-correlation-v1.md
  - docs/project_plans/design-specs/rf-intenttree-intent-id-resolution.md
  - docs/project_plans/reports/feature-retro-linkage-gap-analysis.md
---

# IntentTree-as-Import-Path — New-Session Handoff

> **✅ RESOLVED 2026-07-26; verdict REVISED 2026-07-28 to `conditional`. Read the findings §0 + §8.**
> → `spikes/intenttree-import-path/intenttree-import-path-findings.md` (verdict **conditional**, 0.8)
>
> **Outcome: "additionally", not "instead".**
> - **Architecture A (consume the tree instead of parsing files): NO.** The `aos-ccdash` tree is
>   3 plans of 132, frozen since 2026-06-24, no `wave`/`gate` node type, and its
>   `acceptance_criteria` is default container inheritance rather than per-task authorship — F-4/F-5
>   were materially overstated. (The importer itself is capable; the problem is freshness, coverage,
>   and AOS constraint #2.)
> - **Architecture B (IntentTree pushes correlation): CONDITIONAL — F-2's conclusion survives.**
>   IntentTree does link only 1 session per run, but that turned out not to matter: CCDash already
>   derives the orchestrator→subagent family graph from logs, populated on **16,658/16,658** sessions
>   with 100% coherence, so one `node_id` fans out to every subagent. The blocker is **adoption**
>   (IntentTree has never dispatched: 0 ccdash-bound runs, 0 `claude_code` harness) plus a small
>   CCDash-side build — not missing capability.
>
> **Parent plan**: Slice 1 stays file-based/GO (only path covering the historical corpus); Slice 2
> stays deferred but now has a named, buildable mechanism instead of an unknown one.
> **Retracted**: an earlier revision routed `aos_trace_uuid` propagation to the AOS launchpad as the
> key unlock — unnecessary, CCDash's existing lineage already solves it.
>
> The sections below are preserved **as-authored** for provenance; §2's F-1…F-6 are adjudicated in
> §1 of the findings doc — several did not survive.

> **You are picking up a scoped follow-on to the `plan-execution-session-correlation` exploration
> (verdict: CONDITIONAL, main `69b4cab`).** The parent exploration asked whether CCDash can ingest the
> plan hierarchy (wave→gate→phase→task→AC) and correlate sessions to every level. One leg dismissed
> reusing IntentTree's `sync_import` with a single line ("premise does not hold in this repo"). The
> operator wants that dismissal **re-investigated properly**: could IntentTree be the import path —
> *instead of*, or *in addition to*, CCDash-native file parsing? This handoff gives you the findings
> already gathered so you do not re-derive them, and the exact open questions to resolve.

## 0. The question (verbatim intent)

> "Dig deeper into using IntentTree to import the data, either instead or additionally, depending on
> what's available."

Two decisions ride on this:
1. **Slice 1 (hierarchy ingestion)** — should CCDash re-parse plan files itself, or **consume
   IntentTree's already-derived node tree**, or both?
2. **Slice 2 (per-level session correlation)** — the parent exploration flagged this as the hard part
   because subagent sessions can't be attributed to a plan level from slash-command tags. **IntentTree
   dispatch already knows which node it dispatched to.** Does that dissolve the Slice-2 attribution
   problem entirely?

## 1. Read these first (in order)

1. `plan-execution-session-correlation-feasibility-brief.md` — the parent verdict + two-slice split.
2. `spikes/correlation-crux-findings.md` and `spikes/hierarchy-ingestion-findings.md` — the two legs
   this handoff reopens (the crux owns the deal-killer; hierarchy-ingestion is where the IntentTree
   dismissal lives).
3. **`docs/project_plans/PRDs/integrations/intenttree-session-correlation-v1.md`** — ⭐ the single most
   important prior artifact. Read it fully. It already specs the IntentTree↔CCDash seam.
4. `docs/project_plans/design-specs/rf-intenttree-intent-id-resolution.md` — the opaque
   cross-system-ID resolution problem (`intent_id`/`task_node_id`), currently `deferred`.
5. `docs/project_plans/reports/feature-retro-linkage-gap-analysis.md` — the base-join gap this all sits on.

## 2. Findings already established this session (do NOT re-derive)

### F-1 — An unimplemented HIGH-priority PRD already specs the seam (the inverse direction)
`intenttree-session-correlation-v1.md` (schema v3, `status: draft`, `implementation_plan_ref: null`,
"2–3 weeks / 3 phases") specifies **IntentTree → CCDash session registration**: IntentTree
pre-declares a dispatched task via an opaque `external_ref`; CCDash binds the matching transcript on
ingest; IntentTree pulls metrics. New table `session_correlations`, `POST /api/correlations/register`,
a sync-engine binding hook, and an optional webhook. **It is designed but never built.** This is the
_inverse_ of "CCDash imports from IntentTree," but it is the load-bearing infrastructure for the
correlation direction.

### F-2 — The registration payload already carries `node_id` — that IS the plan-hierarchy pointer ⭐
The PRD's registration `metadata` example is literally `{ "node_id": "node_xyz", "workspace_id": "ws_1" }`
(PRD §3.1). If IntentTree dispatches a run tied to a specific plan node (a phase or task) and registers
it with CCDash, the bound session inherits an IntentTree `node_id` = **the exact plan-hierarchy level**.
That is precisely the per-level attribution mechanism the `correlation-crux` leg concluded does not
exist for subagents (it reasoned only about slash-command-tag derivation, which fails for `Task()`
children). **IntentTree-dispatched runs sidestep that failure entirely** — the dispatcher knows the node.
This is the strongest argument for the "additionally" path and should be the centerpiece of your analysis.

### F-3 — CCDash's backend has NO IntentTree data-import path today (the leg was right, narrowly)
`grep -ri intenttree backend/` returns only: CORS-origin config for LAN/IntentTree agents
(`config.py:955,962,1318`), a capability-discovery endpoint comment (`routers/client_v1.py:144,160`),
a CORS merge (`runtime/bootstrap.py:165`), and an entity_graph comment about "future IntentTree
cross-reference" (`entity_graph.py:22`). These are **transport/CORS/capability plumbing, not data
import.** So the hierarchy-ingestion leg's core claim (no `sync_import` reuse path) holds — but frame
it precisely: the seam is *anticipated* in code comments and CORS, just not wired.

### F-4 — IntentTree already ingests CCDash's SDLC plans into a live, populated tree
`mcp__intenttree__list_trees` shows an `aos-ccdash` tree (`tree_01KVTH95F7P7CXK3QH9ZMECM5T`,
"real SDLC plans captured from …/CCDash") plus trees for skillmeat (progress 0.70), agentic_meta_dev,
research-foundry, meatywiki, etc. `list_tree_nodes(aos-ccdash, depth=2)` returned **736 KB** of nodes —
the tree is richly populated. So the derived Feature→Phase→Task projection **already exists** for CCDash;
the question is its fidelity (see OQ-1) and whether CCDash should read it.

### F-5 — IntentTree's node model is rich (from the MCP tool surface)
Nodes carry `type`, `effort_size`, `priority`, `tags`, **`acceptance_criteria`**, `branch`, `repo`,
`scores{}`, `execution_mode`, owner/agent assignment. Typed edges exist (`depends_on`/`blocks`/`relates_to`).
There are first-class **runs** (`create_run`/`start_run`/`report_run`) with **`link_session`** (bind a
CCDash session to a run) and **`link_external(link_type: ccdash)`**. `sync_import`/`sync_export`/`sync_status`
project a plan file's `tasks[]` onto the node tree and report drift. **Much of Slice-1's target hierarchy
may already be modeled in IntentTree** — including AC as a node field, which CCDash's parsers do NOT extract.

### F-6 — AOS-constraint tension (the architectural crux of "instead vs additionally")
AOS constraint #2: *files are canonical; databases are derived.* Both CCDash and IntentTree derive from
the **same canonical plan files**. So "CCDash reads IntentTree's node DB" is *derived-reading-derived* —
it couples two derived stores and inverts the constraint. The AOS-clean shape is: both derive from files,
and they **correlate on a shared key** (`external_ref` / `node_id` / `feature_slug`). Weigh this against
the pragmatic win of not duplicating plan-parsing logic. This is the decision to make deliberately.

## 3. Three candidate architectures to evaluate

| # | Shape | "instead"/"additionally" | Pros | Cons / risks |
|---|-------|--------------------------|------|--------------|
| **A. CCDash consumes IntentTree tree** | CCDash pulls the derived Feature→Phase→Task(+AC) tree from IntentTree's HTTP/MCP API instead of parsing plan files | **instead** (Slice 1) | No duplicate plan-parsing; AC already modeled; single hierarchy source of truth | Hard runtime dep on IntentTree (node down = no hierarchy); derived-reading-derived (AOS #2); node-model fidelity for wave/gate unverified (OQ-1); cross-repo node trees still separate |
| **B. IntentTree pushes correlation (revive the PRD)** | Implement `intenttree-session-correlation-v1`: IntentTree registers dispatched runs w/ `node_id`; CCDash binds sessions; node_id → hierarchy level | **additionally** (Slice 2) | Solves the subagent-attribution gap (F-2); already designed; per-level tokens/cost falls out of the bound run | Only covers IntentTree-*dispatched* runs (not historical/ad-hoc sessions); needs IntentTree to be the dispatcher; opaque-ID resolution (F-4/OQ-4) |
| **C. Hybrid (likely recommendation)** | CCDash keeps **file-based** Slice-1 ingestion as canonical AND accepts IntentTree correlation (`node_id`) to enrich Slice-2 per-level attribution | **additionally** | AOS-clean (both derive from files, correlate on key); Slice 1 stays independent of node uptime; Slice 2 gets the dispatch-known node for free | Two derivation paths to keep consistent; drift between CCDash's parse and IntentTree's `sync_import` (mitigated by `sync_status`) |

## 4. Open questions to resolve (the actual investigation)

- **OQ-1 — Node-model fidelity.** Does IntentTree's `aos-ccdash` tree capture **wave** and **gate** as
  first-class nodes, or only Feature→Phase→Task? Is `acceptance_criteria` populated per node or empty?
  Probe: `mcp__intenttree__list_tree_nodes(tree, type=…)` filtered by type, then `get_node(..., include=children,edges)` on a feature and a phase. (The full depth=2 dump is at
  `…/tool-results/mcp-intenttree-list_tree_nodes-1785114762989.txt` — 736 KB, query with `jq`, do not read whole.)
- **OQ-2 — `sync_import` fidelity.** Does `itt sync import` capture `wave_plan`, gates, and AC blocks,
  or only `tasks[]`? Read the AWPR v2 contract + CLI source in the **intenttree repo**
  (`~/dev/homelab/development/intenttree`, look for `client/src/intenttree_client/cli/commands/sync_cmd.py`
  and the `awpr-v2-task-node-contract` plan). Note: `.claude/rules/intenttree-integration.md` referenced by
  the planning skill is **NOT in the CCDash repo** — it lives in skillmeat/agentic_meta_dev.
- **OQ-3 — IntentTree read API for CCDash.** What HTTP surface would CCDash call to read the tree? Is it
  the node-service on rocket-fedora (`10.42.10.76`) or local? What are latency/availability/auth? Is a hard
  runtime dependency acceptable, or should CCDash cache/snapshot the tree?
- **OQ-4 — Opaque-ID resolution.** How does a CCDash-side IntentTree `node_id` resolve to a hierarchy
  level and a feature? This is exactly the `rf-intenttree-intent-id-resolution` design-spec's problem
  (currently deferred). Does that spec's resolution approach generalize here?
- **OQ-5 — Does B actually close the subagent gap?** Verify: when IntentTree dispatches a `Task()`-style
  fan-out, does each subagent run get its own `node_id` registration, or only the orchestrator? If only the
  orchestrator, B inherits the same subagent-unreachability the file-based path has (gap-analysis G-2).
- **OQ-6 — Coverage of non-dispatched sessions.** The bulk of the 14,399-session corpus was NOT
  IntentTree-dispatched. B/C only enrich *future* IntentTree-dispatched runs. Quantify what fraction of
  real retros that covers, and whether Slice-1 file ingestion is still required for historical coverage.

## 5. Recommended investigation shape

Run this as a **focused spike** (not a full 4-leg exploration — most current-state is already in §2):
1. **Probe leg (technical):** resolve OQ-1 + OQ-2 + OQ-3 against the live IntentTree service and the
   intenttree repo. Deliver the node-model fidelity table + the read-API contract.
2. **Seam leg (technical):** resolve OQ-4 + OQ-5 by reading the `intenttree-session-correlation-v1` PRD
   against IntentTree's dispatch/run model; confirm whether `node_id` reaches subagent runs.
3. **Synthesis:** pick A / B / C (C is the prior), and produce a recommendation that either (a) revives
   `intenttree-session-correlation-v1` as the Slice-2 vehicle, (b) proposes CCDash-consumes-tree for Slice 1,
   or (c) both. Feed the result back into the parent exploration's Slice-1/Slice-2 plan.

## 6. Environment & delegation notes

- **IntentTree access:** MCP tools (`mcp__intenttree__*`) are live in-session; the service also runs on
  the agentic node (`ssh agentic-nuc`, `10.42.10.76`). Use MCP for reads.
- **Agent-tool hazard:** the native `Agent`/`Task` tool **overflows on this repo's oversized CLAUDE.md**.
  Dispatch delegated legs via **ICA `--bare` bash delegation** (`~/ica-claude.sh --bare
  --allow-dangerously-skip-permissions --model 'claude-sonnet-5[1m]' -p "$(cat prompt.txt)"`), which skips
  CLAUDE.md discovery. This is the pattern the parent exploration used successfully.
- **Token discipline:** the 736 KB node dump must be `jq`-queried, never read whole. Opus reads frontmatter
  + verdicts; delegate deep reads.
- **Decision this feeds:** whether Slice 1 stays file-based / becomes IntentTree-consumed / hybrid, and
  whether Slice 2's correlation IS the (revived) `intenttree-session-correlation-v1` PRD rather than net-new
  work. Update `plan-execution-session-correlation-feasibility-brief.md` §6 with the outcome.
