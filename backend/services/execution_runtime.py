"""Runtime manager for local execution workbench runs."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from typing import Any

from backend.db.factory import get_execution_repository


logger = logging.getLogger("ccdash.execution.runtime")

_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "TERM",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "PYTHONPATH",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_text(value: str, size: int = 2000) -> list[str]:
    if not value:
        return []
    return [value[idx: idx + size] for idx in range(0, len(value), size)]


class LocalExecutionRuntime:
    """Manages local subprocess lifecycle and stream persistence."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_requested: set[str] = set()
        self._lock = asyncio.Lock()

    async def start_run(
        self,
        *,
        db: Any,
        run_id: str,
        command_tokens: list[str],
        cwd: str,
        env_profile: str,
        project_root: str,
    ) -> None:
        if not command_tokens:
            repo = get_execution_repository(db)
            await repo.update_run(
                run_id,
                {
                    "status": "failed",
                    "ended_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
            )
            await repo.append_run_events(
                run_id,
                [
                    {
                        "stream": "system",
                        "event_type": "error",
                        "payload_text": "Run failed: empty command token list.",
                        "payload_json": {"reason": "empty_command_tokens"},
                        "occurred_at": _now_iso(),
                    }
                ],
            )
            return

        async with self._lock:
            if run_id in self._tasks:
                return
            task = asyncio.create_task(
                self._execute(
                    db=db,
                    run_id=run_id,
                    command_tokens=command_tokens,
                    cwd=cwd,
                    env_profile=env_profile,
                    project_root=project_root,
                )
            )
            self._tasks[run_id] = task

            def _cleanup(done_task: asyncio.Task[None]) -> None:
                _ = done_task
                self._tasks.pop(run_id, None)

            task.add_done_callback(_cleanup)

    async def cancel_run(self, *, db: Any, run_id: str, reason: str = "") -> bool:
        self._cancel_requested.add(run_id)
        repo = get_execution_repository(db)
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "status",
                    "payload_text": "Cancel requested.",
                    "payload_json": {"status": "cancel_requested", "reason": reason},
                    "occurred_at": _now_iso(),
                }
            ],
        )
        process = self._processes.get(run_id)
        if process is None:
            return False
        try:
            process.terminate()
        except ProcessLookupError:
            return True

        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return True
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting to kill process for run %s", run_id)
        return True

    async def reset_for_tests(self) -> None:
        for run_id, process in list(self._processes.items()):
            try:
                process.kill()
            except Exception:
                logger.debug("Failed to kill process for run %s during reset", run_id)
        for task in list(self._tasks.values()):
            task.cancel()
        self._processes.clear()
        self._tasks.clear()
        self._cancel_requested.clear()

    async def _execute(
        self,
        *,
        db: Any,
        run_id: str,
        command_tokens: list[str],
        cwd: str,
        env_profile: str,
        project_root: str,
    ) -> None:
        repo = get_execution_repository(db)
        started_at = _now_iso()
        await repo.update_run(
            run_id,
            {"status": "running", "started_at": started_at, "updated_at": started_at},
        )
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "status",
                    "payload_text": "Run started.",
                    "payload_json": {"status": "running"},
                    "occurred_at": started_at,
                }
            ],
        )

        environment = self._build_environment(env_profile=env_profile, project_root=project_root)
        try:
            process = await asyncio.create_subprocess_exec(
                *command_tokens,
                cwd=cwd,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            ended_at = _now_iso()
            await repo.update_run(
                run_id,
                {
                    "status": "failed",
                    "ended_at": ended_at,
                    "updated_at": ended_at,
                },
            )
            await repo.append_run_events(
                run_id,
                [
                    {
                        "stream": "system",
                        "event_type": "error",
                        "payload_text": f"Failed to launch process: {exc}",
                        "payload_json": {"error": str(exc)},
                        "occurred_at": ended_at,
                    }
                ],
            )
            return

        self._processes[run_id] = process
        try:
            stdout_task = asyncio.create_task(self._pump_stream(repo, run_id, "stdout", process.stdout))
            stderr_task = asyncio.create_task(self._pump_stream(repo, run_id, "stderr", process.stderr))
            await asyncio.gather(stdout_task, stderr_task, process.wait())
            return_code = int(process.returncode or 0)
        finally:
            self._processes.pop(run_id, None)

        canceled = run_id in self._cancel_requested
        ended_at = _now_iso()
        status = "canceled" if canceled else ("succeeded" if return_code == 0 else "failed")
        await repo.update_run(
            run_id,
            {
                "status": status,
                "exit_code": return_code,
                "ended_at": ended_at,
                "updated_at": ended_at,
            },
        )
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "status",
                    "payload_text": f"Run {status}.",
                    "payload_json": {"status": status, "exitCode": return_code},
                    "occurred_at": ended_at,
                }
            ],
        )
        self._cancel_requested.discard(run_id)

    async def _pump_stream(
        self,
        repo: Any,
        run_id: str,
        stream_name: str,
        stream: asyncio.StreamReader | None,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(1024)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            pieces = _chunk_text(text, size=1500)
            if not pieces:
                continue
            now = _now_iso()
            await repo.append_run_events(
                run_id,
                [
                    {
                        "stream": stream_name,
                        "event_type": "output",
                        "payload_text": piece,
                        "payload_json": {},
                        "occurred_at": now,
                    }
                    for piece in pieces
                ],
            )

    def _build_environment(self, *, env_profile: str, project_root: str) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in _ENV_ALLOWLIST:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value

        profile = str(env_profile or "default").strip().lower()
        if profile == "ci":
            env["CI"] = "1"
        if profile in {"project", "ci"}:
            env["CCDASH_PROJECT_ROOT"] = str(project_root or "")
        return env


_RUNTIME = LocalExecutionRuntime()


def get_execution_runtime() -> LocalExecutionRuntime:
    return _RUNTIME
