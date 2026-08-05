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


# ── Zero-egress-by-default backend resolution ───────────────────────────────

class BackendResolutionTests(unittest.TestCase):
    """The milestone's headline AC: default config never reaches the hosted lane."""

    def test_default_config_resolves_to_local_backend(self) -> None:
        self.assertEqual(config.CCDASH_SESSION_NAMING_BACKEND, "local")
        backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, LocalOllamaNamingBackend)

    def test_hosted_flag_alone_is_unreachable_without_redaction_gate_check(self) -> None:
        """The opt-in flag by itself is not sufficient to inspect --

        this resolver additionally consults the redaction gate (T3-003).
        With the default redaction gate ON (the secure default), opting
        into "hosted" DOES construct a real backend -- see
        ``test_session_naming_hosted_backend.py`` for the full
        both-conditions-required matrix. This test only pins that the
        resolver no longer hardcodes ``None`` for "hosted" now that Lane B
        has landed.
        """
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"):
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
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), self.assertLogs(
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
