"""SQLite + PostgreSQL repositories for the provider dimension entities.

Covers three tables shipped by the ``provider-channel-credential-entities-v1``
milestone (M1, SCHEMA_VERSION 52; DDL in ``backend/db/sqlite_migrations.py``'s
``_PROVIDER_DIMENSION_TABLES`` block, mirrored in
``backend/db/postgres_migrations.py``):

- ``provider_dimensions``  -- one row per derived ``providerId`` (see
  ``backend.model_identity.derive_provider_identity``), keyed on ``provider_id``.
- ``provider_channels``    -- one row per observed ``channel`` token (the raw,
  unrecognized-tokens-allowed key namespace used by ``provider_credentials``),
  keyed on ``channel``.
- ``provider_credentials`` -- one row per credential *name* (never secret
  material -- see the module-level secret guard below), keyed on
  ``(channel, credential_name)``.

Two backend implementations are provided --
:class:`SqliteProviderDimensionsRepository` (aiosqlite) and
:class:`PostgresProviderDimensionsRepository` (asyncpg) -- with an identical
public interface (every upsert, every read, and the backfill). Callers should
go through :func:`get_provider_dimensions_repository` rather than
constructing either class directly, so the correct backend is always picked
for the connection in hand. This dual-backend shape mirrors
``backend/db/repositories/aar_reviews.py``'s
``SqliteAarReviewsRepository`` / ``PostgresAarReviewsRepository`` split.

ADR-007 contract (backend/db/repositories/base.py::retry_on_locked)
---------------------------------------------------------------------------
Per ADR-007 (``docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md``),
every write path in this module goes through
``backend.db.repositories.base.retry_on_locked`` with a ``repo=`` label so
SQLite "database is locked" contention is retried with backoff (and, on
exhaustion, surfaced -- never silently swallowed) rather than raising
immediately or, worse, silently no-oping. This is the same shape used by
``SqliteAarReviewsRepository`` and ``SqliteSessionRepository``: build the SQL
+ params, wrap the actual ``self.db.execute(...)`` (+ ``self.db.commit()`` on
SQLite) call in a zero-arg async closure, and pass that closure to
``retry_on_locked``. No write method in this module calls ``self.db.execute``
directly outside that wrapper. The Postgres repository wraps its writes in
``retry_on_locked`` too (mirroring ``PostgresAarReviewsRepository`` /
``PostgresRoutingRollupRepository``) even though "locked" is a SQLite-specific
condition -- it is a harmless pass-through there and keeps both backends on
the same call shape.

Rotation lineage -- declare path (M2)
---------------------------------------------------------------------------
``declare_rotation`` is the ONLY way ``rotated_from_id`` /
``rotation_declared_at`` / ``rotation_declared_by`` are ever written --
``upsert_provider_credential`` never touches them, on insert or update. It
takes the successor and predecessor credential EXPLICITLY (as
``(channel, credential_name)`` pairs resolved to their ``provider_credentials
.id``); nothing is inferred from name similarity or timing -- that is this
feature's central design decision. Before writing, it validates:

- the predecessor credential must exist (else ``ValueError``, nothing
  written);
- the successor credential must exist (else ``ValueError``, nothing
  written);
- a credential may not be declared as its own predecessor (``ValueError``);
- the declaration must not close a CYCLE -- the existing chain reachable from
  the predecessor via ``rotated_from_id`` is walked (visited-guarded) before
  writing, and if the successor's id is found on that chain, the write is
  rejected. The READ side
  (``backend/application/services/agent_queries/provider_credential_rollup.py``'s
  union-find) is deliberately cycle-TOLERANT, because a stray cycle already
  in the data must not crash a read -- but this write path is where chain
  integrity is actually enforced, since the DDL deliberately carries no FK on
  ``rotated_from_id`` (open-vocabulary derived data, same reasoning as
  ``channel``);
- re-declaring the identical pointer (same predecessor) is a no-op --
  idempotent, no error, no duplicate write, no timestamp refresh;
- re-declaring a DIFFERENT predecessor over an existing declared pointer is
  rejected outright rather than silently overwriting a recorded human
  decision -- callers must not have a "just overwrite" path here.

See :func:`_validate_declare_rotation` (shared, backend-agnostic) for the
actual validation logic, and ``backend/cli/commands/provider.py``'s
``provider declare-rotation`` command for the operator-facing entry point.

Secret-material guard
---------------------------------------------------------------------------
Every caller-supplied string column persisted into any of the three tables
is guarded by :func:`_reject_if_secret_shaped` BEFORE any SQL is built or
executed -- including ``channel`` / ``provider_channel``, not just
``credential_name``. Concretely, per write method:

- ``upsert_provider_dimension``: guards ``provider_id``, ``provider_vendor``,
  ``provider_surface``, ``provider_channel``, ``provider_label``.
- ``upsert_provider_channel``: guards ``channel``, ``label``.
- ``upsert_provider_credential``: guards ``channel``, ``credential_name``,
  ``provider_id``.
- ``declare_rotation``: guards ``channel``, ``predecessor_credential_name``,
  ``successor_credential_name``, ``declared_by``.

This is a fail-closed heuristic: a false reject is an operator annoyance
(rename the key), a false accept is a secret landing in the database, so the
guard errs toward rejecting. See ``_SECRET_NAME_MAX_LENGTH`` and
``_looks_like_secret`` for the exact rules. Every legitimate value these
columns actually carry -- a derived ``providerId`` slug
("anthropic:claude-code:ica"), a short vendor/surface/channel token
("Anthropic", "Claude Code", "subscription"), or a "vendor · surface" display
label ("Anthropic · Claude Code · ICA") -- passes; see
``backend/tests/test_provider_dimensions_repo.py`` for the realistic-value
coverage locking this in.

Why ``-`` and ``_`` are excluded from the high-entropy-run alphabet
---------------------------------------------------------------------------
Unknown ``channel`` tokens are explicitly allowed to persist and round-trip
unchanged -- this table's key namespace is NOT drawn from a closed
vocabulary by design (see ``ProviderChannelsDirectCountTests
.test_unknown_channel_token_never_raises_and_round_trips``, an M1 acceptance
criterion, unchanged, still using its original 38-char hyphenated token --
this is the regression lock for the issue described here). An earlier version
of ``_HIGH_ENTROPY_RUN_PATTERN`` (``[A-Za-z0-9+/_-]{32,}``) INCLUDED the
hyphen and underscore in its run alphabet, which meant a hyphenated
human-readable slug like "totally-unrecognized-future-channel-v9" or
"vertex-ai-workbench-preview-2027-rollout" read as ONE unbroken 32+ char
high-entropy run and false-rejected -- a real, reproduced false-reject, not a
hypothetical, and it directly contradicted the open-vocabulary contract that
test locks in. The fix was not to exempt ``channel`` from the guard (which
would have left a real gap: a raw, prefix-less secret pasted into ``channel``
would have slipped past every other defense) but to fix the ALPHABET: ``-``
and ``_`` are word SEPARATORS in every legitimate value this guard sees, not
entropy. Excluding them from ``_HIGH_ENTROPY_RUN_PATTERN`` (now
``[A-Za-z0-9+/]{32,}``) makes hyphenated/underscored slugs read as multiple
short segments instead of one long run, which is exactly the shape that
should pass. Every documented secret shape still trips this rule with the
narrower alphabet -- a real secret's encoding (hex, base64, base64url, or a
raw API-key body) is genuinely high-entropy across contiguous alphanumerics
regardless of whether ``-``/``_`` also happen to appear in it (e.g. ``ghp_``
is a 4-char prefix followed by an unbroken 36-char alphanumeric body; the
prefix rule catches it independently anyway). See
``NarrowedEntropyAlphabetTests`` in
``backend/tests/test_provider_dimensions_repo.py`` for the explicit
before/after sweep across every legitimate and secret shape this guard is
meant to classify, and note that widening the alphabet back would fail that
suite loudly, by design.

SECURITY -- guard-before-INSERT ordering on the Postgres path
---------------------------------------------------------------------------
On :class:`PostgresProviderDimensionsRepository`, every guard call happens
before any SQL string is built and before ``self.db.execute`` is ever
reached. This ordering is load-bearing, not incidental: PostgreSQL's
UNIQUE-violation error carries a ``DETAIL`` line that ECHOES THE OFFENDING
VALUES (e.g. ``Key (channel, credential_name)=(ica, <value>) already
exists.``), unlike SQLite's ``IntegrityError``, which names only the
constraint/column, never the value. If a secret-shaped value ever reached
the SQL layer here and collided with an existing row, the duplicate-key
error itself would disclose the secret that this guard exists to keep out of
logs and error bodies -- silently defeating the whole point of
:func:`_reject_if_secret_shaped`. A future refactor that reorders "build SQL"
ahead of "run the guard" (e.g. to share a query-builder helper) would
reintroduce that leak without any test failing unless it specifically probes
guard-vs-INSERT ordering -- see
``ProviderCredentialUpsertGuardMessageLeakTests`` /
``PostgresProviderCredentialGuardOrderingTests`` in
``backend/tests/test_provider_dimensions_repo.py``, which assert the guard
fires before ``self.db.execute`` is ever called.

Backfill skip-on-poison contract
---------------------------------------------------------------------------
``backfill_provider_dimensions_from_sessions`` derives dimension/channel/
credential values from ``sessions`` columns per-row. If a derived value for
ANY of the three tables happens to be secret-shaped (should never happen by
contract, but the guard exists precisely because "should never happen" is
not "cannot happen"), that ONE row's upsert for that table is skipped and
counted (``providers_skipped_secret`` / ``channels_skipped_secret`` /
``credentials_skipped_secret``) -- the ``ValueError`` is caught, the rest of
the pass continues, and no partial write reaches the table (the guard runs
before any SQL is built). This mirrors the original ``ica_key`` ->
``credentials_skipped_secret`` behavior, extended to every derived field on
every table.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.db.repositories.base import retry_on_locked
from backend.model_identity import derive_provider_identity

_REPO_NAME = "provider_dimensions"

# ── Secret-shaped value guard ────────────────────────────────────────────────

# A credential *name* should be a short human-chosen label. 128 chars is a
# generous ceiling for that (well beyond "prod-api-key-name-for-team-3") while
# comfortably excluding most real secret encodings, which tend to run longer.
# The same ceiling is reused for every other guarded field below -- none of
# their legitimate values (short vendor/surface/channel tokens, "vendor ·
# surface" display labels, "vendor:surface:channel" provider-id slugs) come
# remotely close to it either.
_SECRET_NAME_MAX_LENGTH = 128

# Known API-key / token prefix shapes. Matched case-sensitively where the
# real-world convention is case-sensitive (e.g. "sk-", "ghp_") to avoid
# false-rejecting legitimate names that merely happen to share letters.
_SECRET_PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^sk-ant-"),           # Anthropic API key
    re.compile(r"^sk-"),               # OpenAI-style API key
    re.compile(r"^ghp_"),              # GitHub personal access token
    re.compile(r"^gho_"),              # GitHub OAuth token
    re.compile(r"^github_pat_"),       # GitHub fine-grained PAT
    re.compile(r"^xox[baprs]-"),       # Slack tokens (bot/app/user/refresh/etc.)
    re.compile(r"^AIza"),              # Google API key
    re.compile(r"^AKIA"),              # AWS access key ID
)

# A bare JWT: three dot-separated base64url segments, starting with the
# standard "eyJ" header prefix (base64 of '{"').
_JWT_PATTERN = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$")

# A whitespace-free run of >= 32 hex or base64-alphabet characters anywhere in
# the value -- catches raw high-entropy secrets even when not prefixed by a
# recognizable vendor marker (generic tokens, hex-encoded keys, etc.).
#
# DELIBERATELY EXCLUDES "-" and "_" from the run alphabet. In a real secret
# encoding (hex, base64, base64url, a bare API-key body) those two characters
# are just more alphabet, so a genuine secret's high-entropy run is unbroken
# whether or not they are included -- every secret shape this guard is meant
# to catch (sk-ant-.../ghp_.../a raw hex or base64 blob) still trips this rule
# with the narrower alphabet (see the empirical sweep in
# ``backend/tests/test_provider_dimensions_repo.py``'s
# ``NarrowedEntropyAlphabetTests``). In a human-authored SLUG, though, "-" and
# "_" are word SEPARATORS, not entropy -- a hyphenated name like
# "totally-unrecognized-future-channel-v9" is semantically closer to five
# short words than one 38-character blob. Including them in the run alphabet
# made the guard read separator-delimited slugs as a single unbroken
# high-entropy run, which is what caused a real, reproduced false-reject on
# ``channel`` (a legitimate, M1-shipped, tested open-vocabulary field -- see
# ``test_unknown_channel_token_never_raises_and_round_trips``). Treating "-"
# and "_" as separators (i.e. excluding them from the character class) fixes
# that false-reject for every guarded field without weakening detection on
# any of them.
_HIGH_ENTROPY_RUN_PATTERN = re.compile(r"[A-Za-z0-9+/]{32,}")


def _looks_like_secret(value: str) -> str | None:
    """Return a matched-rule CLASS identifier if *value* looks secret-shaped, else None.

    The returned identifier is deliberately a coarse rule CLASS
    ('secret-prefix', 'jwt-shape', 'high-entropy-run', 'over-length') and
    never the concrete pattern or matched substring -- even naming which
    *vendor's* prefix pattern matched (e.g. echoing ``'^sk-ant-'``) would leak
    which provider's key was pasted. Callers must not embed the offending
    *value* in any message built from this result either -- see
    :func:`_reject_if_secret_shaped`.
    """
    if len(value) > _SECRET_NAME_MAX_LENGTH:
        return "over-length"
    for pattern in _SECRET_PREFIX_PATTERNS:
        if pattern.search(value):
            return "secret-prefix"
    if _JWT_PATTERN.match(value):
        return "jwt-shape"
    if _HIGH_ENTROPY_RUN_PATTERN.search(value):
        return "high-entropy-run"
    return None


def _reject_if_secret_shaped(value: str, *, field: str) -> None:
    """Raise ``ValueError`` if *value* looks like secret material.

    Called on EVERY caller-supplied string column before it is written to
    ``provider_dimensions`` / ``provider_channels`` / ``provider_credentials``
    -- see the module docstring's "Secret-material guard" section for the
    full per-method field list. Err on the side of rejecting: a legitimate
    short name ("CC1", "CC6", "prod-api-key-name", "team-seat-3"), vendor/
    surface/channel token ("Anthropic", "Claude Code", "subscription"), or
    "vendor · surface" display label never trips any of the rules above.

    SECURITY: the raised message MUST NOT contain *value*, any prefix/suffix
    of it, a redacted-but-partial form, or a hash of it -- only the field
    name, the matched rule CLASS, and the value's length. This repo has an
    adjacent open defect (IntentTree node_01KZEXSPEKDRCSY3FGEVZPEWMV) for
    credentials leaking into logs/error bodies via exception messages; a
    ``ValueError`` that echoes the secret it just caught would regress it the
    moment any caller logs the exception or it surfaces through a router.
    Nothing in this function logs *value* either -- the guard never calls a
    logger, so the only way *value* could reach a log/error body is a caller
    doing so explicitly, which this message is written to make unnecessary.

    Callers on the Postgres path MUST invoke this before building any SQL --
    see the module docstring's "guard-before-INSERT ordering" section for
    why that ordering is load-bearing there.
    """
    rule = _looks_like_secret(value)
    if rule is not None:
        raise ValueError(
            f"Refusing to persist {field}: value looks like secret material "
            f"(matched rule {rule!r}; length {len(value)}). "
            f"{field} must be a short human-chosen value, "
            "never the secret bytes themselves. The offending value is deliberately "
            "not included in this message so it cannot reach logs or an error body."
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Shared backfill loop (backend-agnostic) ──────────────────────────────────


async def _run_provider_backfill(repo: Any, session_rows: Any) -> dict[str, int]:
    """Dedup + upsert loop shared by both backends' ``backfill_provider_dimensions_from_sessions``.

    *repo* must expose ``get_provider_dimension`` / ``upsert_provider_dimension`` /
    ``get_provider_channel`` / ``upsert_provider_channel`` / ``get_provider_credential`` /
    ``upsert_provider_credential`` -- both :class:`SqliteProviderDimensionsRepository`
    and :class:`PostgresProviderDimensionsRepository` satisfy this shape, and each
    passes its own backend's already-fetched *session_rows* here. ``aiosqlite.Row``
    and ``asyncpg.Record`` both support ``row["col"]`` indexing, so this loop is
    written once and never diverges between backends.

    For every ``sessions`` row, derives provider identity via
    :func:`backend.model_identity.derive_provider_identity` from the session's
    ``model``, ``platform_type``, ``launcher``, and ``model_variant`` columns
    (this is a READ-only scan -- no column on ``sessions`` is ever written by
    this function), then upserts:

    - one ``provider_dimensions`` row per distinct ``providerId``,
    - one ``provider_channels`` row per distinct ``providerChannel``
      (unrecognized/"unknown" channel tokens are stored and read back
      unchanged, never rejected -- see the module docstring), and
    - one ``provider_credentials`` row per distinct
      ``(channel, ica_key)`` pair, but ONLY where ``sessions.ica_key IS
      NOT NULL`` and non-empty after stripping whitespace. Most rows in
      the wild have a NULL ``ica_key`` today; that is the common path,
      not an edge case, and produces zero credential rows with zero
      errors.

    Every write below goes through the repo's existing ``upsert_provider_*``
    methods, so it already carries ``retry_on_locked`` (ADR-007) and the
    ``_reject_if_secret_shaped`` guard on every persisted field. If a
    session's derived value for ANY of the three tables happens to be
    secret-shaped (a poisoned row -- should never happen by contract, but the
    guard exists precisely because "should never happen" is not "cannot
    happen"), that ONE row's upsert for that table is skipped and counted in
    ``providers_skipped_secret`` / ``channels_skipped_secret`` /
    ``credentials_skipped_secret`` -- the ``ValueError`` is caught here and
    does not abort the rest of the pass, and no partial write reaches the
    table (the guard runs before any SQL is built). Other tables' entries for
    the same row are still derived normally; only the poisoned table's row is
    skipped.

    Idempotent: re-running against an unchanged ``sessions`` table upserts
    the exact same distinct keys every time. Insert/update are distinguished
    with a pre-write existence check (``get_provider_*``) so the returned
    stats accurately report 0 new inserts on a repeat pass -- ``first_seen_at``
    / ``created_at`` are never touched by the underlying ``ON CONFLICT``
    clauses either way.

    Returns a stats dict:
    ``{"sessions_scanned", "providers_inserted", "providers_updated",
    "providers_skipped_secret", "channels_inserted", "channels_updated",
    "channels_skipped_secret", "credentials_inserted", "credentials_updated",
    "credentials_skipped_secret"}``.
    """
    stats: dict[str, int] = {
        "sessions_scanned": len(session_rows),
        "providers_inserted": 0,
        "providers_updated": 0,
        "providers_skipped_secret": 0,
        "channels_inserted": 0,
        "channels_updated": 0,
        "channels_skipped_secret": 0,
        "credentials_inserted": 0,
        "credentials_updated": 0,
        "credentials_skipped_secret": 0,
    }

    # Dedupe within this pass -- keyed dicts (not sets) so the LAST
    # session observed for a given key wins deterministically, matching
    # the fixed row order `SELECT ... WHERE project_id = ?` returns
    # against an unchanged table (the property idempotency relies on).
    seen_providers: dict[str, dict[str, str]] = {}
    seen_channels: set[str] = set()
    seen_credentials: dict[tuple[str, str], str] = {}

    for row in session_rows:
        identity = derive_provider_identity(
            row["model"],
            row["platform_type"],
            row["launcher"],
            row["model_variant"],
        )
        provider_id = identity["providerId"]
        channel = identity["providerChannel"]
        seen_providers[provider_id] = identity
        seen_channels.add(channel)

        ica_key = row["ica_key"]
        key_name = str(ica_key).strip() if ica_key is not None else ""
        if key_name:
            seen_credentials[(channel, key_name)] = provider_id

    for provider_id, identity in seen_providers.items():
        existed = await repo.get_provider_dimension(provider_id) is not None
        try:
            await repo.upsert_provider_dimension(
                provider_id=provider_id,
                provider_vendor=identity["providerVendor"],
                provider_surface=identity["providerSurface"],
                provider_channel=identity["providerChannel"],
                provider_label=identity["providerLabel"],
            )
        except ValueError:
            stats["providers_skipped_secret"] += 1
            continue
        if existed:
            stats["providers_updated"] += 1
        else:
            stats["providers_inserted"] += 1

    for channel in seen_channels:
        existed = await repo.get_provider_channel(channel) is not None
        try:
            await repo.upsert_provider_channel(channel=channel)
        except ValueError:
            stats["channels_skipped_secret"] += 1
            continue
        if existed:
            stats["channels_updated"] += 1
        else:
            stats["channels_inserted"] += 1

    for (channel, credential_name), provider_id in seen_credentials.items():
        existed = (
            await repo.get_provider_credential(channel, credential_name) is not None
        )
        try:
            await repo.upsert_provider_credential(
                channel=channel,
                credential_name=credential_name,
                provider_id=provider_id,
            )
        except ValueError:
            stats["credentials_skipped_secret"] += 1
            continue
        if existed:
            stats["credentials_updated"] += 1
        else:
            stats["credentials_inserted"] += 1

    return stats


# ── Shared rotation-declare validation (backend-agnostic) ───────────────────


class RotationCredentialNotFoundError(ValueError):
    """Raised when the predecessor or successor credential does not exist."""


class RotationSelfReferenceError(ValueError):
    """Raised when a credential is declared as its own predecessor."""


class RotationCycleError(ValueError):
    """Raised when declaring the rotation would close a cycle in the chain."""


class RotationConflictError(ValueError):
    """Raised when re-declaring a different predecessor than the one already recorded."""


async def _validate_declare_rotation(
    *,
    get_by_channel_name: Any,
    get_by_id: Any,
    channel: str,
    predecessor_name: str,
    successor_name: str,
) -> tuple[int, int] | None:
    """Validate a rotation declaration and resolve it to a write, or a no-op.

    *get_by_channel_name* and *get_by_id* are zero-state async callables
    (``(channel, name) -> dict | None`` and ``(id) -> dict | None``
    respectively) supplied by each backend so this validation logic is
    written once and never diverges between :class:`SqliteProviderDimensionsRepository`
    and :class:`PostgresProviderDimensionsRepository` -- mirrors the
    :func:`_run_provider_backfill` sharing pattern above.

    Returns ``(successor_id, predecessor_id)`` to write if the declaration is
    new and valid, or ``None`` if it is an idempotent re-declare of the exact
    pointer already recorded (nothing to write). Raises ``ValueError`` (one
    of the subclasses above) for every other rejection case, and never
    resolves partial state before raising -- callers write nothing in that
    case.
    """
    predecessor_row = await get_by_channel_name(channel, predecessor_name)
    if predecessor_row is None:
        raise RotationCredentialNotFoundError(
            f"Predecessor credential not found: channel={channel!r} "
            f"credential_name={predecessor_name!r}"
        )
    successor_row = await get_by_channel_name(channel, successor_name)
    if successor_row is None:
        raise RotationCredentialNotFoundError(
            f"Successor credential not found: channel={channel!r} "
            f"credential_name={successor_name!r}"
        )

    predecessor_id = int(predecessor_row["id"])
    successor_id = int(successor_row["id"])

    if predecessor_id == successor_id:
        raise RotationSelfReferenceError(
            "A credential may not be declared as its own predecessor "
            f"(channel={channel!r} credential_name={predecessor_name!r})."
        )

    existing_pointer = successor_row["rotated_from_id"]
    if existing_pointer is not None:
        existing_pointer = int(existing_pointer)
        if existing_pointer == predecessor_id:
            # Idempotent re-declare of the exact same pointer: no-op.
            return None
        raise RotationConflictError(
            f"Successor credential (channel={channel!r} "
            f"credential_name={successor_name!r}, id={successor_id}) already "
            f"has a declared predecessor (id={existing_pointer}); declaring a "
            f"different predecessor (id={predecessor_id}) over it is "
            "rejected rather than silently overwriting a recorded human "
            "decision."
        )

    # Cycle check: walk the existing rotated_from_id chain starting at the
    # predecessor. If the successor's id is already reachable on that chain,
    # writing successor -> predecessor would close a loop. Visited-guarded
    # so a pre-existing cycle in stored data (should never happen -- the DDL
    # has no FK/CHECK -- but "should never happen" is not "cannot happen")
    # cannot spin this walk forever.
    visited: set[int] = {predecessor_id}
    current_id: int | None = predecessor_id
    while True:
        current_row = await get_by_id(current_id)
        if current_row is None:
            break
        next_id = current_row["rotated_from_id"]
        if next_id is None:
            break
        next_id = int(next_id)
        if next_id == successor_id:
            raise RotationCycleError(
                f"Declaring channel={channel!r} successor="
                f"{successor_name!r} (id={successor_id}) <- predecessor="
                f"{predecessor_name!r} (id={predecessor_id}) would close a "
                "cycle in the rotation chain: the predecessor already "
                "transitively leads back to the successor."
            )
        if next_id in visited:
            break
        visited.add(next_id)
        current_id = next_id

    return (successor_id, predecessor_id)


# ── SQLite ────────────────────────────────────────────────────────────────


class SqliteProviderDimensionsRepository:
    """aiosqlite-backed writer/reader for the three provider dimension tables."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    # ── provider_dimensions ──────────────────────────────────────────────

    async def upsert_provider_dimension(
        self,
        *,
        provider_id: str,
        provider_vendor: str = "",
        provider_surface: str = "",
        provider_channel: str = "",
        provider_label: str = "",
    ) -> None:
        """Idempotently upsert a ``provider_dimensions`` row keyed on ``provider_id``.

        Every field -- including ``provider_channel`` -- is guarded by
        :func:`_reject_if_secret_shaped` before any SQL is built or executed;
        see the module docstring's "why ``-``/``_`` are excluded from the
        high-entropy-run alphabet" section for why guarding ``provider_channel``
        no longer false-rejects legitimate open-vocabulary channel tokens.

        Sets ``first_seen_at`` only on insert (``ON CONFLICT`` never touches it);
        ``last_seen_at`` and ``updated_at`` are refreshed on every call, insert
        or update alike.
        """
        _reject_if_secret_shaped(provider_id, field="provider_id")
        _reject_if_secret_shaped(provider_vendor, field="provider_vendor")
        _reject_if_secret_shaped(provider_surface, field="provider_surface")
        _reject_if_secret_shaped(provider_channel, field="provider_channel")
        _reject_if_secret_shaped(provider_label, field="provider_label")
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                INSERT INTO provider_dimensions (
                    provider_id, provider_vendor, provider_surface, provider_channel,
                    provider_label, first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    provider_vendor = excluded.provider_vendor,
                    provider_surface = excluded.provider_surface,
                    provider_channel = excluded.provider_channel,
                    provider_label = excluded.provider_label,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (
                    provider_id,
                    provider_vendor,
                    provider_surface,
                    provider_channel,
                    provider_label,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            await self.db.commit()

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def get_provider_dimension(self, provider_id: str) -> dict[str, Any] | None:
        cursor = await self.db.execute(
            "SELECT * FROM provider_dimensions WHERE provider_id = ?", (provider_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_provider_dimensions(self) -> list[dict[str, Any]]:
        cursor = await self.db.execute(
            "SELECT * FROM provider_dimensions ORDER BY provider_id"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── provider_channels ─────────────────────────────────────────────────

    async def upsert_provider_channel(self, *, channel: str, label: str = "") -> None:
        """Idempotently upsert a ``provider_channels`` row keyed on ``channel``.

        Both ``channel`` and ``label`` are guarded by
        :func:`_reject_if_secret_shaped` before any SQL is built or executed.
        ``channel`` is NOT drawn from a closed vocabulary -- an unrecognized
        (but not secret-*shaped*) token, including a long/hyphenated one, is
        stored and read back unchanged, never rejected or coerced; see the
        module docstring's "why ``-``/``_`` are excluded from the
        high-entropy-run alphabet" section for why the guard no longer
        confuses a hyphenated slug for a high-entropy secret. Locked in by
        ``test_unknown_channel_token_never_raises_and_round_trips``.
        """
        _reject_if_secret_shaped(channel, field="channel")
        _reject_if_secret_shaped(label, field="label")
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                INSERT INTO provider_channels (
                    channel, label, first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel) DO UPDATE SET
                    label = excluded.label,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (channel, label, now, now, now, now),
            )
            await self.db.commit()

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def get_provider_channel(self, channel: str) -> dict[str, Any] | None:
        cursor = await self.db.execute(
            "SELECT * FROM provider_channels WHERE channel = ?", (channel,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_provider_channels(self) -> list[dict[str, Any]]:
        cursor = await self.db.execute(
            "SELECT * FROM provider_channels ORDER BY channel"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── provider_credentials ─────────────────────────────────────────────

    async def upsert_provider_credential(
        self,
        *,
        channel: str,
        credential_name: str,
        provider_id: str = "",
    ) -> None:
        """Idempotently upsert a ``provider_credentials`` row keyed on
        ``(channel, credential_name)``.

        ``channel``, ``credential_name``, and ``provider_id`` are all guarded
        by :func:`_reject_if_secret_shaped` before any SQL is built -- a
        secret-shaped value in ANY of the three raises ``ValueError`` and
        nothing is written. Never sets ``rotated_from_id`` /
        ``rotation_declared_at`` / ``rotation_declared_by`` -- those default
        to NULL on insert and are left untouched on update; the only method
        that ever writes them is :meth:`declare_rotation`.
        """
        _reject_if_secret_shaped(channel, field="channel")
        _reject_if_secret_shaped(credential_name, field="credential_name")
        _reject_if_secret_shaped(provider_id, field="provider_id")
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                INSERT INTO provider_credentials (
                    channel, credential_name, provider_id,
                    first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel, credential_name) DO UPDATE SET
                    provider_id = excluded.provider_id,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (channel, credential_name, provider_id, now, now, now, now),
            )
            await self.db.commit()

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def get_provider_credential(
        self, channel: str, credential_name: str
    ) -> dict[str, Any] | None:
        cursor = await self.db.execute(
            "SELECT * FROM provider_credentials WHERE channel = ? AND credential_name = ?",
            (channel, credential_name),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_provider_credentials(self) -> list[dict[str, Any]]:
        cursor = await self.db.execute(
            "SELECT * FROM provider_credentials ORDER BY channel, credential_name"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def declare_rotation(
        self,
        *,
        channel: str,
        predecessor_credential_name: str,
        successor_credential_name: str,
        declared_by: str = "",
    ) -> None:
        """Declare that *successor_credential_name* was rotated FROM
        *predecessor_credential_name* on *channel* (M2).

        See the module docstring's "Rotation lineage -- declare path (M2)"
        section for the full validation contract (predecessor/successor must
        exist, no self-reference, no cycle, idempotent re-declare of the same
        pointer, conflicting re-declare rejected) -- enforced by
        :func:`_validate_declare_rotation`, shared with
        :class:`PostgresProviderDimensionsRepository`.

        ``channel``, ``predecessor_credential_name``,
        ``successor_credential_name``, and ``declared_by`` are all guarded by
        :func:`_reject_if_secret_shaped` before any SQL is built or any
        validation lookup runs.
        """
        _reject_if_secret_shaped(channel, field="channel")
        _reject_if_secret_shaped(
            predecessor_credential_name, field="predecessor_credential_name"
        )
        _reject_if_secret_shaped(
            successor_credential_name, field="successor_credential_name"
        )
        _reject_if_secret_shaped(declared_by, field="declared_by")

        async def _get_by_channel_name(ch: str, name: str) -> dict[str, Any] | None:
            return await self.get_provider_credential(ch, name)

        async def _get_by_id(credential_id: int) -> dict[str, Any] | None:
            cursor = await self.db.execute(
                "SELECT * FROM provider_credentials WHERE id = ?", (credential_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

        resolved = await _validate_declare_rotation(
            get_by_channel_name=_get_by_channel_name,
            get_by_id=_get_by_id,
            channel=channel,
            predecessor_name=predecessor_credential_name,
            successor_name=successor_credential_name,
        )
        if resolved is None:
            return  # idempotent re-declare of the exact same pointer: no-op
        successor_id, predecessor_id = resolved
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                UPDATE provider_credentials
                SET rotated_from_id = ?,
                    rotation_declared_at = ?,
                    rotation_declared_by = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (predecessor_id, now, declared_by, now, successor_id),
            )
            await self.db.commit()

        await retry_on_locked(_write, repo=_REPO_NAME)

    # ── backfill (M2-002) ────────────────────────────────────────────────

    async def backfill_provider_dimensions_from_sessions(
        self, project_id: str
    ) -> dict[str, int]:
        """Idempotently derive dimension rows from ``sessions`` (M2-002).

        This is a standalone backfill job, deliberately NOT run inside a DDL
        migration -- a long table scan inside ``sqlite_migrations.py`` /
        ``postgres_migrations.py`` would widen the known api/worker
        concurrent-migration race on the deployment node. Callers are the
        sync-engine phase-1 block (adjacent to
        ``backfill_ica_spend_attribution``) and the ``ccdash provider
        backfill`` CLI command for an on-demand run.

        See :func:`_run_provider_backfill` (shared with
        :class:`PostgresProviderDimensionsRepository`) for the full
        derivation/dedup/upsert/skip-on-poison contract.

        Uses ``SELECT DISTINCT`` over just the five columns the derivation
        actually consumes (``model``, ``platform_type``, ``launcher``,
        ``model_variant``, ``ica_key``) instead of materializing every
        ``sessions`` row for the project. Correctness-preserving: identity
        derivation (:func:`backend.model_identity.derive_provider_identity`)
        and the credential-key extraction below are pure functions of exactly
        these five columns, so any two rows that agree on all five produce
        the identical (provider_id, channel, credential_name) outputs -- the
        distinct row is interchangeable with either full source row for this
        job's purposes. On a project with tens of thousands of sessions but
        under 10 distinct provider/channel/credential combinations, this
        collapses an O(sessions) fetch to O(distinct combinations) per sync
        pass, which is what this repeats on every pass. See the module
        docstring's ``_run_provider_backfill`` doc for how these rows are
        deduped/upserted.
        """
        cursor = await self.db.execute(
            "SELECT DISTINCT model, platform_type, launcher, model_variant, ica_key "
            "FROM sessions WHERE project_id = ?",
            (project_id,),
        )
        rows = await cursor.fetchall()
        return await _run_provider_backfill(self, rows)


# ── PostgreSQL ────────────────────────────────────────────────────────────


class PostgresProviderDimensionsRepository:
    """asyncpg-backed writer/reader for the three provider dimension tables.

    Mirrors :class:`SqliteProviderDimensionsRepository`'s public interface
    exactly (every upsert, every read, and the backfill) -- see the module
    docstring's "guard-before-INSERT ordering" section for why the secret
    guard runs before any SQL is built on this backend specifically.
    """

    def __init__(self, db: Any) -> None:
        # db is an asyncpg.Connection or asyncpg.Pool
        self.db = db

    # ── provider_dimensions ──────────────────────────────────────────────

    async def upsert_provider_dimension(
        self,
        *,
        provider_id: str,
        provider_vendor: str = "",
        provider_surface: str = "",
        provider_channel: str = "",
        provider_label: str = "",
    ) -> None:
        # SECURITY: guard every field BEFORE building any SQL. Postgres'
        # UNIQUE-violation DETAIL line echoes the offending values (unlike
        # SQLite's, which names only the column) -- a secret-shaped value
        # that reached self.db.execute() and collided would leak through the
        # duplicate-key error itself. Guard first, always. Do not reorder
        # this ahead of the SQL build without re-reading the module
        # docstring's "guard-before-INSERT ordering" section. Every field,
        # including provider_channel, is guarded -- see the module
        # docstring's "why -/_ are excluded from the high-entropy-run
        # alphabet" section for why that no longer false-rejects legitimate
        # open-vocabulary channel tokens.
        _reject_if_secret_shaped(provider_id, field="provider_id")
        _reject_if_secret_shaped(provider_vendor, field="provider_vendor")
        _reject_if_secret_shaped(provider_surface, field="provider_surface")
        _reject_if_secret_shaped(provider_channel, field="provider_channel")
        _reject_if_secret_shaped(provider_label, field="provider_label")
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                INSERT INTO provider_dimensions (
                    provider_id, provider_vendor, provider_surface, provider_channel,
                    provider_label, first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT(provider_id) DO UPDATE SET
                    provider_vendor = excluded.provider_vendor,
                    provider_surface = excluded.provider_surface,
                    provider_channel = excluded.provider_channel,
                    provider_label = excluded.provider_label,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                provider_id,
                provider_vendor,
                provider_surface,
                provider_channel,
                provider_label,
                now,
                now,
                now,
                now,
            )

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def get_provider_dimension(self, provider_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM provider_dimensions WHERE provider_id = $1", provider_id
        )
        return dict(row) if row else None

    async def list_provider_dimensions(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM provider_dimensions ORDER BY provider_id")
        return [dict(row) for row in rows]

    # ── provider_channels ─────────────────────────────────────────────────

    async def upsert_provider_channel(self, *, channel: str, label: str = "") -> None:
        # SECURITY: see upsert_provider_dimension's comment -- guard before
        # any SQL is built, unconditionally, on this backend. Both fields
        # are guarded.
        _reject_if_secret_shaped(channel, field="channel")
        _reject_if_secret_shaped(label, field="label")
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                INSERT INTO provider_channels (
                    channel, label, first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT(channel) DO UPDATE SET
                    label = excluded.label,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                channel,
                label,
                now,
                now,
                now,
                now,
            )

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def get_provider_channel(self, channel: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM provider_channels WHERE channel = $1", channel
        )
        return dict(row) if row else None

    async def list_provider_channels(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT * FROM provider_channels ORDER BY channel")
        return [dict(row) for row in rows]

    # ── provider_credentials ─────────────────────────────────────────────

    async def upsert_provider_credential(
        self,
        *,
        channel: str,
        credential_name: str,
        provider_id: str = "",
    ) -> None:
        # SECURITY: see upsert_provider_dimension's comment -- this is the
        # highest-risk field set (credential_name most of all), guard first.
        # All three fields are guarded.
        _reject_if_secret_shaped(channel, field="channel")
        _reject_if_secret_shaped(credential_name, field="credential_name")
        _reject_if_secret_shaped(provider_id, field="provider_id")
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                INSERT INTO provider_credentials (
                    channel, credential_name, provider_id,
                    first_seen_at, last_seen_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT(channel, credential_name) DO UPDATE SET
                    provider_id = excluded.provider_id,
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                channel,
                credential_name,
                provider_id,
                now,
                now,
                now,
                now,
            )

        await retry_on_locked(_write, repo=_REPO_NAME)

    async def get_provider_credential(
        self, channel: str, credential_name: str
    ) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM provider_credentials WHERE channel = $1 AND credential_name = $2",
            channel,
            credential_name,
        )
        return dict(row) if row else None

    async def list_provider_credentials(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            "SELECT * FROM provider_credentials ORDER BY channel, credential_name"
        )
        return [dict(row) for row in rows]

    async def declare_rotation(
        self,
        *,
        channel: str,
        predecessor_credential_name: str,
        successor_credential_name: str,
        declared_by: str = "",
    ) -> None:
        """Declare that *successor_credential_name* was rotated FROM
        *predecessor_credential_name* on *channel* (M2), Postgres backend.

        See :class:`SqliteProviderDimensionsRepository.declare_rotation` and
        the module docstring's "Rotation lineage -- declare path (M2)"
        section for the full validation contract, shared via
        :func:`_validate_declare_rotation`.

        SECURITY: guard every field BEFORE building any SQL or running any
        lookup -- same guard-before-INSERT ordering rule as every other write
        method on this backend (Postgres' UNIQUE-violation DETAIL echoes
        offending values; SQLite's does not).
        """
        _reject_if_secret_shaped(channel, field="channel")
        _reject_if_secret_shaped(
            predecessor_credential_name, field="predecessor_credential_name"
        )
        _reject_if_secret_shaped(
            successor_credential_name, field="successor_credential_name"
        )
        _reject_if_secret_shaped(declared_by, field="declared_by")

        async def _get_by_channel_name(ch: str, name: str) -> dict[str, Any] | None:
            return await self.get_provider_credential(ch, name)

        async def _get_by_id(credential_id: int) -> dict[str, Any] | None:
            row = await self.db.fetchrow(
                "SELECT * FROM provider_credentials WHERE id = $1", credential_id
            )
            return dict(row) if row else None

        resolved = await _validate_declare_rotation(
            get_by_channel_name=_get_by_channel_name,
            get_by_id=_get_by_id,
            channel=channel,
            predecessor_name=predecessor_credential_name,
            successor_name=successor_credential_name,
        )
        if resolved is None:
            return  # idempotent re-declare of the exact same pointer: no-op
        successor_id, predecessor_id = resolved
        now = _now_iso()

        async def _write() -> None:
            await self.db.execute(
                """
                UPDATE provider_credentials
                SET rotated_from_id = $1,
                    rotation_declared_at = $2,
                    rotation_declared_by = $3,
                    updated_at = $4
                WHERE id = $5
                """,
                predecessor_id,
                now,
                declared_by,
                now,
                successor_id,
            )

        await retry_on_locked(_write, repo=_REPO_NAME)

    # ── backfill (M2-002) ────────────────────────────────────────────────

    async def backfill_provider_dimensions_from_sessions(
        self, project_id: str
    ) -> dict[str, int]:
        """Idempotently derive dimension rows from ``sessions`` (M2-002), Postgres backend.

        See :func:`_run_provider_backfill` (shared with
        :class:`SqliteProviderDimensionsRepository`) for the full
        derivation/dedup/upsert/skip-on-poison contract -- this method only
        fetches the raw session rows via asyncpg's ``$1``-placeholder
        convention and hands them to the shared loop.

        Uses ``SELECT DISTINCT`` over just the five columns the derivation
        actually consumes, for the same O(sessions) -> O(distinct
        combinations) reason documented on the SQLite sibling method.
        """
        rows = await self.db.fetch(
            "SELECT DISTINCT model, platform_type, launcher, model_variant, ica_key "
            "FROM sessions WHERE project_id = $1",
            project_id,
        )
        return await _run_provider_backfill(self, rows)


# ── Factory ───────────────────────────────────────────────────────────────


def get_provider_dimensions_repository(db: Any):
    """Return the correct provider-dimensions repository implementation for *db*.

    ``db`` is either an ``aiosqlite.Connection`` (SQLite backend) or an
    ``asyncpg.Pool`` / ``asyncpg.Connection`` (Postgres backend) -- the same
    ``Union[aiosqlite.Connection, asyncpg.Pool]`` contract
    ``SyncEngine.__init__`` already carries for every other repository it
    constructs (see ``get_session_repository`` and friends in
    ``backend/db/factory.py``). Always returns a repository -- there is no
    supported backend this feature does not cover, so callers should not
    guard the result for ``None``.
    """
    if isinstance(db, aiosqlite.Connection):
        return SqliteProviderDimensionsRepository(db)
    return PostgresProviderDimensionsRepository(db)


__all__ = [
    "SqliteProviderDimensionsRepository",
    "PostgresProviderDimensionsRepository",
    "get_provider_dimensions_repository",
    "_reject_if_secret_shaped",
    "_looks_like_secret",
]
