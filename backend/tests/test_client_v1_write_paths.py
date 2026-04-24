"""Verify that FastAPI/Starlette auto-decodes percent-encoded path parameters.

The frontend ``services/apiClient.ts`` encodes IDs with ``encodeURIComponent``
before interpolating them into URL paths (e.g. ``FEAT-123#draft`` →
``FEAT-123%23draft``).  FastAPI's path-parameter extraction should transparently
decode those back to the raw value before the handler receives it.

Routes under test (all in ``backend/routers/features.py``):
  PATCH /api/features/{feature_id}/status           → update_feature_status
  PATCH /api/features/{feature_id}/phases/{phase_id}/status   → update_phase_status
  PATCH /api/features/{feature_id}/phases/{phase_id}/tasks/{task_id}/status
                                                     → update_task_status

Strategy: bootstrap the test app (same pattern as test_client_v1_contract.py),
then issue PATCH requests with a percent-encoded path and intercept the call to
``_resolve_feature_alias_id`` to assert that the handler already received the
*decoded* string.  Because the mock raises immediately after capture, no
database or filesystem access is needed.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.runtime.bootstrap import build_runtime_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project():
    """Minimal active-project stub sufficient for handler preamble."""
    proj = MagicMock()
    proj.id = "proj-test"
    return proj


def _make_paths():
    """Return three dummy paths (sessions_dir, docs_dir, progress_dir)."""
    return ("/tmp/sessions", "/tmp/docs", "/tmp/progress")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestPercentEncodedPathParams(unittest.TestCase):
    """FastAPI auto-decodes percent-encoded path params before handler sees them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": cls._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        cls._env_patcher.start()

        cls._app = build_runtime_app("test")

        cls._std_patches = [
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.start",
                new_callable=lambda: lambda: AsyncMock(),
            ),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.stop",
                new_callable=lambda: lambda: AsyncMock(),
            ),
        ]
        for p in cls._std_patches:
            p.start()

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._std_patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Parametrized cases expressed as individual test methods
    # ------------------------------------------------------------------

    def _assert_decoded_feature_id(self, raw_id: str, encoded_url_segment: str) -> None:
        """PATCH /api/features/{encoded}/status — handler receives decoded ID."""
        captured: list[str] = []

        async def _fake_resolve(repo, project_id: str, feature_id: str) -> str:
            del repo, project_id
            captured.append(feature_id)
            raise RuntimeError("sentinel – abort handler after capture")

        proj = _make_project()
        proj_mgr = MagicMock()
        proj_mgr.get_active_project.return_value = proj
        proj_mgr.get_active_paths.return_value = _make_paths()

        with (
            patch("backend.routers.features.project_manager", proj_mgr),
            patch(
                "backend.routers.features._resolve_feature_alias_id",
                side_effect=_fake_resolve,
            ),
            patch(
                "backend.routers.features.connection.get_connection",
                new_callable=AsyncMock,
            ),
            patch("backend.routers.features.get_feature_repository", return_value=MagicMock()),
        ):
            url = f"/api/features/{encoded_url_segment}/status"
            self.client.patch(url, json={"status": "in_progress"})

        self.assertEqual(
            len(captured),
            1,
            f"_resolve_feature_alias_id was not called for {url!r}",
        )
        self.assertEqual(
            captured[0],
            raw_id,
            f"Expected decoded ID {raw_id!r}, got {captured[0]!r}",
        )

    def test_feature_status_plain_id(self) -> None:
        """Plain IDs (no special chars) pass through unchanged."""
        self._assert_decoded_feature_id("FEAT-123", "FEAT-123")

    def test_feature_status_hash_encoded(self) -> None:
        """FEAT-123#draft encoded as FEAT-123%23draft is decoded to FEAT-123#draft."""
        self._assert_decoded_feature_id("FEAT-123#draft", "FEAT-123%23draft")

    def test_feature_status_slash_encoded_returns_404(self) -> None:
        """%2F in a path segment is NOT decoded by Starlette — it yields a 404.

        Starlette (the ASGI layer under FastAPI) treats a decoded '/' as a path
        separator.  ``FEAT-123%2Fsub`` therefore hits a route that does not
        exist (``/api/features/FEAT-123/sub/status``), returning 404.

        Implication: feature IDs that contain literal '/' characters cannot be
        round-tripped through a URL path segment, even with ``encodeURIComponent``.
        The frontend should either avoid such IDs or send them via a request body
        / query parameter instead.
        """
        proj_mgr = MagicMock()
        proj_mgr.get_active_project.return_value = _make_project()
        proj_mgr.get_active_paths.return_value = _make_paths()

        with patch("backend.routers.features.project_manager", proj_mgr):
            response = self.client.patch(
                "/api/features/FEAT-123%2Fsub/status",
                json={"status": "in_progress"},
            )
        # 404 (or 422) — route not matched because decoded slash splits the path.
        self.assertIn(response.status_code, (404, 422))

    def _assert_decoded_phase_id(self, raw_feat: str, enc_feat: str, raw_phase: str, enc_phase: str) -> None:
        """PATCH /api/features/{feat}/phases/{phase}/status — both params decoded."""
        captured: list[tuple[str, str]] = []

        async def _fake_resolve(repo, project_id: str, feature_id: str) -> str:
            del repo, project_id
            # Record feature_id; we'll check phase separately via the exception path.
            captured.append(("feature", feature_id))
            # Return a value so the handler continues to use phase_id.
            return feature_id

        phase_captured: list[str] = []

        def _spy_resolve_phase(feature_id: str, phase_id: str, progress_dir: str):
            del feature_id, progress_dir
            phase_captured.append(phase_id)
            raise RuntimeError("sentinel – abort after phase_id capture")

        proj_mgr = MagicMock()
        proj_mgr.get_active_project.return_value = _make_project()
        proj_mgr.get_active_paths.return_value = _make_paths()

        with (
            patch("backend.routers.features.project_manager", proj_mgr),
            patch(
                "backend.routers.features._resolve_feature_alias_id",
                side_effect=_fake_resolve,
            ),
            patch(
                "backend.routers.features._require_feature_write_through_sync_engine",
                return_value=MagicMock(),
            ),
            patch(
                "backend.routers.features.connection.get_connection",
                new_callable=AsyncMock,
            ),
            patch("backend.routers.features.get_feature_repository", return_value=MagicMock()),
            patch(
                "backend.routers.features.resolve_file_for_phase",
                side_effect=_spy_resolve_phase,
            ),
        ):
            url = f"/api/features/{enc_feat}/phases/{enc_phase}/status"
            self.client.patch(url, json={"status": "completed"})

        # feature_id decoded
        self.assertTrue(captured, "feature resolver was never called")
        self.assertEqual(captured[0][1], raw_feat, f"feature_id: expected {raw_feat!r}, got {captured[0][1]!r}")

        # phase_id decoded
        self.assertTrue(phase_captured, "phase resolver was never called")
        self.assertEqual(phase_captured[0], raw_phase, f"phase_id: expected {raw_phase!r}, got {phase_captured[0]!r}")

    def test_phase_status_plain(self) -> None:
        self._assert_decoded_phase_id("FEAT-1", "FEAT-1", "3", "3")

    def test_phase_status_hash_encoded_feature(self) -> None:
        """Feature ID with # is decoded; plain phase number passes unchanged."""
        self._assert_decoded_phase_id("FEAT-1#beta", "FEAT-1%23beta", "2", "2")

    def test_task_status_hash_encoded_task_id(self) -> None:
        """Task ID with # encoded as %23 is decoded before the handler uses it.

        The task handler in ``update_task_status`` passes ``task_id`` directly
        to ``update_task_in_frontmatter``.  We intercept that call to capture
        the value FastAPI supplied to the handler.
        """
        raw_task = "T3-007#retry"
        enc_task = "T3-007%23retry"
        task_captured: list[str] = []

        async def _fake_resolve(repo, project_id: str, feature_id: str) -> str:
            del repo, project_id
            return feature_id

        def _spy_resolve_phase(feature_id: str, phase_id: str, progress_dir: str):
            del feature_id, phase_id, progress_dir
            return "/tmp/fake-phase.md"

        def _spy_update_task(file_path: str, task_id: str, *args, **kwargs):
            del file_path, args, kwargs
            task_captured.append(task_id)
            raise RuntimeError("sentinel – abort after task_id capture")

        proj_mgr = MagicMock()
        proj_mgr.get_active_project.return_value = _make_project()
        proj_mgr.get_active_paths.return_value = _make_paths()

        with (
            patch("backend.routers.features.project_manager", proj_mgr),
            patch(
                "backend.routers.features._resolve_feature_alias_id",
                side_effect=_fake_resolve,
            ),
            patch(
                "backend.routers.features._require_feature_write_through_sync_engine",
                return_value=MagicMock(),
            ),
            patch(
                "backend.routers.features.connection.get_connection",
                new_callable=AsyncMock,
            ),
            patch("backend.routers.features.get_feature_repository", return_value=MagicMock()),
            patch(
                "backend.routers.features.resolve_file_for_phase",
                side_effect=_spy_resolve_phase,
            ),
            patch(
                "backend.routers.features.update_task_in_frontmatter",
                side_effect=_spy_update_task,
            ),
        ):
            url = f"/api/features/FEAT-1/phases/3/tasks/{enc_task}/status"
            self.client.patch(url, json={"status": "completed"})

        self.assertTrue(task_captured, "update_task_in_frontmatter was never called")
        self.assertEqual(
            task_captured[0],
            raw_task,
            f"task_id: expected {raw_task!r}, got {task_captured[0]!r}",
        )


if __name__ == "__main__":
    unittest.main()
