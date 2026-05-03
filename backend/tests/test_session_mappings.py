import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    ProjectScope,
    RequestContext,
    TenancyContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.ports import AuthorizationDecision
from backend.routers import session_mappings as session_mappings_router

from backend.session_mappings import (
    classify_bash_command,
    classify_key_command,
    classify_session_key_metadata,
    classify_transcript_message,
    default_session_mappings,
    normalize_session_mappings,
    workflow_command_markers,
)


class _AuthorizationPolicy:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[dict] = []

    async def authorize(self, context, *, action: str, resource: str | None = None):
        self.calls.append({"action": action, "resource": resource})
        return AuthorizationDecision(
            allowed=self.allowed,
            code="permission_allowed" if self.allowed else "permission_not_granted",
            reason="test policy",
        )


class _WorkspaceRegistry:
    def __init__(self, project, *, active_project=None) -> None:
        self.project = project
        self.active_project = project if active_project is None else active_project
        self.active_calls = 0

    def get_project(self, project_id):
        return self.project if project_id == self.project.id else None

    def get_active_project(self):
        self.active_calls += 1
        return self.active_project


def _request_context(*, project_id: str | None = "project-1", hosted: bool = False) -> RequestContext:
    root = Path("/tmp/project")
    provider = AuthProviderMetadata(provider_id="oidc", issuer="issuer", hosted=True) if hosted else None
    workspace = WorkspaceScope(workspace_id=project_id, root_path=root) if project_id else None
    project = (
        ProjectScope(
            project_id=project_id,
            project_name=project_id,
            root_path=root,
            sessions_dir=root / "sessions",
            docs_dir=root / "docs",
            progress_dir=root / "progress",
        )
        if project_id
        else None
    )
    return RequestContext(
        principal=Principal(
            subject="test-user",
            display_name="Test User",
            auth_mode="oidc" if hosted else "local",
            provider=provider,
        ),
        workspace=workspace,
        project=project,
        runtime_profile="api" if hosted else "local",
        trace=TraceContext(request_id="req-1"),
        tenancy=TenancyContext(workspace_id=project_id, project_id=project_id),
    )


def _core_ports(project=None, *, authorization_policy=None, active_project=None):
    project = project or types.SimpleNamespace(id="project-1", name="Project One")
    return types.SimpleNamespace(
        workspace_registry=_WorkspaceRegistry(project, active_project=active_project),
        authorization_policy=authorization_policy or _AuthorizationPolicy(),
    )


class SessionMappingsTests(unittest.TestCase):
    def test_defaults_include_key_command_mapping(self) -> None:
        mappings = default_session_mappings()
        execute_phase = next((item for item in mappings if item.get("id") == "key-dev-execute-phase"), None)
        self.assertIsNotNone(execute_phase)
        assert execute_phase is not None
        self.assertEqual(execute_phase.get("mappingType"), "key_command")
        self.assertEqual(execute_phase.get("sessionTypeLabel"), "Phased Execution")
        expected_ids = {
            "key-dev-implement-story",
            "key-dev-complete-user-story",
            "key-fix-debug",
            "key-recovering-sessions",
        }
        mapping_ids = {str(item.get("id") or "") for item in mappings}
        self.assertTrue(expected_ids.issubset(mapping_ids))

    def test_workflow_command_markers_include_full_default_coverage(self) -> None:
        markers = workflow_command_markers(default_session_mappings())
        self.assertIn("/dev:execute-phase", markers)
        self.assertIn("/dev:quick-feature", markers)
        self.assertIn("/plan:plan-feature", markers)
        self.assertIn("/dev:implement-story", markers)
        self.assertIn("/dev:complete-user-story", markers)
        self.assertIn("/fix:debug", markers)
        self.assertIn("/recovering-sessions", markers)

    def test_classify_key_command_extracts_related_fields(self) -> None:
        mappings = default_session_mappings()
        classified = classify_key_command(
            "/dev:execute-phase",
            "4 docs/project_plans/implementation_plans/features/example-v1.md",
            {},
            mappings,
        )

        self.assertIsNotNone(classified)
        assert classified is not None
        self.assertEqual(classified.get("sessionTypeLabel"), "Phased Execution")
        self.assertEqual(classified.get("relatedPhases"), ["4"])
        self.assertEqual(classified.get("relatedFilePath"), "docs/project_plans/implementation_plans/features/example-v1.md")
        fields = {item["id"]: item["value"] for item in classified.get("fields", [])}
        self.assertEqual(fields.get("related-command"), "/dev:execute-phase")
        self.assertEqual(fields.get("related-phases"), "4")
        self.assertEqual(fields.get("feature-path"), "docs/project_plans/implementation_plans/features/example-v1.md")

    def test_classify_session_key_metadata_uses_highest_priority_match(self) -> None:
        mappings = default_session_mappings()
        result = classify_session_key_metadata(
            [
                {"name": "/dev:quick-feature", "args": "foo", "parsedCommand": {}},
                {"name": "/dev:execute-phase", "args": "2 docs/project_plans/implementation_plans/features/example-v1.md", "parsedCommand": {}},
            ],
            mappings,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("sessionTypeId"), "key-dev-execute-phase")
        self.assertEqual(result.get("sessionTypeLabel"), "Phased Execution")

    def test_classify_bash_command_ignores_key_command_rules(self) -> None:
        mappings = default_session_mappings()
        self.assertIsNone(classify_bash_command("/dev:execute-phase 1 plan.md", mappings))

    def test_classification_respects_platform_filters(self) -> None:
        mappings = default_session_mappings()
        execute_phase = next((item for item in mappings if item.get("id") == "key-dev-execute-phase"), None)
        assert execute_phase is not None
        execute_phase["platforms"] = ["claude_code"]

        match_for_claude = classify_key_command(
            "/dev:execute-phase",
            "2 docs/project_plans/implementation_plans/features/example-v1.md",
            {},
            mappings,
            platform_type="Claude Code",
        )
        self.assertIsNotNone(match_for_claude)

        match_for_codex = classify_key_command(
            "/dev:execute-phase",
            "2 docs/project_plans/implementation_plans/features/example-v1.md",
            {},
            mappings,
            platform_type="Codex",
        )
        self.assertIsNone(match_for_codex)

    def test_classify_transcript_message_matches_artifact_mapping(self) -> None:
        mappings = default_session_mappings()
        match = classify_transcript_message(
            "/mc capture \"flaky test trace\"",
            mappings,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.get("mappingId"), "artifact-capture-command")
        self.assertEqual(match.get("transcriptKind"), "artifact")
        self.assertEqual(match.get("command"), "/mc")

    def test_classify_transcript_message_matches_hook_artifact_mapping(self) -> None:
        mappings = default_session_mappings()
        match = classify_transcript_message(
            "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/notebooklm-sync-hook.sh",
            mappings,
            platform_type="Claude Code",
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.get("mappingId"), "artifact-hook-invocation")
        self.assertEqual(match.get("transcriptKind"), "artifact")
        self.assertEqual(match.get("matchText"), ".claude/hooks/notebooklm-sync-hook.sh")

    def test_normalize_transcript_fields_sanitizes_color_and_icon(self) -> None:
        mappings = normalize_session_mappings([
            {
                "id": "custom-style",
                "mappingType": "action_call",
                "label": "Custom Style",
                "category": "action",
                "pattern": r"^/ops:sync\\b",
                "transcriptLabel": "Ops Sync",
                "color": "tomato",
                "icon": "invalid icon",
                "summaryTemplate": "run {command}",
            }
        ])
        custom = next((item for item in mappings if item.get("id") == "custom-style"), None)
        self.assertIsNotNone(custom)
        assert custom is not None
        self.assertEqual(custom.get("mappingType"), "action_call")
        self.assertEqual(custom.get("transcriptKind"), "action")
        self.assertEqual(custom.get("matchScope"), "command")
        self.assertEqual(custom.get("summaryTemplate"), "run {command}")
        self.assertFalse(custom.get("icon"))
        self.assertFalse(custom.get("color"))


class SessionMappingsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_hosted_request_without_project_does_not_use_active_project(self) -> None:
        active_project = types.SimpleNamespace(id="active-project", name="Active")
        authorization_policy = _AuthorizationPolicy()
        core_ports = _core_ports(active_project=active_project, authorization_policy=authorization_policy)

        payload = await session_mappings_router.list_session_mappings(
            _request_context(project_id=None, hosted=True),
            core_ports,
        )

        self.assertEqual(payload, [])
        self.assertEqual(core_ports.workspace_registry.active_calls, 0)
        self.assertEqual(authorization_policy.calls[0]["action"], "session_mapping:read")

    async def test_update_requires_session_mapping_update_permission(self) -> None:
        core_ports = _core_ports(authorization_policy=_AuthorizationPolicy(allowed=False))
        payload = session_mappings_router.SessionMappingsPayload(mappings=[])

        with self.assertRaises(HTTPException) as ctx:
            await session_mappings_router.update_session_mappings(
                payload,
                _request_context(),
                core_ports,
            )

        self.assertEqual(ctx.exception.status_code, 403)

    async def test_list_uses_request_project(self) -> None:
        core_ports = _core_ports()
        with (
            patch.object(session_mappings_router.connection, "get_connection", return_value=object()),
            patch.object(
                session_mappings_router,
                "load_session_mappings",
                return_value=[
                    {
                        "id": "custom",
                        "mappingType": "bash",
                        "label": "Custom",
                        "pattern": "custom",
                        "transcriptLabel": "Custom",
                    }
                ],
            ) as load_mappings,
        ):
            payload = await session_mappings_router.list_session_mappings(_request_context(), core_ports)

        self.assertEqual(payload[0].id, "custom")
        load_mappings.assert_awaited_once()
        self.assertEqual(load_mappings.await_args.args[1], "project-1")


if __name__ == "__main__":
    unittest.main()
