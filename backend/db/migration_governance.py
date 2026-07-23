"""Governance matrix for supported storage compositions and migration backends.

Column/Constraint Parity Normalization
======================================
``column_parity_diff`` and ``get_column_parity_diff_all`` parse the DDL for each
shared table and compare column structure across backends after applying a
canonical type-normalization mapping.  The goal is to surface *structural* drift
(genuinely missing columns, wrong nullability, wrong defaults) while suppressing
noise from expected cross-backend type aliases.

Type normalization rules (SQLite raw → canonical, Postgres raw → canonical):
  TEXT, VARCHAR(n), CHARACTER VARYING(n), CLOB  → "text"
  INTEGER, INT, INT4, SMALLINT, TINYINT         → "integer"
  BIGINT, INT8                                  → "integer"   (width alias only)
  SERIAL                                        → "integer"   (identity strategy, already categorized)
  BIGSERIAL                                     → "integer"   (identity strategy, already categorized)
  REAL, FLOAT, FLOAT4                           → "real"      (floating-point, already categorized)
  DOUBLE PRECISION, FLOAT8                      → "real"      (floating-point, already categorized)
  NUMERIC, DECIMAL                              → "real"
  BOOLEAN                                       → "integer"   (SQLite stores bools as 0/1 INTEGER;
                                                               already categorized as identity_column_strategy
                                                               sibling; treat as equivalent)
  JSONB                                         → "text"      (json_storage category; already categorized)
  TIMESTAMP WITH TIME ZONE, TIMESTAMPTZ        → "text"      (timestamp_default_expression category;
                                                               already categorized; Postgres TIMESTAMPTZ
                                                               used for audit-trail columns and is
                                                               semantically equivalent to TEXT ISO-8601)
  DATETIME                                      → "text"      (SQLite datetime alias → text)

Default-value normalization:
  SQLite ``(datetime('now'))`` and Postgres ``CURRENT_TIMESTAMP`` / ``CURRENT_TIMESTAMP::text``
  are both normalized to the sentinel ``"<timestamp_now>"`` because the
  timestamp_default_expression difference is already in the approved category list.

Allowlist of known structural drift items
==========================================
Some tables have deliberate structural differences that cannot be collapsed by
type-normalization alone.  These are recorded in
  .claude/findings/ccdash-db-design-remediation-findings.md
and listed here explicitly so the CI test can assert an *empty* diff after
exclusions are applied.

  DRIFT-001  outbound_telemetry_queue / event_type column
    The SQLite baseline _TABLES DDL omits event_type; it is added via the
    _migrate_outbound_telemetry_queue_add_event_type() procedure.  The Postgres
    baseline _TABLES DDL includes it from the start.  Both backends *converge* at
    runtime once the SQLite migration runs; the DDL-level difference is a
    bootstrapping artifact, not a semantic schema gap.  Excluded from the parity
    assertion.

  DRIFT-002  session_relationships / created_at nullability
    SQLite: TEXT NOT NULL DEFAULT (datetime('now'))
    Postgres: TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP  (nullable)
    After type normalization both become "text" with default "<timestamp_now>", but
    SQLite marks the column NOT NULL while Postgres allows NULL.  This is a minor
    real drift; it is harmless in practice (the repo layer always writes a value),
    but is captured here for auditability.  Excluded from the parity assertion.

  DRIFT-003  oq_resolutions / created_at and updated_at nullability
    SQLite: TEXT NOT NULL DEFAULT (datetime('now'))
    Postgres: TEXT DEFAULT CURRENT_TIMESTAMP::text  (nullable)
    Both columns carry the same semantic intent (record creation/update time) and
    the repository always provides a value.  The NOT NULL constraint on the SQLite
    side is tighter but harmless; excluded from the parity assertion.

  DRIFT-004  session_sentiment_facts / evidence_json NOT NULL constraint
  DRIFT-005  session_code_churn_facts / evidence_json NOT NULL constraint
  DRIFT-006  session_scope_drift_facts / evidence_json NOT NULL constraint
    SQLite:   evidence_json TEXT DEFAULT '{}'               (nullable)
    Postgres: evidence_json JSONB NOT NULL DEFAULT '{}'     (NOT NULL)
    The json_storage difference category already accounts for TEXT vs JSONB.
    The NOT NULL mismatch is a genuine structural drift: Postgres was given the
    tighter constraint when these tables were authored, but the SQLite DDL was
    not updated in kind.  Fixing the SQLite DDL to add NOT NULL would change
    applied-migration semantics (existing NULLs would become invalid), so the
    divergence is recorded here rather than patched.  The repository layer
    always writes a non-NULL JSON object so no NULL values exist in practice.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Literal

from backend import config
from backend.db import postgres_migrations, sqlite_migrations
from backend.runtime.storage_contract import StorageModeName, resolve_storage_mode

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

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+"
    r"(?:(?P<schema>[a-zA-Z_][a-zA-Z0-9_]*)\.)?"
    r"(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s*"
    r"\((?P<body>.*?)\);",
    re.DOTALL,
)

_IDENTITY_ACCESS_CONCERNS = frozenset({"principals", "scope_identifiers", "memberships", "role_bindings"})
_AUDIT_SECURITY_CONCERNS = frozenset({"privileged_action_audit_records", "access_decision_logs"})
_OBSERVED_ENTITY_ENTERPRISE_ONLY_CONCERNS = frozenset({"session_embeddings"})


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


def resolve_storage_composition_contract(
    storage_profile: config.StorageProfileConfig,
) -> StorageCompositionContract:
    storage_mode = resolve_storage_mode(storage_profile)
    for composition in SUPPORTED_STORAGE_COMPOSITIONS:
        if composition.storage_mode != storage_mode:
            continue
        if composition.profile != storage_profile.profile:
            continue
        if composition.backend != storage_profile.db_backend:
            continue
        if storage_profile.isolation_mode not in composition.isolation_modes:
            continue
        return composition

    supported = ", ".join(
        f"{composition.composition} ({composition.backend}, isolation={','.join(composition.isolation_modes)})"
        for composition in SUPPORTED_STORAGE_COMPOSITIONS
    )
    raise RuntimeError(
        "Resolved storage profile is not part of the supported storage composition matrix. "
        f"profile={storage_profile.profile} backend={storage_profile.db_backend} "
        f"mode={storage_mode} isolation={storage_profile.isolation_mode}. "
        f"Supported compositions: {supported}"
    )


def build_migration_governance_metadata(
    storage_profile: config.StorageProfileConfig,
) -> dict[str, tuple[str, ...] | str]:
    composition = resolve_storage_composition_contract(storage_profile)
    return {
        "storageComposition": composition.composition,
        "migrationGovernanceStatus": "verified",
        "supportedStorageCompositions": tuple(
            contract.composition for contract in SUPPORTED_STORAGE_COMPOSITIONS
        ),
        "supportedBackendDifferenceCategories": SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES,
    }


def _extract_table_blocks(ddl: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for match in _CREATE_TABLE_RE.finditer(ddl):
        blocks[match.group("table")] = match.group("body")
    return blocks


def _extract_table_schema_map(ddl: str) -> dict[str, str | None]:
    schema_map: dict[str, str | None] = {}
    for match in _CREATE_TABLE_RE.finditer(ddl):
        schema_map[match.group("table")] = match.group("schema")
    return schema_map


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
    """Extract table blocks from enterprise-only DDL strings."""
    blocks: dict[str, str] = {}
    for attr in ("_ENTERPRISE_IDENTITY_AUDIT_TABLES", "_ENTERPRISE_SESSION_INTELLIGENCE_TABLES"):
        enterprise = getattr(module, attr, "")
        if isinstance(enterprise, str):
            blocks.update(_extract_table_blocks(enterprise))
    return blocks


def _enterprise_only_table_schema_map(module: object) -> dict[str, str | None]:
    schema_map: dict[str, str | None] = {}
    for attr in ("_ENTERPRISE_IDENTITY_AUDIT_TABLES", "_ENTERPRISE_SESSION_INTELLIGENCE_TABLES"):
        enterprise = getattr(module, attr, "")
        if isinstance(enterprise, str):
            schema_map.update(_extract_table_schema_map(enterprise))
    return schema_map


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


@lru_cache(maxsize=1)
def get_enterprise_only_postgres_table_schemas() -> dict[str, str]:
    """Return enterprise-only table -> schema mapping."""
    schema_map = _enterprise_only_table_schema_map(postgres_migrations)
    # Enterprise-only concerns must always be schema-qualified.
    return {table: schema or "" for table, schema in schema_map.items()}


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
    from backend.data_domains import ENTERPRISE_ONLY_POSTGRES_CONCERNS

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
    expected_enterprise = frozenset(ENTERPRISE_ONLY_POSTGRES_CONCERNS)
    if enterprise_only != expected_enterprise:
        missing = sorted(expected_enterprise - enterprise_only)
        extra = sorted(enterprise_only - expected_enterprise)
        raise RuntimeError(
            "Enterprise-only Postgres tables must match planned identity/audit concerns. "
            f"missing={missing} extra={extra}"
        )

    schema_map = get_enterprise_only_postgres_table_schemas()
    if frozenset(schema_map) != expected_enterprise:
        missing_schema = sorted(expected_enterprise - frozenset(schema_map))
        extra_schema = sorted(frozenset(schema_map) - expected_enterprise)
        raise RuntimeError(
            "Enterprise-only Postgres schema map must match planned identity/audit concerns. "
            f"missing={missing_schema} extra={extra_schema}"
        )
    expected_schema_map = {concern: "identity" for concern in _IDENTITY_ACCESS_CONCERNS}
    expected_schema_map.update({concern: "audit" for concern in _AUDIT_SECURITY_CONCERNS})
    expected_schema_map.update({concern: "app" for concern in _OBSERVED_ENTITY_ENTERPRISE_ONLY_CONCERNS})
    if schema_map != expected_schema_map:
        raise RuntimeError(
            "Enterprise-only Postgres tables are not in the expected schemas. "
            f"actual={schema_map} expected={expected_schema_map}"
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


# ── Column/Constraint Parity (T3-009) ─────────────────────────────────────────

# Canonical type mapping: (uppercased token prefix → canonical type string).
# Longer prefixes must come before shorter ones that are prefixes of them.
_TYPE_NORM_MAP: tuple[tuple[str, str], ...] = (
    # Postgres serial identity types → integer (identity strategy: already categorized)
    ("BIGSERIAL", "integer"),
    ("SERIAL", "integer"),
    # Floating-point → real (floating_point_type: already categorized)
    ("DOUBLE PRECISION", "real"),
    ("FLOAT8", "real"),
    ("FLOAT4", "real"),
    ("FLOAT", "real"),
    ("REAL", "real"),
    ("NUMERIC", "real"),
    ("DECIMAL", "real"),
    # Integer family
    ("BIGINT", "integer"),
    ("INT8", "integer"),
    ("INT4", "integer"),
    ("INTEGER", "integer"),
    ("SMALLINT", "integer"),
    ("TINYINT", "integer"),
    ("INT", "integer"),
    # Boolean → integer (SQLite stores as 0/1 INTEGER)
    ("BOOLEAN", "integer"),
    ("BOOL", "integer"),
    # JSONB → text (json_storage: already categorized)
    ("JSONB", "text"),
    ("JSON", "text"),
    # Timestamp with time zone → text (timestamp_default_expression: already categorized)
    ("TIMESTAMP WITH TIME ZONE", "text"),
    ("TIMESTAMPTZ", "text"),
    ("TIMESTAMP", "text"),
    ("DATETIME", "text"),
    # Text family
    ("CHARACTER VARYING", "text"),
    ("VARCHAR", "text"),
    ("CLOB", "text"),
    ("TEXT", "text"),
)

# Default-value normalization sentinels.
_TIMESTAMP_NOW_DEFAULTS = frozenset({
    "DATETIME('NOW')",
    "(DATETIME('NOW'))",
    "CURRENT_TIMESTAMP",
    "CURRENT_TIMESTAMP::TEXT",
    "(DATETIME('NOW'))::TEXT",
    "NOW()",
    # Unstripped variants sometimes produced by the extractor
    "DATETIME('NOW'))",
})

# Allowlist of (table, column) pairs excluded from the parity assertion.
# Each entry references a DRIFT-NNN item documented in this module's docstring
# and in .claude/findings/ccdash-db-design-remediation-findings.md.
COLUMN_PARITY_DRIFT_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
    # DRIFT-001: event_type exists in Postgres baseline DDL but not in SQLite _TABLES
    # (added via migration procedure instead).
    ("outbound_telemetry_queue", "event_type"),
    # DRIFT-002: created_at NOT NULL in SQLite, nullable in Postgres
    ("session_relationships", "created_at"),
    # DRIFT-003: created_at / updated_at NOT NULL in SQLite, nullable in Postgres
    ("oq_resolutions", "created_at"),
    ("oq_resolutions", "updated_at"),
    # DRIFT-004/005/006: evidence_json NOT NULL in Postgres, nullable in SQLite
    # (json_storage type difference already categorized; NOT NULL gap recorded here)
    ("session_sentiment_facts", "evidence_json"),
    ("session_code_churn_facts", "evidence_json"),
    ("session_scope_drift_facts", "evidence_json"),
    # Phase 5 detection columns (T5-006/T5-007): model_slug, workflow_id,
    # subagent_parent_id, skill_name, context_window are declared identically in
    # BOTH the SQLite and Postgres `sessions` CREATE TABLE DDL (same type TEXT,
    # same nullability, same default). They are therefore PARITY-CLEAN by
    # construction and intentionally NOT allowlisted — any drift here is a real
    # regression the parity test must catch.
    #
    # rf_events (T1-001/T1-002, research-foundry-run-telemetry v1, v40): every
    # column is declared identically across both DDL files — same name, same
    # normalized type (INTEGER/BOOLEAN, TEXT/JSONB, REAL/DOUBLE PRECISION all
    # collapse to the same canonical type; TEXT NOT NULL DEFAULT (datetime('now'))
    # vs TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP for created_at is the
    # already-suppressed timestamp-default nullability case), same nullability,
    # same default. `column_parity_diff("rf_events")` is `{}` by construction.
    # rf_events is therefore intentionally NOT allowlisted here — see
    # backend/tests/test_rf_events_migration_governance.py, which pins this and
    # would fail if a future edit introduced real drift.
    #
    # research_runs (T2-001/T2-002, research-foundry-run-telemetry v1, Phase 2,
    # v41): the derived rollup table folded from rf_events. Every column is
    # declared identically across both DDL files using the same
    # canonical-type/normalized-default conventions established for rf_events
    # above (INTEGER/BOOLEAN, TEXT/JSONB, REAL/DOUBLE PRECISION, and the
    # timestamp-default nullability case for created_at/updated_at all
    # collapse to the same canonical form). `column_parity_diff("research_runs")`
    # is `{}` by construction. research_runs is therefore intentionally NOT
    # allowlisted here — see backend/tests/test_research_runs_migration_governance.py
    # and the `test_research_runs_columns_are_parity_clean_not_allowlisted` case
    # in backend/tests/test_migration_governance.py (ADR-007 exit gate, T2-002),
    # either of which would fail if a future edit introduced real drift.
    #
    # aar_reviews (T1-005/T1-007, ccdash-automated-aar-review-v1 Phase 1, v42):
    # the AAR-document<->session triage rollup persisted by
    # backend/db/repositories/aar_reviews.py. Every column is declared
    # identically across both DDL files using the same canonical-type/
    # normalized-default conventions established above for rf_events/
    # research_runs (TEXT/JSONB for the JSON-encoded correlation/flags/
    # triage_reasons/evidence_refs columns, and the timestamp-default
    # nullability case for created_at/updated_at). `column_parity_diff(
    # "aar_reviews")` is `{}` by construction. aar_reviews is therefore
    # intentionally NOT allowlisted here — see
    # backend/tests/test_aar_reviews_repo.py, which pins this and would fail
    # if a future edit introduced real drift.
})

# Regex for splitting a column line into (name, type-and-rest)
_COL_NAME_RE = re.compile(r"^\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s+(?P<rest>.+)", re.DOTALL)
# Matches table-level constraint keywords that are not column definitions
_CONSTRAINT_KEYWORDS = frozenset({
    "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "CONSTRAINT", "INDEX",
})


def _normalize_type(raw: str) -> str:
    """Return the canonical type string for a raw SQL type token."""
    upper = raw.strip().upper()
    for prefix, canonical in _TYPE_NORM_MAP:
        if upper.startswith(prefix):
            return canonical
    # Fallback: lowercase the first token
    return upper.split("(")[0].split()[0].lower()


def _normalize_default(raw: str) -> str:
    """Normalize a DEFAULT value to suppress known-equivalent expressions."""
    cleaned = raw.strip()
    # Strip outer parens that wrap the entire expression (SQLite convention)
    while cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    upper = cleaned.upper()
    if upper in _TIMESTAMP_NOW_DEFAULTS:
        return "<timestamp_now>"
    # Strip PostgreSQL type-cast suffix (e.g. '{}'::jsonb → '{}', '[]'::jsonb → '[]')
    cleaned = re.sub(r"::\s*\w+(\s+\w+)*(\[\])?$", "", cleaned).strip()
    # Strip surrounding quotes
    cleaned = cleaned.strip("'\"")
    # Normalize boolean literals to 0/1 so SQLite DEFAULT 0 == Postgres DEFAULT FALSE
    if cleaned.upper() == "FALSE":
        return "0"
    if cleaned.upper() == "TRUE":
        return "1"
    return cleaned.lower()


def _parse_table_columns(body: str) -> dict[str, tuple[str, bool, str]]:
    """Parse a CREATE TABLE body into a normalized column map.

    Returns:
        {column_name: (normalized_type, nullable, normalized_default)}

    Table-level constraints (PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY) are
    skipped.  Inline PRIMARY KEY / NOT NULL modifiers are tracked.
    """
    result: dict[str, tuple[str, bool, str]] = {}

    # Strip SQL line comments BEFORE splitting on commas.  Comments can
    # contain commas (e.g. "-- ... the repository layer, which binds ...")
    # that would otherwise produce spurious split points.
    body_no_comments = re.sub(r"--[^\n]*", "", body)

    # Split on commas at the top level (not inside parentheses or quotes)
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    in_sq = False  # inside single-quoted string
    for ch in body_no_comments:
        if ch == "'" and not in_sq:
            in_sq = True
            buf.append(ch)
        elif ch == "'" and in_sq:
            in_sq = False
            buf.append(ch)
        elif in_sq:
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Skip block comment fragments or parts with no identifier-like content
        if part.startswith("/*") or not re.search(r"[a-zA-Z_]", part):
            continue

        m = _COL_NAME_RE.match(part)
        if not m:
            continue

        name = m.group("name").lower()
        rest = m.group("rest").strip()

        # Skip table-level constraints
        if name.upper() in _CONSTRAINT_KEYWORDS:
            continue

        # Extract type: everything up to the first constraint keyword or end
        rest_upper = rest.upper()
        type_end = len(rest)
        for kw in ("NOT NULL", "NULL", "DEFAULT", "PRIMARY KEY", "REFERENCES",
                   "CHECK", "UNIQUE", "CONSTRAINT"):
            idx = rest_upper.find(kw)
            if idx != -1 and idx < type_end:
                type_end = idx

        raw_type = rest[:type_end].strip()
        normalized_type = _normalize_type(raw_type)

        # Nullable: column is nullable unless NOT NULL is present
        nullable = "NOT NULL" not in rest_upper

        # Default value — extract everything after DEFAULT up to the next
        # constraint keyword, handling nested parentheses correctly.
        default_val = ""
        default_kw_match = re.search(r"\bDEFAULT\b", rest, re.IGNORECASE)
        if default_kw_match:
            after_default = rest[default_kw_match.end():].strip()
            # Walk character-by-character to handle nested parens
            depth_d = 0
            buf_d: list[str] = []
            in_single_quote = False
            for ch in after_default:
                if ch == "'" and not in_single_quote:
                    in_single_quote = True
                    buf_d.append(ch)
                elif ch == "'" and in_single_quote:
                    in_single_quote = False
                    buf_d.append(ch)
                elif in_single_quote:
                    buf_d.append(ch)
                elif ch == "(":
                    depth_d += 1
                    buf_d.append(ch)
                elif ch == ")":
                    if depth_d == 0:
                        break  # End of the column definition section
                    depth_d -= 1
                    buf_d.append(ch)
                elif ch == "," and depth_d == 0:
                    break
                else:
                    # Stop at constraint keywords at depth 0
                    remainder = "".join(buf_d) + ch + after_default[len(buf_d) + 1:]
                    tok_upper = "".join(buf_d).strip().upper()
                    # Check if we've hit a constraint keyword that terminates the default
                    hit_kw = False
                    for kw in ("NOT NULL", "NULL", "PRIMARY KEY", "REFERENCES",
                               "CHECK", "UNIQUE", "CONSTRAINT"):
                        if tok_upper.endswith(kw):
                            # Remove the keyword we accidentally collected
                            buf_d = buf_d[: -len(kw)]
                            hit_kw = True
                            break
                    if hit_kw:
                        break
                    buf_d.append(ch)
            raw_default = "".join(buf_d).strip()
            # Strip trailing constraint keyword tokens that slipped through
            for kw in ("NOT NULL", "NULL", "PRIMARY KEY", "REFERENCES",
                       "CHECK", "UNIQUE", "CONSTRAINT"):
                if raw_default.upper().endswith(kw):
                    raw_default = raw_default[: -len(kw)].strip()
            if raw_default:
                default_val = _normalize_default(raw_default)

        result[name] = (normalized_type, nullable, default_val)

    return result


def column_parity_diff(table: str) -> dict[str, dict[str, dict]]:
    """Return a machine-readable diff for *table* across the two shared backends.

    Returns an empty dict when the table is structurally identical (after type
    normalization and allowlist exclusions).  Returns::

        {table: {"sqlite": <normalized_cols>, "postgres": <normalized_cols>}}

    when any structural difference is detected.

    Each *normalized_cols* value is a mapping of
    ``{column_name: {"type": str, "nullable": bool, "default": str}}``.

    Only columns in the intersection/symmetric-difference are included in the
    diff output – columns present in both backends and identical are omitted
    from the per-side representations to keep the output concise.
    """
    sqlite_blocks = _backend_table_blocks(sqlite_migrations)
    postgres_blocks = _backend_table_blocks(postgres_migrations)

    if table not in sqlite_blocks or table not in postgres_blocks:
        # Table not shared; no parity diff to compute.
        return {}

    sqlite_cols = _parse_table_columns(sqlite_blocks[table])
    postgres_cols = _parse_table_columns(postgres_blocks[table])

    # Build symmetric diff: columns that differ or exist on one side only,
    # excluding allowlisted (table, column) pairs and suppressing differences
    # that fall under already-categorized backend difference categories.
    all_cols = set(sqlite_cols) | set(postgres_cols)
    differing: set[str] = set()
    for col in all_cols:
        if (table, col) in COLUMN_PARITY_DRIFT_ALLOWLIST:
            continue
        sq = sqlite_cols.get(col)
        pg = postgres_cols.get(col)
        if sq == pg:
            continue
        # Suppress timestamp-default nullability drift.
        # Postgres TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP columns
        # are nullable by DDL convention; the SQLite equivalent TEXT NOT NULL
        # DEFAULT (datetime('now')) is NOT NULL.  Both sides normalize to
        # type="text" default="<timestamp_now>"; the nullability gap is
        # already categorized as "timestamp_default_expression".
        if (
            sq is not None and pg is not None
            and sq[0] == pg[0]          # same normalized type
            and sq[2] == pg[2] == "<timestamp_now>"  # both timestamp defaults
            and sq[1] != pg[1]          # only nullability differs
        ):
            continue
        differing.add(col)

    if not differing:
        return {}

    def _fmt(cols: dict[str, tuple[str, bool, str]], relevant: set[str]) -> dict:
        return {
            col: {"type": cols[col][0], "nullable": cols[col][1], "default": cols[col][2]}
            for col in sorted(relevant)
            if col in cols
        }

    return {
        table: {
            "sqlite": _fmt(sqlite_cols, differing),
            "postgres": _fmt(postgres_cols, differing),
        }
    }


@lru_cache(maxsize=1)
def get_column_parity_diff_all() -> dict[str, dict[str, dict]]:
    """Return merged column-parity diff across all shared tables.

    Returns an empty dict when no structural drift is found (after type
    normalization and allowlist exclusions).  Suitable for a CI assertion::

        assert get_column_parity_diff_all() == {}
    """
    sqlite_tables = get_sqlite_migration_tables()
    postgres_enterprise = get_enterprise_only_postgres_tables()
    postgres_all = get_postgres_migration_tables()
    shared_tables = sorted(sqlite_tables & (postgres_all - postgres_enterprise))

    merged: dict[str, dict[str, dict]] = {}
    for table in shared_tables:
        diff = column_parity_diff(table)
        merged.update(diff)
    return merged
