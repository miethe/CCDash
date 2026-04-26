from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.application.services.feature_surface import (
    FeatureCardDTO,
    FeatureCardPageDTO,
    FeatureModalSectionDTO,
    FeatureModalSectionItemDTO,
    FeatureRollupDTO,
    LinkedFeatureSessionPageDTO,
)


def test_feature_card_serializes_nested_fields_with_camel_case_aliases() -> None:
    freshness = {"observed_at": datetime(2026, 4, 23, 12, 0, tzinfo=UTC)}
    dto = FeatureCardDTO(
        id="FEAT-123",
        effective_status="in_progress",
        total_tasks=5,
        completed_tasks=3,
        document_coverage={"counts_by_type": {"prd": 1}},
        quality_signals={"blocker_count": 2, "integrity_signal_refs": ["SIG-1"]},
        dependency_state={"blocked_by_count": 1},
        primary_documents=[{"document_id": "doc-1", "doc_type": "prd"}],
        related_feature_count=4,
        freshness=freshness,
    )

    payload = dto.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert payload["effectiveStatus"] == "in_progress"
    assert payload["totalTasks"] == 5
    assert payload["documentCoverage"]["countsByType"] == {"prd": 1}
    assert payload["qualitySignals"]["blockerCount"] == 2
    assert payload["dependencyState"]["blockedByCount"] == 1
    assert payload["primaryDocuments"][0]["documentId"] == "doc-1"
    assert payload["relatedFeatureCount"] == 4
    assert payload["freshness"]["observedAt"] == "2026-04-23T12:00:00Z"


def test_feature_rollup_accepts_camel_case_input_and_preserves_precision_metadata() -> None:
    dto = FeatureRollupDTO.model_validate(
        {
            "featureId": "FEAT-9",
            "sessionCount": 8,
            "precision": "partial",
            "freshness": {
                "cacheVersion": "rollup-v1",
                "sourceRevision": "rev-22",
                "sessionSyncAt": "2026-04-23T12:30:00Z",
            },
            "modelFamilies": [{"key": "sonnet", "count": 6}],
        }
    )

    payload = dto.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert dto.feature_id == "FEAT-9"
    assert dto.precision == "partial"
    assert payload["freshness"]["cacheVersion"] == "rollup-v1"
    assert payload["freshness"]["sourceRevision"] == "rev-22"
    assert payload["freshness"]["sessionSyncAt"] == "2026-04-23T12:30:00Z"
    assert payload["modelFamilies"][0]["count"] == 6


def test_pages_and_sections_enforce_basic_validation_boundaries() -> None:
    with pytest.raises(ValidationError):
        FeatureCardPageDTO(limit=0)

    with pytest.raises(ValidationError):
        FeatureModalSectionDTO(
            feature_id="FEAT-1",
            section="history",
            items=[FeatureModalSectionItemDTO(item_id="x")],
        )


def test_linked_feature_session_page_serializes_enrichment_aliases() -> None:
    dto = LinkedFeatureSessionPageDTO.model_validate(
        {
            "items": [
                {
                    "sessionId": "sess-1",
                    "threadChildCount": 2,
                    "relatedTasks": [{"taskId": "TASK-1", "matchedBy": "link"}],
                }
            ],
            "total": 1,
            "hasMore": True,
            "enrichment": {
                "includes": ["tasks", "thread_children"],
                "logsRead": False,
                "taskRefsIncluded": True,
                "threadChildrenIncluded": True,
            },
        }
    )

    payload = dto.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert payload["items"][0]["sessionId"] == "sess-1"
    assert payload["items"][0]["threadChildCount"] == 2
    assert payload["items"][0]["relatedTasks"][0]["taskId"] == "TASK-1"
    assert payload["enrichment"]["taskRefsIncluded"] is True
    assert payload["enrichment"]["threadChildrenIncluded"] is True
    assert payload["hasMore"] is True
