"""Project Manager to handle project persistence and context switching."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from backend import config
from backend.application.ports.core import ProjectBinding
from backend.models import Project, ProjectDisplayConfig, ProjectDisplayMetadata
from backend.services.project_paths.models import ResolvedProjectPath, ResolvedProjectPaths
from backend.services.project_paths.resolver import ProjectPathResolver
from backend.services.test_config import normalize_project_test_config

logger = logging.getLogger("ccdash")

# ---------------------------------------------------------------------------
# Display-config fallback helpers
# ---------------------------------------------------------------------------

# A fixed palette of visually distinct hex colors.  The palette index is
# derived deterministically from sha256(project_id) so the same project id
# always maps to the same color across runs and restarts.
_DISPLAY_COLOR_PALETTE: tuple[str, ...] = (
    "#6366f1",  # indigo
    "#22c55e",  # green
    "#f59e0b",  # amber
    "#ec4899",  # pink
    "#14b8a6",  # teal
    "#f97316",  # orange
    "#8b5cf6",  # violet
    "#06b6d4",  # cyan
    "#ef4444",  # red
    "#84cc16",  # lime
    "#a855f7",  # purple
    "#0ea5e9",  # sky
)

_DEFAULT_GROUP = "default"


def _stable_hash_index(project_id: str, palette_len: int) -> int:
    """Return a deterministic index into a palette using sha256(project_id)."""
    digest = hashlib.sha256(project_id.encode()).digest()
    # Take the first 4 bytes as a big-endian unsigned int.
    value = int.from_bytes(digest[:4], "big")
    return value % palette_len


def resolve_display_metadata(project: Project) -> ProjectDisplayMetadata:
    """Merge persisted ``project.display`` config over deterministic fallbacks.

    Guarantees that the returned ``ProjectDisplayMetadata`` always has
    non-None ``color`` and ``group`` values regardless of whether the project
    has a stored ``ProjectDisplayConfig``.  ``sort_order`` and
    ``label_override`` are passed through as-is (may be None).

    Algorithm for deterministic fallbacks:
    - ``color``:   palette[ sha256(project.id)[:4] % len(palette) ]
    - ``group``:   "default"
    - ``sort_order``:     None  (frontend sorts alphabetically by project name)
    - ``label_override``: None  (frontend uses project.name)

    Calling this function twice with the same project always returns identical
    values (pure / side-effect-free).
    """
    cfg: ProjectDisplayConfig = project.display or ProjectDisplayConfig()

    color = cfg.color or _DISPLAY_COLOR_PALETTE[
        _stable_hash_index(project.id, len(_DISPLAY_COLOR_PALETTE))
    ]
    group = cfg.group or _DEFAULT_GROUP
    sort_order = cfg.sortOrder  # may be None — caller decides ordering
    label_override = cfg.labelOverride  # may be None

    return ProjectDisplayMetadata(
        color=color,
        group=group,
        sort_order=sort_order,
        label_override=label_override,
    )


class ProjectManager:
    """Manages project configurations and active context."""

    def __init__(self, storage_path: Path, *, path_resolver: ProjectPathResolver | None = None):
        self.storage_path = storage_path
        self._projects: dict[str, Project] = {}
        self._active_project_id: Optional[str] = None
        self._path_resolver = path_resolver or ProjectPathResolver()
        migrated = self._load()

        # Ensure at least one default project exists if empty
        if not self._projects:
            self._create_default_project()
        elif migrated:
            self._save()

        # Set active project if not set
        if self._active_project_id is None or self._active_project_id not in self._projects:
            if self._projects:
                # Set the first one as active
                first_id = next(iter(self._projects))
                self.set_active_project(first_id)

    def _load(self) -> bool:
        """Load projects from JSON storage."""
        if not self.storage_path.exists():
            return False

        migrated = False
        try:
            content = self.storage_path.read_text()
            if not content.strip():
                return False
            data = json.loads(content)
            self._active_project_id = data.get("activeProjectId")
            for p_data in data.get("projects", []):
                try:
                    if isinstance(p_data, dict):
                        if "skillMeat" not in p_data:
                            migrated = True
                        if "pathConfig" not in p_data:
                            migrated = True
                        skillmeat = p_data.get("skillMeat")
                        if isinstance(skillmeat, dict) and "workspaceId" in skillmeat and "collectionId" not in skillmeat:
                            migrated = True
                    p = Project(**p_data)
                    normalize_project_test_config(p, legacy_test_results_dir=config.TEST_RESULTS_DIR)
                    self._projects[p.id] = p
                except Exception as e:
                    logger.error(f"Failed to load project: {e}")
        except Exception as e:
            logger.error(f"Failed to load projects file: {e}")
        return migrated

    def _save(self):
        """Save projects to JSON storage."""
        data = {
            "activeProjectId": self._active_project_id,
            "projects": [p.model_dump() for p in self._projects.values()]
        }
        self.storage_path.write_text(json.dumps(data, indent=2))

    def _create_default_project(self):
        """Create the default SkillMeat example project."""
        default_project = Project(
            id="default-skillmeat",
            name="SkillMeat Example",
            path=str(config.DATA_DIR),  # Using the existing example path
            description="Default example project demonstrating CCDash capabilities.",
            repoUrl="",
            agentPlatforms=["Claude Code"],
            planDocsPath="project_plans"  # Relative to project root
        )
        self.add_project(default_project)
        self._active_project_id = default_project.id
        self._save()

    def list_projects(self) -> list[Project]:
        return list(self._projects.values())

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def add_project(self, project: Project):
        normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
        self._projects[project.id] = project
        self._save()

    def update_project(self, project_id: str, project: Project):
        """Update an existing project in-place."""
        if project_id not in self._projects:
            raise ValueError(f"Project {project_id} not found")
        project.id = project_id  # ensure ID is preserved
        normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
        self._projects[project_id] = project
        self._save()
        logger.info(f"Updated project: {project.name}")

    def set_active_project(self, project_id: str):
        if project_id in self._projects:
            self._active_project_id = project_id
            self._save()
            logger.info(f"Switched active project to: {self._projects[project_id].name}")
        else:
            raise ValueError(f"Project {project_id} not found")

    def get_active_project(self) -> Optional[Project]:
        if self._active_project_id:
            return self._projects.get(self._active_project_id)
        return None

    def resolve_project_binding(
        self,
        project_id: str | None = None,
        *,
        allow_active_fallback: bool = True,
        refresh: bool = False,
    ) -> ProjectBinding | None:
        requested_project_id = str(project_id or "").strip() or None
        if requested_project_id is not None:
            project = self.get_project(requested_project_id)
            source = "explicit"
        elif allow_active_fallback:
            project = self.get_active_project()
            source = "active"
        else:
            project = None
            source = "explicit"

        if project is None:
            return None

        return ProjectBinding(
            project=project,
            paths=self.resolve_project_paths(project, refresh=refresh),
            source=source,
            requested_project_id=requested_project_id,
        )

    def resolve_project_paths(self, project: Project, *, refresh: bool = False) -> ResolvedProjectPaths:
        if project.id == "default-skillmeat":
            root = ResolvedProjectPath(
                field="root",
                source_kind="filesystem",
                requested=project.pathConfig.root,
                path=config.DATA_DIR.resolve(strict=False),
                diagnostic="Resolved from the bundled example workspace.",
            )
            return ResolvedProjectPaths(
                project_id=project.id,
                root=root,
                plan_docs=ResolvedProjectPath(
                    field="plan_docs",
                    source_kind="project_root",
                    requested=project.pathConfig.planDocs,
                    path=config.DOCUMENTS_DIR.resolve(strict=False),
                    diagnostic="Resolved from the bundled example workspace.",
                ),
                sessions=ResolvedProjectPath(
                    field="sessions",
                    source_kind="filesystem",
                    requested=project.pathConfig.sessions,
                    path=config.SESSIONS_DIR.resolve(strict=False),
                    diagnostic="Resolved from the bundled example workspace.",
                ),
                progress=ResolvedProjectPath(
                    field="progress",
                    source_kind="project_root",
                    requested=project.pathConfig.progress,
                    path=config.PROGRESS_DIR.resolve(strict=False),
                    diagnostic="Resolved from the bundled example workspace.",
                ),
            )
        return self._path_resolver.resolve_project(project, refresh=refresh)

    def get_active_path_bundle(self, *, refresh: bool = False) -> ResolvedProjectPaths:
        project = self.get_active_project()
        if not project:
            fallback = Project(
                id="config-fallback",
                name="Config Fallback",
                path=str(config.DATA_DIR),
                planDocsPath=str(config.DOCUMENTS_DIR.relative_to(config.DATA_DIR)),
                sessionsPath=str(config.SESSIONS_DIR),
                progressPath=str(config.PROGRESS_DIR.relative_to(config.DATA_DIR)),
            )
            return self._path_resolver.resolve_project(fallback, refresh=refresh)
        return self.resolve_project_paths(project, refresh=refresh)

    def get_project_root(self, project: Project, *, refresh: bool = False) -> Path:
        if not hasattr(project, "pathConfig"):
            return Path(getattr(project, "path", config.DATA_DIR)).expanduser().resolve(strict=False)
        return self.resolve_project_paths(project, refresh=refresh).root.path

    def get_active_paths(self) -> tuple[Path, Path, Path]:
        """Return (sessions_dir, documents_dir, progress_dir) for the active project."""
        bundle = self.get_active_path_bundle()
        return bundle.as_tuple()


# Global instance initialized with projects.json in backend root
project_manager = ProjectManager(config.PROJECT_ROOT / "projects.json")
