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
(keep `httpx`, add a provider-agnostic seam, Anthropic wire format via ICA).

> **Update 2026-08-07 — OQ-2 and OQ-3 are RESOLVED.** Both were the implementation blockers; both
> are now answered (OQ-2 from the `claude-api` skill, OQ-3 by direct probe against the ICA gateway).
> Results are recorded in the rows below and in
> [§ Empirical Addendum](./hosted-llm-provider-strategy.md#empirical-addendum--ica-compat-probe-2026-08-07)
> of the findings doc. **Nothing now blocks P1.** One assumption was falsified in the process — see
> the new **OQ-8**, which is a correction, not an open question.

| ID | Question | Why unresolved | Blocks | Owner / next step |
|---|---|---|---|---|
| **OQ-1** | Who is expected to populate `app.session_embeddings.embedding`? CCDash writes literal `NULL` (`backend/db/repositories/postgres/session_embeddings.py:53-58`) and `bge-m3` is pulled on the agentic node, but no CCDash code path connects them. Is there an external producer, was one planned and dropped, or is the column speculative? | Settled what CCDash does (nothing); could not identify an out-of-repo producer from inside this repo. | Nothing in this SPIKE — the embedding lane is explicitly out of scope for the seam's v1. | Operator. Check the node for a non-CCDash writer; if none exists, decide whether the column is aspirational or should be dropped. |
| **OQ-2** ✅ **RESOLVED 2026-08-07** | Exact Anthropic Messages API endpoint path, required version header **value**, current model ids, and per-MTok input/output rates for the small/mid tiers — plus which of those ids ICA actually serves. | Answered from the `claude-api` skill (authoritative, not memory), then endpoint + headers confirmed by live probe. | ~~P3, P4~~ — **unblocked**. | **Endpoint** `POST /v1/messages`. **Version header** `anthropic-version: 2023-06-01`. **Rates** (per MTok in/out): `claude-haiku-4-5` $1/$5 (200K ctx, 64K max output — the only current model that is *not* 1M); `claude-sonnet-5` $3/$15 ($2/$10 introductory through 2026-08-31); `claude-opus-5` $5/$25. Cheap classification/naming arm = **`claude-haiku-4-5`**. The cost formula's one remaining unmeasured input is the actual per-call token count — measure from `build_prompt_text` before quoting a figure. |
| **OQ-3** ✅ **RESOLVED 2026-08-07** | Does ICA's Anthropic-compatible surface implement everything the adapter assumes — same auth header shape, same version header handling, same response envelope, and does it reject or ignore unknown fields? | Probed directly: four requests against `https://api.nextgen-beta.ica.ibm.com/ica/v1/messages`, all HTTP 200. | ~~P3~~ — **unblocked**. | **Yes, with two caveats.** Envelope is standard Messages (`content/id/model/role/stop_reason/stop_sequence/type/usage`; `usage` carries `cache_creation`/`cache_read`). Auth: **both** `x-api-key` and `Authorization: Bearer` accepted. Version header is **optional** on ICA (200 without it) — send it anyway, it is required on Anthropic direct. **Caveat 1:** ICA **ignores** unknown top-level fields (`ccdash_unknown_probe: true` → 200) where Anthropic direct would 400 — so ICA is *not* a validation lane; ICA-green proves nothing about correctness. **Caveat 2:** ICA is **Bedrock-backed** (`msg_bdrk_…` response ids), so the Bedrock feature mask plausibly applies (no Batches / Files API / Models API / automatic prompt caching / web search·fetch / code execution). None are in v1 scope, but do not design a future surface on an unprobed feature there. |
| **OQ-4** | Does Gemini expose an OpenAI-compatible `/v1/chat/completions` endpoint that would also be reachable by an OpenAI-shaped client? | Not verified. | Nothing — recorded only for completeness of the option-(b) rejection. Even if true, ICA's Anthropic-compat is the deciding factor, so the verdict is unchanged. | Optional. Only revisit if ICA's Anthropic-compat surface turns out to be unusable (OQ-3 fails). |
| **OQ-5** ✅ **RESOLVED 2026-08-09** | Charter decision inputs state `CCDASH_OLLAMA_TIMEOUT_SECONDS` "is now 60", but the code default is **15** (`backend/config.py:253`) and no in-repo file sets 60 — not `.env.example`, not `docker-compose.yml`, not `deploy/runtime/compose.hosted.yml`. | Both halves of the drift confirmed and closed. **Where the 60 lived:** `agentic_meta_dev/infra/agentic-node/bootstrap-agentic-node.sh` wrote `CCDASH_OLLAMA_TIMEOUT_SECONDS=60` into the node's `deploy/runtime/.env` on 2026-08-06 with the cold-start rationale inline — a *deliberate* deployment override, in another repo, which is why an in-CCDash search found nothing. Confirmed live: `podman exec ccdash_worker_1 env` shows `60`. **Why 15 was wrong, not merely low:** re-measured from inside the worker container over the real request path — **cold 25.6s** (9.1s of it model load) vs warm 13.7s, at `MAX_PROMPT_CHARS`-length prompt. Worse than the 20.0s previously believed. A 15s ceiling could not succeed on a tick's first call, and since the sweep interval (1800s) exceeds Ollama's 5m keep_alive, **every** tick starts cold — three timeouts, breaker opens (`_CONSECUTIVE_FAILURE_THRESHOLD = 3`), tick yields nothing, near-silently. | Nothing decision-wise; the drift is closed. | **Done — the repo now tells the truth.** `config.py`'s default raised 15 → **60**, matching the deployed value, with the measurement recorded inline; `deploy/runtime/compose.yaml` and `deploy/runtime/.env.example` moved in lockstep. The original "short by design" fail-fast intent is preserved by the consecutive-failure breaker (a wedged daemon costs ≤ 3× the timeout), not by the timeout itself — so raising it does not reintroduce the stall it guarded against. Re-measure if `CCDASH_OLLAMA_MODEL` changes: this value is a function of model × host, not a constant. |
| **OQ-6** | Is `SessionTranscriptService.list_session_logs` (`backend/application/services/sessions.py:93`) reading JSONL directly or the DB cache? | Out of the investigation's scope; the class body was not opened. Does not affect the redaction argument — either way it returns pre-redaction content and the envelope factory is what gates it. | Nothing. | Read the class when implementing the guardrail test, to make the denylist precise. |
| **OQ-7** | Should the `gemini` lane be deprecated once the Anthropic lane exists, or retained indefinitely? | Deliberately not decided. Retaining it costs one small adapter; removing it is a user-visible behaviour change for anyone whose `CCDASH_SESSION_NAMING_BACKEND=hosted` currently means Gemini. | Nothing — findings doc retains it and does not extend it. | Revisit after P4. If the experiment promotes an Anthropic-lane model, a deprecation note (not a removal) is the likely answer. |
| **OQ-8** ⚠️ **CORRECTION, not an open question** | The charter's decision inputs state ICA serves `claude-haiku-4-5[1m]`, `claude-sonnet-5[1m]`, `claude-opus-4-8[1m]`. **Falsified against the raw Messages endpoint 2026-08-07:** every `[1m]`-suffixed id returns **403 `team_model_access_denied`** — *"This team can only access models=['global-models']"*. Bare `claude-haiku-4-5` and `claude-sonnet-5` return 200. | The `[1m]` convention evidently lives in the Claude Code + `ica-settings.json` layer, not in what the gateway's `/v1/messages` endpoint accepts. Probed with the **default** key from `~/.dotfiles/ICA_CLAUDE`; a named `ICA_KEY` block may have broader access. | Nothing — but it changes what the adapter must send. | **The adapter MUST use bare model ids.** Consistent with the known dated-id failure (`claude-haiku-4-5-20251001` → 401), which is the same `global-models` scoping. If CCDash is ever pointed at a different ICA key, re-probe before assuming `[1m]` works. |

## Explicitly closed, not open

- **Q1 (embeddings ownership)** — settled with code evidence: CCDash never computes a vector. Only the
  *external producer* sub-question survives, as OQ-1.
- **Whether any surface needs streaming** — closed: no, and the no-model-on-render-path constraint
  means none plausibly will.
- **Whether the AAR loop should become model-driven** — settled NO-GO before this SPIKE
  (`docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/`, `verdict: no-go`,
  confidence 0.8). Out of scope; not re-explored.
