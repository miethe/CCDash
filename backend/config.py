"""CCDash Backend Configuration."""
import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

# Project root (one level up from backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default data paths (relative to project root)
DATA_DIR = PROJECT_ROOT / "examples" / "skillmeat"
SESSIONS_DIR = DATA_DIR / "claude-sessions"
DOCUMENTS_DIR = DATA_DIR / "project_plans"
PROGRESS_DIR = DATA_DIR / "progress"

# Database
DB_PATH = os.getenv("CCDASH_DB_PATH", ".ccdash.db")
DB_BACKEND = os.getenv("CCDASH_DB_BACKEND", "sqlite")
DATABASE_URL = os.getenv("CCDASH_DATABASE_URL", "postgresql://user:password@localhost/ccdash")
LINKING_LOGIC_VERSION = os.getenv("CCDASH_LINKING_LOGIC_VERSION", "1")
SESSION_MAPPINGS_JSON = os.getenv("CCDASH_SESSION_MAPPINGS_JSON", "")
SESSION_MAPPINGS_FILE = os.getenv("CCDASH_SESSION_MAPPINGS_FILE", "")
OTEL_ENABLED = _env_bool("CCDASH_OTEL_ENABLED", False)
OTEL_ENDPOINT = os.getenv("CCDASH_OTEL_ENDPOINT", "http://localhost:4318")
OTEL_SERVICE_NAME = os.getenv("CCDASH_OTEL_SERVICE_NAME", "ccdash-backend")
PROM_PORT = _env_int("CCDASH_PROM_PORT", 9464)

# Feature flags
CCDASH_TEST_VISUALIZER_ENABLED = _env_bool("CCDASH_TEST_VISUALIZER_ENABLED", False)
CCDASH_INTEGRITY_SIGNALS_ENABLED = _env_bool("CCDASH_INTEGRITY_SIGNALS_ENABLED", False)
CCDASH_LIVE_TEST_UPDATES_ENABLED = _env_bool("CCDASH_LIVE_TEST_UPDATES_ENABLED", False)
CCDASH_SEMANTIC_MAPPING_ENABLED = _env_bool("CCDASH_SEMANTIC_MAPPING_ENABLED", False)
CCDASH_SKILLMEAT_INTEGRATION_ENABLED = _env_bool("CCDASH_SKILLMEAT_INTEGRATION_ENABLED", True)
CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED = _env_bool("CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED", True)
CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED = _env_bool("CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED", True)
CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED = _env_bool("CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED", True)
CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED = _env_bool("CCDASH_SESSION_BLOCK_INSIGHTS_ENABLED", True)
CCDASH_PROJECT_ROOT = os.getenv("CCDASH_PROJECT_ROOT", str(PROJECT_ROOT)).strip() or str(PROJECT_ROOT)
TEST_RESULTS_DIR = os.getenv("CCDASH_TEST_RESULTS_DIR", "").strip()
INTEGRATIONS_SETTINGS_FILE = Path(
    os.getenv("CCDASH_INTEGRATIONS_SETTINGS_FILE", str(PROJECT_ROOT / ".ccdash-integrations.json"))
).expanduser()
REPO_WORKSPACE_CACHE_DIR = Path(
    os.getenv("CCDASH_REPO_WORKSPACE_CACHE_DIR", str(PROJECT_ROOT / ".ccdash-repo-cache"))
).expanduser()

# Telemetry exporter
CCDASH_TELEMETRY_EXPORT_ENABLED = _env_bool("CCDASH_TELEMETRY_EXPORT_ENABLED", False)
CCDASH_SAM_ENDPOINT = os.getenv("CCDASH_SAM_ENDPOINT", "").strip()
CCDASH_SAM_API_KEY = os.getenv("CCDASH_SAM_API_KEY", "").strip()
CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS = _env_int("CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS", 900)
CCDASH_TELEMETRY_EXPORT_BATCH_SIZE = _env_int("CCDASH_TELEMETRY_EXPORT_BATCH_SIZE", 50)
CCDASH_TELEMETRY_EXPORT_TIMEOUT_SECONDS = _env_int("CCDASH_TELEMETRY_EXPORT_TIMEOUT_SECONDS", 30)
CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE = _env_int("CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE", 10000)
CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS = _env_int("CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS", 30)
CCDASH_TELEMETRY_ALLOW_INSECURE = _env_bool("CCDASH_TELEMETRY_ALLOW_INSECURE", False)
CCDASH_VERSION = os.getenv("CCDASH_VERSION", "0.1.0").strip() or "0.1.0"


class TelemetryExporterConfig(BaseModel):
    """Validated telemetry exporter runtime configuration."""

    enabled: bool = False
    sam_endpoint: str = ""
    sam_api_key: str = ""
    interval_seconds: int = Field(default=900, ge=60)
    batch_size: int = Field(default=50, ge=1, le=500)
    timeout_seconds: int = Field(default=30, ge=1)
    max_queue_size: int = Field(default=10000, ge=1)
    queue_retention_days: int = Field(default=30, ge=1)
    allow_insecure: bool = False
    ccdash_version: str = Field(default="0.1.0", min_length=1)

    @property
    def configured(self) -> bool:
        return bool(self.sam_endpoint and self.sam_api_key)

    @model_validator(mode="after")
    def validate_enabled_requirements(self) -> "TelemetryExporterConfig":
        if self.enabled and not self.sam_endpoint:
            raise ValueError("CCDASH_SAM_ENDPOINT is required when telemetry export is enabled")
        if self.enabled and not self.sam_api_key:
            raise ValueError("CCDASH_SAM_API_KEY is required when telemetry export is enabled")
        return self


TELEMETRY_EXPORTER_CONFIG = TelemetryExporterConfig(
    enabled=CCDASH_TELEMETRY_EXPORT_ENABLED,
    sam_endpoint=CCDASH_SAM_ENDPOINT,
    sam_api_key=CCDASH_SAM_API_KEY,
    interval_seconds=CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS,
    batch_size=CCDASH_TELEMETRY_EXPORT_BATCH_SIZE,
    timeout_seconds=CCDASH_TELEMETRY_EXPORT_TIMEOUT_SECONDS,
    max_queue_size=CCDASH_TELEMETRY_EXPORT_MAX_QUEUE_SIZE,
    queue_retention_days=CCDASH_TELEMETRY_QUEUE_RETENTION_DAYS,
    allow_insecure=CCDASH_TELEMETRY_ALLOW_INSECURE,
    ccdash_version=CCDASH_VERSION,
)

# Startup sync tuning
STARTUP_SYNC_DELAY_SECONDS = _env_int("CCDASH_STARTUP_SYNC_DELAY_SECONDS", 2)
STARTUP_SYNC_LIGHT_MODE = _env_bool("CCDASH_STARTUP_SYNC_LIGHT_MODE", True)
STARTUP_DEFERRED_REBUILD_LINKS = _env_bool("CCDASH_STARTUP_DEFERRED_REBUILD_LINKS", True)
STARTUP_DEFERRED_REBUILD_DELAY_SECONDS = _env_int("CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS", 45)
STARTUP_DEFERRED_CAPTURE_ANALYTICS = _env_bool("CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS", False)
ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = _env_int("CCDASH_ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 900)
CCDASH_LIVE_REPLAY_BUFFER_SIZE = _env_int("CCDASH_LIVE_REPLAY_BUFFER_SIZE", 200)
CCDASH_LIVE_HEARTBEAT_SECONDS = _env_int("CCDASH_LIVE_HEARTBEAT_SECONDS", 15)
CCDASH_LIVE_MAX_PENDING_EVENTS = _env_int("CCDASH_LIVE_MAX_PENDING_EVENTS", 100)

# Server settings
HOST = os.getenv("CCDASH_HOST", "0.0.0.0")
PORT = int(os.getenv("CCDASH_PORT", "8000"))

# CORS
FRONTEND_ORIGIN = os.getenv("CCDASH_FRONTEND_ORIGIN", "http://localhost:3000")
