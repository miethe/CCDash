---
schema_version: 2
doc_type: spike
title: "Hosted LLM Provider Strategy — Open Questions"
description: "Unresolved items from the hosted-llm-provider-strategy SPIKE. Each is recorded here rather than asserted in the findings doc, per the verification rule."
status: completed
created: 2026-08-06
updated: 2026-08-06
feature_slug: hosted-llm-provider-strategy
charter_ref: docs/project_plans/spikes/hosted-llm-provider-strategy-charter.md
spike_ref: docs/project_plans/spikes/hosted-llm-provider-strategy.md
---

# Hosted LLM Provider Strategy — Open Questions

These were deliberately **not** asserted in
[the findings doc](./hosted-llm-provider-strategy.md). None of them changes the recommendation
(keep `httpx`, add a provider-agnostic seam, Anthropic wire format via ICA); OQ-2 and OQ-3 are
blocking for **implementation**, not for the decision.

| ID | Question | Why unresolved | Blocks | Owner / next step |
|---|---|---|---|---|
| **OQ-1** | Who is expected to populate `app.session_embeddings.embedding`? CCDash writes literal `NULL` (`backend/db/repositories/postgres/session_embeddings.py:53-58`) and `bge-m3` is pulled on the agentic node, but no CCDash code path connects them. Is there an external producer, was one planned and dropped, or is the column speculative? | Settled what CCDash does (nothing); could not identify an out-of-repo producer from inside this repo. | Nothing in this SPIKE — the embedding lane is explicitly out of scope for the seam's v1. | Operator. Check the node for a non-CCDash writer; if none exists, decide whether the column is aspirational or should be dropped. |
| **OQ-2** | Exact Anthropic Messages API endpoint path, required version header **value**, current model ids, and per-MTok input/output rates for the small/mid tiers — plus which of those ids ICA actually serves under its `[1m]` suffix convention. | Model ids and pricing change; this repo has a documented failure mode of agents inventing them. Not answered from memory by deliberate choice. | **P3** (adapter implementation) and **P4** (naming the experiment's arms B and C). | Verify against live Anthropic docs at implementation time; use the `claude-api` skill. The cost *formula* in the findings doc is rate-independent and already usable. |
| **OQ-3** | Does ICA's Anthropic-compatible surface implement everything the adapter assumes — same auth header shape, same version header handling, same response envelope, and does it reject or ignore unknown fields? | Not empirically probed during this SPIKE. | **P3**. | One `curl` against `https://api.nextgen-beta.ica.ibm.com/ica` with a minimal Messages payload settles it before the adapter is written. |
| **OQ-4** | Does Gemini expose an OpenAI-compatible `/v1/chat/completions` endpoint that would also be reachable by an OpenAI-shaped client? | Not verified. | Nothing — recorded only for completeness of the option-(b) rejection. Even if true, ICA's Anthropic-compat is the deciding factor, so the verdict is unchanged. | Optional. Only revisit if ICA's Anthropic-compat surface turns out to be unusable (OQ-3 fails). |
| **OQ-5** | Charter decision inputs state `CCDASH_OLLAMA_TIMEOUT_SECONDS` "is now 60", but the code default is **15** (`backend/config.py:253`) and no in-repo file sets 60 — not `.env.example`, not `docker-compose.yml`, not `deploy/runtime/compose.hosted.yml`. | The 60 appears to be an operator-local or node-side override with no repo representation. Given defect 6 (no LLM env var reaches any container), it is unclear whether the override is even in effect where it was believed to be. | Nothing decision-wise, but it is a live config-drift signal. | Operator. Confirm where 60 is set; if it is the intended default, change `config.py` so the repo tells the truth. |
| **OQ-6** | Is `SessionTranscriptService.list_session_logs` (`backend/application/services/sessions.py:93`) reading JSONL directly or the DB cache? | Out of the investigation's scope; the class body was not opened. Does not affect the redaction argument — either way it returns pre-redaction content and the envelope factory is what gates it. | Nothing. | Read the class when implementing the guardrail test, to make the denylist precise. |
| **OQ-7** | Should the `gemini` lane be deprecated once the Anthropic lane exists, or retained indefinitely? | Deliberately not decided. Retaining it costs one small adapter; removing it is a user-visible behaviour change for anyone whose `CCDASH_SESSION_NAMING_BACKEND=hosted` currently means Gemini. | Nothing — findings doc retains it and does not extend it. | Revisit after P4. If the experiment promotes an Anthropic-lane model, a deprecation note (not a removal) is the likely answer. |

## Explicitly closed, not open

- **Q1 (embeddings ownership)** — settled with code evidence: CCDash never computes a vector. Only the
  *external producer* sub-question survives, as OQ-1.
- **Whether any surface needs streaming** — closed: no, and the no-model-on-render-path constraint
  means none plausibly will.
- **Whether the AAR loop should become model-driven** — settled NO-GO before this SPIKE
  (`docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/`, `verdict: no-go`,
  confidence 0.8). Out of scope; not re-explored.
