"""Features API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.models import Feature
from backend.parsers.features import (
    scan_features,
    resolve_file_for_feature,
    resolve_file_for_phase,
)
from backend.parsers.status_writer import update_frontmatter_field, update_task_in_frontmatter
from backend.project_manager import project_manager

features_router = APIRouter(prefix="/api/features", tags=["features"])

# ── Request models ──────────────────────────────────────────────────

class StatusUpdateRequest(BaseModel):
    status: str  # backlog | in-progress | review | done


# ── Status value mapping (frontend values → frontmatter values) ─────

_REVERSE_STATUS = {
    "done": "completed",
    "in-progress": "in-progress",
    "review": "review",
    "backlog": "draft",
}


# ── GET endpoints ───────────────────────────────────────────────────

@features_router.get("", response_model=list[Feature])
def list_features():
    """Return all discovered features (phases included, tasks omitted for perf)."""
    _, docs_dir, progress_dir = project_manager.get_active_paths()
    all_features = scan_features(docs_dir, progress_dir)

    # Strip task details from phases for the list endpoint
    lite: list[Feature] = []
    for f in all_features:
        f_copy = f.model_copy()
        f_copy.phases = [
            p.model_copy(update={"tasks": []}) for p in f_copy.phases
        ]
        lite.append(f_copy)
    return lite


@features_router.get("/{feature_id}", response_model=Feature)
def get_feature(feature_id: str):
    """Return full feature detail including phases and tasks."""
    _, docs_dir, progress_dir = project_manager.get_active_paths()
    all_features = scan_features(docs_dir, progress_dir)

    for f in all_features:
        if f.id == feature_id:
            return f

    raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")


# ── PATCH endpoints ─────────────────────────────────────────────────

@features_router.patch("/{feature_id}/status", response_model=Feature)
def update_feature_status(feature_id: str, req: StatusUpdateRequest):
    """Update a feature's top-level status (writes to PRD or impl plan)."""
    _, docs_dir, progress_dir = project_manager.get_active_paths()

    file_path = resolve_file_for_feature(feature_id, docs_dir, progress_dir)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"No file found for feature '{feature_id}'")

    # Map frontend status to frontmatter value
    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    update_frontmatter_field(file_path, "status", fm_status)

    # Re-read and return the updated feature
    all_features = scan_features(docs_dir, progress_dir)
    for f in all_features:
        if f.id == feature_id:
            return f

    raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found after update")


@features_router.patch("/{feature_id}/phases/{phase_id}/status", response_model=Feature)
def update_phase_status(feature_id: str, phase_id: str, req: StatusUpdateRequest):
    """Update a specific phase's status (writes to the progress file)."""
    _, docs_dir, progress_dir = project_manager.get_active_paths()

    file_path = resolve_file_for_phase(feature_id, phase_id, progress_dir)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No progress file found for feature '{feature_id}', phase '{phase_id}'",
        )

    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    update_frontmatter_field(file_path, "status", fm_status)

    # Re-read and return the updated feature
    all_features = scan_features(docs_dir, progress_dir)
    for f in all_features:
        if f.id == feature_id:
            return f

    raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found after update")


@features_router.patch("/{feature_id}/phases/{phase_id}/tasks/{task_id}/status", response_model=Feature)
def update_task_status(feature_id: str, phase_id: str, task_id: str, req: StatusUpdateRequest):
    """Update a single task's status within a phase's progress file."""
    _, docs_dir, progress_dir = project_manager.get_active_paths()

    file_path = resolve_file_for_phase(feature_id, phase_id, progress_dir)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"No progress file found for feature '{feature_id}', phase '{phase_id}'",
        )

    fm_status = _REVERSE_STATUS.get(req.status, req.status)
    updated = update_task_in_frontmatter(file_path, task_id, "status", fm_status)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found in progress file",
        )

    # Re-read and return the updated feature
    all_features = scan_features(docs_dir, progress_dir)
    for f in all_features:
        if f.id == feature_id:
            return f

    raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found after update")
