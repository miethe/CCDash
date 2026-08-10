"""automatic-session-naming (M3 / T3-004) — guard flags + fail-open wiring.

Mirrors ``test_aar_review_worker_guards.py``'s naming/shape for this
feature's guard layer. Covers:

  1. Default values for all five ``CCDASH_SESSION_NAMING_*`` flags
     (``ENABLED``, ``QUOTA``, ``WINDOW_HOURS``, ``SWEEP_INTERVAL_SECONDS``,
     ``BACKEND``) — especially that ``ENABLED`` defaults False (kill-switch)
     and ``BACKEND`` defaults to the zero-egress ``"local"`` lane.
  2. Fail-open behaviour: a naming backend whose ``derive_name`` raises must
     never crash the sweep tick, never block a later candidate, and must
     leave ``session_name`` NULL (i.e. ``sessions_named`` stays 0 for that
     candidate) — the AC this task exists to satisfy.
  3. The happy path (a backend that succeeds) increments ``sessions_named``,
     as a sanity check that the seam is actually wired end-to-end and not
     just a no-op regardless of input.
  4. ``_start_session_naming_sweep_task`` (backend/adapters/jobs/runtime.py)
     obeys the same worker-only / job-present gating as its AAR-review and
     routing-feedback siblings.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_naming_sweep_guards.py -v
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend import config
from backend.adapters.jobs.runtime import RuntimeJobAdapter
from backend.adapters.jobs.session_naming_sweep_job import (
    SessionNamingSweepJob,
    derive_name_fail_open,
)
from backend.runtime.profiles import get_runtime_profile


class DefaultFlagValueTests(unittest.TestCase):
    """Pins the exact defaults T3-002/T3-003 will consume."""

    def test_enabled_defaults_false(self) -> None:
        """Kill-switch: default-off for the derive-worker."""
        self.assertFalse(config.CCDASH_SESSION_NAMING_ENABLED)

    def test_quota_defaults_to_200(self) -> None:
        self.assertEqual(config.CCDASH_SESSION_NAMING_QUOTA, 200)

    def test_window_hours_defaults_to_24(self) -> None:
        self.assertEqual(config.CCDASH_SESSION_NAMING_WINDOW_HOURS, 24)

    def test_sweep_interval_seconds_defaults_to_1800(self) -> None:
        self.assertEqual(config.CCDASH_SESSION_NAMING_SWEEP_INTERVAL_SECONDS, 1800)

    def test_backend_defaults_to_local(self) -> None:
        """Zero-egress-by-default: "hosted" is opt-in only, never the default."""
        self.assertEqual(config.CCDASH_SESSION_NAMING_BACKEND, "local")

    def test_llm_egress_consent_defaults_false(self) -> None:
        """hosted-llm-anthropic-ica-lane-v1 M2: the GLOBAL egress consent

        kill-switch -- fail-closed by default, same polarity as
        ``CCDASH_SESSION_NAMING_ENABLED`` above (opt-in, never opt-out).
        """
        self.assertFalse(config.CCDASH_LLM_EGRESS_CONSENT)

    def test_llm_session_naming_lane_defaults_to_unset(self) -> None:
        """hosted-llm-anthropic-ica-lane-v1 M3-B: the PREFERRED lane

        selector is left UN-defaulted (empty string, not "local") so the
        legacy-fallback helper can distinguish "absent" from "explicitly
        local" -- ``CCDASH_SESSION_NAMING_BACKEND`` above stays the
        defaulted fallback source.
        """
        self.assertEqual(config.CCDASH_LLM_SESSION_NAMING_LANE, "")

    def test_llm_anthropic_base_url_defaults_to_ica(self) -> None:
        """ADR-017: ICA is the default hosted endpoint, not the paid

        Anthropic-direct lane -- the trust boundary is already crossed and
        ICA's free tier makes a systematic sweep affordable.
        """
        self.assertEqual(
            config.CCDASH_LLM_ANTHROPIC_BASE_URL,
            "https://api.nextgen-beta.ica.ibm.com/ica",
        )

    def test_llm_anthropic_api_key_defaults_empty_no_legacy(self) -> None:
        """No legacy equivalent -- absent means the anthropic lane is

        disabled at derive-time (never a crash), same contract as
        ``CCDASH_GEMINI_API_KEY``'s own "unset -> disabled" precedent.
        """
        self.assertEqual(config.CCDASH_LLM_ANTHROPIC_API_KEY, "")

    def test_llm_anthropic_model_defaults_empty_deliberately_no_default(self) -> None:
        """This plan's own open_questions: "a wrong default is a silent

        cost decision" -- pins that NO default was added, on purpose.
        """
        self.assertEqual(config.CCDASH_LLM_ANTHROPIC_MODEL, "")


class DeriveNameFailOpenTests(unittest.IsolatedAsyncioTestCase):
    """Pure unit coverage of the fail-open primitive itself."""

    async def test_raising_backend_returns_none_and_never_raises(self) -> None:
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(side_effect=RuntimeError("boom"))
        )
        result = await derive_name_fail_open(backend, {"id": "s1"})
        self.assertIsNone(result)

    async def test_raising_backend_is_logged_not_silently_swallowed(self) -> None:
        """T3-005 (5): fail-open must leave ``session_name`` NULL AND log --

        a caught-and-discarded exception with no log trace would be
        indistinguishable from "nothing happened" during an incident, which
        defeats the point of failing open rather than failing silent. Pins
        the WARNING-level log emitted by ``derive_name_fail_open`` (see
        ``backend/adapters/jobs/session_naming_sweep_job.py``), including the
        candidate id, so an operator can find the affected session.
        """
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(side_effect=RuntimeError("ollama daemon crashed"))
        )
        with self.assertLogs("ccdash.jobs.session_naming_sweep", level="WARNING") as captured:
            result = await derive_name_fail_open(backend, {"id": "sess-needs-a-name"})

        self.assertIsNone(result)
        joined = "\n".join(captured.output)
        self.assertIn("sess-needs-a-name", joined)
        self.assertIn("fail-open", joined.lower())

    async def test_successful_backend_returns_the_derived_name(self) -> None:
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(return_value="Fix the login bug")
        )
        result = await derive_name_fail_open(backend, {"id": "s1"})
        self.assertEqual(result, "Fix the login bug")

    async def test_backend_returning_falsy_is_a_normal_no_op_not_a_failure(self) -> None:
        backend = types.SimpleNamespace(derive_name=AsyncMock(return_value=None))
        result = await derive_name_fail_open(backend, {"id": "s1"})
        self.assertIsNone(result)


class SessionNamingSweepJobFailOpenTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end (mocked ports) fail-open coverage through ``_execute_inner``."""

    def _make_ports(self, *, candidates: list[dict]) -> types.SimpleNamespace:
        async def _list_missing_session_name(project_id, *, limit=None, since=None):
            # Mirrors the real repository's SQL-level LIMIT: slicing happens
            # HERE (inside the fake "query"), never in the job's own Python
            # loop, matching the reviewer fix that pushed the quota into SQL.
            return candidates[:limit] if limit is not None else list(candidates)

        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(side_effect=_list_missing_session_name),
            count_missing_session_name=AsyncMock(return_value=len(candidates)),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        return types.SimpleNamespace(storage=storage)

    async def test_raising_backend_never_crashes_and_leaves_all_names_null(self) -> None:
        candidates = [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]
        ports = self._make_ports(candidates=candidates)
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(side_effect=RuntimeError("naming backend unreachable"))
        )
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)
        project = types.SimpleNamespace(id="proj-a")

        result = await job._execute_inner(project, "proj-a")

        self.assertTrue(result.success)
        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.candidates_found, 3)
        # Fail-open: every candidate's derivation raised, so none were named —
        # but the tick itself completed successfully (never crashed).
        self.assertEqual(result.sessions_named, 0)
        # A raising backend must never block a later candidate: all three
        # candidates were still attempted (three calls), not just the first.
        self.assertEqual(backend.derive_name.await_count, 3)

    async def test_reset_circuit_breaker_is_called_once_per_tick_when_present(self) -> None:
        """Reviewer fix: the job resets a duck-typed circuit breaker at the

        start of each tick's derive loop, so an outage on one tick never
        permanently disables a later tick (see
        LocalOllamaNamingBackend.reset_circuit_breaker's docstring).
        """
        candidates = [{"id": "s1"}, {"id": "s2"}]
        ports = self._make_ports(candidates=candidates)
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(return_value="A derived name"),
            reset_circuit_breaker=Mock(),
        )
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)
        project = types.SimpleNamespace(id="proj-a")

        await job._execute_inner(project, "proj-a")

        backend.reset_circuit_breaker.assert_called_once_with()

    async def test_missing_reset_circuit_breaker_is_tolerated(self) -> None:
        """A backend without a breaker (no ``reset_circuit_breaker`` method)

        must not crash the tick -- the job duck-types the call.
        """
        candidates = [{"id": "s1"}]
        ports = self._make_ports(candidates=candidates)
        backend = types.SimpleNamespace(derive_name=AsyncMock(return_value="A name"))
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)
        project = types.SimpleNamespace(id="proj-a")

        result = await job._execute_inner(project, "proj-a")

        self.assertTrue(result.success)
        self.assertEqual(result.sessions_named, 1)

    async def test_successful_backend_increments_sessions_named(self) -> None:
        candidates = [{"id": "s1"}, {"id": "s2"}]
        ports = self._make_ports(candidates=candidates)
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(return_value="Investigate the flaky test")
        )
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)
        project = types.SimpleNamespace(id="proj-a")

        result = await job._execute_inner(project, "proj-a")

        self.assertTrue(result.success)
        self.assertEqual(result.candidates_found, 2)
        self.assertEqual(result.sessions_named, 2)

    async def test_no_backend_injected_stays_a_structural_no_op(self) -> None:
        """Default ``naming_backend=None`` — the production-today wiring —

        still finds candidates but derives nothing (T3-002/T3-003 have not
        landed yet).
        """
        ports = self._make_ports(candidates=[{"id": "s1"}])
        job = SessionNamingSweepJob(ports=ports, project=None)
        project = types.SimpleNamespace(id="proj-a")

        result = await job._execute_inner(project, "proj-a")

        self.assertEqual(result.candidates_found, 1)
        self.assertEqual(result.sessions_named, 0)

    async def test_quota_bounds_the_derive_loop_not_the_candidate_count(self) -> None:
        """``CCDASH_SESSION_NAMING_QUOTA`` caps per-tick derive attempts —

        ``candidates_found`` still reports the FULL backlog size (the
        idempotency/backlog signal), only the derive loop is bounded.
        """
        candidates = [{"id": f"s{i}"} for i in range(5)]
        ports = self._make_ports(candidates=candidates)
        backend = types.SimpleNamespace(
            derive_name=AsyncMock(return_value="A derived name")
        )
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)
        project = types.SimpleNamespace(id="proj-a")

        with patch.object(config, "CCDASH_SESSION_NAMING_QUOTA", 2):
            result = await job._execute_inner(project, "proj-a")

        self.assertEqual(result.candidates_found, 5)
        self.assertEqual(result.sessions_named, 2)
        self.assertEqual(backend.derive_name.await_count, 2)


class SessionNamingSweepTaskStarterTests(unittest.TestCase):
    """``_start_session_naming_sweep_task`` mirrors the AAR-review/routing-

    feedback sweep starters' worker-only / job-present gating exactly.
    """

    def _make_adapter(self, *, profile_name: str, job: object | None) -> RuntimeJobAdapter:
        profile = get_runtime_profile(profile_name)
        return RuntimeJobAdapter(
            profile=profile,
            ports=types.SimpleNamespace(job_scheduler=None),
            sync_engine=None,
            session_naming_sweep_job=job,
        )

    def test_returns_none_when_job_is_absent(self) -> None:
        adapter = self._make_adapter(profile_name="worker", job=None)
        self.assertIsNone(adapter._start_session_naming_sweep_task())

    def test_returns_none_on_worker_watch_profile_even_with_job_present(self) -> None:
        """Construction-time gating (container.py) admits worker-watch, but

        the periodic loop only ever starts under the plain ``worker``
        profile — identical asymmetry to the AAR-review/routing-feedback
        precedents.
        """
        job = types.SimpleNamespace(execute=AsyncMock())
        adapter = self._make_adapter(profile_name="worker-watch", job=job)
        self.assertIsNone(adapter._start_session_naming_sweep_task())


if __name__ == "__main__":
    unittest.main()
