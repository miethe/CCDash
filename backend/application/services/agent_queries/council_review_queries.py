"""Transport-neutral ARC council review query service (P5-012).

Capability-gated: when ``config.ARC_ENABLED`` is False, all methods return
an empty-state ``CouncilReviewResponse(items=[], enabled=False)`` without
hitting the database.  Consumers should hide the ARC surface when
``enabled=False`` rather than rendering an empty list.
"""
from __future__ import annotations

import logging

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.db.repositories.council_reviews import SqliteCouncilReviewRepository
from backend.models import CouncilReview, CouncilReviewResponse

logger = logging.getLogger("ccdash.agent_queries.council_review")


def _row_to_model(row: dict) -> CouncilReview:
    return CouncilReview(
        id=str(row.get("id") or ""),
        projectId=str(row.get("project_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        status=str(row.get("status") or "pending"),
        summary=str(row.get("summary") or ""),
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


class CouncilReviewQueryService:
    """Read-only query surface for ARC council reviews.

    Transport-neutral: called from the REST router (council.py).
    """

    async def get_for_feature(
        self,
        ctx: RequestContext,
        ports: CorePorts,
        project_id: str,
        feature_id: str,
    ) -> CouncilReviewResponse:
        """Return council reviews for a feature, or empty-state when ARC is off.

        Args:
            ctx: Request context (unused for now; present for transport-neutral parity).
            ports: Core ports providing DB access.
            project_id: Resolved project identifier.
            feature_id: Feature to query.

        Returns:
            ``CouncilReviewResponse`` with ``enabled=False`` when the capability
            flag is off, or populated ``items`` when on.
        """
        if not config.ARC_ENABLED:
            return CouncilReviewResponse(items=[], enabled=False)

        try:
            db = ports.storage.db
            repo = SqliteCouncilReviewRepository(db)
            rows = await repo.list_by_feature(project_id, feature_id)
            items = [_row_to_model(row) for row in rows]
            return CouncilReviewResponse(items=items, enabled=True)
        except Exception:
            logger.exception(
                "council_review_queries: failed to load reviews project=%s feature=%s",
                project_id,
                feature_id,
            )
            return CouncilReviewResponse(items=[], enabled=True)
