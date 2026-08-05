"""automatic-session-naming M1 (T1-001) — schema v50 + provenance vocabulary.

Mirrors ``test_skill_name_source_provenance.py`` / ``test_effort_tier_source_provenance.py``
(the ``skill_name_source`` / ``effort_tier_source`` precedents) shape-for-shape. Covers:

1. **Dual DDL parity** — ``session_name`` and ``session_name_source`` exist in
   BOTH the SQLite and Postgres ``CREATE TABLE sessions`` blocks, are NOT
   allowlisted as drift, and both backends carry an ``_ensure_column`` upgrade
   path for existing databases.
2. **Vocabulary** — the four-token closed vocabulary is unique, ordered
   strongest-first, and the reserved tokens
   (``derived_embedding_transfer``, ``operator_set``) are declared but write
   to nothing yet.
3. **Rank helper** — ``session_name_rank`` / ``may_overwrite`` enforce "a
   weaker source never overwrites a stronger one" without callers
   re-deriving the comparison, and treat an unrecognised token as unknown
   provenance rather than raising.

Ingest/write-path coverage (parser attribution, repository upsert wiring) is
scoped to later tasks (T1-002/T1-003) and is deliberately not asserted here.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from backend.db.migration_governance import COLUMN_PARITY_DRIFT_ALLOWLIST
from backend.parsers.session_name_provenance import (
    KNOWN_SESSION_NAME_SOURCES,
    RESERVED_SESSION_NAME_SOURCES,
    SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
    SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER,
    SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
    SESSION_NAME_SOURCE_OPERATOR_SET,
    SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
    SESSION_NAME_SOURCE_TRUST_ORDER,
    may_overwrite,
    session_name_rank,
)

_COLUMNS = ("session_name", "session_name_source")


class TestSessionNameDualDDL(unittest.TestCase):
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

    def test_columns_present_in_both_create_table_ddls(self) -> None:
        sqlite_cols, pg_cols = self._session_columns()
        for column in _COLUMNS:
            with self.subTest(column=column):
                self.assertIn(
                    column, sqlite_cols, msg=f"sessions.{column} absent from SQLite DDL"
                )
                self.assertIn(
                    column, pg_cols, msg=f"sessions.{column} absent from Postgres DDL"
                )

    def test_columns_are_parity_clean_not_allowlisted(self) -> None:
        for column in _COLUMNS:
            with self.subTest(column=column):
                self.assertNotIn(
                    ("sessions", column),
                    COLUMN_PARITY_DRIFT_ALLOWLIST,
                    msg=(
                        f"sessions.{column} must be parity-clean by construction; "
                        "allowlisting it would hide real drift"
                    ),
                )

    def test_column_parity_diff_is_clean(self) -> None:
        from backend.db.migration_governance import column_parity_diff

        diff = column_parity_diff("sessions")
        for column in _COLUMNS:
            with self.subTest(column=column):
                self.assertNotIn(
                    column,
                    diff,
                    msg=f"sessions.{column} differs across backends: {diff.get(column)!r}",
                )

    def test_ensure_column_migration_exists_for_both_backends(self) -> None:
        sqlite_src = Path("backend/db/sqlite_migrations.py").read_text(encoding="utf-8")
        pg_src = Path("backend/db/postgres_migrations.py").read_text(encoding="utf-8")
        for column in _COLUMNS:
            needle = f'_ensure_column(db, "sessions", "{column}", "TEXT")'
            with self.subTest(column=column):
                self.assertIn(needle, sqlite_src, msg="SQLite _ensure_column call missing")
                self.assertIn(needle, pg_src, msg="Postgres _ensure_column call missing")

    def test_schema_versions_match_and_advanced(self) -> None:
        from backend.db import postgres_migrations, sqlite_migrations

        self.assertEqual(
            sqlite_migrations.SCHEMA_VERSION,
            postgres_migrations.SCHEMA_VERSION,
            msg="SQLite and Postgres SCHEMA_VERSION must stay in lockstep",
        )
        self.assertGreaterEqual(sqlite_migrations.SCHEMA_VERSION, 50)


class TestSessionNameProvenanceVocabulary(unittest.TestCase):
    """The four-token closed vocabulary: uniqueness, order, reserved status."""

    def test_trust_order_has_four_unique_tokens(self) -> None:
        self.assertEqual(len(SESSION_NAME_SOURCE_TRUST_ORDER), 4)
        self.assertEqual(
            len(set(SESSION_NAME_SOURCE_TRUST_ORDER)),
            4,
            msg="trust-order tokens must be unique",
        )

    def test_trust_order_is_provider_deterministic_embedding_generative(self) -> None:
        self.assertEqual(
            SESSION_NAME_SOURCE_TRUST_ORDER,
            (
                SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
                SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
                SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER,
                SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
            ),
        )

    def test_token_spellings(self) -> None:
        self.assertEqual(SESSION_NAME_SOURCE_PROVIDER_PERSISTED, "provider_persisted")
        self.assertEqual(
            SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC, "derived_deterministic"
        )
        self.assertEqual(
            SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER,
            "derived_embedding_transfer",
        )
        self.assertEqual(
            SESSION_NAME_SOURCE_DERIVED_GENERATIVE, "derived_generative"
        )
        self.assertEqual(SESSION_NAME_SOURCE_OPERATOR_SET, "operator_set")

    def test_reserved_tokens_are_declared_but_unused_by_this_module(self) -> None:
        self.assertIn(SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER, RESERVED_SESSION_NAME_SOURCES)
        self.assertIn(SESSION_NAME_SOURCE_OPERATOR_SET, RESERVED_SESSION_NAME_SOURCES)

    def test_operator_set_is_known_but_not_ranked(self) -> None:
        self.assertIn(SESSION_NAME_SOURCE_OPERATOR_SET, KNOWN_SESSION_NAME_SOURCES)
        self.assertNotIn(SESSION_NAME_SOURCE_OPERATOR_SET, SESSION_NAME_SOURCE_TRUST_ORDER)
        self.assertIsNone(session_name_rank(SESSION_NAME_SOURCE_OPERATOR_SET))

    def test_known_sources_is_closed_over_trust_order_plus_operator_set(self) -> None:
        self.assertEqual(
            KNOWN_SESSION_NAME_SOURCES,
            frozenset(SESSION_NAME_SOURCE_TRUST_ORDER) | {SESSION_NAME_SOURCE_OPERATOR_SET},
        )

    def test_no_code_path_references_grep_for_reserved_writes(self) -> None:
        """Reserved tokens must not be write-targets outside this module yet."""
        src_dir = Path("backend")
        offenders: list[str] = []
        for path in src_dir.rglob("*.py"):
            if path.name in {"session_name_provenance.py", "test_session_name_provenance.py"}:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if (
                SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER in text
                or SESSION_NAME_SOURCE_OPERATOR_SET in text
            ):
                offenders.append(str(path))
        self.assertEqual(
            offenders,
            [],
            msg=(
                "reserved session-name-source tokens must remain unused outside "
                f"session_name_provenance.py; found references in: {offenders}"
            ),
        )


class TestSessionNameRankHelpers(unittest.TestCase):
    """``session_name_rank`` / ``may_overwrite`` — the "never overwrite a
    stronger source" contract, enforced via helper rather than inline logic.
    """

    def test_rank_orders_strongest_first(self) -> None:
        self.assertEqual(
            session_name_rank(SESSION_NAME_SOURCE_PROVIDER_PERSISTED), 0
        )
        self.assertEqual(
            session_name_rank(SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC), 1
        )
        self.assertEqual(
            session_name_rank(SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER), 2
        )
        self.assertEqual(
            session_name_rank(SESSION_NAME_SOURCE_DERIVED_GENERATIVE), 3
        )

    def test_rank_of_none_is_none(self) -> None:
        self.assertIsNone(session_name_rank(None))

    def test_rank_of_unknown_token_is_none_not_a_hard_fail(self) -> None:
        self.assertIsNone(session_name_rank("some_future_token_nobody_has_declared_yet"))

    def test_may_overwrite_when_no_incumbent(self) -> None:
        self.assertTrue(
            may_overwrite(SESSION_NAME_SOURCE_DERIVED_GENERATIVE, None)
        )

    def test_may_overwrite_when_incumbent_is_unranked(self) -> None:
        # A bare pre-existing session_name with no recorded provenance is the
        # weakest possible incumbent -- anything ranked may overwrite it.
        self.assertTrue(
            may_overwrite(SESSION_NAME_SOURCE_DERIVED_GENERATIVE, "legacy_unranked_value")
        )
        self.assertTrue(
            may_overwrite(SESSION_NAME_SOURCE_DERIVED_GENERATIVE, None)
        )

    def test_operator_set_incumbent_is_never_overwritable(self) -> None:
        # Regression guard for the feature-level review's M-1 finding. operator_set
        # sits OUTSIDE the ranked ladder, so session_name_rank returns None for it
        # -- which means the "unranked incumbent is the weakest possible incumbent"
        # rule above would otherwise invert the strongest (human) signal into the
        # weakest one, and every lane would happily clobber an operator override.
        # Not reachable today (operator_set is reserved and unwritten, and the
        # sweep only selects session_name IS NULL), but the declared rename-UI
        # follow-on walks straight into it, so the contract is enforced here --
        # in the helper this module's docstring designates as THE enforcement
        # mechanism -- rather than left to each call site to remember.
        for candidate in (
            SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
            SESSION_NAME_SOURCE_DERIVED_EMBEDDING_TRANSFER,
            SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
            SESSION_NAME_SOURCE_OPERATOR_SET,
            "some_future_stronger_token",
            None,
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(
                    may_overwrite(candidate, SESSION_NAME_SOURCE_OPERATOR_SET),
                    f"{candidate!r} must not be able to overwrite an operator_set name",
                )

    def test_stronger_candidate_may_overwrite_weaker_incumbent(self) -> None:
        self.assertTrue(
            may_overwrite(
                SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
                SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
            )
        )

    def test_equal_strength_may_overwrite(self) -> None:
        self.assertTrue(
            may_overwrite(
                SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
                SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
            )
        )

    def test_weaker_candidate_must_never_overwrite_stronger_incumbent(self) -> None:
        self.assertFalse(
            may_overwrite(
                SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
                SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            )
        )
        self.assertFalse(
            may_overwrite(
                SESSION_NAME_SOURCE_DERIVED_DETERMINISTIC,
                SESSION_NAME_SOURCE_PROVIDER_PERSISTED,
            )
        )

    def test_unranked_candidate_never_overwrites_a_ranked_incumbent(self) -> None:
        self.assertFalse(
            may_overwrite(None, SESSION_NAME_SOURCE_DERIVED_GENERATIVE)
        )
        self.assertFalse(
            may_overwrite(
                "some_future_token_nobody_has_declared_yet",
                SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
            )
        )
        self.assertFalse(
            may_overwrite(
                SESSION_NAME_SOURCE_OPERATOR_SET,
                SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
            )
        )


if __name__ == "__main__":
    unittest.main()
