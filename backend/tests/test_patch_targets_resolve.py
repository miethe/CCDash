"""Guard: every string ``mock.patch`` target in the backend suite must resolve.

Why this exists
---------------
``unittest.mock.patch("a.b.c")`` resolves its target at *patch time*, not at import
time.  If ``c`` is renamed or removed, the patch raises ``AttributeError`` during
setup — so when the patch lives in ``setUpClass``, **every test in the file errors
before its body runs** and the file becomes silently dead coverage.

That happened: ADR-006 replaced ``backend.runtime_ports.project_manager`` with
``db_project_manager``, and three patch sites were left pointing at the removed
attribute.  ``test_client_v1_contract.py`` (37 tests) and
``test_client_v1_feature_surface.py`` (6 tests) were 100% dead, plus one test in
``test_runtime_bootstrap.py``.

This test closes the class rather than the instance: it walks every test module,
extracts the literal string target of each ``patch(...)`` call, and asserts the
dotted path still resolves.  It is a static/attribute check only — it never runs
the tests, so it stays fast and has no fixture dependencies.

Deliberate limitations (documented so a future reader does not mistake them for bugs):
  * Only string-literal first arguments are checked.  ``patch(SOME_CONST)`` and
    f-string targets are skipped — they cannot be resolved without executing code.
  * ``patch.object`` / ``patch.dict`` are skipped: their first argument is an
    object or mapping, not a dotted path.
  * ``create=True`` patches (intentionally patching a non-existent attribute) are
    skipped, since a missing attribute is legal there.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent


def _iter_patch_targets() -> list[tuple[str, str, int]]:
    """Return ``(dotted_target, file, lineno)`` for every literal patch target."""
    found: list[tuple[str, str, int]] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Accept bare `patch(...)`; reject `patch.object(...)` / `patch.dict(...)`,
            # whose first argument is not a dotted path.
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
                if name in {"object", "dict", "multiple", "stopall"}:
                    continue
            else:
                continue
            if name != "patch":
                continue
            if any(kw.arg == "create" for kw in node.keywords):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            target = first.value
            if "." not in target:
                continue
            found.append((target, str(path.relative_to(TESTS_DIR)), node.lineno))
    return found


def _resolve(target: str) -> str | None:
    """Return None if ``target`` resolves, else a human-readable reason."""
    parts = target.split(".")
    module = None
    remainder: list[str] = []
    # Walk the longest importable module prefix inward: `a.b.c.d` may be module
    # `a.b` with attribute chain `c.d`.
    for split_at in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:split_at]))
        except Exception:  # noqa: BLE001 - any import failure just means "not here"
            continue
        remainder = parts[split_at:]
        break
    if module is None:
        return "no importable module prefix"

    obj = module
    for attr in remainder:
        if not hasattr(obj, attr):
            return f"missing attribute {attr!r}"
        obj = getattr(obj, attr)
    return None


def test_all_string_patch_targets_resolve() -> None:
    """A stale patch target silently kills whole test files — fail loudly instead."""
    targets = _iter_patch_targets()
    assert targets, "found no literal patch() targets — the AST walk is broken"

    # Resolve each unique target once; report every distinct site that uses it.
    sites: dict[str, list[str]] = {}
    for target, file, lineno in targets:
        sites.setdefault(target, []).append(f"{file}:{lineno}")

    failures: list[str] = []
    for target, where in sorted(sites.items()):
        reason = _resolve(target)
        if reason is not None:
            locations = ", ".join(sorted(where))
            failures.append(f"  {target}\n      {reason}\n      used at: {locations}")

    if failures:
        pytest.fail(
            "Unresolvable mock.patch target(s) — these patches raise AttributeError at "
            "setup, so every test relying on them errors before its body runs:\n"
            + "\n".join(failures),
            pytrace=False,
        )
