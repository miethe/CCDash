from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine


class _ParsedSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


class SyncEngineSessionIngestBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.engine = SyncEngine(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_unchanged_session_skips_before_parser_cleanup_or_ingest_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text('{"type":"user","message":{"content":"hi"}}\n', encoding="utf-8")
            mtime = session_path.stat().st_mtime
            sync_key = self.engine._canonical_source_key("project-1", session_path, "session")

            self.engine.sync_repo.get_sync_state = AsyncMock(return_value={"file_mtime": mtime})  # type: ignore[method-assign]
            self.engine.sync_repo.upsert_sync_state = AsyncMock()  # type: ignore[method-assign]
            self.engine.session_repo.list_by_source = AsyncMock(  # type: ignore[method-assign]
                return_value=[{"id": "S-1", "thread_kind": "root", "conversation_family_id": "S-1"}]
            )
            self.engine.session_repo.delete_by_source = AsyncMock()  # type: ignore[method-assign]
            self.engine.session_repo.delete_relationships_for_source = AsyncMock()  # type: ignore[method-assign]

            ingest_service = Mock()
            ingest_service.persist_envelope = AsyncMock()
            self.engine._get_session_ingest_service = Mock(return_value=ingest_service)  # type: ignore[method-assign]

            with patch("backend.db.sync_engine.parse_session_file") as parse_mock:
                synced = await self.engine._sync_single_session("project-1", session_path, force=False)

        self.assertFalse(synced)
        self.engine.sync_repo.get_sync_state.assert_awaited_once_with(sync_key)  # type: ignore[attr-defined]
        self.engine.session_repo.list_by_source.assert_awaited_once_with(sync_key)  # type: ignore[attr-defined]
        parse_mock.assert_not_called()
        self.engine.session_repo.delete_by_source.assert_not_awaited()  # type: ignore[attr-defined]
        self.engine.session_repo.delete_relationships_for_source.assert_not_awaited()  # type: ignore[attr-defined]
        ingest_service.persist_envelope.assert_not_awaited()
        self.engine.sync_repo.upsert_sync_state.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_cleanup_runs_before_ingest_service_and_sync_state_stays_in_sync_engine(self) -> None:
        events: list[str] = []

        async def get_sync_state(_file_path: str) -> None:
            events.append("get_sync_state")
            return None

        async def delete_by_source(_source_file: str) -> None:
            events.append("delete_by_source")

        async def delete_relationships_for_source(_project_id: str, _source_file: str) -> None:
            events.append("delete_relationships_for_source")

        async def persist_envelope(*_args: Any, **_kwargs: Any) -> None:
            events.append("persist_envelope")

        async def upsert_sync_state(_state: dict[str, Any]) -> None:
            events.append("upsert_sync_state")

        def parse_session_file(_path: Path) -> _ParsedSession:
            events.append("parse_session_file")
            return _ParsedSession(
                {
                    "id": "S-boundary",
                    "logs": [],
                    "toolsUsed": [],
                    "updatedFiles": [],
                    "linkedArtifacts": [],
                }
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text('{"type":"user","message":{"content":"hi"}}\n', encoding="utf-8")
            mtime = session_path.stat().st_mtime
            sync_key = self.engine._canonical_source_key("project-1", session_path, "session")

            self.engine.sync_repo.get_sync_state = AsyncMock(side_effect=get_sync_state)  # type: ignore[method-assign]
            self.engine.sync_repo.upsert_sync_state = AsyncMock(side_effect=upsert_sync_state)  # type: ignore[method-assign]
            self.engine.session_repo.delete_by_source = AsyncMock(side_effect=delete_by_source)  # type: ignore[method-assign]
            self.engine.session_repo.delete_relationships_for_source = AsyncMock(  # type: ignore[method-assign]
                side_effect=delete_relationships_for_source
            )

            ingest_service = Mock()
            ingest_service.persist_envelope = AsyncMock(side_effect=persist_envelope)
            self.engine._get_session_ingest_service = Mock(return_value=ingest_service)  # type: ignore[method-assign]

            with (
                patch("backend.db.sync_engine.parse_session_file", side_effect=parse_session_file),
                patch("backend.db.sync_engine.observability.start_span", return_value=nullcontext()),
                patch("backend.db.sync_engine.observability.record_ingestion"),
            ):
                synced = await self.engine._sync_single_session("project-1", session_path, force=False)

        self.assertTrue(synced)
        self.assertEqual(
            events,
            [
                "get_sync_state",
                "parse_session_file",
                "delete_by_source",
                "delete_relationships_for_source",
                "persist_envelope",
                "upsert_sync_state",
            ],
        )
        self.engine.sync_repo.get_sync_state.assert_awaited_once_with(sync_key)  # type: ignore[attr-defined]
        self.engine.session_repo.delete_by_source.assert_awaited_once_with(sync_key)  # type: ignore[attr-defined]
        self.engine.session_repo.delete_relationships_for_source.assert_awaited_once_with(  # type: ignore[attr-defined]
            "project-1",
            sync_key,
        )
        self.engine.sync_repo.upsert_sync_state.assert_awaited_once()  # type: ignore[attr-defined]
        sync_state = self.engine.sync_repo.upsert_sync_state.await_args.args[0]  # type: ignore[attr-defined]
        self.assertEqual(sync_state["file_path"], sync_key)
        self.assertEqual(sync_state["file_mtime"], mtime)
        self.assertTrue(sync_state["file_hash"])

        ingest_service.persist_envelope.assert_awaited_once()
        persist_args = ingest_service.persist_envelope.await_args
        self.assertEqual(persist_args.args[0], "project-1")
        self.assertEqual(persist_args.args[1].source_identity, sync_key)
        self.assertEqual(persist_args.kwargs["observed_source_file"], str(session_path))
        self.assertEqual(persist_args.kwargs["telemetry_source"], "sync")


if __name__ == "__main__":
    unittest.main()
