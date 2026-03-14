"""Hosted-style API bootstrap."""
from __future__ import annotations

from fastapi import FastAPI

from backend.runtime.bootstrap import build_runtime_app


def build_api_app() -> FastAPI:
    return build_runtime_app("api")


app = build_api_app()
