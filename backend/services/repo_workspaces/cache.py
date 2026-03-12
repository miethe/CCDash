from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from backend.models import GitRepoRef


def _slugify(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._").lower()
    return normalized or fallback


@dataclass(frozen=True)
class RepoWorkspacePaths:
    cache_root: Path
    repo_key: str
    branch_key: str
    workspace_dir: Path


class RepoWorkspaceCache:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root.expanduser()

    def paths_for(self, repo_ref: GitRepoRef) -> RepoWorkspacePaths:
        repo_slug = repo_ref.repoSlug or "repo"
        repo_hash = hashlib.sha1(str(repo_ref.repoUrl or repo_slug).encode("utf-8")).hexdigest()[:10]
        repo_key = f"{_slugify(repo_slug, fallback='repo')}-{repo_hash}"
        branch_key = _slugify(repo_ref.branch or "default", fallback="default")
        workspace_dir = self.cache_root / repo_key / branch_key
        return RepoWorkspacePaths(
            cache_root=self.cache_root,
            repo_key=repo_key,
            branch_key=branch_key,
            workspace_dir=workspace_dir,
        )
