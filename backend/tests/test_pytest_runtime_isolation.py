"""Exercise collection-time runtime isolation in real xdist workers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PytestRuntimeIsolationTests(unittest.TestCase):
    def test_workers_replace_inherited_runtime_paths_before_backend_imports(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix=".pytest-isolation-", dir=repo) as tmp:
            probe_dir = Path(tmp)
            probe = probe_dir / "test_worker_paths.py"
            probe.write_text('''\
import json
import os
from pathlib import Path
import sqlite3
import pytest
from backend import config
from backend.project_manager import project_manager

@pytest.mark.parametrize("item", range(4))
def test_worker_runtime(item):
    root = config.LOCAL_STORAGE_ROOT
    assert root.exists()
    assert config.DB_PATH.is_relative_to(root)
    assert config.PROJECTS_FILE.is_relative_to(root)
    assert config.PROJECTS_FILE.exists()
    assert not str(root).startswith("/unwritable-inherited-runtime")
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.DB_PATH) as db:
        assert db.execute("SELECT 1").fetchone() == (1,)
    destination = Path(os.environ["CCDASH_ISOLATION_PROBE_DIR"])
    worker = os.environ["PYTEST_XDIST_WORKER"]
    (destination / (worker + ".json")).write_text(json.dumps({
        "root": str(root), "registry": str(config.PROJECTS_FILE),
        "database": str(config.DB_PATH),
    }))
''', encoding="utf-8")
            env = dict(os.environ)
            env.update({
                "CCDASH_LOCAL_STORAGE_ROOT": "/unwritable-inherited-runtime",
                "CCDASH_DB_PATH": "/unwritable-inherited-runtime/cache.db",
                "CCDASH_PROJECTS_FILE": "/unwritable-inherited-runtime/projects.json",
                "CCDASH_ISOLATION_PROBE_DIR": str(probe_dir),
            })
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-n", "2", str(probe)],
                cwd=repo, env=env, capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            records = [json.loads(path.read_text()) for path in probe_dir.glob("gw*.json")]
            self.assertEqual(len(records), 2, result.stdout + result.stderr)
            for field in ("root", "registry", "database"):
                self.assertEqual(len({record[field] for record in records}), 2)
            self.assertTrue(all(not Path(record["root"]).exists() for record in records))
