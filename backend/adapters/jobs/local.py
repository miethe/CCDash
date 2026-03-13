"""In-process job scheduling for local/test runtimes."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable


class InProcessJobScheduler:
    def schedule(self, job: Awaitable[Any], *, name: str | None = None) -> asyncio.Task[Any]:
        return asyncio.create_task(job, name=name)
