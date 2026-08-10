---
title: "Feature Contract: TextCompletionPort Seam (P1 — Zero Behaviour Change)"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: "Introduce TextCompletionPort + PromptEnvelope over httpx and move the three existing LLM call sites behind it, with zero observable behaviour change."
status: draft
created: 2026-08-10
updated: 2026-08-10
feature_slug: textcompletionport-seam-p1
category: "refactors"
estimated_points: 6
tier: 1
owner: null
priority: medium
risk_level: low
changelog_required: false
node_type: work_package
acceptance_criteria: []
definition_of_done: "All five existing test files pass unmodified; ai_insight response shapes are byte-identical; redaction seam (session_detail.get_session_detail -> redact_entries) remains the exclusive prompt-material source for both naming lanes."
execution_mode: unassigned
agent_title: "Land TextCompletionPort seam over httpx (P1, zero behaviour change)"
agent_summary: "Extract a TextCompletionPort protocol + PromptEnvelope dataclass and ollama/gemini adapters; move the three existing httpx call sites behind them without changing any observable behaviour."
agent_context: "Seed context: backend/application/ports/, backend/services/session_naming_local_backend.py, backend/services/session_naming_hosted_backend.py, backend/services/session_naming_prompt.py, backend/services/ai_insight.py, backend/runtime/container.py, backend/routers/ai.py, docs/project_plans/spikes/hosted-llm-provider-strategy.md (proposal at line ~399, phase description at lines 703-746)."
open_questions: []
decisions:
  - decision: "Single autonomous sprint (Tier 1, execute-contract), not a multi-wave plan."
    rationale: "Bounded pure-transport refactor across 4 existing files + 1 new port module + 2 new adapter modules; no new tests, no new config, no new egress — well under the Tier 2 large-file/complexity thresholds."
    status: accepted
scores: {}
related_documents:
  - docs/project_plans/spikes/hosted-llm-provider-strategy.md
spike_ref: docs/project_plans/spikes/hosted-llm-provider-strategy.md
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/application/ports/llm.py
  - backend/adapters/llm/__init__.py
  - backend/adapters/llm/ollama.py
  - backend/adapters/llm/gemini.py
  - backend/services/session_naming_prompt.py
  - backend/services/session_naming_local_backend.py
  - backend/services/session_naming_hosted_backend.py
  - backend/services/ai_insight.py
---

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 6,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 8,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/refactors/textcompletionport-seam-p1.md",
  "execution_target": "execute-contract",
  "slug": "textcompletionport-seam-p1",
  "category": "refactors",
  "review_intensity": "standard",
  "files_affected": [
    "backend/application/ports/llm.py",
    "backend/adapters/llm/__init__.py",
    "backend/adapters/llm/ollama.py",
    "backend/adapters/llm/gemini.py",
    "backend/services/session_naming_prompt.py",
    "backend/services/session_naming_local_backend.py",
    "backend/services/session_naming_hosted_backend.py",
    "backend/services/ai_insight.py"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Land TextCompletionPort seam over httpx (zero behaviour change)",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "assigned_to": "refactoring-expert",
                "effort": 6,
                "files_affected": [
                  "backend/application/ports/llm.py",
                  "backend/adapters/llm/__init__.py",
                  "backend/adapters/llm/ollama.py",
                  "backend/adapters/llm/gemini.py",
                  "backend/services/session_naming_prompt.py",
                  "backend/services/session_naming_local_backend.py",
                  "backend/services/session_naming_hosted_backend.py",
                  "backend/services/ai_insight.py"
                ],
                "prompt": "Mode C: Autonomous Feature Sprint. This is a PURE TRANSPORT REFACTOR — zero behaviour change is the entire point. Read docs/project_plans/feature_contracts/refactors/textcompletionport-seam-p1.md in full before starting; it is your spec. Also read the seam proposal at docs/project_plans/spikes/hosted-llm-provider-strategy.md around line 399 (PromptProvenance/PromptEnvelope sketch) and lines 703-746 (P1 exit criteria) for the design intent — you are implementing that proposal, not inventing a new shape.\n\nSteps:\n1. Create backend/application/ports/llm.py: a `TextCompletionPort` Protocol (one async method, e.g. `async def complete(self, envelope: PromptEnvelope) -> str | None`), a `PromptProvenance` StrEnum (`AGGREGATE`, `TRANSCRIPT_REDACTED`), and a frozen `PromptEnvelope` dataclass (`text: str`, `provenance: PromptProvenance`, `redaction_events: int = 0`). Provide two factory functions only: `envelope_from_aggregate(text: str) -> PromptEnvelope` and `envelope_from_redacted_transcript(text: str, redaction_events: int) -> PromptEnvelope` (the latter should raise if `agent_queries.redaction.redaction_patterns_enabled()` is False — fail-closed at the egress boundary, mirroring the read path's existing fail-open-on-read but converting it to fail-closed-on-egress per the spike proposal). Follow the existing port-module conventions in backend/application/ports/core.py and ingest.py (module docstring, `__all__`, dataclass style) and register new names in backend/application/ports/__init__.py.\n2. Create backend/adapters/llm/ (new package, __init__.py + ollama.py + gemini.py). Move `_call_ollama`'s HTTP body (currently in backend/services/session_naming_local_backend.py, the `_call_ollama` method) into an `OllamaTextCompletionAdapter` implementing `TextCompletionPort`, constructed with base_url/model/timeout_seconds. Move `_call_gemini`'s HTTP body (backend/services/session_naming_hosted_backend.py) into a `GeminiTextCompletionAdapter` implementing the same port, constructed with api_key/model/timeout_seconds. Preserve every existing behavior exactly: same URLs, same payload shapes, same raise-on-error semantics (the adapter's `complete` method raises on transport/HTTP error exactly like `_call_ollama`/`_call_gemini` do today — the caller still owns fail-open wrapping). httpx only, no new SDK.\n3. Update backend/services/session_naming_local_backend.py and session_naming_hosted_backend.py to construct their respective adapter and call `adapter.complete(envelope)` instead of `self._call_ollama(prompt_text)` / `self._call_gemini(prompt_text)`. Delete the now-dead `_call_ollama`/`_call_gemini` methods (or leave as thin deprecated wrappers only if that's materially safer — default is delete). All circuit-breaker, fail-open, redaction-gate, and persistence logic in `derive_name` stays completely unchanged; only the transport call is redirected through the port.\n4. Retype backend/services/session_naming_prompt.py's `build_prompt_text(items) -> str` to `build_prompt_text(items) -> PromptEnvelope`, returning `envelope_from_redacted_transcript(joined_text, redaction_events=<count>)` (redaction_events count: use whatever count is available from the caller's session_detail bundle at the call site — if no count is currently threaded through, pass 0 with a comment, do NOT invent a fake redaction pipeline). Update both call sites (local_backend.py, hosted_backend.py) to pass `envelope.text` into the adapter/prompt-instruction formatting exactly as `prompt_text` was used before (i.e., the instruction-wrapping string stays byte-identical; only the type of the intermediate value changes). Keep the empty-prompt check (`if not prompt_text` -> now check `if not envelope.text`).\n5. Update backend/services/ai_insight.py: replace its inline httpx POST block with a `GeminiTextCompletionAdapter` (constructed with `envelope_from_aggregate(prompt)` since this call site sends aggregated dashboard metrics, never transcript content — per the module's own docstring). Preserve exact response shapes: `{disabled:true}` with no key, `AIInsightResult(text=...)` on success, `AIInsightResult(error=...)` on failure, byte-identical to today.\n6. Do NOT add httpx to requirements.txt (already a dependency per ai_insight.py's own docstring), do NOT add auth to the ai router, do NOT touch config.py, do NOT touch backend/runtime/container.py's `resolve_naming_backend` wiring beyond what's mechanically required by the rename (it should still work unchanged — this task does not touch it directly unless an import path breaks). This is P1 ONLY: no new provider, no new egress, no config change, no compose changes.\n\nRun and verify UNMODIFIED (do not edit any of these five test files — if one fails, your refactor is wrong, not the test):\n- backend/.venv/bin/python -m pytest backend/tests/test_session_naming_hosted_backend.py -v\n- backend/.venv/bin/python -m pytest backend/tests/test_session_naming_local_backend.py -v\n- backend/.venv/bin/python -m pytest backend/tests/test_ai_insight_router.py -v\n- backend/.venv/bin/python -m pytest backend/tests/test_session_naming_read_path_no_model_client.py -v (CRITICAL — this statically walks read-path imports; your new backend/adapters/llm/ and backend/application/ports/llm.py modules must never become reachable from any read-path router/service, only from the two naming-backend modules and ai_insight.py)\n- backend/.venv/bin/python -m pytest backend/tests/test_session_naming.py backend/tests/test_session_naming_sweep_guards.py backend/tests/test_session_naming_sweep_job.py -v (adjacent coverage, should also stay green)\n\nAlso verify: the redaction seam is preserved — grep session_naming_local_backend.py and session_naming_hosted_backend.py to confirm `get_session_detail(... include={INCLUDE_TRANSCRIPT})` is still the ONLY source of transcript text feeding `build_prompt_text`; no raw JSONL read was introduced.\n\nProduce a Completion Report per .claude/skills/dev-execution/validation/completion-criteria.md (files changed, tests run + results, deviations, risks). Do NOT git add/commit/push/stash."
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "If the sprint discovers the redaction_events count cannot be threaded through get_session_detail's bundle without a signature change beyond this seam's scope, or if build_prompt_text's retype ripples into more than the two naming backends + ai_insight, stop and promote to a Tier 2 PRD + milestone plan rather than stretching this contract — cite docs/project_plans/spikes/hosted-llm-provider-strategy.md P2 as the natural next-phase home for anything that grows beyond a pure transport swap."
}
```

# Feature Contract: TextCompletionPort Seam (P1 — Zero Behaviour Change)

## 1. Goal

Introduce a `TextCompletionPort` protocol + `PromptEnvelope` value type over `httpx`, and move the
three existing raw HTTP call sites (`_call_ollama`, `_call_gemini`, `ai_insight`'s inline block)
behind it, with **zero observable behaviour change** — this is Phase P1 of the hosted-LLM-provider
strategy (`docs/project_plans/spikes/hosted-llm-provider-strategy.md` §Phased Implementation Shape,
lines 703–746).

---

## 2. User / Actor

- **Primary user**: Future engineers/agents extending the LLM call surface (P2+ of the strategy
  doc) — they inherit a typed seam instead of three near-duplicate httpx blocks.
- **Secondary users**: None end-user-visible. This is a pure internal transport refactor.

---

## 3. Job To Be Done

When **a future phase needs to add a new LLM provider or tighten the egress boundary** (P2's auth
hardening, P3's Anthropic lane + consent gating), the codebase wants to **already have a single
typed port and adapter shape to extend**, so it can **add the new provider/adapter without touching
three independent httpx call sites again**.

---

## 4. Scope

### In Scope

- `TextCompletionPort` Protocol + `PromptEnvelope`/`PromptProvenance` in `backend/application/ports/llm.py`
- `OllamaTextCompletionAdapter` and `GeminiTextCompletionAdapter` under a new `backend/adapters/llm/` package
- Migrating `LocalOllamaNamingBackend._call_ollama`, `HostedGeminiNamingBackend._call_gemini`, and
  `ai_insight.generate_dashboard_insight`'s inline httpx block to call through the new adapters
- Retyping `session_naming_prompt.build_prompt_text` to return a `PromptEnvelope` instead of `str`

### Out of Scope

- Any new provider (Anthropic, etc.) — that is P3
- Any new egress, config surface, or consent gating — that is P3
- `httpx` requirements.txt declaration, auth on `/api/ai/insight`, credential-in-URL fixes, compose
  env allowlist changes, redaction-provenance guardrail test — those are P2 (already largely closed
  per the 2026-08-09 update in the spike doc; not this contract's job)
- Any change to `resolve_naming_backend`'s selection logic or `CCDASH_SESSION_NAMING_BACKEND` semantics

---

## 5. UX / Behavior Requirements

- No observable behavior changes anywhere. `ai_insight` still returns `{disabled:true}` with no key
  and an `error` string on failure, byte-identically.
- Both naming lanes' fail-open/circuit-breaker/redaction-gate semantics are unchanged; only the
  transport call underneath is redirected through the new port.

---

## 6. Data Requirements

- No schema changes, no new DB columns, no new persisted fields.
- `PromptEnvelope` is an in-memory, request-scoped value object — never persisted.

---

## 7. API / Integration Requirements

**No new or modified endpoints.** `POST /api/ai/insight` keeps its existing contract exactly.

**Internal service dependencies:**
- `backend/adapters/llm/ollama.py` / `gemini.py` — new adapters, httpx-only, no new SDK
- `backend/application/ports/llm.py` — new port module, consumed by both naming backends and `ai_insight`

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/application/ports/core.py` / `ingest.py` — Protocol + dataclass port conventions
- `ai_insight.py`'s existing fail-open/try-except-at-call-site shape

**Must not change** (protected areas):
- `resolve_naming_backend`'s selection logic and reachability guards
- `session_detail.get_session_detail` → `redact_entries` as the exclusive prompt-material source
- Any of the five named test files (listed in §9) — unmodified pass is the contract

**New dependencies:**
- Allowed? **No.** httpx only — no provider SDK. `ai_insight.py:5` already documents this as
  deliberate; this contract does not revisit that decision.

---

## 9. Acceptance Criteria

- [ ] `backend/tests/test_session_naming_hosted_backend.py` passes unmodified
- [ ] `backend/tests/test_session_naming_local_backend.py` passes unmodified
- [ ] `backend/tests/test_ai_insight_router.py` passes unmodified
- [ ] `backend/tests/test_session_naming_read_path_no_model_client.py` passes unmodified (the
      no-model-on-read-path guard — new adapter/port modules must never become reachable from any
      read-path router/service)
- [ ] `ai_insight` still returns `{disabled:true}` with no key, and an `error` string on failure,
      byte-identically
- [ ] Redaction seam preserved: prompt material reaches providers exclusively via
      `session_detail.get_session_detail` (which runs `redact_entries` first); no raw transcript
      read introduced anywhere in the new adapter/port code

---

## 10. Validation Requirements

- [ ] All five named existing test files pass, run unmodified
- [ ] Adjacent coverage (`test_session_naming.py`, `test_session_naming_sweep_guards.py`,
      `test_session_naming_sweep_job.py`) stays green
- [ ] Grep confirms no adapter/port module bypasses `get_session_detail`
- [ ] No unrelated changes introduced (no config.py, no requirements.txt, no compose files)

---

## 11. Risk Areas

- **Static import-graph test (`test_session_naming_read_path_no_model_client.py`)**: the new
  `backend/adapters/llm/` package and `backend/application/ports/llm.py` must stay reachable only
  from the two naming backends and `ai_insight.py` — never from a read-path router/service. This is
  the test most likely to catch an accidental wiring mistake.
- **`build_prompt_text` retype ripple**: changing its return type from `str` to `PromptEnvelope`
  touches both naming backends' call sites; keep the instruction-formatting string byte-identical
  by using `envelope.text` in place of the old `prompt_text` variable, not by changing the prompt
  wording.
- **Redaction-events count**: `envelope_from_redacted_transcript` wants a redaction-event count per
  the spike's proposal; if that count is not currently threaded through the caller's bundle, pass 0
  with an inline comment rather than fabricating a count — do not invent new instrumentation in this
  pass (that is P2/P3 territory).

---

## 12. Implementation Notes

**Suggested approach:**
- Start with the port module (`backend/application/ports/llm.py`) since everything else depends on
  its shape.
- Build the two adapters next, copy-pasting the exact existing httpx bodies from `_call_ollama`
  and `_call_gemini` with minimal reshaping.
- Wire the two naming backends, then `ai_insight.py`, last, since `ai_insight` uses the aggregate
  (non-transcript) envelope factory and is otherwise independent.

**Similar existing code:**
- `backend/application/ports/core.py` and `ingest.py` — Protocol + `@runtime_checkable` + frozen
  dataclass conventions to mirror.

**Known gotchas:**
- `test_session_naming_read_path_no_model_client.py` does a static AST-level import walk — an
  unused/dangling import added anywhere in a read-path module during cleanup can trip it.

---

## 13. Completion Report Required

Per `.claude/skills/dev-execution/validation/completion-criteria.md`: files changed, tests run +
results, deviations from contract, risks/limitations, follow-up recommendations (in particular:
whether the redaction-events count should be threaded through in a follow-on P2 task).

---

## Metadata & References

**Tier**: 1 (6 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents**:
- `docs/project_plans/spikes/hosted-llm-provider-strategy.md` (§Phased Implementation Shape, P1; seam proposal ~line 399)

---

## Notes for Agents

This contract is your specification. This is a **pure transport refactor** — the entire point is
that nothing observable changes. If a test fails, the refactor is wrong; do not edit the test to
make it pass. Stay within P1 scope: no new provider, no new egress, no config change. Flag any
scope ambiguity in the Completion Report rather than expanding scope.
