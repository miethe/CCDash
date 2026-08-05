"""automatic-session-naming (M1 / T1-003) — repository persistence + seam contract.

Covers the T1-003 half of FR-6/FR-8/FR-9/FR-11 that the parser-level
``test_session_naming.py`` and the pure-function ``test_session_name_provenance.py``
do not: the ``sessions.session_name`` / ``sessions.session_name_source`` pair
actually persists through the EXISTING ``SqliteSessionRepository.upsert``
INSERT/ON CONFLICT path (no new repository method was added), round-trips
null correctly, is COALESCE-protected against a transient re-ingest wipe, and
is present on the BE (``AgentSession``) / FE (``types.ts``) seam.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_name_persistence.py -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.db import migration_governance as gov
from backend.models import AgentSession
from backend.parsers.session_name_provenance import (
    SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
    SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
)

_NEW_COLUMNS = ("session_name", "session_name_source")
_REPO_ROOT = Path(__file__).resolve().parents[2]


# ── Dual-DDL column parity (already asserted for v50 by test_phase5_detection_
# columns.py's sibling suite; re-pinned here scoped to this feature's columns
# so this file is self-contained evidence for the "Dual DDL + parity" AC row) ──
class SessionNameColumnParityTests(unittest.TestCase):
    def test_sessions_table_is_parity_clean(self) -> None:
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
        """These columns are parity-clean, so they must NOT appear in the allowlist."""
        for col in _NEW_COLUMNS:
            self.assertNotIn(
                ("sessions", col),
                gov.COLUMN_PARITY_DRIFT_ALLOWLIST,
                msg=f"sessions.{col} should be parity-clean, not allowlisted",
            )


# ── Repo round-trip through the EXISTING upsert path (T1-003) ──────────────────
class SessionNameRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_session_name_persists_and_reads_back(self) -> None:
        await self.repo.upsert(
            {
                "id": "s1",
                "sessionName": "Fix the flaky retry test",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            "proj-a",
        )
        row = await self.repo.get_by_id("s1", project_id="proj-a")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["session_name"], "Fix the flaky retry test")
        self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    async def test_absent_session_name_round_trips_as_null_with_null_source(self) -> None:
        """A null session_name always carries a null source (module contract)."""
        await self.repo.upsert({"id": "s2"}, "proj-a")
        row = await self.repo.get_by_id("s2", project_id="proj-a")
        assert row is not None
        self.assertIsNone(row["session_name"])
        self.assertIsNone(row["session_name_source"])

    async def test_session_name_not_wiped_on_reingest_without_provider_name(self) -> None:
        """COALESCE guard: a re-parse that transiently misses ai-title/thread_name

        must not wipe a previously-captured session_name (same capture-once
        posture this repo already applies to cwd/worktree_name/context_window).
        """
        await self.repo.upsert(
            {
                "id": "s3",
                "sessionName": "Automatic session naming spike",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            "proj-a",
        )
        # Re-ingest with sessionName omitted (e.g. a partial re-parse pass).
        await self.repo.upsert({"id": "s3", "model": "claude-sonnet"}, "proj-a")
        row = await self.repo.get_by_id("s3", project_id="proj-a")
        assert row is not None
        self.assertEqual(row["session_name"], "Automatic session naming spike")
        self.assertEqual(row["session_name_source"], SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    async def test_direct_count_of_named_rows_matches_expected(self) -> None:
        """Direct-count assertion: query COUNT(*) rather than trust per-row .get().

        Three sessions ingested; only two carry a provider-persisted name. The
        COUNT(*) over ``session_name IS NOT NULL`` must equal exactly 2 — not
        3 (over-count, a write leaking onto the unnamed row) and not 0/1
        (under-count, the upsert silently dropping a value).
        """
        await self.repo.upsert(
            {
                "id": "s4",
                "sessionName": "Provider-named session A",
                "sessionNameSource": SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            },
            "proj-a",
        )
        await self.repo.upsert(
            {
                "id": "s5",
                "sessionName": "Deterministic-named session B",
                "sessionNameSource": SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
            },
            "proj-a",
        )
        await self.repo.upsert({"id": "s6"}, "proj-a")  # no name at all

        cursor = await self.db.execute(
            "SELECT COUNT(*) AS n FROM sessions "
            "WHERE project_id = ? AND session_name IS NOT NULL",
            ("proj-a",),
        )
        row = await cursor.fetchone()
        self.assertEqual(row["n"], 2)

        cursor = await self.db.execute(
            "SELECT COUNT(*) AS n FROM sessions "
            "WHERE project_id = ? AND session_name_source = ?",
            ("proj-a", SESSION_NAME_SOURCE_PROVIDER_PERSISTED),
        )
        row = await cursor.fetchone()
        self.assertEqual(row["n"], 1)

        cursor = await self.db.execute(
            "SELECT COUNT(*) AS n FROM sessions "
            "WHERE project_id = ? AND session_name IS NULL AND session_name_source IS NULL",
            ("proj-a",),
        )
        row = await cursor.fetchone()
        self.assertEqual(row["n"], 1)


# ── BE↔FE seam contract pin ─────────────────────────────────────────────────────
class SessionNameSeamContractTests(unittest.TestCase):
    def test_agent_session_model_declares_fields_with_null_default(self) -> None:
        s = AgentSession(id="x")
        dumped = s.model_dump()
        self.assertIn("sessionName", dumped)
        self.assertIn("sessionNameSource", dumped)
        self.assertIsNone(dumped["sessionName"])
        self.assertIsNone(dumped["sessionNameSource"])

    def test_agent_session_accepts_explicit_values(self) -> None:
        s = AgentSession(
            id="x",
            sessionName="A real title",
            sessionNameSource=SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
        )
        self.assertEqual(s.sessionName, "A real title")
        self.assertEqual(s.sessionNameSource, SESSION_NAME_SOURCE_PROVIDER_PERSISTED)

    def test_fe_types_declare_matching_optional_nullable_fields(self) -> None:
        """FE types.ts AgentSession declares the same fields, optional/nullable.

        Static text assertion; tsc is the compile gate.
        """
        types_src = (_REPO_ROOT / "types.ts").read_text(encoding="utf-8")
        for field in ("sessionName", "sessionNameSource"):
            self.assertIn(field, types_src, msg=f"types.ts missing field {field}")
            self.assertRegex(types_src, rf"{field}\?:\s*string\s*\|\s*null")


if __name__ == "__main__":
    unittest.main()
