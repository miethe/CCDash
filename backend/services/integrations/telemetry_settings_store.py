from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend import config
from backend.models import TelemetryExportSettings, TelemetryExportSettingsUpdateRequest


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetrySettingsStore:
    def __init__(self, storage_path: Path | None = None):
        self.storage_path = (storage_path or config.INTEGRATIONS_SETTINGS_FILE).expanduser()

    def load(self) -> TelemetryExportSettings:
        data = self._read_all()
        payload = data.get("telemetry_exporter")
        if isinstance(payload, dict):
            return TelemetryExportSettings.model_validate(payload)
        return TelemetryExportSettings()

    def save(self, request: TelemetryExportSettingsUpdateRequest) -> TelemetryExportSettings:
        updated = TelemetryExportSettings(
            enabled=bool(request.enabled),
            updatedAt=_now_iso(),
        )
        data = self._read_all()
        data["telemetry_exporter"] = updated.model_dump()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return updated

    def _read_all(self) -> dict:
        if not self.storage_path.exists():
            return {}
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}
