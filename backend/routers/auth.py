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
    return service.session_payload(request)


@auth_router.get("/login")
async def auth_login(
    redirect: bool = Query(default=True),
    redirect_to: str = Query(default="/", alias="redirectTo"),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    return await _start_login(redirect=redirect, redirect_to=redirect_to, service=service)


@auth_router.get("/login/start")
async def auth_login_start(
    redirect: bool = Query(default=True),
    redirect_to: str = Query(default="/", alias="redirectTo"),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    return await _start_login(redirect=redirect, redirect_to=redirect_to, service=service)


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
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

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
    redirect: bool,
    redirect_to: str,
    service: AuthenticationService,
) -> Response:
    try:
        login = await service.start_login(redirect_to=redirect_to)
    except RequestAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

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
