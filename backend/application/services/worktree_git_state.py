"""Safe, cached git status probing for known planning worktrees."""
from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from backend.application.services.agent_queries.models import PlanningCommandCenterGitStateDTO


GitRunner = Callable[[Path, list[str], float], subprocess.CompletedProcess[str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_runner(cwd: Path, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


class WorktreeGitStateProbe:
    """Probe a known worktree path without letting git failures break rows."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 5.0,
        timeout_seconds: float = 0.8,
        runner: GitRunner | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _default_runner
        self._cache: dict[str, tuple[float, PlanningCommandCenterGitStateDTO]] = {}

    async def probe(self, worktree_path: str) -> PlanningCommandCenterGitStateDTO:
        token = str(worktree_path or "").strip()
        if not token:
            return PlanningCommandCenterGitStateDTO(
                path_exists=None,
                probed_at=_now_iso(),
                warnings=["No worktree path is stored for this feature."],
            )

        path = Path(token).expanduser()
        cache_key = str(path)
        loop = asyncio.get_running_loop()
        now = loop.time()
        cached = self._cache.get(cache_key)
        if cached is not None and now - cached[0] <= self.ttl_seconds:
            return cached[1]

        state = await asyncio.to_thread(self._probe_sync, path)
        self._cache[cache_key] = (now, state)
        return state

    def _probe_sync(self, path: Path) -> PlanningCommandCenterGitStateDTO:
        warnings: list[str] = []
        if not path.exists():
            return PlanningCommandCenterGitStateDTO(
                path_exists=False,
                probed_at=_now_iso(),
                warnings=[f"Worktree path does not exist: {path}"],
            )

        def git(args: list[str]) -> str:
            try:
                completed = self._runner(path, args, self.timeout_seconds)
            except subprocess.TimeoutExpired:
                warnings.append(f"git {' '.join(args)} timed out")
                return ""
            except Exception as exc:
                warnings.append(f"git {' '.join(args)} failed: {exc}")
                return ""
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                if stderr:
                    warnings.append(stderr.splitlines()[0])
                return ""
            return (completed.stdout or "").strip()

        head = git(["rev-parse", "--short", "HEAD"])
        dirty_output = git(["status", "--porcelain"])
        stash_output = git(["stash", "list"])
        upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        ahead = behind = None
        if upstream:
            counts = git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
            parts = counts.split()
            if len(parts) >= 2:
                try:
                    behind = int(parts[0])
                    ahead = int(parts[1])
                except ValueError:
                    warnings.append("Unable to parse ahead/behind counts.")

        return PlanningCommandCenterGitStateDTO(
            path_exists=True,
            head=head,
            dirty_count=len([line for line in dirty_output.splitlines() if line.strip()]),
            stash_count=len([line for line in stash_output.splitlines() if line.strip()]),
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            probed_at=_now_iso(),
            warnings=warnings,
        )
