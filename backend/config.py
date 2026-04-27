"""CCDash Backend Configuration."""
import os
from pathlib import Path
from typing import Literal, Mapping

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


def _env_bool_from(environ: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# Project root (one level up from backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default data paths (relative to project root)
DATA_DIR = PROJECT_ROOT / "examples" / "skillmeat"
SESSIONS_DIR = DATA_DIR / "claude-sessions"
DOCUMENTS_DIR = DATA_DIR / "project_plans"
PROGRESS_DIR = DATA_DIR / "progress"

# Database
DEFAULT_DATABASE_URL = "postgresql://user:password@localhost/ccdash"
DB_PATH = os.getenv("CCDASH_DB_PATH", ".ccdash.db")
DB_BACKEND = os.getenv("CCDASH_DB_BACKEND", "sqlite")
DATABASE_URL = os.getenv("CCDASH_DATABASE_URL", DEFAULT_DATABASE_URL)
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
CCDASH_LAUNCH_PREP_ENABLED = _env_bool("CCDASH_LAUNCH_PREP_ENABLED", False)
CCDASH_PLANNING_CONTROL_PLANE_ENABLED = _env_bool("CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True)
CCDASH_FEATURE_SURFACE_V2_ENABLED = _env_bool("CCDASH_FEATURE_SURFACE_V2_ENABLED", True)
CCDASH_NEXT_RUN_PREVIEW_ENABLED = _env_bool("CCDASH_NEXT_RUN_PREVIEW_ENABLED", True)
INCREMENTAL_LINK_REBUILD_ENABLED = _env_bool("CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED", False)
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
CCDASH_SAM_ARTIFACT_TELEMETRY_ENABLED = _env_bool("CCDASH_SAM_ARTIFACT_TELEMETRY_ENABLED", False)
CCDASH_VERSION = os.getenv("CCDASH_VERSION", "0.1.0").strip() or "0.1.0"
CCDASH_API_BEARER_TOKEN_ENV = "CCDASH_API_BEARER_TOKEN"
CCDASH_WORKER_PROJECT_ID_ENV = "CCDASH_WORKER_PROJECT_ID"


StorageProfileName = Literal["local", "enterprise"]
StorageIsolationMode = Literal["dedicated", "schema", "tenant"]
RuntimeProfileName = Literal["local", "api", "worker", "test"]
DeploymentMode = Literal["local", "hosted"]
EnvironmentContractScope = Literal["shared", "api_only", "worker_only", "local_only"]
EnvironmentVariableStatus = Literal["configured", "default", "missing", "not_applicable"]


class StorageProfileConfig(BaseModel):
    """Operator-facing storage profile contract."""

    profile: StorageProfileName = "local"
    db_backend: str = "sqlite"
    database_url: str = ""
    filesystem_source_of_truth: bool = True
    shared_postgres_enabled: bool = False
    isolation_mode: StorageIsolationMode = "dedicated"
    schema_name: str = "ccdash"

    @property
    def hosted(self) -> bool:
        return self.profile == "enterprise"

    @property
    def compatibility_backend_env(self) -> str:
        return "CCDASH_DB_BACKEND"

    @property
    def compatibility_database_url_env(self) -> str:
        return "CCDASH_DATABASE_URL"

    @property
    def canonical_session_store(self) -> str:
        return "postgres" if self.profile == "enterprise" else "filesystem_cache"

    @property
    def database_url_uses_local_default(self) -> bool:
        value = self.database_url.strip()
        return not value or value == DEFAULT_DATABASE_URL

    @property
    def storage_mode(self) -> str:
        if self.profile == "enterprise" and self.shared_postgres_enabled:
            return "shared-enterprise"
        return self.profile

    @property
    def supported_isolation_modes(self) -> tuple[StorageIsolationMode, ...]:
        if self.storage_mode == "shared-enterprise":
            return ("schema", "tenant")
        return ("dedicated",)

    @model_validator(mode="after")
    def validate_contract(self) -> "StorageProfileConfig":
        if self.profile == "local" and self.db_backend != "sqlite":
            raise ValueError("local storage profile requires CCDASH_DB_BACKEND=sqlite")
        if self.profile == "enterprise" and self.db_backend != "postgres":
            raise ValueError("enterprise storage profile requires CCDASH_DB_BACKEND=postgres")
        if self.shared_postgres_enabled and self.profile != "enterprise":
            raise ValueError("shared Postgres is only supported for the enterprise storage profile")
        if self.shared_postgres_enabled and self.isolation_mode == "dedicated":
            raise ValueError("shared Postgres requires schema or tenant isolation")
        if self.isolation_mode not in self.supported_isolation_modes:
            allowed = ", ".join(self.supported_isolation_modes)
            raise ValueError(
                f"storage mode '{self.storage_mode}' only supports isolation modes: {allowed}"
            )
        return self


def resolve_storage_profile_config(environ: Mapping[str, str] | None = None) -> StorageProfileConfig:
    env = environ or os.environ
    db_backend = str(env.get("CCDASH_DB_BACKEND", "sqlite")).strip().lower() or "sqlite"
    requested_profile = str(env.get("CCDASH_STORAGE_PROFILE", "")).strip().lower()
    profile: StorageProfileName = "enterprise" if requested_profile == "enterprise" else "local"
    if not requested_profile:
        profile = "enterprise" if db_backend == "postgres" else "local"

    shared_postgres_enabled = _env_bool_from(env, "CCDASH_STORAGE_SHARED_POSTGRES", False)
    requested_isolation = str(env.get("CCDASH_STORAGE_ISOLATION_MODE", "")).strip().lower()
    if requested_isolation not in {"dedicated", "schema", "tenant"}:
        requested_isolation = "schema" if shared_postgres_enabled else "dedicated"

    filesystem_source_of_truth = profile == "local"
    if profile == "enterprise":
        filesystem_source_of_truth = _env_bool_from(env, "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED", False)

    schema_name = str(env.get("CCDASH_STORAGE_SCHEMA", "ccdash")).strip() or "ccdash"
    return StorageProfileConfig(
        profile=profile,
        db_backend=db_backend,
        database_url=str(env.get("CCDASH_DATABASE_URL", DATABASE_URL)).strip(),
        filesystem_source_of_truth=filesystem_source_of_truth,
        shared_postgres_enabled=shared_postgres_enabled,
        isolation_mode=requested_isolation,
        schema_name=schema_name,
    )


def resolve_api_bearer_token(environ: Mapping[str, str] | None = None) -> str:
    env = environ or os.environ
    return str(env.get(CCDASH_API_BEARER_TOKEN_ENV, "")).strip()


class WorkerBindingConfig(BaseModel):
    """Validated worker runtime binding configuration."""

    project_id: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.project_id)


def resolve_worker_binding_config(environ: Mapping[str, str] | None = None) -> WorkerBindingConfig:
    env = environ or os.environ
    return WorkerBindingConfig(
        project_id=str(env.get(CCDASH_WORKER_PROJECT_ID_ENV, "")).strip(),
    )


class RuntimeEnvironmentVariableContract(BaseModel):
    """One environment variable in the operator-facing runtime contract."""

    name: str
    scope: EnvironmentContractScope
    required: bool = False
    secret: bool = False
    status: EnvironmentVariableStatus = "not_applicable"
    notes: str = ""


class RuntimeEnvironmentContract(BaseModel):
    """Resolved environment/secrets contract for a runtime profile."""

    runtime_profile: RuntimeProfileName
    deployment_mode: DeploymentMode
    storage_profile: StorageProfileName
    shared: tuple[RuntimeEnvironmentVariableContract, ...] = ()
    api_only: tuple[RuntimeEnvironmentVariableContract, ...] = ()
    worker_only: tuple[RuntimeEnvironmentVariableContract, ...] = ()
    local_only: tuple[RuntimeEnvironmentVariableContract, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def required_variables(self) -> tuple[str, ...]:
        return tuple(
            entry.name
            for entry in self._entries()
            if entry.required and entry.status != "not_applicable"
        )

    @property
    def secret_variables(self) -> tuple[str, ...]:
        return tuple(
            entry.name
            for entry in self._entries()
            if entry.secret and entry.status != "not_applicable"
        )

    def as_runtime_metadata(self) -> dict[str, object]:
        return {
            "runtimeProfile": self.runtime_profile,
            "deploymentMode": self.deployment_mode,
            "storageProfile": self.storage_profile,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "requiredVariables": list(self.required_variables),
            "secretVariables": list(self.secret_variables),
            "shared": [entry.model_dump(mode="python") for entry in self.shared],
            "apiOnly": [entry.model_dump(mode="python") for entry in self.api_only],
            "workerOnly": [entry.model_dump(mode="python") for entry in self.worker_only],
            "localOnly": [entry.model_dump(mode="python") for entry in self.local_only],
        }

    def _entries(self) -> tuple[RuntimeEnvironmentVariableContract, ...]:
        return self.shared + self.api_only + self.worker_only + self.local_only


def _environment_status(
    environ: Mapping[str, str],
    name: str,
    *,
    default_when_missing: bool = False,
    active: bool = True,
) -> EnvironmentVariableStatus:
    if not active:
        return "not_applicable"
    value = str(environ.get(name, "")).strip()
    if value:
        return "configured"
    return "default" if default_when_missing else "missing"


def _build_env_contract_entry(
    *,
    name: str,
    scope: EnvironmentContractScope,
    environ: Mapping[str, str],
    required: bool = False,
    secret: bool = False,
    default_when_missing: bool = False,
    active: bool = True,
    notes: str,
) -> RuntimeEnvironmentVariableContract:
    return RuntimeEnvironmentVariableContract(
        name=name,
        scope=scope,
        required=required,
        secret=secret,
        status=_environment_status(
            environ,
            name,
            default_when_missing=default_when_missing,
            active=active,
        ),
        notes=notes,
    )


def resolve_runtime_environment_contract(
    runtime_profile: RuntimeProfileName,
    storage_profile: StorageProfileConfig,
    environ: Mapping[str, str] | None = None,
) -> RuntimeEnvironmentContract:
    env = environ or os.environ
    deployment_mode: DeploymentMode = "hosted" if runtime_profile in {"api", "worker"} else "local"
    hosted_runtime = deployment_mode == "hosted"
    hosted_storage = hosted_runtime and storage_profile.hosted
    worker_runtime = runtime_profile == "worker"
    api_runtime = runtime_profile == "api"

    shared = (
        _build_env_contract_entry(
            name="CCDASH_STORAGE_PROFILE",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Operator-facing storage posture selector; hosted runtimes should resolve to enterprise storage.",
        ),
        _build_env_contract_entry(
            name="CCDASH_DB_BACKEND",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Canonical database backend selector; hosted runtimes are expected to resolve to Postgres.",
        ),
        _build_env_contract_entry(
            name="CCDASH_DATABASE_URL",
            scope="shared",
            environ=env,
            required=hosted_storage,
            secret=True,
            default_when_missing=storage_profile.database_url_uses_local_default,
            notes=(
                "Shared database connection string. Hosted runtimes must override the local placeholder and point at canonical Postgres."
            ),
        ),
        _build_env_contract_entry(
            name="CCDASH_STORAGE_SHARED_POSTGRES",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Enables shared-enterprise storage mode when the hosted deployment reuses a Postgres instance.",
        ),
        _build_env_contract_entry(
            name="CCDASH_STORAGE_ISOLATION_MODE",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Dedicated, schema, or tenant isolation boundary for the storage contract.",
        ),
        _build_env_contract_entry(
            name="CCDASH_STORAGE_SCHEMA",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Schema or tenant boundary label used by shared-enterprise storage layouts.",
        ),
        _build_env_contract_entry(
            name="CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Optional hosted ingestion adapter switch; stays off unless enterprise filesystem ingestion is intentional.",
        ),
        _build_env_contract_entry(
            name="CCDASH_OTEL_ENABLED",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Shared observability switch for traces and metrics.",
        ),
        _build_env_contract_entry(
            name="CCDASH_OTEL_ENDPOINT",
            scope="shared",
            environ=env,
            default_when_missing=True,
            active=_env_bool_from(env, "CCDASH_OTEL_ENABLED", OTEL_ENABLED) or hosted_runtime,
            notes="Collector endpoint for OTEL export when observability is enabled.",
        ),
        _build_env_contract_entry(
            name="CCDASH_OTEL_SERVICE_NAME",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Logical service name emitted in observability metadata.",
        ),
        _build_env_contract_entry(
            name="CCDASH_PROM_PORT",
            scope="shared",
            environ=env,
            default_when_missing=True,
            notes="Prometheus metrics port for runtime probes and metrics scraping.",
        ),
    )
    api_only = (
        _build_env_contract_entry(
            name=CCDASH_API_BEARER_TOKEN_ENV,
            scope="api_only",
            environ=env,
            required=api_runtime,
            secret=True,
            notes="Hosted API authentication secret; required before the API should serve protected traffic.",
        ),
    )
    worker_only = (
        _build_env_contract_entry(
            name=CCDASH_WORKER_PROJECT_ID_ENV,
            scope="worker_only",
            environ=env,
            required=worker_runtime,
            notes="Hosted worker binding target; required before background jobs can own a project.",
        ),
        _build_env_contract_entry(
            name="CCDASH_TELEMETRY_EXPORT_ENABLED",
            scope="worker_only",
            environ=env,
            default_when_missing=True,
            active=worker_runtime,
            notes="Worker-only telemetry export master switch.",
        ),
        _build_env_contract_entry(
            name="CCDASH_SAM_ENDPOINT",
            scope="worker_only",
            environ=env,
            secret=False,
            default_when_missing=False,
            active=worker_runtime and _env_bool_from(env, "CCDASH_TELEMETRY_EXPORT_ENABLED", False),
            notes="Worker telemetry export endpoint when SAM export is enabled.",
        ),
        _build_env_contract_entry(
            name="CCDASH_SAM_API_KEY",
            scope="worker_only",
            environ=env,
            secret=True,
            default_when_missing=False,
            active=worker_runtime and _env_bool_from(env, "CCDASH_TELEMETRY_EXPORT_ENABLED", False),
            notes="Worker telemetry export API key when SAM export is enabled.",
        ),
    )
    local_only = (
        _build_env_contract_entry(
            name="CCDASH_DB_PATH",
            scope="local_only",
            environ=env,
            default_when_missing=True,
            active=runtime_profile in {"local", "test"},
            notes="SQLite file path for local-first runtimes; hosted runtimes must not rely on it.",
        ),
        _build_env_contract_entry(
            name="CCDASH_SESSION_MAPPINGS_FILE",
            scope="local_only",
            environ=env,
            active=runtime_profile in {"local", "test"},
            notes="Local override file for session mappings on top of persisted runtime state.",
        ),
        _build_env_contract_entry(
            name="CCDASH_SESSION_MAPPINGS_JSON",
            scope="local_only",
            environ=env,
            active=runtime_profile in {"local", "test"},
            notes="Inline local override for session mappings during development and test harnesses.",
        ),
    )

    errors: list[str] = []
    if hosted_storage and storage_profile.database_url_uses_local_default:
        errors.append(
            f"Runtime profile '{runtime_profile}' requires an explicit non-placeholder "
            "CCDASH_DATABASE_URL before serving hosted traffic."
        )
    if api_runtime and not resolve_api_bearer_token(env):
        errors.append(
            f"Runtime profile '{runtime_profile}' requires a non-empty "
            f"{CCDASH_API_BEARER_TOKEN_ENV} before serving traffic."
        )
    if worker_runtime and not resolve_worker_binding_config(env).configured:
        errors.append(
            f"Runtime profile '{runtime_profile}' requires a non-empty "
            f"{CCDASH_WORKER_PROJECT_ID_ENV} before starting background jobs."
        )

    warnings: list[str] = []
    if hosted_runtime and storage_profile.filesystem_source_of_truth:
        warnings.append(
            "Hosted storage contract enables CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED; keep filesystem ingestion scoped intentionally."
        )

    return RuntimeEnvironmentContract(
        runtime_profile=runtime_profile,
        deployment_mode=deployment_mode,
        storage_profile=storage_profile.profile,
        shared=shared,
        api_only=api_only,
        worker_only=worker_only,
        local_only=local_only,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def validate_runtime_environment_contract(
    runtime_profile: RuntimeProfileName,
    storage_profile: StorageProfileConfig,
    environ: Mapping[str, str] | None = None,
) -> RuntimeEnvironmentContract:
    contract = resolve_runtime_environment_contract(
        runtime_profile,
        storage_profile,
        environ=environ,
    )
    if contract.errors:
        raise RuntimeError(contract.errors[0])
    return contract


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
    artifact_telemetry_enabled: bool = False

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
    artifact_telemetry_enabled=CCDASH_SAM_ARTIFACT_TELEMETRY_ENABLED,
)
STORAGE_PROFILE = resolve_storage_profile_config()

# Startup sync tuning
STARTUP_SYNC_DELAY_SECONDS = _env_int("CCDASH_STARTUP_SYNC_DELAY_SECONDS", 2)
STARTUP_SYNC_LIGHT_MODE = _env_bool("CCDASH_STARTUP_SYNC_LIGHT_MODE", True)
STARTUP_DEFERRED_REBUILD_LINKS = _env_bool("CCDASH_STARTUP_DEFERRED_REBUILD_LINKS", False)
STARTUP_DEFERRED_REBUILD_DELAY_SECONDS = _env_int("CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS", 45)
STARTUP_DEFERRED_CAPTURE_ANALYTICS = _env_bool("CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS", False)
ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = _env_int("CCDASH_ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 900)
CCDASH_LIVE_REPLAY_BUFFER_SIZE = _env_int("CCDASH_LIVE_REPLAY_BUFFER_SIZE", 200)
CCDASH_LIVE_HEARTBEAT_SECONDS = _env_int("CCDASH_LIVE_HEARTBEAT_SECONDS", 15)
CCDASH_LIVE_MAX_PENDING_EVENTS = _env_int("CCDASH_LIVE_MAX_PENDING_EVENTS", 100)

# Agent query cache settings
# Controls how long memoized agent query service results are cached.
# Set to 0 to disable caching entirely.
CCDASH_QUERY_CACHE_TTL_SECONDS = _env_int("CCDASH_QUERY_CACHE_TTL_SECONDS", 60)
# Reserved for background cache refresh scheduling (not active in phase 3).
CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = _env_int("CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS", 300)

# Server settings
HOST = os.getenv("CCDASH_HOST", "0.0.0.0")
PORT = int(os.getenv("CCDASH_PORT", "8000"))

# CORS
FRONTEND_ORIGIN = os.getenv("CCDASH_FRONTEND_ORIGIN", "http://localhost:3000")
