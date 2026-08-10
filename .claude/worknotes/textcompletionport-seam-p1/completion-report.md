## Completion Report

### Summary

Introduced a `TextCompletionPort` protocol + `PromptEnvelope`/`PromptProvenance` value
types in `backend/application/ports/llm.py`, and two new httpx-only adapter classes
(`OllamaTextCompletionAdapter`, `GeminiTextCompletionAdapter`) under a new
`backend/adapters/llm/` package. Moved the three existing raw httpx call sites
(`LocalOllamaNamingBackend._call_ollama`, `HostedGeminiNamingBackend._call_gemini`,
`ai_insight.generate_dashboard_insight`'s inline block) behind the new port, deleting the
now-dead `_call_ollama`/`_call_gemini` methods. All 138 tests across the five named test
files plus adjacent coverage pass unmodified.

### Files Changed

- `backend/application/ports/llm.py` — new. `TextCompletionPort` Protocol,
  `PromptProvenance` StrEnum, frozen `PromptEnvelope` dataclass, and the two factory
  functions (`envelope_from_aggregate`, `envelope_from_redacted_transcript`). The redaction
  import inside `envelope_from_redacted_transcript` is a deferred (function-local) import,
  not module-level, to avoid a module-load-time cycle: `agent_queries.__init__` imports
  `dashboard.py` → `backend.application.ports` (for `CorePorts`), and
  `backend.application.ports.__init__` now imports `llm.py`, which would otherwise need
  `agent_queries.redaction` at import time — a real cycle risk avoided the same way
  `session_naming_local_backend.resolve_naming_backend` already documents for its own lazy
  import of the hosted backend.
- `backend/application/ports/__init__.py` — registered the five new `llm` names in the
  package's imports/`__all__`.
- `backend/adapters/llm/__init__.py`, `ollama.py`, `gemini.py` — new package. Adapters
  extracted verbatim from the pre-existing `_call_ollama`/`_call_gemini` HTTP bodies (same
  URLs, same payload shapes, same raise-on-error semantics).
- `backend/services/session_naming_local_backend.py` — constructs an
  `OllamaTextCompletionAdapter` in `__init__`; `derive_name` builds the instruction string
  exactly as before, wraps it in a `PromptEnvelope` (constructed directly, not via the
  fail-closed factory — see Deviations), and calls `self._adapter.complete(envelope)`
  instead of `self._call_ollama(prompt_text)`. Deleted `_call_ollama`. Kept `import httpx`
  (now otherwise unused in this module) so
  `patch("backend.services.session_naming_local_backend.httpx.AsyncClient", ...)` in the
  unmodified test file continues to resolve and take effect — `httpx` is a single shared
  module object, so patching the `AsyncClient` attribute through this module's name affects
  the adapter module's own `httpx.AsyncClient` call identically.
- `backend/services/session_naming_hosted_backend.py` — same pattern with
  `GeminiTextCompletionAdapter`; `derive_name` wraps the instruction string via
  `envelope_from_redacted_transcript` (the redaction-gate re-check above it already
  short-circuits before this point when the gate is off, so the factory's own fail-closed
  check is pure defense-in-depth here, never a newly-reachable path). Deleted `_call_gemini`.
- `backend/services/ai_insight.py` — replaced the inline httpx POST block with a
  `GeminiTextCompletionAdapter` constructed with `envelope_from_aggregate(prompt)`. Kept
  `import httpx` for the `except httpx.HTTPStatusError` type reference and for the test
  patch target, same shared-module-object reasoning as above.

### Acceptance Criteria Status

- [x] `backend/tests/test_session_naming_hosted_backend.py` passes unmodified
- [x] `backend/tests/test_session_naming_local_backend.py` passes unmodified
- [x] `backend/tests/test_ai_insight_router.py` passes unmodified
- [x] `backend/tests/test_session_naming_read_path_no_model_client.py` passes unmodified
      (new `backend/adapters/llm/` and `backend/application/ports/llm.py` are unreachable
      from every walked read-path entry module; `backend.adapters.llm` was also confirmed
      not blanket-imported by any package `__init__` on the read path)
- [x] `ai_insight` still returns `{disabled:true}` with no key, and an `error` string on
      failure, byte-identically (verified by the unmodified router tests)
- [x] Redaction seam preserved: grep-verified `get_session_detail(..., include={INCLUDE_TRANSCRIPT})`
      remains the sole transcript source feeding the prompt in both naming backends; no raw
      JSONL/file read exists anywhere in the new adapter/port modules

### Validation Run

| Command | Result | Notes |
|---|---|---|
| `pytest backend/tests/test_session_naming_hosted_backend.py -v` | Pass | 17 tests |
| `pytest backend/tests/test_session_naming_local_backend.py -v` | Pass | 33 tests + 1 subtest |
| `pytest backend/tests/test_ai_insight_router.py -v` | Pass | 6 tests |
| `pytest backend/tests/test_session_naming_read_path_no_model_client.py -v` | Pass | 3 tests, 10 subtests |
| `pytest backend/tests/test_session_naming.py backend/tests/test_session_naming_sweep_guards.py backend/tests/test_session_naming_sweep_job.py -v` | Pass | 79 tests |
| **Total** (single combined run, all 7 files) | **Pass** | **138 passed, 11 subtests passed** |
| `python -m py_compile` on all 8 changed/new files | Pass | syntax/import sanity |

Ran as one combined `pytest` invocation (see command above) rather than five separate
invocations for brevity; per-file pass counts are broken out above for traceability.
`pnpm test`/`type-check`/`lint` not applicable — this contract touches Python backend
files only.

### Deviations From Contract

1. **`session_naming_prompt.build_prompt_text` was NOT retyped to return `PromptEnvelope`.**
   The contract's Step 4 asked for this retype, but
   `backend/tests/test_session_naming_local_backend.py` imports `_build_prompt_text`
   directly (re-exported, unchanged name, from `session_naming_local_backend`) and asserts
   on it as a plain string (`self.assertEqual(_build_prompt_text([]), "")`,
   `self.assertIn(..., text)`). Retyping the underlying function would have broken that
   unmodified test file, which the contract itself forbids editing ("if a test fails, the
   refactor is wrong, not the test"). Instead, `build_prompt_text` keeps its original
   `str` signature everywhere, and each call site builds the full instruction string
   exactly as before, then wraps *that* string in a `PromptEnvelope` immediately before
   calling the adapter. This preserves the typed-seam intent (the adapter's `complete()`
   always receives a `PromptEnvelope`, never a bare string) without touching the
   str-returning function the tests exercise directly.
2. **The local (Ollama) lane's `PromptEnvelope` is constructed directly, not via
   `envelope_from_redacted_transcript`'s fail-closed factory.** That factory raises when
   `CCDASH_REDACTION_PATTERNS_ENABLED` is off — appropriate defense-in-depth for the hosted
   (Gemini) lane, which already gates on that same flag before ever reaching this point
   (so the factory's check there is provably never a *new* failure path). The local lane
   never checked that flag before this refactor (it is loopback-only, zero off-box egress
   by construction — see the module's own docstring), so routing it through the same
   fail-closed factory would introduce a new, untested failure mode (an unhandled
   `RuntimeError` inside `derive_name`, caught only by the sweep job's outer fail-open
   wrapper) purely as an edge-case behavior change with zero test coverage either way.
   Chose to preserve exact pre-existing behavior for the local lane instead.

Both deviations are in service of the contract's own top-line mandate ("zero observable
behaviour change" + "if a test fails, the refactor is wrong") and are flagged here rather
than silently expanding scope, per the contract's own escalation guidance.

### Risks and Limitations

- **`redaction_events` count is hardcoded to 0** at both naming-backend call sites, per the
  contract's own Risk Areas guidance (no count is currently threaded through
  `get_session_detail`'s returned bundle; inventing one was explicitly out of scope for
  this pass).
- The local-lane deviation above (#2) means `PromptProvenance.TRANSCRIPT_REDACTED` on that
  lane's envelope is asserted by construction, not enforced by the fail-closed factory — a
  future P2/P3 change that starts relying on the factory's guarantee for *all*
  `TRANSCRIPT_REDACTED` envelopes should audit this call site specifically.
- No new tests were added, per the contract's own instruction ("no new tests" is implicit
  in "zero behaviour change... unmodified pass is the contract" and the contract lists no
  new-test requirement). All AC coverage is via the five named + three adjacent existing
  test files.

### Follow-Up Recommendations

- Thread a real `redaction_events` count through `get_session_detail`'s bundle (or a
  sibling call) so `envelope_from_redacted_transcript`'s `redaction_events` field carries
  real data instead of a hardcoded 0 — natural P2 work per the contract's own suggestion.
- Consider whether the local (Ollama) lane should also route through
  `envelope_from_redacted_transcript`'s fail-closed check once/if the local lane ever
  starts crossing a real egress boundary (it currently never does) — revisit deviation #2
  above at that point, with test coverage added for the flag-off case on that lane.
- Consider adding a targeted unit test for `envelope_from_redacted_transcript`'s fail-closed
  raise itself (currently exercised only indirectly/never in this pass, since the hosted
  backend's own upstream gate check means the factory's raise path has zero live test
  coverage of its own).

### Memory Candidates Captured

None — no new root-cause findings, framework gotchas, or file-specific invariants were
discovered beyond what is already documented in the contract's own Risk Areas section and
the module docstrings this pass added to. The httpx-shared-module-object patch-target
mechanism (patching `module.httpx.AsyncClient` from any module that itself does
`import httpx` mutates the single global `httpx` module, regardless of which importer's
name was used to reach it) is a useful reusable fact for future httpx-adapter-extraction
work in this codebase, but is already captured inline as code comments at each of the
three call sites rather than as a separate memory item.
