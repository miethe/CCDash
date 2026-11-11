"""Metadata-only exact joins, unit honesty and project-scoped HTTP contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.adapters.auth.local import PermitAllAuthorizationPolicy
from backend.application.context import (
    AuthProviderMetadata, Principal, PrincipalMembership, ProjectScope,
    RequestContext, TraceContext,
)
from backend.application.services.authorization import RoleBindingAuthorizationPolicy
from backend.routers.api import sessions_router
from backend.request_scope import get_core_ports, get_request_context
from backend.services.session_context_attribution import (
    load_session_context_attribution,
)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class ContextAttributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receipts.json"
        self.row = {
            "id": "local_synthetic",
            "project_id": "project-a",
            "cwd": "/synthetic/project",
            "platform_type": "claude_code",
            "session_forensics_json": json.dumps(
                {"rawSessionId": "synthetic-native", "platform": "claude_code"}
            ),
        }
        self.record = {
            "ccdashSessionKey": digest(self.row["id"]),
            "nativeSessionKey": digest("synthetic-native"),
            "projectPathKey": digest(self.row["cwd"]),
            "platform": "claude_code",
            "stages": [
                {
                    "id": "startup-1",
                    "phase": "first_observed_after_sessionstart",
                    "observedAt": "2026-11-03T10:00:00Z",
                    "source": "synthetic-counter",
                    "sourceVersion": "1",
                    "unit": "tokens",
                    "amount": 0,
                    "method": "observed usage counters",
                    "provenance": "synthetic metadata",
                    "layers": [
                        {
                            "name": "identity",
                            "unit": "unknown",
                            "amount": None,
                            "source": "unrecorded",
                            "sourceVersion": None,
                            "attribution": "missing",
                        },
                        {
                            "name": "cache read",
                            "unit": "tokens",
                            "amount": 50,
                            "source": "usage",
                            "sourceVersion": "1",
                            "attribution": "unattributed",
                        },
                    ],
                }
            ],
            "unknowns": ["Layer identity is not measured."],
        }
        self.write([self.record])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, records):
        self.path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "generatedAt": "2026-11-03T11:00:00Z",
                    "sessions": records,
                }
            )
        )

    def test_exact_join_zero_and_named_unknown_layers_are_retained(self):
        before = self.path.read_bytes()
        result = load_session_context_attribution(self.row, source_path=self.path)
        self.assertEqual(result.coverage["joinStatus"], "matched")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.stages[0].amount, 0)
        layer = result.stages[0].layers[0]
        self.assertEqual(
            (layer.name, layer.unit, layer.amount, layer.attribution),
            ("identity", "unknown", None, "missing"),
        )
        self.assertEqual(result.stages[0].layers[1].amount, 50)
        self.assertEqual(self.path.read_bytes(), before)
        serialized = result.model_dump_json()
        self.assertNotIn("synthetic-native", serialized)
        self.assertNotIn("nativeSessionKey", serialized)
        self.assertNotIn("/synthetic/project", serialized)

    def test_wrong_project_native_platform_and_duplicates_never_match(self):
        for row in [
            {**self.row, "cwd": "/synthetic/other"},
            {**self.row, "session_forensics_json": "{}"},
            {**self.row, "platform_type": "codex"},
        ]:
            result = load_session_context_attribution(row, source_path=self.path)
            self.assertEqual(result.coverage["joinStatus"], "unmatched")
            self.assertEqual(result.stages, [])
        self.write([self.record, self.record])
        result = load_session_context_attribution(self.row, source_path=self.path)
        self.assertEqual(result.coverage["joinStatus"], "ambiguous")
        self.assertEqual(result.stages, [])

    def test_missing_source_and_invalid_amounts_stay_unknown(self):
        result = load_session_context_attribution(
            self.row, source_path=self.path.with_name("absent")
        )
        self.assertEqual(result.coverage["joinStatus"], "source_unavailable")
        self.assertEqual(result.status, "unmeasured")
        self.record["stages"][0]["amount"] = -9
        self.record["stages"][0]["layers"][1]["amount"] = False
        self.write([self.record])
        result = load_session_context_attribution(self.row, source_path=self.path)
        self.assertIsNone(result.stages[0].amount)
        self.assertIsNone(result.stages[0].layers[1].amount)

    def test_http_requires_explicit_project_and_existing_scoped_session(self):
        row = self.row

        class Repo:
            async def get_by_id(self, session_id, project_id=None):
                return (
                    row
                    if (session_id, project_id) == (row["id"], row["project_id"])
                    else None
                )

        class Registry:
            def get_project(self, key):
                return (
                    SimpleNamespace(id=key)
                    if key in {"project-a", "project-b"}
                    else None
                )

        app = FastAPI()
        app.include_router(sessions_router)
        app.dependency_overrides[get_core_ports] = lambda: SimpleNamespace(
            authorization_policy=PermitAllAuthorizationPolicy(),
            storage=SimpleNamespace(sessions=lambda: Repo()),
            workspace_registry=Registry(),
        )
        app.dependency_overrides[get_request_context] = lambda: self.hosted_context("project-b")
        with (
            patch(
                "backend.config.CCDASH_SESSION_CONTEXT_ATTRIBUTION_PATH", str(self.path)
            ),
            TestClient(app) as client,
        ):
            base = "/api/sessions/local_synthetic/context-attribution"
            self.assertEqual(client.get(base).status_code, 400)
            self.assertEqual(
                client.get(base + "?project_id=project-b").status_code, 404
            )
            self.assertEqual(client.get(base + "?project_id=missing").status_code, 404)
            response = client.get(base + "?project_id=project-a")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["coverage"]["joinStatus"], "matched")
            self.assertEqual(
                response.json()["stages"][0]["layers"][0]["unit"], "unknown"
            )

    def hosted_context(self, project_id, authorized_projects=None):
        return RequestContext(
            principal=Principal(
                subject="synthetic-user", display_name="Synthetic user", auth_mode="oidc",
                provider=AuthProviderMetadata(provider_id="synthetic", hosted=True),
                memberships=tuple(
                    PrincipalMembership(
                        workspace_id=key, role="viewer", scope_type="project", scope_id=key,
                    )
                    for key in (authorized_projects or (project_id,))
                ),
            ),
            workspace=None,
            project=ProjectScope(
                project_id=project_id, project_name=project_id,
                root_path=Path("/synthetic"), sessions_dir=Path("/synthetic/sessions"),
                docs_dir=Path("/synthetic/docs"), progress_dir=Path("/synthetic/progress"),
            ),
            runtime_profile="api", trace=TraceContext(request_id="synthetic-scope-check"),
        )

    def test_http_authorizes_target_project_before_reading_metadata(self):
        cases = (
            ("cross-project denied", "project-b", ("project-b",), 403),
            ("own project allowed", "project-a", ("project-a",), 200),
            ("cross-project authorized", "project-b", ("project-b", "project-a"), 200),
        )
        for label, current_project, authorized_projects, expected_status in cases:
            with self.subTest(label=label):
                context = self.hosted_context(current_project, authorized_projects)
                repo = SimpleNamespace(get_by_id=AsyncMock(return_value=self.row))
                policy = RoleBindingAuthorizationPolicy()
                policy.authorize = AsyncMock(wraps=policy.authorize)
                ports = SimpleNamespace(
                    authorization_policy=policy,
                    storage=SimpleNamespace(sessions=lambda: repo),
                    workspace_registry=SimpleNamespace(
                        get_project=lambda key: SimpleNamespace(id=key),
                    ),
                )
                app = FastAPI()
                app.include_router(sessions_router)
                app.dependency_overrides[get_request_context] = lambda: context
                app.dependency_overrides[get_core_ports] = lambda: ports
                with (
                    patch("backend.config.CCDASH_SESSION_CONTEXT_ATTRIBUTION_PATH", str(self.path)),
                    patch("backend.routers.api.load_session_context_attribution", wraps=load_session_context_attribution) as loader,
                    TestClient(app) as client,
                ):
                    response = client.get(
                        "/api/sessions/local_synthetic/context-attribution?project_id=project-a"
                    )
                    self.assertEqual(response.status_code, expected_status)
                    policy.authorize.assert_awaited_once_with(
                        context, action="session:read", resource="project:project-a",
                    )
                    if expected_status == 403:
                        self.assertEqual(response.json()["detail"], {
                            "error": "forbidden",
                            "code": "permission_not_granted",
                            "reason": "Permission 'session:read' is not granted for the requested scope.",
                            "action": "session:read",
                            "resource": "project:project-a",
                        })
                        repo.get_by_id.assert_not_awaited()
                        loader.assert_not_called()
                    else:
                        self.assertEqual(response.json()["coverage"]["joinStatus"], "matched")
                        repo.get_by_id.assert_awaited_once_with(
                            "local_synthetic", project_id="project-a",
                        )
                        loader.assert_called_once()
