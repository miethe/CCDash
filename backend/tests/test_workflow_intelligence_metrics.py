"""Tests for OBS-405: Histogram observation of workflow detail batch row counts.

Verifies that `otel.record_workflow_detail_batch_rows` is called with the
correct count on a successful batch fetch, and is NOT called on the empty
fallback path (i.e., when fetch_workflow_details raises an exception).
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.workflow_intelligence import (
    WorkflowDiagnosticsQueryService,
)


def _make_ports() -> CorePorts:
    storage = MagicMock()
    storage.db = MagicMock()
    ports = MagicMock(spec=CorePorts)
    ports.storage = storage
    return ports


def _make_context() -> RequestContext:
    return MagicMock(spec=RequestContext)


def _make_scope(project_id: str = "proj-test") -> object:
    """Build a minimal scope stub with a real string project.id."""
    project = types.SimpleNamespace(id=project_id, project_id=project_id)
    scope = types.SimpleNamespace(project=project, request_scope=None)
    return scope


# Patch targets — all resolved relative to workflow_intelligence's own namespace.
_LIST_REGISTRY = "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry"
_FETCH_DETAILS = "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details"
_RECORD_ROWS = "backend.observability.otel.record_workflow_detail_batch_rows"
_GET_EFFECTIVENESS = "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness"
_DETECT_FAILURES = "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns"
_RESOLVE_SCOPE = "backend.application.services.agent_queries.workflow_intelligence.resolve_project_scope"

_REGISTRY_ROW = {"id": "w1", "identity": {"resolvedWorkflowId": "w1", "displayLabel": "W1"}}


class WorkflowDetailBatchMetricsTests(unittest.IsolatedAsyncioTestCase):
    """OBS-405: record_workflow_detail_batch_rows wired into the batch fetch path."""

    async def test_records_row_count_on_successful_fetch(self) -> None:
        """Histogram is recorded with the actual returned row count."""
        fake_rows = [{"id": "w1"}, {"id": "w2"}, {"id": "w3"}]
        registry_rows = [
            {"id": "w1", "identity": {"resolvedWorkflowId": "w1", "displayLabel": "W1"}},
            {"id": "w2", "identity": {"resolvedWorkflowId": "w2", "displayLabel": "W2"}},
            {"id": "w3", "identity": {"resolvedWorkflowId": "w3", "displayLabel": "W3"}},
        ]

        with (
            patch(_RESOLVE_SCOPE, return_value=_make_scope()),
            patch(_LIST_REGISTRY, new_callable=AsyncMock, return_value={"items": registry_rows}),
            patch(_FETCH_DETAILS, new_callable=AsyncMock, return_value=fake_rows),
            patch(_RECORD_ROWS) as mock_record,
            patch(_GET_EFFECTIVENESS, new_callable=AsyncMock, return_value={}),
            patch(_DETECT_FAILURES, new_callable=AsyncMock, return_value={}),
        ):
            svc = WorkflowDiagnosticsQueryService()
            await svc.get_diagnostics(context=_make_context(), ports=_make_ports())
            mock_record.assert_called_once_with(len(fake_rows))

    async def test_does_not_record_on_exception_fallback(self) -> None:
        """Histogram is NOT recorded when fetch_workflow_details raises."""
        with (
            patch(_RESOLVE_SCOPE, return_value=_make_scope()),
            patch(_LIST_REGISTRY, new_callable=AsyncMock, return_value={"items": [_REGISTRY_ROW]}),
            patch(_FETCH_DETAILS, new_callable=AsyncMock, side_effect=RuntimeError("db unavailable")),
            patch(_RECORD_ROWS) as mock_record,
            patch(_GET_EFFECTIVENESS, new_callable=AsyncMock, return_value={}),
            patch(_DETECT_FAILURES, new_callable=AsyncMock, return_value={}),
        ):
            svc = WorkflowDiagnosticsQueryService()
            await svc.get_diagnostics(context=_make_context(), ports=_make_ports())
            mock_record.assert_not_called()

    async def test_records_zero_when_fetch_returns_empty_list(self) -> None:
        """Histogram records 0 when fetch_workflow_details returns an empty list (no exception)."""
        with (
            patch(_RESOLVE_SCOPE, return_value=_make_scope()),
            patch(_LIST_REGISTRY, new_callable=AsyncMock, return_value={"items": [_REGISTRY_ROW]}),
            patch(_FETCH_DETAILS, new_callable=AsyncMock, return_value=[]),
            patch(_RECORD_ROWS) as mock_record,
            patch(_GET_EFFECTIVENESS, new_callable=AsyncMock, return_value={}),
            patch(_DETECT_FAILURES, new_callable=AsyncMock, return_value={}),
        ):
            svc = WorkflowDiagnosticsQueryService()
            await svc.get_diagnostics(context=_make_context(), ports=_make_ports())
            mock_record.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
