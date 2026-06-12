#!/usr/bin/env python3
"""Regenerate docs/openapi/ccdash-v1.json from the live application OpenAPI schema.

Usage (from repo root, with the backend venv active):
    python scripts/regen-openapi-v1.py

The script:
1. Builds the test runtime app (no live DB required — uses a temp SQLite file).
2. Calls app.openapi() to get the full schema.
3. Filters paths to those starting with /api/v1 and collects the referenced schemas.
4. Writes docs/openapi/ccdash-v1.json (pretty-printed, UTF-8, trailing newline).

Run this whenever you add, rename, or remove a route or response model under
/api/v1.  Commit the result alongside your code change so the spec stays in
sync with the implementation.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ensure the repo root and worktree package sources are on sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
# Worktree-local package sources take precedence over the editable venv install
# so that worktree-local contract changes are reflected without a venv reinstall.
for _pkg_src in [
    _REPO_ROOT / "packages" / "ccdash_contracts" / "src",
    _REPO_ROOT / "packages" / "ccdash_cli" / "src",
]:
    _s = str(_pkg_src)
    if _s not in sys.path:
        sys.path.insert(1, _s)

OUTPUT = _REPO_ROOT / "docs" / "openapi" / "ccdash-v1.json"


def _build_filtered_schema() -> dict:
    """Return an OpenAPI schema containing only /api/v1 paths + their components."""
    tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmpdb.close()

    with patch.dict(
        os.environ,
        {"CCDASH_DB_PATH": tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
    ):
        from backend.runtime.bootstrap import build_runtime_app

    patches = [
        patch("backend.runtime.container.initialize_observability"),
        patch("backend.runtime.container.shutdown_observability"),
        patch(
            "backend.adapters.jobs.runtime.file_watcher.start",
            new_callable=lambda: lambda: AsyncMock(),
        ),
        patch(
            "backend.adapters.jobs.runtime.file_watcher.stop",
            new_callable=lambda: lambda: AsyncMock(),
        ),
        patch(
            "backend.runtime_ports.db_project_manager.get_active_project",
            return_value=None,
        ),
    ]
    for p in patches:
        p.start()

    try:
        app = build_runtime_app("test")
        full_schema: dict = copy.deepcopy(app.openapi())
    finally:
        for p in reversed(patches):
            p.stop()
        try:
            os.unlink(tmpdb.name)
        except OSError:
            pass

    # Filter paths to /api/v1 only.
    v1_paths = {
        path: definition
        for path, definition in full_schema.get("paths", {}).items()
        if path.startswith("/api/v1")
    }

    # Collect $ref schema names referenced by v1 paths so we can include only
    # the relevant components/schemas entries.
    import re
    raw = json.dumps(v1_paths)
    ref_names = set(re.findall(r'"#/components/schemas/([^"]+)"', raw))

    components = full_schema.get("components", {})
    schemas = components.get("schemas", {})
    # Include directly referenced schemas + transitively referenced ones (one level).
    included: set[str] = set()
    queue = list(ref_names)
    while queue:
        name = queue.pop()
        if name in included or name not in schemas:
            continue
        included.add(name)
        nested_refs = set(re.findall(r'"#/components/schemas/([^"]+)"', json.dumps(schemas[name])))
        queue.extend(nested_refs - included)

    filtered_schemas = {k: schemas[k] for k in sorted(included) if k in schemas}

    result = {
        "openapi": full_schema.get("openapi", "3.1.0"),
        "info": {
            "title": "CCDash External API v1",
            "description": (
                "Versioned external API for IntentTree and LAN agents. "
                "See docs/guides/external-api-lan-deployment.md for operator guidance."
            ),
            "version": full_schema.get("info", {}).get("version", "0.1.0"),
        },
        "paths": v1_paths,
        "components": {"schemas": filtered_schemas},
    }
    return result


def main() -> None:
    print(f"Building /api/v1 OpenAPI schema → {OUTPUT}")
    schema = _build_filtered_schema()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path_count = len(schema.get("paths", {}))
    schema_count = len(schema.get("components", {}).get("schemas", {}))
    print(f"  {path_count} paths, {schema_count} component schemas")
    print(f"  Written: {OUTPUT}")


if __name__ == "__main__":
    main()
