"""Unit tests for the worktree-attribution backfill planner.

The backfill re-points historical rows and stamps ``worktree_name``. Writes are
irreversible, so the planner (which decides WHICH rows to move and WHICH to
only label) is the load-bearing piece here. This test file exercises it in
isolation -- no DB, no psycopg -- via importlib so the script's stdlib-only
entry point stays honest.

The DB-touching passes (``_fetch_candidates``, ``_known_project_ids``,
``_apply``) are covered by integration on the live snapshot before the operator
runs ``--apply``, not here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "backfill_worktree_attribution.py"

spec = importlib.util.spec_from_file_location("backfill_worktree_attribution", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]

plan = _mod.plan
parent_project_id_for_row = _mod.parent_project_id_for_row


PARENT_DIR = "-Users-m-dev-agentic-meta-dev"
WT_DIR = "-Users-m-dev-agentic-meta-dev--claude-worktrees-run-01ABC"
HERMES_WT_DIR = "-home-miethe-dev-agentic-meta-dev--git-hermes-worktrees-run-01XYZ"


def _src(dirname: str, session_id: str = "sess-a") -> str:
    return str(Path.home() / ".claude" / "projects" / dirname / f"{session_id}.jsonl")


# Real hash used by scripts/register_claude_projects.stable_project_id and by
# the backfill's own parent_project_id_from_source; computed once so the tests
# assert the CONTRACT rather than mirror the implementation.
def _stable_id(dirname: str) -> str:
    import hashlib

    return "ccp-" + hashlib.sha1(dirname.encode()).hexdigest()[:12]


PARENT_ID = _stable_id(PARENT_DIR)
WT_ID = _stable_id(WT_DIR)


def test_parent_project_id_from_source_matches_stable_project_id() -> None:
    """Contract lock: backfill and register script MUST produce the same id.

    Any drift here silently prevents move-and-label rows from resolving to a
    registered parent project, downgrading them to label-only.
    """
    assert parent_project_id_for_row(_src(WT_DIR), None) == PARENT_ID


def test_non_worktree_source_returns_none() -> None:
    assert parent_project_id_for_row(_src(PARENT_DIR), None) is None


def test_empty_source_returns_none() -> None:
    assert parent_project_id_for_row("", None) is None


def test_cwd_shape_resolves_parent_via_encoding() -> None:
    """The historical shape: source_file is a canonical id, cwd is the fs path.

    Claude collapses '/', '_' and '.' all to '-', so
    ``/Users/m/dev/agentic-meta-dev/.claude/worktrees/x`` encodes to
    ``-Users-m-dev-agentic-meta-dev`` for the parent -- same PARENT_ID.
    """
    cwd = "/Users/m/dev/agentic-meta-dev/.claude/worktrees/run-01ABC"
    canonical_source = "ccdash-source:v1/ccp-9999/session/some.jsonl"  # not a fs path
    assert parent_project_id_for_row(canonical_source, cwd) == PARENT_ID


def test_codex_worktree_cwd_returns_none_for_parent() -> None:
    """Codex ~/.codex/worktrees/<hash>/<repo> cannot resolve without a probe."""
    cwd = "/Users/m/.codex/worktrees/b0d1/skillmeat"
    assert parent_project_id_for_row(None, cwd) is None


def test_move_and_label_when_parent_is_registered() -> None:
    """Session sits on the worktree's own id, parent exists -> re-point + stamp."""
    rows = [("s1", WT_ID, _src(WT_DIR), None, None)]
    result = plan(rows, known_project_ids={PARENT_ID, WT_ID})

    assert result["move_and_label"] == [("s1", WT_ID, "run-01ABC", PARENT_ID)]
    assert result["label_only"] == []
    assert result["skip_already_done"] == []


def test_label_only_when_parent_is_not_registered() -> None:
    """No parent row exists -> we must not orphan the session; only stamp label."""
    rows = [("s1", WT_ID, _src(WT_DIR), None, None)]
    result = plan(rows, known_project_ids={WT_ID})  # parent NOT in registry

    assert result["move_and_label"] == []
    assert result["label_only"] == [("s1", WT_ID, "run-01ABC")]


def test_skip_when_already_moved_and_labeled() -> None:
    """Idempotency: rerunning the backfill must not queue any writes."""
    rows = [("s1", PARENT_ID, _src(WT_DIR), None, "run-01ABC")]
    result = plan(rows, known_project_ids={PARENT_ID})

    assert result["move_and_label"] == []
    assert result["label_only"] == []
    assert result["skip_already_done"] == ["s1"]


def test_label_still_planned_when_only_project_id_is_correct() -> None:
    """Partial state: on the right project but no label yet -> stamp only."""
    rows = [("s1", PARENT_ID, _src(WT_DIR), None, None)]
    result = plan(rows, known_project_ids={PARENT_ID})

    assert result["label_only"] == [("s1", PARENT_ID, "run-01ABC")]
    assert result["move_and_label"] == []


def test_hermes_worktree_layout_also_planned() -> None:
    hermes_parent = "-home-miethe-dev-agentic-meta-dev"
    hermes_parent_id = _stable_id(hermes_parent)
    rows = [("s1", _stable_id(HERMES_WT_DIR), _src(HERMES_WT_DIR), None, None)]
    result = plan(rows, known_project_ids={hermes_parent_id, _stable_id(HERMES_WT_DIR)})

    assert result["move_and_label"] == [
        ("s1", _stable_id(HERMES_WT_DIR), "run-01XYZ", hermes_parent_id),
    ]


def test_cwd_only_row_gets_moved_and_labeled_when_parent_exists() -> None:
    """The dominant historical shape: derivation MUST come from cwd, not source."""
    canonical = "ccdash-source:v1/ccp-9999/session/x.jsonl"
    cwd = "/Users/m/dev/agentic-meta-dev/.claude/worktrees/run-01ABC"
    rows = [("s-codex", "ccp-9999", canonical, cwd, None)]
    result = plan(rows, known_project_ids={PARENT_ID})

    assert result["move_and_label"] == [("s-codex", "ccp-9999", "run-01ABC", PARENT_ID)]


def test_row_with_unparseable_source_is_skipped_no_label() -> None:
    """Source path exists but is not a worktree -> skip without touching row."""
    rows = [("s1", PARENT_ID, _src(PARENT_DIR), None, None)]
    result = plan(rows, known_project_ids={PARENT_ID})

    assert result["skip_no_label"] == ["s1"]
    assert result["label_only"] == []
    assert result["move_and_label"] == []


def test_mixed_batch_partitions_correctly() -> None:
    """A realistic 5-row batch hits every branch exactly once."""
    rows = [
        # move + label via SOURCE (Claude-shape)
        ("s-mv", WT_ID, _src(WT_DIR, "s-mv"), None, None),
        # move + label via CWD (Codex-shape) -- the historical majority
        ("s-cwd", "ccp-9999",
         "ccdash-source:v1/ccp-9999/session/x.jsonl",
         "/Users/m/dev/agentic-meta-dev/.claude/worktrees/run-01ABC",
         None),
        # label-only: parent NOT registered
        ("s-lbl", _stable_id("-Users-m-dev-orphan"),
         _src("-Users-m-dev-orphan--claude-worktrees-x", "s-lbl"),
         None, None),
        # already done
        ("s-done", PARENT_ID, _src(WT_DIR, "s-done"), None, "run-01ABC"),
        # non-worktree source
        ("s-skip", PARENT_ID, _src(PARENT_DIR, "s-skip"), None, None),
    ]
    result = plan(rows, known_project_ids={PARENT_ID})

    assert sorted(r[0] for r in result["move_and_label"]) == ["s-cwd", "s-mv"]
    assert [r[0] for r in result["label_only"]] == ["s-lbl"]
    assert result["skip_already_done"] == ["s-done"]
    assert result["skip_no_label"] == ["s-skip"]
