"""Transaction helper for asyncpg-backed repositories."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def postgres_transaction(db: Any) -> AsyncIterator[Any]:
    acquire = getattr(db, "acquire", None)
    if acquire is not None:
        async with db.acquire() as conn:
            async with conn.transaction():
                yield conn
        return

    async with db.transaction():
        yield db
