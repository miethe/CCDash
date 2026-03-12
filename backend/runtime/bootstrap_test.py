"""Test bootstrap with incidental background work disabled."""
from __future__ import annotations

from fastapi import FastAPI

from backend.runtime.bootstrap import build_runtime_app


def build_test_app() -> FastAPI:
    return build_runtime_app("test")


app = build_test_app()
