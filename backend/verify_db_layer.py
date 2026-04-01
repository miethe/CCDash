"""Verification helpers for the CCDash storage composition contract."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend import config
from backend.db import connection, migrations
from backend.db.migration_governance import (
    SUPPORTED_STORAGE_COMPOSITIONS,
    StorageCompositionContract,
    get_enterprise_only_postgres_tables,
    get_sqlite_migration_tables,
    resolve_storage_composition_contract,
    validate_migration_governance_contract,
)
from backend.runtime.profiles import get_runtime_profile
from backend.runtime.storage_contract import get_storage_capability_contract
from backend.runtime_ports import build_core_ports

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ccdash.verify")


@dataclass(frozen=True, slots=True)
class StorageVerificationReport:
    composition: str
    storage_mode: str
    profile: str
    backend: str
    isolation_mode: str
    schema_name: str
    filesystem_source_of_truth: bool
    canonical_session_store: str
    required_guarantees: tuple[str, ...]
    shared_postgres_enabled: bool
    shared_table_count: int
    enterprise_only_table_count: int
    checks: tuple[str, ...]


async def _open_verification_connection(
    storage_profile: config.StorageProfileConfig,
) -> Any:
    if storage_profile.db_backend == "postgres":
        if connection.asyncpg is None:
            raise ImportError("asyncpg is required for Postgres backend.")
        logger.info("Opening Postgres verification connection for %s", storage_profile.database_url)
        return await connection.asyncpg.create_pool(storage_profile.database_url)

    db_path = Path(connection.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Opening SQLite verification connection for %s", db_path)
    db = await connection.aiosqlite.connect(str(db_path))
    db.row_factory = connection.aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute(f"PRAGMA busy_timeout={connection.SQLITE_BUSY_TIMEOUT_MS}")
    return db


async def _close_verification_connection(db: Any | None) -> None:
    if db is None:
        return
    close = getattr(db, "close", None)
    if close is None:
        return
    await close()


def resolve_storage_composition(
    storage_profile: config.StorageProfileConfig,
    *,
    supported_compositions: Iterable[StorageCompositionContract] = SUPPORTED_STORAGE_COMPOSITIONS,
) -> StorageCompositionContract:
    storage_contract = get_storage_capability_contract(storage_profile)
    if storage_profile.isolation_mode not in storage_contract.supported_isolation_modes:
        allowed = ", ".join(storage_contract.supported_isolation_modes)
        raise RuntimeError(
            f"Storage mode '{storage_contract.mode}' only supports isolation modes: {allowed}. "
            f"Resolved isolation mode: {storage_profile.isolation_mode}."
        )

    supported = tuple(supported_compositions)
    if supported is SUPPORTED_STORAGE_COMPOSITIONS:
        return resolve_storage_composition_contract(storage_profile)

    for composition in supported:
        if (
            composition.storage_mode == storage_contract.mode
            and composition.profile == storage_profile.profile
            and composition.backend == storage_profile.db_backend
            and storage_profile.isolation_mode in composition.isolation_modes
        ):
            return composition

    supported_names = ", ".join(
        f"{composition.composition} ({composition.backend}, isolation={','.join(composition.isolation_modes)})"
        for composition in supported
    )
    raise RuntimeError(
        "Resolved storage profile is not part of the supported storage composition matrix. "
        f"profile={storage_profile.profile} backend={storage_profile.db_backend} "
        f"mode={storage_contract.mode} isolation={storage_profile.isolation_mode}. "
        f"Supported compositions: {supported_names}"
    )


def verify_storage_profile_contract(
    storage_profile: config.StorageProfileConfig,
    *,
    supported_compositions: Iterable[StorageCompositionContract] = SUPPORTED_STORAGE_COMPOSITIONS,
) -> StorageVerificationReport:
    validate_migration_governance_contract()
    composition = resolve_storage_composition(
        storage_profile,
        supported_compositions=supported_compositions,
    )
    storage_contract = get_storage_capability_contract(storage_profile)
    shared_table_count = len(get_sqlite_migration_tables())
    enterprise_only_table_count = (
        len(get_enterprise_only_postgres_tables()) if composition.backend == "postgres" else 0
    )

    checks = [
        f"storage mode '{storage_contract.mode}' maps to composition '{composition.composition}'",
        f"backend '{composition.backend}' is supported with isolation '{storage_profile.isolation_mode}'",
        f"shared migration parity covers {shared_table_count} table(s)",
    ]
    if composition.backend == "postgres":
        checks.append(
            f"enterprise-only Postgres coverage reserves {enterprise_only_table_count} table(s)"
        )
    if storage_profile.shared_postgres_enabled:
        checks.append(
            f"shared Postgres isolation boundary uses schema '{storage_profile.schema_name}'"
        )

    return StorageVerificationReport(
        composition=composition.composition,
        storage_mode=storage_contract.mode,
        profile=storage_profile.profile,
        backend=storage_profile.db_backend,
        isolation_mode=storage_profile.isolation_mode,
        schema_name=storage_profile.schema_name,
        filesystem_source_of_truth=storage_profile.filesystem_source_of_truth,
        canonical_session_store=storage_profile.canonical_session_store,
        required_guarantees=storage_contract.required_guarantees,
        shared_postgres_enabled=storage_profile.shared_postgres_enabled,
        shared_table_count=shared_table_count,
        enterprise_only_table_count=enterprise_only_table_count,
        checks=tuple(checks),
    )


def build_storage_verification_matrix() -> tuple[StorageVerificationReport, ...]:
    return (
        verify_storage_profile_contract(
            config.resolve_storage_profile_config({"CCDASH_DB_BACKEND": "sqlite"})
        ),
        verify_storage_profile_contract(
            config.resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "enterprise",
                    "CCDASH_DB_BACKEND": "postgres",
                    "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                }
            )
        ),
        verify_storage_profile_contract(
            config.resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "enterprise",
                    "CCDASH_DB_BACKEND": "postgres",
                    "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                    "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                    "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                    "CCDASH_STORAGE_SCHEMA": "ccdash_app",
                    "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
                }
            )
        ),
    )


async def verify(
    storage_profile: config.StorageProfileConfig | None = None,
) -> StorageVerificationReport:
    active_profile = storage_profile or config.STORAGE_PROFILE
    report = verify_storage_profile_contract(active_profile)
    logger.info("Verifying storage composition: %s", report.composition)
    for check in report.checks:
        logger.info("CHECK %s", check)

    db = None
    try:
        db = await _open_verification_connection(active_profile)
        logger.info("✅ Database connected")
        await migrations.run_migrations(db)
        logger.info("✅ Migrations applied")
        ports = build_core_ports(
            db,
            runtime_profile=get_runtime_profile("test"),
            storage_profile=active_profile,
        )
        logger.info("✅ Storage adapter composed: %s", type(ports.storage).__name__)
        logger.info("✅ Canonical session store: %s", report.canonical_session_store)
        return report
    finally:
        await _close_verification_connection(db)
        if db is not None:
            logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(verify())
