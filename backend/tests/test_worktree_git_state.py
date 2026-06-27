import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.application.services.worktree_git_state import WorktreeGitStateProbe


class WorktreeGitStateProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_worktree_path_degrades_without_exception(self) -> None:
        probe = WorktreeGitStateProbe()

        state = await probe.probe("/tmp/ccdash-definitely-missing-worktree")

        self.assertFalse(state.path_exists)
        self.assertTrue(state.warnings)

    async def test_probe_collects_head_dirty_stash_and_upstream_when_git_succeeds(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(cwd: Path, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
            calls.append(tuple(args))
            output = {
                ("rev-parse", "--short", "HEAD"): "abc1234\n",
                ("status", "--porcelain"): " M file.txt\n?? new.txt\n",
                ("stash", "list"): "stash@{0}: WIP\n",
                ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/main\n",
                ("rev-list", "--left-right", "--count", "origin/main...HEAD"): "1\t2\n",
            }.get(tuple(args), "")
            return subprocess.CompletedProcess(["git", *args], 0, output, "")

        with tempfile.TemporaryDirectory() as tmp:
            probe = WorktreeGitStateProbe(runner=runner)
            state = await probe.probe(tmp)

        self.assertTrue(state.path_exists)
        self.assertEqual(state.head, "abc1234")
        self.assertEqual(state.dirty_count, 2)
        self.assertEqual(state.stash_count, 1)
        self.assertEqual(state.upstream, "origin/main")
        self.assertEqual(state.behind, 1)
        self.assertEqual(state.ahead, 2)
        self.assertIn(("rev-parse", "--short", "HEAD"), calls)


if __name__ == "__main__":
    unittest.main()
