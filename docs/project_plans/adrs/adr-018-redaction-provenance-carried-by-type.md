---
title: "ADR-018: Redaction Provenance Is Carried by Type, Not by Convention"
type: "adr"
status: "accepted"
created: "2026-08-10"
parent_prd: "docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md"
depends_on_spike: "docs/project_plans/spikes/hosted-llm-provider-strategy.md"
supersedes: null
related_adrs: ["adr-016-provider-agnostic-llm-client-seam-over-httpx.md", "adr-017-anthropic-wire-format-canonical-hosted-lane.md"]
tags: ["adr", "llm", "redaction", "egress", "security", "type-safety"]
---

# ADR-018: Redaction Provenance Is Carried by Type, Not by Convention

## Status

Accepted (SPIKE-resolved 2026-08-07, ratified as part of M3 of
`hosted-llm-anthropic-ica-lane-v1`, 2026-08-10).

## Context

Before this feature, CCDash's redaction guarantee for hosted-egress content lived entirely in a
**code comment**, not a type. `session_naming_hosted_backend.py:195-197` states that
`bundle.transcript.items` "has already been through `redact_entries` inside `get_session_detail`"
— and that comment was, verified by the SPIKE, the *entire enforcement mechanism*. Two different
call sites send materially different content under materially different obligations through what
was becoming a single, increasingly generic call surface:

- **Derived naming** (both the local/Ollama and hosted/Gemini lanes) sends transcript-derived text.
  It must be redacted, and today is — via `get_session_detail(..., include={INCLUDE_TRANSCRIPT})`.
- **Dashboard insight** (`ai_insight.py`) sends aggregates — task titles, statuses, costs — never
  transcript content, and has no redaction gate, which is defensible for that content class but
  leaves the surface un-gated.

The SPIKE's audit of `agent_queries/session_detail.py` also found that the module's own docstring
claim — that `SessionTranscriptService.list_session_logs` is "the **only** transcript reader" — is
already violated *inside the function that makes the claim*: `session_detail.py` calls
`list_session_logs` a second time (for `aosCorrelation` derivation) without routing that second read
through `redact_entries` at all. That second read is not currently exposed to any hosted lane, but
it proves the "single choke point" is a convention, not a mechanically enforced invariant — nothing
at the type level distinguishes a redacted `list[dict]` from an unredacted one, so a future call site
could route the wrong one to a provider adapter and nothing would stop it, catch it in review, or
fail a test.

Compounding this: `get_session_detail`'s redaction step is **deliberately fail-open**.
`session_detail.py:456-462` (`redact_entries` exception path) logs a warning and proceeds
"without redaction for this page," a trade-off documented at `session_detail.py:374-375`/`386` as
*"delivery safety > potential partial secret exposure in edge cases."* That trade-off is correct for
`get_session_detail`'s actual job — it is a **read** surface serving the session-detail UI/API, and
a UI that silently drops a page of transcript because redaction hiccuped is a worse outcome for that
consumer than an edge-case leak of already-narrow-scope content. It is the wrong trade-off,
unmodified, for a **provider adapter** deciding whether to send content off-box: a hosted-egress call
site inheriting that same "proceed anyway" posture would mean a redaction failure silently degrades
into an *unredacted network send* rather than a UI degradation — a fundamentally different severity
class hiding behind an identical-looking exception handler.

## Decision

**The `TextCompletionPort` accepts only a `PromptEnvelope` carrying a `PromptProvenance`, and a
`PromptEnvelope` is constructible solely through two named factory functions in
`backend/application/ports/llm.py`:**

```python
class PromptProvenance(StrEnum):
    AGGREGATE = "aggregate"                      # ai_insight's use case — no transcript content
    TRANSCRIPT_REDACTED = "transcript_redacted"   # derived-naming's use case — post-redact_entries

@dataclass(frozen=True, slots=True)
class PromptEnvelope:
    text: str
    provenance: PromptProvenance
    redaction_events: int = 0   # COUNT only — never payload, per existing logging policy

def envelope_from_aggregate(text: str) -> PromptEnvelope: ...
def envelope_from_redacted_transcript(text: str, redaction_events: int = 0) -> PromptEnvelope: ...
```

No third constructor path exists. A caller cannot build a `PromptEnvelope` that claims
`TRANSCRIPT_REDACTED` provenance without going through `envelope_from_redacted_transcript`, and
cannot claim `AGGREGATE` provenance for transcript-derived text without a caller actively lying to
the factory about what it is sending — the type does not prevent that lie, but it makes the lie the
*only* way past the gate, rather than the default outcome of a generic `str`-typed port.

### The crux: `envelope_from_redacted_transcript` is fail-closed, and that is a deliberate divergence

`envelope_from_redacted_transcript` raises `RuntimeError` if
`CCDASH_REDACTION_PATTERNS_ENABLED` is off, refusing to construct the envelope at all. This
**intentionally contradicts** `get_session_detail`'s fail-open posture described above — the same
underlying fact ("redaction is not currently active/successful") produces the *opposite* behavior
depending on which side of the egress boundary is asking:

- `get_session_detail` (a **read** surface): fail-open. Proceed without redaction; a stale/degraded
  page is better than no page.
- `envelope_from_redacted_transcript` (an **egress** boundary): fail-closed. Refuse to build the
  envelope; no envelope means no call, means nothing leaves the process.

This is not an oversight to reconcile — it is the entire point of this ADR. **A future reader who
finds the fail-open comment at `session_detail.py:374-375`/`:386` next to this fail-closed factory,
with no ADR to consult, has every reason to conclude one of them is a bug and "fix" it to match the
other.** Either direction of that fix is wrong: making the read path fail-closed would degrade the
session-detail UI on every transient redaction hiccup for no security gain (nothing there reaches a
network egress); making the egress factory fail-open would mean a redaction outage silently
converts into unredacted transcript content leaving the process — the exact failure mode this whole
feature exists to prevent. The two postures differ because **what happens next differs**: one path's
failure mode is "the user sees less," the other's is "a third party receives something it should
never receive." Same signal, opposite consumer, opposite correct response — recorded here so it is
never "corrected" into consistency.

### The remaining structural gate: `enforce_egress_provenance`

`EGRESS_ALLOWED_PROVENANCE` (a `frozenset` currently containing both `PromptProvenance` members) and
`enforce_egress_provenance(envelope)` (`backend/application/ports/llm.py`) are the consequence this
milestone adds on top of the envelope/factory design: every adapter marked `EGRESS = True`
(`AnthropicTextCompletionAdapter`, `GeminiTextCompletionAdapter`) calls
`enforce_egress_provenance(envelope)` as the **very first statement** inside `complete()`, before any
URL, payload, or connection is built — a wrong-provenance envelope is rejected (`ValueError`) before
any network work happens, not merely before the send completes. `OllamaTextCompletionAdapter`
(`EGRESS = False`, loopback) never calls it — a call that never leaves the box has nothing off-box to
protect, and gating it would only slow down the zero-egress-by-default lane for no safety gain.

`EGRESS_ALLOWED_PROVENANCE` exists as its own named constant, distinct from "every value in
`PromptProvenance`," specifically so that **adding a future provenance value to the enum does not
automatically make it egress-eligible** — a hypothetical third provenance value (e.g. some future
"raw, unconfirmed" state) would have to be added to `EGRESS_ALLOWED_PROVENANCE` explicitly, as a
second, deliberate act, before any `EGRESS = True` adapter could ever accept it.

### Architecture guardrail

An architecture-level test is required to forbid provider modules under `backend/adapters/llm/` from
importing raw transcript readers directly — `backend/parsers/sessions.py`'s `parse_session_file` /
`scan_sessions`, and `SessionTranscriptService.list_session_logs` itself
(`application/services/sessions.py`) — mirroring the AST-import-walk guardrail pattern this codebase
already uses elsewhere (e.g. `backend/tests/test_aar_review_no_llm_imports.py`,
`test_routing_rollup_no_llm_imports.py`). The intent is structural, not merely conventional: a
provider adapter has no legitimate reason to read a transcript itself — every transcript-derived
envelope it ever receives must already have passed through `envelope_from_redacted_transcript`,
which is upstream of the adapter by construction. A provider module importing a raw reader directly
would be the one code shape that could bypass the envelope/factory gate entirely, so it is the one
import shape this guardrail must always catch, regardless of which adapter or how it got there.

## Decision Drivers

1. **A code comment is not an enforcement mechanism.** The SPIKE found the "redaction happened"
   guarantee was, verified by grep, exactly one comment wide. A type the compiler/type-checker can
   see, and a runtime factory that can raise, close that gap structurally rather than by convention.
2. **The "single choke point" claim was already false.** `session_detail.py`'s own docstring
   asserted a guarantee its own second internal call site violated. Fixing the docstring would not
   have fixed the underlying gap; only a type that distinguishes redacted from unredacted content —
   independent of which function produced it — closes it.
3. **Read and egress are different severity classes and must be allowed to diverge.** Conflating
   "fail gracefully for a UI" with "fail gracefully for a network send" was the latent risk this
   feature had to design against explicitly, not inherit implicitly from an existing helper.
4. **The gate must be impossible to bypass by omission, not just by malice.** A future contributor
   adding a new hosted surface should not need to remember to call a redaction check — the port's own
   input type should make sending unredacted or wrongly-labeled content a compile-time-visible
   mistake (wrong factory call) rather than a runtime-only, easy-to-miss one.

## Alternatives Considered

### Keep the port `str`-typed; document the redaction contract in the port's docstring (rejected)

This is, functionally, the status quo the SPIKE audited and found already broken by
`session_detail.py`'s own second call site. A docstring is exactly as enforceable as the comment
this ADR replaces — a future call site can construct a plain string from any source and hand it to
`complete()` with nothing checking where the string came from. Rejected for the same reason the
existing comment was found insufficient.

### A single provenance-agnostic envelope with a boolean `is_redacted` flag (rejected)

Simpler on its face — one bool instead of an enum — but a bare bool conflates "this is aggregate
content that never needed redaction" with "this is transcript content that was successfully
redacted," which are different claims with different failure modes (aggregate content has no
redaction step to fail; transcript content's redaction step can fail and that failure must be
distinguishable). The `AGGREGATE` / `TRANSCRIPT_REDACTED` distinction is not decorative — it is what
lets `envelope_from_aggregate` skip the redaction-enabled check entirely (aggregate content was never
subject to it) while `envelope_from_redacted_transcript` enforces it unconditionally. A single bool
would need a third state ("not applicable") to express the same thing, which is an enum in disguise.
Rejected as a false simplification.

### Make `envelope_from_redacted_transcript` fail-open, matching `get_session_detail` (rejected)

Considered explicitly, precisely because it is the "obvious" consistency fix a future reader might
reach for. Rejected because it converts a redaction outage into a silent unredacted network send —
the single worst outcome this whole feature is designed to prevent, traded away for API-shape
consistency with a function whose fail-open posture exists for an unrelated reason (UI degradation
tolerance, not egress safety). See the Decision section's "crux" discussion — this is the alternative
this ADR exists specifically to foreclose.

### Enforce provenance only at the call site (inside each backend), not inside the adapter (rejected)

Would mean `AnthropicTextCompletionAdapter` and `GeminiTextCompletionAdapter` each trust whatever
envelope they are handed, relying on `HostedGeminiNamingBackend`/`AnthropicNamingBackend` (or any
future caller) to have checked provenance correctly before calling `complete()`. Rejected because it
makes the guarantee caller-dependent again — exactly the property this ADR exists to remove. Putting
`enforce_egress_provenance` inside the adapter, as the first statement of `complete()`, means the
guarantee holds regardless of which caller reaches the adapter, including a caller not yet written.

## Consequences

### Positive

- The distinction the module docstring merely *asserted* is now a type the type-checker sees at
  every call site that constructs or consumes a `PromptEnvelope` — a reviewer does not need to trace
  provenance manually to know which content class a given `complete()` call is sending.
- The fail-open/fail-closed divergence between `get_session_detail` and
  `envelope_from_redacted_transcript` is now a documented, deliberate design decision instead of an
  inconsistency waiting to be "fixed" by someone who has not read this ADR.
- Adding a third hosted surface in the future requires that surface's author to call one of exactly
  two named factories — there is no third, undocumented way to build a `PromptEnvelope` that a future
  contributor could reach for under time pressure.
- `EGRESS_ALLOWED_PROVENANCE` being a separate constant from `PromptProvenance` itself means a future
  provenance value cannot become egress-eligible by accident — someone has to add it to both places,
  which is a second deliberate act a reviewer can catch.

### Negative

- Two names (`envelope_from_aggregate`, `envelope_from_redacted_transcript`) must now be kept in sync
  with any future change to what "redacted" or "aggregate" means at the read layer — the envelope
  factories are a second place (alongside `get_session_detail`/`redact_entries`) that must be updated
  together if the underlying redaction contract changes shape.
- The fail-closed behavior of `envelope_from_redacted_transcript` means that disabling
  `CCDASH_REDACTION_PATTERNS_ENABLED` — which today only degrades the session-detail *read* UI —
  now additionally and silently disables every hosted-egress naming/insight call that depends on
  transcript content, with no separate flag to distinguish "redaction is off" from "hosted egress is
  therefore also off." This is intentional (see Decision) but is an operational surface that must be
  documented for operators, not just for future code readers.
- The architecture guardrail test (forbidding `backend/adapters/llm/*` from importing raw transcript
  readers) adds one more AST-import-walk test to maintain, in the pattern of
  `test_aar_review_no_llm_imports.py` / `test_routing_rollup_no_llm_imports.py` — a maintenance cost
  this codebase has already accepted for structurally similar guarantees elsewhere.

### Risks

| Risk | Mitigation |
|---|---|
| A future contributor "fixes" the fail-open/fail-closed divergence to make the two functions consistent | This ADR's "crux" section states the reasoning explicitly and is the canonical answer; cite it, do not re-derive |
| A future hosted surface bypasses the factories by constructing `PromptEnvelope(...)` directly (the dataclass itself is not private) | The architecture guardrail test's intent extends to reviewing any direct `PromptEnvelope(` construction outside `backend/application/ports/llm.py` during code review; the dataclass is frozen but not otherwise access-controlled by the language |
| A provider adapter imports a raw transcript reader for an unrelated, seemingly-innocuous reason (e.g. debugging, logging) | Architecture guardrail test (AST import walk over `backend/adapters/llm/`) catches this at test time, not review time |
| Disabling redaction silently disables hosted egress with no distinct operator-facing signal | Existing egress observability logging (lane, model, project id, calls made — never content) at INFO per sweep tick surfaces a lane going quiet; operator documentation for `CCDASH_REDACTION_PATTERNS_ENABLED` must state this coupling |

## Related

- ADR-016 — Provider-agnostic `TextCompletionPort` seam over `httpx`; no provider SDK (proposed
  elsewhere; establishes the port this envelope type is the sole accepted input to).
- ADR-017 — Anthropic wire format is the canonical hosted lane; ICA is the default endpoint
  (governs *where* a correctly-provenanced envelope may be sent; this ADR governs *what* may be
  built into one in the first place).
- SPIKE: `docs/project_plans/spikes/hosted-llm-provider-strategy.md` — §Redaction Enforcement
  ("The problem is not 'is redaction called' — it is 'the port erases the distinction'", "Verified
  gaps in the current 'single choke point' claim", "Recommended mechanism: primary + cheap
  complement").
- Implementation: `backend/application/ports/llm.py` (`PromptProvenance`, `PromptEnvelope`,
  `envelope_from_aggregate`, `envelope_from_redacted_transcript`, `EGRESS_ALLOWED_PROVENANCE`,
  `enforce_egress_provenance`); `backend/adapters/llm/anthropic.py`,
  `backend/adapters/llm/gemini.py` (both `EGRESS = True`); `backend/adapters/llm/ollama.py`
  (`EGRESS = False`).
- The fail-open read posture this ADR deliberately diverges from:
  `backend/application/services/agent_queries/session_detail.py` (documented at
  `:374-375`/`:386`, implemented at the `redact_entries` exception path around `:456-462`).
- Tests: `backend/tests/test_anthropic_adapter.py` (`ProvenanceEnforcementTests`),
  `backend/tests/test_aar_review_no_llm_imports.py` / `test_routing_rollup_no_llm_imports.py`
  (the AST-import-walk guardrail pattern the new architecture test mirrors).
