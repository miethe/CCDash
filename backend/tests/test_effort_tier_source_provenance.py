"""Gap 4 — ``sessions.effort_tier_source`` provenance column.

Covers the four things that can silently rot:

1. **Dual DDL parity** — the column exists in BOTH the SQLite and Postgres
   ``CREATE TABLE sessions`` blocks and is NOT allowlisted as drift (CLAUDE.md
   "Session columns" convention).
2. **Hook literal parity** — the standalone SessionStart hook cannot import
   ``backend``, so it repeats the token strings; they must equal the canonical
   constants.
3. **Write-path invariant** — a non-null source is written iff a non-null tier is
   written, per lane (launch env, Claude settings, Codex primary, Codex fallback).
4. **Backward compatibility** — v1 sidecars (every one already on disk) still
   parse, yielding a null source rather than being rejected outright.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.db.migration_governance import COLUMN_PARITY_DRIFT_ALLOWLIST
from backend.parsers.capture_sidecar import CaptureSidecar, parse_capture_sidecar
from backend.parsers.effort_provenance import (
    AUTHORITATIVE_EFFORT_SOURCES,
    EFFORT_SOURCE_CLAUDE_SETTINGS,
    EFFORT_SOURCE_CODEX_COLLABORATION_MODE,
    EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT,
    EFFORT_SOURCE_INHERITED_PARENT,
    EFFORT_SOURCE_LAUNCH_ENV,
    EFFORT_SOURCE_TRUST_ORDER,
    KNOWN_EFFORT_SOURCES,
)

_COLUMN = "effort_tier_source"


class TestEffortTierSourceDualDDL(unittest.TestCase):
    """The Mode-D reason this change exists: dual SQLite + Postgres DDL."""

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
        """Existing DBs get the column via _ensure_column, not just fresh ones."""
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
        self.assertGreaterEqual(sqlite_migrations.SCHEMA_VERSION, 44)

    def test_both_upsert_paths_write_the_column(self) -> None:
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
                    'session_data.get("effortTierSource")',
                    src,
                    msg=f"{name} upsert never binds the effortTierSource value",
                )
                # Capture-once: a null on re-ingest must not clobber a known value.
                self.assertIn(
                    f"{_COLUMN}=COALESCE(",
                    src.replace("EXCLUDED", "excluded"),
                    msg=f"{name} upsert must COALESCE-guard {_COLUMN}",
                )


class TestHookLiteralParity(unittest.TestCase):
    """The hook duplicates token literals because it cannot import backend."""

    def setUp(self) -> None:
        self.hook_src = Path(
            "scripts/hooks/ccdash_capture_session_start.py"
        ).read_text(encoding="utf-8")

    def test_hook_literals_match_canonical_constants(self) -> None:
        self.assertIn(
            f'_EFFORT_SOURCE_LAUNCH_ENV = "{EFFORT_SOURCE_LAUNCH_ENV}"',
            self.hook_src,
            msg="hook launch_env literal drifted from effort_provenance constant",
        )
        self.assertIn(
            f'_EFFORT_SOURCE_CLAUDE_SETTINGS = "{EFFORT_SOURCE_CLAUDE_SETTINGS}"',
            self.hook_src,
            msg="hook claude_settings literal drifted from effort_provenance constant",
        )

    def test_hook_declares_schema_version_3(self) -> None:
        # v51 (ica-key-and-spend-capture) bumped the sidecar to v3. Older
        # sidecars still parse (see capture_sidecar._SUPPORTED_SCHEMA_VERSIONS).
        self.assertIn("_SCHEMA_VERSION = 3", self.hook_src)

    def test_hook_does_not_import_backend(self) -> None:
        """Importing backend would break the hook at launch time (no venv)."""
        self.assertNotIn("from backend", self.hook_src)
        self.assertNotIn("import backend", self.hook_src)


class TestVocabulary(unittest.TestCase):
    def test_tokens_are_unique_and_closed(self) -> None:
        self.assertEqual(
            len(EFFORT_SOURCE_TRUST_ORDER),
            len(KNOWN_EFFORT_SOURCES),
            msg="duplicate token in EFFORT_SOURCE_TRUST_ORDER",
        )

    def test_trust_order_puts_launch_env_first(self) -> None:
        self.assertEqual(EFFORT_SOURCE_TRUST_ORDER[0], EFFORT_SOURCE_LAUNCH_ENV)

    def test_stale_capable_and_derived_sources_are_not_authoritative(self) -> None:
        self.assertNotIn(EFFORT_SOURCE_CLAUDE_SETTINGS, AUTHORITATIVE_EFFORT_SOURCES)
        self.assertNotIn(EFFORT_SOURCE_INHERITED_PARENT, AUTHORITATIVE_EFFORT_SOURCES)
        self.assertIn(EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT, AUTHORITATIVE_EFFORT_SOURCES)


class TestHookWritePath(unittest.TestCase):
    """Each resolution lane stamps its own token; null tier ⇒ null source."""

    def setUp(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_ccdash_capture_hook",
            "scripts/hooks/ccdash_capture_session_start.py",
        )
        assert spec and spec.loader
        self.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hook)

    def _write(self, env: dict, *, cwd: Path, tmp: Path) -> dict:
        payload = {
            "session_id": "sess-abc",
            "transcript_path": str(tmp / "sess-abc.jsonl"),
            "cwd": str(cwd),
        }
        out = self.hook.write_capture_sidecar(payload, env, fallback_base=tmp)
        self.assertIsNotNone(out, msg="sidecar was not written")
        return json.loads(Path(out).read_text(encoding="utf-8"))

    def test_launch_env_stamps_launch_env_source(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            empty_project = tmp / "proj"
            empty_project.mkdir()
            doc = self._write(
                {"CCDASH_LAUNCH_EFFORT": "xhigh", "CLAUDE_CONFIG_DIR": str(tmp / "nope")},
                cwd=empty_project,
                tmp=tmp,
            )
        self.assertEqual(doc["effortTier"], "xhigh")
        self.assertEqual(doc["effortTierSource"], EFFORT_SOURCE_LAUNCH_ENV)
        # v51: sidecar bumped to 3 (ica-key-and-spend-capture). The prior 1/2
        # remain accepted by the reader; the writer emits the current version.
        self.assertEqual(doc["schemaVersion"], 3)

    def test_settings_fallback_stamps_claude_settings_source(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "proj"
            (project / ".claude").mkdir(parents=True)
            (project / ".claude" / "settings.json").write_text(
                json.dumps({"effortLevel": "medium"}), encoding="utf-8"
            )
            doc = self._write(
                {"CLAUDE_CONFIG_DIR": str(tmp / "nope")}, cwd=project, tmp=tmp
            )
        self.assertEqual(doc["effortTier"], "medium")
        self.assertEqual(doc["effortTierSource"], EFFORT_SOURCE_CLAUDE_SETTINGS)

    def test_no_effort_anywhere_yields_null_tier_and_null_source(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "proj"
            project.mkdir()
            doc = self._write(
                {"CLAUDE_CONFIG_DIR": str(tmp / "nope")}, cwd=project, tmp=tmp
            )
        self.assertIsNone(doc["effortTier"])
        self.assertIsNone(
            doc["effortTierSource"],
            msg="provenance must never be stamped without a value to explain",
        )

    def test_malformed_settings_nulls_source_but_keeps_other_fields(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "proj"
            (project / ".claude").mkdir(parents=True)
            (project / ".claude" / "settings.json").write_text(
                "{not json", encoding="utf-8"
            )
            doc = self._write(
                {
                    "CCDASH_LAUNCHER": "ica-claude.sh",
                    "CLAUDE_CONFIG_DIR": str(tmp / "nope"),
                },
                cwd=project,
                tmp=tmp,
            )
        self.assertIsNone(doc["effortTier"])
        self.assertIsNone(doc["effortTierSource"])
        self.assertEqual(doc["launcher"], "ica-claude.sh")


class TestSidecarBackwardCompatibility(unittest.TestCase):
    def _parse(self, doc: dict) -> CaptureSidecar | None:
        with TemporaryDirectory() as td:
            path = Path(td) / "s.capture.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            return parse_capture_sidecar(path)

    def test_v1_sidecar_still_parses_with_null_source(self) -> None:
        """Every sidecar already on disk is v1 — rejecting them would blind the lane."""
        result = self._parse(
            {
                "schemaVersion": 1,
                "sessionId": "s",
                "effortTier": "high",
                "launcher": "claude",
            }
        )
        self.assertIsNotNone(result, msg="v1 sidecar must remain accepted")
        assert result is not None
        self.assertEqual(result.effort_tier, "high")
        self.assertIsNone(result.effort_tier_source)

    def test_v2_sidecar_round_trips_source(self) -> None:
        result = self._parse(
            {
                "schemaVersion": 2,
                "sessionId": "s",
                "effortTier": "high",
                "effortTierSource": EFFORT_SOURCE_LAUNCH_ENV,
            }
        )
        assert result is not None
        self.assertEqual(result.effort_tier_source, EFFORT_SOURCE_LAUNCH_ENV)

    def test_source_without_tier_is_dropped(self) -> None:
        result = self._parse(
            {
                "schemaVersion": 2,
                "sessionId": "s",
                "effortTierSource": EFFORT_SOURCE_LAUNCH_ENV,
            }
        )
        assert result is not None
        self.assertIsNone(result.effort_tier)
        self.assertIsNone(
            result.effort_tier_source,
            msg="provenance without a value it describes must be dropped",
        )

    def test_unsupported_future_version_still_rejected(self) -> None:
        self.assertIsNone(self._parse({"schemaVersion": 99, "sessionId": "s"}))


class SqliteEffortTierSourceRoundTripTests(unittest.IsolatedAsyncioTestCase):
    """Real DB round-trip with direct-count assertions (ADR-007 write-path rule).

    Proves the migration actually creates the column, the upsert actually writes
    it, and the COALESCE guard actually protects a known provenance from being
    downgraded to unknown by a later sidecar-less re-ingest.
    """

    PROJECT = "proj-provenance"

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

    async def _read(self, sid: str) -> tuple[str | None, str | None]:
        async with self.db.execute(
            "SELECT effort_tier, effort_tier_source FROM sessions"
            " WHERE project_id = ? AND id = ?",
            (self.PROJECT, sid),
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, msg=f"session {sid} not persisted")
        return row[0], row[1]

    async def _direct_count(self, sid: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ? AND id = ?",
            (self.PROJECT, sid),
        ) as cur:
            row = await cur.fetchone()
        return row[0]

    async def test_migration_creates_the_column(self) -> None:
        async with self.db.execute("PRAGMA table_info(sessions)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        self.assertIn(_COLUMN, cols)

    async def test_source_persists_through_upsert(self) -> None:
        await self.repo.upsert(
            self._session(
                "s1",
                effortTier="high",
                effortTierSource=EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT,
            ),
            self.PROJECT,
        )
        await self.db.commit()

        self.assertEqual(await self._direct_count("s1"), 1)
        self.assertEqual(
            await self._read("s1"), ("high", EFFORT_SOURCE_CODEX_PAYLOAD_EFFORT)
        )

    async def test_absent_source_persists_as_null(self) -> None:
        await self.repo.upsert(self._session("s2"), self.PROJECT)
        await self.db.commit()
        self.assertEqual(await self._read("s2"), (None, None))

    async def test_reingest_without_sidecar_does_not_clobber_known_provenance(
        self,
    ) -> None:
        """The COALESCE guard: capture-once, exactly like its sibling columns."""
        await self.repo.upsert(
            self._session(
                "s3", effortTier="xhigh", effortTierSource=EFFORT_SOURCE_LAUNCH_ENV
            ),
            self.PROJECT,
        )
        await self.db.commit()

        # Re-ingest the same session with no capture fields (sidecar deleted /
        # unreadable on a later sync pass).
        await self.repo.upsert(self._session("s3"), self.PROJECT)
        await self.db.commit()

        self.assertEqual(
            await self._read("s3"),
            ("xhigh", EFFORT_SOURCE_LAUNCH_ENV),
            msg="re-ingest downgraded a known provenance to unknown",
        )
        self.assertEqual(await self._direct_count("s3"), 1)

    async def test_reingest_can_upgrade_unknown_to_known(self) -> None:
        """Null → known is a legitimate upgrade the COALESCE must still allow."""
        await self.repo.upsert(self._session("s4", effortTier="medium"), self.PROJECT)
        await self.db.commit()
        self.assertEqual(await self._read("s4"), ("medium", None))

        await self.repo.upsert(
            self._session(
                "s4", effortTier="medium", effortTierSource=EFFORT_SOURCE_CLAUDE_SETTINGS
            ),
            self.PROJECT,
        )
        await self.db.commit()
        self.assertEqual(
            await self._read("s4"), ("medium", EFFORT_SOURCE_CLAUDE_SETTINGS)
        )


if __name__ == "__main__":
    unittest.main()
