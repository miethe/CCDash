from __future__ import annotations

from pathlib import Path

from backend.models import Project, ProjectPathReference
from backend.services.project_paths.models import ResolvedProjectPath
from backend.services.project_paths.providers.base import PathResolutionError


class FilesystemProjectPathProvider:
    def resolve(
        self,
        reference: ProjectPathReference,
        *,
        project: Project,
        refresh: bool = False,
    ) -> ResolvedProjectPath:
        _ = refresh
        raw_value = str(reference.filesystemPath or "").strip()
        if not raw_value and reference.field == "sessions":
            raw_value = str(Path.home() / ".claude" / "sessions")
        if not raw_value and reference.field == "root":
            # ``Project.path`` is the legacy mirror of the root reference (see
            # ``Project._derive_legacy_fields``).  A row whose stored pathConfig carries a
            # blank root but whose ``path`` column is populated must still resolve, rather
            # than raising on every watcher/reconcile tick (node_01M44GE8XNP7ZEA3PM1C2D7YGK).
            raw_value = str(getattr(project, "path", "") or "").strip()
        if not raw_value:
            raise PathResolutionError("missing_filesystem_path", f"Field '{reference.field}' requires a filesystem path.")

        candidate = Path(raw_value).expanduser()
        if not candidate.is_absolute():
            candidate = (Path(project.path).expanduser().resolve(strict=False) / candidate).resolve(strict=False)
        else:
            candidate = candidate.resolve(strict=False)

        return ResolvedProjectPath(
            field=reference.field,
            source_kind=reference.sourceKind,
            requested=reference,
            path=candidate,
            diagnostic="Resolved from filesystem path.",
        )
