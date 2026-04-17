"""PCP-502: Launch Preparation Contract tests.

Validates Pydantic DTO shapes, defaults, serialisation round-trips, and
rejection of invalid literal values.  No services, routes, or DB required.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import (
    LaunchApprovalRequirementDTO,
    LaunchBatchSummaryDTO,
    LaunchBatchTaskSummary,
    LaunchPreparationDTO,
    LaunchPreparationRequest,
    LaunchProviderCapabilityDTO,
    LaunchStartRequest,
    LaunchStartResponse,
    LaunchWorktreeSelectionDTO,
    WorktreeContextDTO,
)


# ---------------------------------------------------------------------------
# 1. LaunchPreparationDTO round-trip
# ---------------------------------------------------------------------------

def test_launch_preparation_dto_roundtrip() -> None:
    batch = LaunchBatchSummaryDTO(
        batchId="batch-1",
        phaseNumber=2,
        featureId="FEAT-42",
        featureName="Auth revamp",
        readinessState="ready",
        isReady=True,
        tasks=[
            LaunchBatchTaskSummary(taskId="T-1", title="Scaffold login", status="open")
        ],
    )
    provider = LaunchProviderCapabilityDTO(
        provider="claude",
        label="Claude Sonnet",
        supported=True,
        supportsWorktrees=True,
        supportsModelSelection=True,
        defaultModel="claude-sonnet-4-6",
        availableModels=["claude-sonnet-4-6", "claude-opus-4-5"],
    )
    prep = LaunchPreparationDTO(
        projectId="proj-1",
        featureId="FEAT-42",
        phaseNumber=2,
        batchId="batch-1",
        batch=batch,
        providers=[provider],
        selectedProvider="claude",
        generatedAt="2026-04-17T00:00:00Z",
    )

    # Serialise → JSON string → re-validate
    json_str = prep.model_dump_json()
    restored = LaunchPreparationDTO.model_validate_json(json_str)

    assert restored.providers[0].supported is True
    assert restored.batch.readinessState == "ready"
    assert restored.providers[0].supportsWorktrees is True
    assert restored.batch.featureId == "FEAT-42"


# ---------------------------------------------------------------------------
# 2. LaunchPreparationRequest rejects missing required fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_field", ["projectId", "featureId", "phaseNumber", "batchId"])
def test_launch_preparation_request_requires_fields(missing_field: str) -> None:
    valid = dict(projectId="p", featureId="f", phaseNumber=1, batchId="b")
    del valid[missing_field]
    with pytest.raises(ValidationError):
        LaunchPreparationRequest(**valid)


# ---------------------------------------------------------------------------
# 3. LaunchStartRequest defaults
# ---------------------------------------------------------------------------

def test_launch_start_request_defaults() -> None:
    req = LaunchStartRequest(
        projectId="p",
        featureId="f",
        phaseNumber=1,
        batchId="b",
        provider="local",
    )
    assert req.envProfile == "default"
    assert req.actor == "user"
    assert req.worktree.worktreeContextId == ""
    assert req.model == ""
    assert req.commandOverride == ""
    assert req.approvalDecision == ""


# ---------------------------------------------------------------------------
# 4. LaunchWorktreeSelectionDTO serialises cleanly
# ---------------------------------------------------------------------------

def test_worktree_selection_serialises() -> None:
    sel = LaunchWorktreeSelectionDTO(
        createIfMissing=True,
        branch="feat/pcp-502",
        worktreePath="/tmp/pcp-502",
        baseBranch="main",
    )
    data = sel.model_dump(mode="json")
    assert data["createIfMissing"] is True
    assert data["branch"] == "feat/pcp-502"
    assert data["worktreeContextId"] == ""

    restored = LaunchWorktreeSelectionDTO.model_validate(data)
    assert restored.createIfMissing is True
    assert restored.branch == "feat/pcp-502"


# ---------------------------------------------------------------------------
# 5. LaunchApprovalRequirementDTO defaults
# ---------------------------------------------------------------------------

def test_launch_approval_requirement_defaults() -> None:
    dto = LaunchApprovalRequirementDTO()
    assert dto.requirement == "none"
    assert dto.riskLevel == "low"
    assert dto.reasonCodes == []


# ---------------------------------------------------------------------------
# 6. LaunchBatchReadinessState rejects bogus value
# ---------------------------------------------------------------------------

def test_launch_batch_readiness_state_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        LaunchBatchSummaryDTO(
            batchId="b",
            phaseNumber=1,
            featureId="f",
            readinessState="garbage",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# 7. LaunchStartResponse defaults
# ---------------------------------------------------------------------------

def test_launch_start_response_defaults() -> None:
    resp = LaunchStartResponse(runId="run-abc")
    assert resp.status == "queued"
    assert resp.requiresApproval is False
    assert resp.worktreeContextId == ""
    assert resp.warnings == []
