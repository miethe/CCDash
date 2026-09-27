"""Regression coverage for legacy and reversible worktree backfills."""
from __future__ import annotations
import asyncio
import importlib.util
from pathlib import Path
from backend.scripts.backfill_worktree_attribution import Change, apply_changes, plan_changes, read_undo_file, undo_changes, write_undo_file

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location("legacy_backfill", _REPO_ROOT / "scripts" / "backfill_worktree_attribution.py")
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]
plan, parent_project_id_for_row = _mod.plan, _mod.parent_project_id_for_row
PARENT_DIR, WT_DIR, HERMES_WT_DIR = "-Users-m-dev-agentic-meta-dev", "-Users-m-dev-agentic-meta-dev--claude-worktrees-run-01ABC", "-home-miethe-dev-agentic-meta-dev--git-hermes-worktrees-run-01XYZ"
def _src(dirname: str, session_id: str = "sess-a") -> str: return str(Path.home() / ".claude" / "projects" / dirname / f"{session_id}.jsonl")
def _stable_id(dirname: str) -> str:
 import hashlib
 return "ccp-" + hashlib.sha1(dirname.encode()).hexdigest()[:12]
PARENT_ID, WT_ID = _stable_id(PARENT_DIR), _stable_id(WT_DIR)

def test_parent_project_id_from_source_matches_stable_project_id(): assert parent_project_id_for_row(_src(WT_DIR), None) == PARENT_ID
def test_non_worktree_source_returns_none(): assert parent_project_id_for_row(_src(PARENT_DIR), None) is None
def test_empty_source_returns_none(): assert parent_project_id_for_row("", None) is None
def test_cwd_shape_resolves_parent_via_encoding(): assert parent_project_id_for_row("ccdash-source:v1/ccp-9999/session/some.jsonl", "/Users/m/dev/agentic-meta-dev/.claude/worktrees/run-01ABC") == PARENT_ID
def test_codex_worktree_cwd_returns_none_for_parent(): assert parent_project_id_for_row(None, "/Users/m/.codex/worktrees/b0d1/skillmeat") is None
def test_move_and_label_when_parent_is_registered():
 result = plan([("s1", WT_ID, _src(WT_DIR), None, None)], known_project_ids={PARENT_ID, WT_ID})
 assert result["move_and_label"] == [("s1", WT_ID, "run-01ABC", PARENT_ID)]
 assert result["label_only"] == [] and result["skip_already_done"] == []
def test_label_only_when_parent_is_not_registered():
 result = plan([("s1", WT_ID, _src(WT_DIR), None, None)], known_project_ids={WT_ID})
 assert result["move_and_label"] == [] and result["label_only"] == [("s1", WT_ID, "run-01ABC")]
def test_skip_when_already_moved_and_labeled():
 result = plan([("s1", PARENT_ID, _src(WT_DIR), None, "run-01ABC")], known_project_ids={PARENT_ID})
 assert result["move_and_label"] == [] and result["label_only"] == [] and result["skip_already_done"] == ["s1"]
def test_label_still_planned_when_only_project_id_is_correct():
 result = plan([("s1", PARENT_ID, _src(WT_DIR), None, None)], known_project_ids={PARENT_ID})
 assert result["label_only"] == [("s1", PARENT_ID, "run-01ABC")] and result["move_and_label"] == []
def test_hermes_worktree_layout_also_planned():
 parent = _stable_id("-home-miethe-dev-agentic-meta-dev")
 result = plan([("s1", _stable_id(HERMES_WT_DIR), _src(HERMES_WT_DIR), None, None)], known_project_ids={parent, _stable_id(HERMES_WT_DIR)})
 assert result["move_and_label"] == [("s1", _stable_id(HERMES_WT_DIR), "run-01XYZ", parent)]
def test_cwd_only_row_gets_moved_and_labeled_when_parent_exists():
 result = plan([("s-codex", "ccp-9999", "ccdash-source:v1/ccp-9999/session/x.jsonl", "/Users/m/dev/agentic-meta-dev/.claude/worktrees/run-01ABC", None)], known_project_ids={PARENT_ID})
 assert result["move_and_label"] == [("s-codex", "ccp-9999", "run-01ABC", PARENT_ID)]
def test_row_with_unparseable_source_is_skipped_no_label():
 result = plan([("s1", PARENT_ID, _src(PARENT_DIR), None, None)], known_project_ids={PARENT_ID})
 assert result["skip_no_label"] == ["s1"] and result["label_only"] == [] and result["move_and_label"] == []
def test_mixed_batch_partitions_correctly():
 rows=[("s-mv",WT_ID,_src(WT_DIR,"s-mv"),None,None),("s-cwd","ccp-9999","ccdash-source:v1/ccp-9999/session/x.jsonl","/Users/m/dev/agentic-meta-dev/.claude/worktrees/run-01ABC",None),("s-lbl",_stable_id("-Users-m-dev-orphan"),_src("-Users-m-dev-orphan--claude-worktrees-x","s-lbl"),None,None),("s-done",PARENT_ID,_src(WT_DIR,"s-done"),None,"run-01ABC"),("s-skip",PARENT_ID,_src(PARENT_DIR,"s-skip"),None,None)]
 result=plan(rows,known_project_ids={PARENT_ID})
 assert sorted(r[0] for r in result["move_and_label"]) == ["s-cwd","s-mv"] and [r[0] for r in result["label_only"]] == ["s-lbl"] and result["skip_already_done"] == ["s-done"] and result["skip_no_label"] == ["s-skip"]

class _FakeConnection:
 def __init__(self, rows): self.rows=rows
 async def execute(self, _query, new, session_id, old):
  old_key,new_key=(old,session_id),(new,session_id)
  if old_key not in self.rows or new_key in self.rows: return "UPDATE 0"
  row=self.rows.pop(old_key); row["project_id"]=new; self.rows[new_key]=row; return "UPDATE 1"
def test_unique_basename_match_moves_from_catch_all():
 changes, totals=plan_changes([{"id":"s1","project_id":"catch","cwd":"/Users/miethe/.codex/worktrees/a1/CCDash/src"}],[{"id":"catch","repo_path":"/Users/miethe"},{"id":"ccdash","repo_path":"/code/CCDash"}])
 assert changes == [Change("s1","catch","ccdash")] and totals.moved == 1 and totals.ambiguous == 0
def test_ambiguous_basename_moves_to_existing_unattributed_bucket():
 changes, totals=plan_changes([{"id":"s1","project_id":"catch","cwd":"/Users/miethe/.codex/worktrees/a1/repo/src"}],[{"id":"one","repo_path":"/code/repo"},{"id":"two","repo_path":"/other/repo"}])
 assert changes == [Change("s1","catch","")] and totals.moved == 1 and totals.ambiguous == 1
def test_already_migrated_row_is_a_noop():
 changes, totals=plan_changes([{"id":"s1","project_id":"ccdash","cwd":"/Users/miethe/.codex/worktrees/a1/CCDash"}],[{"id":"ccdash","repo_path":"/code/CCDash"}])
 assert changes == [] and totals.moved == 0 and totals.skipped == 1
def test_undo_restores_exact_prior_project(tmp_path: Path):
 change=Change("s1","catch","ccdash"); path=write_undo_file([change],tmp_path); assert read_undo_file(path)==[change]
 connection=_FakeConnection({("catch","s1"):{"project_id":"catch"}}); assert asyncio.run(apply_changes(connection,[change])) == 1; assert asyncio.run(undo_changes(connection,read_undo_file(path))) == 1; assert ("catch","s1") in connection.rows
