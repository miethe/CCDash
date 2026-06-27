"""Tests for P5-010: POST /api/agent/planning/specs — spec document creation.

Run with:
    PYTHONPATH=/Users/miethe/dev/homelab/development/CCDash/.claude/worktrees/ee-phase-3fu-5-6 \
    /Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python \
    -m pytest backend/tests/test_p5_spec_create.py -p no:cacheprovider --no-header -q
"""
from __future__ import annotations

import importlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan_docs_dir() -> tuple[Path, object]:
    """Return (plan_docs_dir, tmp_context_manager) with auto-cleanup."""
    tmp = tempfile.TemporaryDirectory()
    return Path(tmp.name), tmp


# ---------------------------------------------------------------------------
# Unit tests: spec_create service
# ---------------------------------------------------------------------------


class TestCreateSpecDocument(unittest.TestCase):
    """Tests for backend.services.spec_create.create_spec_document."""

    def _call(self, plan_docs_dir: Path, title: str, doc_type: str = "design-spec", now=None):
        from backend.services.spec_create import create_spec_document
        return create_spec_document(plan_docs_dir, title, doc_type, now=now)

    # ── Happy-path ──────────────────────────────────────────────────────────

    def test_creates_file_with_correct_frontmatter(self):
        """A title creates a .md file under plan_docs_dir with YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp)
            result = self._call(plan_docs, "My New Spec")

        self.assertEqual(result["status"], "created")
        self.assertTrue(result["id"].startswith("DOC-"))
        self.assertTrue(result["path"].endswith(".md"))

    def test_file_is_written_to_disk(self):
        """The returned path corresponds to a real file on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp)
            result = self._call(plan_docs, "Auth Flow Design")
            target = plan_docs / result["path"]
            self.assertTrue(target.exists(), f"Expected file at {target}")
            content = target.read_text()
            self.assertIn("schema_version: 2", content)
            self.assertIn("doc_type: design-spec", content)
            self.assertIn("title: Auth Flow Design", content)
            self.assertIn("status: draft", content)
            self.assertIn("# Auth Flow Design", content)

    def test_doc_id_matches_sync_engine_convention(self):
        """id is 'DOC-<slug>-<uid>' matching make_document_id format."""
        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp)
            result = self._call(plan_docs, "Token Budget Strategy")
        # Should be DOC-<slug>-<6-char-uid>
        self.assertTrue(result["id"].startswith("DOC-token-budget-strategy-"))
        # uid suffix is 6 hex chars
        uid_part = result["id"].split("-")[-1]
        self.assertEqual(len(uid_part), 6)
        self.assertTrue(all(c in "0123456789abcdef" for c in uid_part))

    def test_timestamp_injected_correctly(self):
        """Frontmatter created: timestamp matches the injected now value."""
        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp)
            fixed_now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
            result = self._call(plan_docs, "Timestamp Test", now=fixed_now)
            content = (plan_docs / result["path"]).read_text()
            self.assertIn("created: 2026-06-01T12:00:00Z", content)

    def test_custom_doc_type(self):
        """Custom doc_type appears in frontmatter."""
        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp)
            result = self._call(plan_docs, "My PRD", doc_type="prd")
            content = (plan_docs / result["path"]).read_text()
            self.assertIn("doc_type: prd", content)

    def test_creates_plan_docs_dir_if_missing(self):
        """plan_docs_dir is created (mkdir parents=True) if it does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "docs" / "project_plans"
            # nested does NOT exist yet
            self.assertFalse(nested.exists())
            result = self._call(nested, "Nested Dir Test")
            self.assertTrue((nested / result["path"]).exists())

    # ── Path-traversal rejection ─────────────────────────────────────────────

    def test_traversal_in_title_is_safe(self):
        """Titles containing '../' do not produce a file outside plan_docs_dir.

        The slugifier strips non-alphanumeric chars, so '../evil' becomes
        'evil' and the resulting file lands safely inside plan_docs_dir.
        """
        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp)
            result = self._call(plan_docs, "../../../etc/passwd Injection")
            target = plan_docs / result["path"]
            # Must be inside plan_docs
            target.relative_to(plan_docs)  # raises if outside
            self.assertTrue(target.exists())

    def test_path_traversal_via_symlink_base_rejected(self):
        """Even if plan_docs_dir itself were malicious, the safety check fires.

        We test this by patching the result of resolve() to make the target
        appear outside plan_docs_dir.  The service raises ValueError.
        """
        from backend.services.spec_create import create_spec_document

        with tempfile.TemporaryDirectory() as tmp:
            plan_docs = Path(tmp) / "safe"
            plan_docs.mkdir()
            # Monkey-patch Path.resolve on the target to return an escaped path
            evil_path = Path("/tmp/evil_escape.md")

            orig_resolve = Path.resolve

            def patched_resolve(self, **kw):
                s = orig_resolve(self, **kw)
                # Only redirect if this looks like a file in plan_docs
                if s.parent == orig_resolve(plan_docs):
                    return evil_path
                return s

            with patch.object(Path, "resolve", patched_resolve):
                with self.assertRaises(ValueError, msg="Expected traversal rejection"):
                    create_spec_document(plan_docs, "Safe Title")

    # ── Validation errors ────────────────────────────────────────────────────

    def test_empty_title_raises(self):
        """Empty title raises ValueError."""
        from backend.services.spec_create import create_spec_document
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_spec_document(Path(tmp), "")

    def test_whitespace_only_title_raises(self):
        """Whitespace-only title raises ValueError."""
        from backend.services.spec_create import create_spec_document
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_spec_document(Path(tmp), "   ")

    def test_too_long_title_raises(self):
        """Title longer than 200 chars raises ValueError."""
        from backend.services.spec_create import create_spec_document
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_spec_document(Path(tmp), "x" * 201)

    def test_invalid_doc_type_raises(self):
        """doc_type with uppercase or spaces raises ValueError."""
        from backend.services.spec_create import create_spec_document
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_spec_document(Path(tmp), "Valid Title", doc_type="Design Spec")

    # ── Missing plan_docs path via HTTP route ─────────────────────────────────


# ---------------------------------------------------------------------------
# Unit tests: HTTP route via mocked dependencies
# ---------------------------------------------------------------------------


def _make_mock_bundle(plan_docs_dir: Path):
    """Return a mock ProjectBundle with plan_docs resolved to plan_docs_dir."""
    from backend.services.project_paths.models import ResolvedProjectPath, ResolvedProjectPaths

    plan_docs = MagicMock(spec=ResolvedProjectPath)
    plan_docs.path = plan_docs_dir

    paths = MagicMock(spec=ResolvedProjectPaths)
    paths.plan_docs = plan_docs

    project = MagicMock()
    project.id = "test-project-1"

    bundle = MagicMock()
    bundle.project = project
    bundle.paths = paths
    return bundle


class TestSpecCreateRoute(unittest.TestCase):
    """Integration-ish tests for the POST /api/agent/planning/specs route.

    We call the view function directly after injecting mock dependencies,
    avoiding httpx/TestClient startup overhead.
    """

    def _get_handler(self):
        from backend.routers.agent import post_planning_spec_create
        return post_planning_spec_create

    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)

    # ── Happy-path ──────────────────────────────────────────────────────────

    def test_happy_path_returns_created_response(self):
        """Valid request returns 201-ish SpecCreateResponse with id/path/status."""
        from backend.routers.agent import SpecCreateRequest

        with tempfile.TemporaryDirectory() as tmp:
            plan_docs_dir = Path(tmp)
            mock_bundle = _make_mock_bundle(plan_docs_dir)

            body = SpecCreateRequest(title="My Test Spec")
            mock_ctx = MagicMock()
            mock_ports = MagicMock()

            with patch(
                "backend.routers.agent.resolve_project_bundle",
                return_value=mock_bundle,
            ), patch(
                "backend.routers.agent.config",
                CCDASH_PLANNING_CONTROL_PLANE_ENABLED=True,
            ):
                result = self._run(
                    self._get_handler()(
                        body=body,
                        request_context=mock_ctx,
                        core_ports=mock_ports,
                    )
                )

            # Assertions inside the with-block so plan_docs_dir still exists
            self.assertEqual(result.status, "created")
            self.assertTrue(result.id.startswith("DOC-my-test-spec-"))
            self.assertTrue(result.path.endswith(".md"))
            # File should exist on disk
            self.assertTrue((plan_docs_dir / result.path).exists())

    # ── 422: no active project ───────────────────────────────────────────────

    def test_no_bundle_raises_422(self):
        """Returns 422 when no active project can be resolved."""
        from fastapi import HTTPException
        from backend.routers.agent import SpecCreateRequest

        body = SpecCreateRequest(title="Will Fail")
        mock_ctx = MagicMock()
        mock_ports = MagicMock()

        with patch(
            "backend.routers.agent.resolve_project_bundle",
            return_value=None,
        ), patch(
            "backend.routers.agent.config",
            CCDASH_PLANNING_CONTROL_PLANE_ENABLED=True,
        ):
            with self.assertRaises(HTTPException) as cm:
                self._run(
                    self._get_handler()(
                        body=body,
                        request_context=mock_ctx,
                        core_ports=mock_ports,
                    )
                )

        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("no_active_project", str(cm.exception.detail))

    # ── 422: no plan_docs path ───────────────────────────────────────────────

    def test_empty_plan_docs_path_raises_422(self):
        """Returns 422 when plan_docs.path resolves to empty/None."""
        from fastapi import HTTPException
        from backend.routers.agent import SpecCreateRequest

        mock_bundle = MagicMock()
        mock_bundle.project.id = "proj-x"
        mock_bundle.paths.plan_docs.path = None  # simulate no configured path

        body = SpecCreateRequest(title="Will Also Fail")
        mock_ctx = MagicMock()
        mock_ports = MagicMock()

        with patch(
            "backend.routers.agent.resolve_project_bundle",
            return_value=mock_bundle,
        ), patch(
            "backend.routers.agent.config",
            CCDASH_PLANNING_CONTROL_PLANE_ENABLED=True,
        ), patch(
            "backend.routers.agent.create_spec_document",
            side_effect=AssertionError("should not be called"),
        ):
            with self.assertRaises(HTTPException) as cm:
                self._run(
                    self._get_handler()(
                        body=body,
                        request_context=mock_ctx,
                        core_ports=mock_ports,
                    )
                )

        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("no_plan_docs_path", str(cm.exception.detail))

    # ── path-traversal title rejected at service level ───────────────────────

    def test_path_traversal_title_safe(self):
        """Titles with '../' are slugified safely — file lands inside plan_docs."""
        from backend.routers.agent import SpecCreateRequest

        with tempfile.TemporaryDirectory() as tmp:
            plan_docs_dir = Path(tmp)
            mock_bundle = _make_mock_bundle(plan_docs_dir)

            body = SpecCreateRequest(title="../../../etc/shadow Attack")
            mock_ctx = MagicMock()
            mock_ports = MagicMock()

            with patch(
                "backend.routers.agent.resolve_project_bundle",
                return_value=mock_bundle,
            ), patch(
                "backend.routers.agent.config",
                CCDASH_PLANNING_CONTROL_PLANE_ENABLED=True,
            ):
                result = self._run(
                    self._get_handler()(
                        body=body,
                        request_context=mock_ctx,
                        core_ports=mock_ports,
                    )
                )

            # File must be inside plan_docs_dir — assertions inside block
            target = plan_docs_dir / result.path
            target.relative_to(plan_docs_dir)  # raises ValueError if outside
            self.assertTrue(target.exists())


# ---------------------------------------------------------------------------
# Module import check
# ---------------------------------------------------------------------------


class TestModuleImports(unittest.TestCase):
    def test_spec_create_service_importable(self):
        mod = importlib.import_module("backend.services.spec_create")
        self.assertTrue(hasattr(mod, "create_spec_document"))
        self.assertTrue(hasattr(mod, "SpecCreateResult"))

    def test_agent_router_still_importable(self):
        mod = importlib.import_module("backend.routers.agent")
        self.assertTrue(hasattr(mod, "agent_router"))
        self.assertTrue(hasattr(mod, "post_planning_spec_create"))
        self.assertTrue(hasattr(mod, "SpecCreateRequest"))
        self.assertTrue(hasattr(mod, "SpecCreateResponse"))


if __name__ == "__main__":
    unittest.main()
