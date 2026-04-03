import json
import types
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.routers import api as api_router


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


class _FakeAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):
        _ = name
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):
        _ = integration, operation, payload
        return {}


class _FakeWorkspaceRegistry:
    def __init__(self, project) -> None:
        self.project = project

    def get_project(self, project_id):
        if self.project and str(getattr(self.project, "id", "")) == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project


class _EmptySessionMessageRepo:
    async def list_by_session(self, session_id):
        _ = session_id
        return []


class _FakeStorage:
    def __init__(self, *, db=None, session_repo=None, session_message_repo=None, link_repo=None, feature_repo=None) -> None:
        self.db = db if db is not None else object()
        self._session_repo = session_repo
        self._session_message_repo = session_message_repo or _EmptySessionMessageRepo()
        self._link_repo = link_repo
        self._feature_repo = feature_repo

    def sessions(self):
        return self._session_repo

    def session_messages(self):
        return self._session_message_repo

    def entity_links(self):
        return self._link_repo

    def features(self):
        return self._feature_repo


def _request_context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test:operator", display_name="Test Operator", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=api_router.Path("/tmp/project"),
            sessions_dir=api_router.Path("/tmp/sessions"),
            docs_dir=api_router.Path("/tmp/docs"),
            progress_dir=api_router.Path("/tmp/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _core_ports(*, project=None, db=None, session_repo=None, session_message_repo=None, link_repo=None, feature_repo=None) -> CorePorts:
    resolved_project = project or types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(resolved_project),
        storage=_FakeStorage(
            db=db,
            session_repo=session_repo,
            session_message_repo=session_message_repo,
            link_repo=link_repo,
            feature_repo=feature_repo,
        ),
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class _FakeRepo:
    def __init__(self) -> None:
        self.last_filters = None
        self.last_include_subagents_for_facets = None
        self.last_include_subagents_for_platform_facets = None

    async def list_paginated(self, offset, limit, project_id, sort_by, sort_order, filters):
        self.last_filters = dict(filters)
        return [
            {
                "id": "S-main",
                "task_id": "",
                "status": "completed",
                "model": "claude-sonnet",
                "platform_type": "Claude Code",
                "platform_version": "2.1.52",
                "platform_versions_json": "[\"2.1.52\"]",
                "platform_version_transitions_json": "[]",
                "session_type": "session",
                "parent_session_id": None,
                "root_session_id": "S-main",
                "agent_id": None,
                "thread_kind": "root",
                "conversation_family_id": "S-main",
                "context_inheritance": "fresh",
                "fork_parent_session_id": None,
                "fork_point_log_id": None,
                "fork_point_entry_uuid": None,
                "fork_point_parent_entry_uuid": None,
                "fork_depth": 0,
                "fork_count": 1,
                "duration_seconds": 1,
                "tokens_in": 1,
                "tokens_out": 1,
                "model_io_tokens": 2,
                "cache_creation_input_tokens": 3,
                "cache_read_input_tokens": 5,
                "cache_input_tokens": 8,
                "observed_tokens": 10,
                "tool_reported_tokens": 13,
                "tool_result_input_tokens": 21,
                "tool_result_output_tokens": 34,
                "tool_result_cache_creation_input_tokens": 55,
                "tool_result_cache_read_input_tokens": 89,
                "total_cost": 0.0,
                "started_at": "2026-02-16T00:00:00Z",
                "quality_rating": 0,
                "friction_rating": 0,
                "git_commit_hash": None,
                "git_author": None,
                "git_branch": None,
                "thinking_level": "high",
                "session_forensics_json": "{\"platform\":\"claude_code\",\"sidecars\":{\"teams\":{\"totalMessages\":2}}}",
            }
        ]

    async def count(self, project_id, filters):
        return 1

    async def get_logs(self, session_id):
        return []

    async def get_model_facets(self, project_id, include_subagents=True):
        self.last_include_subagents_for_facets = include_subagents
        return [
            {"model": "claude-opus-4-5-20251101", "count": 7},
            {"model": "claude-sonnet-4-0-20251001", "count": 3},
        ]

    async def get_platform_facets(self, project_id, include_subagents=True):
        self.last_include_subagents_for_platform_facets = include_subagents
        return [
            {"platform_type": "Claude Code", "platform_version": "2.1.52", "count": 9},
            {"platform_type": "Claude Code", "platform_version": "2.1.51", "count": 2},
        ]


class _FakeSessionDetailRepo:
    async def get_by_id(self, session_id):
        if session_id == "S-main":
            return {"id": session_id}
        return None


class _FakeFullSessionRepo:
    async def get_by_id(self, session_id):
        if session_id == "S-main":
            return {
                "id": "S-main",
                "project_id": "project-1",
                "task_id": "",
                "status": "completed",
                "model": "claude-sonnet",
                "platform_type": "Claude Code",
                "platform_version": "2.1.52",
                "platform_versions_json": "[\"2.1.52\"]",
                "platform_version_transitions_json": "[]",
                "session_type": "session",
                "parent_session_id": None,
                "root_session_id": "S-main",
                "agent_id": None,
                "thread_kind": "root",
                "conversation_family_id": "S-main",
                "context_inheritance": "fresh",
                "fork_parent_session_id": None,
                "fork_point_log_id": None,
                "fork_point_entry_uuid": None,
                "fork_point_parent_entry_uuid": None,
                "fork_depth": 0,
                "fork_count": 1,
                "duration_seconds": 1,
                "tokens_in": 1,
                "tokens_out": 1,
                "model_io_tokens": 2,
                "cache_creation_input_tokens": 3,
                "cache_read_input_tokens": 5,
                "cache_input_tokens": 8,
                "observed_tokens": 10,
                "tool_reported_tokens": 13,
                "tool_result_input_tokens": 21,
                "tool_result_output_tokens": 34,
                "tool_result_cache_creation_input_tokens": 55,
                "tool_result_cache_read_input_tokens": 89,
                "total_cost": 0.0,
                "started_at": "2026-02-16T00:00:00Z",
                "ended_at": "2026-02-16T00:00:01Z",
                "created_at": "2026-02-16T00:00:00Z",
                "updated_at": "2026-02-16T00:00:01Z",
                "quality_rating": 0,
                "friction_rating": 0,
                "git_commit_hash": None,
                "git_commit_hashes_json": "[]",
                "git_author": None,
                "git_branch": None,
                "thinking_level": "high",
                "impact_history_json": "[]",
                "session_forensics_json": "{\"platform\":\"claude_code\"}",
                "timeline_json": "[]",
            }
        if session_id == "S-fork-1":
            return {
                "id": "S-fork-1",
                "project_id": "project-1",
                "session_forensics_json": "{\"forkSummary\":{\"entryCount\":2}}",
            }
        return None

    async def get_logs(self, session_id):
        return []

    async def get_tool_usage(self, session_id):
        return []

    async def get_file_updates(self, session_id):
        return []

    async def get_artifacts(self, session_id):
        return []

    async def list_relationships(self, project_id, session_id):
        return [
            {
                "id": "REL-1",
                "parent_session_id": "S-main",
                "child_session_id": "S-fork-1",
                "relationship_type": "fork",
                "context_inheritance": "full",
                "source_platform": "claude_code",
                "parent_entry_uuid": "entry-parent",
                "child_entry_uuid": "entry-fork-1",
                "source_log_id": "log-4",
                "metadata_json": json.dumps(
                    {
                        "label": "Fork 1",
                        "forkPointTimestamp": "2026-02-16T00:00:00Z",
                        "forkPointPreview": "fork preview",
                        "entryCount": 2,
                    }
                ),
            }
        ]


class _FakeCanonicalSessionMessageRepo:
    async def list_by_session(self, session_id):
        if session_id != "S-main":
            return []
        return [
            {
                "message_index": 0,
                "source_log_id": "log-0",
                "message_id": "message-1",
                "role": "assistant",
                "message_type": "message",
                "content": "hello from canonical",
                "event_timestamp": "2026-02-16T00:00:00Z",
                "agent_name": "Planner",
                "tool_name": None,
                "tool_call_id": None,
                "related_tool_call_id": "",
                "linked_session_id": "",
                "entry_uuid": "entry-1",
                "parent_entry_uuid": "",
                "source_provenance": "canonical_table",
                "metadata_json": "{\"custom\":true}",
            }
        ]


class _FakeCanonicalCompatibilitySessionMessageRepo:
    async def list_by_session(self, session_id):
        if session_id == "S-main":
            return [
                {
                    "message_index": 0,
                    "source_log_id": "log-command",
                    "message_id": "message-command",
                    "role": "user",
                    "message_type": "command",
                    "content": "/dev:execute-phase",
                    "event_timestamp": "2026-02-16T00:00:00Z",
                    "agent_name": "Planner",
                    "tool_name": None,
                    "tool_call_id": None,
                    "related_tool_call_id": "",
                    "linked_session_id": "",
                    "entry_uuid": "entry-command",
                    "parent_entry_uuid": "",
                    "source_provenance": "canonical_table",
                    "metadata_json": "{\"args\":\"1 docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md\"}",
                },
                {
                    "message_index": 1,
                    "source_log_id": "log-tool",
                    "message_id": "message-tool",
                    "role": "assistant",
                    "message_type": "tool",
                    "content": "ran bash",
                    "event_timestamp": "2026-02-16T00:00:01Z",
                    "agent_name": "Planner",
                    "tool_name": "bash",
                    "tool_call_id": "tool-1",
                    "related_tool_call_id": "",
                    "linked_session_id": "",
                    "entry_uuid": "entry-tool",
                    "parent_entry_uuid": "entry-command",
                    "source_provenance": "canonical_table",
                    "metadata_json": "{\"toolArgs\":\"{\\\"cmd\\\":\\\"pytest\\\"}\",\"toolStatus\":\"success\"}",
                },
            ]
        if session_id == "S-parent":
            return [
                {
                    "message_index": 0,
                    "source_log_id": "log-parent-tool",
                    "message_id": "message-parent-tool",
                    "role": "assistant",
                    "message_type": "tool",
                    "content": "",
                    "event_timestamp": "2026-02-16T00:00:00Z",
                    "agent_name": "Coordinator",
                    "tool_name": "Task",
                    "tool_call_id": "task-1",
                    "related_tool_call_id": "",
                    "linked_session_id": "S-main",
                    "entry_uuid": "entry-parent-tool",
                    "parent_entry_uuid": "",
                    "source_provenance": "canonical_table",
                    "metadata_json": "{\"toolArgs\":\"{\\\"subagent_type\\\":\\\"python-backend-engineer\\\"}\",\"toolStatus\":\"success\"}",
                }
            ]
        return []


class _FakeLinkRepo:
    async def get_links_for(self, entity_type, entity_id, link_type=None):
        return [
            {
                "source_type": "feature",
                "source_id": "feat-alpha",
                "target_type": "session",
                "target_id": "S-main",
                "confidence": 0.8,
                "metadata_json": json.dumps(
                    {
                        "linkStrategy": "session_evidence",
                        "signals": [{"type": "file_write"}, {"type": "command_args_path"}],
                        "commands": ["/clear", "/model", "/dev:execute-phase"],
                        "commitHashes": ["abc1234"],
                        "ambiguityShare": 0.64,
                    }
                ),
            },
            {
                "source_type": "document",
                "source_id": "DOC-1",
                "target_type": "session",
                "target_id": "S-main",
                "confidence": 1.0,
                "metadata_json": "{}",
            },
        ]


class _MutableFakeLinkRepo:
    def __init__(self, links=None):
        self.links = list(links or [])

    async def get_links_for(self, entity_type, entity_id, link_type=None):
        return list(self.links)

    async def upsert(self, link_data):
        key = (
            str(link_data.get("source_type") or ""),
            str(link_data.get("source_id") or ""),
            str(link_data.get("target_type") or ""),
            str(link_data.get("target_id") or ""),
            str(link_data.get("link_type") or "related"),
        )
        for index, existing in enumerate(self.links):
            existing_key = (
                str(existing.get("source_type") or ""),
                str(existing.get("source_id") or ""),
                str(existing.get("target_type") or ""),
                str(existing.get("target_id") or ""),
                str(existing.get("link_type") or "related"),
            )
            if existing_key == key:
                merged = dict(existing)
                merged.update(link_data)
                self.links[index] = merged
                return
        self.links.append(dict(link_data))

    async def delete_link(self, source_type, source_id, target_type, target_id, link_type="related"):
        kept = []
        for row in self.links:
            if (
                str(row.get("source_type") or "") == source_type
                and str(row.get("source_id") or "") == source_id
                and str(row.get("target_type") or "") == target_type
                and str(row.get("target_id") or "") == target_id
                and str(row.get("link_type") or "related") == link_type
            ):
                continue
            kept.append(row)
        self.links = kept


class _FakeFeatureRepo:
    async def get_by_id(self, feature_id):
        feature_map = {
            "feat-alpha": {
                "id": "feat-alpha",
                "name": "Feature Alpha",
                "status": "in-progress",
                "category": "enhancement",
                "updated_at": "2026-02-16T12:00:00Z",
                "total_tasks": 10,
                "completed_tasks": 4,
            },
            "feat-beta": {
                "id": "feat-beta",
                "name": "Feature Beta",
                "status": "backlog",
                "category": "feature",
                "updated_at": "2026-02-16T11:00:00Z",
                "total_tasks": 5,
                "completed_tasks": 1,
            },
        }
        return feature_map.get(feature_id)


class SessionApiRouterTests(unittest.IsolatedAsyncioTestCase):
    def test_derive_session_title_prefers_subagent_type_for_subagent(self) -> None:
        title = api_router._derive_session_title(
            session_metadata=None,
            summary="",
            session_id="S-agent-1",
            session_type="subagent",
            subagent_type="python-backend-engineer",
        )
        self.assertEqual(title, "python-backend-engineer")

    def test_subagent_type_from_logs_resolves_from_tool_and_linked_session(self) -> None:
        own_logs = [
            {
                "type": "tool",
                "tool_name": "Agent",
                "linked_session_id": "S-agent-xyz",
                "metadata_json": "{\"taskSubagentType\":\"python-backend-engineer\"}",
                "tool_args": "{}",
            }
        ]
        parent_logs = [
            {
                "type": "tool",
                "tool_name": "Task",
                "linked_session_id": "S-agent-abc",
                "metadata_json": "{\"taskSubagentType\":\"frontend-architect\"}",
                "tool_args": "{}",
            },
            {
                "type": "tool",
                "tool_name": "Task",
                "linked_session_id": "S-agent-target",
                "metadata_json": "{}",
                "tool_args": "{\"subagent_type\":\"python-backend-engineer\"}",
            },
        ]

        from_own = api_router._subagent_type_from_logs(own_logs, target_linked_session_id="S-agent-xyz")
        from_parent = api_router._subagent_type_from_logs(parent_logs, target_linked_session_id="S-agent-target")

        self.assertEqual(from_own, "python-backend-engineer")
        self.assertEqual(from_parent, "python-backend-engineer")

    def test_subagent_type_from_logs_accepts_normalized_transcript_payloads(self) -> None:
        normalized_logs = [
            {
                "type": "tool",
                "linkedSessionId": "S-agent-target",
                "metadata": {},
                "toolCall": {
                    "name": "Task",
                    "args": "{\"subagent_type\":\"python-backend-engineer\"}",
                },
            }
        ]

        resolved = api_router._subagent_type_from_logs(
            normalized_logs,
            target_linked_session_id="S-agent-target",
        )

        self.assertEqual(resolved, "python-backend-engineer")

    async def test_list_sessions_defaults_to_excluding_subagents(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)

        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.list_sessions(
                include_subagents=False,
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(response.total, 1)
        self.assertFalse(repo.last_filters["include_subagents"])
        self.assertEqual(response.items[0].rootSessionId, "S-main")
        self.assertEqual(response.items[0].threadKind, "root")
        self.assertEqual(response.items[0].conversationFamilyId, "S-main")
        self.assertEqual(response.items[0].thinkingLevel, "high")
        self.assertEqual(response.items[0].sessionForensics.get("platform"), "claude_code")
        self.assertEqual(response.items[0].observedTokens, 10)
        self.assertEqual(response.items[0].cacheInputTokens, 8)
        self.assertEqual(response.items[0].toolReportedTokens, 13)
        self.assertAlmostEqual(response.items[0].cacheShare, 0.8)
        self.assertAlmostEqual(response.items[0].outputShare, 0.5)

    async def test_list_sessions_uses_canonical_logs_for_title_and_badges(self) -> None:
        class _FakeCanonicalListRepo(_FakeRepo):
            async def list_paginated(self, offset, limit, project_id, sort_by, sort_order, filters):
                rows = await super().list_paginated(offset, limit, project_id, sort_by, sort_order, filters)
                rows[0]["session_type"] = "subagent"
                rows[0]["parent_session_id"] = "S-parent"
                return rows

        repo = _FakeCanonicalListRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(
            project=project,
            session_repo=repo,
            session_message_repo=_FakeCanonicalCompatibilitySessionMessageRepo(),
        )

        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.list_sessions(
                include_subagents=True,
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(response.items[0].title, "python-backend-engineer")
        self.assertEqual(response.items[0].agentsUsed, ["Planner"])
        self.assertEqual(response.items[0].toolSummary, ["bash x1"])

    async def test_list_sessions_accepts_thread_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)

        with patch.object(api_router, "load_session_mappings", return_value=[]):
            await api_router.list_sessions(
                include_subagents=True,
                root_session_id="S-main",
                thread_kind="fork",
                conversation_family_id="S-main",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertTrue(repo.last_filters["include_subagents"])
        self.assertEqual(repo.last_filters["root_session_id"], "S-main")
        self.assertEqual(repo.last_filters["thread_kind"], "fork")
        self.assertEqual(repo.last_filters["conversation_family_id"], "S-main")

    async def test_list_sessions_accepts_model_identity_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)
        with patch.object(api_router, "load_session_mappings", return_value=[]):
            await api_router.list_sessions(
                model_provider="Claude",
                model_family="Opus",
                model_version="Opus 4.5",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(repo.last_filters["model_provider"], "Claude")
        self.assertEqual(repo.last_filters["model_family"], "Opus")
        self.assertEqual(repo.last_filters["model_version"], "Opus 4.5")

    async def test_list_sessions_accepts_platform_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)
        with patch.object(api_router, "load_session_mappings", return_value=[]):
            await api_router.list_sessions(
                platform_type="Claude Code",
                platform_version="2.1.52",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(repo.last_filters["platform_type"], "Claude Code")
        self.assertEqual(repo.last_filters["platform_version"], "2.1.52")

    async def test_get_session_model_facets_returns_normalized_values(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)

        response = await api_router.get_session_model_facets(
            include_subagents=False,
            request_context=_request_context(project.id),
            core_ports=core_ports,
        )

        self.assertEqual(len(response), 2)
        self.assertFalse(repo.last_include_subagents_for_facets)
        self.assertEqual(response[0].modelProvider, "Claude")
        self.assertEqual(response[0].modelFamily, "Opus")
        self.assertEqual(response[0].modelVersion, "Opus 4.5")

    async def test_get_session_platform_facets_returns_values(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)

        response = await api_router.get_session_platform_facets(
            include_subagents=False,
            request_context=_request_context(project.id),
            core_ports=core_ports,
        )

        self.assertEqual(len(response), 2)
        self.assertFalse(repo.last_include_subagents_for_platform_facets)
        self.assertEqual(response[0].platformType, "Claude Code")
        self.assertEqual(response[0].platformVersion, "2.1.52")

    async def test_get_session_includes_fork_relationships_and_summaries(self) -> None:
        repo = _FakeFullSessionRepo()
        project = types.SimpleNamespace(id="project-1")
        usage_payload = {
            "usageEvents": [
                {
                    "id": "evt-1",
                    "projectId": "project-1",
                    "sessionId": "S-main",
                    "rootSessionId": "S-main",
                    "linkedSessionId": "",
                    "sourceLogId": "log-1",
                    "capturedAt": "2026-02-16T00:00:00Z",
                    "eventKind": "message",
                    "model": "claude-sonnet",
                    "toolName": "",
                    "agentName": "planner",
                    "tokenFamily": "model_input",
                    "deltaTokens": 2,
                    "costUsdModelIO": 0.0,
                    "metadata": {},
                }
            ],
            "usageAttributions": [
                {
                    "eventId": "evt-1",
                    "entityType": "skill",
                    "entityId": "symbols",
                    "attributionRole": "primary",
                    "weight": 1.0,
                    "method": "explicit_skill_invocation",
                    "confidence": 1.0,
                    "metadata": {},
                }
            ],
            "usageAttributionSummary": {
                "generatedAt": "2026-02-16T00:00:01Z",
                "total": 1,
                "offset": 0,
                "limit": 1,
                "rows": [
                    {
                        "entityType": "skill",
                        "entityId": "symbols",
                        "entityLabel": "symbols",
                        "exclusiveTokens": 2,
                        "supportingTokens": 0,
                        "exclusiveModelIOTokens": 2,
                        "exclusiveCacheInputTokens": 0,
                        "supportingModelIOTokens": 0,
                        "supportingCacheInputTokens": 0,
                        "exclusiveCostUsdModelIO": 0.0,
                        "supportingCostUsdModelIO": 0.0,
                        "eventCount": 1,
                        "primaryEventCount": 1,
                        "supportingEventCount": 0,
                        "sessionCount": 1,
                        "averageConfidence": 1.0,
                        "methods": [],
                    }
                ],
                "summary": {
                    "entityCount": 1,
                    "sessionCount": 1,
                    "eventCount": 1,
                    "totalExclusiveTokens": 2,
                    "totalSupportingTokens": 0,
                    "totalExclusiveModelIOTokens": 2,
                    "totalExclusiveCacheInputTokens": 0,
                    "totalExclusiveCostUsdModelIO": 0.0,
                    "averageConfidence": 1.0,
                },
            },
            "usageAttributionCalibration": {
                "projectId": "project-1",
                "sessionCount": 1,
                "eventCount": 1,
                "attributedEventCount": 1,
                "primaryAttributedEventCount": 1,
                "ambiguousEventCount": 0,
                "unattributedEventCount": 0,
                "primaryCoverage": 1.0,
                "supportingCoverage": 1.0,
                "sessionModelIOTokens": 2,
                "exclusiveModelIOTokens": 2,
                "modelIOGap": 0,
                "sessionCacheInputTokens": 8,
                "exclusiveCacheInputTokens": 0,
                "cacheGap": 8,
                "averageConfidence": 1.0,
                "confidenceBands": [],
                "methodMix": [],
                "generatedAt": "2026-02-16T00:00:01Z",
            },
        }

        core_ports = _core_ports(project=project, session_repo=repo)
        with patch.object(api_router, "load_session_mappings", return_value=[]), patch.object(api_router, "get_session_usage_attribution_details", return_value=usage_payload):
            response = await api_router.get_session(
                "S-main",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(response.id, "S-main")
        self.assertEqual(response.threadKind, "root")
        self.assertEqual(response.conversationFamilyId, "S-main")
        self.assertEqual(len(response.sessionRelationships or []), 1)
        self.assertEqual(str((response.sessionRelationships or [])[0].get("childSessionId") or ""), "S-fork-1")
        self.assertEqual(len(response.forks or []), 1)
        self.assertEqual(str((response.forks or [])[0].get("sessionId") or ""), "S-fork-1")
        self.assertEqual(response.modelIOTokens, 2)
        self.assertEqual(response.cacheCreationInputTokens, 3)
        self.assertEqual(response.cacheReadInputTokens, 5)
        self.assertEqual(response.cacheInputTokens, 8)
        self.assertEqual(response.observedTokens, 10)
        self.assertEqual(response.toolReportedTokens, 13)
        self.assertEqual(len(response.usageEvents or []), 1)
        self.assertEqual((response.usageAttributionSummary or api_router.SessionUsageAggregateResponse()).summary.totalExclusiveTokens, 2)
        self.assertEqual((response.usageAttributionCalibration or api_router.SessionUsageCalibrationSummary()).modelIOGap, 0)

    async def test_get_session_omits_usage_attribution_when_disabled(self) -> None:
        repo = _FakeFullSessionRepo()
        project = types.SimpleNamespace(id="project-1")

        core_ports = _core_ports(project=project, session_repo=repo)
        with patch.object(api_router, "load_session_mappings", return_value=[]), patch.object(api_router, "usage_attribution_enabled", return_value=False):
            response = await api_router.get_session(
                "S-main",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(response.usageEvents, [])
        self.assertEqual(response.usageAttributions, [])
        self.assertIsNone(response.usageAttributionSummary)
        self.assertIsNone(response.usageAttributionCalibration)
        self.assertEqual(response.toolResultInputTokens, 21)
        self.assertEqual(response.toolResultOutputTokens, 34)
        self.assertEqual(response.toolResultCacheCreationInputTokens, 55)
        self.assertEqual(response.toolResultCacheReadInputTokens, 89)
        self.assertAlmostEqual(response.cacheShare, 0.8)

    async def test_get_session_includes_intelligence_summary_when_available(self) -> None:
        repo = _FakeFullSessionRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(project=project, session_repo=repo)

        with patch.object(api_router, "load_session_mappings", return_value=[]), patch.object(
            api_router,
            "usage_attribution_enabled",
            return_value=False,
        ), patch.object(
            api_router.session_intelligence_read_service,
            "get_session_detail",
            return_value=types.SimpleNamespace(
                summary={
                    "sessionId": "S-main",
                    "rootSessionId": "S-main",
                    "startedAt": "2026-02-16T00:00:00Z",
                    "endedAt": "2026-02-16T00:00:01Z",
                    "sentiment": {
                        "label": "negative",
                        "score": -0.6,
                        "confidence": 0.8,
                        "factCount": 1,
                        "flaggedCount": 1,
                    },
                    "churn": {
                        "label": "stable",
                        "score": 0.1,
                        "confidence": 0.7,
                        "factCount": 0,
                        "flaggedCount": 0,
                    },
                    "scopeDrift": {
                        "label": "in_scope",
                        "score": 0.0,
                        "confidence": 0.0,
                        "factCount": 0,
                        "flaggedCount": 0,
                    },
                }
            ),
        ):
            response = await api_router.get_session(
                "S-main",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertIsNotNone(response.intelligenceSummary)
        self.assertEqual(response.intelligenceSummary.sessionId, "S-main")
        self.assertEqual(response.intelligenceSummary.sentiment.label, "negative")

    async def test_get_session_preserves_api_shape_when_using_canonical_messages(self) -> None:
        repo = _FakeFullSessionRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(
            project=project,
            session_repo=repo,
            session_message_repo=_FakeCanonicalSessionMessageRepo(),
        )

        with patch.object(api_router, "load_session_mappings", return_value=[]), patch.object(api_router, "usage_attribution_enabled", return_value=False):
            response = await api_router.get_session(
                "S-main",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(len(response.logs), 1)
        self.assertEqual(response.logs[0].id, "log-0")
        self.assertEqual(response.logs[0].content, "hello from canonical")
        self.assertEqual(response.logs[0].speaker, "agent")
        self.assertEqual(response.logs[0].metadata.get("sourceProvenance"), "canonical_table")
        self.assertEqual(response.logs[0].metadata.get("entryUuid"), "entry-1")
        self.assertAlmostEqual(response.outputShare, 0.5)

    async def test_get_session_uses_canonical_logs_for_title_and_badges(self) -> None:
        class _FakeCanonicalFullSessionRepo(_FakeFullSessionRepo):
            async def get_by_id(self, session_id):
                if session_id == "S-main":
                    row = await super().get_by_id(session_id)
                    assert row is not None
                    row["session_type"] = "subagent"
                    row["parent_session_id"] = "S-parent"
                    return row
                if session_id == "S-parent":
                    return {
                        "id": "S-parent",
                        "project_id": "project-1",
                        "session_type": "session",
                    }
                return await super().get_by_id(session_id)

        repo = _FakeCanonicalFullSessionRepo()
        project = types.SimpleNamespace(id="project-1")
        core_ports = _core_ports(
            project=project,
            session_repo=repo,
            session_message_repo=_FakeCanonicalCompatibilitySessionMessageRepo(),
        )

        with patch.object(api_router, "load_session_mappings", return_value=[]), patch.object(api_router, "usage_attribution_enabled", return_value=False):
            response = await api_router.get_session(
                "S-main",
                request_context=_request_context(project.id),
                core_ports=core_ports,
            )

        self.assertEqual(response.title, "python-backend-engineer")
        self.assertEqual(response.agentsUsed, ["Planner"])
        self.assertEqual(response.toolSummary, ["bash x1"])
        self.assertEqual(len(response.logs), 2)

    async def test_get_session_linked_features_returns_scored_links(self) -> None:
        session_repo = _FakeSessionDetailRepo()
        link_repo = _FakeLinkRepo()
        feature_repo = _FakeFeatureRepo()

        response = await api_router.get_session_linked_features(
            "S-main",
            request_context=_request_context(),
            core_ports=_core_ports(session_repo=session_repo, link_repo=link_repo, feature_repo=feature_repo),
        )

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].featureId, "feat-alpha")
        self.assertEqual(response[0].featureName, "Feature Alpha")
        self.assertTrue(response[0].isPrimaryLink)
        self.assertIn("file_write", response[0].reasons)
        self.assertEqual(response[0].commands, ["/dev:execute-phase"])

    async def test_get_session_linked_features_404_when_missing(self) -> None:
        session_repo = _FakeSessionDetailRepo()

        with self.assertRaises(HTTPException) as ctx:
            await api_router.get_session_linked_features(
                "S-missing",
                request_context=_request_context(),
                core_ports=_core_ports(session_repo=session_repo),
            )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_get_session_linked_features_respects_manual_related_role(self) -> None:
        session_repo = _FakeSessionDetailRepo()
        link_repo = _MutableFakeLinkRepo(
            links=[
                {
                    "source_type": "feature",
                    "source_id": "feat-alpha",
                    "target_type": "session",
                    "target_id": "S-main",
                    "confidence": 1.0,
                    "metadata_json": json.dumps(
                        {
                            "linkStrategy": "manual_set",
                            "linkRole": "related",
                        }
                    ),
                }
            ]
        )
        feature_repo = _FakeFeatureRepo()

        response = await api_router.get_session_linked_features(
            "S-main",
            request_context=_request_context(),
            core_ports=_core_ports(session_repo=session_repo, link_repo=link_repo, feature_repo=feature_repo),
        )

        self.assertEqual(len(response), 1)
        self.assertFalse(response[0].isPrimaryLink)
        self.assertEqual(response[0].confidence, 1.0)

    async def test_upsert_session_linked_feature_primary_replaces_existing_primary(self) -> None:
        session_repo = _FakeSessionDetailRepo()
        link_repo = _MutableFakeLinkRepo(
            links=[
                {
                    "source_type": "feature",
                    "source_id": "feat-alpha",
                    "target_type": "session",
                    "target_id": "S-main",
                    "link_type": "related",
                    "origin": "auto",
                    "confidence": 0.95,
                    "metadata_json": json.dumps(
                        {
                            "linkStrategy": "session_evidence",
                        }
                    ),
                }
            ]
        )
        feature_repo = _FakeFeatureRepo()

        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.upsert_session_linked_feature(
                "S-main",
                api_router.SessionFeatureLinkMutationRequest(featureId="feat-beta", linkRole="primary"),
                request_context=_request_context(),
                core_ports=_core_ports(session_repo=session_repo, link_repo=link_repo, feature_repo=feature_repo),
            )

        by_feature_id = {item.featureId: item for item in response}
        self.assertTrue(by_feature_id["feat-beta"].isPrimaryLink)
        self.assertEqual(by_feature_id["feat-beta"].confidence, 1.0)
        self.assertFalse(by_feature_id["feat-alpha"].isPrimaryLink)

    async def test_upsert_session_linked_feature_related_sets_full_confidence(self) -> None:
        session_repo = _FakeSessionDetailRepo()
        link_repo = _MutableFakeLinkRepo()
        feature_repo = _FakeFeatureRepo()

        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.upsert_session_linked_feature(
                "S-main",
                api_router.SessionFeatureLinkMutationRequest(featureId="feat-beta", linkRole="related"),
                request_context=_request_context(),
                core_ports=_core_ports(session_repo=session_repo, link_repo=link_repo, feature_repo=feature_repo),
            )

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].featureId, "feat-beta")
        self.assertEqual(response[0].confidence, 1.0)
        self.assertFalse(response[0].isPrimaryLink)

    async def test_delete_session_linked_feature_removes_link(self) -> None:
        session_repo = _FakeSessionDetailRepo()
        link_repo = _MutableFakeLinkRepo(
            links=[
                {
                    "source_type": "feature",
                    "source_id": "feat-alpha",
                    "target_type": "session",
                    "target_id": "S-main",
                    "link_type": "related",
                    "origin": "manual",
                    "confidence": 1.0,
                    "metadata_json": json.dumps({"linkStrategy": "manual_set", "linkRole": "primary"}),
                }
            ]
        )
        feature_repo = _FakeFeatureRepo()

        with patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.delete_session_linked_feature(
                "S-main",
                "feat-alpha",
                request_context=_request_context(),
                core_ports=_core_ports(session_repo=session_repo, link_repo=link_repo, feature_repo=feature_repo),
            )

        self.assertEqual(response, [])


if __name__ == "__main__":
    unittest.main()
