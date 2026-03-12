from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Mapping


class GitCommandError(RuntimeError):
    def __init__(self, message: str, *, returncode: int, stdout: str, stderr: str):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class GitRunner:
    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> str:
        command = ["git", *args]
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise GitCommandError(
                f"Git command failed: {' '.join(command)}",
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        return completed.stdout.strip()
