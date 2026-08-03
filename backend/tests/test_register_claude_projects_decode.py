"""Regression tests for ``decode_repo_path`` in scripts/register_claude_projects.py.

Claude Code encodes a repo path by collapsing '/', '_' and '.' all to '-', which
makes the encoding lossy and a backwards decode ambiguous: the encoded token run
``agentic-meta-dev`` could mean the single segment ``agentic_meta_dev``,
``agentic-meta-dev``, ``agentic.meta.dev``, or the three segments
``agentic/meta/dev``.

The pre-fix decoder only probed literal-dash candidates with ``os.path.isdir``, so
an underscore repo never matched and it degraded to one-token-at-a-time
consumption -- turning ``/root/agentic_meta_dev`` into ``/root/agentic/meta/dev``.
That silently broke ``project_root``-relative resolution (planDocs, progress) for
every underscore-named repo, including the launchpad itself.

The fix encodes real directory names FORWARD (the direction that is well-defined)
and compares, so any separator combination resolves in a single readdir.

These tests build a synthetic tree under ``tmp_path`` -- no dependence on the
developer's actual filesystem layout, no network, no DB.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the script module directly; scripts/ has no __init__.py and should not
# be added to sys.path permanently (mirrors test_capture_session_start_hook.py).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "register_claude_projects.py"

spec = importlib.util.spec_from_file_location("register_claude_projects", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]

decode_repo_path = _mod.decode_repo_path
encode_segment = _mod.encode_segment


def _encode_path(abs_path: Path) -> str:
    """Encode an absolute path the way Claude Code names its project dirs."""
    return "".join("-" + encode_segment(part) for part in abs_path.parts[1:])


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """A synthetic dev root holding the separator variants we care about."""
    root = tmp_path / "dev"
    for name in (
        "agentic_meta_dev",       # underscores -- the launchpad case
        "artifact_atlas",
        "citytile_pack",
        "signal_to_system",
        "agentic-research",       # genuine dashes -- must not regress
        "pediatric-anemia-site",
        "boxbrain-2",
        "skillmeat",
        "skillmeat-ce-parity",    # dashed sibling that prefixes another entry
    ):
        (root / name).mkdir(parents=True)
    return root


@pytest.mark.parametrize(
    "repo_name",
    [
        "agentic_meta_dev",
        "artifact_atlas",
        "citytile_pack",
        "signal_to_system",
        "agentic-research",
        "pediatric-anemia-site",
        "boxbrain-2",
        "skillmeat",
        "skillmeat-ce-parity",
    ],
)
def test_round_trips_every_separator_style(tree: Path, repo_name: str) -> None:
    """encode(path) -> decode() must return the original path, dashes or underscores."""
    target = tree / repo_name
    assert decode_repo_path(_encode_path(target)) == str(target)


def test_underscore_repo_is_not_split_into_segments(tree: Path) -> None:
    """The specific pre-fix failure: underscores became path separators."""
    target = tree / "agentic_meta_dev"
    decoded = decode_repo_path(_encode_path(target))
    assert decoded == str(target)
    # The exact corruption we regressed against.
    assert not decoded.endswith("agentic/meta/dev")


def test_longest_match_wins_over_shorter_real_prefix(tree: Path) -> None:
    """'skillmeat-ce-parity' must not be decoded as 'skillmeat' + leftovers.

    Both ``skillmeat`` and ``skillmeat-ce-parity`` exist, so a shortest-first
    matcher would stop at ``skillmeat`` and mangle the remainder.
    """
    target = tree / "skillmeat-ce-parity"
    assert decode_repo_path(_encode_path(target)) == str(target)


def test_dot_directory_resolves(tmp_path: Path) -> None:
    """'.claude' encodes to '--claude' (empty token); it must still resolve."""
    target = tmp_path / ".claude" / "projects"
    target.mkdir(parents=True)
    assert decode_repo_path(_encode_path(target)) == str(target)


def test_nonexistent_path_degrades_without_raising(tmp_path: Path) -> None:
    """Unknown dirs are best-effort, not fatal -- registration must not crash."""
    encoded = _encode_path(tmp_path / "no_such_repo_here")
    decoded = decode_repo_path(encoded)
    assert decoded.startswith(str(tmp_path))


def test_non_dash_prefixed_input_returned_as_is() -> None:
    """Defensive branch for unexpected input format."""
    assert decode_repo_path("not-an-encoded-dir") == "not-an-encoded-dir"


def test_encode_segment_collapses_underscore_and_dot() -> None:
    assert encode_segment("agentic_meta_dev") == "agentic-meta-dev"
    assert encode_segment("agentic.meta.dev") == "agentic-meta-dev"
    assert encode_segment("agentic-meta-dev") == "agentic-meta-dev"


# ---------------------------------------------------------------------------
# Worktree marker/parent helpers (mirrored in backend.parsers.worktree_attribution)
# ---------------------------------------------------------------------------
#
# The register script keeps the pure-string worktree helpers because it must
# run without importing ``backend`` (stdlib-only stance). The full ingest-time
# behaviour is tested in ``test_worktree_attribution.py``; the tests here only
# lock the two functions that the script itself calls, so a drift between the
# two copies would fail here fast.

parent_repo_dirname = _mod.parent_repo_dirname
worktree_marker = _mod.worktree_marker


@pytest.mark.parametrize(
    "dirname,expected_parent",
    [
        # dev-execution worktrees: <repo>/.claude/worktrees/<name>
        (
            "-Users-m-dev-agentic-meta-dev--claude-worktrees-run-01ABC",
            "-Users-m-dev-agentic-meta-dev",
        ),
        # Hermes worktrees on the node: <repo>/.git/hermes-worktrees/<name>
        (
            "-home-miethe-dev-agentic-meta-dev--git-hermes-worktrees-run-01XYZ",
            "-home-miethe-dev-agentic-meta-dev",
        ),
    ],
)
def test_parent_repo_dirname_truncates_at_marker(dirname: str, expected_parent: str) -> None:
    assert parent_repo_dirname(dirname) == expected_parent


def test_non_worktree_dir_has_no_parent_and_no_marker() -> None:
    plain = "-Users-m-dev-agentic-meta-dev"
    assert worktree_marker(plain) is None
    assert parent_repo_dirname(plain) is None


def test_no_worktrees_drops_worktree_dirs(tmp_path: Path) -> None:
    """Registration now ONLY sees canonical repos.

    Worktree sessions still get ingested (by the watcher, under the parent's
    project_id, with ``sessions.worktree_name`` set) -- they just do not get
    their own project row anymore. This test locks the "one row per repo"
    invariant at registration time.
    """
    root = tmp_path / "projects"
    (root / "-Users-m-dev-repo").mkdir(parents=True)
    wt = root / "-Users-m-dev-repo--claude-worktrees-run-1"
    wt.mkdir(parents=True)
    (wt / "a.jsonl").write_text("{}")
    (root / "-Users-m-dev-repo" / "b.jsonl").write_text("{}")

    kept = _mod.collect_candidates(
        projects_root=root, min_sessions=1, include=[], exclude=[],
        no_worktrees=True,
    )
    assert [c["dirname"] for c in kept] == ["-Users-m-dev-repo"]

    # Without --no-worktrees the worktree dir IS still collected (the flag is
    # opt-in), but no folding transform runs -- the registry would just get an
    # alias row. That is the legacy pre-schema-v46 shape; we keep the behaviour
    # so operators who opt in explicitly are not surprised.
    unfiltered = _mod.collect_candidates(
        projects_root=root, min_sessions=1, include=[], exclude=[],
        no_worktrees=False,
    )
    assert len(unfiltered) == 2
