"""Governance matrix for supported storage compositions and migration backends."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Literal

from backend import config
from backend.db import postgres_migrations, sqlite_migrations
from backend.runtime.storage_contract import StorageModeName

BackendName = Literal["sqlite", "postgres"]
StorageCompositionName = Literal["local-sqlite", "enterprise-postgres", "shared-enterprise-postgres"]

SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES: tuple[str, ...] = (
    "floating_point_type",
    "identity_column_strategy",
    "json_storage",
    "postgres_gin_indexes",
    "timestamp_default_expression",
)
_SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES_SET = frozenset(SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES)

_CREATE_TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\);", re.DOTALL)


@dataclass(frozen=True, slots=True)
class BackendSchemaCapability:
    backend: BackendName
    json_storage: str
    identity_strategy: str
    timestamp_default_strategy: str
    supports_gin_indexes: bool


@dataclass(frozen=True, slots=True)
class StorageCompositionContract:
    composition: StorageCompositionName
    storage_mode: StorageModeName
    profile: config.StorageProfileName
    backend: BackendName
    isolation_modes: tuple[config.StorageIsolationMode, ...]


BACKEND_SCHEMA_CAPABILITIES: dict[BackendName, BackendSchemaCapability] = {
    "sqlite": BackendSchemaCapability(
        backend="sqlite",
        json_storage="text_json_payloads",
        identity_strategy="integer_primary_key_autoincrement",
        timestamp_default_strategy="datetime_now_expression",
        supports_gin_indexes=False,
    ),
    "postgres": BackendSchemaCapability(
        backend="postgres",
        json_storage="jsonb_and_text_payloads",
        identity_strategy="serial_or_bigserial_identity",
        timestamp_default_strategy="current_timestamp_expression",
        supports_gin_indexes=True,
    ),
}


SUPPORTED_STORAGE_COMPOSITIONS: tuple[StorageCompositionContract, ...] = (
    StorageCompositionContract(
        composition="local-sqlite",
        storage_mode="local",
        profile="local",
        backend="sqlite",
        isolation_modes=("dedicated",),
    ),
    StorageCompositionContract(
        composition="enterprise-postgres",
        storage_mode="enterprise",
        profile="enterprise",
        backend="postgres",
        isolation_modes=("dedicated",),
    ),
    StorageCompositionContract(
        composition="shared-enterprise-postgres",
        storage_mode="shared-enterprise",
        profile="enterprise",
        backend="postgres",
        isolation_modes=("schema", "tenant"),
    ),
)


def _extract_table_blocks(ddl: str) -> dict[str, str]:
    return {table: block for table, block in _CREATE_TABLE_RE.findall(ddl)}


def _backend_table_blocks(module: object) -> dict[str, str]:
    """Extract table blocks from shared DDL strings (_TABLES, _TEST_VISUALIZER_TABLES)."""
    blocks: dict[str, str] = {}
    primary = getattr(module, "_TABLES", "")
    if isinstance(primary, str):
        blocks.update(_extract_table_blocks(primary))
    gated = getattr(module, "_TEST_VISUALIZER_TABLES", "")
    if isinstance(gated, str):
        blocks.update(_extract_table_blocks(gated))
    return blocks


def _enterprise_only_table_blocks(module: object) -> dict[str, str]:
    """Extract table blocks from enterprise-only DDL (_ENTERPRISE_IDENTITY_AUDIT_TABLES)."""
    blocks: dict[str, str] = {}
    enterprise = getattr(module, "_ENTERPRISE_IDENTITY_AUDIT_TABLES", "")
    if isinstance(enterprise, str):
        blocks.update(_extract_table_blocks(enterprise))
    return blocks


@lru_cache(maxsize=1)
def get_sqlite_migration_tables() -> frozenset[str]:
    return frozenset(_backend_table_blocks(sqlite_migrations))


@lru_cache(maxsize=1)
def get_postgres_migration_tables() -> frozenset[str]:
    """Return all Postgres migration tables (shared + enterprise-only)."""
    return frozenset(_backend_table_blocks(postgres_migrations)) | get_enterprise_only_postgres_tables()


@lru_cache(maxsize=1)
def get_enterprise_only_postgres_tables() -> frozenset[str]:
    """Return tables that exist only in enterprise Postgres, not in SQLite."""
    return frozenset(_enterprise_only_table_blocks(postgres_migrations))


def _difference_categories(sqlite_block: str, postgres_block: str) -> tuple[str, ...]:
    categories: list[str] = []
    sqlite_upper = sqlite_block.upper()
    postgres_upper = postgres_block.upper()

    if "REAL" in sqlite_upper and "DOUBLE PRECISION" in postgres_upper:
        categories.append("floating_point_type")
    if "AUTOINCREMENT" in sqlite_upper and ("SERIAL" in postgres_upper or "BIGSERIAL" in postgres_upper):
        categories.append("identity_column_strategy")
    if "TEXT DEFAULT (DATETIME('NOW'))" in sqlite_upper and "CURRENT_TIMESTAMP" in postgres_upper:
        categories.append("timestamp_default_expression")
    if "JSONB" in postgres_upper:
        categories.append("json_storage")
    if "USING GIN" in postgres_upper:
        categories.append("postgres_gin_indexes")

    # Preserve stable ordering while removing duplicates.
    deduped = list(dict.fromkeys(categories))
    return tuple(deduped)


@lru_cache(maxsize=1)
def get_table_backend_difference_matrix() -> dict[str, tuple[str, ...]]:
    sqlite_blocks = _backend_table_blocks(sqlite_migrations)
    postgres_blocks = _backend_table_blocks(postgres_migrations)
    shared_tables = sorted(set(sqlite_blocks).intersection(postgres_blocks))
    return {
        table: _difference_categories(sqlite_blocks[table], postgres_blocks[table])
        for table in shared_tables
    }


def validate_migration_governance_contract() -> None:
    from backend.data_domains import PLANNED_AUTH_AUDIT_CONCERNS

    sqlite_tables = get_sqlite_migration_tables()
    postgres_tables = get_postgres_migration_tables()
    enterprise_only = get_enterprise_only_postgres_tables()
    shared_postgres = postgres_tables - enterprise_only

    # Shared tables must be identical across both backends.
    if sqlite_tables != shared_postgres:
        only_sqlite = sorted(sqlite_tables - shared_postgres)
        only_shared_postgres = sorted(shared_postgres - sqlite_tables)
        raise RuntimeError(
            "SQLite and shared Postgres migration table sets diverged. "
            f"sqlite_only={only_sqlite} shared_postgres_only={only_shared_postgres}"
        )

    # Enterprise-only Postgres tables must match the planned identity/audit concerns.
    expected_enterprise = frozenset(PLANNED_AUTH_AUDIT_CONCERNS)
    if enterprise_only != expected_enterprise:
        missing = sorted(expected_enterprise - enterprise_only)
        extra = sorted(enterprise_only - expected_enterprise)
        raise RuntimeError(
            "Enterprise-only Postgres tables must match planned identity/audit concerns. "
            f"missing={missing} extra={extra}"
        )

    # Backend difference matrix classifies only the shared tables.
    matrix = get_table_backend_difference_matrix()
    if set(matrix) != sqlite_tables:
        raise RuntimeError("Migration governance matrix must classify every shared migration-managed table.")

    for table, categories in matrix.items():
        unsupported = sorted(set(categories) - _SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES_SET)
        if unsupported:
            raise RuntimeError(
                f"Table '{table}' uses unsupported backend-difference categories: {unsupported}"
            )

    expected_compositions = {
        "local-sqlite": ("local", "sqlite", ("dedicated",)),
        "enterprise-postgres": ("enterprise", "postgres", ("dedicated",)),
        "shared-enterprise-postgres": ("shared-enterprise", "postgres", ("schema", "tenant")),
    }
    if len(SUPPORTED_STORAGE_COMPOSITIONS) != len(expected_compositions):
        raise RuntimeError("Supported storage composition matrix is incomplete.")

    for composition in SUPPORTED_STORAGE_COMPOSITIONS:
        expected = expected_compositions.get(composition.composition)
        if expected is None:
            raise RuntimeError(f"Unknown storage composition in governance matrix: {composition.composition}")
        expected_mode, expected_backend, expected_isolation = expected
        if composition.storage_mode != expected_mode:
            raise RuntimeError(
                f"Composition '{composition.composition}' has storage_mode={composition.storage_mode}, "
                f"expected={expected_mode}"
            )
        if composition.backend != expected_backend:
            raise RuntimeError(
                f"Composition '{composition.composition}' has backend={composition.backend}, "
                f"expected={expected_backend}"
            )
        if composition.isolation_modes != expected_isolation:
            raise RuntimeError(
                f"Composition '{composition.composition}' has isolation_modes={composition.isolation_modes}, "
                f"expected={expected_isolation}"
            )
