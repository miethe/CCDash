"""Project Manager to handle project persistence and context switching."""
from __future__ import annotations

import json
import logging
import uuid
import os
from pathlib import Path
from typing import Optional

from backend import config
from backend.models import Project
from backend.services.test_config import normalize_project_test_config

logger = logging.getLogger("ccdash")


class ProjectManager:
    """Manages project configurations and active context."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self._projects: dict[str, Project] = {}
        self._active_project_id: Optional[str] = None
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

    def get_active_paths(self) -> tuple[Path, Path, Path]:
        """Return (sessions_dir, documents_dir, progress_dir) for the active project."""
        project = self.get_active_project()
        
        # Fallback to default config if no project is active (shouldn't happen)
        if not project:
            return config.SESSIONS_DIR, config.DOCUMENTS_DIR, config.PROGRESS_DIR

        # Use SkillMeat example paths explicitly for the default project
        if project.id == "default-skillmeat":
            return config.SESSIONS_DIR, config.DOCUMENTS_DIR, config.PROGRESS_DIR

        project_root = Path(project.path)

        # 1. Sessions — use project.sessionsPath if set, otherwise fall back to ~/.claude/sessions
        if project.sessionsPath and project.sessionsPath.strip():
            sessions_path = Path(project.sessionsPath)
        else:
            sessions_path = Path.home() / ".claude" / "sessions"

        # 2. Documents — relative to project root
        docs_path = project_root / project.planDocsPath

        # 3. Progress — use project.progressPath (relative to project root)
        progress_path = project_root / (project.progressPath or "progress")

        return sessions_path, docs_path, progress_path


# Global instance initialized with projects.json in backend root
project_manager = ProjectManager(config.PROJECT_ROOT / "projects.json")
