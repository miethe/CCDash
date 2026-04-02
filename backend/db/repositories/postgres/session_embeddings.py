"""Postgres capability seam for canonical session embeddings storage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg


@dataclass(frozen=True, slots=True)
class StorageCapabilityDescriptor:
    supported: bool
    authoritative: bool
    storage_profile: str
    notes: str


class PostgresSessionEmbeddingRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    def describe_capability(self) -> StorageCapabilityDescriptor:
        return StorageCapabilityDescriptor(
            supported=True,
            authoritative=True,
            storage_profile="enterprise",
            notes=(
                "Enterprise Postgres is the canonical store for transcript embedding blocks. "
                "Requires pgvector extension and the app.session_embeddings table."
            ),
        )

    async def list_by_session(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM app.session_embeddings
            WHERE session_id = $1
            ORDER BY block_kind ASC, block_index ASC, id ASC
            """,
            session_id,
        )
        return [dict(row) for row in rows]
