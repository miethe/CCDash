"""Shared test fixtures for ccdash_cli tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove CCDash env vars so tests start from a known state."""
    for var in ("CCDASH_TARGET", "CCDASH_URL", "CCDASH_TOKEN", "CCDASH_PROJECT"):
        monkeypatch.delenv(var, raising=False)
