"""Regression guard for node_01M20SZBBX00X4W618A90TSYMY.

Incident (2026-09-08): RuntimeContainer.startup() called
self._resolve_startup_project_binding() -- which can reach
_resolve_watcher_fan_out_bindings() -> workspace_registry.list_projects(), a
live schema-dependent query -- BEFORE migrations.run_migrations(self.db).
A pending additive migration (the v57 parent_project_id column) therefore
crash-looped worker-watch startup with psycopg2.errors.UndefinedColumn even
though run_migrations() would have added the column cleanly.

CRITICAL (per test_p3_worker_bootstrap.py's own note): do NOT call the full
RuntimeContainer.startup() in tests -- it triggers real DB connections and
hangs in worktree environments. This test exercises the exact ordered
sequence startup() now runs (get_connection -> run_migrations ->
_resolve_startup_project_binding) directly, with the DB connection and the
workspace registry both faked, so the ordering fix is verified without any
live DB/FastAPI/app machinery.
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from backend import config
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile


class MigrationsRunBeforeProjectBindingResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_binding_resolution_does_not_crash_on_a_db_missing_a_pending_additive_column(self) -> None:
        """A fresh worker-watch startup against a DB missing a newly-added
        additive column must not crash-loop: run_migrations() must add the
        column before the schema-dependent list_projects() call runs.
        """
        container = RuntimeContainer(profile=get_runtime_profile("worker"))

        # Fake DB: starts without the pending additive column applied.
        fake_db = types.SimpleNamespace(parent_project_id_column_present=False)
        call_order: list[str] = []

        async def fake_get_connection():
            return fake_db

        async def fake_run_migrations(db):
            call_order.append("migrations")
            # Simulates the additive migration landing (e.g. v57
            # parent_project_id) -- idempotent, like the real _ensure_column.
            db.parent_project_id_column_present = True

        registry_stub = MagicMock()

        def fake_list_projects():
            call_order.append("list_projects")
            if not fake_db.parent_project_id_column_present:
                # This is the exact failure mode from the incident: a
                # schema-dependent query hitting a column that a pending
                # migration would have added.
                raise RuntimeError(
                    "UndefinedColumn: column \"parent_project_id\" does not exist"
                )
            return []

        registry_stub.list_projects.side_effect = fake_list_projects
        registry_stub.resolve_project_binding.return_value = MagicMock()

        with patch(
            "backend.runtime.container.connection.get_connection",
            fake_get_connection,
        ), patch(
            "backend.runtime.container.migrations.run_migrations",
            fake_run_migrations,
        ), patch(
            "backend.runtime.container.build_workspace_registry",
            return_value=registry_stub,
        ), patch.dict(
            __import__("os").environ,
            {config.CCDASH_WORKER_PROJECT_ID_ENV: "proj-x"},
        ):
            # Exercise the exact ordered sequence startup() now runs.
            container.db = await fake_get_connection()
            from backend.db import migrations as migrations_module

            await migrations_module.run_migrations(container.db)
            container.migration_status = "applied"

            # Must not raise: migrations already ran, so the schema-dependent
            # query below sees the column.
            (
                container.project_binding,
                container.watcher_fan_out_bindings,
            ) = container._resolve_startup_project_binding()

        self.assertEqual(
            call_order,
            ["migrations", "list_projects"],
            "migrations.run_migrations() must run before the schema-dependent "
            "list_projects() call inside _resolve_startup_project_binding()",
        )
        self.assertTrue(fake_db.parent_project_id_column_present)

    def test_startup_source_runs_migrations_before_binding_resolution(self) -> None:
        """Structural guard: startup()'s source must call run_migrations()
        before _resolve_startup_project_binding(), so a future edit that
        reorders them again is caught even without exercising the DB path.
        """
        import inspect

        source_lines = [
            line
            for line in inspect.getsource(RuntimeContainer.startup).splitlines()
            if not line.lstrip().startswith("#")
        ]
        migrations_idx = next(
            i for i, line in enumerate(source_lines) if "await migrations.run_migrations(" in line
        )
        binding_idx = next(
            i
            for i, line in enumerate(source_lines)
            if "self._resolve_startup_project_binding()" in line
        )
        self.assertLess(
            migrations_idx,
            binding_idx,
            "migrations.run_migrations() must appear before "
            "_resolve_startup_project_binding() in RuntimeContainer.startup()",
        )


if __name__ == "__main__":
    unittest.main()
