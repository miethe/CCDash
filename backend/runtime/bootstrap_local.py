"""Local convenience bootstrap."""
from __future__ import annotations

from fastapi import FastAPI

from backend.runtime.bootstrap import build_runtime_app


def build_local_app() -> FastAPI:
    return build_runtime_app("local")


app = build_local_app()
