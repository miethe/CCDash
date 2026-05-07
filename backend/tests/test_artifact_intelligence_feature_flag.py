import importlib
import logging
import os

import pytest

from backend import config
from backend.services import agentic_intelligence_flags


FLAG_NAME = "CCDASH_ARTIFACT_INTELLIGENCE_ENABLED"


@pytest.fixture(autouse=True)
def restore_artifact_intelligence_flag():
    original = os.environ.get(FLAG_NAME)
    yield
    if original is None:
        os.environ.pop(FLAG_NAME, None)
    else:
        os.environ[FLAG_NAME] = original
    importlib.reload(config)
    importlib.reload(agentic_intelligence_flags)


def _reload_with_flag(value: str | None):
    if value is None:
        os.environ.pop(FLAG_NAME, None)
    else:
        os.environ[FLAG_NAME] = value
    importlib.reload(config)
    return importlib.reload(agentic_intelligence_flags)


def test_artifact_intelligence_flag_defaults_false() -> None:
    flags = _reload_with_flag(None)

    assert config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED is False
    assert flags.artifact_intelligence_enabled() is False


def test_artifact_intelligence_flag_reads_true_env_value() -> None:
    flags = _reload_with_flag("true")

    assert config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED is True
    assert flags.artifact_intelligence_enabled() is True


def test_disabled_stub_imports_and_reports_disabled_state(caplog) -> None:
    flags = _reload_with_flag(None)

    caplog.set_level(logging.INFO, logger="ccdash.artifact_intelligence")
    status = flags.report_artifact_intelligence_disabled("unit-test")

    assert status == {
        "enabled": False,
        "reason": "artifact intelligence disabled",
        "context": "unit-test",
    }
    assert "artifact intelligence disabled" in caplog.text


def test_disabled_stub_reports_enabled_without_logging(caplog) -> None:
    flags = _reload_with_flag("1")

    caplog.set_level(logging.INFO, logger="ccdash.artifact_intelligence")
    status = flags.report_artifact_intelligence_disabled("unit-test")

    assert status == {"enabled": True, "reason": "", "context": "unit-test"}
    assert "artifact intelligence disabled" not in caplog.text
