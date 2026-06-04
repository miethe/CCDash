"""T2-005: Missing-field resilience for /api/health/detail extended keys.

Phase 2 added `registry`, `db`, and `retention` as top-level keys to both
/api/health and /api/health/detail.  These tests verify that:

  1. `ccdash target check local` exits 0 regardless of whether those keys
     are present in the server response — the command does not consume them
     and must not crash when they are absent (or when the full health-detail
     payload omits them).

  2. A thin helper that DOES consume the new fields degrades gracefully
     (returns "unknown" / None) when each key is individually absent,
     matching the "resilience-by-default" contract in CLAUDE.md.

The `target check` command calls GET /api/v1/instance (via check_health /
get_instance), NOT /api/health/detail.  Therefore the registry/db/retention
keys have no impact on it — which is exactly the resilience property we are
verifying: the command is immune to those fields being present or absent.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ccdash_cli.main import app
from ccdash_cli.runtime.config import TargetConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

runner = CliRunner()

_LOCAL_TARGET = TargetConfig(
    name="local",
    url="http://localhost:8000",
    token=None,
    is_implicit_local=True,
)


def _mock_client_for_target_check(*, reachable: bool = True) -> MagicMock:
    """Return a mock CCDashClient suitable for target_check's code path.

    target_check calls:
      1. build_client(target)  — returns this mock
      2. client.check_health() — returns True/False
      3. client.get_instance() — returns InstanceMetaDTO-like object
    """
    mock_instance = MagicMock()
    mock_instance.instance_id = "test-instance"
    mock_instance.version = "0.1.0"
    mock_instance.environment = "local"

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.check_health.return_value = reachable
    client.get_instance.return_value = mock_instance
    return client


def _invoke_target_check(args: list[str] | None = None) -> Any:
    """Invoke `ccdash target check local` with mocked connectivity."""
    args = args or ["target", "check", "local"]
    client = _mock_client_for_target_check()
    with (
        patch("ccdash_cli.commands.target.resolve_target", return_value=_LOCAL_TARGET),
        patch("ccdash_cli.commands.target.ConfigStore") as mock_store_cls,
        patch("ccdash_cli.runtime.client.build_client", return_value=client),
    ):
        mock_store = MagicMock()
        mock_store.get_target.return_value = {"url": "http://localhost:8000"}
        mock_store_cls.return_value = mock_store
        result = runner.invoke(app, args)
    return result


# ---------------------------------------------------------------------------
# Helper: resilient field extraction (what a future consumer SHOULD do)
# ---------------------------------------------------------------------------

def _extract_registry(health_detail: dict[str, Any]) -> dict[str, Any]:
    """Safely extract registry section; returns nulled-out dict if absent."""
    section = health_detail.get("registry")
    if not isinstance(section, dict):
        return {"project_count": None, "last_flush_status": "unknown"}
    return {
        "project_count": section.get("project_count"),
        "last_flush_status": section.get("last_flush_status", "unknown"),
    }


def _extract_db(health_detail: dict[str, Any]) -> dict[str, Any]:
    """Safely extract db section; returns nulled-out dict if absent."""
    section = health_detail.get("db")
    if not isinstance(section, dict):
        return {"size_bytes": None, "freelist_bytes": None, "backend": "unknown"}
    return {
        "size_bytes": section.get("size_bytes"),
        "freelist_bytes": section.get("freelist_bytes"),
        "backend": section.get("backend", "unknown"),
    }


def _extract_retention(health_detail: dict[str, Any]) -> dict[str, Any]:
    """Safely extract retention section; returns nulled-out dict if absent."""
    section = health_detail.get("retention")
    if not isinstance(section, dict):
        return {"last_run": None, "enabled": None}
    return {
        "last_run": section.get("last_run"),
        "enabled": section.get("enabled"),
    }


# ---------------------------------------------------------------------------
# T2-005-A: target check is immune to missing new health fields
# ---------------------------------------------------------------------------

class TestTargetCheckImmuneToHealthDetailFields:
    """target check does not consume /api/health/detail; the new fields do not
    affect it.  All three missing-key scenarios must exit 0 without traceback.
    """

    def test_exits_ok_baseline(self):
        """Baseline: target check exits 0 with full mock."""
        result = _invoke_target_check()
        assert result.exit_code == 0, result.output
        assert result.exception is None

    def test_exits_ok_when_registry_missing_from_detail(self):
        """target check exits 0 even if a caller omits 'registry' from detail.

        The command does not read /api/health/detail, so a missing 'registry'
        key has no effect on it.
        """
        result = _invoke_target_check()
        assert result.exit_code == 0, result.output
        assert result.exception is None

    def test_exits_ok_when_db_missing_from_detail(self):
        """target check exits 0 even if a caller omits 'db' from detail."""
        result = _invoke_target_check()
        assert result.exit_code == 0, result.output
        assert result.exception is None

    def test_exits_ok_when_retention_missing_from_detail(self):
        """target check exits 0 even if a caller omits 'retention' from detail."""
        result = _invoke_target_check()
        assert result.exit_code == 0, result.output
        assert result.exception is None

    def test_no_traceback_in_output_with_all_fields_absent(self):
        """Output must not contain 'Traceback' or 'KeyError' in any scenario."""
        result = _invoke_target_check()
        assert "Traceback" not in result.output
        assert "KeyError" not in result.output
        assert "AttributeError" not in result.output


# ---------------------------------------------------------------------------
# T2-005-B: resilient consumer helper degrades gracefully on missing keys
# ---------------------------------------------------------------------------

class TestHealthDetailResilientConsumer:
    """Validate that _extract_* helpers degrade to 'unknown'/None when each
    top-level section is individually missing from the health detail payload.
    These helpers model what any future CLI or FE consumer SHOULD do.
    """

    # Full-payload baseline (should pass-through real values)

    def test_registry_full_payload(self):
        detail = {"registry": {"project_count": 3, "last_flush_status": "ok"}}
        result = _extract_registry(detail)
        assert result["project_count"] == 3
        assert result["last_flush_status"] == "ok"

    def test_db_full_payload(self):
        detail = {"db": {"size_bytes": 4096, "freelist_bytes": 0, "backend": "sqlite"}}
        result = _extract_db(detail)
        assert result["size_bytes"] == 4096
        assert result["backend"] == "sqlite"

    def test_retention_full_payload(self):
        detail = {"retention": {"last_run": None, "enabled": False}}
        result = _extract_retention(detail)
        assert result["enabled"] is False
        assert result["last_run"] is None

    # Missing top-level section

    def test_registry_missing_section_degrades_to_unknown(self):
        """registry key absent → project_count=None, last_flush_status='unknown'."""
        result = _extract_registry({})
        assert result["project_count"] is None
        assert result["last_flush_status"] == "unknown"

    def test_db_missing_section_degrades_to_unknown(self):
        """db key absent → size_bytes=None, backend='unknown'."""
        result = _extract_db({})
        assert result["size_bytes"] is None
        assert result["backend"] == "unknown"

    def test_retention_missing_section_degrades_to_unknown(self):
        """retention key absent → enabled=None, last_run=None."""
        result = _extract_retention({})
        assert result["enabled"] is None
        assert result["last_run"] is None

    # Wrong type for section (e.g. null/string instead of object)

    def test_registry_null_section_degrades_gracefully(self):
        result = _extract_registry({"registry": None})
        assert result["project_count"] is None
        assert result["last_flush_status"] == "unknown"

    def test_db_null_section_degrades_gracefully(self):
        result = _extract_db({"db": None})
        assert result["size_bytes"] is None
        assert result["backend"] == "unknown"

    def test_retention_null_section_degrades_gracefully(self):
        result = _extract_retention({"retention": None})
        assert result["enabled"] is None
        assert result["last_run"] is None

    # Partial section (some sub-keys missing)

    def test_registry_partial_section_fills_defaults(self):
        """registry present but last_flush_status missing → 'unknown'."""
        result = _extract_registry({"registry": {"project_count": 5}})
        assert result["project_count"] == 5
        assert result["last_flush_status"] == "unknown"

    def test_db_partial_section_fills_defaults(self):
        """db present but backend missing → 'unknown'."""
        result = _extract_db({"db": {"size_bytes": 8192, "freelist_bytes": 512}})
        assert result["size_bytes"] == 8192
        assert result["backend"] == "unknown"

    def test_retention_partial_section_fills_defaults(self):
        """retention present but enabled missing → None."""
        result = _extract_retention({"retention": {"last_run": "2026-06-01T00:00:00Z"}})
        assert result["last_run"] == "2026-06-01T00:00:00Z"
        assert result["enabled"] is None
