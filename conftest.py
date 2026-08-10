"""Root pytest configuration.

Holds the collection/setup-error guard.  See ``pytest_terminal_summary`` below for
why "errors" need louder handling than pytest gives them by default.
"""
from __future__ import annotations

from collections import defaultdict


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Make collection/setup errors impossible to mistake for environment noise.

    Background: ``backend/tests/test_client_v1_contract.py`` sat 100% dead for an
    unknown period — all 37 tests errored at ``setUpClass`` because a ``mock.patch``
    target (``backend.runtime_ports.project_manager``) had been removed by ADR-006.
    ``mock.patch`` resolves its target at setup, so every test errored before its
    body ran, and the ``/api/v1`` envelope contract had no guard at all.

    pytest *does* already exit non-zero on such errors, so the exit code was never
    the problem.  What hid this was the *reporting*: errors are summarised as their
    own category, and N uniform setup errors in one file read like a local
    environment problem rather than lost coverage.  This hook restates them as
    lost coverage, grouped by file with a count, so the signal is legible.
    """
    _ = config  # part of the pytest hook signature; unused here
    error_reports = terminalreporter.stats.get("error", [])
    if not error_reports:
        return

    by_file: dict[str, int] = defaultdict(int)
    for report in error_reports:
        nodeid = getattr(report, "nodeid", "") or "<unknown>"
        by_file[nodeid.split("::", 1)[0]] += 1

    terminalreporter.write_sep("=", "LOST COVERAGE — collection/setup errors", red=True, bold=True)
    terminalreporter.write_line(
        "These tests never executed. An error is not a pass and not a skip: the "
        "assertions below were NOT run, so whatever they guard is currently unguarded."
    )
    for path, count in sorted(by_file.items(), key=lambda kv: (-kv[1], kv[0])):
        terminalreporter.write_line(f"  {count:>4} error(s)  {path}")
    terminalreporter.write_line(
        "If every test in a file errors identically, suspect a stale patch target or "
        "fixture rather than your environment — see backend/tests/test_patch_targets_resolve.py."
    )

    # Defensive: pytest already fails the run on collection/setup errors, but an
    # error-only run under --continue-on-collection-errors (or a teardown-only
    # error) must not be allowed to report success.
    if exitstatus == 0:
        session = getattr(terminalreporter, "_session", None)
        if session is not None:
            session.exitstatus = 1
