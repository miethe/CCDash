"""Schema-level assertion tests for the provider dimension entity tables.

Covers ``provider_dimensions``, ``provider_channels``, and ``provider_credentials``
added by commit 8dacdcc (provider-channel-credential-entities-v1 M1), which bumped
``SCHEMA_VERSION`` 51 -> 52 in both backend.db.sqlite_migrations and
backend.db.postgres_migrations.

This file is intentionally static/DDL-only: it never opens a database connection.
It reuses the public parsing helpers from backend.db.migration_governance (the same
seam backend/tests/test_migration_governance.py uses) rather than hand-rolling a DDL
parser, so table/column extraction stays consistent with the rest of the governance
suite.
"""
import re
import unittest

from backend.db import postgres_migrations, sqlite_migrations
from backend.db.migration_governance import (
    COLUMN_PARITY_DRIFT_ALLOWLIST,
    _backend_table_blocks,
    _parse_table_columns,
    get_postgres_migration_tables,
    get_sqlite_migration_tables,
)

_PROVIDER_TABLES = ("provider_dimensions", "provider_channels", "provider_credentials")

# Column-name substrings that would indicate secret material is being stored
# directly on one of these entity tables. `credential_name` is a legitimate
# label (e.g. "CC1") and must NOT trip any of these substrings.
_FORBIDDEN_SUBSTRINGS = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "private_key",
)
_FORBIDDEN_EXACT_NAMES = frozenset({"key", "value"})


class ProviderDimensionSchemaVersionTests(unittest.TestCase):
    """AC1: SCHEMA_VERSION == 52 in both migration modules, asserted separately."""

    # Relaxed from `== 52` to `>= 52` when the hosted-llm-anthropic-ica-lane
    # feature landed concurrently and took v53 (projects.llm_egress_consent).
    # SCHEMA_VERSION is a repo-global high-water mark, not this feature's
    # property, so pinning it with `==` made these two assertions fail on the
    # next schema change by ANY feature. The invariant this test actually
    # protects is that the provider-dimension DDL is gated at or after v52 --
    # which `>=` states exactly, and which the `if current_version < 52`
    # migration gate in both backends still implements unchanged.
    def test_sqlite_schema_version_is_at_least_52(self) -> None:
        self.assertGreaterEqual(sqlite_migrations.SCHEMA_VERSION, 52)

    def test_postgres_schema_version_is_at_least_52(self) -> None:
        self.assertGreaterEqual(postgres_migrations.SCHEMA_VERSION, 52)


class ProviderDimensionTablesPresentTests(unittest.TestCase):
    """AC2: all three tables are visible to the migration-governance table parser.

    LOAD-BEARING: this is what stops the "no drift" and "no secrets" assertions
    below from passing vacuously. If a future refactor moved this DDL somewhere
    the get_*_migration_tables() parser can't see (e.g. out of the module-level
    _TABLES / _PROVIDER_DIMENSION_TABLES strings _backend_table_blocks() scans),
    those assertions would trivially pass on an empty/absent table set while the
    real schema went unchecked. This test is the tripwire for that failure mode.
    """

    def test_all_three_tables_present_in_sqlite_migration_tables(self) -> None:
        sqlite_tables = get_sqlite_migration_tables()
        for table in _PROVIDER_TABLES:
            self.assertIn(table, sqlite_tables, msg=f"{table} missing from get_sqlite_migration_tables()")

    def test_all_three_tables_present_in_postgres_migration_tables(self) -> None:
        postgres_tables = get_postgres_migration_tables()
        for table in _PROVIDER_TABLES:
            self.assertIn(table, postgres_tables, msg=f"{table} missing from get_postgres_migration_tables()")


class ProviderDimensionNoAllowlistDriftTests(unittest.TestCase):
    """AC3: none of the three tables appear in COLUMN_PARITY_DRIFT_ALLOWLIST."""

    def test_no_provider_dimension_table_is_allowlisted(self) -> None:
        offending_pairs = sorted(
            pair for pair in COLUMN_PARITY_DRIFT_ALLOWLIST if pair[0] in _PROVIDER_TABLES
        )
        self.assertEqual(
            offending_pairs,
            [],
            msg=(
                "Provider dimension tables must not carry any COLUMN_PARITY_DRIFT_ALLOWLIST "
                f"exclusions (they are new, schema-parity-clean-by-construction tables); "
                f"offending (table, column) pairs: {offending_pairs}"
            ),
        )


class ProviderDimensionColumnParityTests(unittest.TestCase):
    """AC4: SQLite and Postgres column NAME sets are identical per table."""

    def test_structural_column_parity_per_table(self) -> None:
        sqlite_blocks = _backend_table_blocks(sqlite_migrations)
        postgres_blocks = _backend_table_blocks(postgres_migrations)

        for table in _PROVIDER_TABLES:
            self.assertIn(table, sqlite_blocks, msg=f"{table} not found in SQLite _TABLES DDL")
            self.assertIn(table, postgres_blocks, msg=f"{table} not found in Postgres _TABLES DDL")

            sqlite_cols = set(_parse_table_columns(sqlite_blocks[table]))
            postgres_cols = set(_parse_table_columns(postgres_blocks[table]))

            self.assertSetEqual(
                sqlite_cols,
                postgres_cols,
                msg=(
                    f"Column name sets diverged for '{table}': "
                    f"sqlite_only={sorted(sqlite_cols - postgres_cols)} "
                    f"postgres_only={sorted(postgres_cols - sqlite_cols)}"
                ),
            )


class ProviderDimensionNoSecretColumnsTests(unittest.TestCase):
    """AC5: no column on any of the three tables can hold secret material."""

    def test_no_column_names_look_like_secrets(self) -> None:
        sqlite_blocks = _backend_table_blocks(sqlite_migrations)

        for table in _PROVIDER_TABLES:
            columns = _parse_table_columns(sqlite_blocks[table])
            for col_name in columns:
                lowered = col_name.lower()
                self.assertNotIn(
                    lowered,
                    _FORBIDDEN_EXACT_NAMES,
                    msg=f"Column '{table}.{col_name}' is a forbidden exact secret-shaped name",
                )
                for forbidden in _FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(
                        forbidden,
                        lowered,
                        msg=(
                            f"Column '{table}.{col_name}' contains forbidden substring "
                            f"'{forbidden}' — secret material must never be a column value"
                        ),
                    )

    def test_credential_name_column_exists_on_provider_credentials(self) -> None:
        """Positive control: credential_name is legitimate and must exist.

        Without this assertion, a future rename of credential_name (e.g. to
        something the forbidden-substring check would also pass) would silently
        make the secret-shape check above vacuous for provider_credentials.
        """
        sqlite_blocks = _backend_table_blocks(sqlite_migrations)
        postgres_blocks = _backend_table_blocks(postgres_migrations)

        sqlite_cols = _parse_table_columns(sqlite_blocks["provider_credentials"])
        postgres_cols = _parse_table_columns(postgres_blocks["provider_credentials"])

        self.assertIn("credential_name", sqlite_cols)
        self.assertIn("credential_name", postgres_cols)


class ProviderDimensionDesignConstraintTests(unittest.TestCase):
    """AC6: the two deliberate design constraints, checked against DDL text.

    Both are load-bearing product decisions (see the module docstring / DDL
    comments in sqlite_migrations.py and postgres_migrations.py):

    1. No FOREIGN KEY / REFERENCES anywhere in the three tables' DDL.
       rotated_from_id on provider_credentials is deliberately a plain integer
       pointer, not an enforced FK: SQLite does not enforce foreign keys by
       default while Postgres does, so declaring an FK here would be a real
       behavioural divergence between backends (Postgres would reject
       inserts/deletes SQLite would silently allow). Rotation-lineage integrity
       is enforced in the repository layer instead. A future edit adding an FK
       to any of these tables would introduce exactly that divergence and MUST
       fail this test.

    2. No CHECK constraint on either `channel` column (provider_dimensions.
       provider_channel, provider_channels.channel). The channel vocabulary is
       deliberately open (subscription/ica/api/unknown/...) so an unrecognized
       future channel token is still storable rather than raising a database
       error. A future edit adding a CHECK on either column would close that
       vocabulary and MUST fail this test.
    """

    def _provider_table_ddl_slices(self, module: object) -> dict[str, str]:
        """Return {table: full DDL text of its CREATE TABLE statement(s)}.

        Uses the same CREATE TABLE regex family the governance module relies on,
        but keeps the raw (non-column-parsed) text so FK/CHECK keyword scanning
        sees the full statement, including table-level constraints.
        """
        create_table_re = re.compile(
            r"CREATE TABLE IF NOT EXISTS\s+"
            r"(?:(?P<schema>[a-zA-Z_][a-zA-Z0-9_]*)\.)?"
            r"(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s*"
            r"\((?P<body>.*?)\);",
            re.DOTALL,
        )
        slices: dict[str, list[str]] = {table: [] for table in _PROVIDER_TABLES}
        # Scan every module-level string attribute that plausibly holds DDL,
        # so both the SQLite baseline (_TABLES) and migration-path mirror
        # (_PROVIDER_DIMENSION_TABLES) are covered, matching how the tables
        # can appear more than once (baseline + idempotent migration path).
        for attr_name in dir(module):
            if attr_name.startswith("__"):
                continue
            value = getattr(module, attr_name)
            if not isinstance(value, str) or "provider_" not in value:
                continue
            for match in create_table_re.finditer(value):
                table = match.group("table")
                if table in slices:
                    slices[table].append(match.group(0))
        return {table: "\n".join(chunks) for table, chunks in slices.items() if chunks}

    def test_no_foreign_key_constraints_sqlite(self) -> None:
        ddl_slices = self._provider_table_ddl_slices(sqlite_migrations)
        for table in _PROVIDER_TABLES:
            self.assertIn(table, ddl_slices, msg=f"No DDL found for {table} in sqlite_migrations")
            ddl = ddl_slices[table].upper()
            self.assertNotIn("FOREIGN KEY", ddl, msg=f"Unexpected FOREIGN KEY in SQLite DDL for {table}")
            self.assertNotIn("REFERENCES", ddl, msg=f"Unexpected REFERENCES clause in SQLite DDL for {table}")

    def test_no_foreign_key_constraints_postgres(self) -> None:
        ddl_slices = self._provider_table_ddl_slices(postgres_migrations)
        for table in _PROVIDER_TABLES:
            self.assertIn(table, ddl_slices, msg=f"No DDL found for {table} in postgres_migrations")
            ddl = ddl_slices[table].upper()
            self.assertNotIn("FOREIGN KEY", ddl, msg=f"Unexpected FOREIGN KEY in Postgres DDL for {table}")
            self.assertNotIn("REFERENCES", ddl, msg=f"Unexpected REFERENCES clause in Postgres DDL for {table}")

    def test_no_check_constraint_on_channel_columns_sqlite(self) -> None:
        ddl_slices = self._provider_table_ddl_slices(sqlite_migrations)
        for table in ("provider_dimensions", "provider_channels"):
            ddl = ddl_slices[table].upper()
            self.assertNotIn(
                "CHECK",
                ddl,
                msg=(
                    f"Unexpected CHECK constraint in SQLite DDL for {table} — the channel "
                    "vocabulary must stay open, not database-enforced"
                ),
            )

    def test_no_check_constraint_on_channel_columns_postgres(self) -> None:
        ddl_slices = self._provider_table_ddl_slices(postgres_migrations)
        for table in ("provider_dimensions", "provider_channels"):
            ddl = ddl_slices[table].upper()
            self.assertNotIn(
                "CHECK",
                ddl,
                msg=(
                    f"Unexpected CHECK constraint in Postgres DDL for {table} — the channel "
                    "vocabulary must stay open, not database-enforced"
                ),
            )


if __name__ == "__main__":
    unittest.main()
