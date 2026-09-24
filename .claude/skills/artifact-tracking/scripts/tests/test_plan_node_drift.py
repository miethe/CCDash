#!/usr/bin/env python3
"""Tests for plan-node-drift.py (M4, operator-p0-state-integrity).

Offline, no network, no live `itt` CLI: every itt read is faked at the IttClient `runner` seam
(``_itt_client.IttClient(runner=...)``) — the same seam ``test_stamp_node_slug.py`` uses.

A fixture that cannot produce a mismatch proves only that it matches itself (plan rubric — "a
fixture bounds what green proves"), so this suite builds ONE clean world and then mutates a copy
of it (a real plan file rewritten with a skewed status, checked against the SAME live-shaped node)
to prove the tool can actually detect drift, not just echo agreement.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import _itt_client as itc  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


drift_mod = _load("plan_node_drift_mod", "plan-node-drift.py")


def _write_plan(path: Path, *, status: str, itt_node_id: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"status: {status}", "feature_slug: fixture-plan"]
    if itt_node_id:
        lines.append(f"itt_node_id: {itt_node_id}")
    lines += ["---", "", "# Fixture plan body", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


class _FakeItt:
    """Fake ``itt`` CLI runner. Only handles ``--json node get <id>`` — everything this tool needs."""

    def __init__(self, nodes: dict[str, dict[str, Any]]):
        self.nodes = nodes
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> itc.CliResult:
        self.calls.append(args)
        # args == ["--json", "node", "get", node_id]
        assert args[:3] == ["--json", "node", "get"]
        node_id = args[3]
        node = self.nodes.get(node_id)
        if node is None:
            return itc.CliResult(returncode=1, stdout="", stderr=f"not found: {node_id}")
        import json

        return itc.CliResult(returncode=0, stdout=json.dumps(node), stderr="")


def _client(nodes: dict[str, dict[str, Any]]) -> tuple[itc.IttClient, _FakeItt]:
    fake = _FakeItt(nodes)
    return itc.IttClient(runner=fake), fake


# ---------------------------------------------------------------------------
# Clean world: three tracked-shaped bindings, all agreeing.
# ---------------------------------------------------------------------------
def test_clean_world_reports_zero_mismatches(tmp_path: Path, capsys):
    plan_a = tmp_path / "plan-a.md"
    plan_b = tmp_path / "plan-b.md"
    _write_plan(plan_a, status="completed")
    _write_plan(plan_b, status="completed")

    nodes = {
        "node_A1": {"id": "node_A1", "status": "completed"},
        "node_A2": {"id": "node_A2", "status": "completed"},  # same file, second node (CF shape)
        "node_B1": {"id": "node_B1", "status": "completed"},
    }
    client, fake = _client(nodes)

    rc = drift_mod.main(
        [
            "--repo-root", str(tmp_path),
            "--binding", "plan-a.md:node_A1",
            "--binding", "plan-a.md:node_A2",
            "--binding", "plan-b.md:node_B1",
            "--json",
        ],
        client=client,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert '"mismatched": 0' in out
    assert '"errored": 0' in out
    # Confirms it actually talked to the (fake) API rather than trivially passing.
    assert len(fake.calls) == 3


def test_skewed_fixture_reports_nonzero(tmp_path: Path, capsys):
    """Same shape as the clean world, but one plan file is deliberately rewritten with a status
    that disagrees with its node — the tool must catch it, not just agree with itself."""
    plan_a = tmp_path / "plan-a.md"
    plan_b = tmp_path / "plan-b.md"
    _write_plan(plan_a, status="completed")
    # Skew: plan-b says waiting_human, its node says completed (the exact real-world shape found
    # on cross-harness-self-state-v1.md / BP-5 before this milestone's fix).
    _write_plan(plan_b, status="waiting_human")

    nodes = {
        "node_A1": {"id": "node_A1", "status": "completed"},
        "node_B1": {"id": "node_B1", "status": "completed"},
    }
    client, _fake = _client(nodes)

    rc = drift_mod.main(
        [
            "--repo-root", str(tmp_path),
            "--binding", "plan-a.md:node_A1",
            "--binding", "plan-b.md:node_B1",
            "--json",
        ],
        client=client,
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert '"mismatched": 1' in out
    assert "MISMATCH" in out


def test_alias_spellings_do_not_false_positive(tmp_path: Path, capsys):
    """A plan file spelled with a legacy alias ("complete") against a node spelled with its
    canonical NodeStatus ("completed") must NOT be reported as drift — the whole point of routing
    both sides through `_status_aliases.resolve()`."""
    plan = tmp_path / "plan.md"
    _write_plan(plan, status="complete")  # legacy alias, not the NodeStatus spelling

    nodes = {"node_X": {"id": "node_X", "status": "completed"}}
    client, _fake = _client(nodes)

    rc = drift_mod.main(
        ["--repo-root", str(tmp_path), "--binding", "plan.md:node_X", "--json"],
        client=client,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert '"mismatched": 0' in out


def test_missing_plan_status_is_an_error_not_a_mismatch(tmp_path: Path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text("---\nfeature_slug: no-status\n---\n\nbody\n", encoding="utf-8")

    nodes = {"node_X": {"id": "node_X", "status": "completed"}}
    client, _fake = _client(nodes)

    rc = drift_mod.main(
        ["--repo-root", str(tmp_path), "--binding", "plan.md:node_X", "--json"],
        client=client,
    )
    out = capsys.readouterr().out
    # An ERROR (unreadable side) is distinct from a MISMATCH (both sides read fine but disagree) —
    # it must not silently pass as clean, but it also must not be conflated with real drift.
    assert rc == 0
    assert '"errored": 1' in out
    assert '"mismatched": 0' in out


def test_unreachable_node_is_an_error_and_does_not_force_exit_2(tmp_path: Path, capsys):
    """The API being unreachable is exactly the case the attaching hook must survive — the check
    itself must not conflate 'could not verify' with 'found drift'."""
    plan = tmp_path / "plan.md"
    _write_plan(plan, status="completed")

    client, _fake = _client(nodes={})  # node_X is absent -> fake returns rc=1 "not found"

    rc = drift_mod.main(
        ["--repo-root", str(tmp_path), "--binding", "plan.md:node_X", "--json"],
        client=client,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert '"errored": 1' in out


def test_direct_plan_binding_via_own_itt_node_id(tmp_path: Path, capsys):
    """--plan resolves the node id from the plan file's own itt_node_id frontmatter (the same
    binding shape rf-swarm/cross-harness now carry) rather than requiring --binding."""
    plan = tmp_path / "plan.md"
    _write_plan(plan, status="completed", itt_node_id="node_X")

    nodes = {"node_X": {"id": "node_X", "status": "completed"}}
    client, _fake = _client(nodes)

    rc = drift_mod.main(
        ["--repo-root", str(tmp_path), "--plan", "plan.md", "--json"],
        client=client,
    )
    assert rc == 0


def test_no_bindings_is_a_usage_error_not_a_silent_clean_pass(tmp_path: Path, monkeypatch):
    """0 bindings checked must never render as '0 mismatches' — that would be indistinguishable
    from an actually-clean run and defeats the whole point of the check."""
    # No explicit --binding/--bindings-file/--plan, AND no default bindings file reachable.
    monkeypatch.setattr(drift_mod, "DEFAULT_BINDINGS_FILE", tmp_path / "does-not-exist.json")
    rc = drift_mod.main(["--repo-root", str(tmp_path)], client=itc.IttClient(runner=_FakeItt({})))
    assert rc == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
