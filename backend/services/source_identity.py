"""Filesystem-derived source identity contract.

This module defines the Phase 1 contract for canonical source keys used by
later live-ingest hardening work. It intentionally does not wire the sync
engine or repositories yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal, NewType


SourceKey = NewType("SourceKey", str)
ProjectId = NewType("ProjectId", str)
SourceRootId = NewType("SourceRootId", str)

SourceArtifactKind = Literal["session", "document", "progress", "test", "unknown"]

SOURCE_KEY_SCHEME = "ccdash-source"
SOURCE_KEY_VERSION = "v1"


class SourceAliasBehavior(str, Enum):
    """How an observed path should be treated when resolving source identity."""

    COLLAPSE_TO_ROOT = "collapse_to_root"
    KEEP_OPAQUE = "keep_opaque"
    REJECT_ESCAPE = "reject_escape"


@dataclass(frozen=True, slots=True)
class SourceRootAlias:
    """Configured alias for the same logical filesystem root.

    Inputs:
        root_id: Stable root token scoped by project configuration, such as
            ``claude_home``, ``codex_home``, ``workspace``, or an optional
            mount slot id like ``extra_mount_1``.
        alias_path: Absolute host or container path for that root. Examples
            include ``/Users/miethe/.claude`` and ``/home/ccdash/.claude``.
        behavior: ``COLLAPSE_TO_ROOT`` means files below this alias may share
            source keys with other aliases for the same ``root_id``.

    Rollout constraint:
        Alias configuration must come from project/runtime registry data, not
        broad ad hoc suffix replacement. A container path and host path only
        collapse when they are explicit aliases for the same ``root_id``.
    """

    root_id: SourceRootId
    alias_path: PurePosixPath
    behavior: SourceAliasBehavior = SourceAliasBehavior.COLLAPSE_TO_ROOT


@dataclass(frozen=True, slots=True)
class SourceIdentityInput:
    """Observed filesystem source identity inputs.

    ``observed_path`` is the raw path seen by the active runtime. It may be a
    host path, container path, symlink-resolved path, or optional mount path.
    ``project_id`` is always part of the identity boundary so unrelated
    projects cannot collide when they share root ids or relative paths.
    """

    project_id: ProjectId
    observed_path: PurePosixPath
    artifact_kind: SourceArtifactKind
    runtime_label: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalSourceIdentity:
    """Resolved canonical source identity.

    Output format:
        Known-root keys use
        ``ccdash-source:v1/{project_id}/{artifact_kind}/{root_id}/{relative_path}``.
        Unknown or intentionally opaque paths use the same scheme with an
        opaque root token and a digest-like terminal component supplied by the
        future helper implementation.

    Alias behavior:
        Host/container aliases for the same configured root collapse to the
        same key. Unknown paths remain stable but do not collapse across roots
        or projects. Escapes such as ``..`` outside a known root must be
        rejected instead of normalized into a neighboring root.

    Rollout constraint:
        Persistence code should use ``source_key`` for lookup/write/delete
        boundaries while preserving ``observed_path`` or another display path
        for debugging and UI compatibility.
    """

    source_key: SourceKey
    project_id: ProjectId
    artifact_kind: SourceArtifactKind
    root_id: SourceRootId
    relative_path: PurePosixPath | None
    observed_path: PurePosixPath
    alias_behavior: SourceAliasBehavior


@dataclass(frozen=True, slots=True)
class SourceIdentityPolicy:
    """Pure policy bundle for resolving canonical source identity.

    Later implementation tasks will populate this from project registry paths,
    ``~/.claude`` and ``~/.codex`` roots, container home remaps, and optional
    runtime mount slots.
    """

    aliases: tuple[SourceRootAlias, ...] = field(default_factory=tuple)
    unknown_path_behavior: SourceAliasBehavior = SourceAliasBehavior.KEEP_OPAQUE


class SourceIdentityResolutionPending(NotImplementedError):
    """Raised while only the SRC-001 contract is implemented."""


def format_known_source_key(
    *,
    project_id: ProjectId,
    artifact_kind: SourceArtifactKind,
    root_id: SourceRootId,
    relative_path: PurePosixPath,
) -> SourceKey:
    """Format a canonical known-root source key.

    The caller must provide an already validated relative POSIX path. This
    helper is intentionally small and side-effect free so later tasks can reuse
    the contract without importing repository or runtime code.
    """

    relative = relative_path.as_posix().lstrip("/")
    return SourceKey(
        f"{SOURCE_KEY_SCHEME}:{SOURCE_KEY_VERSION}/"
        f"{project_id}/{artifact_kind}/{root_id}/{relative}"
    )


def resolve_source_identity(
    source: SourceIdentityInput,
    policy: SourceIdentityPolicy,
) -> CanonicalSourceIdentity:
    """Resolve an observed filesystem path to a canonical source identity.

    This is the pure API skeleton for SRC-002. It accepts only data inputs and a
    policy object, performs no filesystem I/O, and must stay deterministic.
    Behavior is deliberately pending in SRC-001 to avoid silently introducing
    repository semantics before the helper tests and sync boundaries are ready.
    """

    raise SourceIdentityResolutionPending(
        "SRC-001 defines the source identity contract only; SRC-002 implements resolution."
    )


__all__ = [
    "CanonicalSourceIdentity",
    "ProjectId",
    "SOURCE_KEY_SCHEME",
    "SOURCE_KEY_VERSION",
    "SourceAliasBehavior",
    "SourceArtifactKind",
    "SourceIdentityInput",
    "SourceIdentityPolicy",
    "SourceIdentityResolutionPending",
    "SourceKey",
    "SourceRootAlias",
    "SourceRootId",
    "format_known_source_key",
    "resolve_source_identity",
]
