"""Runtime container and lifecycle orchestration."""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI

from backend.adapters.live_updates import InMemoryLiveEventBroker
from backend.adapters.jobs import RuntimeJobAdapter, RuntimeJobState, TelemetryExporterJob
from backend.application.context import RequestContext, RequestMetadata, TraceContext
from backend.application.live_updates import BrokerLiveEventPublisher, LiveEventBroker, LiveEventPublisher
from backend.application.live_updates.runtime_state import set_live_event_publisher
from backend.application.ports import CorePorts
from backend import config
from backend.db import connection, migrations, sync_engine
from backend.db.factory import get_telemetry_queue_repository
from backend.observability import initialize as initialize_observability, shutdown as shutdown_observability
from backend.observability import otel as observability
from backend.runtime.profiles import RuntimeProfile
from backend.runtime.storage_contract import (
    get_runtime_storage_contract,
    get_storage_capability_contract,
    validate_runtime_storage_pairing,
)
from backend.runtime_ports import build_core_ports
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

    async def startup(self, app: FastAPI) -> None:
        validate_runtime_storage_pairing(self.profile, self.storage_profile)
        logger.info(
            "CCDash backend starting up (profile=%s, storage_profile=%s)",
            self.profile.name,
            self.storage_profile.profile,
        )
        app.state.runtime_profile = self.profile
        app.state.storage_profile = self.storage_profile
        app.state.runtime_container = self

        initialize_observability(app)

        self.db = await connection.get_connection()
        await migrations.run_migrations(self.db)
        self.ports = self._build_core_ports()
        app.state.core_ports = self.ports
        self.live_event_broker = InMemoryLiveEventBroker(replay_buffer_size=config.CCDASH_LIVE_REPLAY_BUFFER_SIZE)
        self.live_event_publisher = BrokerLiveEventPublisher(self.live_event_broker)
        set_live_event_publisher(self.live_event_publisher)
        app.state.live_event_broker = self.live_event_broker
        app.state.live_event_publisher = self.live_event_publisher

        self.sync = sync_engine.SyncEngine(self.db)
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
        )

    def runtime_status(self) -> dict[str, Any]:
        validate_runtime_storage_pairing(self.profile, self.storage_profile)
        runtime_contract = get_runtime_storage_contract(self.profile)
        storage_contract = get_storage_capability_contract(self.storage_profile)
        status = {
            "profile": self.profile.name,
            "watchEnabled": self.profile.capabilities.watch,
            "syncEnabled": self.profile.capabilities.sync,
            "jobsEnabled": self.profile.capabilities.jobs,
            "authEnabled": self.profile.capabilities.auth,
            "integrationsEnabled": self.profile.capabilities.integrations,
            "recommendedStorageProfile": self.profile.recommended_storage_profile,
            "allowedStorageProfiles": runtime_contract.allowed_storage_profiles,
            "supportedStorageProfiles": runtime_contract.allowed_storage_profiles,
            "runtimeSyncBehavior": runtime_contract.sync_behavior,
            "runtimeJobBehavior": runtime_contract.job_behavior,
            "runtimeAuthBehavior": runtime_contract.auth_behavior,
            "runtimeIntegrationBehavior": runtime_contract.integration_behavior,
            "storageMode": storage_contract.mode,
            "storageProfile": self.storage_profile.profile,
            "storageBackend": self.storage_profile.db_backend,
            "storageCanonicalStore": storage_contract.canonical_store,
            "filesystemSourceOfTruth": self.storage_profile.filesystem_source_of_truth,
            "storageFilesystemRole": storage_contract.filesystem_role,
            "sharedPostgresEnabled": self.storage_profile.shared_postgres_enabled,
            "storageIsolationMode": self.storage_profile.isolation_mode,
            "supportedStorageIsolationModes": storage_contract.supported_isolation_modes,
            "storageSchema": self.storage_profile.schema_name,
            "canonicalSessionStore": self.storage_profile.canonical_session_store,
            "requiredStorageGuarantees": storage_contract.required_guarantees,
        }
        if self.job_adapter is not None:
            status.update(self.job_adapter.status_snapshot())
        return status

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
