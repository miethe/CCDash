"""Structured audit attribution helpers for auth decisions."""
from __future__ import annotations

import inspect
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.application.context import Principal, RequestContext
from backend.application.ports import AuthorizationDecision, StorageUnitOfWork
from backend.observability import otel


logger = logging.getLogger("ccdash.auth.audit")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    occurred_at: str
    subject: str
    stable_subject: str
    provider: str
    issuer: str
    action: str
    resource: str
    decision: str
    status: str
    reason: str
    client: str
    path: str
    method: str
    runtime_profile: str
    request_id: str
    enterprise_id: str
    team_id: str
    workspace_id: str
    project_id: str

    def to_log_extra(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event"] = "auth.audit"
        return payload

    def to_access_decision_record(self) -> dict[str, Any]:
        resource_type, resource_id = split_resource(self.resource)
        scope_id = (
            self.project_id
            or self.workspace_id
            or self.team_id
            or self.enterprise_id
            or "unknown"
        )
        return {
            "id": self.event_id,
            "principal_id": self.stable_subject or self.subject or "unknown",
            "scope_id": scope_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "requested_action": self.action,
            "decision": self.decision,
            "evaluator": "request_scope.require_http_authorization",
            "metadata_json": {
                "subject": self.subject,
                "stable_subject": self.stable_subject,
                "provider": self.provider,
                "issuer": self.issuer,
                "status": self.status,
                "reason": self.reason,
                "client": self.client,
                "path": self.path,
                "method": self.method,
                "runtime_profile": self.runtime_profile,
                "request_id": self.request_id,
                "enterprise_id": self.enterprise_id,
                "team_id": self.team_id,
                "workspace_id": self.workspace_id,
                "project_id": self.project_id,
            },
            "occurred_at": self.occurred_at,
        }


def authorization_audit_event(
    context: RequestContext,
    decision: AuthorizationDecision,
    *,
    action: str,
    resource: str | None = None,
) -> AuditEvent:
    principal = context.principal
    return AuditEvent(
        event_id=str(uuid4()),
        occurred_at=datetime.now(timezone.utc).isoformat(),
        subject=_principal_subject(principal),
        stable_subject=_safe_text(principal.stable_subject),
        provider=_safe_text(principal.auth_provider_id or principal.auth_mode),
        issuer=_safe_text(principal.issuer),
        action=_safe_text(action),
        resource=_safe_text(resource),
        decision="allow" if decision.allowed else "deny",
        status=_safe_text(decision.code) or ("allowed" if decision.allowed else "denied"),
        reason=_safe_text(decision.reason),
        client=_safe_text(context.trace.client_host),
        path=_safe_text(context.trace.path),
        method=_safe_text(context.trace.method),
        runtime_profile=_safe_text(context.runtime_profile),
        request_id=_safe_text(context.trace.request_id),
        enterprise_id=_safe_text(context.tenancy.enterprise_id or context.effective_enterprise_id),
        team_id=_safe_text(context.tenancy.team_id),
        workspace_id=_safe_text(
            context.tenancy.workspace_id
            or (context.workspace.workspace_id if context.workspace is not None else None)
        ),
        project_id=_safe_text(
            context.tenancy.project_id
            or (context.project.project_id if context.project is not None else None)
        ),
    )


async def record_authorization_decision(
    context: RequestContext,
    storage: StorageUnitOfWork | Any,
    decision: AuthorizationDecision,
    *,
    action: str,
    resource: str | None = None,
) -> AuditEvent:
    event = authorization_audit_event(context, decision, action=action, resource=resource)
    otel.record_auth_authorization_decision(
        action=event.action,
        resource=event.resource,
        decision=event.decision,
        status=event.status,
        provider=event.provider,
        runtime_profile=event.runtime_profile,
    )
    _log_audit_event(event)
    await _maybe_record_access_decision(storage, event)
    return event


def split_resource(resource: str) -> tuple[str, str]:
    text = _safe_text(resource)
    if not text:
        return "none", ""
    for separator in (":", "/"):
        head, sep, tail = text.partition(separator)
        if sep:
            return (_safe_text(head) or "unknown", _safe_text(tail))
    return text, ""


def _log_audit_event(event: AuditEvent) -> None:
    level = logging.INFO if event.decision == "allow" else logging.WARNING
    logger.log(level, "authorization decision audited", extra=event.to_log_extra())


async def _maybe_record_access_decision(storage: StorageUnitOfWork | Any, event: AuditEvent) -> None:
    try:
        audit_security = getattr(storage, "audit_security", None)
        if not callable(audit_security):
            return
        repo = audit_security().access_decision_logs()
        descriptor = getattr(repo, "describe_capability", lambda: None)()
        if not bool(getattr(descriptor, "authoritative", False)):
            return
        writer = getattr(repo, "record_access_decision", None)
        if not callable(writer):
            return
        result = writer(event.to_access_decision_record())
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.debug("access decision audit storage skipped", exc_info=True)


def _principal_subject(principal: Principal) -> str:
    return _safe_text(principal.subject)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()
