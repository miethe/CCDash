"""Ingest idempotency regression test for ``rf_events`` (T1-005, AC-1).

Exercises the *service* layer (``RfEventsIngestService``) end-to-end against a
real in-memory SQLite DB migrated via ``run_migrations`` — one level below the
HTTP contract tests in ``test_rf_events_ingest_endpoint.py`` (T1-003) and one
level above the raw-repository direct-count tests in
``test_rf_events_migration_governance.py`` (T1-002). This is the dedicated
AC-1 regression gate named directly in the phase plan's ``verified_by`` list
and depends on T1-002 (the migrated `rf_events` table) and T1-004 (the
`ingest_cursors` idempotent enqueue wiring) both being in place.

Covers exactly the two AC-1 contracts:

  1. Idempotency — ``process()`` called twice with the identical ``event_id``
     inserts exactly one ``rf_events`` row (direct ``SELECT COUNT(*)``
     assertion, not just a return-value check), and the second call reports
     ``was_new_insert=False`` while leaving the ``ingest_cursors`` watermark
     from the first call untouched.
  2. Optional-field resilience — a payload missing every optional RF field
     (``human_review``, ``metrics``, ``governance``, ``reuse``,
     ``output_artifacts``, etc. — the "``output.claim_ledger_created``, etc."
     class of fields called out in the PRD/phase plan) persists successfully
     with those columns ``NULL``. Because this test operates below the HTTP
     layer, "never a 422" is verified as "``RfEventPayload`` validation and
     ``RfEventsIngestService.process()`` never raise" for such a payload.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_rf_events_ingest_idempotency.py -v
"""
from __future__ import annotations

import unittest
import uuid

import aiosqlite

from backend.application.models.ingest import RfEventPayload
from backend.application.services.ingest.rf_events_ingest import (
    SOURCE_ID,
    RfEventsIngestService,
)
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.repositories.rf_events import SqliteRfEventsRepository
from backend.db.sqlite_migrations import run_migrations


def _event_id() -> str:
    return str(uuid.uuid4())


def _full_event(event_id: str | None = None, **extra) -> RfEventPayload:
    """A fully-populated RF event — every optional field present."""
    obj: dict = {
        "event_id": event_id or _event_id(),
        "timestamp": "2026-07-21T10:00:00.000000Z",
        "project": "research-foundry",
        "run_id": "run-abc123",
        "intent_id": "intent-xyz",
        "task_node_id": "node-1",
        "agent_postures": ["autonomous"],
        "skillbom_ids": ["sk-1"],
        "tools": ["web_search"],
        "input_artifacts": ["source-1"],
        "output_artifacts": ["report-1"],
        "metrics": {
            "claims_total": 10,
            "claims_supported": 8,
            "verification_passed": True,
            "cost_estimated_usd": 0.42,
            "quality_score": "high",
        },
        "governance": {
            "sensitivity": "public",
            "policy_passed": True,
        },
        "reuse": {
            "skillbom_candidate": True,
        },
        "human_review": {
            "required": True,
            "status": "pending",
            "reviewer": None,
        },
    }
    obj.update(extra)
    return RfEventPayload.model_validate(obj)


def _minimal_event(event_id: str | None = None) -> RfEventPayload:
    """Only the RF schema's ``required`` fields — every optional field absent."""
    return RfEventPayload.model_validate(
        {
            "event_id": event_id or _event_id(),
            "timestamp": "2026-07-21T10:05:00.000000Z",
            "project": "research-foundry",
        }
    )


class RfEventsIngestIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    """T1-005: idempotency + optional-field resilience at the service layer."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteRfEventsRepository(self.db)
        self.cursor_repo = SqliteIngestCursorRepository(self.db)
        self.service = RfEventsIngestService(self.repo, self.cursor_repo)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self, event_id: str) -> int:
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM rf_events WHERE event_id = ?", (event_id,)
        )
        (count,) = await cursor.fetchone()
        return int(count)

    async def _fetch_row(self, event_id: str) -> aiosqlite.Row | None:
        cursor = await self.db.execute(
            "SELECT * FROM rf_events WHERE event_id = ?", (event_id,)
        )
        return await cursor.fetchone()

    # ------------------------------------------------------------------
    # 1. Idempotency: process() twice with the same event_id -> one row
    # ------------------------------------------------------------------

    async def test_process_same_event_id_twice_persists_exactly_one_row(self) -> None:
        event = _full_event()

        was_new_first, returned_id_first = await self.service.process(
            event, project_id="proj-1"
        )
        self.assertTrue(was_new_first)
        self.assertEqual(returned_id_first, event.event_id)
        self.assertEqual(await self._count(event.event_id), 1)

        # Re-process the identical event (mirrors a re-delivered/retried batch).
        was_new_second, returned_id_second = await self.service.process(
            event, project_id="proj-1"
        )
        self.assertFalse(was_new_second, "duplicate event_id must report was_new_insert=False")
        self.assertEqual(returned_id_second, event.event_id)

        # The direct-count assertion (ADR-007 §4) is the authoritative check —
        # not just the return value.
        self.assertEqual(
            await self._count(event.event_id),
            1,
            "re-processing the identical event_id must never produce a second row",
        )

    async def test_process_same_event_id_three_times_still_exactly_one_row(self) -> None:
        """Repeated redelivery (not just a single retry) must stay idempotent."""
        event = _full_event()

        for _ in range(3):
            await self.service.process(event, project_id="proj-1")

        self.assertEqual(await self._count(event.event_id), 1)

    async def test_duplicate_process_does_not_re_advance_cursor(self) -> None:
        """Idempotent duplicates must not disturb the ingest_cursors watermark.

        The first process() call advances the source_id='rf' cursor to this
        event_id (T1-004); a duplicate re-process must be a pure no-op on that
        watermark, not just on the rf_events row.
        """
        event = _full_event()

        await self.service.process(event, project_id="proj-cursor")
        cursor_after_first = await self.cursor_repo.get_or_create(
            source_id=SOURCE_ID, project_id="proj-cursor", workspace_id="default-local"
        )
        self.assertEqual(cursor_after_first.last_cursor, event.event_id)

        # A second, duplicate process() call must leave the watermark exactly
        # as-is (it must not error, and must not double-advance/reset it).
        await self.service.process(event, project_id="proj-cursor")
        cursor_after_second = await self.cursor_repo.get_or_create(
            source_id=SOURCE_ID, project_id="proj-cursor", workspace_id="default-local"
        )
        self.assertEqual(cursor_after_second.last_cursor, event.event_id)
        self.assertEqual(cursor_after_second.error_count, 0)

    async def test_two_distinct_events_produce_two_rows(self) -> None:
        """Sanity check: idempotency must not accidentally collapse distinct events."""
        event_a = _full_event()
        event_b = _full_event()

        await self.service.process(event_a, project_id="proj-1")
        await self.service.process(event_b, project_id="proj-1")

        self.assertEqual(await self._count(event_a.event_id), 1)
        self.assertEqual(await self._count(event_b.event_id), 1)

    # ------------------------------------------------------------------
    # 2. Optional-field resilience: missing fields persist as NULL, never raise
    # ------------------------------------------------------------------

    async def test_process_minimal_payload_never_raises(self) -> None:
        """A payload carrying only event_id/timestamp/project must process cleanly.

        Equivalent, below the HTTP layer, to "never a 422": neither
        RfEventPayload validation nor RfEventsIngestService.process() may
        raise for an RF-schema-valid payload that omits every optional field.
        """
        event = _minimal_event()

        try:
            was_new, returned_id = await self.service.process(event, project_id="proj-2")
        except Exception as exc:  # pragma: no cover - failure path documented in assertion
            self.fail(f"process() must never raise for a minimal valid payload: {exc!r}")

        self.assertTrue(was_new)
        self.assertEqual(returned_id, event.event_id)

    async def test_process_minimal_payload_persists_optional_columns_as_null(self) -> None:
        event = _minimal_event()
        await self.service.process(event, project_id="proj-2")

        row = await self._fetch_row(event.event_id)
        self.assertIsNotNone(row)

        # Required columns are present.
        self.assertEqual(row["event_id"], event.event_id)
        self.assertEqual(row["project_id"], "proj-2")
        self.assertEqual(row["rf_project"], "research-foundry")

        # Every optional field the RF schema allows to be absent -- including
        # the human_review / output_artifacts class of fields called out in
        # the phase plan ("human_review, output.claim_ledger_created, etc.")
        # -- must persist as NULL, never trip a NOT NULL constraint or a
        # mapping error.
        optional_null_columns = (
            "run_id",
            "intent_id",
            "task_node_id",
            "agent_postures_json",
            "skillbom_ids_json",
            "tools_json",
            "input_artifacts_json",
            "output_artifacts_json",
            "human_review_required",
            "human_review_status",
            "human_review_reviewer",
            "metric_claims_total",
            "metric_verification_passed",
            "metric_quality_score",
            "governance_sensitivity",
            "governance_policy_passed",
            "reuse_skillbom_candidate",
        )
        for column in optional_null_columns:
            self.assertIsNone(
                row[column],
                msg=f"column '{column}' must be NULL for a payload that omits it",
            )

    async def test_process_partial_human_review_missing_nested_keys_persists_null(self) -> None:
        """A present-but-partial optional group (human_review) must not choke.

        Mirrors the "output.claim_ledger_created"-style deeply-nested optional
        field: the group itself is present, but a specific nested key inside
        it is absent -- that key must map to NULL, not raise or default.
        """
        event = _full_event(
            human_review={"required": True},  # 'status' and 'reviewer' omitted
            output_artifacts=None,  # explicit absence of a top-level optional list
        )

        await self.service.process(event, project_id="proj-3")

        row = await self._fetch_row(event.event_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["human_review_required"], 1)
        self.assertIsNone(row["human_review_status"])
        self.assertIsNone(row["human_review_reviewer"])
        self.assertIsNone(row["output_artifacts_json"])

    async def test_minimal_payload_idempotent_on_reprocess(self) -> None:
        """Both AC-1 contracts composed: a minimal payload is ALSO idempotent."""
        event = _minimal_event()

        await self.service.process(event, project_id="proj-2")
        was_new_second, _ = await self.service.process(event, project_id="proj-2")

        self.assertFalse(was_new_second)
        self.assertEqual(await self._count(event.event_id), 1)


if __name__ == "__main__":
    unittest.main()
