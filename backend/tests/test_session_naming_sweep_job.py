"""automatic-session-naming (M3 / T3-001) — SessionNamingSweepJob scaffold.

Covers this task's two required assertions:

  1. Worker-only registration: the ``api`` profile is excluded from the same
     profile set (``backend.runtime.container._WORKER_JOB_PROFILES``) that
     gates ``SessionNamingSweepJob`` construction in
     ``RuntimeContainer.startup()``; ``worker``/``worker-watch`` are included.
  2. Idempotency / candidate-selection query: ``list_missing_session_name``
     returns exactly (and only) the rows where ``session_name IS NULL`` —
     a session with a non-null ``session_name`` from ANY source (provider-
     persisted or derived-deterministic) is never selected.

Also covers the job's own default-off / candidate-count wiring at the unit
level (mocked ports), independent of the real repository.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_naming_sweep_job.py -v
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.adapters.jobs.session_naming_sweep_job import SessionNamingSweepJob
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.parsers.session_name_provenance import (
    SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
    SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
)


# ── Worker-only registration ─────────────────────────────────────────────────
class WorkerOnlyRegistrationTests(unittest.TestCase):
    """Pins the profile gate SessionNamingSweepJob's construction relies on.

    ``RuntimeContainer.startup()`` constructs ``SessionNamingSweepJob`` only
    when ``self.profile.name in _export_profiles`` where
    ``_export_profiles = _WORKER_JOB_PROFILES`` (see
    ``backend/runtime/container.py``). This test asserts that gate set
    excludes ``api`` and includes both worker profiles — the same predicate
    the container evaluates, made directly testable without exercising the
    full container lifecycle.
    """

    def test_api_profile_is_excluded(self) -> None:
        from backend.runtime.container import _WORKER_JOB_PROFILES

        self.assertNotIn("api", _WORKER_JOB_PROFILES)

    def test_worker_and_worker_watch_profiles_are_included(self) -> None:
        from backend.runtime.container import _WORKER_JOB_PROFILES

        self.assertIn("worker", _WORKER_JOB_PROFILES)
        self.assertIn("worker-watch", _WORKER_JOB_PROFILES)


class ConstructSessionNamingSweepJobTests(unittest.TestCase):
    """Drives the ACTUAL construction function ``RuntimeContainer.startup()``

    calls (``_construct_session_naming_sweep_job``), not merely the profile
    SET it happens to also consult -- a test that only asserts
    ``_WORKER_JOB_PROFILES``'s membership (above) cannot fail if the
    container's own gate logic were wrong (e.g. an inverted condition, or the
    flag check dropped entirely), because it never calls the function that
    performs the gating. This test does — with a lightweight stub ``ports``
    object, never a live DB connection, so it stays fast and never risks the
    ``RuntimeContainer.startup()`` DB-connection hang other worker-bootstrap
    tests in this repo warn against (see ``test_p3_worker_bootstrap.py``'s
    module docstring).
    """

    def _ports_stub(self) -> object:
        # `resolve_naming_backend` only needs `getattr(config, ...)` reads at
        # construction time (no network call) -- a bare object satisfies it.
        return types.SimpleNamespace()

    def test_api_profile_returns_none_even_when_flag_is_enabled(self) -> None:
        from backend.runtime.container import _construct_session_naming_sweep_job

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            result = _construct_session_naming_sweep_job("api", self._ports_stub())

        self.assertIsNone(result)

    def test_worker_profile_constructs_the_job_when_flag_is_enabled(self) -> None:
        from backend.runtime.container import _construct_session_naming_sweep_job

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            result = _construct_session_naming_sweep_job("worker", self._ports_stub())

        self.assertIsInstance(result, SessionNamingSweepJob)

    def test_worker_watch_profile_constructs_the_job_when_flag_is_enabled(self) -> None:
        from backend.runtime.container import _construct_session_naming_sweep_job

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            result = _construct_session_naming_sweep_job("worker-watch", self._ports_stub())

        self.assertIsInstance(result, SessionNamingSweepJob)

    def test_worker_profile_returns_none_when_flag_is_disabled(self) -> None:
        """The kill-switch: a worker-eligible profile still gets None unless

        CCDASH_SESSION_NAMING_ENABLED is also true.
        """
        from backend.runtime.container import _construct_session_naming_sweep_job

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", False):
            result = _construct_session_naming_sweep_job("worker", self._ports_stub())

        self.assertIsNone(result)


# ── Candidate-selection / idempotency query ──────────────────────────────────
class CandidateSelectionQueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_only_null_session_name_rows_are_selected(self) -> None:
        """Idempotency contract: a non-null session_name from ANY source is

        never re-selected, regardless of which provenance token it carries.
        """
        await self.repo.upsert(
            {
                "id": "named-provider",
                "sessionName": "Provider-named session",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            "proj-a",
        )
        await self.repo.upsert(
            {
                "id": "named-derived",
                "sessionName": "Derived-named session",
                "sessionNameSource": SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
            },
            "proj-a",
        )
        await self.repo.upsert({"id": "unnamed-1"}, "proj-a")
        await self.repo.upsert({"id": "unnamed-2"}, "proj-a")

        candidates = await self.repo.list_missing_session_name("proj-a")
        candidate_ids = {row["id"] for row in candidates}

        self.assertEqual(candidate_ids, {"unnamed-1", "unnamed-2"})
        self.assertNotIn("named-provider", candidate_ids)
        self.assertNotIn("named-derived", candidate_ids)

    async def test_scoped_to_project_id(self) -> None:
        await self.repo.upsert({"id": "unnamed-a"}, "proj-a")
        await self.repo.upsert({"id": "unnamed-b"}, "proj-b")

        candidates = await self.repo.list_missing_session_name("proj-a")
        candidate_ids = {row["id"] for row in candidates}

        self.assertEqual(candidate_ids, {"unnamed-a"})

    async def test_empty_when_every_session_already_named(self) -> None:
        await self.repo.upsert(
            {
                "id": "named-only",
                "sessionName": "Already named",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            "proj-a",
        )

        candidates = await self.repo.list_missing_session_name("proj-a")
        self.assertEqual(candidates, [])

    async def test_limit_bounds_result_count(self) -> None:
        await self.repo.upsert({"id": "unnamed-1"}, "proj-a")
        await self.repo.upsert({"id": "unnamed-2"}, "proj-a")
        await self.repo.upsert({"id": "unnamed-3"}, "proj-a")

        candidates = await self.repo.list_missing_session_name("proj-a", limit=2)
        self.assertEqual(len(candidates), 2)

    async def test_since_bounds_result_to_created_at_recency(self) -> None:
        """Reviewer fix: CCDASH_SESSION_NAMING_WINDOW_HOURS must actually
        change which candidates are selected, not just exist in config.py.
        """
        await self.db.execute(
            "INSERT INTO sessions (id, project_id, workspace_id, created_at, updated_at, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("old", "proj-a", "default-local", "2020-01-01T00:00:00", "2020-01-01T00:00:00", "old.jsonl"),
        )
        await self.repo.upsert({"id": "recent"}, "proj-a")
        await self.db.commit()

        unbounded = await self.repo.list_missing_session_name("proj-a")
        self.assertEqual({row["id"] for row in unbounded}, {"old", "recent"})

        bounded = await self.repo.list_missing_session_name("proj-a", since="2025-01-01T00:00:00")
        self.assertEqual({row["id"] for row in bounded}, {"recent"})

    async def test_count_missing_session_name_matches_list_length(self) -> None:
        await self.repo.upsert({"id": "unnamed-1"}, "proj-a")
        await self.repo.upsert({"id": "unnamed-2"}, "proj-a")
        await self.repo.upsert(
            {
                "id": "named",
                "sessionName": "Already named",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            "proj-a",
        )

        count = await self.repo.count_missing_session_name("proj-a")
        self.assertEqual(count, 2)

    async def test_count_missing_session_name_is_unaffected_by_limit(self) -> None:
        """The count is the TRUE backlog size, independent of any per-tick quota."""
        for i in range(5):
            await self.repo.upsert({"id": f"unnamed-{i}"}, "proj-a")

        count = await self.repo.count_missing_session_name("proj-a")
        limited = await self.repo.list_missing_session_name("proj-a", limit=2)

        self.assertEqual(count, 5)
        self.assertEqual(len(limited), 2)

    async def test_a_previously_derived_name_is_never_re_selected(self) -> None:
        """Simulates a sweep having already written a name on a prior tick —

        the row must disappear from the candidate set on the next tick, the
        same as any other non-null session_name.
        """
        await self.repo.upsert({"id": "s1"}, "proj-a")
        candidates_before = await self.repo.list_missing_session_name("proj-a")
        self.assertEqual({row["id"] for row in candidates_before}, {"s1"})

        # Simulate a naming backend (T3-002/T3-003) persisting a derived name.
        await self.repo.upsert(
            {
                "id": "s1",
                "sessionName": "Derived by the sweep",
                "sessionNameSource": SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
            },
            "proj-a",
        )
        candidates_after = await self.repo.list_missing_session_name("proj-a")
        self.assertEqual(candidates_after, [])


# ── Job-level unit tests (mocked ports) ──────────────────────────────────────
class SessionNamingSweepJobUnitTests(unittest.IsolatedAsyncioTestCase):
    def _make_ports(self, *, candidates: list[dict]) -> types.SimpleNamespace:
        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(return_value=candidates),
            count_missing_session_name=AsyncMock(return_value=len(candidates)),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        project = types.SimpleNamespace(id="proj-a")
        workspace_registry = types.SimpleNamespace(
            list_projects=lambda: [project], reload_projects=lambda: None
        )
        return types.SimpleNamespace(storage=storage, workspace_registry=workspace_registry)

    async def test_disabled_by_default(self) -> None:
        """CCDASH_SESSION_NAMING_ENABLED (T3-004) defaults to False —

        the kill-switch keeps this job a structural no-op until the flag is
        explicitly flipped on.
        """
        self.assertFalse(config.CCDASH_SESSION_NAMING_ENABLED)
        ports = self._make_ports(candidates=[{"id": "s1"}])
        job = SessionNamingSweepJob(ports=ports, project=None)

        result = job.execute
        outcome = await result(trigger="scheduled")

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.outcome, "disabled")
        self.assertEqual(outcome.candidates_found, 0)

    async def test_execute_inner_reports_candidate_count_without_deriving(self) -> None:
        """Directly exercises _execute_inner (bypassing the disabled-flag

        gate) to prove candidate counting is wired end-to-end while no
        naming backend call has happened yet (sessions_named stays 0). With
        no naming_backend injected there is nothing for candidate rows to
        do, so list_missing_session_name is never called at all (only the
        cheap count query runs) -- a perf win over loading rows nobody will
        use.
        """
        ports = self._make_ports(candidates=[{"id": "s1"}, {"id": "s2"}])
        job = SessionNamingSweepJob(ports=ports, project=None)
        project = types.SimpleNamespace(id="proj-a")

        result = await job._execute_inner(project, "proj-a")

        self.assertTrue(result.success)
        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.candidates_found, 2)
        self.assertEqual(result.sessions_named, 0)
        ports.storage.sessions().count_missing_session_name.assert_awaited_once_with("proj-a")
        ports.storage.sessions().list_missing_session_name.assert_not_awaited()

    async def test_execute_inner_passes_quota_as_sql_limit_when_backend_present(self) -> None:
        """Reviewer fix: the per-tick quota must be pushed into the

        repository call as `limit=`, never sliced in Python after loading
        the full backlog into memory.
        """
        ports = self._make_ports(candidates=[{"id": "s1"}, {"id": "s2"}])
        backend = types.SimpleNamespace(derive_name=AsyncMock(return_value="A name"))
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)
        project = types.SimpleNamespace(id="proj-a")

        with patch.object(config, "CCDASH_SESSION_NAMING_QUOTA", 2):
            result = await job._execute_inner(project, "proj-a")

        self.assertEqual(result.candidates_found, 2)
        self.assertEqual(result.sessions_named, 2)
        _, kwargs = ports.storage.sessions().list_missing_session_name.await_args
        self.assertEqual(kwargs.get("limit"), 2)


# ── Per-project egress consent gate (hosted-llm-anthropic-ica-lane-v1 M2) ───

class PerProjectEgressConsentTests(unittest.IsolatedAsyncioTestCase):
    """The per-project half of the leg's headline AC: global consent true +

    exactly one of two projects consented => only that project's sessions
    egress. The consent flag is read from whatever ``Project``-like object
    ``ports.workspace_registry.list_projects()`` returns each tick -- never
    cached on the job -- so a second test below proves the SAME job
    instance re-evaluates it on the very next tick without being
    reconstructed (the "no restart required" asymmetry the plan calls out).

    NOTE on the security-review fix: every ``workspace_registry`` stub in
    this class exposes a (no-op) ``reload_projects`` callable, so the
    per-tick freshness check (``SessionNamingSweepJob._resolve_projects_to_sweep``)
    always reports "confirmed" here -- these mock-based tests exercise the
    per-project consent LOGIC, not the caching layer itself (a mock that
    re-reads the same mutable Python object every call cannot exercise a
    real snapshot cache -- see
    ``test_db_project_registry.py::TestSweepJobObservesConsentFlipThroughTheRealCachingLayer``
    for the test that actually exercises the caching layer against a real
    ``DbProjectManager``). ``MissingReloadHookFailsClosedTests`` below is
    the mock-based test for the OTHER branch: no reload hook at all.
    """

    def _make_two_project_ports(
        self, *, consented_candidates: list[dict]
    ) -> tuple[object, object]:
        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(return_value=consented_candidates),
            count_missing_session_name=AsyncMock(return_value=len(consented_candidates)),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        proj_a = types.SimpleNamespace(id="proj-a", llm_egress_consent=True)
        proj_b = types.SimpleNamespace(id="proj-b", llm_egress_consent=False)
        workspace_registry = types.SimpleNamespace(
            list_projects=lambda: [proj_a, proj_b], reload_projects=lambda: None
        )
        ports = types.SimpleNamespace(storage=storage, workspace_registry=workspace_registry)
        return ports, sessions_repo

    def _egress_backend(self, *, name: str = "A name") -> types.SimpleNamespace:
        # A minimal stand-in for HostedGeminiNamingBackend: only the two
        # attributes SessionNamingSweepJob actually reads (``EGRESS``,
        # ``model``) plus the ``derive_name`` contract every naming backend
        # exposes.
        return types.SimpleNamespace(
            EGRESS=True, model="fake-hosted-model", derive_name=AsyncMock(return_value=name)
        )

    async def test_only_the_consented_project_is_swept_when_backend_is_egress(self) -> None:
        ports, sessions_repo = self._make_two_project_ports(
            consented_candidates=[{"id": "s1", "project_id": "proj-a"}]
        )
        backend = self._egress_backend()
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        # The declined project's id must NEVER appear in a repository call --
        # not "the derive loop skipped it," but "the sweep never even asked
        # how many candidates it has."
        queried_project_ids = {
            call.args[0] for call in sessions_repo.count_missing_session_name.await_args_list
        }
        self.assertEqual(queried_project_ids, {"proj-a"})

        self.assertTrue(result.success)
        self.assertEqual(result.candidates_found, 1)
        self.assertEqual(result.sessions_named, 1)
        self.assertEqual(set(result.details.get("projectIds", [])), {"proj-a", "proj-b"})

    async def test_local_backend_never_consults_per_project_consent(self) -> None:
        """A non-egress backend (``EGRESS`` absent/False, e.g. Lane A local

        Ollama) is unaffected by any project's ``llm_egress_consent`` value
        -- both projects are swept even though ``proj-b`` has not consented.
        """
        ports, sessions_repo = self._make_two_project_ports(
            consented_candidates=[{"id": "s1", "project_id": "proj-a"}]
        )
        backend = types.SimpleNamespace(
            model="fake-local-model", derive_name=AsyncMock(return_value="A name")
        )  # no EGRESS attribute at all -- duck-typed default False

        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            await job.execute(trigger="scheduled")

        queried_project_ids = {
            call.args[0] for call in sessions_repo.count_missing_session_name.await_args_list
        }
        self.assertEqual(queried_project_ids, {"proj-a", "proj-b"})

    async def test_revoking_consent_between_ticks_bites_on_the_very_next_tick_without_restart(
        self,
    ) -> None:
        """Consent revoked at "14:00" bites at "14:30" -- no restart of this

        SAME ``SessionNamingSweepJob`` instance, no reconstruction of it or
        its ``naming_backend``. The project object mutates between ticks,
        exactly as a real DB-backed ``workspace_registry.list_projects()``
        would return an updated row on the next call.
        """
        project = types.SimpleNamespace(id="proj-a", llm_egress_consent=True)
        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(
                return_value=[{"id": "s1", "project_id": "proj-a"}]
            ),
            count_missing_session_name=AsyncMock(return_value=1),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        workspace_registry = types.SimpleNamespace(
            list_projects=lambda: [project], reload_projects=lambda: None
        )
        ports = types.SimpleNamespace(storage=storage, workspace_registry=workspace_registry)
        backend = self._egress_backend()
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            first_tick = await job.execute(trigger="scheduled")
            self.assertEqual(first_tick.candidates_found, 1)
            sessions_repo.count_missing_session_name.assert_awaited_once_with("proj-a")

            # Consent revoked "at 14:00" -- no restart, no new job instance.
            project.llm_egress_consent = False
            sessions_repo.count_missing_session_name.reset_mock()

            second_tick = await job.execute(trigger="scheduled")

        sessions_repo.count_missing_session_name.assert_not_awaited()
        self.assertEqual(second_tick.candidates_found, 0)


class MissingReloadHookFailsClosedTests(unittest.IsolatedAsyncioTestCase):
    """hosted-llm-anthropic-ica-lane-v1 M2 security-review fix, step 2's

    DECISION: a ``workspace_registry`` that exposes NEITHER
    ``reload_projects()`` nor ``reload()`` cannot prove its
    ``list_projects()`` reads are fresh -- ``SessionNamingSweepJob`` treats
    every project's consent as UNCONFIRMED (fail-CLOSED) on ticks where the
    active naming backend is egress-shaped, rather than silently trusting a
    possibly-stale flag. See
    ``SessionNamingSweepJob._resolve_projects_to_sweep``'s own docstring for
    the full rationale.
    """

    async def test_no_reload_hook_skips_every_project_as_consent_unconfirmed(self) -> None:
        proj_a = types.SimpleNamespace(id="proj-a", llm_egress_consent=True)
        proj_b = types.SimpleNamespace(id="proj-b", llm_egress_consent=False)
        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(return_value=[]),
            count_missing_session_name=AsyncMock(return_value=0),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        # Deliberately NO ``reload_projects``/``reload`` attribute at all.
        workspace_registry = types.SimpleNamespace(list_projects=lambda: [proj_a, proj_b])
        ports = types.SimpleNamespace(storage=storage, workspace_registry=workspace_registry)
        backend = types.SimpleNamespace(
            EGRESS=True, model="fake-hosted-model", derive_name=AsyncMock(return_value="A name")
        )
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        # proj-a HAS consented, but freshness cannot be confirmed for this
        # registry -- it must still be skipped, same as proj-b.
        sessions_repo.count_missing_session_name.assert_not_awaited()
        self.assertTrue(result.success)
        self.assertEqual(result.candidates_found, 0)

    async def test_local_backend_is_unaffected_by_a_missing_reload_hook(self) -> None:
        """A non-egress backend never consults consent freshness either --

        same exemption as ``PerProjectEgressConsentTests``'s local-backend
        test, now also proven when the registry cannot be refreshed at all.
        """
        proj_a = types.SimpleNamespace(id="proj-a", llm_egress_consent=False)
        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(return_value=[{"id": "s1", "project_id": "proj-a"}]),
            count_missing_session_name=AsyncMock(return_value=1),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        workspace_registry = types.SimpleNamespace(list_projects=lambda: [proj_a])
        ports = types.SimpleNamespace(storage=storage, workspace_registry=workspace_registry)
        backend = types.SimpleNamespace(
            model="fake-local-model", derive_name=AsyncMock(return_value="A name")
        )  # no EGRESS attribute -- duck-typed default False

        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True):
            result = await job.execute(trigger="scheduled")

        sessions_repo.count_missing_session_name.assert_awaited_once_with("proj-a")
        self.assertEqual(result.candidates_found, 1)


class EgressAuditEventLaneTests(unittest.IsolatedAsyncioTestCase):
    """The per-tick egress AUDIT line must name the lane that was RESOLVED.

    hosted-llm-anthropic-ica-lane-v1 M3 (reviewer-gate fix): the event used
    to be built from the raw LEGACY ``CCDASH_SESSION_NAMING_BACKEND``
    attribute. An operator following the documented preference -- set the
    NEW ``CCDASH_LLM_SESSION_NAMING_LANE=anthropic`` and leave the legacy
    var alone -- therefore got ``lane="local"`` in an audit line emitted for
    a tick that was egressing to ICA. An egress audit line that names the
    wrong lane is worse than no line, so this class pins the VALUE (never
    the event's field names/shape, which are unchanged) against BOTH
    precedence directions of ``config.resolve_with_legacy_fallback``.
    """

    def _egress_ports_and_backend(self) -> tuple[object, object]:
        sessions_repo = types.SimpleNamespace(
            list_missing_session_name=AsyncMock(return_value=[{"id": "s1", "project_id": "proj-a"}]),
            count_missing_session_name=AsyncMock(return_value=1),
        )
        storage = types.SimpleNamespace(sessions=lambda: sessions_repo)
        project = types.SimpleNamespace(id="proj-a", llm_egress_consent=True)
        workspace_registry = types.SimpleNamespace(
            list_projects=lambda: [project], reload_projects=lambda: None
        )
        ports = types.SimpleNamespace(storage=storage, workspace_registry=workspace_registry)
        backend = types.SimpleNamespace(
            EGRESS=True,
            model="claude-sonnet-5",
            derive_name=AsyncMock(return_value="A name"),
        )
        return ports, backend

    async def test_event_reports_the_new_lane_var_when_only_it_is_set(self) -> None:
        """ONLY ``CCDASH_LLM_SESSION_NAMING_LANE=anthropic`` is set; the

        legacy ``CCDASH_SESSION_NAMING_BACKEND`` is unset -- i.e. it holds
        the ``"local"`` value ``config.py`` gives it when the env var is
        absent. The emitted event must record ``lane="anthropic"``: the lane
        the naming resolver actually resolved (and would have built the
        Anthropic/ICA backend from), never the legacy var's default.
        """
        ports, backend = self._egress_ports_and_backend()
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True), patch.object(
            config, "CCDASH_LLM_SESSION_NAMING_LANE", "anthropic"
        ), patch.object(
            # The legacy var's own default when its env var is absent -- this
            # is exactly what an operator who only set the new var has.
            config,
            "CCDASH_SESSION_NAMING_BACKEND",
            "local",
        ), patch(
            "backend.observability.otel.log_llm_egress_event"
        ) as log_event:
            await job.execute(trigger="scheduled")

        log_event.assert_called_once()
        _, kwargs = log_event.call_args
        self.assertEqual(kwargs.get("lane"), "anthropic")
        # Shape/field names unchanged -- only the lane VALUE was wrong.
        self.assertEqual(kwargs.get("model"), "claude-sonnet-5")
        self.assertEqual(kwargs.get("project_id"), "proj-a")

    async def test_event_still_reports_the_legacy_var_when_the_new_one_is_unset(self) -> None:
        """The other precedence direction, so the fix cannot over-correct

        into ignoring the legacy var: new var absent (empty string, its real
        default) + legacy ``CCDASH_SESSION_NAMING_BACKEND=hosted`` must
        still audit as ``lane="hosted"``.
        """
        ports, backend = self._egress_ports_and_backend()
        job = SessionNamingSweepJob(ports=ports, project=None, naming_backend=backend)

        with patch.object(config, "CCDASH_SESSION_NAMING_ENABLED", True), patch.object(
            config, "CCDASH_LLM_SESSION_NAMING_LANE", ""
        ), patch.object(config, "CCDASH_SESSION_NAMING_BACKEND", "hosted"), patch(
            "backend.observability.otel.log_llm_egress_event"
        ) as log_event:
            await job.execute(trigger="scheduled")

        log_event.assert_called_once()
        _, kwargs = log_event.call_args
        self.assertEqual(kwargs.get("lane"), "hosted")


if __name__ == "__main__":
    unittest.main()
