"""automatic-session-naming (M3 / T3-003) — Lane B hosted (Gemini) naming backend.

Covers this task's required assertions:

  1. Both-conditions-required gate: the hosted backend is reachable ONLY
     when BOTH ``CCDASH_SESSION_NAMING_BACKEND=hosted`` AND
     ``CCDASH_REDACTION_PATTERNS_ENABLED`` are true. Either one absent makes
     the hosted path unreachable and the job falls back to a structural
     no-op (``resolve_naming_backend`` returns ``None``) -- never to
     sending anyway.
  2. Positive redaction assertion: this is the load-bearing test for this
     task. A known secret pattern present in a fixture transcript is
     observed to be ABSENT from the actual outbound Gemini payload, and
     ``[REDACTED]`` is observed present in its place -- proving the prompt
     that left the process had already passed ``redact_entries``, not
     merely that some flag was read.
  3. Fail-open: missing API key, network error, and timeout all return
     ``None`` without raising and without persisting anything.
  4. Persistence: a successful derivation is written with
     ``session_name_source = derived_generative`` and never overwrites a
     stronger existing source (idempotency/rank gate), mirroring Lane A.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_naming_hosted_backend.py -v
"""
from __future__ import annotations

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
from backend.services.session_naming_hosted_backend import HostedGeminiNamingBackend
from backend.services.session_naming_local_backend import (
    LocalOllamaNamingBackend,
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
    """Minimal real-DB CorePorts stand-in (mirrors test_session_naming_local_backend.py)."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


def _mock_gemini_client(
    response_text: str | None = None, *, raise_exc: Exception | None = None
) -> MagicMock:
    mock_client_instance = AsyncMock()
    if raise_exc is not None:
        mock_client_instance.post = AsyncMock(side_effect=raise_exc)
    else:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": response_text}]}}]
            if response_text is not None
            else []
        }
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_client_instance


def _mock_gemini_error_client(status_code: int, body_text: str) -> MagicMock:
    """A mock ``httpx.AsyncClient`` whose response's ``raise_for_status()``

    raises ``httpx.HTTPStatusError`` -- carrying a distinctive ``body_text``
    the adapter/backend must never place in a log record (M1: no provider
    error body may reach a log).
    """
    mock_client_instance = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body_text
    mock_resp.content = body_text.encode()
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=mock_resp
        )
    )
    mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_client_instance


# ── Both-conditions-required gate ────────────────────────────────────────────

class BothConditionsRequiredGateTests(unittest.TestCase):
    """The headline AC for this task: hosted is reachable ONLY when BOTH

    ``CCDASH_SESSION_NAMING_BACKEND=hosted`` AND
    ``CCDASH_REDACTION_PATTERNS_ENABLED`` are true. Each condition is
    tested absent independently.
    """

    def test_both_conditions_present_constructs_hosted_backend(self) -> None:
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ):
            backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, HostedGeminiNamingBackend)

    def test_backend_flag_absent_is_unreachable_even_with_redaction_on(self) -> None:
        """``CCDASH_SESSION_NAMING_BACKEND`` absent (default "local") --

        the hosted path is never reached regardless of the redaction gate.
        """
        self.assertEqual(config.CCDASH_SESSION_NAMING_BACKEND, "local")
        with patch.dict("os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}):
            backend = resolve_naming_backend(ports=object())
        self.assertIsInstance(backend, LocalOllamaNamingBackend)

    def test_redaction_gate_absent_is_unreachable_even_with_backend_hosted(self) -> None:
        """``CCDASH_REDACTION_PATTERNS_ENABLED=false`` -- the hosted path is

        unreachable even though the operator explicitly opted into
        "hosted". The job must fall back to a structural no-op
        (``None``), never to sending unredacted content.
        """
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "false"}
        ):
            backend = resolve_naming_backend(ports=object())
        self.assertIsNone(backend)

    def test_naming_egress_hosted_requires_both_flags(self) -> None:
        """Named for the plan's AC->command row (``pytest -k "naming_egress"``)."""
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "false"}
        ):
            self.assertIsNone(resolve_naming_backend(ports=object()))
        with patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch.dict(
            "os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "true"}
        ):
            self.assertIsInstance(resolve_naming_backend(ports=object()), HostedGeminiNamingBackend)


# ── derive_name: fail-open + persistence + THE positive redaction assertion ─

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
        backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
        result = await backend.derive_name({})
        self.assertIsNone(result)

    async def test_missing_api_key_is_fail_open_no_op(self) -> None:
        backend = HostedGeminiNamingBackend(ports=self.ports, api_key="")
        result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertIsNone(row["session_name"])

    async def test_redaction_gate_off_at_call_time_is_fail_closed_no_op(self) -> None:
        """Defense-in-depth: even if constructed while the gate was on, a

        gate flip to off before the call must still short-circuit --
        this backend never sends once the gate is off, regardless of when
        the flag changed.
        """
        backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
        with patch.dict("os.environ", {"CCDASH_REDACTION_PATTERNS_ENABLED": "false"}), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient"
        ) as mock_client_cls:
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)
        mock_client_cls.assert_not_called()

    async def test_connection_error_is_fail_open_no_op(self) -> None:
        fake_logs = [_make_fake_log(1, "Please help me fix the flaky test")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=_mock_gemini_client(raise_exc=httpx.ConnectError("Connection refused")),
        ):
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertIsNone(row["session_name"])

    async def test_timeout_is_fail_open_no_op(self) -> None:
        fake_logs = [_make_fake_log(1, "Investigate the memory leak")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=_mock_gemini_client(raise_exc=httpx.ReadTimeout("timed out")),
        ):
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)

    async def test_no_usable_transcript_text_returns_none_without_calling_gemini(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ) as mock_logs, patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient"
        ) as mock_client_cls:
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
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
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=_mock_gemini_client(response_text="Refactor the auth module"),
        ):
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertEqual(result, "Refactor the auth module")
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertEqual(row["session_name"], "Refactor the auth module")
        self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_DERIVED_GENERATIVE)

    async def test_successful_derivation_logs_an_audit_trail_line(self) -> None:
        """Security-review fix (T3-006): since Lane A and Lane B share the

        same `derived_generative` provenance token (the accepted deviation
        in implementation-notes.md), a successful Lane B write must be
        independently observable in the log stream by session_id/project_id
        -- the compensating audit trail for that token gap.
        """
        fake_logs = [_make_fake_log(1, "Please help me refactor the auth module")]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=_mock_gemini_client(response_text="Refactor the auth module"),
        ), self.assertLogs(
            "ccdash.services.session_naming_hosted_backend", level="INFO"
        ) as captured:
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        joined = "\n".join(captured.output)
        self.assertIn(SESSION_A1, joined)
        self.assertIn(PROJ_A, joined)
        self.assertIn("hosted", joined.lower())

    async def test_never_overwrites_a_stronger_existing_source(self) -> None:
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
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=_mock_gemini_client(response_text="Refactor the auth module"),
        ):
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

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
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=_mock_gemini_client(response_text=essay),
        ):
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertIsNone(result)
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertIsNone(row["session_name"])

    async def test_prompt_never_contains_a_secret_present_in_the_raw_transcript(self) -> None:
        """THE positive redaction assertion for this task.

        A known Layer-1 secret pattern (an "sk-" style API key) in the
        fixture transcript must be scrubbed to REDACTED_PLACEHOLDER before
        it is ever assembled into the Lane B outbound payload -- observed
        directly on the actual httpx call the backend makes, proving this
        backend reads via ``session_detail.get_session_detail`` (which runs
        ``redact_entries``) rather than any raw-JSONL/unredacted path.
        """
        secret = "sk-" + "A" * 30
        fake_logs = [_make_fake_log(1, f"Here is my key: {secret} please rotate it")]
        mock_client = _mock_gemini_client(response_text="Rotate the leaked API key")
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        self.assertTrue(mock_client.post.await_args is not None)
        sent_payload = mock_client.post.await_args.kwargs.get("json") or mock_client.post.await_args.args[1]
        sent_prompt = sent_payload["contents"][0]["parts"][0]["text"]
        self.assertNotIn(secret, sent_prompt)
        self.assertIn("[REDACTED]", sent_prompt)

    async def test_uses_configured_model_and_sends_api_key_as_a_header(self) -> None:
        """M1 (egress-path hardening): the credential travels as the

        ``x-goog-api-key`` request header, never in the URL query string --
        a URL lands in access logs, proxy logs, and browser history, so a
        credential there is a leak surface a header is not.
        """
        fake_logs = [_make_fake_log(1, "Please help me fix the login bug")]
        mock_client = _mock_gemini_client(response_text="Fix the login bug")
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=mock_client,
        ):
            backend = HostedGeminiNamingBackend(
                ports=self.ports, api_key="fake-key-123", model="gemini-2.0-flash"
            )
            await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        called_url = mock_client.post.await_args.args[0]
        called_kwargs = mock_client.post.await_args.kwargs
        self.assertIn("gemini-2.0-flash", called_url)
        self.assertNotIn("key=", called_url)
        self.assertNotIn("fake-key-123", called_url)
        self.assertEqual(
            called_kwargs.get("headers", {}).get("x-goog-api-key"), "fake-key-123"
        )


# ── derive_name_fail_open integration with the sweep job's own wrapper ──────

class SweepJobIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """A raising HostedGeminiNamingBackend must also survive the sweep job's

    own ``derive_name_fail_open`` wrapper -- belt-and-suspenders across both
    layers (backend's own internal fail-open AND the job's), mirroring Lane
    A's identical coverage.
    """

    async def test_backend_exception_survives_the_jobs_fail_open_wrapper(self) -> None:
        import types

        from backend.adapters.jobs.session_naming_sweep_job import derive_name_fail_open

        backend = types.SimpleNamespace(
            derive_name=AsyncMock(side_effect=RuntimeError("gemini call crashed"))
        )
        result = await derive_name_fail_open(backend, {"id": SESSION_A1, "project_id": PROJ_A})
        self.assertIsNone(result)


# ── M1: no provider error body ever reaches a log ───────────────────────────

class ProviderErrorBodyNeverLoggedTests(unittest.IsolatedAsyncioTestCase):
    """M1 (egress-path hardening) -- a non-2xx provider response's body

    must never appear in any log record. ``backend/adapters/llm/gemini.py``
    logs the status code plus a fixed message on a non-2xx/transport error;
    it never logs ``response.text``/``.content``/a parsed body. This is
    asserted end-to-end through ``HostedGeminiNamingBackend.derive_name``
    (the real egress call site), not just against the adapter in isolation.
    """

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

    async def test_non_2xx_response_body_is_absent_from_every_log_record(self) -> None:
        secret_marker = "UPSTREAM_ERROR_BODY_MARKER_9f31a2"
        fake_logs = [_make_fake_log(1, "Please help me fix the login bug")]
        mock_client = _mock_gemini_error_client(status_code=403, body_text=secret_marker)
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=fake_logs),
        ), patch(
            "backend.services.session_naming_hosted_backend.httpx.AsyncClient",
            return_value=mock_client,
        ), self.assertLogs("ccdash.adapters.llm.gemini", level="WARNING") as captured:
            backend = HostedGeminiNamingBackend(ports=self.ports, api_key="fake-key")
            result = await backend.derive_name({"id": SESSION_A1, "project_id": PROJ_A})

        # Fail-open: the caller still gets a clean None, never a raised
        # exception or a partially-persisted name.
        self.assertIsNone(result)
        row = await self.session_repo.get_by_id(SESSION_A1, project_id=PROJ_A)
        self.assertIsNone(row["session_name"])

        joined = "\n".join(captured.output)
        self.assertNotIn(secret_marker, joined)
        # The status code IS expected to be present -- that's the "fixed
        # message plus status code" contract, not a blanket "log nothing."
        self.assertIn("403", joined)


if __name__ == "__main__":
    unittest.main()
