"""End-to-end test for the offline CLI bootstrap + scoped sync path.

Exercises ``backend.cli.offline.bootstrap_offline`` + ``ensure_synced`` against
a real on-disk temp project (raw ``*.jsonl`` session logs + ``projects.json``)
with the real ``aiosqlite`` cache DB and migrations.  No mocks for the sync
engine — this is the actual offline read-only ingest the CLI runs when
``--offline`` is set on ``backend.cli.main``.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_cli_offline_sync.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from backend.cli import offline
from backend.db import connection


def _user_entry(uuid: str, content: str, ts: str) -> dict[str, Any]:
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": uuid,
        "message": {"role": "user", "content": content},
    }


def _assistant_entry(
    uuid: str, parent_uuid: str, text: str, ts: str
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": ts,
        "uuid": uuid,
        "parentUuid": parent_uuid,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet",
            "content": [{"type": "text", "text": text}],
        },
    }


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _build_temp_workspace(tmp_root: Path) -> tuple[Path, Path, str]:
    """Build a project tree + projects.json registry under ``tmp_root``.

    Layout::
        <tmp_root>/
            registry/projects.json
            project/
                sessions/<id>.jsonl
                docs/
                progress/

    Returns ``(project_root, projects_json_path, project_id)``.
    """
    project_root = tmp_root / "project"
    sessions_dir = project_root / "sessions"
    docs_dir = project_root / "docs"
    progress_dir = project_root / "progress"
    for directory in (sessions_dir, docs_dir, progress_dir):
        directory.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        sessions_dir / "alpha.jsonl",
        [
            _user_entry("u-alpha-1", "Plan the work", "2026-05-02T10:00:00Z"),
            _assistant_entry(
                "a-alpha-1",
                "u-alpha-1",
                "Working on it",
                "2026-05-02T10:00:01Z",
            ),
        ],
    )
    _write_jsonl(
        sessions_dir / "beta.jsonl",
        [
            _user_entry("u-beta-1", "Second session", "2026-05-02T11:00:00Z"),
        ],
    )

    project_id = "offline-proj-1"
    registry = {
        "activeProjectId": project_id,
        "projects": [
            {
                "id": project_id,
                "name": "Offline Proj 1",
                "path": str(project_root),
                "pathConfig": {
                    "root": {
                        "field": "root",
                        "sourceKind": "filesystem",
                        "filesystemPath": str(project_root),
                    },
                    "planDocs": {
                        "field": "plan_docs",
                        "sourceKind": "project_root",
                        "relativePath": "docs",
                    },
                    "sessions": {
                        "field": "sessions",
                        "sourceKind": "filesystem",
                        "filesystemPath": str(sessions_dir),
                    },
                    "progress": {
                        "field": "progress",
                        "sourceKind": "project_root",
                        "relativePath": "progress",
                    },
                },
            }
        ],
    }

    registry_dir = tmp_root / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    projects_json = registry_dir / "projects.json"
    projects_json.write_text(json.dumps(registry), encoding="utf-8")
    return project_root, projects_json, project_id


def _snapshot_tree(root: Path) -> dict[str, tuple[int, float]]:
    """Capture (size, mtime) for every file under ``root``.

    Used to assert the offline path never mutates the project repo.
    """
    snapshot: dict[str, tuple[int, float]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            snapshot[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime)
    return snapshot


class CliOfflineSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # Defensive: ensure no stale offline state leaks between tests.
        offline._offline_container = None
        offline._offline_manager = None
        offline._ephemeral_db_path = None
        self._original_db_path = connection.DB_PATH

    async def asyncTearDown(self) -> None:
        # Always tear down the offline runtime and restore the DB_PATH global so
        # later tests in the suite see the production default.
        try:
            await offline.shutdown_offline()
        except Exception:  # pragma: no cover - defensive cleanup
            pass
        connection.DB_PATH = self._original_db_path

    async def _count_sessions(self, db, project_id: str) -> int:
        async with db.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def test_offline_sync_seeds_db_from_local_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            _, projects_json, project_id = _build_temp_workspace(tmp_root)

            container = await offline.bootstrap_offline(
                ephemeral=True,
                config_path=str(projects_json),
            )
            manager = offline.get_offline_manager()

            stats = await offline.ensure_synced(
                manager,
                container.db,
                project_id=project_id,
                refresh=False,
            )

            self.assertGreater(
                int(stats.get("sessions_synced", 0)),
                0,
                f"Expected at least one session synced; got stats={stats!r}",
            )
            self.assertGreaterEqual(
                await self._count_sessions(container.db, project_id),
                1,
                "Expected sessions table to contain at least one row after offline sync.",
            )

    async def test_offline_sync_is_idempotent_for_unchanged_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            _, projects_json, project_id = _build_temp_workspace(tmp_root)

            container = await offline.bootstrap_offline(
                ephemeral=True,
                config_path=str(projects_json),
            )
            manager = offline.get_offline_manager()

            first = await offline.ensure_synced(
                manager,
                container.db,
                project_id=project_id,
                refresh=False,
            )
            self.assertGreater(int(first.get("sessions_synced", 0)), 0)

            second = await offline.ensure_synced(
                manager,
                container.db,
                project_id=project_id,
                refresh=False,
            )

            # Idempotency: nothing new parsed, files routed through the skip path.
            self.assertEqual(
                int(second.get("sessions_synced", 0)),
                0,
                f"Second offline sync re-parsed unchanged files; stats={second!r}",
            )
            self.assertGreater(
                int(second.get("sessions_skipped", 0)),
                0,
                f"Expected sessions_skipped > 0 on idempotent re-run; stats={second!r}",
            )

    async def test_offline_sync_does_not_mutate_project_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            project_root, projects_json, project_id = _build_temp_workspace(tmp_root)

            before = _snapshot_tree(project_root)

            container = await offline.bootstrap_offline(
                ephemeral=True,
                config_path=str(projects_json),
            )
            manager = offline.get_offline_manager()
            await offline.ensure_synced(
                manager,
                container.db,
                project_id=project_id,
                refresh=False,
            )

            after = _snapshot_tree(project_root)

            self.assertEqual(
                before,
                after,
                "Offline sync mutated the project repo (allow_writeback=False contract violated).",
            )


if __name__ == "__main__":
    unittest.main()
