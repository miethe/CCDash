"""Features API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models import Feature
from backend.parsers.features import scan_features
from backend.project_manager import project_manager

features_router = APIRouter(prefix="/api/features", tags=["features"])


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
