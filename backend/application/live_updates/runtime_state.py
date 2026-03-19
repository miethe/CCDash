"""Runtime accessors for the active live event publisher."""
from __future__ import annotations

import logging
from typing import Any

from backend.application.live_updates.publisher import LiveEventPublisher


logger = logging.getLogger("ccdash.live.runtime")

_LIVE_EVENT_PUBLISHER: LiveEventPublisher | None = None


def set_live_event_publisher(publisher: LiveEventPublisher | None) -> None:
    global _LIVE_EVENT_PUBLISHER
    _LIVE_EVENT_PUBLISHER = publisher


def get_live_event_publisher() -> LiveEventPublisher | None:
    return _LIVE_EVENT_PUBLISHER


async def publish_live_append(*, topic: str, payload: dict[str, Any], occurred_at: str | None = None) -> None:
    publisher = get_live_event_publisher()
    if publisher is None:
        return
    try:
        await publisher.publish_append(topic=topic, payload=payload, occurred_at=occurred_at)
    except Exception:
        logger.exception("Failed to publish live append event for topic '%s'.", topic)


async def publish_live_invalidation(
    *,
    topic: str,
    payload: dict[str, Any],
    occurred_at: str | None = None,
    recovery_hint: str | None = "rest_snapshot",
) -> None:
    publisher = get_live_event_publisher()
    if publisher is None:
        return
    try:
        await publisher.publish_invalidation(
            topic=topic,
            payload=payload,
            occurred_at=occurred_at,
            recovery_hint=recovery_hint,
        )
    except Exception:
        logger.exception("Failed to publish live invalidation event for topic '%s'.", topic)

