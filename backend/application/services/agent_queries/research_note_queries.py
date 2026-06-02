"""Transport-neutral MeatyWiki research note query service (P5-013).

Capability-gated: when ``config.MEATYWIKI_ENABLED`` is False, all methods
return an empty-state ``ResearchNoteResponse(items=[], enabled=False)``
without hitting the database.  Consumers should hide the MeatyWiki surface
when ``enabled=False``.
"""
from __future__ import annotations

import logging

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.db.repositories.research_notes import SqliteResearchNoteRepository
from backend.models import ResearchNote, ResearchNoteResponse

logger = logging.getLogger("ccdash.agent_queries.research_note")


def _row_to_model(row: dict) -> ResearchNote:
    return ResearchNote(
        id=str(row.get("id") or ""),
        projectId=str(row.get("project_id") or ""),
        featureId=str(row.get("feature_id") or "") or None,
        title=str(row.get("title") or ""),
        url=str(row.get("url") or ""),
        body=str(row.get("body") or ""),
        source=str(row.get("source") or ""),
        createdAt=str(row.get("created_at") or ""),
    )


class ResearchNoteQueryService:
    """Read-only query surface for MeatyWiki research notes.

    Transport-neutral: called from the REST router (meatywiki.py).
    """

    async def get_for_feature(
        self,
        ctx: RequestContext,
        ports: CorePorts,
        project_id: str,
        feature_id: str,
    ) -> ResearchNoteResponse:
        """Return research notes for a feature, or empty-state when MeatyWiki is off.

        Args:
            ctx: Request context (unused for now; present for transport-neutral parity).
            ports: Core ports providing DB access.
            project_id: Resolved project identifier.
            feature_id: Feature to query.

        Returns:
            ``ResearchNoteResponse`` with ``enabled=False`` when the capability
            flag is off, or populated ``items`` when on.
        """
        if not config.MEATYWIKI_ENABLED:
            return ResearchNoteResponse(items=[], enabled=False)

        try:
            db = ports.storage.db
            repo = SqliteResearchNoteRepository(db)
            rows = await repo.list_by_feature(project_id, feature_id)
            items = [_row_to_model(row) for row in rows]
            return ResearchNoteResponse(items=items, enabled=True)
        except Exception:
            logger.exception(
                "research_note_queries: failed to load notes project=%s feature=%s",
                project_id,
                feature_id,
            )
            return ResearchNoteResponse(items=[], enabled=True)
