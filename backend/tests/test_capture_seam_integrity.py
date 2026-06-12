"""Phase 11 (T11-006): seam-integrity test for the full launch-time-capture chain.

Proves NO field is dropped across:
  capture sidecar → parser → DB columns (snake_case) → session-detail surface (camelCase)

AND that a null/absent sidecar surfaces cleanly (all four null, no crash).

Cases:
  1. POPULATED round-trip  — all four fields non-null; asserted at both the DB
     column boundary (snake_case) AND the detail surface (camelCase).
  2. NULL/ABSENT sidecar   — all four fields are None in the detail bundle; no
     KeyError, no omit-then-crash, no exception.
  3. PARTIAL sidecar       — only ``profile`` set; profile populated, the
     remaining three are None with no defaulting.

Run as a NAMED file:
    backend/.venv/bin/python -m pytest \\
        backend/tests/test_capture_seam_integrity.py -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.services.agent_queries.session_detail import (
    SessionDetailBundle,
    get_session_detail,
)
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.parsers.sessions import parse_session_file


# ── Fixtures ──────────────────────────────────────────────────────────────────

# The Claude Code parser normalises the JSONL filename stem to "S-<stem>".
# _STEM is the raw filename stem (also the value the sidecar's sessionId field
# must carry, because the parser checks sidecar.session_id != raw_session_id).
# _SESSION_ID is the normalised form that ends up in the DB and must be used
# for all DB / detail-service lookups.
_STEM = "seam-test-capture-001"
_SESSION_ID = f"S-{_STEM}"                 # "S-seam-test-capture-001"
_PROJECT_ID = "proj-seam-integrity-test"

_MINIMAL_JSONL_ENTRY = {
    "type": "assistant",
    "timestamp": "2026-06-11T10:00:00Z",
    "uuid": "msg-seam-001",
    "parentUuid": None,
    "message": {
        "role": "assistant",
        "model": "claude-opus-4-5",
        "usage": {"input_tokens": 12, "output_tokens": 6},
        "content": [{"type": "text", "text": "seam integrity test"}],
    },
}

# All four fields populated (effortTier='high', not null — exercises the full path).
# sidecar.sessionId must be the raw stem, not the normalised "S-…" form.
_FULL_SIDECAR = {
    "schemaVersion": 1,
    "sessionId": _STEM,
    "launcher": "ica-claude.sh",
    "profile": "ica-delegate",
    "effortTier": "high",
    "modelVariant": "claude-opus-4-8[1m]",
    "capturedAt": "2026-06-11T10:00:00Z",
}

# Only profile set — exercises the partial-sidecar / no-defaulting contract
_PARTIAL_SIDECAR = {
    "schemaVersion": 1,
    "sessionId": _STEM,
    "profile": "ica-delegate",
    # launcher / effortTier / modelVariant deliberately absent
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_jsonl(directory: Path, stem: str, entries: list[dict]) -> Path:
    path = directory / f"{stem}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return path


def _write_json(directory: Path, name: str, content: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


class _FakePorts:
    """Minimal CorePorts-compatible object backed by an in-memory SQLite DB."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


# ── Shared async test base ────────────────────────────────────────────────────

class _SeamBase(unittest.IsolatedAsyncioTestCase):
    """Spin up a real in-memory SQLite DB for each test class."""

    async def asyncSetUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.workdir = Path(self._td.name)

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.session_repo = SqliteSessionRepository(self.db)
        self.ports = _FakePorts(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._td.cleanup()

    async def _parse_and_persist(self, jsonl_path: Path) -> None:
        """Parse JSONL (+ co-located sidecar if present) and upsert to DB."""
        session = parse_session_file(jsonl_path)
        self.assertIsNotNone(session, "parse_session_file returned None — fixture broken")
        session_data = session.model_dump()
        await self.session_repo.upsert(session_data, _PROJECT_ID)
        await self.db.commit()

    async def _get_detail(self) -> SessionDetailBundle:
        """Call get_session_detail with a mocked transcript service."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            bundle = await get_session_detail(_PROJECT_ID, _SESSION_ID, self.ports)
        self.assertIsNotNone(bundle, "get_session_detail returned None for existing session")
        return bundle  # type: ignore[return-value]


# ══════════════════════════════════════════════════════════════════════════════
# Case 1: POPULATED round-trip — all four fields set
# ══════════════════════════════════════════════════════════════════════════════

class TestCaptureSeamIntegrityPopulated(_SeamBase):
    """All four capture fields are non-null — no field must be dropped anywhere."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        jsonl = _write_jsonl(self.workdir, _STEM, [_MINIMAL_JSONL_ENTRY])
        _write_json(self.workdir, f"{_STEM}.capture.json", _FULL_SIDECAR)
        await self._parse_and_persist(jsonl)

    # ── DB boundary: snake_case columns ───────────────────────────────────────

    async def test_db_column_launcher_stored(self) -> None:
        """DB column 'launcher' retains its value after parse+upsert."""
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["launcher"], "ica-claude.sh",
                         "launcher dropped between parser and DB write")

    async def test_db_column_profile_stored(self) -> None:
        """DB column 'profile' retains its value after parse+upsert."""
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["profile"], "ica-delegate",
                         "profile dropped between parser and DB write")

    async def test_db_column_effort_tier_stored(self) -> None:
        """DB column 'effort_tier' (snake_case) retains its value after parse+upsert.

        This guards the camelCase→snake_case mapping in the repository (the repo
        reads session_data.get('effortTier') and writes to effort_tier).
        """
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["effort_tier"], "high",
                         "effort_tier dropped — camelCase→snake_case mapping broken in repo")

    async def test_db_column_model_variant_stored(self) -> None:
        """DB column 'model_variant' (snake_case) retains its value after parse+upsert.

        This guards the camelCase→snake_case mapping in the repository (the repo
        reads session_data.get('modelVariant') and writes to model_variant).
        """
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["model_variant"], "claude-opus-4-8[1m]",
                         "model_variant dropped — camelCase→snake_case mapping broken in repo")

    # ── Detail surface: camelCase contract ────────────────────────────────────

    async def test_detail_launcher_exact_value(self) -> None:
        """bundle.session['launcher'] carries the exact value end-to-end."""
        bundle = await self._get_detail()
        self.assertIn("launcher", bundle.session,
                      "launcher key missing from detail surface")
        self.assertEqual(bundle.session["launcher"], "ica-claude.sh")

    async def test_detail_profile_exact_value(self) -> None:
        """bundle.session['profile'] carries the exact value end-to-end."""
        bundle = await self._get_detail()
        self.assertIn("profile", bundle.session,
                      "profile key missing from detail surface")
        self.assertEqual(bundle.session["profile"], "ica-delegate")

    async def test_detail_effortTier_camel_exact_value(self) -> None:
        """bundle.session['effortTier'] (camelCase) carries the exact value.

        This is the critical snake→camel conversion: DB column 'effort_tier'
        must arrive as 'effortTier' on the FE-facing detail surface.
        A missing key here is a full field-drop, not a naming style issue.
        """
        bundle = await self._get_detail()
        self.assertIn(
            "effortTier", bundle.session,
            "effortTier (camelCase) absent from detail surface — snake→camel "
            "conversion broken in _apply_launch_capture",
        )
        self.assertEqual(bundle.session["effortTier"], "high",
                         "effortTier value dropped between DB and detail surface")

    async def test_detail_modelVariant_camel_exact_value(self) -> None:
        """bundle.session['modelVariant'] (camelCase) carries the exact value.

        DB column 'model_variant' must arrive as 'modelVariant' on the FE-facing
        detail surface.
        """
        bundle = await self._get_detail()
        self.assertIn(
            "modelVariant", bundle.session,
            "modelVariant (camelCase) absent from detail surface — snake→camel "
            "conversion broken in _apply_launch_capture",
        )
        self.assertEqual(bundle.session["modelVariant"], "claude-opus-4-8[1m]",
                         "modelVariant value dropped between DB and detail surface")

    async def test_all_four_camel_keys_present_simultaneously(self) -> None:
        """Single assertion covering all four camelCase keys at once (full no-drop proof)."""
        bundle = await self._get_detail()
        s = bundle.session
        expected = {
            "launcher": "ica-claude.sh",
            "profile": "ica-delegate",
            "effortTier": "high",
            "modelVariant": "claude-opus-4-8[1m]",
        }
        for key, val in expected.items():
            with self.subTest(key=key):
                self.assertIn(key, s, f"'{key}' missing from detail surface")
                self.assertEqual(s[key], val, f"'{key}' has wrong value in detail surface")


# ══════════════════════════════════════════════════════════════════════════════
# Case 2: NULL/ABSENT sidecar
# ══════════════════════════════════════════════════════════════════════════════

class TestCaptureSeamIntegrityNullSidecar(_SeamBase):
    """No sidecar file: all four fields must be None in the detail bundle — no crash."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        jsonl = _write_jsonl(self.workdir, _STEM, [_MINIMAL_JSONL_ENTRY])
        # Intentionally no .capture.json written
        await self._parse_and_persist(jsonl)

    async def test_no_exception_on_null_sidecar(self) -> None:
        """Round-trip with no sidecar completes without raising."""
        # _get_detail() raises on any exception; success here IS the assertion
        bundle = await self._get_detail()
        self.assertIsNotNone(bundle)

    async def test_db_columns_null_when_no_sidecar(self) -> None:
        """DB columns are None when no sidecar was present (contract state, not a bug)."""
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertIsNone(row.get("launcher"),      "launcher should be None in DB")
        self.assertIsNone(row.get("profile"),       "profile should be None in DB")
        self.assertIsNone(row.get("effort_tier"),   "effort_tier should be None in DB")
        self.assertIsNone(row.get("model_variant"), "model_variant should be None in DB")

    async def test_detail_launcher_none_not_missing(self) -> None:
        """'launcher' key is present with None value (key absent would KeyError on get())."""
        bundle = await self._get_detail()
        self.assertIn("launcher", bundle.session,
                      "launcher key missing entirely — should be present with None value")
        self.assertIsNone(bundle.session["launcher"])

    async def test_detail_profile_none_not_missing(self) -> None:
        bundle = await self._get_detail()
        self.assertIn("profile", bundle.session,
                      "profile key missing entirely — should be present with None value")
        self.assertIsNone(bundle.session["profile"])

    async def test_detail_effortTier_none_not_missing(self) -> None:
        """effortTier key is present with None — not omitted (omit-then-KeyError guard)."""
        bundle = await self._get_detail()
        self.assertIn("effortTier", bundle.session,
                      "effortTier key missing entirely — should be present with None value; "
                      "missing == potential KeyError in FE consumers")
        self.assertIsNone(bundle.session["effortTier"])

    async def test_detail_modelVariant_none_not_missing(self) -> None:
        bundle = await self._get_detail()
        self.assertIn("modelVariant", bundle.session,
                      "modelVariant key missing entirely — should be present with None value")
        self.assertIsNone(bundle.session["modelVariant"])

    async def test_all_four_null_together(self) -> None:
        """Omnibus: all four camelCase keys present, all None, no crash."""
        bundle = await self._get_detail()
        s = bundle.session
        for key in ("launcher", "profile", "effortTier", "modelVariant"):
            with self.subTest(key=key):
                self.assertIn(key, s, f"'{key}' missing from null-sidecar detail surface")
                self.assertIsNone(s[key], f"'{key}' should be None when no sidecar present")


# ══════════════════════════════════════════════════════════════════════════════
# Case 3: PARTIAL sidecar — only profile set
# ══════════════════════════════════════════════════════════════════════════════

class TestCaptureSeamIntegrityPartialSidecar(_SeamBase):
    """Only profile set → profile populated, other three None (no defaulting)."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        jsonl = _write_jsonl(self.workdir, _STEM, [_MINIMAL_JSONL_ENTRY])
        _write_json(self.workdir, f"{_STEM}.capture.json", _PARTIAL_SIDECAR)
        await self._parse_and_persist(jsonl)

    async def test_db_profile_stored_on_partial_sidecar(self) -> None:
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertEqual(row["profile"], "ica-delegate")

    async def test_db_effort_tier_null_on_partial_sidecar(self) -> None:
        """Absent effortTier in sidecar → DB column effort_tier is None (no defaulting)."""
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertIsNone(row.get("effort_tier"),
                          "effort_tier should be None when absent from sidecar — defaulting detected")

    async def test_db_model_variant_null_on_partial_sidecar(self) -> None:
        row = await self.session_repo.get_by_id(_SESSION_ID, _PROJECT_ID)
        self.assertIsNotNone(row)
        self.assertIsNone(row.get("model_variant"))

    async def test_detail_profile_populated_partial(self) -> None:
        bundle = await self._get_detail()
        self.assertEqual(bundle.session.get("profile"), "ica-delegate")

    async def test_detail_launcher_null_partial(self) -> None:
        bundle = await self._get_detail()
        self.assertIn("launcher", bundle.session)
        self.assertIsNone(bundle.session["launcher"])

    async def test_detail_effortTier_null_no_default_partial(self) -> None:
        """Absent effortTier in sidecar → None in detail surface, not some default."""
        bundle = await self._get_detail()
        self.assertIn("effortTier", bundle.session)
        self.assertIsNone(bundle.session["effortTier"],
                          "effortTier was defaulted instead of remaining None")

    async def test_detail_modelVariant_null_no_default_partial(self) -> None:
        bundle = await self._get_detail()
        self.assertIn("modelVariant", bundle.session)
        self.assertIsNone(bundle.session["modelVariant"],
                          "modelVariant was defaulted instead of remaining None")


if __name__ == "__main__":
    unittest.main()
