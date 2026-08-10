"""Unit tests for the DI-4e Codex ``session_tool_usage`` backfill script.

The script lives outside the ``backend`` package (a one-shot operator tool),
so it is loaded via ``importlib`` from its file path -- same convention as
``test_backfill_worktree_attribution.py``. All tests here run with NO live
database: the pure planning functions need no DB at all, and the write-path
reuse (``PostgresSessionRepository.upsert_tool_usage``) is instead exercised
against the real ``SqliteSessionRepository`` write path on an in-memory
SQLite DB -- a genuine (non-mocked) DB round trip that proves idempotency
without ever touching Postgres.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_backfill_codex_tool_usage.py -q
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.parsers.platforms.codex.parser import _make_id as codex_make_id
from backend.parsers.sessions import parse_session_file

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = (
    _REPO_ROOT
    / ".claude"
    / "worknotes"
    / "di-4e-routing-success-rate"
    / "backfill_codex_tool_usage.py"
)

_spec = importlib.util.spec_from_file_location("backfill_codex_tool_usage", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules[_spec.name] = _mod  # dataclasses' _is_type needs the module registered
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

build_jsonl_index = _mod.build_jsonl_index
build_plan = _mod.build_plan
summarize_plan = _mod.summarize_plan
render_report = _mod.render_report
apply_plan = _mod.apply_plan
SKIP_NO_LOCAL_FILE = _mod.SKIP_NO_LOCAL_FILE
SKIP_PARSE_RETURNED_NONE = _mod.SKIP_PARSE_RETURNED_NONE

_FIXTURE = Path(__file__).parent / "fixtures" / "codex_tool_error_payloads.jsonl"

_SESSION_BASE = {
    "taskId": "",
    "status": "completed",
    "sessionType": "session",
    "model": "gpt-5",
    "platformType": "Codex",
    "platformVersion": "",
    "platformVersions": [],
    "platformVersionTransitions": [],
    "durationSeconds": 1,
    "tokensIn": 10,
    "tokensOut": 20,
    "modelIOTokens": 30,
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
    "startedAt": "2026-07-01T00:00:00Z",
    "endedAt": "2026-07-01T00:01:00Z",
    "sourceFile": "",
    "parentSessionId": None,
    "rootSessionId": "root",
    "agentId": None,
    "threadKind": "root",
    "conversationFamilyId": "root",
    "contextInheritance": "fresh",
}


def _session_dict(session_id: str, **overrides) -> dict:
    return {**_SESSION_BASE, "id": session_id, **overrides}


# ---------------------------------------------------------------------------
# 1. Id-mapping rule: 'S-' + path.stem, per codex/parser.py `_make_id`.
# ---------------------------------------------------------------------------


class IdMappingRuleTests(unittest.TestCase):
    def test_build_jsonl_index_uses_the_codebase_make_id_function(self, ) -> None:
        """The index key for a file is EXACTLY `_make_id(path)` -- not a
        reimplementation that could drift from the real parser's mapping.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            f1 = root / "rollout-2026-07-12T21-21-56-019f5911.jsonl"
            f2 = root / "sub" / "rollout-2026-07-13T00-00-00-abc123.jsonl"
            f1.write_text("{}\n")
            f2.write_text("{}\n")

            index = build_jsonl_index(root)

            self.assertEqual(index[codex_make_id(f1)], f1)
            self.assertEqual(index[codex_make_id(f2)], f2)
            self.assertEqual(len(index), 2)

    def test_simple_stem_maps_to_S_prefixed_id_verbatim(self) -> None:
        """For the common shape (letters/digits/dots/colons/underscores/
        hyphens only), the mapping is the literal 'S-' + stem -- the rule
        cited in the DI-4d re-measurement doc.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-2026-07-12T21-21-56-019f5911-abcd.jsonl"
            path.write_text("{}\n")
            index = build_jsonl_index(Path(tmp))
            self.assertEqual(
                list(index.keys()),
                [f"S-{path.stem}"],
            )

    def test_missing_root_returns_empty_index_not_an_error(self) -> None:
        self.assertEqual(build_jsonl_index(Path("/does/not/exist/anywhere")), {})


# ---------------------------------------------------------------------------
# 2. build_plan uses the CURRENT parser and reproduces its exact tool output.
# ---------------------------------------------------------------------------


class BuildPlanFixtureTests(unittest.TestCase):
    def test_matched_session_is_reparsed_and_after_tools_match_the_real_parser(self) -> None:
        session_id = codex_make_id(_FIXTURE)
        candidates = [{"id": session_id, "project_id": "proj-x"}]
        jsonl_index = {session_id: _FIXTURE}
        # Simulate the historical broken-detector state: every call recorded
        # as a success (successRate 1.0 baked into call_count == success_count).
        before = {
            session_id: [
                {"tool_name": "exec_command", "call_count": 1, "success_count": 1},
                {"tool_name": "exec", "call_count": 2, "success_count": 2},
            ]
        }

        rows = build_plan(candidates, jsonl_index, before)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsNone(row.skip_reason)
        self.assertEqual(row.session_id, session_id)
        self.assertEqual(row.project_id, "proj-x")

        expected_after = [t.model_dump() for t in parse_session_file(_FIXTURE).toolsUsed]
        self.assertEqual(row.after_tools, expected_after)
        # Headline of the whole backfill: re-parsing must surface errors that
        # the stale "before" rows recorded as zero.
        after_by_name = {t["name"]: t for t in row.after_tools}
        self.assertLess(after_by_name["exec"]["successRate"], 1.0)

    def test_summary_and_report_reflect_the_before_after_delta(self) -> None:
        session_id = codex_make_id(_FIXTURE)
        candidates = [{"id": session_id, "project_id": "proj-x"}]
        jsonl_index = {session_id: _FIXTURE}
        before = {session_id: [{"tool_name": "exec", "call_count": 2, "success_count": 2}]}

        rows = build_plan(candidates, jsonl_index, before)
        summary = summarize_plan(rows)

        self.assertEqual(summary["matched"], 1)
        self.assertEqual(summary["total_candidates"], 1)
        self.assertEqual(summary["skip_counts"], {})
        exec_delta = summary["tool_delta"]["exec"]
        self.assertEqual(exec_delta["before_calls"], 2)
        self.assertEqual(exec_delta["before_success"], 2)
        self.assertEqual(exec_delta["after_calls"], 2)
        # exec successRate is 0.5 in the fixture -> truncated success == 1
        self.assertEqual(exec_delta["after_success"], 1)

        report = render_report(summary)
        self.assertIn("coverage: 1/1", report)
        self.assertIn("exec:", report)


# ---------------------------------------------------------------------------
# 3. Missing local file -> left completely untouched, reported not zeroed.
# ---------------------------------------------------------------------------


class MissingFilePathTests(unittest.IsolatedAsyncioTestCase):
    def test_build_plan_flags_missing_file_with_before_tools_preserved(self) -> None:
        candidates = [{"id": "S-does-not-exist", "project_id": "proj-x"}]
        before = {
            "S-does-not-exist": [
                {"tool_name": "exec", "call_count": 10, "success_count": 10},
            ]
        }
        rows = build_plan(candidates, jsonl_index={}, before_tool_usage=before)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.skip_reason, SKIP_NO_LOCAL_FILE)
        self.assertEqual(row.after_tools, [])
        # The row still carries the historical values for reporting -- they
        # are not discarded, just never overwritten.
        self.assertEqual(row.before_tools, before["S-does-not-exist"])

    def test_parse_returned_none_is_also_skipped_not_zeroed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            empty_path = Path(tmp) / "rollout-empty.jsonl"
            empty_path.write_text("")  # parse_session_file returns None for empty files
            session_id = codex_make_id(empty_path)
            candidates = [{"id": session_id, "project_id": "proj-x"}]
            jsonl_index = {session_id: empty_path}

            rows = build_plan(candidates, jsonl_index, before_tool_usage={})

            self.assertEqual(rows[0].skip_reason, SKIP_PARSE_RETURNED_NONE)
            self.assertEqual(rows[0].after_tools, [])

    async def test_apply_plan_never_calls_upsert_for_a_skipped_row(self) -> None:
        candidates = [{"id": "S-does-not-exist", "project_id": "proj-x"}]
        before = {"S-does-not-exist": [{"tool_name": "exec", "call_count": 10, "success_count": 10}]}
        rows = build_plan(candidates, jsonl_index={}, before_tool_usage=before)

        class BoomIfCalled:
            async def upsert_tool_usage(self, *args, **kwargs) -> None:
                raise AssertionError("upsert_tool_usage must not be called for a skipped row")

        written = await apply_plan(BoomIfCalled(), rows)
        self.assertEqual(written, 0)


# ---------------------------------------------------------------------------
# 4. Dry-run performs zero writes.
# ---------------------------------------------------------------------------


class DryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_never_invokes_apply_plan(self) -> None:
        args = argparse.Namespace(
            apply=False,
            window_days=30,
            codex_sessions_root=Path("/does/not/matter"),
            limit=None,
        )

        class FakePool:
            async def close(self) -> None:
                return None

        fake_pool = FakePool()

        with patch.dict(os.environ, {"CCDASH_DSN": "postgres://fake-dsn-never-used"}), \
            patch.object(_mod, "_open_pool", new=AsyncMock(return_value=fake_pool)) as mock_open, \
            patch.object(_mod, "fetch_codex_candidates", new=AsyncMock(return_value=[])), \
            patch.object(_mod, "fetch_existing_tool_usage", new=AsyncMock(return_value={})), \
            patch.object(_mod, "build_jsonl_index", return_value={}), \
            patch.object(_mod, "apply_plan", new=AsyncMock()) as mock_apply:
            result = await _mod._async_main(args)

        self.assertEqual(result, 0)
        mock_open.assert_awaited_once()
        mock_apply.assert_not_called()

    async def test_apply_true_does_invoke_apply_plan(self) -> None:
        """Sanity counterpart: --apply DOES reach apply_plan (still fully mocked)."""
        args = argparse.Namespace(
            apply=True,
            window_days=30,
            codex_sessions_root=Path("/does/not/matter"),
            limit=None,
        )

        class FakePool:
            async def close(self) -> None:
                return None

        fake_pool = FakePool()

        with patch.dict(os.environ, {"CCDASH_DSN": "postgres://fake-dsn-never-used"}), \
            patch.object(_mod, "_open_pool", new=AsyncMock(return_value=fake_pool)), \
            patch.object(_mod, "fetch_codex_candidates", new=AsyncMock(return_value=[])), \
            patch.object(_mod, "fetch_existing_tool_usage", new=AsyncMock(return_value={})), \
            patch.object(_mod, "build_jsonl_index", return_value={}), \
            patch.object(_mod, "apply_plan", new=AsyncMock(return_value=0)) as mock_apply, \
            patch(
                "backend.db.repositories.postgres.sessions.PostgresSessionRepository",
                autospec=True,
            ):
            result = await _mod._async_main(args)

        self.assertEqual(result, 0)
        mock_apply.assert_awaited_once()

    async def test_missing_dsn_env_var_aborts_before_any_pool_open(self) -> None:
        args = argparse.Namespace(
            apply=False, window_days=30, codex_sessions_root=Path("/x"), limit=None
        )
        env = dict(os.environ)
        env.pop("CCDASH_DSN", None)
        with patch.dict(os.environ, env, clear=True), \
            patch.object(_mod, "_open_pool", new=AsyncMock()) as mock_open:
            result = await _mod._async_main(args)
        self.assertEqual(result, 2)
        mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Idempotency -- real (non-mocked) write path against an in-memory SQLite
#    DB. `apply_plan` is repo-agnostic (duck-typed on upsert_tool_usage), so
#    this exercises the exact same contract the real PostgresSessionRepository
#    honours, without ever touching Postgres.
# ---------------------------------------------------------------------------


class IdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)

        self.session_id = codex_make_id(_FIXTURE)
        self.project_id = "proj-idempotency"
        # session_tool_usage has an FK on (project_id, session_id) -> sessions;
        # seed the parent row first.
        await self.repo.upsert(_session_dict(self.session_id), self.project_id)
        await self.db.commit()

        # Seed the STALE state a broken-detector write would have produced:
        # every call recorded as a success.
        await self.repo.upsert_tool_usage(
            self.session_id,
            [{"name": "exec", "count": 2, "successRate": 1.0, "totalMs": 100}],
            self.project_id,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _rows(self) -> list[dict]:
        return await self.repo.get_tool_usage(self.session_id)

    async def test_apply_plan_overwrites_stale_rows_with_reparsed_truth(self) -> None:
        candidates = [{"id": self.session_id, "project_id": self.project_id}]
        jsonl_index = {self.session_id: _FIXTURE}
        before = {
            r["tool_name"]: r
            for r in await self._rows()
        }
        before_map = {self.session_id: list(before.values())}

        rows = build_plan(candidates, jsonl_index, before_map)
        written = await apply_plan(self.repo, rows)
        self.assertEqual(written, 1)

        after_rows = {r["tool_name"]: r for r in await self._rows()}
        # `exec` in the fixture has 2 calls / successRate 0.5 -> 1 success,
        # not the stale 2/2 the pre-fix detector wrote.
        self.assertEqual(after_rows["exec"]["call_count"], 2)
        self.assertEqual(after_rows["exec"]["success_count"], 1)

    async def test_running_apply_plan_twice_is_idempotent(self) -> None:
        candidates = [{"id": self.session_id, "project_id": self.project_id}]
        jsonl_index = {self.session_id: _FIXTURE}

        rows = build_plan(candidates, jsonl_index, before_tool_usage={})
        await apply_plan(self.repo, rows)
        first_pass = sorted(await self._rows(), key=lambda r: r["tool_name"])

        # Re-run against the SAME (now up to date) DB state and the SAME
        # local file -- end state must be byte-for-byte identical.
        rows_again = build_plan(candidates, jsonl_index, before_tool_usage={})
        await apply_plan(self.repo, rows_again)
        second_pass = sorted(await self._rows(), key=lambda r: r["tool_name"])

        self.assertEqual(
            [dict(r) for r in first_pass],
            [dict(r) for r in second_pass],
        )
        self.assertTrue(first_pass, "fixture produced no tool_usage rows to compare")


if __name__ == "__main__":
    unittest.main()
