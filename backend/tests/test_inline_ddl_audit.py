"""CI audit: no repository-layer file may contain inline CREATE TABLE IF NOT EXISTS
for a migration-managed table.

Background
----------
Phase 1 of the DB-remediation plan (CCDash ADR-006) guarantees that the
migration runner executes before any repository method is called.  Phase 3
(T3-010) removes the inline ``CREATE TABLE IF NOT EXISTS projects`` DDL from
both ``SqliteProjectRepository.ensure_table`` and
``PostgresProjectRepository.ensure_table`` and replaces it with a guard that
raises ``RuntimeError`` if the table is absent (i.e. migrations didn't run).

This test module enforces that invariant for all future changes: no file under
``backend/db/repositories/`` may contain a bare ``CREATE TABLE IF NOT EXISTS
<table>`` for any table that the canonical migration files also create.

Intentional exceptions
----------------------
Some inline ``CREATE TABLE IF NOT EXISTS`` statements are intentional and must
NOT be flagged by this scanner.  Each such statement must carry a
``# noqa: inline-ddl`` comment on the *same source line* as the
``CREATE TABLE IF NOT EXISTS`` token.  Document each exception here:

  backend/tests/test_health_detail_fields.py::_seed_projects_db
    Creates a minimal ``projects`` table schema for the warm-start health-probe
    tests.  This is test-only scaffolding that runs against an in-memory or
    temp-file SQLite DB.  The ``_build_registry_detail`` function catches
    ``RuntimeError`` from ``ensure_table`` so the probe itself is unaffected;
    ``_seed_projects_db`` exists purely to populate enough rows for the
    project-count assertion.  Marked with ``# noqa: inline-ddl``.

Scope
-----
Scanned tree: ``backend/db/repositories/`` (production repository layer only).
Test files are *not* scanned because test-only scaffolding may legitimately
create tables inline.  The only production path that matters is the repository
layer.
"""
from __future__ import annotations

import re
import textwrap
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]  # → <worktree>/backend/..
_REPOSITORIES_DIR = _REPO_ROOT / "backend" / "db" / "repositories"

# Regex: matches "CREATE TABLE IF NOT EXISTS [schema.]<table>" on a single
# logical line of source code.  Multi-line DDL strings are handled by scanning
# line-by-line; if the keyword and table name appear on the same line (which
# is the overwhelmingly common pattern in Python f-strings and triple-quoted
# strings), the match fires.  DDL split across multiple lines is not flagged
# (deliberate: the scanner targets the common single-line form seen in
# repository ensure_table bodies).
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"
    r"(?:[a-zA-Z_][a-zA-Z0-9_]*\.)?"   # optional schema prefix
    r"([a-zA-Z_][a-zA-Z0-9_]*)",        # captured table name
    re.IGNORECASE,
)

# Marker that exempts a line from the scanner.
_NOQA_MARKER = "# noqa: inline-ddl"


def _get_migration_tables() -> frozenset[str]:
    """Return the canonical set of migration-managed tables for SQLite.

    Uses ``migration_governance.get_sqlite_migration_tables()`` which scans
    ``_TABLES`` and ``_TEST_VISUALIZER_TABLES`` in ``sqlite_migrations.py``.
    The Postgres canonical set is a superset of SQLite's, so checking SQLite
    is sufficient for the common tables (including ``projects``).
    """
    from backend.db.migration_governance import get_sqlite_migration_tables
    return get_sqlite_migration_tables()


def _find_violations(
    search_dir: Path,
    canonical_tables: frozenset[str],
) -> list[tuple[Path, int, str, str]]:
    """Scan *search_dir* recursively for inline-DDL violations.

    Returns a list of (file_path, line_number, table_name, line_text) tuples
    for each violation found.  Lines containing ``# noqa: inline-ddl`` are
    skipped.
    """
    violations: list[tuple[Path, int, str, str]] = []
    for py_file in sorted(search_dir.rglob("*.py")):
        # Skip __pycache__ and compiled artefacts
        if "__pycache__" in py_file.parts:
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(source.splitlines(), start=1):
            # Lines with the noqa marker are intentional exceptions.
            if _NOQA_MARKER in line:
                continue
            match = _CREATE_TABLE_RE.search(line)
            if match:
                table_name = match.group(1).lower()
                if table_name in canonical_tables:
                    violations.append((py_file, lineno, table_name, line.strip()))

    return violations


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestInlineDDLAudit(unittest.TestCase):
    """AC-008: zero inline CREATE TABLE IF NOT EXISTS hits for migration-managed
    tables in the repository layer.

    The test scans ``backend/db/repositories/`` only (test files are excluded
    from the scan — test-only scaffolding may legitimately seed tables inline,
    provided such lines carry ``# noqa: inline-ddl``).
    """

    def test_no_inline_ddl_in_repository_layer(self) -> None:
        """Zero inline CREATE TABLE IF NOT EXISTS for migration-managed tables
        in backend/db/repositories/**."""
        canonical = _get_migration_tables()
        self.assertIn(
            "projects",
            canonical,
            "Precondition: 'projects' must be in the canonical migration table set "
            "(check sqlite_migrations._TABLES / migration_governance).",
        )

        violations = _find_violations(_REPOSITORIES_DIR, canonical)

        if violations:
            details = "\n".join(
                f"  {v[0].relative_to(_REPO_ROOT)}:{v[1]}  table={v[2]!r}\n"
                f"    {v[3]}"
                for v in violations
            )
            self.fail(
                "Found inline CREATE TABLE IF NOT EXISTS for migration-managed table(s) "
                "in the repository layer.  Remove the inline DDL and replace it with a "
                "migration-guard (see SqliteProjectRepository.ensure_table for the "
                "canonical pattern).\n\n"
                "Violations:\n"
                + textwrap.indent(details, "  ")
            )

    def test_noqa_marker_documented(self) -> None:
        """Every # noqa: inline-ddl marker in the repository layer must be for a
        migration-managed table.  (Prevents stale noqa markers from silencing
        future violations.)"""
        canonical = _get_migration_tables()
        stale_noqa: list[tuple[Path, int, str]] = []

        for py_file in sorted(_REPOSITORIES_DIR.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for lineno, line in enumerate(source.splitlines(), start=1):
                if _NOQA_MARKER not in line:
                    continue
                match = _CREATE_TABLE_RE.search(line)
                if match:
                    table_name = match.group(1).lower()
                    if table_name not in canonical:
                        stale_noqa.append(
                            (py_file, lineno, f"table={table_name!r} not in canonical set")
                        )
                else:
                    # noqa marker present but no CREATE TABLE — stale marker
                    stale_noqa.append(
                        (py_file, lineno, "# noqa: inline-ddl without CREATE TABLE statement")
                    )

        if stale_noqa:
            details = "\n".join(
                f"  {v[0].relative_to(_REPO_ROOT)}:{v[1]}  {v[2]}"
                for v in stale_noqa
            )
            self.fail(
                "Stale or misapplied # noqa: inline-ddl markers found in the repository "
                "layer:\n" + details
            )


if __name__ == "__main__":
    unittest.main()
