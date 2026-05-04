import unittest

from backend.db.repositories.postgres.session_messages import PostgresSessionMessageRepository


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePostgresConnection:
    def __init__(self):
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def transaction(self):
        return _AsyncContext(self)

    async def execute(self, query: str, *args):
        self.execute_calls.append((query, args))

    async def executemany(self, query: str, records):
        self.executemany_calls.append((query, list(records)))


class PostgresSessionMessageRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_replace_session_messages_locks_and_upserts_by_message_index(self) -> None:
        conn = _FakePostgresConnection()
        repo = PostgresSessionMessageRepository(conn)  # type: ignore[arg-type]

        await repo.replace_session_messages(
            "session-1",
            [
                {
                    "messageIndex": 0,
                    "sourceLogId": "log-0",
                    "messageId": "msg-0",
                    "role": "assistant",
                    "messageType": "message",
                    "content": "hello",
                    "timestamp": "2026-05-04T12:00:00Z",
                    "agentName": "codex",
                    "sourceProvenance": "test",
                    "metadata": {"source": "unit"},
                    "tokenUsage": {
                        "inputTokens": 10,
                        "outputTokens": 20,
                        "cacheReadInputTokens": 3,
                        "cacheCreationInputTokens": 4,
                    },
                }
            ],
        )

        self.assertEqual(conn.execute_calls[0][0], "SELECT pg_advisory_xact_lock(hashtext($1))")
        self.assertEqual(conn.execute_calls[0][1], ("session-1",))
        self.assertEqual(conn.execute_calls[1][0], "DELETE FROM session_messages WHERE session_id = $1")
        self.assertEqual(conn.execute_calls[1][1], ("session-1",))

        self.assertEqual(len(conn.executemany_calls), 1)
        insert_query, records = conn.executemany_calls[0]
        self.assertIn("ON CONFLICT (session_id, message_index) DO UPDATE SET", insert_query)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], "session-1")
        self.assertEqual(records[0][1], 0)
        self.assertEqual(records[0][-4:], (10, 20, 3, 4))
