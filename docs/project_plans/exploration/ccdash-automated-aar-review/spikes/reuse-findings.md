---
leg: reuse
duplication_risk: medium
confidence: 0.82
schema_version: 2
doc_type: exploration_spike_findings
feature_slug: ccdash-automated-aar-review
question: "What already exists across the AOS that an automated-AAR-review loop MUST reuse/extend rather than duplicate; the honest delta; and where the ownership seams sit."
persona_directive: "close seams, don't add tools"
updated: '2026-07-21'
---

# Reuse Leg — AOS Seam Mapping (op story / ARC / RF / SkillMeat / IntentTree)

## TL;DR (decisive)

- **NOT a no-go.** The AAR→**public blog** loop is delivered end-to-end by `op story` + Signal→System.
  The AAR→**system-improvement** loop (triage → ARC deep-dive-or-surface-review → enhancement
  recommendation into op/SkillMeat) is **not delivered anywhere**. Real gap exists.
- **The biggest live overlap is `op story`, and it already calls CCDash.** `op story` shells
  `ccdash feature list` + `ccdash report aar` to synthesise AAR pointers and triages them with a
  deterministic intensive-feature heuristic. CCDash must **reuse this input path, not rebuild it.**
- **The one seam CCDash is uniquely positioned to close:** deterministic **surface-flag computation
  over session evidence** — the cheap-extract tier that decides *which* sessions merit expensive ARC
  review. No subsystem computes "generic-agent-where-a-specialist-existed / context ballooning /
  missing artifacts / stack-ineffectiveness" from raw session JSONL today. That flag-set, emitted as a
  structured triage event, is CCDash-native and non-duplicative.

---

## 1. Ownership line (the seam)

| Concern | Owner | Evidence |
|---|---|---|
| Session JSONL, docs+frontmatter, features, tokens/costs, artifact snapshots (**evidence**) | **CCDash** | AOS-AGENT-GUIDE.md:68,170 ("L5 CCDash: session telemetry, costs, AAR evidence, operational insight") |
| AAR **generation** (`ccdash report aar --feature`) + AAR↔**feature** correlation | **CCDash** | `backend/application/services/agent_queries/reporting.py`; MCP `ccdash_generate_aar(feature_id)`; consumed by story.py:1434 |
| Deterministic **surface-flag** computation (missing artifacts, ctx balloon, generic-agent, stack-ineffectiveness) | **CCDash (GAP — unowned today)** | no such computation found in any repo; see §4 |
| AAR → **public dev-story** synthesis + gated blog draft PR | **op story** | contracts/story.md §1,§5 |
| Model-driven **adversarial deep review** + scorecard verdict (the "full swarm") | **ARC / council-review** | contracts/arc.md §2 |
| Artifact **ranking / recommendation over existing artifacts** + deploy | **SkillMeat** | `backend/services/artifact_recommendation_service.py`; contracts/skillmeat.md §2 |
| Run-record ↔ session correlation, AAR evidence rows, task-graph writeback + gate | **IntentTree** | contracts/intenttree.md:14,211,268-271 |
| route×tier classification, the three gates, durable run record | **op** | .claude/skills/op/SKILL.md §2,§6 |

**Line to draw:** CCDash = *evidence + AAR↔session/feature correlation + deterministic triage flags*
(producer). op/ARC/SkillMeat = *model-driven synthesis + gated writeback + artifact
creation/deploy* (consumer). This is the **exact precedent already set by `ccdash persona extract`**:
> "CCDash is the **producer** only; reconcile/dedup/gate/writeback stay here. Additive — the bank
> works without it." — contracts/persona.md:35

CCDash produces a model-free candidate/event; agentic_meta_dev owns the model calls and the gate.
The automated-AAR-review loop should be the **same shape**.

---

## 2. Overlap register

| Existing capability | Repo / path | Overlaps intent | Reuse-or-extend |
|---|---|---|---|
| **`op story` synthetic-AAR ingest** — `ccdash feature list --status completed` + `ccdash report aar --feature <id>` → pointer | `src/operator_core/adapters/story.py:1414-1452` | **Partial (input)** | **REUSE.** CCDash already feeds it. Do NOT rebuild AAR sourcing. |
| **`op story` intensive-feature triage** — `_is_intensive_feature` (≥100k tok OR ≥3 sessions OR ≥180 min) | `story.py:1454-1458` | **Partial (triage)** | **EXTEND.** Same idea, coarser. CCDash's richer flags supersede these 3 thresholds — but keep them as the fallback signal. |
| **`op story` candidate scoring** — `_classify_candidate` (novelty/narrative/forensic/audience/dedup → post/hold/archive) | `story.py:1462-1485` | **None (different sink)** | **DO NOT reuse.** Scores *blog-worthiness*, not *review-worthiness*. Different rubric, different terminal. |
| **`op story` gated draft PR** — `story.review` → writeback gate → `story.approve_draft` → `gh pr create --draft`, never merges | contracts/story.md:108-120 | **None** | Leave alone. Charter out-of-scope explicitly forbids touching story gates. |
| **ARC council** — scaffold (`arc run`) → populate (`council-review` skill) → validate → `scorecard.json.recommendation` | contracts/arc.md §2; `agentic-research` repo | **Full (the deep-dive)** | **REUSE as terminal.** Triage routes *to* ARC; op `council` route wraps the 3-step pipeline. CCDash never runs ARC itself. |
| **op `council` route** — `op council "<text>"` forces council route | SKILL.md:82 | **Full (invocation)** | **REUSE.** The dispatch already exists; emit a recommendation that op turns into `op council`. |
| **RF→CCDash writeback** — `rf writeback` emits `writebacks/ccdash_event.yaml` (metrics+governance+human_review) | `src/operator_core/adapters/rf.py:309-359`; CCDash commit 9594fcc (RF run telemetry ingest/analytics tab) | **Pattern precedent** | **REUSE the pattern (inverted).** Established structured-YAML-event-into-CCDash contract; CCDash's triage event can mirror `*_event.yaml` shape. |
| **IntentTree run↔session linkage** — `start_run/report_run(ccdash_session_id, ccdash_transcript_path)`, `link_session` | contracts/intenttree.md:14,268-271 | **Full (correlation infra)** | **REUSE.** Run-record↔session correlation is already solved; don't invent a second key. |
| **IntentTree AAR evidence + off-tree capture** — `evidence:{kind:aar}`, `capture add` w/ `meta.external_ref=op_run_id` | contracts/intenttree.md:154,211,228 | **Partial (writeback home)** | **REUSE.** Enhancement recommendations land as IntentTree nodes, not a new CCDash store. |
| **SkillMeat artifact recommendations** — `disable_candidate / load_on_demand / optimization_target / workflow_specific_swap / version_regression` | `backend/services/artifact_recommendation_service.py:195-431` | **Partial (existing-artifact advice)** | **REUSE for "use/swap X" advice.** These are advisory over *existing* artifacts only. |
| **SkillMeat `add` / `deploy`** | contracts/skillmeat.md §2 | **None (no synthesis)** | Requires an existing GitHub/local source. **No "create a new skill/agent" path exists anywhere** — that stays a human/Claude authoring act (skill-builder/agent-expert). |
| **`ccdash persona extract`** producer→consumer split | CCDash `CLAUDE.md`; contracts/persona.md:35 | **Precedent** | **COPY the pattern.** This is the template for the whole loop's ownership boundary. |

---

## 3. Duplication risk — honest delta

**Risk: MEDIUM.** Rationale:

- **The input half is already built inside `op story`.** `story.py:1414-1458` already (a) pulls
  completed features from CCDash, (b) generates a synthetic AAR per feature via `ccdash report aar`,
  and (c) triages with a deterministic "intensive feature" heuristic. If CCDash re-implements
  synthetic-AAR generation or a feature-intensity gate, that is **direct duplication.** The mitigation
  is to *reuse* `ccdash report aar` (which CCDash already owns) and let op story keep consuming it —
  CCDash adds flags, not a parallel sourcing pipeline.

- **The output half is genuinely unbuilt.** No repo routes an AAR into either a surface-flag review
  *or* an ARC deep-dive *and then* into an enhancement recommendation. `op story`'s terminal is a
  **blog draft PR** (contracts/story.md:9,120), a categorically different sink from
  "new skill/agent / config change." ARC exists but is only invoked when a human/op points it at a
  target — nothing auto-decides *which sessions* deserve ARC. So the loop is **not delivered
  end-to-end**; the charter no-go trigger ("op story + ARC already deliver the loop") is **not met.**

- **Correlation caveat (honest):** the linkage that exists today is **feature-level**
  (`ccdash report aar --feature <id>`, IntentTree `ccdash_session_id` on runs). The charter's
  deal-killer is about **AAR-doc → session-log** pairing. Feature→session is derivable in CCDash
  (features already aggregate sessions), and IntentTree already carries `ccdash_session_id`, so a key
  is *cheaply derivable* — but the agent-written-`*-aar.md`→session pairing is the **tech leg's** call,
  not confirmed here. Reuse leg confirms only that no *second* correlation system should be built:
  extend `document_linking` + IntentTree's existing `ccdash_session_id`.

- **What CCDash must NOT do (writeback blast radius):** never call `gh pr merge`, never `skillmeat add`
  a synthesised artifact, never run ARC autonomously. All model-driven synthesis and every irreversible
  writeback already have gates (op's writeback gate, story's approve gate, ARC's validate gate,
  IntentTree's AgentRun gate). CCDash emits *candidates/events*; the gates stay upstream.

---

## 4. The single biggest seam CCDash is uniquely positioned to close

**Deterministic surface-flag triage over session evidence — the cheap-extract tier that decides
*which* sessions escalate to expensive ARC review.**

Why only CCDash can: the four charter flags —
missing artifacts, context ballooning, generic-agent-where-a-specialist-existed, stack-ineffectiveness
— are computable **only** from data CCDash already holds and no one else does: session JSONL +
per-session tokens/`context_window` + `subagent_parent_id`/`skill_name`/`model_slug` detection columns
(CCDash `CLAUDE.md` "Session columns — detection") + feature frontmatter + SkillMeat artifact
snapshots. `op story` knows only three coarse thresholds (tokens/sessions/duration). ARC knows nothing
until pointed. There is **no flag computation anywhere in the AOS today** (grep of story.py, arc.md,
artifact_recommendation_service.py: only blog-scoring, schema-validation, and existing-artifact advice
respectively).

**Shape it as a producer event, mirroring the RF→CCDash `ccdash_event.yaml` precedent (rf.py:349), in
reverse:** CCDash computes flags → emits a model-free `aar_review_candidate` record (feature/session
refs + flag set + severity) → op reads it and decides route (surface-review note vs
`op council`/ARC) at its existing plan gate. This is exactly the `persona extract` producer/consumer
split (contracts/persona.md:35) applied to review triage.

**Bounded prerequisite (for a `conditional` verdict, if tech leg confirms it):** the flag computation
is the one new CCDash-native surface; everything downstream (synthesis, ARC, deploy, gates) is reuse.
Next command candidate: a CCDash `agent_queries` service `aar_triage.py` + `ccdash report aar-triage`
CLI/MCP verb that emits the candidate event — deterministic, no model, no writeback.

---

## 5. Verdict-criteria inputs (for Opus synthesis)

- **reuse-leg confidence ≥ 0.7:** met (0.82).
- **Non-duplicative seam with op story / ARC:** **confirmed** — CCDash = evidence + deterministic
  triage flags; op/ARC = synthesis + gated writeback. The `persona extract` precedent proves the
  boundary is real and already operating.
- **"Already delivered end-to-end?" no-go:** **refuted for the improvement loop** (only the blog loop
  is end-to-end). But CCDash **must reuse** `op story`'s existing CCDash calls and route to ARC via the
  `op council` route rather than re-home either.
- **Do-not-build list:** synthetic-AAR sourcing (reuse story.py), blog-scoring rubric (wrong sink),
  a second correlation key (reuse IntentTree `ccdash_session_id` + `document_linking`), new-artifact
  synthesis (does not exist by design; stays human/Claude), any ungated autonomous writeback.

## Citations
- `src/operator_core/adapters/story.py:1414-1458` (CCDash synthetic-AAR ingest + intensive-feature triage), `:1462-1485` (blog-scoring), `:1523-1537` (CCDash forensic context)
- `docs/agentic-operator/contracts/story.md` §1,§5,§6 (story owns AAR→blog draft PR, gates)
- `docs/agentic-operator/contracts/arc.md` §2 (scaffold→populate→validate; verdict in scorecard.json)
- `docs/agentic-operator/contracts/persona.md:35` (producer/consumer precedent)
- `docs/agentic-operator/contracts/skillmeat.md` §2 (add/deploy require existing source; no synthesis)
- `docs/agentic-operator/contracts/intenttree.md:14,211,268-271` (ccdash_session_id linkage, aar evidence)
- `src/operator_core/adapters/rf.py:309-359` (rf→CCDash `ccdash_event.yaml` writeback pattern)
- `.claude/skills/op/SKILL.md` §2,§5,§6 (route enum incl. `council`→ARC; three gates)
- `docs/agentic-operator/AOS-AGENT-GUIDE.md:68,170,176-189,211` (CCDash=evidence layer; AAR/story flow; "AAR-on-merge auto-emit: not a general automatic trigger")
- CCDash `backend/services/artifact_recommendation_service.py:195-431` (advisory-over-existing recs only)
- CCDash `backend/application/services/agent_queries/reporting.py` (`generate_aar`), CCDash `CLAUDE.md` (persona extract producer split; session detection columns), commit 9594fcc (RF run telemetry ingest)
