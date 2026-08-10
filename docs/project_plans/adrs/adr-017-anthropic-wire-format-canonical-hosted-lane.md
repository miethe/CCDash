---
title: "ADR-017: Anthropic Wire Format Is the Canonical Hosted Lane; ICA Is the Default Endpoint"
type: "adr"
status: "accepted"
created: "2026-08-10"
parent_prd: "docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md"
depends_on_spike: "docs/project_plans/spikes/hosted-llm-provider-strategy.md"
supersedes: null
related_adrs: ["adr-016-provider-agnostic-llm-client-seam-over-httpx.md", "adr-018-redaction-provenance-carried-by-type.md"]
tags: ["adr", "llm", "hosted-egress", "anthropic", "ica", "provider-strategy"]
---

# ADR-017: Anthropic Wire Format Is the Canonical Hosted Lane; ICA Is the Default Endpoint

## Status

Accepted (SPIKE-resolved 2026-08-07, ratified as part of M3 of
`hosted-llm-anthropic-ica-lane-v1`, 2026-08-10).

## Context

`hosted-llm-provider-strategy.md` (SPIKE) established a provider-agnostic `TextCompletionPort`
seam (ADR-016, proposed elsewhere and already shipped as the P1 `TextCompletionPort` refactor)
so every hosted-egress call site — the derived-naming sweep and the dashboard-insight
endpoint — speaks through one typed port instead of three near-duplicate `httpx` blocks. ADR-016
settles *how* CCDash calls out; it does not settle *which wire format* the hosted lane speaks or
*which endpoint* is the default target. Both of those are strategy decisions the tracker node
explicitly asked for, and both were left open by ADR-016.

Three wire-format candidates existed for the new hosted adapter:

1. **Anthropic Messages API format**, reachable both via IBM's internal ICA gateway
   (`https://api.nextgen-beta.ica.ibm.com/ica`) and via Anthropic direct
   (`https://api.anthropic.com`) — both endpoints accept the same request/response shape.
2. **OpenAI-compatible chat-completions format**, which Ollama (the existing local/loopback lane)
   already serves, and which several hosted providers also expose as a compatibility surface.
3. **A provider SDK** (`anthropic`, `openai`) — rejected outright under ADR-016 for reasons
   unrelated to wire format (vendors a fourth HTTP stack, retry/backoff undesirable against an
   existing circuit breaker and fail-open contract); not re-litigated here.

The genuinely competing choice, once the SDK question is closed, is Anthropic-format vs.
OpenAI-compat format — and the OpenAI-compat path has a real, non-trivial argument in its favor:
**Ollama already serves an OpenAI-compatible surface.** Choosing OpenAI-compat as the hosted wire
format would have let one adapter shape serve *both* the local lane and the hosted lane, unifying
local and hosted behind a single client shape. That argument is real enough that a future
contributor will re-derive it and question why it was not taken — this ADR exists to record why it
was not.

## Decision

**Hosted egress speaks the Anthropic Messages wire format, reached through a single adapter with a
configurable base URL. ICA is the default endpoint for that lane.**

Concretely:

- `backend/adapters/llm/anthropic.py` (`AnthropicTextCompletionAdapter`) implements the Anthropic
  Messages API (`POST {base_url}/v1/messages`) exactly once. **There is no provider-branching flag
  anywhere in this adapter** — `base_url` alone selects ICA vs. Anthropic direct. One ~150-line
  adapter serves both trust postures.
- **ICA is the default endpoint**, not Anthropic direct. This is a cost decision, stated plainly so
  it is never mistaken for a security or capability judgment: the trust boundary between CCDash and
  ICA is *already crossed* elsewhere in this operator's environment (ICA is the default Claude Code
  offload target per the operator's global model-routing policy), and ICA serves the naming/insight
  workload's model tiers on a **free tier**. That combination — no new trust boundary, no marginal
  cost — makes a systematic sweep (the naming job evaluates every eligible session on a schedule,
  not once per user click) affordable in a way a metered Anthropic-direct default would not be.
  Pointing the same adapter at Anthropic direct remains a one-line config change
  (`CCDASH_LLM_ANTHROPIC_BASE_URL=https://api.anthropic.com`, the adapter's own default) for a
  deployment that cannot or should not route through ICA.
- The Gemini lane (`backend/adapters/llm/gemini.py`, `GeminiTextCompletionAdapter`) is **retained**
  for the surfaces that already ship on it (Lane B / `HostedGeminiNamingBackend`) but is **not
  extended** to new surfaces or new call sites. It is a maintained legacy lane, not a second
  first-class hosted target.
- The OpenAI-compat path is **foreclosed** for the hosted lane. See Alternatives Considered for why
  the Ollama-compat argument does not win.

### Empirically settled consequences (probed 2026-08-07 against the live ICA gateway)

These are measured facts, not design choices, but they are consequences of choosing the Anthropic
wire format and are recorded here so they are never re-probed or "improved":

- Endpoint is always `POST {base_url}/v1/messages`. `base_url` alone distinguishes ICA from
  Anthropic direct — no other request shape differs.
- `anthropic-version: 2023-06-01` is sent **unconditionally** on every request. It is required by
  Anthropic direct (omitting it errors) and merely optional/ignored by ICA. Sending it always means
  the same request body works unmodified against either endpoint.
- The credential travels as the `x-api-key` request header on both endpoints. ICA additionally
  accepts `Authorization: Bearer`, but Anthropic direct only accepts `x-api-key` — so `x-api-key` is
  the one header shape that is valid everywhere, and is the only one this adapter uses.
- **Model ids must be bare** (e.g. `claude-haiku-4-5`, `claude-sonnet-5`). A `[1m]`-suffixed id
  (e.g. `claude-haiku-4-5[1m]`) returns `403 team_model_access_denied` on ICA. The `[1m]` suffix is a
  **Claude-Code-layer delegation convention** (`ica-claude.sh` / `ica-settings.json`), not something
  either raw HTTP endpoint accepts — a caller who copy-pastes a Claude-Code-facing model string into
  this adapter's config surface is making a category error, not a typo, and the adapter rejects it
  at construction time (`ValueError`) rather than silently stripping the suffix.
- ICA is Bedrock-backed: response ids look like `msg_bdrk_...` rather than Anthropic's native `msg_...`
  shape. The adapter parses the Messages envelope generically (by field, never by id-prefix
  assertion) so this difference is invisible to callers.
- **ICA silently returns `200 OK` on unknown top-level request fields where Anthropic direct returns
  `400`.** This means a green call against ICA proves reachability, not request correctness — ICA is
  not a validation lane for this wire format. The adapter therefore sends only the fields the
  Messages API actually documents (`model`, `max_tokens`, `messages`); a typo or speculative field
  added later would pass silently on ICA and only surface when (or if) the same deployment is pointed
  at Anthropic direct.

### Implementation

- Adapter: `backend/adapters/llm/anthropic.py` (`AnthropicTextCompletionAdapter`, `EGRESS = True`).
- Config surface (`backend/config.py`): `CCDASH_LLM_ANTHROPIC_BASE_URL` (default
  `https://api.anthropic.com`), `CCDASH_LLM_ANTHROPIC_API_KEY` (default empty — unset means the
  lane is unreachable, never a crash), `CCDASH_LLM_ANTHROPIC_MODEL` (see below),
  `CCDASH_LLM_SESSION_NAMING_LANE` (per-surface lane selector; adds `"anthropic"` to
  `CCDASH_SESSION_NAMING_BACKEND`'s existing `local`/`hosted` vocabulary without renaming or
  retiring that variable).
- **`CCDASH_LLM_ANTHROPIC_MODEL` deliberately has no default.** Every other CCDash provider var with
  a hosted destination (`CCDASH_OLLAMA_MODEL`, `CCDASH_GEMINI_API_KEY`) either defaults to a
  loopback-safe value or defaults to unset-meaning-disabled; a *model* default on a paid hosted lane
  would be a silent cost decision baked into the codebase rather than an explicit operator choice.
  Absent means the lane is unreachable at derive time — identical in kind to an absent API key —
  never a fallback to some other model.
- Egress is gated by a two-level consent model, not by the lane selector alone: a global
  `CCDASH_LLM_EGRESS_CONSENT` (default `False`, fail-closed — no `egress=True` adapter may be
  constructed unless this is explicitly `true`) **and** a per-project `projects.llm_egress_consent`
  column (v52 migration, `NOT NULL DEFAULT FALSE`/`0`, both SQLite and Postgres DDL), evaluated by
  `SessionNamingSweepJob` per project, per sweep tick. Separating the two means a deployment can have
  the Anthropic lane fully configured (URL, key, model) with egress still cold, and a shared
  multi-project deployment's egress decision is per-project, not deployment-wide — one operator's
  consent never speaks for another project's sessions.

## Decision Drivers

1. **One adapter, two trust postures, zero branching.** The Anthropic wire format is identical
   between ICA and Anthropic direct at the request/response level; only `base_url` differs. This is
   the single strongest argument in the SPIKE — it is a genuine two-for-one, not a marginal
   convenience.
2. **The trust boundary is already crossed.** ICA is the default hosted delegation target for this
   operator's Claude Code environment generally (see the global model-routing policy). Routing
   CCDash's own hosted-egress lane through the same gateway adds no *new* boundary to reason about —
   the remaining question for CCDash's own gates is blast radius (systematic sweep vs. one click),
   not trust, and that is handled by the consent model above, not by this ADR.
3. **The free tier makes systematic egress affordable.** The naming sweep is a scheduled job that
   evaluates every eligible session, not a per-click action — its call volume (~100/day steady,
   documented in the SPIKE's cost model) would carry a real metered cost against Anthropic direct
   and none against ICA's free tier for the model sizes this workload needs.
4. **Gemini stays alive for what already ships, and nothing new.** Retiring Gemini outright would
   force an unforced migration of `HostedGeminiNamingBackend`'s existing, working call site for no
   behavioral gain. Extending it to new surfaces would mean maintaining two hosted wire formats
   going forward for no gain the Anthropic lane doesn't already provide. Neither extreme is taken.

## Alternatives Considered

### OpenAI-compatible wire format (rejected)

**The real counter-argument, recorded so it is not re-litigated:** Ollama, CCDash's local/loopback
lane, already serves an OpenAI-compatible chat-completions surface. Had the hosted lane also adopted
OpenAI-compat, one adapter shape could plausibly have served both local and hosted egress, reducing
the total number of wire-format-specific client shapes in the codebase from two (Ollama's native
shape + a hosted shape) to effectively one vocabulary.

**Why ICA compatibility outweighs Ollama compatibility:** the unification OpenAI-compat offers is
between *local* and *hosted* — two lanes that are already required to diverge in every property that
matters for this feature (egress gating, consent, redaction-provenance enforcement, blast-radius
controls). Unifying their wire format would not remove any of that required divergence; it would
only mean the local and hosted adapters *happen* to parse similarly-shaped JSON, which is a cosmetic
saving of roughly one adapter's worth of code. Adopting the Anthropic format instead unifies the two
lanes that are **not** required to diverge — ICA and Anthropic direct are the *same* lane at two base
URLs, differing only in trust posture and price, and every gate this feature adds (consent, per-
project column, provenance) applies identically to both. The unification that matters is the one
that removes actual branching logic (provider selection inside one adapter); the unification that
does not matter is the one that only removes incidental code duplication between two lanes that
were always going to have different policies wrapped around them. Rejected.

### Anthropic direct as the default endpoint, ICA as opt-in (rejected)

Symmetric with the treatment above but inverted: making Anthropic direct the default would be the
conventional "customer of record" choice, and would avoid stating a preference for an internal
gateway in a project's own ADR. Rejected because it inverts the actual cost/trust reality this
milestone is built around — CCDash would default to *paying* for a lane whose free equivalent is
already trusted elsewhere in the same operator's environment, for no corresponding gain in
capability, correctness, or safety. The default must match the decision actually being made, not a
generic-sounding one.

### Keep the port SDK-agnostic and support all three wire formats behind flags (rejected)

Considered and rejected under ADR-016's own reasoning, restated here because it bears directly on
this decision: supporting Anthropic-format, OpenAI-compat, and a raw-Gemini shape simultaneously
behind runtime flags would mean every future adapter change is validated against three wire
contracts instead of one, for a workload (session naming + one insight blurb) that has never needed
more than one hosted lane active at a time. Rejected as scope the workload does not justify.

## Consequences

### Positive

- A single ~150-line adapter (`anthropic.py`) reaches both a free internal gateway and the paid
  provider of record, with the swap being a one-line base-URL change — no code path forks on
  provider identity.
- The default configuration (ICA) costs nothing at the naming sweep's measured call volume
  (915 input + 8–10 output tokens per call, measured 2026-08-09), making the zero-egress-by-default
  posture's *opt-in* path cheap enough that turning it on is a genuinely low-stakes decision for an
  operator, not one that requires a budget conversation.
- Anthropic direct remains a first-class, equally-supported destination for any deployment that
  cannot route through ICA (e.g. a deployment outside this operator's environment) — nothing about
  this decision is ICA-specific at the code level, only at the *default* level.

### Negative

- CCDash now carries two hosted wire formats in its adapter set (Anthropic-format + Gemini's native
  shape) rather than one, because Gemini is retained rather than migrated. This is an accepted,
  bounded cost — Gemini's surface area is frozen (not extended), so the ongoing maintenance burden
  does not grow with new features.
- Because ICA silently accepts unknown top-level request fields (200 OK) where Anthropic direct
  returns 400 for the same request, a bug in this adapter that adds an undocumented field would ship
  invisibly against the default (ICA) configuration and only surface the first time the same
  deployment is pointed at Anthropic direct. The adapter's discipline of sending only documented
  fields is the mitigation; it is a discipline that must be maintained by every future edit to this
  file, not a property enforced by the wire format itself.
- A caller who reaches for a Claude-Code-facing model string (with a `[1m]` suffix) when configuring
  `CCDASH_LLM_ANTHROPIC_MODEL` gets a hard construction-time failure rather than a working call. This
  is deliberate (see Decision) but means operator-facing documentation for this config surface must
  say so explicitly, or the failure mode will look like a bug report rather than a config error.

### Risks

| Risk | Mitigation |
|---|---|
| ICA's lenient field validation masks a request-shape bug until an Anthropic-direct deployment surfaces it | Adapter sends only the three documented top-level fields (`model`, `max_tokens`, `messages`); any new field requires a deliberate code review, not just "it worked on ICA" |
| A future contributor "fixes" the default back to Anthropic direct, assuming that is the conventional choice | This ADR states the cost/trust reasoning plainly; re-derive from here, not from convention |
| A future contributor extends the Gemini lane to a new surface instead of using the Anthropic lane, because Gemini's call site already exists | This ADR records the Anthropic lane as canonical for new hosted work; Gemini is legacy-only by this decision |
| An operator points `CCDASH_LLM_ANTHROPIC_BASE_URL` at ICA without also setting a bare (non-`[1m]`) model id | Adapter raises `ValueError` at construction time naming the offending value, rather than 403-ing silently at call time |

## Related

- ADR-016 — Provider-agnostic `TextCompletionPort` seam over `httpx`; no provider SDK (proposed
  elsewhere; already shipped as the P1 seam this ADR's adapter plugs into).
- ADR-018 — Redaction provenance carried by type, not by convention (governs what content this
  adapter is permitted to send, independent of which endpoint receives it).
- SPIKE: `docs/project_plans/spikes/hosted-llm-provider-strategy.md` — §Provider Seam Design
  (`Answer to RQ-3`), §Config Surface, §Empirical Addendum (2026-08-07 ICA probe), §ADR Candidates.
- Implementation: `backend/adapters/llm/anthropic.py`, `backend/config.py`
  (`CCDASH_LLM_ANTHROPIC_*`, `CCDASH_LLM_SESSION_NAMING_LANE`, `CCDASH_LLM_EGRESS_CONSENT`).
- Tests: `backend/tests/test_anthropic_adapter.py` (wire-shape, provenance-enforcement,
  fail-open-degradation, suffixed-model-id-rejection coverage).
