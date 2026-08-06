---
schema_version: 2
doc_type: spike
title: "Hosted LLM Provider Strategy — One Coherent Lane for Every LLM-Enhanced Capability"
status: completed
created: 2026-08-06
updated: 2026-08-06
completed_date: 2026-08-06
spike_output: docs/project_plans/spikes/hosted-llm-provider-strategy.md
open_questions_ref: docs/project_plans/spikes/hosted-llm-provider-strategy-open-questions.md
recommendation: "Option (c) + (d) — keep httpx behind a provider-agnostic client seam; Anthropic wire format as the canonical hosted lane, ICA as the default endpoint. Agent SDK, OpenAI SDK, and the bare anthropic SDK all rejected."
unresolved_open_questions: 7
adrs_proposed: 3
feature_slug: hosted-llm-provider-strategy
complexity: medium
estimated_research_time: "3 days (1 engineer)"
prd_ref: null
plan_ref: null
itt_node_id: node_01KZCA2MAA0K0TWEPW0KZGC4WF
intenttree_workspace: ws_01KV8VMWX9EJ6VDQKEBMYQZRXG
related_documents:
  - docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
  - docs/guides/redaction-tuning.md
  - docs/guides/aar-review-loop.md
  - docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/ccdash-aar-review-semantic-triage-tier-feasibility-brief.md
research_questions:
  - "RQ-1: Who actually owns `session_embeddings` / bge-m3 — CCDash or an external producer? Trace the write path in `backend/` and settle it with code evidence. Highest priority: the answer determines whether an embedding lane is even in scope for the provider seam."
  - "RQ-2: What is the minimal provider-abstraction seam that serves all current LLM surfaces (dashboard insight, session naming local + hosted, any future embedding lane) WITHOUT adopting a provider SDK? Where does it live given the routers → services → repositories convention and the transport-neutral `agent_queries` pattern?"
  - "RQ-3: Does adopting an Anthropic-shaped client (SDK or httpx) buy enough over the current raw-httpx idiom to justify the dependency? Weigh: ICA Anthropic-API compatibility, retry/backoff, streaming need (does ANY surface need streaming today?), token counting, structured output."
  - "RQ-4: What are the auth/config surface changes — how do `CCDASH_*` env vars express a multi-provider, multi-lane config without combinatorial explosion? Propose concrete names consistent with `backend/config.py`."
  - "RQ-5: How is the redaction seam enforced STRUCTURALLY (not by convention) so a future provider lane cannot bypass it?"
  - "RQ-6: What does the empirical larger-model test look like — which surfaces, which models, which measured outcome decides GO?"
  - "RQ-7: What blast-radius controls belong in the design for a systematic sweep (~100 calls/day steady, ~20k backfill) vs. per-request user-triggered egress: opt-in flag placement, per-project consent, rate cap, backfill gate, observability?"
---

# SPIKE Charter: Hosted LLM Provider Strategy

## 1. Charter Purpose

CCDash has accreted LLM-enhanced capabilities one surface at a time, each with its own hand-rolled
transport, its own env vars, and its own degradation story. This SPIKE defines **one** coherent
hosted-LLM strategy covering every such capability, decides between four candidate shapes, and
specifies the chosen shape behind a single provider abstraction. It also specifies an empirical
larger-model test so the "is a bigger model worth it?" question stops being answered by intuition.

The charter defines research questions and scope only. Findings, the recommendation, rejection
reasons, and the phased implementation shape live in
[`hosted-llm-provider-strategy.md`](./hosted-llm-provider-strategy.md); unresolved items live in
[`hosted-llm-provider-strategy-open-questions.md`](./hosted-llm-provider-strategy-open-questions.md).

## 2. Decision Under Consideration

Choose ONE of:

| Option | Shape |
|---|---|
| (a) | Anthropic **Agent SDK** (`claude-agent-sdk`) |
| (b) | **OpenAI SDK** (`openai`) as the lingua-franca client |
| (c) | **Plain API keys over the existing `httpx` transport** behind a provider-agnostic client seam |
| (d) | **ICA gateway** as the hosted lane |

These are not fully mutually exclusive — (c) is a seam shape and (d) is an endpoint choice. The
SPIKE must state which combination it recommends and why the others are rejected.

## 3. Background — Measured Current State (main `65747be`, 2026-08-06)

- **Dashboard AI insight**: `POST /api/ai/insight` (`backend/routers/ai.py`), service
  `backend/services/ai_insight.py`. Gemini REST via raw `httpx`. Key `CCDASH_GEMINI_API_KEY`;
  returns `{disabled: true}` when unset.
- **Automatic session naming**: two backends selected by `CCDASH_SESSION_NAMING_BACKEND` —
  `local` (default, Ollama, headline AC is **zero off-box egress**) and `hosted` (Gemini REST,
  same `httpx` idiom). See
  [`automatic-session-naming-v1.md`](../PRDs/enhancements/automatic-session-naming-v1.md).
- **Embeddings / semantic mapping**: a `session_embeddings` table exists (Postgres schema `app`)
  and `bge-m3` is pulled on the agentic node, but no embedding-model config was found in
  `backend/config.py`. Ownership was **unconfirmed** at charter time — RQ-1 exists precisely to
  settle it with evidence rather than assumption.

**Key architectural fact**: there is **no provider SDK dependency anywhere in CCDash**. Every
hosted call is a hand-rolled `httpx` POST, and `backend/services/ai_insight.py:5` documents this as
deliberate ("Uses httpx (already a project dependency) — no new Python SDK is added"). Adopting
an Anthropic or OpenAI SDK is therefore a genuine architectural change — new dependency, new auth
surface, new retry semantics, new streaming surface — not an incremental swap. **The SPIKE must
justify any SDK adoption against simply keeping `httpx` and adding a provider-agnostic seam.**

## 4. Must-Hold Constraints

Any recommendation violating these is invalid.

1. **No model call on the read/render/recall path.** LLM work belongs in worker jobs or explicit
   user-triggered endpoints only. The AAR review loop is deterministic **by design**
   ([`aar-review-loop.md`](../../guides/aar-review-loop.md)) and stays model-free on its compute path.
2. **Resilience by default.** Every provider is optional. Absent key / unreachable provider is a
   *contract state*, not a bug — degrade, never fail the surface. `ai_insight`'s `{disabled: true}`
   is the established pattern.
3. **Redaction is the egress gate and must be preserved.** Hosted naming reads prompt material
   exclusively via `get_session_detail` in
   `backend/application/services/agent_queries/session_detail.py`, which runs `redact_entries`
   first. `CCDASH_REDACTION_PATTERNS_ENABLED` governs **both** hosted-lane reachability and the
   outbound scrub. Any new provider lane MUST route through that same seam — never read raw
   transcripts. See [`redaction-tuning.md`](../../guides/redaction-tuning.md).
4. **`local` (Ollama) stays a first-class supported lane**, not a legacy fallback. Zero-egress is a
   real product property for local CCDash users.

## 5. Decision Inputs (operator-supplied — evidence, not gospel)

- **The ICA trust boundary is already crossed.** ICA is the execution substrate for much of the
  AOS and already receives repo code and delegated task content. Egress to ICA is not a *new*
  exposure. Remaining nuance to weigh, not treat as a blocker: delegation sends material an agent
  *chose* to read, whereas a naming sweep would send *every* session systematically. That is a
  **blast-radius** difference, not a trust-boundary difference.
- **ICA is Anthropic-API-compatible**: `ANTHROPIC_BASE_URL=https://api.nextgen-beta.ica.ibm.com/ica`,
  serving `claude-haiku-4-5[1m]`, `claude-sonnet-5[1m]`, `claude-opus-5[1m]`. An Anthropic-shaped
  client reaches **both** ICA and Anthropic direct — a strong argument for the Anthropic wire
  format over OpenAI's, which the SPIKE must test rather than assume.
- **Cost**: ICA free tier vs. metered Anthropic/OpenAI keys. Naming alone ≈100 calls/day at current
  eligibility; a historical backfill ≈20k calls.
- **Node capacity for the local lane**: 23 GB RAM, ~14 GB free. `gemma2:2b` measured cold 20.0s /
  warm 6.9s; `CCDASH_OLLAMA_TIMEOUT_SECONDS` now 60.

## 6. Out of Scope

- **Making the AAR loop model-driven** — settled NO-GO. Cite
  [`ccdash-aar-review-semantic-triage-tier`](../exploration/ccdash-aar-review-semantic-triage-tier/ccdash-aar-review-semantic-triage-tier-feasibility-brief.md);
  do not re-explore.
- **Any change that puts a model call on a render path.**
- Full Tier-3 implementation planning. The findings doc carries a high-level phased shape only.

## 7. Expected Outputs

| Output | Path | Status |
|---|---|---|
| Findings, recommendation, phased shape | [`hosted-llm-provider-strategy.md`](./hosted-llm-provider-strategy.md) | **written** — all RQs resolved |
| Unresolved / deferred questions | [`hosted-llm-provider-strategy-open-questions.md`](./hosted-llm-provider-strategy-open-questions.md) | **written** — 7 open questions (OQ-1..OQ-7) |
| ADR candidates | Named in the findings doc § ADR Candidates | **proposed, not authored** — ADR-016/017/018; authored only if the recommendation is accepted |

**RQ resolution status**: RQ-1 through RQ-7 are all answered in the findings doc. RQ-1 (embeddings
ownership) is settled with code evidence — CCDash never computes a vector; only the *external
producer* sub-question survives, as OQ-1. RQ-3 and RQ-6 carry an implementation-time verification
dependency on live Anthropic model ids and pricing (OQ-2), which does not affect the recommendation.

## 8. Method

Parallel investigation legs:

| Leg | Question set | Method |
|---|---|---|
| Codebase mapping | RQ-1, and the current-state evidence base for RQ-2/RQ-4/RQ-5 | Grep + read every LLM/embedding call path in `backend/`; trace the `session_embeddings` write path to a terminal statement |
| Seam design | RQ-2, RQ-4, RQ-5, RQ-7 | Design against the layered convention; propose port + adapter placement, config scheme, enforcement mechanism |
| Provider research | RQ-3, RQ-6, plus the model-id/pricing basis | Verify Anthropic/OpenAI SDK surface and ICA compat specifics against live docs; no answers from memory on model ids or pricing |

**Verification rule** (binding, and the reason this section exists): this repo has a documented
failure mode where doc-writing agents invent flag names, enum values, schema versions, and API
surfaces. Every env var, file path, function name, and model id in the outputs must be
grep-verified against runtime truth or explicitly marked as a **proposal**. Anything that could not
be verified is recorded as an open question, never asserted.
