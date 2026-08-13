"""Entry point for ``python -m ccdash_cli``.

Thin re-export so the idiomatic package-level invocation
(``python -m ccdash_cli ...``) behaves identically to both the
``ccdash-cli`` console script and ``python -m ccdash_cli.main``.
"""
from __future__ import annotations

from ccdash_cli.main import app

if __name__ == "__main__":
    app()
