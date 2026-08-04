"""subagent-skill-inheritance — ``sessions.skill_name_source`` provenance column.

Mirrors ``test_effort_tier_source_provenance.py`` (the Gap 4 / schema v44
precedent) shape-for-shape. Covers:

1. **Dual DDL parity** — the column exists in BOTH the SQLite and Postgres
   ``CREATE TABLE sessions`` blocks and is NOT allowlisted as drift.
2. **Vocabulary** — tokens are unique/closed and deliberately reuse
   ``effort_provenance.EFFORT_SOURCE_INHERITED_PARENT``'s spelling (see
   ``skill_provenance.py`` module docstring for the rationale).
3. **Write-path invariant** — direct detection stamps ``directly_detected``;
   a null ``skill_name`` always carries a null ``source``.
4. **Backfill correctness** (direct-count assertions, per ADR-007):
   - AC 2: an orphaned subagent (parent's ``skill_name`` also NULL) stays NULL.
   - AC 3: a directly-detected ``skill_name`` is never overwritten.
   - AC 5: running the backfill twice changes zero rows on the second pass.
   - AC 8: every join is ``(id, project_id)``-scoped — proven via a fixture
     with a *duplicate* ``id`` across two projects, the exact shape that
     fooled two prior DI-4f spike legs.
"""
from __future__ import annotations

import unittest

from backend.db.migration_governance import COLUMN_PARITY_DRIFT_ALLOWLIST
from backend.parsers.skill_provenance import (
    KNOWN_SKILL_SOURCES,
    SKILL_SOURCE_DIRECT,
    SKILL_SOURCE_INHERITED_PARENT,
    SKILL_SOURCE_TRUST_ORDER,
)

_COLUMN = "skill_name_source"


class TestSkillNameSourceDualDDL(unittest.TestCase):
    """Dual SQLite + Postgres DDL, per CLAUDE.md's "DB write paths" rule."""

    def _session_columns(self) -> tuple[set[str], set[str]]:
        from backend.db import postgres_migrations, sqlite_migrations
        from backend.db.migration_governance import (
            _backend_table_blocks,
            _parse_table_columns,
        )

        sqlite_cols = set(
            _parse_table_columns(_backend_table_blocks(sqlite_migrations)["sessions"])
        )
        pg_cols = set(
            _parse_table_columns(_backend_table_blocks(postgres_migrations)["sessions"])
        )
        return sqlite_cols, pg_cols

    def test_column_present_in_both_create_table_ddls(self) -> None:
        sqlite_cols, pg_cols = self._session_columns()
        self.assertIn(
            _COLUMN, sqlite_cols, msg=f"sessions.{_COLUMN} absent from SQLite DDL"
        )
        self.assertIn(
            _COLUMN, pg_cols, msg=f"sessions.{_COLUMN} absent from Postgres DDL"
        )

    def test_column_is_parity_clean_not_allowlisted(self) -> None:
        self.assertNotIn(
            ("sessions", _COLUMN),
            COLUMN_PARITY_DRIFT_ALLOWLIST,
            msg=(
                f"sessions.{_COLUMN} must be parity-clean by construction; "
                "allowlisting it would hide real drift"
            ),
        )

    def test_column_parity_diff_is_clean(self) -> None:
        from backend.db.migration_governance import column_parity_diff

        diff = column_parity_diff("sessions")
        self.assertNotIn(
            _COLUMN,
            diff,
            msg=f"sessions.{_COLUMN} differs across backends: {diff.get(_COLUMN)!r}",
        )

    def test_ensure_column_migration_exists_for_both_backends(self) -> None:
        from pathlib import Path

        sqlite_src = Path("backend/db/sqlite_migrations.py").read_text(encoding="utf-8")
        pg_src = Path("backend/db/postgres_migrations.py").read_text(encoding="utf-8")
        needle = f'_ensure_column(db, "sessions", "{_COLUMN}", "TEXT")'
        self.assertIn(needle, sqlite_src, msg="SQLite _ensure_column call missing")
        self.assertIn(needle, pg_src, msg="Postgres _ensure_column call missing")

    def test_schema_versions_match_and_advanced(self) -> None:
        from backend.db import postgres_migrations, sqlite_migrations

        self.assertEqual(
            sqlite_migrations.SCHEMA_VERSION,
            postgres_migrations.SCHEMA_VERSION,
            msg="SQLite and Postgres SCHEMA_VERSION must stay in lockstep",
        )
        self.assertGreaterEqual(sqlite_migrations.SCHEMA_VERSION, 49)

    def test_both_upsert_paths_write_the_column(self) -> None:
        from pathlib import Path

        sqlite_src = Path("backend/db/repositories/sessions.py").read_text(
            encoding="utf-8"
        )
        pg_src = Path("backend/db/repositories/postgres/sessions.py").read_text(
            encoding="utf-8"
        )
        for name, src in (("sqlite", sqlite_src), ("postgres", pg_src)):
            with self.subTest(backend=name):
                self.assertIn(_COLUMN, src, msg=f"{name} upsert omits {_COLUMN}")
                self.assertIn(
                    "backfill_skill_name_inheritance",
                    src,
                    msg=f"{name} repository is missing the inheritance backfill method",
                )


class TestVocabulary(unittest.TestCase):
    def test_tokens_are_unique_and_closed(self) -> None:
        self.assertEqual(
            len(SKILL_SOURCE_TRUST_ORDER),
            len(KNOWN_SKILL_SOURCES),
            msg="duplicate token in SKILL_SOURCE_TRUST_ORDER",
        )

    def test_direct_outranks_inherited(self) -> None:
        self.assertEqual(SKILL_SOURCE_TRUST_ORDER[0], SKILL_SOURCE_DIRECT)
        self.assertEqual(SKILL_SOURCE_TRUST_ORDER[1], SKILL_SOURCE_INHERITED_PARENT)

    def test_inherited_token_matches_effort_provenance_spelling(self) -> None:
        """Deliberate reconciliation with the Gap 4 precedent (Constraint 7).

        The contract's expansion proposed ``inherited_from_parent``; this module
        instead matches ``effort_provenance.EFFORT_SOURCE_INHERITED_PARENT``'s
        existing ``inherited_parent`` spelling so the codebase does not carry two
        near-identical tokens for "derived from a parent session".
        """
        from backend.parsers.effort_provenance import EFFORT_SOURCE_INHERITED_PARENT

        self.assertEqual(SKILL_SOURCE_INHERITED_PARENT, EFFORT_SOURCE_INHERITED_PARENT)
        self.assertEqual(SKILL_SOURCE_INHERITED_PARENT, "inherited_parent")


class SqliteSkillNameSourceRoundTripTests(unittest.IsolatedAsyncioTestCase):
    """Real DB round-trip with direct-count assertions (ADR-007 write-path rule)."""

    PROJECT_A = "proj-a"
    PROJECT_B = "proj-b"

    _BASE = {
        "taskId": "",
        "status": "completed",
        "sessionType": "session",
        "model": "claude-sonnet-5",
        "platformType": "Claude Code",
        "platformVersion": "2.1.52",
        "platformVersions": ["2.1.52"],
        "platformVersionTransitions": [],
        "durationSeconds": 1,
        "tokensIn": 1,
        "tokensOut": 1,
        "modelIOTokens": 2,
        "cacheCreationInputTokens": 0,
        "cacheReadInputTokens": 0,
        "cacheInputTokens": 0,
        "observedTokens": 0,
        "toolReportedTokens": 0,
        "toolResultInputTokens": 0,
        "toolResultOutputTokens": 0,
        "toolResultCacheCreationInputTokens": 0,
        "toolResultCacheReadInputTokens": 0,
        "totalCost": 0.0,
        "qualityRating": 0,
        "frictionRating": 0,
        "gitCommitHash": None,
        "gitAuthor": None,
        "gitBranch": None,
        "startedAt": "2026-08-02T00:00:00Z",
        "endedAt": "2026-08-02T00:01:00Z",
        "sourceFile": "",
        "parentSessionId": None,
        "rootSessionId": "root-1",
        "agentId": None,
        "threadKind": "root",
        "conversationFamilyId": "root-1",
        "contextInheritance": "fresh",
    }

    async def asyncSetUp(self) -> None:
        import aiosqlite

        from backend.db.repositories.sessions import SqliteSessionRepository
        from backend.db.sqlite_migrations import run_migrations

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    def _session(self, sid: str, **overrides) -> dict:
        return {**self._BASE, "id": sid, **overrides}

    async def _read(self, project_id: str, sid: str) -> tuple[str | None, str | None]:
        async with self.db.execute(
            "SELECT skill_name, skill_name_source FROM sessions"
            " WHERE project_id = ? AND id = ?",
            (project_id, sid),
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, msg=f"session {sid} not persisted")
        return row[0], row[1]

    async def _direct_count(self, project_id: str, sid: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ? AND id = ?",
            (project_id, sid),
        ) as cur:
            row = await cur.fetchone()
        return row[0]

    # -- migration -----------------------------------------------------

    async def test_migration_creates_the_column(self) -> None:
        async with self.db.execute("PRAGMA table_info(sessions)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        self.assertIn(_COLUMN, cols)

    # -- write path: direct detection -----------------------------------

    async def test_direct_detection_stamps_directly_detected(self) -> None:
        await self.repo.upsert(
            self._session("s1", skillName="rf"), self.PROJECT_A
        )
        self.assertEqual(
            await self._read(self.PROJECT_A, "s1"), ("rf", SKILL_SOURCE_DIRECT)
        )

    async def test_null_skill_persists_as_null_source(self) -> None:
        await self.repo.upsert(self._session("s2"), self.PROJECT_A)
        self.assertEqual(await self._read(self.PROJECT_A, "s2"), (None, None))

    # -- AC 1 / AC 2 / AC 3: backfill behavior --------------------------

    async def test_ac1_subagent_inherits_parent_skill(self) -> None:
        await self.repo.upsert(
            self._session("parent-1", skillName="rf"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session(
                "child-1",
                subagentParentId="parent-1",
                threadKind="subagent",
            ),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(result["rows"], 1)
        self.assertEqual(
            await self._read(self.PROJECT_A, "child-1"),
            ("rf", SKILL_SOURCE_INHERITED_PARENT),
        )

    async def test_ac2_orphaned_subagent_stays_null(self) -> None:
        """Parent's own skill_name is NULL — child must never fabricate one."""
        await self.repo.upsert(self._session("parent-2"), self.PROJECT_A)
        await self.repo.upsert(
            self._session(
                "child-2", subagentParentId="parent-2", threadKind="subagent"
            ),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(result["rows"], 0)
        self.assertEqual(await self._read(self.PROJECT_A, "child-2"), (None, None))

    async def test_ac3_direct_detection_never_overwritten(self) -> None:
        await self.repo.upsert(
            self._session("parent-3", skillName="rf"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session(
                "child-3",
                subagentParentId="parent-3",
                skillName="council-review",
                threadKind="subagent",
            ),
            self.PROJECT_A,
        )

        result = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(
            result["rows"],
            0,
            msg="backfill must not touch a session with a non-null skill_name",
        )
        self.assertEqual(
            await self._read(self.PROJECT_A, "child-3"),
            ("council-review", SKILL_SOURCE_DIRECT),
        )

    async def test_ac5_backfill_is_idempotent(self) -> None:
        await self.repo.upsert(
            self._session("parent-5", skillName="rf"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session(
                "child-5", subagentParentId="parent-5", threadKind="subagent"
            ),
            self.PROJECT_A,
        )

        first = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(first["rows"], 1)

        second = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        self.assertEqual(
            second["rows"],
            0,
            msg="second backfill pass must change zero rows",
        )
        self.assertEqual(
            await self._read(self.PROJECT_A, "child-5"),
            ("rf", SKILL_SOURCE_INHERITED_PARENT),
        )

    # -- AC 8: (id, project_id)-scoped join ------------------------------

    async def test_ac8_duplicate_id_across_projects_does_not_cross_contaminate(
        self,
    ) -> None:
        """The exact shape that fooled two prior DI-4f spike legs.

        Both projects use the SAME session id for parent and child. An unscoped
        `subagent_parent_id = parent.id` join would match the wrong project's
        parent row; a correctly `(id, project_id)`-scoped join must not.
        """
        # Project A: parent has skill "rf", child should inherit it.
        await self.repo.upsert(
            self._session("parent-dup", skillName="rf"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session(
                "child-dup", subagentParentId="parent-dup", threadKind="subagent"
            ),
            self.PROJECT_A,
        )

        # Project B: SAME ids, but parent has a DIFFERENT skill (or none) —
        # if the join is not project-scoped, child-dup in project A could
        # pick up project B's parent skill instead, or vice versa.
        await self.repo.upsert(
            self._session("parent-dup", skillName="meatywiki"), self.PROJECT_B
        )
        await self.repo.upsert(
            self._session(
                "child-dup", subagentParentId="parent-dup", threadKind="subagent"
            ),
            self.PROJECT_B,
        )

        result_a = await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)
        result_b = await self.repo.backfill_skill_name_inheritance(self.PROJECT_B)

        self.assertEqual(result_a["rows"], 1)
        self.assertEqual(result_b["rows"], 1)

        self.assertEqual(
            await self._read(self.PROJECT_A, "child-dup"),
            ("rf", SKILL_SOURCE_INHERITED_PARENT),
            msg="project A child must inherit project A's parent skill only",
        )
        self.assertEqual(
            await self._read(self.PROJECT_B, "child-dup"),
            ("meatywiki", SKILL_SOURCE_INHERITED_PARENT),
            msg="project B child must inherit project B's parent skill only",
        )

        # Direct-count sanity: exactly one row per (project_id, id) pair, no fan-out.
        self.assertEqual(await self._direct_count(self.PROJECT_A, "child-dup"), 1)
        self.assertEqual(await self._direct_count(self.PROJECT_B, "child-dup"), 1)

    async def test_ac8_scoping_when_running_single_project_backfill_only(
        self,
    ) -> None:
        """Running the backfill for project A only must never touch project B."""
        await self.repo.upsert(
            self._session("parent-scope", skillName="rf"), self.PROJECT_A
        )
        await self.repo.upsert(
            self._session(
                "child-scope", subagentParentId="parent-scope", threadKind="subagent"
            ),
            self.PROJECT_A,
        )
        # Project B has an unrelated orphan with the same child id, no parent
        # with a matching skill.
        await self.repo.upsert(
            self._session("child-scope", threadKind="subagent"), self.PROJECT_B
        )

        await self.repo.backfill_skill_name_inheritance(self.PROJECT_A)

        self.assertEqual(
            await self._read(self.PROJECT_A, "child-scope"),
            ("rf", SKILL_SOURCE_INHERITED_PARENT),
        )
        self.assertEqual(
            await self._read(self.PROJECT_B, "child-scope"),
            (None, None),
            msg="project-scoped backfill must not leak into another project",
        )


if __name__ == "__main__":
    unittest.main()
