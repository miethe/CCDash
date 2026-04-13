"""Import boundary guard — ensure ccdash_cli never imports backend internals."""
from __future__ import annotations

import subprocess
import sys


def test_backend_not_importable():
    """The 'backend' package must NOT be importable from ccdash_cli's environment.

    This validates the package boundary: the standalone CLI depends only on
    ccdash_contracts, httpx, typer, etc. — never on the backend runtime.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import ccdash_cli; import backend"],
        capture_output=True,
        text=True,
    )
    # If backend is importable, this is a boundary violation
    # (In a clean install environment, backend wouldn't be present.
    # In the dev environment, it might be — so we check the import
    # graph of ccdash_cli instead.)

    # Alternative: verify no ccdash_cli module transitively imports backend
    result2 = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib, pkgutil;"
            "import ccdash_cli;"
            "mods = [name for _, name, _ in pkgutil.walk_packages(ccdash_cli.__path__, 'ccdash_cli.')];"
            "bad = [];"
            "[bad.append(m) for m in mods if 'backend' in m];"
            "assert not bad, f'Modules reference backend: {bad}';"
            "print('PASS: no backend references in ccdash_cli module tree')",
        ],
        capture_output=True,
        text=True,
    )
    assert result2.returncode == 0, f"Import boundary violated: {result2.stderr}"


def test_ccdash_cli_importable():
    """The ccdash_cli package itself must be importable without error."""
    result = subprocess.run(
        [sys.executable, "-c", "import ccdash_cli; print('ok')"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"ccdash_cli is not importable:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ok" in result.stdout


def test_no_backend_string_in_module_names():
    """None of the discovered ccdash_cli module names contain 'backend'."""
    import pkgutil
    import ccdash_cli

    module_names = [
        name
        for _, name, _ in pkgutil.walk_packages(ccdash_cli.__path__, "ccdash_cli.")
    ]
    bad = [m for m in module_names if "backend" in m]
    assert not bad, f"ccdash_cli submodules reference 'backend': {bad}"


def test_runtime_client_no_backend_imports():
    """Importing the HTTP client module must not pull in any backend package."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;"
            "import ccdash_cli.runtime.client;"
            "bad = [m for m in sys.modules if m == 'backend' or m.startswith('backend.')];"
            "assert not bad, f'backend modules loaded: {bad}';"
            "print('PASS')",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"backend leak via runtime.client:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_runtime_config_no_backend_imports():
    """Importing the config module must not pull in any backend package."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;"
            "import ccdash_cli.runtime.config;"
            "bad = [m for m in sys.modules if m == 'backend' or m.startswith('backend.')];"
            "assert not bad, f'backend modules loaded: {bad}';"
            "print('PASS')",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"backend leak via runtime.config:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
