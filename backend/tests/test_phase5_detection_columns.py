"""Phase 5 detection columns — persistence, parity, and BE↔FE seam.

Covers:
  * AC-5.3 — new detection columns are parity-clean across SQLite + Postgres
    (static DDL parse; live-PG e2e is Phase 9's hard gate). Allowlist-aware.
  * AC-5.5 / T5-009 — repo→model round-trip: detection columns persist and read
    back; a null skill_name round-trips as null (not '' / 'null'). The BE
    response model (AgentSession) and FE types.ts agree on names + nullability.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_phase5_detection_columns.py -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.db import migration_governance as gov
from backend.models import AgentSession

_NEW_COLUMNS = ("model_slug", "workflow_id", "subagent_parent_id", "skill_name", "context_window")
_REPO_ROOT = Path(__file__).resolve().parents[2]


# ── AC-5.3: dual-DDL column parity (static; live PG deferred to Phase 9) ────────
class DetectionColumnParityTests(unittest.TestCase):
    def test_sessions_table_is_parity_clean(self) -> None:
        """No drift on the sessions table after adding the detection columns."""
        self.assertEqual(gov.column_parity_diff("sessions"), {})

    def test_new_columns_present_on_both_backends(self) -> None:
        sqlite_blocks = gov._backend_table_blocks(gov.sqlite_migrations)
        postgres_blocks = gov._backend_table_blocks(gov.postgres_migrations)
        sqlite_cols = set(gov._parse_table_columns(sqlite_blocks["sessions"]))
        postgres_cols = set(gov._parse_table_columns(postgres_blocks["sessions"]))
        for col in _NEW_COLUMNS:
            self.assertIn(col, sqlite_cols, msg=f"{col} missing from SQLite sessions DDL")
            self.assertIn(col, postgres_cols, msg=f"{col} missing from Postgres sessions DDL")

    def test_new_columns_not_allowlisted(self) -> None:
        """Detection columns are parity-clean, so they must NOT appear in the allowlist."""
        for col in _NEW_COLUMNS:
            self.assertNotIn(
                ("sessions", col),
                gov.COLUMN_PARITY_DRIFT_ALLOWLIST,
                msg=f"sessions.{col} should be parity-clean, not allowlisted",
            )


# ── AC-5.5: repo→model round-trip (SQLite); live PG e2e is Phase 9's gate ───────
class DetectionColumnRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_detection_columns_persist_and_read_back(self) -> None:
        await self.repo.upsert(
            {
                "id": "s1",
                "modelSlug": "claude-opus-4-8",
                "workflowId": "wf-1",
                "subagentParentId": "parent-1",
                "skillName": "planning",
                "contextWindow": "1M",
            },
            "proj-a",
        )
        row = await self.repo.get_by_id("s1", project_id="proj-a")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["model_slug"], "claude-opus-4-8")
        self.assertEqual(row["workflow_id"], "wf-1")
        self.assertEqual(row["subagent_parent_id"], "parent-1")
        self.assertEqual(row["skill_name"], "planning")
        self.assertEqual(row["context_window"], "1M")

    async def test_absent_skill_and_context_round_trip_as_null(self) -> None:
        """Absent detection facts are null in the DB — never '' or the string 'null'."""
        await self.repo.upsert({"id": "s2"}, "proj-a")
        row = await self.repo.get_by_id("s2", project_id="proj-a")
        assert row is not None
        self.assertIsNone(row["workflow_id"])
        self.assertIsNone(row["subagent_parent_id"])
        self.assertIsNone(row["skill_name"])
        self.assertIsNone(row["context_window"])
        # model_slug is a string contract column → defaults to '' (not null).
        self.assertEqual(row["model_slug"], "")

    async def test_context_window_not_wiped_on_reingest_without_sidecar(self) -> None:
        """COALESCE guard: a re-ingest with a null context_window keeps the prior value."""
        await self.repo.upsert({"id": "s3", "contextWindow": "1M"}, "proj-a")
        # Re-ingest (e.g. sidecar transiently absent) with contextWindow omitted.
        await self.repo.upsert({"id": "s3", "model": "claude-sonnet"}, "proj-a")
        row = await self.repo.get_by_id("s3", project_id="proj-a")
        assert row is not None
        self.assertEqual(row["context_window"], "1M")


# ── AC-5.5 / T5-009: BE↔FE seam contract pin ───────────────────────────────────
class DetectionSeamContractTests(unittest.TestCase):
    def test_agent_session_model_defaults_encode_nulls(self) -> None:
        s = AgentSession(id="x")
        dumped = s.model_dump()
        # All five fields exist on the response model.
        for field in ("modelSlug", "workflowId", "subagentParentId", "skillName", "contextWindow"):
            self.assertIn(field, dumped)
        # Null encoding: nullable detection facts default to None; modelSlug to "".
        self.assertEqual(dumped["modelSlug"], "")
        self.assertIsNone(dumped["workflowId"])
        self.assertIsNone(dumped["subagentParentId"])
        self.assertIsNone(dumped["skillName"])
        self.assertIsNone(dumped["contextWindow"])

    def test_agent_session_accepts_explicit_nulls(self) -> None:
        """Omitting/None-ing any detection field is a valid response, not a parse error."""
        s = AgentSession(
            id="x",
            workflowId=None,
            subagentParentId=None,
            skillName=None,
            contextWindow=None,
        )
        self.assertEqual(s.id, "x")

    def test_fe_types_declare_matching_optional_fields(self) -> None:
        """FE types.ts AgentSession declares the same fields, optional/nullable.

        Pins the FE side of the seam: field names + nullability annotations match
        the BE response model. (Static text assertion; tsc is the compile gate.)
        """
        types_src = (_REPO_ROOT / "types.ts").read_text(encoding="utf-8")
        # camelCase names present.
        for field in ("modelSlug", "workflowId", "subagentParentId", "skillName", "contextWindow"):
            self.assertIn(field, types_src, msg=f"types.ts missing detection field {field}")
        # Nullable detection facts are declared `string | null`.
        for field in ("workflowId", "subagentParentId", "skillName", "contextWindow"):
            self.assertRegex(
                types_src, rf"{field}\?:\s*string\s*\|\s*null"
            )


if __name__ == "__main__":
    unittest.main()
