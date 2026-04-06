"""Local compatibility repository for enterprise-only session embeddings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StorageCapabilityDescriptor:
    supported: bool
    authoritative: bool
    storage_profile: str
    notes: str


class SqliteSessionEmbeddingRepository:
    def __init__(self, db: Any) -> None:
        self.db = db

    def describe_capability(self) -> StorageCapabilityDescriptor:
        return StorageCapabilityDescriptor(
            supported=False,
            authoritative=False,
            storage_profile="local",
            notes=(
                "Session embedding storage is enterprise-only. Local SQLite keeps canonical "
                "session_messages rows but does not require pgvector or session_embeddings tables."
            ),
        )

    async def replace_session_embeddings(self, session_id: str, blocks: list[dict[str, Any]]) -> None:
        _ = session_id, blocks

    async def list_by_session(self, session_id: str) -> list[dict[str, Any]]:
        _ = session_id
        return []
