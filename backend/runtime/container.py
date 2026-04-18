"""Runtime container and lifecycle orchestration."""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI

from backend.adapters.live_updates import InMemoryLiveEventBroker
from backend.adapters.jobs import RuntimeJobAdapter, RuntimeJobState, TelemetryExporterJob
from backend.application.context import (
    EnterpriseScope,
    RequestContext,
    RequestMetadata,
    ScopeBinding,
    StorageScope,
    TeamScope,
    TenancyContext,
    TraceContext,
)
from backend.application.live_updates import BrokerLiveEventPublisher, LiveEventBroker, LiveEventPublisher
from backend.application.live_updates.runtime_state import set_live_event_publisher
from backend.application.ports import CorePorts
from backend.application.ports.core import ProjectBinding
from backend import config
from backend.db import connection, migrations, sync_engine
from backend.db.migration_governance import validate_migration_governance_contract
from backend.db.factory import get_telemetry_queue_repository
from backend.observability import initialize as initialize_observability, shutdown as shutdown_observability
from backend.observability import otel as observability
from backend.runtime.profiles import RuntimeProfile
from backend.runtime.storage_contract import (
    build_storage_profile_validation_matrix,
    default_runtime_activity_snapshot,
    get_runtime_storage_contract,
    get_storage_capability_contract,
    validate_runtime_storage_pairing,
)
from backend.runtime_ports import build_core_ports, build_runtime_metadata, build_workspace_registry
from backend.services.integrations import TelemetryExportCoordinator, TelemetrySettingsStore

logger = logging.getLogger("ccdash.runtime")


class RuntimeContainer:
    def __init__(self, *, profile: RuntimeProfile) -> None:
        self.profile = profile
        self.storage_profile = config.STORAGE_PROFILE
        self.db: Any | None = None
        self.sync: Any | None = None
        self.ports: CorePorts | None = None
        self.lifecycle: RuntimeJobState | None = None
        self.job_adapter: RuntimeJobAdapter | None = None
        self.live_event_broker: LiveEventBroker | None = None
        self.live_event_publisher: LiveEventPublisher | None = None
        self.telemetry_exporter: TelemetryExportCoordinator | None = None
        self.telemetry_settings_store: TelemetrySettingsStore | None = None
        self.project_binding: ProjectBinding | None = None
        self.migration_status = "not_started"

    async def startup(self, app: FastAPI) -> None:
        validate_runtime_storage_pairing(self.profile, self.storage_profile)
        validate_migration_governance_contract()
        config.validate_runtime_environment_contract(self.profile.name, self.storage_profile)
        self.project_binding = self._resolve_startup_project_binding()
        startup_metadata = self._runtime_metadata()
        logger.info(
            "CCDash backend starting up "
            "(profile=%s, storage_profile=%s, storage_backend=%s, storage_composition=%s, "
            "auth_enabled=%s, integrations_enabled=%s, allowed_storage_profiles=%s, "
            "runtime_sync_behavior=%s, runtime_job_behavior=%s, runtime_auth_behavior=%s, "
            "runtime_integration_behavior=%s, bound_project_id=%s, bound_project_source=%s)",
            startup_metadata["profile"],
            startup_metadata["storageProfile"],
            startup_metadata["storageBackend"],
            startup_metadata["storageComposition"],
            startup_metadata["authEnabled"],
            startup_metadata["integrationsEnabled"],
            ",".join(startup_metadata["allowedStorageProfiles"]),
            startup_metadata["runtimeSyncBehavior"],
            startup_metadata["runtimeJobBehavior"],
            startup_metadata["runtimeAuthBehavior"],
            startup_metadata["runtimeIntegrationBehavior"],
            startup_metadata["boundProjectId"],
            startup_metadata["projectBindingSource"],
        )
        app.state.runtime_profile = self.profile
        app.state.storage_profile = self.storage_profile
        app.state.runtime_container = self
        app.state.runtime_project_binding = self.project_binding

        initialize_observability(app)

        self.db = await connection.get_connection()
        await migrations.run_migrations(self.db)
        self.migration_status = "applied"
        self.ports = self._build_core_ports()
        app.state.core_ports = self.ports
        self.live_event_broker = InMemoryLiveEventBroker(replay_buffer_size=config.CCDASH_LIVE_REPLAY_BUFFER_SIZE)
        self.live_event_publisher = BrokerLiveEventPublisher(self.live_event_broker)
        set_live_event_publisher(self.live_event_publisher)
        app.state.live_event_broker = self.live_event_broker
        app.state.live_event_publisher = self.live_event_publisher

        self.sync = self._build_sync_engine()
        if self.sync is not None:
            app.state.sync_engine = self.sync
        self.telemetry_settings_store = TelemetrySettingsStore()
        self.telemetry_exporter = TelemetryExportCoordinator(
            repository=get_telemetry_queue_repository(self.db),
            settings_store=self.telemetry_settings_store,
            runtime_config=config.TELEMETRY_EXPORTER_CONFIG,
        )
        app.state.telemetry_settings_store = self.telemetry_settings_store
        app.state.telemetry_exporter = self.telemetry_exporter
        self._record_telemetry_export_disabled_state()

        self.job_adapter = RuntimeJobAdapter(
            profile=self.profile,
            ports=self.require_ports(),
            sync_engine=self.sync,
            project_binding=self.project_binding,
            telemetry_exporter_job=(
                TelemetryExporterJob(self.telemetry_exporter)
                if self.profile.name == "worker" and self.telemetry_exporter is not None
                else None
            ),
        )
        self.lifecycle = await self.job_adapter.start()
        app.state.runtime_jobs = self.job_adapter

        if self.lifecycle.sync_task is not None:
            app.state.sync_task = self.lifecycle.sync_task
        if self.lifecycle.analytics_snapshot_task is not None:
            app.state.analytics_snapshot_task = self.lifecycle.analytics_snapshot_task
        if self.lifecycle.telemetry_export_task is not None:
            app.state.telemetry_export_task = self.lifecycle.telemetry_export_task

    async def shutdown(self, app: FastAPI) -> None:
        logger.info("CCDash backend shutting down (profile=%s)", self.profile.name)

        if self.job_adapter is not None:
            await self.job_adapter.stop()
            self.job_adapter = None
        self.lifecycle = None
        if self.live_event_broker is not None:
            await self.live_event_broker.close()
            self.live_event_broker = None
        set_live_event_publisher(None)
        self.live_event_publisher = None

        shutdown_observability(app)
        await connection.close_connection()

    def require_ports(self) -> CorePorts:
        if self.ports is None:
            raise RuntimeError("Runtime ports are unavailable before startup completes.")
        return self.ports

    def _build_core_ports(self) -> CorePorts:
        return build_core_ports(
            self.db,
            runtime_profile=self.profile,
            storage_profile=self.storage_profile,
        )

    def _build_sync_engine(self) -> Any | None:
        if not self._sync_engine_enabled():
            return None
        return sync_engine.SyncEngine(self.db)

    def _sync_engine_enabled(self) -> bool:
        if not self.profile.capabilities.sync:
            return False
        if self.storage_profile.profile == "local":
            return True
        return bool(self.storage_profile.filesystem_source_of_truth)

    async def build_request_context(self, metadata: RequestMetadata) -> RequestContext:
        ports = self.require_ports()
        requested_project_id = str(metadata.headers.get("x-ccdash-project-id") or "").strip() or None
        principal = await ports.identity_provider.get_principal(
            metadata,
            runtime_profile=self.profile.name,
        )
        workspace_scope, project_scope = ports.workspace_registry.resolve_scope(requested_project_id)

        request_id = self._header(metadata, "x-request-id") or self._header(metadata, "x-correlation-id") or str(uuid4())
        correlation_id = self._header(metadata, "x-correlation-id") or request_id

        # --- Enterprise / team scope resolution (DPM-303) ---
        # In local mode these remain None; enterprise mode resolves from
        # storage profile and request headers.
        enterprise_scope: EnterpriseScope | None = None
        team_scope: TeamScope | None = None

        storage_enterprise_id: str | None = (
            self.storage_profile.schema_name
            if self.storage_profile.profile == "enterprise"
            else None
        )
        storage_tenant_id: str | None = (
            self.storage_profile.schema_name
            if self.storage_profile.isolation_mode == "tenant"
            else None
        )

        # Enterprise scope: present whenever the storage profile is enterprise.
        header_enterprise_id = self._header(metadata, "x-ccdash-enterprise-id")
        resolved_enterprise_id = header_enterprise_id or storage_enterprise_id
        if resolved_enterprise_id is not None:
            enterprise_scope = EnterpriseScope(
                enterprise_id=resolved_enterprise_id,
                display_name=self._header(metadata, "x-ccdash-enterprise-name") or "",
            )

        # Team scope: only when an explicit team header is provided within an
        # enterprise boundary. Follow-on auth work will resolve this from
        # token claims or membership lookups.
        header_team_id = self._header(metadata, "x-ccdash-team-id")
        if header_team_id is not None and resolved_enterprise_id is not None:
            team_scope = TeamScope(
                team_id=header_team_id,
                enterprise_id=resolved_enterprise_id,
                display_name=self._header(metadata, "x-ccdash-team-name") or "",
            )

        # --- Scope bindings chain: enterprise → team → workspace → project ---
        scope_bindings: list[ScopeBinding] = []
        if enterprise_scope is not None:
            scope_bindings.append(
                ScopeBinding(
                    scope_type="enterprise",
                    scope_id=enterprise_scope.enterprise_id,
                )
            )
        if team_scope is not None:
            scope_bindings.append(
                ScopeBinding(
                    scope_type="team",
                    scope_id=team_scope.team_id,
                    parent_scope_type="enterprise",
                    parent_scope_id=enterprise_scope.enterprise_id if enterprise_scope else None,
                )
            )
        if workspace_scope is not None:
            parent_type: str | None = None
            parent_id: str | None = None
            if team_scope is not None:
                parent_type = "team"
                parent_id = team_scope.team_id
            elif enterprise_scope is not None:
                parent_type = "enterprise"
                parent_id = enterprise_scope.enterprise_id
            scope_bindings.append(
                ScopeBinding(
                    scope_type="workspace",
                    scope_id=workspace_scope.workspace_id,
                    parent_scope_type=parent_type,
                    parent_scope_id=parent_id,
                )
            )
        if project_scope is not None:
            scope_bindings.append(
                ScopeBinding(
                    scope_type="project",
                    scope_id=project_scope.project_id,
                    parent_scope_type="workspace" if workspace_scope is not None else None,
                    parent_scope_id=workspace_scope.workspace_id if workspace_scope is not None else None,
                )
            )

        # --- Tenancy context rollup (DPM-303) ---
        # Bundles stable scope keys for follow-on auth/RBAC consumption.
        tenancy = TenancyContext(
            enterprise_id=resolved_enterprise_id,
            team_id=team_scope.team_id if team_scope else None,
            workspace_id=workspace_scope.workspace_id if workspace_scope else None,
            project_id=project_scope.project_id if project_scope else None,
            ownership_posture_default=(
                "directly-ownable" if resolved_enterprise_id is not None else "scope-owned"
            ),
        )

        return RequestContext(
            principal=principal,
            workspace=workspace_scope,
            project=project_scope,
            runtime_profile=self.profile.name,
            trace=TraceContext(
                request_id=request_id,
                correlation_id=correlation_id,
                traceparent=self._header(metadata, "traceparent"),
                client_host=metadata.client_host,
                user_agent=self._header(metadata, "user-agent"),
                path=metadata.path,
                method=metadata.method,
            ),
            storage_scope=StorageScope(
                enterprise_id=storage_enterprise_id,
                tenant_id=storage_tenant_id,
                isolation_mode=self.storage_profile.isolation_mode,
            ),
            scope_bindings=tuple(scope_bindings),
            enterprise=enterprise_scope,
            team=team_scope,
            tenancy=tenancy,
        )

    def runtime_status(self) -> dict[str, Any]:
        validate_runtime_storage_pairing(self.profile, self.storage_profile)
        validate_migration_governance_contract()
        status = self._runtime_metadata()
        activity_status = default_runtime_activity_snapshot(self.profile)
        if self.job_adapter is not None:
            activity_status.update(self.job_adapter.status_snapshot())
        storage_probe = self.ports or build_core_ports(
            object(),
            runtime_profile=self.profile,
            storage_profile=self.storage_profile,
        )
        audit_capability = (
            storage_probe.storage.audit_security().privileged_action_audit_records().describe_capability()
        )
        embedding_capability = (
            storage_probe.storage.observed_product().session_embeddings().describe_capability()
        )
        status.update(
            {
                "auditWriteSupported": audit_capability.supported,
                "auditWriteAuthoritative": audit_capability.authoritative,
                "auditWriteStatus": "authoritative" if audit_capability.authoritative else "unsupported",
                "auditWriteNotes": audit_capability.notes,
                "sessionEmbeddingWriteSupported": embedding_capability.supported,
                "sessionEmbeddingWriteAuthoritative": embedding_capability.authoritative,
                "sessionEmbeddingWriteStatus": (
                    "authoritative" if embedding_capability.authoritative else "unsupported"
                ),
                "sessionEmbeddingWriteNotes": embedding_capability.notes,
                "storageProfileValidationMatrix": build_storage_profile_validation_matrix(),
                "migrationGovernanceStatus": "verified",
                "migrationStatus": self.migration_status,
                "syncProvisioned": self.sync is not None,
            }
        )
        status.update(activity_status)
        probe_contract = self._build_probe_contract(status)
        status.update(
            {
                "probeContract": probe_contract,
                "probeSchemaVersion": str(probe_contract["schemaVersion"]),
                "probeLiveState": str(probe_contract["live"]["state"]),
                "probeReadyState": str(probe_contract["ready"]["state"]),
                "probeReadyStatus": str(probe_contract["ready"]["status"]),
                "probeDetailStatus": str(probe_contract["detail"]["status"]),
                "probeReady": bool(probe_contract["ready"]["ready"]),
                "probeDegraded": bool(probe_contract["ready"]["degraded"]),
                "degradedReasons": list(probe_contract["ready"]["reasons"]),
                "degradedReasonCodes": [
                    str(reason["code"]) for reason in probe_contract["ready"]["reasons"]
                ],
            }
        )
        return status

    def _build_probe_contract(self, status: dict[str, Any]) -> dict[str, Any]:
        runtime_contract = get_runtime_storage_contract(self.profile)
        db_connected = bool(connection._connection)
        migration_status = str(status.get("migrationStatus", "unknown"))
        auth_configured = bool(config.resolve_api_bearer_token())
        worker_binding_config = config.resolve_worker_binding_config()
        watcher_state = str(status.get("watcher", "unknown"))
        startup_sync_state = str(status.get("startupSync", "idle"))
        required_checks = set(runtime_contract.readiness_checks)

        checks = [
            self._probe_check(
                code="db_connection",
                category="database",
                status="pass" if db_connected else "fail",
                required="db_connection" in required_checks,
                summary="Database connection is established."
                if db_connected
                else "Database connection is not established.",
                detail=(
                    "The runtime container has an active database connection."
                    if db_connected
                    else "Readiness requires a live database connection before traffic or jobs can rely on state."
                ),
                data={"db": "connected" if db_connected else "disconnected"},
            ),
            self._probe_check(
                code="storage_pairing",
                category="storage",
                status="pass",
                required="storage_pairing" in required_checks,
                summary="Runtime and storage profiles are compatible.",
                detail=(
                    f"runtime_profile={self.profile.name} storage_profile={self.storage_profile.profile} "
                    f"storage_mode={status.get('storageMode', '')} composition={status.get('storageComposition', '')}"
                ),
                data={
                    "runtimeProfile": self.profile.name,
                    "storageProfile": self.storage_profile.profile,
                    "storageMode": status.get("storageMode"),
                    "storageComposition": status.get("storageComposition"),
                },
            ),
            self._probe_check(
                code="migration_governance",
                category="migration",
                status="pass",
                required="migration_governance" in required_checks,
                summary="Migration governance matrix is verified.",
                detail=(
                    f"Supported compositions: {', '.join(status.get('supportedStorageCompositions', ()))}. "
                    f"Tracked backend differences: {', '.join(status.get('supportedBackendDifferenceCategories', ()))}."
                ),
                data={
                    "migrationGovernanceStatus": status.get("migrationGovernanceStatus"),
                    "supportedStorageCompositions": list(status.get("supportedStorageCompositions", ())),
                    "supportedBackendDifferenceCategories": list(
                        status.get("supportedBackendDifferenceCategories", ())
                    ),
                },
            ),
            self._probe_check(
                code="schema_migrations",
                category="migration",
                status="pass" if migration_status == "applied" else "fail",
                required="schema_migrations" in required_checks,
                summary="Schema migrations are applied."
                if migration_status == "applied"
                else "Schema migrations are not applied.",
                detail=(
                    f"migration_status={migration_status}"
                    if migration_status == "applied"
                    else "Runtime startup must complete migrations before the runtime should be treated as ready."
                ),
                data={"migrationStatus": migration_status},
            ),
            self._probe_check(
                code="auth_contract",
                category="auth",
                status=(
                    "not_applicable"
                    if not self.profile.capabilities.auth
                    else "pass" if auth_configured else "fail"
                ),
                required="auth_contract" in required_checks,
                summary=(
                    "Request authentication is not required for this runtime."
                    if not self.profile.capabilities.auth
                    else "Hosted auth contract is configured."
                    if auth_configured
                    else "Hosted auth contract is missing its bearer token."
                ),
                detail=(
                    "This runtime does not serve authenticated HTTP traffic."
                    if not self.profile.capabilities.auth
                    else f"{config.CCDASH_API_BEARER_TOKEN_ENV} must be set before the API runtime is ready."
                ),
                data={
                    "authEnabled": self.profile.capabilities.auth,
                    "configured": auth_configured,
                },
            ),
            self._probe_check(
                code="worker_binding",
                category="worker",
                status=(
                    "not_applicable"
                    if self.profile.name != "worker"
                    else "pass" if self.project_binding is not None else "fail"
                ),
                required="worker_binding" in required_checks,
                summary=(
                    "Worker project binding is not required for this runtime."
                    if self.profile.name != "worker"
                    else "Worker project binding is resolved."
                    if self.project_binding is not None
                    else "Worker project binding is unresolved."
                ),
                detail=(
                    "Only the worker runtime requires an explicit project binding."
                    if self.profile.name != "worker"
                    else (
                        f"configured={worker_binding_config.configured} "
                        f"requested_project_id={worker_binding_config.project_id or 'n/a'}"
                    )
                ),
                data={
                    "bindingRequired": self.profile.name == "worker",
                    "configured": worker_binding_config.configured,
                    "requestedProjectId": worker_binding_config.project_id or None,
                    "resolvedProjectId": (
                        self.project_binding.project.id if self.project_binding is not None else None
                    ),
                },
            ),
            self._probe_check(
                code="watcher_runtime",
                category="runtime",
                status=(
                    "not_applicable"
                    if not self.profile.capabilities.watch
                    else "pass" if watcher_state == "running" else "warn"
                ),
                required="watcher_runtime" in required_checks,
                summary=(
                    "Watcher is not expected for this runtime."
                    if not self.profile.capabilities.watch
                    else "Watcher is active."
                    if watcher_state == "running"
                    else "Watcher-capable runtime is serving without an active watcher."
                ),
                detail=(
                    "Watcher activity is a local-only degradation signal."
                    if self.profile.capabilities.watch
                    else "This runtime intentionally avoids watcher ownership."
                ),
                data={"watchEnabled": self.profile.capabilities.watch, "watcher": watcher_state},
            ),
            self._probe_check(
                code="startup_sync",
                category="runtime",
                status=(
                    "not_applicable"
                    if not self.profile.capabilities.sync
                    else "warn" if startup_sync_state == "running" else "pass"
                ),
                required="startup_sync" in required_checks,
                summary=(
                    "Startup sync is not expected for this runtime."
                    if not self.profile.capabilities.sync
                    else "Startup sync is still catching up."
                    if startup_sync_state == "running"
                    else "Startup sync is idle."
                ),
                detail=(
                    "A running startup sync indicates the runtime is live but still reconciling background state."
                    if self.profile.capabilities.sync
                    else "This runtime does not own startup sync work."
                ),
                data={
                    "syncEnabled": self.profile.capabilities.sync,
                    "startupSync": startup_sync_state,
                    "syncProvisioned": bool(status.get("syncProvisioned", False)),
                },
            ),
        ]

        failed_checks = [check for check in checks if check["status"] == "fail" and check["required"]]
        warning_checks = [check for check in checks if check["status"] == "warn"]
        reasons = [self._probe_reason(check) for check in checks if check["status"] in {"fail", "warn"}]

        if failed_checks:
            ready_state = "not_ready"
            ready_status = "fail"
            ready = False
            degraded = False
            ready_summary = f"Runtime profile '{self.profile.name}' is live but not ready."
        elif warning_checks:
            ready_state = "degraded"
            ready_status = "warn"
            ready = True
            degraded = True
            ready_summary = f"Runtime profile '{self.profile.name}' is ready with degraded signals."
        else:
            ready_state = "ready"
            ready_status = "pass"
            ready = True
            degraded = False
            ready_summary = f"Runtime profile '{self.profile.name}' is ready."

        return {
            "schemaVersion": "ops-201-v1",
            "runtimeProfile": self.profile.name,
            "live": {
                "state": "live",
                "status": "pass",
                "summary": f"Runtime profile '{self.profile.name}' is responding.",
            },
            "ready": {
                "state": ready_state,
                "status": ready_status,
                "ready": ready,
                "degraded": degraded,
                "summary": ready_summary,
                "reasons": reasons,
                "checks": checks,
            },
            "detail": {
                "state": ready_state,
                "status": ready_status,
                "summary": ready_summary,
                "recommendedCadence": dict(status.get("probeCadence", {})),
                "requiredReadinessChecks": list(status.get("requiredReadinessChecks", ())),
                "runtime": {
                    "profile": status.get("profile"),
                    "description": status.get("runtimeDescription"),
                    "capabilities": dict(status.get("runtimeCapabilities", {})),
                    "allowedStorageProfiles": list(status.get("allowedStorageProfiles", ())),
                    "recommendedStorageProfile": status.get("recommendedStorageProfile"),
                    "syncBehavior": status.get("runtimeSyncBehavior"),
                    "jobBehavior": status.get("runtimeJobBehavior"),
                    "authBehavior": status.get("runtimeAuthBehavior"),
                    "integrationBehavior": status.get("runtimeIntegrationBehavior"),
                },
                "storage": {
                    "mode": status.get("storageMode"),
                    "profile": status.get("storageProfile"),
                    "backend": status.get("storageBackend"),
                    "composition": status.get("storageComposition"),
                    "canonicalStore": status.get("storageCanonicalStore"),
                    "filesystemRole": status.get("storageFilesystemRole"),
                    "filesystemSourceOfTruth": bool(status.get("filesystemSourceOfTruth", False)),
                    "sharedPostgresEnabled": bool(status.get("sharedPostgresEnabled", False)),
                    "isolationMode": status.get("storageIsolationMode"),
                    "supportedIsolationModes": list(status.get("supportedStorageIsolationModes", ())),
                    "requiredGuarantees": list(status.get("requiredStorageGuarantees", ())),
                },
                "database": {
                    "status": "connected" if db_connected else "disconnected",
                    "migrationStatus": migration_status,
                    "migrationGovernanceStatus": status.get("migrationGovernanceStatus"),
                },
                "environment": {
                    "deploymentMode": status.get("deploymentMode"),
                    "valid": bool(status.get("environmentContractValid", False)),
                    "requiredVariables": list(status.get("environmentContractRequired", ())),
                    "secretVariables": list(status.get("environmentContractSecrets", ())),
                    "errors": list(status.get("environmentContractErrors", ())),
                    "warnings": list(status.get("environmentContractWarnings", ())),
                    "contract": dict(status.get("environmentContract", {})),
                },
                "binding": {
                    "projectId": self.project_binding.project.id if self.project_binding is not None else None,
                    "projectName": self.project_binding.project.name if self.project_binding is not None else None,
                    "projectBindingSource": status.get("projectBindingSource"),
                    "projectBindingRequestedId": status.get("projectBindingRequestedId"),
                    "projectBindingLocked": bool(status.get("projectBindingLocked", False)),
                },
                "activities": {
                    "watcher": watcher_state,
                    "startupSync": startup_sync_state,
                    "analyticsSnapshots": str(status.get("analyticsSnapshots", "idle")),
                    "telemetryExports": str(status.get("telemetryExports", "idle")),
                    "cacheWarming": str(status.get("cacheWarming", "idle")),
                    "jobsEnabled": bool(status.get("jobsEnabled", False)),
                    "syncProvisioned": bool(status.get("syncProvisioned", False)),
                },
                "checks": checks,
            },
        }

    def _probe_check(
        self,
        *,
        code: str,
        category: str,
        status: str,
        required: bool,
        summary: str,
        detail: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "category": category,
            "status": status,
            "required": required,
            "summary": summary,
            "detail": detail,
            "data": data or {},
        }

    def _probe_reason(self, check: dict[str, Any]) -> dict[str, str]:
        return {
            "code": str(check["code"]),
            "category": str(check["category"]),
            "severity": str(check["status"]),
            "summary": str(check["summary"]),
        }

    def _header(self, metadata: RequestMetadata, key: str) -> str | None:
        value = metadata.headers.get(key.lower())
        if value is None:
            return None
        clean = str(value).strip()
        return clean or None

    def _record_telemetry_export_disabled_state(self) -> None:
        if self.profile.name != "worker" or self.telemetry_settings_store is None:
            return
        settings = self.telemetry_settings_store.load()
        disabled = not bool(
            config.TELEMETRY_EXPORTER_CONFIG.enabled
            and config.TELEMETRY_EXPORTER_CONFIG.configured
            and settings.enabled
        )
        observability.set_telemetry_export_disabled(disabled)

    def _runtime_metadata(self) -> dict[str, Any]:
        metadata = build_runtime_metadata(self.profile, self.storage_profile)
        storage_contract = get_storage_capability_contract(self.storage_profile)
        environment_contract = config.resolve_runtime_environment_contract(
            self.profile.name,
            self.storage_profile,
        )
        metadata.update(
            {
                "deploymentMode": environment_contract.deployment_mode,
                "environmentContract": environment_contract.as_runtime_metadata(),
                "environmentContractValid": environment_contract.valid,
                "environmentContractErrors": environment_contract.errors,
                "environmentContractWarnings": environment_contract.warnings,
                "environmentContractRequired": environment_contract.required_variables,
                "environmentContractSecrets": environment_contract.secret_variables,
                "auditStore": storage_contract.audit_store,
                "sessionIntelligenceProfile": storage_contract.session_intelligence_profile,
                "sessionIntelligenceAnalyticsLevel": storage_contract.session_intelligence_analytics_level,
                "sessionIntelligenceBackfillStrategy": storage_contract.session_intelligence_backfill_strategy,
                "sessionIntelligenceMemoryDraftFlow": storage_contract.session_intelligence_memory_draft_flow,
                "sessionIntelligenceIsolationBoundary": storage_contract.session_intelligence_isolation_boundary,
                "boundProjectId": self.project_binding.project.id if self.project_binding is not None else None,
                "boundProjectName": self.project_binding.project.name if self.project_binding is not None else None,
                "boundProjectRoot": (
                    str(self.project_binding.paths.root.path)
                    if self.project_binding is not None
                    else None
                ),
                "projectBindingSource": self.project_binding.source if self.project_binding is not None else None,
                "projectBindingRequestedId": (
                    self.project_binding.requested_project_id
                    if self.project_binding is not None
                    else None
                ),
                "projectBindingLocked": self.project_binding.locked if self.project_binding is not None else False,
            }
        )
        return metadata

    def _resolve_startup_project_binding(self) -> ProjectBinding | None:
        if self.profile.name != "worker":
            return None

        binding_config = config.resolve_worker_binding_config()
        if not binding_config.configured:
            raise RuntimeError(
                f"Runtime profile 'worker' requires a non-empty "
                f"{config.CCDASH_WORKER_PROJECT_ID_ENV} before starting background jobs."
            )

        workspace_registry = build_workspace_registry(
            runtime_profile=self.profile,
            storage_profile=self.storage_profile,
        )
        binding = workspace_registry.resolve_project_binding(
            binding_config.project_id,
            allow_active_fallback=False,
        )
        if binding is None:
            raise RuntimeError(
                f"Runtime profile 'worker' could not resolve project "
                f"'{binding_config.project_id}' from the workspace registry."
            )

        logger.info(
            "Resolved worker project binding (project_id=%s, source=%s, project_root=%s)",
            binding.project.id,
            binding.source,
            binding.paths.root.path,
        )
        return binding
