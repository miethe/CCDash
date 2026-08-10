"""automatic-session-naming (M3 / T3-002) — Lane A local (Ollama) naming backend.

Covers this task's required assertions:

  1. Zero-egress-by-default: ``resolve_naming_backend`` resolves to the local
     backend under the DEFAULT config, and the hosted path is unreachable
     without the explicit ``CCDASH_SESSION_NAMING_BACKEND=hosted`` opt-in
     (and even then, resolves to ``None`` here — Lane B has not landed).
  2. Fail-open: Ollama not installed/running/timing out never raises out of
     ``derive_name`` — it returns ``None`` and leaves ``session_name`` NULL.
  3. Redacted input path: the prompt is built from
     ``session_detail.get_session_detail`` output (which already ran
     ``redact_entries``) — a known secret pattern in a fixture transcript is
     absent from the text handed to the Ollama call.
  4. Output validation: non-conforming model output (empty, oversized) is
     rejected rather than stored raw; conforming-but-long output is bounded.
  5. Persistence: a successful derivation is written with
     ``session_name_source = derived_generative`` (the exact provenance
     token from ``session_name_provenance.py`` — never a new invented
     token), gated so it can never overwrite a stronger existing source.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_naming_local_backend.py -v
"""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import httpx

from backend import config
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.parsers.session_name_provenance import (
    SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
    SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
)
from backend.services.session_naming_local_backend import (
    AnthropicNamingBackend,
    LocalOllamaNamingBackend,
    _build_prompt_text,
    _sanitize_title,
    resolve_naming_backend,
)

PROJ_A = "proj-alpha"
SESSION_A1 = "sess-alpha-001"

_BASE_SESSION = {
    "taskId": "",
    "status": "completed",
    "sessionType": "session",
    "model": "claude-sonnet",
    "platformType": "Claude Code",
    "startedAt": "2026-06-01T00:00:00Z",
    "endedAt": "2026-06-01T00:01:00Z",
}


def _session(session_id: str, **overrides: object) -> dict:
    return {**_BASE_SESSION, "id": session_id, **overrides}


def _make_fake_log(idx: int, content: str = "", speaker: str = "user") -> dict:
    return {
        "id": f"log-{idx}",
        "timestamp": f"2026-06-01T00:0{idx}:00Z",
        "speaker": speaker,
        "type": "message",
        "content": content or f"log content {idx}",
        "agentName": None,
        "linkedSessionId": None,
        "relatedToolCallId": None,
        "metadata": {},
        "toolCall": None,
    }


class FakeCorePortsFactory:
    """Minimal real-DB CorePorts stand-in (mirrors test_session_detail_service.py)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


def _mock_ollama_client(response_text: str | None = None, *, raise_exc: Exception | None = None) -> MagicMock:
    mock_client_instance = AsyncMock()
    if raise_exc is not None:
        mock_client_instance.post = AsyncMock(side_effect=raise_exc)
    else:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": response_text}
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_client_instance


def _install_fake_anthropic_adapter_module(
    *,
    complete_return: str | None = "Fake Anthropic Title",
    complete_side_effect: Exception | None = None,
    construct_side_effect: Exception | None = None,
) -> types.ModuleType:
    """Build a FAKE ``backend.adapters.llm.anthropic`` module for ``sys.modules``.

    The real ``backend/adapters/llm/anthropic.py`` (``AnthropicTextCompletionAdapter``)
    is owned by a concurrent leg of this same milestone and may not exist in
    this worktree yet when this test file runs -- these tests must not
    depend on ITS landing order. This fake is duck-typed to the agreed
    contract (an ``EGRESS = True`` class with an async ``complete(envelope)``
    method) and is installed via ``patch.dict(sys.modules, ...)`` around the
    call under test, never imported for real.
    """
    fake_module = types.ModuleType("backend.adapters.llm.anthropic")

    class _FakeAnthropicTextCompletionAdapter:
        EGRESS = True

        def __init__(self, **kwargs: object) -> None:
            if construct_side_effect is not None:
                raise construct_side_effect
            self.kwargs = kwargs

        async def complete(self, envelope: object) -> str | None:
            if complete_side_effect is not None:
                raise complete_side_effect
            return complete_return

    fake_module.AnthropicTextCompletionAdapter = _FakeAnthropicTextCompletionAdapter  # type: ignore[attr-defined]
    return fake_module


# ── Zero-egress-by-default backend resolution ───────────────────────────────

class BackendResolutionTests(unittest.TestCase):
    """The milestone's headline AC: default config never reaches the hosted lane."""

    def test_default_config_resolves_to_local_backend(self) -> None:
        self.assertEqual(config.CCDASH_SESSION_NAMING_BACKEND, "local")
        backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, LocalOllamaNamingBackend)

    def test_hosted_flag_alone_is_unreachable_without_redaction_gate_check(self) -> None:
        """The opt-in flag by itself is not sufficient to inspect --

        this resolver additionally consults the redaction gate (T3-003) AND
        (hosted-llm-anthropic-ica-lane-v1 M2) the GLOBAL egress consent gate
        -- see ``GlobalEgressConsentGateTests`` below for that gate tested in
        isolation. With the default redaction gate ON (the secure default)
        and egress consent explicitly opted into for this test, opting into
        "hosted" DOES construct a real backend -- see
        ``test_session_naming_hosted_backend.py`` for the full
        all-conditions-required matrix. This test only pins that the
        resolver no longer hardcodes ``None`` for "hosted" now that Lane B
        has landed.
        """
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.object(
            config, "CCDASH_LLM_EGRESS_CONSENT", True
        ):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNotNone(backend)
        self.assertNotIsInstance(backend, LocalOllamaNamingBackend)

    def test_unrecognized_backend_value_fails_toward_local(self) -> None:
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "totally-bogus"):
            backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, LocalOllamaNamingBackend)

    def test_naming_egress_default_config_never_reaches_hosted(self) -> None:
        """Named for the plan's AC->command row (``pytest -k "naming_egress"``):

        default config (``CCDASH_SESSION_NAMING_BACKEND=local``) resolves to
        the local backend -- the hosted lane requires an EXPLICIT opt-in,
        it is never reached just by leaving everything at its default.
        """
        self.assertEqual(config.CCDASH_SESSION_NAMING_BACKEND, "local")
        self.assertIsInstance(resolve_naming_backend(ports=object()), LocalOllamaNamingBackend)

    def test_hosted_construction_emits_a_reachability_warning(self) -> None:
        """Security-review fix (T3-006): reachability must be LOUD in logs --

        an operator watching a worker's log stream must be able to see that
        off-box egress became reachable, not only discoverable by reading
        config. Asserts the WARNING (not merely INFO/DEBUG) is emitted at
        the moment ``resolve_naming_backend`` actually constructs the hosted
        backend.
        """
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.object(
            config, "CCDASH_LLM_EGRESS_CONSENT", True
        ), self.assertLogs(
            "ccdash.services.session_naming_local_backend", level="WARNING"
        ) as captured:
            backend = resolve_naming_backend(ports=object())

        self.assertIsNotNone(backend)
        joined = "\n".join(captured.output)
        self.assertIn("REACHABLE", joined)
        self.assertIn("CCDASH_GEMINI_API_KEY", joined)

    def test_local_backend_defaults_are_loopback_only(self) -> None:
        """The default Ollama base URL is a loopback address, not a

        third-party endpoint — the mechanism behind "zero egress by
        default" for the local lane itself.
        """
        backend = LocalOllamaNamingBackend(ports=object())
        self.assertTrue(
            backend.base_url.startswith("http://localhost")
            or backend.base_url.startswith("http://127.0.0.1")
        )

    def test_local_backend_egress_marker_is_false(self) -> None:
        """The explicit, checkable egress marker (M2) -- local/loopback

        never requires per-project consent, and this is how
        ``SessionNamingSweepJob`` tells the two backends apart.
        """
        backend = LocalOllamaNamingBackend(ports=object())
        self.assertFalse(backend.EGRESS)

        from backend.adapters.llm.ollama import OllamaTextCompletionAdapter

        self.assertFalse(OllamaTextCompletionAdapter.EGRESS)


# ── Global egress consent gate (hosted-llm-anthropic-ica-lane-v1 M2) ────────

class GlobalEgressConsentGateTests(unittest.TestCase):
    """The headline AC for this leg: consent false => no egress adapter

    is EVER constructed, verified by reading the resolver alone (a
    reviewer should not need to trace call sites).
    """

    def test_consent_defaults_false(self) -> None:
        self.assertFalse(config.CCDASH_LLM_EGRESS_CONSENT)

    def test_consent_false_keeps_hosted_unreachable_even_with_redaction_on(self) -> None:
        """Global consent is checked FIRST and independently of the

        redaction gate -- redaction being on (the secure default) does NOT
        make the hosted lane reachable while consent is false.
        """
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", False):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNone(backend)

    def test_consent_true_with_hosted_and_redaction_constructs_backend(self) -> None:
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", True):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNotNone(backend)
        self.assertNotIsInstance(backend, LocalOllamaNamingBackend)

    def test_negative_construction_hosted_backend_never_constructed_when_consent_false(
        self,
    ) -> None:
        """Fails LOUDLY (an ``AssertionError`` from the patched constructor,

        not a quiet assertion mismatch) if ``resolve_naming_backend`` EVER
        reaches the point of importing/constructing
        ``HostedGeminiNamingBackend`` while global consent is false --
        modeled on ``test_aar_review_no_llm_imports.py``'s house pattern of
        asserting a structural "this can never happen" property rather than
        merely a return-value expectation. ``CCDASH_SESSION_NAMING_BACKEND``
        is "hosted" and redaction is explicitly on -- i.e. every OTHER gate
        is wide open -- so only the consent gate stands between this call
        and construction.
        """
        import backend.services.session_naming_hosted_backend as hosted_module

        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError(
                "HostedGeminiNamingBackend was constructed while "
                "CCDASH_LLM_EGRESS_CONSENT was false -- the global egress "
                "consent gate has a silent-fail-open regression."
            )

        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", False), patch.object(
            hosted_module, "HostedGeminiNamingBackend", side_effect=_explode
        ):
            backend = resolve_naming_backend(ports=object())

        self.assertIsNone(backend)

    def test_consent_false_keeps_anthropic_unreachable_even_with_redaction_on(self) -> None:
        """hosted-llm-anthropic-ica-lane-v1 M3-B's required assertion: mirrors

        ``test_consent_false_keeps_hosted_unreachable_even_with_redaction_on``
        above, for the NEW anthropic lane -- the anthropic lane sits behind
        the exact SAME global consent gate as the existing hosted (Gemini)
        lane, no second/weaker gate. Uses ``CCDASH_LLM_SESSION_NAMING_LANE``
        (the new selector) rather than the legacy
        ``CCDASH_SESSION_NAMING_BACKEND`` -- "anthropic" is not one of that
        legacy var's own pre-existing values.
        """
        with patch.object(config, "CCDASH_LLM_SESSION_NAMING_LANE", "anthropic"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", False):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNone(backend)

    def test_negative_construction_anthropic_adapter_never_constructed_when_consent_false(
        self,
    ) -> None:
        """Structural guard, mirrors

        ``test_negative_construction_hosted_backend_never_constructed_when_consent_false``:
        fails LOUDLY (an ``AssertionError`` from a patched constructor, not
        a quiet assertion mismatch) if ``resolve_naming_backend`` EVER
        reaches the point of importing/constructing
        ``AnthropicTextCompletionAdapter`` while global consent is false.
        The lane is "anthropic" and redaction is explicitly on -- every
        OTHER gate is wide open -- so only the consent gate stands between
        this call and construction. Installs a FAKE
        ``backend.adapters.llm.anthropic`` module (see
        ``_install_fake_anthropic_adapter_module``) so this test does not
        depend on the real module (a concurrent leg's file) existing yet --
        if the real module also doesn't exist, the import would raise
        ``ModuleNotFoundError`` rather than reach the constructor at all,
        which is a WEAKER (not wrong, just less informative) proof of the
        same property; the fake makes the "would have exploded" case
        observable either way.
        """

        def _explode(**kwargs: object) -> None:
            raise AssertionError(
                "AnthropicTextCompletionAdapter was constructed while "
                "CCDASH_LLM_EGRESS_CONSENT was false -- the global egress "
                "consent gate has a silent-fail-open regression."
            )

        fake_module = _install_fake_anthropic_adapter_module()
        fake_module.AnthropicTextCompletionAdapter = _explode  # type: ignore[attr-defined]

        with patch.object(config, "CCDASH_LLM_SESSION_NAMING_LANE", "anthropic"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", False), patch.dict(
            sys.modules, {"backend.adapters.llm.anthropic": fake_module}
        ):
            backend = resolve_naming_backend(ports=object())

        self.assertIsNone(backend)


# ── Anthropic/ICA lane resolution (hosted-llm-anthropic-ica-lane-v1 M3-B) ───

class AnthropicLaneResolutionTests(unittest.TestCase):
    """Reachability + degradation of the new anthropic lane, at the resolver.

    Uses a FAKE ``backend.adapters.llm.anthropic`` module throughout (see
    ``_install_fake_anthropic_adapter_module``) so these tests are
    independent of the real adapter file's landing order -- that file is
    owned by a concurrent leg of this same milestone.
    """

    def test_consent_true_with_anthropic_and_redaction_constructs_backend(self) -> None:
        fake_module = _install_fake_anthropic_adapter_module()
        with patch.object(config, "CCDASH_LLM_SESSION_NAMING_LANE", "anthropic"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", True), patch.object(
            config, "CCDASH_LLM_ANTHROPIC_API_KEY", "test-ica-key"
        ), patch.object(config, "CCDASH_LLM_ANTHROPIC_MODEL", "claude-sonnet-5"), patch.dict(
            sys.modules, {"backend.adapters.llm.anthropic": fake_module}
        ):
            backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, AnthropicNamingBackend)
        self.assertNotIsInstance(backend, LocalOllamaNamingBackend)
        self.assertTrue(backend.EGRESS)

    def test_new_lane_var_wins_over_legacy_backend_var(self) -> None:
        """Fallback-helper precedence, proven behaviourally: the PREFERRED

        ``CCDASH_LLM_SESSION_NAMING_LANE`` wins even when the legacy
        ``CCDASH_SESSION_NAMING_BACKEND`` disagrees -- "local" (new) beats
        "hosted" (legacy), observable via which backend TYPE gets
        constructed (Local vs. an egress-shaped backend), not merely by
        reading back a string.
        """
        with patch.object(config, "CCDASH_LLM_SESSION_NAMING_LANE", "local"), patch.object(
            config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", True), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ):
            backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, LocalOllamaNamingBackend)

    def test_legacy_backend_var_still_works_when_new_lane_var_is_unset(self) -> None:
        """The compatibility contract this leg must not break: leaving

        ``CCDASH_LLM_SESSION_NAMING_LANE`` unset (its actual default today)
        and setting only the legacy var must behave EXACTLY as it did
        before this leg landed.
        """
        self.assertEqual(config.CCDASH_LLM_SESSION_NAMING_LANE, "")
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.object(
            config, "CCDASH_LLM_EGRESS_CONSENT", True
        ), patch.dict("os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNotNone(backend)
        self.assertNotIsInstance(backend, LocalOllamaNamingBackend)
        self.assertNotIsInstance(backend, AnthropicNamingBackend)

    def test_adapter_construction_failure_degrades_to_none_not_a_crash(self) -> None:
        """Degradation, not failure (this leg's item 4): a construction-time

        mismatch (e.g. adapter constructor signature drift) must resolve to
        ``None`` -- the same structural no-op as every other unreachable
        path -- never propagate as an uncaught exception out of
        ``resolve_naming_backend``.
        """
        fake_module = _install_fake_anthropic_adapter_module(
            construct_side_effect=TypeError("unexpected keyword argument")
        )
        with patch.object(config, "CCDASH_LLM_SESSION_NAMING_LANE", "anthropic"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", True), patch.dict(
            sys.modules, {"backend.adapters.llm.anthropic": fake_module}
        ):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNone(backend)

    def test_reachable_construction_emits_a_reachability_warning(self) -> None:
        """Mirrors the hosted lane's T3-006 fix: reachability must be LOUD."""
        fake_module = _install_fake_anthropic_adapter_module()
        with patch.object(config, "CCDASH_LLM_SESSION_NAMING_LANE", "anthropic"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ), patch.object(config, "CCDASH_LLM_EGRESS_CONSENT", True), patch.dict(
            sys.modules, {"backend.adapters.llm.anthropic": fake_module}
        ), self.assertLogs(
            "ccdash.services.session_naming_local_backend", level="WARNING"
        ) as captured:
            backend = resolve_naming_backend(ports=object())
        self.assertIsNotNone(backend)
        joined = "\n".join(captured.output)
        self.assertIn("REACHABLE", joined)
        self.assertIn("CCDASH_LLM_ANTHROPIC_API_KEY", joined)


class AnthropicNamingBackendDegradationTests(unittest.IsolatedAsyncioTestCase):
    """Three distinguishable degrade states for the anthropic lane's

    ``derive_name`` (this leg's item 4): "not configured" (absent key /
    absent model) and "provider down" (adapter call fails) -- "no consent"
    is proven at the resolver above and never reaches this class at all.
    """

    async def test_absent_api_key_disables_the_lane(self) -> None:
        fake_adapter = types.SimpleNamespace(
            EGRESS=True, complete=AsyncMock(return_value="Should never be reached")
        )
        backend = AnthropicNamingBackend(
            ports=object(), adapter=fake_adapter, api_key="", model="claude-sonnet-5"
        )
        result = await backend.derive_name({"id": "s1", "project_id": "p1"})
        self.assertIsNone(result)
        fake_adapter.complete.assert_not_awaited()

    async def test_absent_model_disables_the_lane_exactly_like_absent_key(self) -> None:
        """The deliberately-no-default var (config.CCDASH_LLM_ANTHROPIC_MODEL)

        must degrade identically to an absent key -- never treated as "use
        some fallback model."
        """
        fake_adapter = types.SimpleNamespace(
            EGRESS=True, complete=AsyncMock(return_value="Should never be reached")
        )
        backend = AnthropicNamingBackend(
            ports=object(), adapter=fake_adapter, api_key="test-key", model=""
        )
        result = await backend.derive_name({"id": "s1", "project_id": "p1"})
        self.assertIsNone(result)
        fake_adapter.complete.assert_not_awaited()

    async def test_egress_property_delegates_to_the_injected_adapter(self) -> None:
        backend = AnthropicNamingBackend(
            ports=object(),
            adapter=types.SimpleNamespace(EGRESS=True),
            api_key="k",
            model="m",
        )
        self.assertTrue(backend.EGRESS)

    async def test_provider_unreachable_is_a_fail_open_no_op(self) -> None:
        """The THIRD degrade state -- "provider down" -- distinguishable

        from "not configured" above: key and model ARE present, but the
        adapter call itself fails (network error/timeout/non-2xx).
        """
        fake_logs = [_make_fake_log(1, "Please help me fix the flaky test")]
        fake_adapter = types.SimpleNamespace(
            EGRESS=True,
            complete=AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
        )
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            await run_migrations(db)
            ports = FakeCorePortsFactory(db)
            session_repo = SqliteSessionRepository(db)
            await session_repo.upsert(_session(SESSION_A1), PROJ_A)
            await db.commit()

            backend = AnthropicNamingBackend(
                ports=ports, adapter=fake_adapter, api_key="test-key", model="claude-sonnet-5"
            )
            with patch(
                "backend.application.services.agent_queries.session_detail"
                "._transcript_service.list_session_logs",
                new=AsyncMock(return_value=fake_logs),
            ):
                result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

            self.assertIsNone(result)
            row = await session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
            self.assertIsNone(row["session_name"])
        finally:
            await db.close()

    async def test_successful_derivation_persists_with_derived_generative_provenance(
        self,
    ) -> None:
        fake_logs = [_make_fake_log(1, "Please help me refactor the auth module")]
        fake_adapter = types.SimpleNamespace(
            EGRESS=True, complete=AsyncMock(return_value="Refactor the auth module")
        )
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            await run_migrations(db)
            ports = FakeCorePortsFactory(db)
            session_repo = SqliteSessionRepository(db)
            await session_repo.upsert(_session(SESSION_A1), PROJ_A)
            await db.commit()

            backend = AnthropicNamingBackend(
                ports=ports, adapter=fake_adapter, api_key="test-key", model="claude-sonnet-5"
            )
            with patch(
                "backend.application.services.agent_queries.session_detail"
                "._transcript_service.list_session_logs",
                new=AsyncMock(return_value=fake_logs),
            ):
                result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

            self.assertEqual(result, "Refactor the auth module")
            row = await session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
            self.assertEqual(row["session_name"], "Refactor the auth module")
            self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_DERIVED_GENERATIVE)
        finally:
            await db.close()


# ── Config fallback helper (hosted-llm-anthropic-ica-lane-v1 M3, Named Risk #4) ─

class ConfigFallbackHelperTests(unittest.TestCase):
    """``config.resolve_with_legacy_fallback`` -- the ONE helper this leg

    writes and routes every ``CCDASH_LLM_*``-vs-legacy-var pair through
    (the naming lane selector AND the Gemini credential -- see
    ``config.py``'s own ``CCDASH_GEMINI_API_KEY`` line), rather than
    open-coding an ``os.getenv(new) or os.getenv(old)`` chain per var.
    """

    def setUp(self) -> None:
        # Each test uses a throwaway legacy_name so the module-level
        # "warned once" seen-set (shared across the whole process/test
        # run) can never make a later test observe a suppressed warning
        # left over from an earlier one.
        self._legacy_name = f"CCDASH_TEST_LEGACY_{id(self)}"
        config._LEGACY_ENV_FALLBACKS_WARNED.discard(self._legacy_name)

    def tearDown(self) -> None:
        config._LEGACY_ENV_FALLBACKS_WARNED.discard(self._legacy_name)

    def test_new_value_wins_when_present(self) -> None:
        result = config.resolve_with_legacy_fallback(
            "new-value", "legacy-value", "default",
            new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
        )
        self.assertEqual(result, "new-value")

    def test_legacy_value_used_when_new_is_absent(self) -> None:
        result = config.resolve_with_legacy_fallback(
            None, "legacy-value", "default",
            new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
        )
        self.assertEqual(result, "legacy-value")

    def test_legacy_value_used_when_new_is_empty_string(self) -> None:
        result = config.resolve_with_legacy_fallback(
            "", "legacy-value", "default",
            new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
        )
        self.assertEqual(result, "legacy-value")

    def test_default_used_when_both_absent(self) -> None:
        result = config.resolve_with_legacy_fallback(
            None, None, "default",
            new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
        )
        self.assertEqual(result, "default")

    def test_default_used_when_both_are_empty_strings(self) -> None:
        result = config.resolve_with_legacy_fallback(
            "", "", "default",
            new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
        )
        self.assertEqual(result, "default")

    def test_whitespace_only_values_are_treated_as_absent(self) -> None:
        result = config.resolve_with_legacy_fallback(
            "   ", "   ", "default",
            new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
        )
        self.assertEqual(result, "default")

    def test_falling_back_to_legacy_logs_a_deprecation_warning_naming_both_vars(self) -> None:
        with self.assertLogs("ccdash.config", level="WARNING") as captured:
            config.resolve_with_legacy_fallback(
                None, "legacy-value", "default",
                new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
            )
        joined = "\n".join(captured.output)
        self.assertIn(self._legacy_name, joined)
        self.assertIn("CCDASH_TEST_NEW", joined)
        self.assertIn("DEPRECATED", joined)

    def test_deprecation_warning_is_logged_only_once_per_legacy_name(self) -> None:
        with self.assertLogs("ccdash.config", level="WARNING") as captured:
            for _ in range(3):
                config.resolve_with_legacy_fallback(
                    None, "legacy-value", "default",
                    new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
                )
        self.assertEqual(len(captured.output), 1)

    def test_using_the_new_value_never_logs_a_deprecation_warning(self) -> None:
        with self.assertRaises(AssertionError):
            # assertNoLogs is Python 3.10+; this repo's fallback is to
            # assert assertLogs itself finds nothing and raises.
            with self.assertLogs("ccdash.config", level="WARNING"):
                config.resolve_with_legacy_fallback(
                    "new-value", "legacy-value", "default",
                    new_name="CCDASH_TEST_NEW", legacy_name=self._legacy_name,
                )

    def test_gemini_api_key_resolves_through_the_same_helper(self) -> None:
        """Config-surface proof (not process-reload-dependent): the SAME

        helper this test class exercises directly is the one
        ``backend/config.py`` calls for ``CCDASH_GEMINI_API_KEY`` -- pinned
        by re-running the exact call config.py makes, so a regression that
        reverts that line back to a bare ``os.getenv`` (losing the fallback)
        would change this test's expected result.
        """
        import inspect

        source = inspect.getsource(config)
        self.assertIn("CCDASH_LLM_GEMINI_API_KEY", source)
        self.assertIn(
            'CCDASH_GEMINI_API_KEY: str = resolve_with_legacy_fallback(',
            source,
        )


# ── Output sanitization ──────────────────────────────────────────────────────

class SanitizeTitleTests(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(_sanitize_title(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_sanitize_title(""))

    def test_whitespace_only_returns_none(self) -> None:
        self.assertIsNone(_sanitize_title("   \n\t  "))

    def test_strips_surrounding_quotes(self) -> None:
        self.assertEqual(_sanitize_title('"Fix the login bug"'), "Fix the login bug")

    def test_takes_only_the_first_line(self) -> None:
        self.assertEqual(
            _sanitize_title("Fix the login bug\nThis is an explanation."),
            "Fix the login bug",
        )

    def test_collapses_internal_whitespace(self) -> None:
        self.assertEqual(_sanitize_title("Fix   the    login   bug"), "Fix the login bug")

    def test_conforming_long_title_is_truncated_not_rejected(self) -> None:
        title = "word " * 30  # ~150 chars, under the reject threshold
        result = _sanitize_title(title)
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), 100)

    def test_wildly_non_conforming_output_is_rejected_outright(self) -> None:
        """An output far longer than any plausible title (e.g. the model

        echoed a whole paragraph) is rejected entirely — never truncated
        into something that still looks like a plausible stored name.
        """
        essay = "This session covered a lot of ground. " * 20  # > 400 chars
        self.assertGreater(len(essay), 400)
        self.assertIsNone(_sanitize_title(essay))


class BuildPromptTextTests(unittest.TestCase):
    def test_prefers_user_and_assistant_speaker_content(self) -> None:
        items = [
            _make_fake_log(1, "Please fix the login bug", speaker="user"),
            _make_fake_log(2, "tool output noise", speaker="tool"),
        ]
        text = _build_prompt_text(items)
        self.assertIn("Please fix the login bug", text)
        self.assertNotIn("tool output noise", text)

    def test_falls_back_to_any_content_when_no_preferred_speaker(self) -> None:
        items = [_make_fake_log(1, "only tool content here", speaker="tool")]
        text = _build_prompt_text(items)
        self.assertIn("only tool content here", text)

    def test_empty_items_yield_empty_prompt(self) -> None:
        self.assertEqual(_build_prompt_text([]), "")

    def test_non_string_content_is_skipped(self) -> None:
        items = [{"speaker": "user", "content": {"not": "a string"}}]
        self.assertEqual(_build_prompt_text(items), "")


# ── derive_name: fail-open + persistence + redaction wiring ─────────────────

class DeriveNameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakeCorePortsFactory(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        await self.session_repo.upsert(_session(SESSION_A1), PROJ_A)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_missing_ids_returns_none(self) -> None:
        backend = LocalOllamaNamingBackend(ports=self.ports)
        result = await backend.derive_name({})
        self.assertIsNone(result)

    async def test_session_not_found_returns_none(self) -> None:
        backend = LocalOllamaNamingBackend(ports=self.ports)
        result = await backend.derive_name({"id": "does-not-exist", "project_id": PROJ_A})
        self.assertIsNone(result)

    async def test_ollama_connection_error_is_fail_open_no_op(self) -> None:
        """Ollama not installed/running is the common case — must never raise."""
        fake_logs = [_make_fake_log(1, "Please help me fix the flaky test")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(
                raise_exc=httpx.ConnectError("Connection refused")
            ),
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertIsNone(result)
        # Never persisted — session_name must remain NULL.
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertIsNone(row["session_name"])

    async def test_timeout_is_fail_open_no_op(self) -> None:
        fake_logs = [_make_fake_log(1, "Investigate the memory leak")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(raise_exc=httpx.ReadTimeout("timed out")),
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)

    async def test_no_usable_transcript_text_returns_none_without_calling_ollama(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ) as mock_logs, patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient"
        ) as mock_client_cls:
            backend = LocalOllamaNamingBackend(ports=self.ports)
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertIsNone(result)
        mock_logs.assert_awaited()
        mock_client_cls.assert_not_called()

    async def test_successful_derivation_persists_with_derived_generative_provenance(self) -> None:
        fake_logs = [_make_fake_log(1, "Please help me refactor the auth module")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(response_text="Refactor the auth module"),
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertEqual(result, "Refactor the auth module")
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertEqual(row["session_name"], "Refactor the auth module")
        self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_DERIVED_GENERATIVE)

    async def test_never_overwrites_a_stronger_existing_source(self) -> None:
        """Idempotency / rank gate: a provider-persisted name already on the

        row must never be replaced by a derived-generative one, even when
        the model call itself succeeds.
        """
        await self.session_repo.upsert(
            {
                "id": SESSION_A1,
                "sessionName": "Provider-set title",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            PROJ_A,
        )
        await self.db.commit()

        fake_logs = [_make_fake_log(1, "Please help me refactor the auth module")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(response_text="Refactor the auth module"),
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        # The backend call itself is not what's asserted here (it may or may
        # not attempt persistence) — what matters is the row is unchanged.
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertEqual(row["session_name"], "Provider-set title")
        self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_PROVIDER_PERSISTED)
        self.assertIsNone(result)

    async def test_non_conforming_model_output_is_never_persisted(self) -> None:
        fake_logs = [_make_fake_log(1, "Please help me refactor the auth module")]
        essay = "This session covered a lot of ground. " * 20
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(response_text=essay),
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertIsNone(result)
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertIsNone(row["session_name"])

    async def test_prompt_never_contains_a_secret_present_in_the_raw_transcript(self) -> None:
        """CRITICAL invariant: input path runs through redact_entries.

        A known Layer-1 secret pattern (an "sk-" style API key) in the
        fixture transcript must be scrubbed to REDACTED_PLACEHOLDER before
        it is ever assembled into the model prompt -- proving this backend
        reads via ``session_detail.get_session_detail`` (which redacts)
        rather than any raw-JSONL path.
        """
        secret = "sk-" + "A" * 30
        fake_logs = [_make_fake_log(1, f"Here is my key: {secret} please rotate it")]
        mock_client = _mock_ollama_client(response_text="Rotate the leaked API key")
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertTrue(mock_client.post.await_args is not None)
        sent_payload = mock_client.post.await_args.kwargs.get("json") or mock_client.post.await_args.args[1]
        sent_prompt = sent_payload["prompt"]
        self.assertNotIn(secret, sent_prompt)
        self.assertIn("[REDACTED]", sent_prompt)

    async def test_uses_configured_model_and_local_base_url(self) -> None:
        fake_logs = [_make_fake_log(1, "Please help me fix the login bug")]
        mock_client = _mock_ollama_client(response_text="Fix the login bug")
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=mock_client,
        ) as mock_client_cls:
            backend = LocalOllamaNamingBackend(
                ports=self.ports, base_url="http://localhost:11434", model="gemma2:2b"
            )
            await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        sent_payload = mock_client.post.await_args.kwargs.get("json") or mock_client.post.await_args.args[1]
        self.assertEqual(sent_payload["model"], "gemma2:2b")
        called_url = mock_client.post.await_args.args[0]
        self.assertTrue(called_url.startswith("http://localhost:11434"))


# ── Circuit breaker: bound the wasted work when Ollama is unavailable ──────

class CircuitBreakerTests(unittest.IsolatedAsyncioTestCase):
    """Reviewer fix: an unavailable Ollama daemon must not pay for a full

    transcript fetch (get_session_detail -- redaction + transcript-parse)
    for every candidate, forever. After
    ``LocalOllamaNamingBackend._CONSECUTIVE_FAILURE_THRESHOLD`` consecutive
    Ollama failures on ONE backend instance, later candidates in the same
    tick must skip the transcript fetch entirely.
    """

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakeCorePortsFactory(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.session_ids = [SESSION_A1, "sess-2", "sess-3", "sess-4", "sess-5"]
        for session_id in self.session_ids:
            await self.session_repo.upsert(_session(session_id), PROJ_A)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_transcript_fetch_is_not_repeated_once_backend_is_known_down(self) -> None:
        fake_logs = [_make_fake_log(1, "Investigate something")]
        threshold = LocalOllamaNamingBackend._CONSECUTIVE_FAILURE_THRESHOLD

        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ) as mock_logs, patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(raise_exc=httpx.ConnectError("Connection refused")),
        ):
            backend = LocalOllamaNamingBackend(ports=self.ports)
            for session_id in self.session_ids:
                result = await backend.derive_name({"id": session_id, "project_id": PROJ_A})
                self.assertIsNone(result)

        # Exactly `threshold` candidates paid for the transcript fetch (each
        # one failing the Ollama call in turn); every candidate after the
        # breaker opened skipped it entirely -- 5 candidates, threshold=3,
        # so exactly 3 fetch attempts, never 5.
        self.assertEqual(mock_logs.await_count, threshold)
        self.assertEqual(backend._consecutive_ollama_failures, threshold)

    async def test_reset_circuit_breaker_allows_a_fresh_attempt(self) -> None:
        """``reset_circuit_breaker`` is what ``SessionNamingSweepJob`` calls

        once per tick -- without it, an outage discovered on tick N would
        permanently disable the naming lane on every later tick, since a
        tripped breaker can never itself observe Ollama recovering (it skips
        the call that would prove recovery). Simulates the job's own reset by
        calling it directly.
        """
        backend = LocalOllamaNamingBackend(ports=self.ports)
        backend._consecutive_ollama_failures = LocalOllamaNamingBackend._CONSECUTIVE_FAILURE_THRESHOLD

        fake_logs = [_make_fake_log(1, "Fix the flaky test")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ) as mock_logs, patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(response_text="Fix the flaky test"),
        ):
            # Breaker is open -- without a reset, this must stay a no-op.
            result_before_reset = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})
            self.assertIsNone(result_before_reset)
            mock_logs.assert_not_awaited()

            backend.reset_circuit_breaker()

            result_after_reset = await backend.derive_name({"id": "sess-2", "project_id": PROJ_A})

        self.assertEqual(result_after_reset, "Fix the flaky test")
        self.assertEqual(backend._consecutive_ollama_failures, 0)

    async def test_a_successful_call_resets_the_counter(self) -> None:
        backend = LocalOllamaNamingBackend(ports=self.ports)
        backend._consecutive_ollama_failures = 2  # below threshold -- not yet open

        fake_logs = [_make_fake_log(1, "Refactor the module")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_local_backend.httpx.AsyncClient",
            return_value=_mock_ollama_client(response_text="Refactor the module"),
        ):
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertEqual(result, "Refactor the module")
        self.assertEqual(backend._consecutive_ollama_failures, 0)


# ── derive_name_fail_open integration with the sweep job's own wrapper ──────

class SweepJobIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """A raising LocalOllamaNamingBackend must also survive the sweep job's

    own ``derive_name_fail_open`` wrapper — belt-and-suspenders across both
    layers (backend's own internal fail-open AND the job's).
    """

    async def test_backend_exception_survives_the_jobs_fail_open_wrapper(self) -> None:
        from backend.adapters.jobs.session_naming_sweep_job import derive_name_fail_open

        backend = types.SimpleNamespace(
            derive_name=AsyncMock(side_effect=RuntimeError("ollama daemon crashed"))
        )
        result = await derive_name_fail_open(backend, {"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)


class SetDerivedSessionNameRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Direct coverage of ``SqliteSessionRepository.set_derived_session_name``,

    independent of the Ollama backend that consumes it.
    """

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)
        await self.repo.upsert(_session(SESSION_A1), PROJ_A)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_writes_when_row_is_unnamed(self) -> None:
        written = await self.repo.set_derived_session_name(
            PROJ_A, SESSION_A1, "A derived title", SESSION_NAME_SOURCE_DERIVED_GENERATIVE
        )
        self.assertTrue(written)
        row = await self.repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertEqual(row["session_name"], "A derived title")
        self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_DERIVED_GENERATIVE)

    async def test_refuses_to_overwrite_a_stronger_source(self) -> None:
        await self.repo.upsert(
            {
                "id": SESSION_A1,
                "sessionName": "Provider title",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            PROJ_A,
        )
        await self.db.commit()

        written = await self.repo.set_derived_session_name(
            PROJ_A, SESSION_A1, "A derived title", SESSION_NAME_SOURCE_DERIVED_GENERATIVE
        )
        self.assertFalse(written)
        row = await self.repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertEqual(row["session_name"], "Provider title")

    async def test_missing_row_returns_false(self) -> None:
        written = await self.repo.set_derived_session_name(
            PROJ_A, "does-not-exist", "A title", SESSION_NAME_SOURCE_DERIVED_GENERATIVE
        )
        self.assertFalse(written)

    async def test_idempotent_no_op_when_already_correct(self) -> None:
        await self.repo.set_derived_session_name(
            PROJ_A, SESSION_A1, "A derived title", SESSION_NAME_SOURCE_DERIVED_GENERATIVE
        )
        written_again = await self.repo.set_derived_session_name(
            PROJ_A, SESSION_A1, "A derived title", SESSION_NAME_SOURCE_DERIVED_GENERATIVE
        )
        self.assertFalse(written_again)


class ReadPathNeverCallsAModelTests(unittest.TestCase):
    """Named for the plan's AC->command row (``pytest -k "naming_read_path"``).

    Narrow structural guard scoped to this task's own module: the read/
    render path (``session_detail.get_session_detail``, the transport this
    backend itself reads through) does not import this naming backend or
    ``httpx`` — a model call can only happen from the worker-side sweep job,
    never from a request-serving read path. The cross-cutting version of
    this guard (every router/service in the read path, mirroring
    ``test_aar_review_no_llm_imports.py``) is T3-005's scope.
    """

    def test_naming_read_path_session_detail_module_has_no_model_client_import(self) -> None:
        import inspect

        from backend.application.services.agent_queries import session_detail

        source = inspect.getsource(session_detail)
        self.assertNotIn("httpx", source)
        self.assertNotIn("session_naming_local_backend", source)
        self.assertNotIn("ollama", source.lower())


if __name__ == "__main__":
    unittest.main()
