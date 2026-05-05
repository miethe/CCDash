"""Router for shared live-update streaming."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend import config
from backend.adapters.live_updates.sse_stream import iter_live_sse_stream
from backend.application.context import RequestContext
from backend.application.live_updates import LiveEventBroker, LiveReplayRequest
from backend.application.live_updates.topics import normalize_topics, parse_cursor_map
from backend.application.ports import CorePorts
from backend.request_scope import get_core_ports, get_request_context, require_http_authorization


live_router = APIRouter(prefix="/api/live", tags=["live"])


def get_live_event_broker(request: Request) -> LiveEventBroker:
    broker = getattr(request.app.state, "live_event_broker", None)
    if broker is None:
        raise HTTPException(status_code=500, detail="Live event broker is unavailable")
    return broker


async def _authorize_topics(
    *,
    request_context: RequestContext,
    core_ports: CorePorts,
    topics: tuple[str, ...],
) -> None:
    resource = f"project:{request_context.project.project_id}" if request_context.project is not None else None
    for topic in topics:
        action = _subscription_action_for_topic(topic)
        await require_http_authorization(
            request_context,
            core_ports,
            action=action,
            resource=resource,
        )
        if topic.startswith("execution."):
            await require_http_authorization(
                request_context,
                core_ports,
                action="execution:read",
                resource=resource,
            )


def _subscription_action_for_topic(topic: str) -> str:
    prefix = topic.split(".", 1)[0]
    if prefix == "execution":
        return "live.execution:subscribe"
    if prefix == "session":
        return "live.session:subscribe"
    if prefix == "feature":
        return "live.feature:subscribe"
    if prefix == "project":
        return "live.project:subscribe"
    return "live:subscribe"


@live_router.get("/stream")
async def stream_live_updates(
    request: Request,
    topic: list[str] = Query(...),
    cursor: list[str] | None = Query(None),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
    live_broker: LiveEventBroker = Depends(get_live_event_broker),
) -> StreamingResponse:
    try:
        topics = normalize_topics(topic)
        cursors = parse_cursor_map(cursor or [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    unexpected_cursor_topics = sorted(set(cursors) - set(topics))
    if unexpected_cursor_topics:
        raise HTTPException(
            status_code=400,
            detail=f"Cursor topics must be part of the subscription: {', '.join(unexpected_cursor_topics)}",
        )

    await _authorize_topics(request_context=request_context, core_ports=core_ports, topics=topics)
    start = await live_broker.open_subscription(
        LiveReplayRequest(
            topics=topics,
            cursors=cursors,
            max_pending_events=config.CCDASH_LIVE_MAX_PENDING_EVENTS,
        )
    )
    return StreamingResponse(
        iter_live_sse_stream(
            request=request,
            start=start,
            heartbeat_interval_seconds=max(1, int(config.CCDASH_LIVE_HEARTBEAT_SECONDS)),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
