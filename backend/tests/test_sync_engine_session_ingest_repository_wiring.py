from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.postgres.session_messages import PostgresSessionMessageRepository
from backend.db.repositories.postgres.sessions import PostgresSessionRepository
from backend.db.repositories.session_messages import SqliteSessionMessageRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sync_engine import SyncEngine
from backend.ingestion.session_ingest_service import SessionIngestService


class _FakePostgresPool:
    pass


class SyncEngineSessionIngestRepositoryWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_sync_engine_reuses_selected_session_repositories_for_ingest_service(self) -> None:
        db = await aiosqlite.connect(":memory:")
        try:
            engine = SyncEngine(db)

            self.assertIsInstance(engine.session_repo, SqliteSessionRepository)
            self.assertIsInstance(engine.session_message_repo, SqliteSessionMessageRepository)
            self.assertIsNone(engine._session_ingest_service)

            service = engine._get_session_ingest_service()

            self.assertIsInstance(service, SessionIngestService)
            self.assertIs(service.session_repo, engine.session_repo)
            self.assertIs(service.session_message_repo, engine.session_message_repo)
            self.assertIs(engine._get_session_ingest_service(), service)
        finally:
            await db.close()

    async def test_postgres_sync_engine_reuses_selected_session_repositories_for_ingest_service(self) -> None:
        engine = SyncEngine(_FakePostgresPool())

        self.assertIsInstance(engine.session_repo, PostgresSessionRepository)
        self.assertIsInstance(engine.session_message_repo, PostgresSessionMessageRepository)
        self.assertIsNone(engine._session_ingest_service)

        service = engine._get_session_ingest_service()

        self.assertIsInstance(service, SessionIngestService)
        self.assertIs(service.session_repo, engine.session_repo)
        self.assertIs(service.session_message_repo, engine.session_message_repo)
        self.assertIs(engine._get_session_ingest_service(), service)


if __name__ == "__main__":
    unittest.main()
