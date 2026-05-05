"""Browser auth session endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from backend.adapters.auth.bearer import RequestAuthenticationError
from backend.adapters.auth.session_state import (
    clear_session_cookie,
    clear_state_cookie,
    set_session_cookie,
    set_state_cookie,
)
from backend.application.services.authentication import AuthenticationService
from backend import config
from backend.observability import otel


auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_authentication_service(request: Request) -> AuthenticationService:
    service = getattr(request.app.state, "auth_service", None)
    if isinstance(service, AuthenticationService):
        return service

    runtime_profile = getattr(request.app.state, "runtime_profile", None)
    profile_name = str(getattr(runtime_profile, "name", runtime_profile or "api"))
    return AuthenticationService(
        config.resolve_auth_provider_config(profile_name),  # type: ignore[arg-type]
        runtime_profile=profile_name,
    )


@auth_router.get("/metadata")
def auth_metadata(service: AuthenticationService = Depends(get_authentication_service)) -> dict:
    return service.provider_metadata()


@auth_router.get("/session")
def auth_session(
    request: Request,
    service: AuthenticationService = Depends(get_authentication_service),
) -> dict:
    try:
        return service.session_payload(request)
    except RequestAuthenticationError as exc:
        _record_auth_error(
            "session",
            request=request,
            service=service,
            exc=exc,
            metric="session",
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@auth_router.get("/login")
async def auth_login(
    request: Request,
    redirect: bool = Query(default=True),
    redirect_to: str = Query(default="/", alias="redirectTo"),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    return await _start_login(request=request, redirect=redirect, redirect_to=redirect_to, service=service)


@auth_router.get("/login/start")
async def auth_login_start(
    request: Request,
    redirect: bool = Query(default=True),
    redirect_to: str = Query(default="/", alias="redirectTo"),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    return await _start_login(request=request, redirect=redirect, redirect_to=redirect_to, service=service)


@auth_router.get("/callback")
async def auth_callback(
    request: Request,
    state: str | None = Query(default=None),
    id_token: str | None = Query(default=None),
    code: str | None = Query(default=None),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    try:
        callback = await service.handle_callback(request, state=state, id_token=id_token, code=code)
    except RequestAuthenticationError as exc:
        _record_auth_error(
            "callback",
            request=request,
            service=service,
            exc=exc,
            metric="login",
        )
        _record_issuer_health(service, status="error")
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    otel.record_auth_issuer_health(
        provider=callback.principal.auth_provider_id or service.config.provider,
        issuer=callback.principal.issuer or service.config.oidc_issuer,
        status="ok",
        runtime_profile=service.runtime_profile,
    )
    response = RedirectResponse(callback.redirect_to, status_code=303)
    set_session_cookie(
        response,
        service.config,
        callback.session_cookie,
        max_age_seconds=callback.session_cookie_max_age_seconds,
    )
    clear_state_cookie(response, service.config)
    return response


@auth_router.post("/logout")
def auth_logout(service: AuthenticationService = Depends(get_authentication_service)) -> JSONResponse:
    response = JSONResponse({"ok": True})
    clear_session_cookie(response, service.config)
    clear_state_cookie(response, service.config)
    return response


async def _start_login(
    *,
    request: Request,
    redirect: bool,
    redirect_to: str,
    service: AuthenticationService,
) -> Response:
    try:
        login = await service.start_login(redirect_to=redirect_to)
    except RequestAuthenticationError as exc:
        _record_auth_error(
            "login",
            request=request,
            service=service,
            exc=exc,
            metric="login",
        )
        _record_issuer_health(service, status="error")
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    _record_issuer_health(service, status="ok")
    if redirect:
        response: Response = RedirectResponse(login.authorization_url, status_code=303)
    else:
        response = JSONResponse({"authorizationUrl": login.authorization_url})
    set_state_cookie(
        response,
        service.config,
        login.state_cookie,
        max_age_seconds=login.state_cookie_max_age_seconds,
    )
    return response


def _record_auth_error(
    phase: str,
    *,
    request: Request,
    service: AuthenticationService,
    exc: RequestAuthenticationError,
    metric: str,
) -> None:
    provider = service.config.provider or "unknown"
    status_code = str(exc.status_code)
    reason = _reason_label(exc.detail)
    if metric == "session":
        otel.record_auth_session_error(
            provider=provider,
            status=status_code,
            reason=reason,
            runtime_profile=service.runtime_profile,
        )
    else:
        otel.record_auth_login_failure(
            provider=provider,
            phase=phase,
            status=status_code,
            reason=reason,
            runtime_profile=service.runtime_profile,
        )
    otel.log_auth_event(
        f"auth.{phase}.failure",
        provider=provider,
        status=status_code,
        reason=reason,
        path=request.url.path,
        client=request.client.host if request.client else "",
        runtime_profile=service.runtime_profile,
    )


def _record_issuer_health(service: AuthenticationService, *, status: str) -> None:
    issuer = service.config.oidc_issuer if service.config.provider == "oidc" else ""
    if not issuer:
        return
    otel.record_auth_issuer_health(
        provider=service.config.provider,
        issuer=issuer,
        status=status,
        runtime_profile=service.runtime_profile,
    )


def _reason_label(detail: object) -> str:
    text = str(detail or "").strip().lower()
    if not text:
        return "unknown"
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text)
    return "_".join(part for part in normalized.split("_") if part)[:80] or "unknown"
