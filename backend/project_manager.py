"""Project Manager to handle project persistence and context switching."""
from __future__ import annotations

import hashlib
import json
import logging
import os
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
# Seed project ids — computed at read-time, never persisted
# ---------------------------------------------------------------------------

# Projects whose ids belong to this set have is_seed=True on the returned
# Project model.  This is a model-computed field; there is no DB column.
# COLUMN_PARITY_DRIFT_ALLOWLIST: N/A — model-computed, not a DB column.
_SEED_PROJECT_IDS: frozenset[str] = frozenset({"default-skillmeat", "test-project-1"})


def _mark_seed(project: Project) -> Project:
    """Return *project* with ``is_seed`` set based on ``_SEED_PROJECT_IDS``."""
    project.is_seed = project.id in _SEED_PROJECT_IDS
    return project


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
        """Save projects to JSON storage atomically (write-then-replace)."""
        data = {
            "activeProjectId": self._active_project_id,
            "projects": [p.model_dump() for p in self._projects.values()]
        }
        tmp_path = self.storage_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(data, indent=2))
            os.replace(tmp_path, self.storage_path)
        except Exception as exc:
            logger.error(
                "Failed to save projects file %s (temp: %s): %s",
                self.storage_path,
                tmp_path,
                exc,
            )
            raise RuntimeError(
                f"Could not persist projects to {self.storage_path}: {exc}"
            ) from exc

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
        return [_mark_seed(p) for p in self._projects.values()]

    def get_project(self, project_id: str) -> Optional[Project]:
        project = self._projects.get(project_id)
        return _mark_seed(project) if project is not None else None

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


# ---------------------------------------------------------------------------
# DB-backed project manager (P3-001)
# ---------------------------------------------------------------------------

class DbProjectManager:
    """ProjectManager backed by the authoritative ``projects`` DB table.

    Strategy: **sync-over-DB with in-memory snapshot**.
    - A dedicated synchronous DB connection (sqlite3 or psycopg2) provides
      persistence without event-loop gymnastics.
    - An in-memory snapshot (``_projects``, ``_active_project_id``) is
      populated lazily on first use and refreshed after every write.
    - ``projects.json`` is used as: (a) one-time bootstrap import when the
      table is empty, (b) read-fallback when the DB is unavailable.
    - All public methods preserve the same sync signatures as
      ``ProjectManager`` so zero caller changes are required.

    Initialization is lazy: the DB is not touched until the first method call.
    No wiring in ``container.py`` is required.
    """

    def __init__(
        self,
        storage_path: Path,
        *,
        db_path: str | Path | None = None,
        db_dsn: str | None = None,
        db_backend: str | None = None,
        path_resolver: ProjectPathResolver | None = None,
    ) -> None:
        self.storage_path = storage_path
        self._path_resolver = path_resolver or ProjectPathResolver()
        # Determine backend
        self._db_backend = (db_backend or config.DB_BACKEND or "sqlite").lower()
        # Derive sync DB accessor parameters from config if not supplied
        from backend.db.connection import DB_PATH as _ASYNC_DB_PATH  # path shared with async layer
        self._db_path: str = str(db_path or _ASYNC_DB_PATH)
        self._db_dsn: str = db_dsn or config.DATABASE_URL
        # Repository (lazy)
        self._repo = None
        # In-memory snapshot (lazy – populated on first access)
        self._projects: dict[str, Project] | None = None
        self._active_project_id: str | None = None
        self._snapshot_loaded: bool = False

    # ------------------------------------------------------------------
    # Repository accessor (lazy init)
    # ------------------------------------------------------------------

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        if self._db_backend == "postgres":
            from backend.db.repositories.postgres.projects import PostgresProjectRepository
            self._repo = PostgresProjectRepository(self._db_dsn)
        else:
            from backend.db.repositories.projects import SqliteProjectRepository
            self._repo = SqliteProjectRepository(self._db_path)
        self._repo.ensure_table()
        return self._repo

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------

    def _ensure_snapshot(self) -> None:
        """Hydrate the in-memory snapshot on first use."""
        if self._snapshot_loaded:
            return
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        """Reload the in-memory snapshot from the DB (or JSON fallback)."""
        logger.info(
            "DbProjectManager: loading snapshot from DB (backend=%s)", self._db_backend
        )
        try:
            repo = self._get_repo()
            rows = repo.list_all()
        except Exception as exc:
            logger.warning(
                "DB unavailable (%s); falling back to projects.json", exc
            )
            self._load_snapshot_from_json()
            return

        if not rows:
            # DB is empty – bootstrap from JSON if it exists
            self._load_snapshot_from_json()
            if self._projects:
                # Persist the JSON projects into the DB
                self._flush_snapshot_to_db()
            else:
                self._create_default_project_in_snapshot()
                self._flush_snapshot_to_db()
            self._snapshot_loaded = True
            logger.info(
                "DbProjectManager: snapshot bootstrap complete "
                "(projects=%d, active=%s)",
                len(self._projects or {}),
                self._active_project_id,
            )
            return

        self._projects = {}
        self._active_project_id = None
        for row in rows:
            try:
                project = self._row_to_project(row)
                self._projects[project.id] = project
                if row.get("is_active"):
                    self._active_project_id = project.id
            except Exception as exc:
                logger.error("Failed to hydrate project from DB row: %s", exc)

        # If no active project is flagged in the DB, pick the first one
        if self._active_project_id is None and self._projects:
            self._active_project_id = next(iter(self._projects))

        self._snapshot_loaded = True
        logger.info(
            "DbProjectManager: snapshot loaded from DB "
            "(projects=%d, active=%s)",
            len(self._projects),
            self._active_project_id,
        )

    def _load_snapshot_from_json(self) -> None:
        """Populate _projects from projects.json (fallback/bootstrap path)."""
        self._projects = {}
        self._active_project_id = None
        if not self.storage_path.exists():
            return
        try:
            content = self.storage_path.read_text()
            if not content.strip():
                return
            data = json.loads(content)
            self._active_project_id = data.get("activeProjectId")
            for p_data in data.get("projects", []):
                try:
                    p = Project(**p_data)
                    normalize_project_test_config(p, legacy_test_results_dir=config.TEST_RESULTS_DIR)
                    self._projects[p.id] = p
                except Exception as exc:
                    logger.error("Failed to load project from JSON: %s", exc)
        except Exception as exc:
            logger.error("Failed to read projects.json: %s", exc)

    def _create_default_project_in_snapshot(self) -> None:
        default_project = Project(
            id="default-skillmeat",
            name="SkillMeat Example",
            path=str(config.DATA_DIR),
            description="Default example project demonstrating CCDash capabilities.",
            repoUrl="",
            agentPlatforms=["Claude Code"],
            planDocsPath="project_plans",
        )
        self._projects = {default_project.id: default_project}
        self._active_project_id = default_project.id

    def _flush_snapshot_to_db(self) -> None:
        """Write the current in-memory snapshot to the DB.

        On failure the exception is logged and re-raised so the caller knows
        the write did not complete.  Critically, ``_snapshot_loaded`` is NOT
        set to ``True`` by this method – only the caller may do that, and only
        after a successful flush.  This ensures that the next call to
        ``list_projects()`` or ``get_project()`` will retry the flush rather
        than silently serving stale/empty data (F-01).
        """
        if not self._projects:
            return
        logger.info(
            "DbProjectManager: flushing %d project(s) to DB (active=%s)",
            len(self._projects),
            self._active_project_id,
        )
        try:
            repo = self._get_repo()
            for project_id, project in self._projects.items():
                row = project.model_dump()
                row["is_active"] = (project_id == self._active_project_id)
                repo.upsert(row)
            if self._active_project_id:
                repo.set_active(self._active_project_id)
        except Exception as exc:
            logger.error(
                "DbProjectManager: flush to DB failed (snapshot_loaded will NOT be "
                "set; next access will retry): %s",
                exc,
            )
            raise
        logger.info(
            "DbProjectManager: flush to DB complete "
            "(projects=%d, active=%s)",
            len(self._projects),
            self._active_project_id,
        )

    def _invalidate_snapshot(self) -> None:
        """Mark snapshot stale so next access reloads from DB."""
        self._snapshot_loaded = False

    # ------------------------------------------------------------------
    # Import / export helpers (ADR-006 Option B)
    # ------------------------------------------------------------------

    @classmethod
    def import_from_json(
        cls,
        json_path: Path,
        *,
        db_path: str | Path | None = None,
        db_dsn: str | None = None,
        db_backend: str | None = None,
        manager: "DbProjectManager | None" = None,
    ) -> "DbProjectManager":
        """Additive upsert from *json_path* into the DB registry.

        Creates (or reuses) a ``DbProjectManager`` instance and upserts every
        project found in the JSON file.  Existing rows are updated in place;
        rows not present in the JSON are left untouched.  The active-project
        flag is set to the JSON ``activeProjectId`` if it refers to a project
        that exists in the DB after the import.

        Parameters
        ----------
        json_path:
            Path to a ``projects.json``-formatted file (same schema as
            ``export_to_json``).
        db_path / db_dsn / db_backend:
            Forwarded to ``DbProjectManager.__init__`` when *manager* is
            ``None``.
        manager:
            Optional pre-constructed ``DbProjectManager`` to import into.
            When supplied, *db_path* / *db_dsn* / *db_backend* are ignored.

        Returns
        -------
        The ``DbProjectManager`` instance that was written to.  Callers can
        immediately call ``list_projects()`` to inspect the imported state.
        """
        if manager is None:
            storage_path = json_path  # used as the fallback bootstrap path
            mgr: "DbProjectManager" = cls(
                storage_path,
                db_path=db_path,
                db_dsn=db_dsn,
                db_backend=db_backend,
            )
        else:
            mgr = manager

        if not json_path.exists():
            logger.warning("import_from_json: %s does not exist – nothing imported", json_path)
            return mgr

        try:
            content = json_path.read_text()
            if not content.strip():
                logger.warning("import_from_json: %s is empty – nothing imported", json_path)
                return mgr
            data = json.loads(content)
        except Exception as exc:
            logger.error("import_from_json: failed to read %s: %s", json_path, exc)
            return mgr

        active_id: str | None = data.get("activeProjectId")
        imported = 0
        for p_data in data.get("projects", []):
            try:
                project = Project(**p_data)
                normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
                # Ensure snapshot is loaded so we can upsert into live state too.
                mgr._ensure_snapshot()
                mgr._projects[project.id] = project  # type: ignore[index]
                row = project.model_dump()
                row["is_active"] = (project.id == active_id)
                mgr._get_repo().upsert(row)
                imported += 1
            except Exception as exc:
                logger.error("import_from_json: failed to import project %r: %s", p_data, exc)

        # Persist the active flag if the referenced project is now present.
        if active_id and active_id in (mgr._projects or {}):
            try:
                mgr._active_project_id = active_id
                mgr._get_repo().set_active(active_id)
            except Exception as exc:
                logger.error("import_from_json: failed to set active project %r: %s", active_id, exc)

        # Refresh snapshot so callers see the imported rows.
        mgr._snapshot_loaded = True
        logger.info("import_from_json: imported %d project(s) from %s", imported, json_path)
        return mgr

    def export_to_json(self, json_path: Path) -> None:
        """Write the current DB registry to *json_path* in ``projects.json`` format.

        The output is identical in structure to the file written by the legacy
        ``ProjectManager._save()`` method so the round-trip is lossless for all
        project fields.

        Parameters
        ----------
        json_path:
            Destination file path.  Written atomically (write-then-replace).
        """
        self._ensure_snapshot()
        data = {
            "activeProjectId": self._active_project_id,
            "projects": [p.model_dump() for p in (self._projects or {}).values()],
        }
        tmp_path = json_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(data, indent=2))
            os.replace(tmp_path, json_path)
        except Exception as exc:
            logger.error("export_to_json: failed to write %s: %s", json_path, exc)
            raise RuntimeError(f"Could not export projects to {json_path}: {exc}") from exc
        logger.info(
            "export_to_json: wrote %d project(s) to %s",
            len(self._projects or {}),
            json_path,
        )

    # ------------------------------------------------------------------
    # Row → Project conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_project(row: dict) -> Project:
        """Convert a flat DB row dict to a Project model instance."""
        # Re-map snake_case DB columns to the camelCase Project fields
        raw: dict = {
            "id": row["id"],
            "name": row["name"],
            "path": row.get("path", ""),
            "description": row.get("description", ""),
            "repoUrl": row.get("repo_url", ""),
            "agentPlatforms": row.get("agent_platforms_json") or ["Claude Code"],
            "planDocsPath": row.get("plan_docs_path", "docs/project_plans/"),
            "sessionsPath": row.get("sessions_path", ""),
            "progressPath": row.get("progress_path", "progress"),
        }
        path_cfg = row.get("path_config_json")
        if path_cfg:
            raw["pathConfig"] = path_cfg
        test_cfg = row.get("test_config_json")
        if test_cfg:
            raw["testConfig"] = test_cfg
        skillmeat = row.get("skillmeat_json")
        if skillmeat:
            raw["skillMeat"] = skillmeat
        display = row.get("display_json")
        if display:
            raw["display"] = display
        project = Project(**raw)
        normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
        return project

    # ------------------------------------------------------------------
    # Public WorkspaceRegistry-compatible interface (all sync)
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Phase 8 (T8-004): invalidate the cached snapshot so the next
        ``list_projects()`` re-reads the DB-authoritative registry (ADR-006).

        Used by the periodic reconcile job to pick up projects/directories added
        AFTER boot without requiring a server restart.  Cheap: only marks the
        snapshot stale; the actual reload happens lazily on next access.
        """
        self._invalidate_snapshot()

    def list_projects(self) -> list[Project]:
        self._ensure_snapshot()
        return [_mark_seed(p) for p in self._projects.values()]

    def get_project(self, project_id: str) -> Optional[Project]:
        self._ensure_snapshot()
        project = self._projects.get(project_id)
        return _mark_seed(project) if project is not None else None

    def add_project(self, project: Project) -> None:
        self._ensure_snapshot()
        normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
        self._projects[project.id] = project
        row = project.model_dump()
        row["is_active"] = (project.id == self._active_project_id)
        try:
            self._get_repo().upsert(row)
        except Exception as exc:
            logger.error("DB upsert failed for add_project: %s", exc)
        self._invalidate_snapshot()

    def update_project(self, project_id: str, project: Project) -> None:
        self._ensure_snapshot()
        if project_id not in self._projects:
            raise ValueError(f"Project {project_id} not found")
        project.id = project_id
        normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
        self._projects[project_id] = project
        row = project.model_dump()
        row["is_active"] = (project_id == self._active_project_id)
        try:
            self._get_repo().upsert(row)
        except Exception as exc:
            logger.error("DB upsert failed for update_project: %s", exc)
        self._invalidate_snapshot()
        logger.info("Updated project: %s", project.name)

    def set_active_project(self, project_id: str) -> None:
        self._ensure_snapshot()
        if project_id not in self._projects:
            raise ValueError(f"Project {project_id} not found")
        self._active_project_id = project_id
        try:
            self._get_repo().set_active(project_id)
        except Exception as exc:
            logger.error("DB set_active failed: %s", exc)
        self._invalidate_snapshot()
        logger.info("Switched active project to: %s", self._projects[project_id].name)

    def get_active_project(self) -> Optional[Project]:
        self._ensure_snapshot()
        if self._active_project_id:
            return self._projects.get(self._active_project_id)
        return None

    # ------------------------------------------------------------------
    # Path-resolution helpers (delegates to ProjectPathResolver, same as
    # ProjectManager – no behaviour change, just a copy of the logic)
    # ------------------------------------------------------------------

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
        bundle = self.get_active_path_bundle()
        return bundle.as_tuple()


# ---------------------------------------------------------------------------
# Global instances
# ---------------------------------------------------------------------------

# DB-backed global registry (P3-001 / ADR-006 Option B).
# This is the AUTHORITATIVE runtime registry — all production code must use
# db_project_manager.  Lazy: DB is not touched until the first method call,
# so tests that do not set CCDASH_DB_BACKEND=postgres still work without any
# extra wiring.
db_project_manager = DbProjectManager(config.PROJECTS_FILE)

# Legacy JSON-backed manager — RETAINED FOR BACKWARD COMPATIBILITY ONLY.
# T1-004 (ADR-006): this instance is no longer on the hot-path for any
# production request.  It exists so that:
#   1. Existing test patches targeting ``backend.project_manager.project_manager``
#      continue to resolve without import errors.
#   2. Modules that imported ``project_manager`` directly (routers, scripts)
#      have been updated to import ``db_project_manager`` instead (see T1-007
#      audit below and the per-module comments added by that task).
# DO NOT pass this instance as ``manager=`` in production code.  Use
# ``db_project_manager`` directly or let ``build_workspace_registry`` /
# ``build_core_ports`` resolve the DB-backed registry automatically.
project_manager = ProjectManager(config.PROJECTS_FILE)
