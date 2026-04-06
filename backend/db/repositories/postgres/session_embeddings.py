"""Postgres capability seam for canonical session embeddings storage."""
from __future__ import annotations

import json
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

    async def replace_session_embeddings(self, session_id: str, blocks: list[dict[str, Any]]) -> None:
        async with self.db.transaction():
            await self.db.execute("DELETE FROM app.session_embeddings WHERE session_id = $1", session_id)
            if not blocks:
                return
            await self.db.executemany(
                """
                INSERT INTO app.session_embeddings (
                    session_id, block_kind, block_index, content_hash, message_ids_json,
                    content, embedding_model, embedding_dimensions, embedding, metadata_json
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, NULL, $9::jsonb)
                """,
                [
                    (
                        session_id,
                        str(block.get("block_kind") or ""),
                        int(block.get("block_index", 0) or 0),
                        str(block.get("content_hash") or ""),
                        json.dumps(list(block.get("message_ids") or [])),
                        str(block.get("content") or ""),
                        str(block.get("embedding_model") or ""),
                        int(block.get("embedding_dimensions", 0) or 0),
                        json.dumps(dict(block.get("metadata_json") or {})),
                    )
                    for block in blocks
                ],
            )
