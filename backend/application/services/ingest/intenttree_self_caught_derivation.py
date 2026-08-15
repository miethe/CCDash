"""Self-caught-ratio derivation (are-we-winning-dashboard-v1 M2 part B).

Closed 3-bucket vocabulary, mirroring ``decide_attribution`` in
``backend/parsers/ica_spend.py`` (see that module's docstring): a single pure
decision function returns exactly one token from
``{self_caught, other_caught, unknown}``, and the never-silently-divide
property is structural (there is no code path here that folds ``unknown``
into either counted bucket, or computes a percentage over a reduced
denominator -- that happens, if at all, in the presentation layer, and this
derivation only ever persists per-node bucket counts).

Why ``unknown`` is expected to dominate -- and is correct, not a bug
-----------------------------------------------------------------------
Measured (worknote, Finding 2): ``node.created`` events are 100%
``actor_type=system`` (3,941/3,941) because every write reaches IntentTree
through one shared service token -- there is no actor-level discriminator on
the event log at all, and this is **permanently unbackfillable** for
historical rows (do not attempt one; there is nothing to recover it from).

The only node-level proxy signals mentioned in the worknote are a
``finding`` tag (17/200 sampled nodes) and ``meta.origin`` (7/200). Ground-
truth verified against the live IntentTree source
(``intenttree.services.work_item_sync.derive_default_origin`` and its seed
data): the ``finding`` tag, per the worknote itself, "marks *that* something
is a finding, not *who* caught it" -- it cannot discriminate self vs. other
by construction. ``meta.origin``'s actual observed value vocabulary
(``meta_plan``, ``implementation_plan``, ``human_gate``, ``decision``,
``bug``, ``deferred``, ``imported_plan``, ``source_artifact``) is a
node-*provenance* label -- which kind of artifact synthesized the node --
**not** a "who found this" attribution field. Neither confirmed value tells
us self-caught vs. other-caught.

Consequence, deliberate: ``_DEFAULT_ORIGIN_BUCKET_MAP`` below is **empty**.
Inventing a mapping from an unconfirmed origin value to
self_caught/other_caught would be exactly the "silently plausible wrong"
failure the plan's routing_constraints warn about ("misrouting a node into
self-caught/other-caught instead of unknown when the proxy signal is absent
is silently plausible and violates the never-silently-divide requirement").
So today, with the confirmed data, every node buckets to ``unknown`` --
which **is** the honest rendering of the measured reality, not a
placeholder to "fix" by inflating a bucket (plan rubric, verbatim).

``decide_self_caught_bucket`` still accepts an ``origin_bucket_map`` so the
closed-vocabulary machinery is real and testable (see
``test_are_we_winning_derivations.py``'s positive-path tests, which inject a
map to prove self_caught/other_caught assignment works) and so that IF
IntentTree's origin vocabulary is later confirmed to carry a genuine
attribution signal, wiring it in is a one-line change to
``_DEFAULT_ORIGIN_BUCKET_MAP`` -- not a new code path.

Candidate set -- incremental by design
-----------------------------------------
Unlike the reopened derivation (which must re-walk its whole candidate set
every pass -- a node can reopen more than once), a node's bucket verdict is
a point-in-time snapshot of its tags/meta at derivation time, and once
written is never re-derived (``insert_if_not_exists`` on the ``node_id``
primary key is a permanent no-op after the first successful bucket). The
candidate set for a pass is therefore ``distinct node.created node ids that
are not yet bucketed`` -- bounded to genuinely new work after the first full
pass. Trade-off, recorded explicitly: if a node's tags/meta change *after*
it has been bucketed (e.g. someone retroactively adds a ``finding`` tag),
that node's stored bucket does not update. Given the confirmed absence of
any current discriminating signal (see above), this trade-off has zero
observable effect today; it is worth revisiting only once a genuine
attribution signal exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Final

import httpx

from backend.db.repositories.base import retry_on_locked

from .intenttree_reopened_derivation import distinct_node_ids_for_event_type

logger = logging.getLogger("ccdash.ingest.intenttree_self_caught_derivation")

# ── Closed vocabulary (mirrors backend/parsers/ica_spend.py) ────────────────

SELF_CAUGHT_BUCKET: Final[str] = "self_caught"
OTHER_CAUGHT_BUCKET: Final[str] = "other_caught"
UNKNOWN_BUCKET: Final[str] = "unknown"

SELF_CAUGHT_RATIO_VOCAB: Final[frozenset[str]] = frozenset(
    {SELF_CAUGHT_BUCKET, OTHER_CAUGHT_BUCKET, UNKNOWN_BUCKET}
)

#: See the module docstring: deliberately empty today. Maps a confirmed
#: ``meta.origin`` value to a bucket token. Any value not present here (which
#: today is every value) resolves to ``unknown`` -- never inferred, never
#: defaulted, never redistributed.
_DEFAULT_ORIGIN_BUCKET_MAP: Final[dict[str, str]] = {}

SOURCE_ID: Final[str] = "intenttree:self_caught_derivation"

HttpGetter = Callable[[str, dict[str, Any], dict[str, str], float], Awaitable[dict[str, Any]]]


async def _default_http_get(
    url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


@dataclass(frozen=True)
class SelfCaughtVerdict:
    bucket: str
    reason: str


def decide_self_caught_bucket(
    *,
    tags: list[str] | None,
    meta: dict[str, Any] | None,
    origin_bucket_map: dict[str, str] | None = None,
) -> SelfCaughtVerdict:
    """Decide one node's self-caught bucket. Closed vocabulary; never raises.

    Precedence (mirrors ``decide_attribution``'s single-pass structure):

    1. ``meta.origin`` is present AND its value is a key in
       *origin_bucket_map* whose mapped token is exactly ``self_caught`` or
       ``other_caught`` -> that bucket.
    2. Anything else -- no discriminator present, an origin value absent
       from the map, or a mapped value that is not one of the two counted
       tokens (defends against a future map entry typo inventing a 4th
       bucket) -- -> ``unknown``.

    ``reason`` always records what was observed (finding-tag presence,
    meta.origin value or its absence) even on an ``unknown`` verdict, so
    drill-through can show *why* a node landed where it did.
    """
    tags = tags or []
    meta = meta or {}
    origin_bucket_map = origin_bucket_map or {}

    has_finding_tag = "finding" in tags
    origin = meta.get("origin")

    reason_bits: list[str] = []
    reason_bits.append(
        "finding tag present (not a caught-by discriminator)"
        if has_finding_tag
        else "no finding tag"
    )
    reason_bits.append(f"meta.origin={origin!r}" if origin else "meta.origin absent")

    if origin:
        candidate = origin_bucket_map.get(str(origin))
        if candidate in (SELF_CAUGHT_BUCKET, OTHER_CAUGHT_BUCKET):
            return SelfCaughtVerdict(bucket=candidate, reason="; ".join(reason_bits))

    return SelfCaughtVerdict(bucket=UNKNOWN_BUCKET, reason="; ".join(reason_bits))


@dataclass(slots=True)
class SelfCaughtDerivationResult:
    ok: bool
    candidate_node_ids: list[str] = field(default_factory=list)
    nodes_processed: int = 0
    buckets_written: dict[str, int] = field(
        default_factory=lambda: {SELF_CAUGHT_BUCKET: 0, OTHER_CAUGHT_BUCKET: 0, UNKNOWN_BUCKET: 0}
    )
    error: str | None = None


class IntentTreeSelfCaughtDerivationService:
    """Buckets every not-yet-bucketed ``node.created`` node id.

    Parameters mirror ``IntentTreeReopenedDerivationService``.
    ``origin_bucket_map`` defaults to ``_DEFAULT_ORIGIN_BUCKET_MAP`` (empty
    today, see module docstring) and is injectable for tests.
    """

    def __init__(
        self,
        events_db: Any,
        buckets_repo: Any,
        cursor_repo: Any | None,
        *,
        api_url: str,
        api_token: str,
        workspace_id: str,
        origin_bucket_map: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
        http_get: HttpGetter | None = None,
    ) -> None:
        self._events_db = events_db
        self._buckets_repo = buckets_repo
        self._cursor_repo = cursor_repo
        self._api_url = api_url.rstrip("/")
        self._api_token = api_token
        self._workspace_id = workspace_id
        self._origin_bucket_map = dict(
            origin_bucket_map if origin_bucket_map is not None else _DEFAULT_ORIGIN_BUCKET_MAP
        )
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get or _default_http_get

    async def derive_all(self) -> SelfCaughtDerivationResult:
        """Bucket every not-yet-bucketed ``node.created`` node id. Never raises."""
        await self._cursor_get_or_create()

        all_created_ids = await distinct_node_ids_for_event_type(self._events_db, "node.created")
        already_bucketed = await self._buckets_repo.get_bucketed_node_ids()
        candidate_node_ids = sorted(all_created_ids - already_bucketed)

        nodes_processed = 0
        buckets_written = {SELF_CAUGHT_BUCKET: 0, OTHER_CAUGHT_BUCKET: 0, UNKNOWN_BUCKET: 0}

        for node_id in candidate_node_ids:
            try:
                node = await self._http_get(
                    f"{self._api_url}/api/v1/nodes/{node_id}",
                    {"workspace_id": self._workspace_id},
                    {"Authorization": f"Bearer {self._api_token}"},
                    self._timeout_seconds,
                )
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                logger.warning(
                    "intenttree self-caught derivation: fetch failed for node_id=%s "
                    "after %d/%d node(s) processed (not rolled back): %s",
                    node_id,
                    nodes_processed,
                    len(candidate_node_ids),
                    exc,
                )
                await self._cursor_record_error(str(exc))
                return SelfCaughtDerivationResult(
                    ok=False,
                    candidate_node_ids=candidate_node_ids,
                    nodes_processed=nodes_processed,
                    buckets_written=buckets_written,
                    error=str(exc),
                )

            verdict = decide_self_caught_bucket(
                tags=node.get("tags"),
                meta=node.get("meta"),
                origin_bucket_map=self._origin_bucket_map,
            )
            was_new = await retry_on_locked(
                lambda r={
                    "node_id": node_id,
                    "bucket": verdict.bucket,
                    "reason": verdict.reason,
                }: self._buckets_repo.insert_if_not_exists(r),
                repo="intent_tree_self_caught_buckets",
            )
            nodes_processed += 1
            if was_new:
                buckets_written[verdict.bucket] = buckets_written.get(verdict.bucket, 0) + 1

        await self._cursor_advance()
        return SelfCaughtDerivationResult(
            ok=True,
            candidate_node_ids=candidate_node_ids,
            nodes_processed=nodes_processed,
            buckets_written=buckets_written,
        )

    # ── Cursor bookkeeping (best-effort, mirrors intenttree_events_ingest.py) ──

    async def _cursor_get_or_create(self) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.get_or_create(
                    source_id=SOURCE_ID,
                    project_id="global",
                    workspace_id=self._workspace_id,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intenttree self-caught derivation: cursor get_or_create failed: %s", exc)

    async def _cursor_advance(self) -> None:
        if self._cursor_repo is None:
            return
        from datetime import datetime, timezone

        try:
            await retry_on_locked(
                lambda: self._cursor_repo.advance(
                    source_id=SOURCE_ID,
                    project_id="global",
                    workspace_id=self._workspace_id,
                    cursor_value=datetime.now(timezone.utc).isoformat(),
                    occurred_at=datetime.now(timezone.utc).isoformat(),
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intenttree self-caught derivation: cursor advance failed: %s", exc)

    async def _cursor_record_error(self, error_message: str) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.record_error(
                    source_id=SOURCE_ID,
                    project_id="global",
                    workspace_id=self._workspace_id,
                    error_message=error_message,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intenttree self-caught derivation: cursor record_error failed: %s", exc)


__all__ = [
    "SELF_CAUGHT_BUCKET",
    "OTHER_CAUGHT_BUCKET",
    "UNKNOWN_BUCKET",
    "SELF_CAUGHT_RATIO_VOCAB",
    "SOURCE_ID",
    "SelfCaughtVerdict",
    "SelfCaughtDerivationResult",
    "IntentTreeSelfCaughtDerivationService",
    "decide_self_caught_bucket",
]
