"""Runtime container and lifecycle orchestration."""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI

from backend.adapters.live_updates import InMemoryLiveEventBroker
from backend.adapters.jobs import RuntimeJobAdapter, RuntimeJobState
from backend.application.context import RequestContext, RequestMetadata, TraceContext
from backend.application.live_updates import BrokerLiveEventPublisher, LiveEventBroker, LiveEventPublisher
from backend.application.live_updates.runtime_state import set_live_event_publisher
from backend.application.ports import CorePorts
from backend import config
from backend.db import connection, migrations, sync_engine
from backend.observability import initialize as initialize_observability, shutdown as shutdown_observability
from backend.runtime.profiles import RuntimeProfile
from backend.runtime_ports import build_core_ports

logger = logging.getLogger("ccdash.runtime")


class RuntimeContainer:
    def __init__(self, *, profile: RuntimeProfile) -> None:
        self.profile = profile
        self.db: Any | None = None
        self.sync: Any | None = None
        self.ports: CorePorts | None = None
        self.lifecycle: RuntimeJobState | None = None
        self.job_adapter: RuntimeJobAdapter | None = None
        self.live_event_broker: LiveEventBroker | None = None
        self.live_event_publisher: LiveEventPublisher | None = None

    async def startup(self, app: FastAPI) -> None:
        logger.info("CCDash backend starting up (profile=%s)", self.profile.name)
        app.state.runtime_profile = self.profile
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

        self.job_adapter = RuntimeJobAdapter(
            profile=self.profile,
            ports=self.require_ports(),
            sync_engine=self.sync,
        )
        self.lifecycle = await self.job_adapter.start()
        app.state.runtime_jobs = self.job_adapter

        if self.lifecycle.sync_task is not None:
            app.state.sync_task = self.lifecycle.sync_task
        if self.lifecycle.analytics_snapshot_task is not None:
            app.state.analytics_snapshot_task = self.lifecycle.analytics_snapshot_task

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
        return build_core_ports(self.db)

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
        status = {
            "profile": self.profile.name,
            "watchEnabled": self.profile.capabilities.watch,
            "syncEnabled": self.profile.capabilities.sync,
            "jobsEnabled": self.profile.capabilities.jobs,
            "authEnabled": self.profile.capabilities.auth,
            "integrationsEnabled": self.profile.capabilities.integrations,
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
