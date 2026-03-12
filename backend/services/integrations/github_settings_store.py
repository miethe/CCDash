from __future__ import annotations

import json
from pathlib import Path

from backend import config
from backend.models import (
    GitHubIntegrationSettings,
    GitHubIntegrationSettingsResponse,
    GitHubIntegrationSettingsUpdateRequest,
)
from backend.services.repo_workspaces.github_client import mask_token


class GitHubSettingsStore:
    def __init__(self, storage_path: Path | None = None):
        self.storage_path = (storage_path or config.INTEGRATIONS_SETTINGS_FILE).expanduser()

    def load(self) -> GitHubIntegrationSettings:
        data = self._read_all()
        payload = data.get("github")
        if isinstance(payload, dict):
            return GitHubIntegrationSettings.model_validate(payload)
        return GitHubIntegrationSettings(cacheRoot=str(config.REPO_WORKSPACE_CACHE_DIR))

    def save(self, request: GitHubIntegrationSettingsUpdateRequest) -> GitHubIntegrationSettings:
        current = self.load()
        token = str(request.token or "").strip()
        updated = GitHubIntegrationSettings(
            enabled=bool(request.enabled),
            provider="github",
            baseUrl=str(request.baseUrl or "https://github.com").strip() or "https://github.com",
            username=str(request.username or "git").strip() or "git",
            token=token or current.token,
            cacheRoot=str(request.cacheRoot or current.cacheRoot or config.REPO_WORKSPACE_CACHE_DIR).strip(),
            writeEnabled=bool(request.writeEnabled),
        )
        data = self._read_all()
        data["github"] = updated.model_dump()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return updated

    def to_response(self, settings: GitHubIntegrationSettings | None = None) -> GitHubIntegrationSettingsResponse:
        current = settings or self.load()
        return GitHubIntegrationSettingsResponse(
            enabled=bool(current.enabled),
            provider="github",
            baseUrl=str(current.baseUrl or "https://github.com"),
            username=str(current.username or "git"),
            tokenConfigured=bool(str(current.token or "").strip()),
            maskedToken=mask_token(current.token),
            cacheRoot=str(current.cacheRoot or config.REPO_WORKSPACE_CACHE_DIR),
            writeEnabled=bool(current.writeEnabled),
        )

    def _read_all(self) -> dict:
        if not self.storage_path.exists():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
