---
leg: risk
charter: ccdash-automated-aar-review
dealkiller: unresolved
confidence: 0.65
created: 2026-07-21
---

# Risk Findings — CCDash Automated AAR Review Loop

## Scope note

This leg does not verify the AAR↔session correlation key itself (that is the `tech` leg's job).
It reasons about what happens *if* correlation and triage exist: cost/recursion bounds, writeback
blast radius, gate placement, and operational risk against the hard AOS constraints (no LLM on the
recall path; cheap-extract/expensive-synthesize; gates are run-record state; CLIs are the contract).
Grounded against CCDash's actual gated-job precedents: `backend/services/integrations/telemetry_exporter.py`,
`backend/adapters/jobs/artifact_rollup_export_job.py`, `backend/application/services/agent_queries/council_review_queries.py`,
and ADR-006/ADR-007.

---

## 1. Cost/recursion risk — auto-escalation to full ARC swarm review

**The core danger**: an "AAR review" job is itself a session. If CCDash treats *any* session log
that discusses AAR review as eligible for triage, the AAR-review session's own JSONL becomes input
to the next triage pass — a self-referential loop with no natural termination. This is structurally
identical to a crawler re-indexing its own index page.

**Required guards (all must exist before any auto-escalation ships):**

1. **Self-exclusion by provenance, not content-sniffing.** The session-capture columns already
   shipped for launch-time capture (`launcher`, `profile`, `effort_tier`, `model_variant`, plus
   detection columns `skill_name`, `workflow_id`) give CCDash a deterministic, non-LLM way to tag
   a session as "AAR-review-originated" at capture time (e.g. `skill_name == "aar-review"` or a
   reserved `workflow_id` prefix). Any session bearing that tag is excluded from the triage input
   set unconditionally — the same pattern the telemetry exporter uses to skip disabled event types
   without failing the batch (`_push_batch`'s `skipped_artifact_ids` path). Sniffing session content
   for "is this an AAR-review session" would require an LLM read on the recall path — forbidden.
2. **A monotonic idempotent ledger, not a re-scan.** Every triage pass must record
   `(aar_doc_id, session_id) → triaged_at` so a re-run of the sync/watcher cycle does not re-enqueue
   the same pair. `emit_artifact_outcomes`'s `dedup_key = f"art:{payload.event_id}"` pattern
   (idempotent enqueue keyed off a stable id) is the direct precedent — reuse it, don't reinvent.
3. **A hard, env-configured ceiling on escalations-to-swarm per unit time**, enforced *before* any
   handoff to `op`/ARC — analogous to the trichotomy the telemetry exporter already enforces
   (`runtime_config.enabled` env-lock → `settings.enabled` persisted toggle → per-run busy-lock). A
   missing or misconfigured ceiling is the single most likely way this feature produces a bill
   shock, because "deep dive" implies model-driven multi-agent work, which is the AOS's most
   expensive execution tier.
4. **CCDash never calls the swarm directly.** It hands off a triage verdict + evidence bundle
   through the CLI contract (`op`/ARC), and `op`'s own classify→plan→dispatch cost/tier gating is
   the actual brake on runaway spend. CCDash's job is to *not multiply the number of handoffs*, not
   to reimplement cost control it doesn't own.

Without (1)+(2), auto-triage-to-swarm is a genuine infinite-loop / cost-explosion risk, not a
theoretical one — CCDash's own sync engine already re-scans on every filesystem change event, so
any newly-written AAR-review session JSONL *will* be picked up by the next sync pass unless
explicitly excluded.

---

## 2. Blast radius of recommendations that write back into SkillMeat/skills/agents

Two representative recommendation shapes named in the charter — "create a new agent" and "the
generic agent was used where a specialist fit" — are both **behavior-changing for every future
session**, not just retrospective commentary. If acted on automatically:

- A bad "create a new specialist agent" recommendation, if auto-materialized, permanently adds a
  persona/skill definition that every subsequent session may select against — a single bad
  inference now compounds across N future sessions, and is hard to roll back once sessions have
  already run against it (SkillMeat catalog bloat, or worse, an agent with subtly wrong tool
  grants).
- A "generic agent was mis-assigned" recommendation, if it auto-triggers a routing-rule change,
  risks *reducing* quality system-wide if the surface-level heuristic was a false positive (e.g. a
  generic agent correctly handled a mixed-domain task that only *looks* like it needed a
  specialist).
- Recommendations that write into the persona/memory bank's `_inbox/capture.jsonl` (the same sink
  CCDash's own `ccdash persona extract` feeds — see CLAUDE.md) are lower-blast-radius (inbox is
  reconciled, not live) but still risk **inbox poisoning at volume**: if AAR-review runs
  automatically at high frequency, an inbox flooded with low-signal auto-generated candidates
  degrades the human/operator triage step that inbox pattern exists to preserve.

**Where the gate must sit — non-negotiable, per charter Out-of-Scope and AOS constraints:**

- CCDash's job stops at **evidence + a deterministic flag + (optionally) a synthesized
  recommendation text produced by a *gated* delegate call**, never at a file write into
  SkillMeat/agents/skills.
- The precedent already in this codebase is `council_review_queries.py`: CCDash **reads** ARC
  council-review state (`SqliteCouncilReviewRepository`, capability-gated on `config.ARC_ENABLED`,
  empty-state when off) — it does not invoke or write ARC review outcomes. The AAR-review loop
  should mirror this ownership line exactly: CCDash produces the input ARC/op consume, and consumes
  the output op/ARC produce, but never writes into either's authoritative state.
- Any writeback into SkillMeat/agents must go through `op`'s existing HITL gate
  (`op approve|reject <run_id>`) and/or the `council-review` adversarial-review skill — both are
  run-record state with an explicit human action, not an ad-hoc prompt CCDash could satisfy itself.
  This is exactly the charter's Out-of-Scope line ("Any autonomous writeback that bypasses existing
  HITL gates") and it is a hard boundary, not a suggestion.
- Concretely: the correct shape is CCDash emits a recommendation as a **draft** (op capture / a
  Signal→System candidate, same shape `op story capture` already produces for other AARs), *not* a
  direct SkillMeat API mutation. If a future iteration wants CCDash to push structured
  recommendation payloads somewhere, the `telemetry_exporter.py` → `SkillMeatClient` pattern (queued,
  retried, privacy-verified via `AnonymizationVerifier`, feature-flag gated, degrades to no-op) is
  the correct *transport* precedent — but note that pattern pushes read-only *usage rollups*, never
  mutates SkillMeat's catalog. Recommendation writeback is a materially different risk class and
  must not reuse that transport to skip the human gate.

---

## 3. Where triage flags may run vs. where synthesis may run

| Concern | Triage flags (surface-level) | Synthesis (deep-dive / recommendation) |
|---|---|---|
| Execution site | Backend worker job (`backend/adapters/jobs/`), scheduled or watcher-triggered | Delegated via CLI contract to `op`/ARC — never inside a CCDash job |
| Model calls | **None.** Deterministic heuristics only (regex/threshold/lookup), same class as `persona_extract_rules.py`'s R1–R8 deterministic rules over text | Yes — this is exactly the "expensive synthesize" tier and is where LLM calls belong |
| Data source | Already-ingested DB rows: session detail, document linking, artifact-intelligence, redaction-passed session excerpts | The triage evidence bundle CCDash hands off, plus whatever context `op`/ARC pulls itself |
| Gating | Feature flag (env-lock + persisted-settings trichotomy, telemetry-exporter pattern) + idempotent dedup ledger | Run-record gate: classify→plan→dispatch, HITL approve/reject, ARC adversarial pass |
| Output | A row/flag record (candidate for a new `aar_review_flags`-shaped table) — evidence, not a verdict | A recommendation artifact routed through `op story`'s existing Signal→System pipeline |
| Failure mode if violated | LLM call sneaks onto the recall path → violates the hardest AOS constraint in this charter | Autonomous writeback bypassing HITL → violates the charter's Out-of-Scope line explicitly |

The four candidate surface-level flags named in the charter (missing artifacts, context
ballooning, generic-agent-where-specialist-fit, stack-ineffectiveness) all look, on their face, like
they reduce to threshold/lookup checks against fields CCDash already computes (token counts, model
identity, tool-usage patterns, artifact-link presence) — i.e. plausibly zero-LLM. The tech leg should
confirm this per-flag; if any flag genuinely requires semantic judgment (e.g. "was the agent choice
*wrong* given the task," not just "which agent was used"), that flag is **not** a triage flag — it
belongs in the synthesis tier and must not be computed on the recall/read path.

---

## 4. Deal-killer assessment

**Charter deal-killer**: "If CCDash cannot correlate an agent-written AAR to the specific session
log(s) it describes ... abandon."

**Assessment from the risk leg (architectural reasoning, not data verification)**: **unresolved by
design** — this leg does not own the data-layer verification (`tech` leg does), but two structural
observations bear on how fatal a *weak* correlation would actually be:

1. CCDash already has an internal precedent for tying an AAR to session evidence: its own
   `ReportingQueryService.generate_aar` (feature-scoped AAR generation) and
   `document_linking.py`'s cross-referencing of sessions/documents/features/tasks show the platform
   already treats "which sessions fed this document" as a computable, non-LLM join over feature_id
   + timestamp + cwd + frontmatter — for AARs CCDash itself produces. The open question the tech
   leg must answer is whether an *externally, agent-authored* AAR (e.g. from `op story capture`, not
   generated by CCDash) carries an equivalent linkage key when it lands in CCDash's ingest path, or
   whether that key has to be manufactured (frontmatter convention, session-id embed, etc.).
2. **A perfect 1:1 correlation key is not actually required for this feature to be safe** — only for
   it to be *fully automatic*. The risk-mitigating reframe: if correlation is probabilistic
   (timestamp-window + cwd + feature-id proximity, no hard foreign key), the correct response is not
   "this feature is dead," it's "route low-confidence pairings to human triage instead of
   auto-escalating them to a swarm review." A correlation-confidence score becomes part of the gate
   itself (low confidence → surface-only, human-reviewed; high confidence → eligible for the
   deterministic-flags tier; nothing is ever fully skipped to synthesis on weak evidence). This
   converts a binary go/no-go into a design constraint on the gate, which is exactly the kind of
   finding this leg is scoped to produce.

**What *would* make it truly fatal** (i.e. actually confirm the deal-killer, not just complicate it):
- Zero derivable linkage of any kind — no shared feature_id, no timestamp proximity, no cwd/project
  scoping, no frontmatter reference, and no cheap way to add one (e.g. because agent-authored AARs
  are produced in a system CCDash cannot touch and carry no session-identifying metadata at all).
- If linkage exists only as freeform prose inside the AAR body that would require an LLM read to
  extract (that would itself violate the no-LLM-on-recall-path constraint to even *establish* the
  correlation, which is a second, independent way the deal-killer could be triggered — worth the
  tech leg checking explicitly, since "the correlation itself requires a model call" is a subtler
  failure mode than "no correlation exists").

**Net**: leaning toward **refutable** conditional on the tech leg finding *any* cheap deterministic
signal (even partial/probabilistic) — the risk leg's job is to insist the gate design absorb
correlation uncertainty rather than assume a hard key. Final verdict belongs to the tech leg's data
findings.

---

## 5. Backward-compat / operational risks

- **Worker load**: A new triage job is another consumer of the same sync/watcher hot path already
  under active tuning (`CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`, `CCDASH_SYNC_COALESCING_ENABLED`,
  `CCDASH_SYNC_RECENT_FIRST_ENABLED`). It must reuse the existing `(project_id, trigger)`-keyed
  coalescing guard rather than introduce a second, uncoordinated scheduler — two schedulers racing
  the same JSONL files is how duplicate-flag or duplicate-escalation bugs get introduced. Precedent
  to follow: `ArtifactRollupExportJob` is a thin adapter over an existing coordinator with its own
  lock (`TelemetryExportCoordinator._lock` — `asyncio.Lock`, busy-returns rather than piling up).
- **DB write paths (ADR-006/007)**: Any new persisted state — a triage-flags table, a
  triaged-pairs ledger, an escalation-quota counter — is a **new write path** and must, per
  CLAUDE.md convention, use `repositories/base.py:retry_on_locked`, carry a direct-count assertion
  test, and (if a new column on an existing table) ship dual SQLite+PostgreSQL DDL in the same
  change with a `COLUMN_PARITY_DRIFT_ALLOWLIST` check. ADR-007's canonical failure mode — a swallowed
  write exception masquerading as success (the registry bootstrap bug that motivated the ADR) — is
  exactly the failure mode that would silently corrupt an escalation-quota ledger and defeat the
  cost-control guard in §1. This is not optional hardening; it is the specific historical bug class
  this feature would reintroduce if the write path skips the shared helper.
- **Registry authority (ADR-006)**: Any project-scoped triage job must resolve project identity via
  the DB-authoritative registry, never `projects.json` directly — same constraint as every other
  production write path in this codebase.
- **Redaction egress**: Session content that flows into a triage flag or a synthesis evidence bundle
  must pass through the same Layer-1/Layer-2 redaction path session-detail already enforces
  (`backend/application/services/agent_queries/redaction.py`, fail-closed defaults). A triage job
  that reads raw JSONL directly (bypassing the session-detail query service that already applies
  redaction) would be a redaction-bypass regression — and would be especially dangerous here because
  the eventual audience for a synthesis payload is an *external* system boundary (op/ARC/SkillMeat),
  which is a stronger egress boundary than an internal dashboard render.
- **Idempotency across restarts**: Worker restarts (common in dev, expected in prod during
  redeploys) must not cause a partially-triaged batch to double-fire escalations. The
  dedup-key + ledger pattern in §1 covers this if implemented; flagging it here because it's the
  kind of gap that only surfaces under redeploy load, not in a clean test run.

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Self-referential loop: AAR-review sessions get re-triaged as input to the next pass | Critical | Medium (structural, not hypothetical — sync engine re-scans on every FS event) | Provenance-tag exclusion via `skill_name`/`workflow_id` capture columns; never content-sniff (would require LLM on recall path) |
| Unbounded cost from auto-escalation to full ARC swarm | Critical | Medium-High if no ceiling shipped day 1 | Hard env-configured escalation quota, checked *before* handoff; CCDash never calls swarm directly, only hands off via `op`/ARC's own gated dispatch |
| Autonomous writeback into SkillMeat/agents/skills bypassing HITL | Critical | Low if design honors charter Out-of-Scope; High if a future increment "helpfully" shortcuts the gate | Recommendations land as `op story`-shaped drafts only; mirror `council_review_queries.py`'s read-only ownership line; no direct SkillMeat catalog mutation ever |
| LLM call required to *establish* AAR↔session correlation | High | Unknown — tech leg must check | If confirmed, correlation itself becomes a synthesis-tier operation gated same as deep-dive; cannot be a "cheap extract" |
| False-positive surface flags (e.g. "generic agent mis-assigned") drive bad recommendations at volume | High | Medium — heuristics are inherently approximate | Route low-confidence/heuristic-only flags to human review, never straight to synthesis-tier auto-recommendation |
| Persona/memory inbox flooded by high-frequency low-signal auto-recommendations | Medium | Medium if triage cadence is aggressive | Rate-limit recommendation emission independent of triage-flag computation cadence; keep triage (cheap, frequent) and recommendation-emission (gated, throttled) as separably-tunable cadences |
| Duplicate/racing triage schedulers against the same sync hot path | Medium | Medium if a new scheduler is added instead of reusing existing coalescing guard | Reuse `(project_id, trigger)` coalescing guard + a coordinator-level `asyncio.Lock` per the `TelemetryExportCoordinator` precedent |
| Silently-swallowed write failure in a new escalation-quota or triaged-pairs ledger (ADR-007 regression) | High | Medium — this exact bug class has occurred before in this codebase (registry bootstrap) | Mandatory `retry_on_locked`, direct-count assertion test, no bare `except Exception: log-and-continue` |
| Redaction bypass if triage reads raw JSONL instead of the redaction-passed session-detail service | High | Low-Medium — depends on implementation discipline | Triage must consume `session_detail.py`'s redacted output, never parse raw transcript files directly |
| Weak/probabilistic (not exact) AAR↔session correlation key | Medium | Medium-High per architectural reasoning above | Correlation confidence becomes part of gate logic — low confidence routes to human triage, never auto-escalates |
| Worker/watcher load increase from an added triage pass on every sync cycle | Low-Medium | Medium | Scope triage to changed/new AAR docs only (incremental, mirrors `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` pattern), not a full re-scan per cycle |
| Idempotency gap across worker restarts causing duplicate escalations | Medium | Low-Medium | Dedup key per `(aar_doc_id, session_id)` pair, same pattern as `emit_artifact_outcomes`'s `dedup_key` |

---

## Summary for verdict synthesis

- **Cost/recursion**: bounded and safe *only if* provenance-based self-exclusion + an idempotent
  ledger + an explicit escalation quota all ship together as day-1 requirements, not follow-ups.
  None of these are novel engineering — all three have direct precedent already in this codebase.
- **Blast radius**: safe *only if* CCDash's role terminates at evidence + flag + (gated) recommendation
  draft, mirroring the existing read-only relationship to ARC (`council_review_queries.py`). Any
  design that has CCDash writing directly into SkillMeat/agents/skills, even "just this once for a
  low-risk case," violates the charter's Out-of-Scope line and the AOS's HITL-gate contract.
- **Gate placement**: triage (deterministic, cheap, worker-side, feature-flagged) vs. synthesis
  (model-driven, expensive, delegated to `op`/ARC, HITL-gated) is a clean split that the codebase
  already models in miniature (telemetry exporter's flag-gated no-op-degrade pattern; council-review's
  read-only ARC-state consumption). The risk is entirely in *where the line gets drawn during
  implementation*, not in whether the line can be drawn.
- **Deal-killer**: not confirmed by this leg — leaning refutable *if* the tech leg finds any cheap
  deterministic signal (exact or probabilistic) to pair AAR↔session, because a probabilistic key can
  be absorbed into the gate design rather than requiring a hard foreign key. Confirmed fatal only if
  either (a) zero derivable linkage exists at all, or (b) establishing linkage itself requires an
  LLM call, which would violate the no-LLM-on-recall-path constraint independent of feasibility.
