from __future__ import annotations

import unittest

from backend.scripts.repair_dangling_codex_sessions import (
    OPAQUE_SOURCE_PREFIX,
    UNATTRIBUTED_PLATFORM_TYPE,
    repair,
)


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object):
        self.calls.append((query, args))
        return [{"project_id": "missing-project"}]

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "UPDATE 97" if query.lstrip().startswith("UPDATE") else "INSERT 0 1"


class RepairDanglingCodexSessionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_repair_registers_missing_project_then_reclassifies_opaque_rows(self) -> None:
        connection = _Connection()

        projects, sessions = await repair(connection)

        self.assertEqual((projects, sessions), (1, 97))
        self.assertEqual(connection.calls[0][1], (f"{OPAQUE_SOURCE_PREFIX}%",))
        insert_query, insert_args = connection.calls[1]
        self.assertIn("ON CONFLICT (id) DO NOTHING", insert_query)
        self.assertEqual(insert_args[0], "missing-project")
        update_query, update_args = connection.calls[2]
        self.assertIn("UPDATE sessions", update_query)
        self.assertNotIn("DELETE", update_query)
        self.assertEqual(update_args, (UNATTRIBUTED_PLATFORM_TYPE, f"{OPAQUE_SOURCE_PREFIX}%"))
