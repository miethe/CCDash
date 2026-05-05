"""Filesystem-derived source identity contract.

This module defines the Phase 1 contract for canonical source keys used by
later live-ingest hardening work. It intentionally does not wire the sync
engine or repositories yet.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Mapping, Literal, NewType


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

    relative = relative_path.as_posix().lstrip("/") or "."
    return SourceKey(
        f"{SOURCE_KEY_SCHEME}:{SOURCE_KEY_VERSION}/"
        f"{project_id}/{artifact_kind}/{root_id}/{relative}"
    )


def _normalize_posix_path(raw: str | PurePosixPath) -> PurePosixPath:
    text = os.path.expanduser(str(raw)).replace("\\", "/").strip()
    if not text:
        raise ValueError("source path cannot be empty")

    is_absolute = text.startswith("/")
    parts: list[str] = []
    for part in PurePosixPath(text).parts:
        if part in ("", "/", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
                continue
            if is_absolute:
                raise ValueError(f"source path escapes filesystem root: {raw}")
            parts.append(part)
            continue
        parts.append(part)

    prefix = "/" if is_absolute else ""
    normalized = prefix + "/".join(parts)
    if not normalized:
        normalized = "/" if is_absolute else "."
    return PurePosixPath(normalized)


def _path_relative_to(path: PurePosixPath, root: PurePosixPath) -> PurePosixPath | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def _opaque_source_key(
    *,
    project_id: ProjectId,
    artifact_kind: SourceArtifactKind,
    observed_path: PurePosixPath,
) -> SourceKey:
    digest = hashlib.sha256(observed_path.as_posix().encode("utf-8")).hexdigest()[:32]
    return SourceKey(
        f"{SOURCE_KEY_SCHEME}:{SOURCE_KEY_VERSION}/"
        f"{project_id}/{artifact_kind}/opaque/{digest}"
    )


def resolve_source_identity(
    source: SourceIdentityInput,
    policy: SourceIdentityPolicy,
) -> CanonicalSourceIdentity:
    """Resolve an observed filesystem path to a canonical source identity.

    The function performs lexical POSIX normalization only. It does not call
    ``Path.resolve()``, inspect symlinks, or touch the filesystem, so the same
    inputs produce the same source key in host and container runtimes.
    """

    observed_path = _normalize_posix_path(source.observed_path)
    aliases = sorted(
        policy.aliases,
        key=lambda alias: len(_normalize_posix_path(alias.alias_path).parts),
        reverse=True,
    )
    for alias in aliases:
        alias_path = _normalize_posix_path(alias.alias_path)
        relative_path = _path_relative_to(observed_path, alias_path)
        if relative_path is None:
            continue
        if alias.behavior == SourceAliasBehavior.REJECT_ESCAPE:
            raise ValueError(f"source path matched rejected alias root: {alias_path}")
        if alias.behavior == SourceAliasBehavior.KEEP_OPAQUE:
            break
        return CanonicalSourceIdentity(
            source_key=format_known_source_key(
                project_id=source.project_id,
                artifact_kind=source.artifact_kind,
                root_id=alias.root_id,
                relative_path=relative_path,
            ),
            project_id=source.project_id,
            artifact_kind=source.artifact_kind,
            root_id=alias.root_id,
            relative_path=relative_path,
            observed_path=observed_path,
            alias_behavior=alias.behavior,
        )

    if policy.unknown_path_behavior == SourceAliasBehavior.REJECT_ESCAPE:
        raise ValueError(f"source path is outside configured roots: {observed_path}")

    return CanonicalSourceIdentity(
        source_key=_opaque_source_key(
            project_id=source.project_id,
            artifact_kind=source.artifact_kind,
            observed_path=observed_path,
        ),
        project_id=source.project_id,
        artifact_kind=source.artifact_kind,
        root_id=SourceRootId("opaque"),
        relative_path=None,
        observed_path=observed_path,
        alias_behavior=SourceAliasBehavior.KEEP_OPAQUE,
    )


def _add_alias_pair(
    aliases: list[SourceRootAlias],
    *,
    root_id: str,
    first: str | None,
    second: str | None,
) -> None:
    seen: set[str] = {alias.alias_path.as_posix() for alias in aliases}
    for raw_path in (first, second):
        if raw_path is None or not str(raw_path).strip():
            continue
        alias_path = _normalize_posix_path(raw_path)
        alias_key = alias_path.as_posix()
        if alias_key in seen:
            continue
        seen.add(alias_key)
        aliases.append(
            SourceRootAlias(
                root_id=SourceRootId(root_id),
                alias_path=alias_path,
            )
        )


def source_identity_policy_from_env(
    env: Mapping[str, str] | None = None,
) -> SourceIdentityPolicy:
    """Build runtime mount aliases from CCDash container env variables.

    This convenience builder is deterministic and side-effect free aside from
    reading ``os.environ`` when no mapping is supplied. It mirrors
    ``deploy/runtime/compose.yaml`` mount pairs.
    """

    values = os.environ if env is None else env
    aliases: list[SourceRootAlias] = []
    _add_alias_pair(
        aliases,
        root_id="workspace",
        first=values.get("CCDASH_WORKSPACE_HOST_ROOT"),
        second=values.get("CCDASH_WORKSPACE_CONTAINER_ROOT"),
    )
    _add_alias_pair(
        aliases,
        root_id="claude_home",
        first=values.get("CCDASH_CLAUDE_HOME"),
        second=values.get("CCDASH_CLAUDE_CONTAINER_HOME"),
    )
    _add_alias_pair(
        aliases,
        root_id="codex_home",
        first=values.get("CCDASH_CODEX_HOME"),
        second=values.get("CCDASH_CODEX_CONTAINER_HOME"),
    )
    for slot in range(1, 7):
        _add_alias_pair(
            aliases,
            root_id=f"extra_mount_{slot}",
            first=values.get(f"CCDASH_EXTRA_MOUNT_{slot}_HOST"),
            second=values.get(f"CCDASH_EXTRA_MOUNT_{slot}_CONTAINER"),
        )
    return SourceIdentityPolicy(aliases=tuple(aliases))


__all__ = [
    "CanonicalSourceIdentity",
    "ProjectId",
    "SOURCE_KEY_SCHEME",
    "SOURCE_KEY_VERSION",
    "SourceAliasBehavior",
    "SourceArtifactKind",
    "SourceIdentityInput",
    "SourceIdentityPolicy",
    "SourceKey",
    "SourceRootAlias",
    "SourceRootId",
    "format_known_source_key",
    "resolve_source_identity",
    "source_identity_policy_from_env",
]
