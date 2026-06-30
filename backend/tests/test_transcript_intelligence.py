from __future__ import annotations

from backend.application.services.agent_queries.transcript_intelligence import (
    build_transcript_intelligence_index,
)


def _log(
    log_id: str,
    *,
    content: str,
    log_type: str = "message",
    metadata: dict | None = None,
    tool_call: dict | None = None,
    token_usage: dict | None = None,
) -> dict:
    return {
        "id": log_id,
        "timestamp": "2026-06-30T12:00:00Z",
        "speaker": "user",
        "type": log_type,
        "content": content,
        "metadata": metadata or {},
        "toolCall": tool_call,
        "tokenUsage": token_usage,
    }


def test_title_ignores_clear_and_prefers_plan_feature_command() -> None:
    index = build_transcript_intelligence_index(
        {"id": "raw-session-id"},
        [
            _log("l1", content="/clear", log_type="command"),
            _log(
                "l2",
                content="/plan:plan-feature",
                log_type="command",
                metadata={
                    "args": "docs/project_plans/implementation_plans/enhancements/session-transcript-orchestration-intelligence-v1.md"
                },
            ),
        ],
        existing_title="raw-session-id",
    )

    assert index.title.displayTitle == "Session Transcript Orchestration Intelligence V1"
    assert index.title.rawSessionId == "raw-session-id"
    assert index.title.source == "command"
    assert index.title.commandName == "/plan:plan-feature"
    assert index.title.featureSlug == "session-transcript-orchestration-intelligence-v1"


def test_effort_timeline_keeps_launch_metadata_and_command_transitions() -> None:
    index = build_transcript_intelligence_index(
        {
            "id": "sess-1",
            "effort_tier": "low",
            "started_at": "2026-06-30T12:00:00Z",
        },
        [
            _log("l1", content="/effort ultracode", log_type="command"),
            _log("l2", content="effort tier changed to medium", log_type="system"),
        ],
    )

    assert [entry.toEffort for entry in index.effortTimeline] == ["low", "high", "medium"]
    assert index.effortTimeline[1].fromEffort == "low"
    assert index.effortTimeline[1].providerEffort == "ultracode"
    assert index.effortTimeline[2].fromEffort == "high"


def test_markers_and_registers_capture_tasks_workflows_and_plan_links() -> None:
    index = build_transcript_intelligence_index(
        {"id": "sess-2"},
        [
            _log(
                "cmd-1",
                content="/plan:plan-feature",
                log_type="command",
                metadata={
                    "args": "docs/project_plans/implementation_plans/enhancements/example-feature-v1.md"
                },
            ),
            _log(
                "task-1",
                content="create task",
                log_type="tool",
                tool_call={
                    "name": "TaskCreate",
                    "args": '{"tasks":[{"id":"T-1","title":"Index transcript markers","status":"in_progress"}]}',
                },
            ),
            _log(
                "agent-1",
                content="delegate",
                log_type="tool",
                tool_call={
                    "name": "Task",
                    "args": '{"subagent_type":"explorer","description":"Map transcript surfaces"}',
                },
                token_usage={
                    "inputTokens": 10,
                    "outputTokens": 5,
                    "cacheReadInputTokens": 3,
                    "cacheCreationInputTokens": 2,
                },
            ),
        ],
    )

    assert {marker.kind for marker in index.markers} >= {"command", "workflow", "task", "subagent"}
    assert [link.path for link in index.planLinks] == [
        "docs/project_plans/implementation_plans/enhancements/example-feature-v1.md"
    ]
    assert any(task.id == "T-1" and task.status == "in_progress" for task in index.taskRegister)
    assert any(task.kind == "subagent" and task.title == "explorer" for task in index.taskRegister)
    assert any(workflow.workflowId == "example-feature-v1" for workflow in index.workflowRegister)
    assert index.tokenCoverage.rowLevelKnownTokens == 20
    assert index.tokenCoverage.sourceGranularity == "message"


def test_aggregate_only_token_coverage_does_not_fabricate_row_usage() -> None:
    index = build_transcript_intelligence_index(
        {"id": "sess-3", "observed_tokens": 42},
        [_log("l1", content="message")],
    )

    assert index.tokenCoverage.rowLevelKnownTokens == 0
    assert index.tokenCoverage.aggregateObservedTokens == 42
    assert index.tokenCoverage.coveragePct == 0.0
    assert index.tokenCoverage.sourceGranularity == "aggregate"
    assert index.tokenCoverage.caveats
