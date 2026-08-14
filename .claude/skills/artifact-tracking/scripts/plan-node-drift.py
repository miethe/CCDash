#!/usr/bin/env python3
"""M4 (operator-p0-state-integrity) drift check — plan-frontmatter `status` vs bound-node status.

Report-only, by design (plan decision OQ-3): this tool NEVER writes to a node or a plan file. It
exists to make a class of drift visible that was previously silent — three real plans/nodes were
found disagreeing (tracker `node_01KZ9B4KJ1CJPMVN78ZFE9AT1A`) with nothing to detect it. Writing a
fix (e.g. closing a stale node) would make this a gated writeback class, which is explicitly out
of this plan's scope; report-only keeps it inside the non-fatal sibling contract it attaches to
(`sdlc-sync.sh`, `finding-sweep.sh`, `provision-artifacts.sh`).

Bindings resolve two ways, most-explicit first:
  1. ``--binding <plan_ref>:<node_id>`` (repeatable) or ``--bindings-file <path>`` (JSON/YAML list
     of ``{"plan_ref": ..., "node_id": ...}``) — the caller names the pair directly. This is the
     path a single-file hook invocation uses (see ``sdlc-sync.sh``'s ``SDLC_SYNC_FILE`` +
     ``ITT_NODE_ID``) and the path the default tracked-bindings file (below) uses.
  2. A plan file that carries BOTH ``itt_node_id`` and ``feature_slug`` in its own frontmatter
     resolves itself via ``_slug_resolution``'s direct path — pass its path with ``--plan`` and no
     node id is needed.

Status comparison normalizes BOTH sides through the same alias table a node's own `status` field
is already drawn from (`_status_aliases.NODE_STATUSES` / `resolve()`) — a plan file spelled
`"complete"` and a node spelled `"completed"` are NOT reported as drift; a plan file spelled
`"waiting_human"` against a node `"completed"` IS.

Same JSON / exit-code convention as `verify-slug-roundtrip.py`: 0 = every checked binding agrees,
2 = one or more mismatches, 1 = usage error. A binding whose node or plan file cannot be read at
all is reported as an ERROR row (not silently skipped) but does not by itself force exit 2 —
only a genuine status MISMATCH does; an unreachable API is exactly the case the attaching hook
must survive non-fatally (see `sdlc-sync.sh`).

Reaches IntentTree exclusively through the injectable `_itt_client.IttClient` seam (read-only:
`get_node` only) so the whole comparison is testable offline with a fake runner — no live network
call in the test suite.

Python 3.10+ floor (must import on the node's 3.11 — no 3.12-only syntax).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _itt_client as itc  # noqa: E402
import _slug_resolution as sr  # noqa: E402
import _status_aliases as sa  # noqa: E402

# The default bindings this check runs against when no --binding/--bindings-file/--plan is given —
# the "three tracked cases" named in the M4 tracker node body and its AC table's "M4 bindings" row
# (node_01KYWWZVSMZQ0NSGSTHAZ7BSMW + its parent node_01KYWWZ832QW2Q79PATCG7B66D + BP-5). Kept as
# data, not a hardcoded literal in the comparison logic, so a caller can override wholesale via
# --bindings-file without editing this script.
DEFAULT_BINDINGS_FILE = (
    Path(__file__).resolve().parent / "tracked-plan-node-bindings.json"
)


class DriftError(RuntimeError):
    """A binding could not be evaluated at all (unreadable file, unreachable API, bad shape)."""


def _read_plan_status(plan_path: Path) -> str | None:
    """Read the plan file's own `status` frontmatter scalar. None if absent/unreadable."""
    scalars = sr.scan_frontmatter_scalars(plan_path)
    return scalars.get("status")


def _normalize(raw: str | None) -> tuple[str | None, str]:
    """Return (canonical_status_or_None, category) — category is one of the _status_aliases
    categories, plus "missing" when *raw* is None."""
    if raw is None:
        return None, "missing"
    canonical, _maturity, category = sa.resolve(raw)
    return canonical, category


def check_binding(
    client: itc.IttClient, plan_ref: str, node_id: str, repo_root: Path
) -> dict[str, Any]:
    """Evaluate one (plan_ref, node_id) pair. Never raises — errors become an ERROR-status row,
    which is deliberately distinct from a status MISMATCH (see module docstring)."""
    row: dict[str, Any] = {"plan_ref": plan_ref, "node_id": node_id}

    plan_path = Path(plan_ref)
    if not plan_path.is_absolute():
        plan_path = repo_root / plan_path
    if not plan_path.is_file():
        row["status"] = "ERROR"
        row["error_class"] = "binding"
        row["reason"] = f"plan file does not exist: {plan_ref}"
        return row

    plan_status_raw = _read_plan_status(plan_path)
    plan_status, plan_category = _normalize(plan_status_raw)
    row["plan_status_raw"] = plan_status_raw
    row["plan_status"] = plan_status

    try:
        node = client.get_node(node_id)
    except Exception as exc:  # noqa: BLE001 — deliberately broad: ANY read failure (the itt CLI
        # missing entirely, a network timeout, a malformed response) must become an ERROR row
        # rather than an uncaught traceback. This is what makes "the API is unreachable" survive
        # non-fatally when this script is shelled out from sdlc-sync.sh — a crash here would exit
        # non-zero for a reason the hook's own rc==2/else-nonzero branching can't distinguish from
        # a real detection, and `itc.IttError` alone does not cover a missing `itt` binary
        # (subprocess.run raises FileNotFoundError, not IttError, in that case).
        row["status"] = "ERROR"
        row["error_class"] = "unreachable"
        row["reason"] = f"could not read node {node_id}: {exc}"
        return row

    node_status_raw = node.get("status")
    node_status, node_category = _normalize(node_status_raw)
    row["node_status_raw"] = node_status_raw
    row["node_status"] = node_status

    if plan_category == "missing":
        row["status"] = "ERROR"
        row["error_class"] = "binding"
        row["reason"] = f"plan file {plan_ref} carries no `status` frontmatter"
        return row
    if plan_category == "hand_review":
        row["status"] = "ERROR"
        row["error_class"] = "binding"
        row["reason"] = f"plan status {plan_status_raw!r} is neither a NodeStatus nor a known alias"
        return row
    if node_category == "hand_review":
        row["status"] = "ERROR"
        row["error_class"] = "binding"
        row["reason"] = f"node status {node_status_raw!r} is not a recognized NodeStatus"
        return row

    if plan_status == node_status:
        row["status"] = "OK"
        return row

    row["status"] = "MISMATCH"
    row["reason"] = (
        f"plan frontmatter status ({plan_status_raw!r} -> {plan_status!r}) disagrees with "
        f"bound node status ({node_status_raw!r} -> {node_status!r})"
    )
    return row


def load_bindings_file(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        import yaml  # local import — only needed for the YAML shape

        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, list):
        raise DriftError(f"{path} must contain a JSON/YAML list of {{plan_ref, node_id}} objects")
    out: list[dict[str, str]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "plan_ref" not in item or "node_id" not in item:
            raise DriftError(f"{path}[{i}] is not a {{plan_ref, node_id}} object: {item!r}")
        out.append({"plan_ref": str(item["plan_ref"]), "node_id": str(item["node_id"])})
    return out


def resolve_bindings(args: argparse.Namespace, repo_root: Path) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []

    for spec in args.binding or []:
        if ":" not in spec:
            raise DriftError(f"--binding must be <plan_ref>:<node_id>, got {spec!r}")
        plan_ref, node_id = spec.split(":", 1)
        bindings.append({"plan_ref": plan_ref, "node_id": node_id})

    if args.bindings_file:
        bindings.extend(load_bindings_file(Path(args.bindings_file)))

    for plan_ref in args.plan or []:
        plan_path = Path(plan_ref)
        if not plan_path.is_absolute():
            plan_path = repo_root / plan_path
        scalars = sr.scan_frontmatter_scalars(plan_path)
        node_id = scalars.get("itt_node_id")
        if not node_id:
            raise DriftError(
                f"--plan {plan_ref} carries no itt_node_id frontmatter — pass "
                f"--binding {plan_ref}:<node_id> explicitly instead"
            )
        bindings.append({"plan_ref": plan_ref, "node_id": node_id})

    if not bindings and not args.binding and not args.bindings_file and not args.plan:
        # Nothing explicit at all -> fall back to the default tracked set, IF it exists. A repo
        # without this file (e.g. a fresh checkout of just this script) gets a clean usage error
        # instead of a silent empty pass — "0 mismatches because 0 bindings" must never look like
        # a real clean run.
        if DEFAULT_BINDINGS_FILE.is_file():
            bindings.extend(load_bindings_file(DEFAULT_BINDINGS_FILE))

    return bindings


def main(argv: list[str] | None = None, client: itc.IttClient | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compare plan-frontmatter `status` against bound IntentTree node status. "
            "Read-only — never writes to a node or a file."
        )
    )
    ap.add_argument(
        "--binding",
        action="append",
        metavar="PLAN_REF:NODE_ID",
        help="An explicit plan_ref:node_id pair to check. Repeatable.",
    )
    ap.add_argument(
        "--bindings-file",
        default=None,
        help="JSON/YAML file of [{plan_ref, node_id}, ...] pairs to check.",
    )
    ap.add_argument(
        "--plan",
        action="append",
        metavar="PLAN_REF",
        help="A plan file that carries its own itt_node_id frontmatter. Repeatable.",
    )
    ap.add_argument("--repo-root", default=".", help="Root plan_ref paths resolve against.")
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()

    try:
        bindings = resolve_bindings(args, repo_root)
    except DriftError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if not bindings:
        sys.stderr.write(
            "error: no bindings to check — pass --binding/--bindings-file/--plan, or seed "
            f"{DEFAULT_BINDINGS_FILE}\n"
        )
        return 1

    client = client or itc.IttClient()
    results = [check_binding(client, b["plan_ref"], b["node_id"], repo_root) for b in bindings]

    mismatches = [r for r in results if r["status"] == "MISMATCH"]
    errors = [r for r in results if r["status"] == "ERROR"]
    # An ERROR row is one of two very different things (karen/codex review, M4 follow-up):
    #   - "binding": a plan file that does not exist, carries no status, or a status on either side
    #     that is not a recognized NodeStatus. These are ACTIONABLE — exactly what the check exists
    #     to surface — so they must be as loud as a MISMATCH.
    #   - "unreachable": the node API/CLI could not be reached. This is transient and must stay
    #     quiet under the hook's non-fatal sibling contract.
    # Bucketing both as a bare "errored" count (and returning 0 for them) is what let an actionable
    # malformed binding produce no output on the only automated path. Split them, and let a binding
    # error force the same exit 2 a mismatch does so the hook's existing rc==2 echo path carries it.
    binding_errors = [r for r in errors if r.get("error_class") == "binding"]
    unreachable_errors = [r for r in errors if r.get("error_class") != "binding"]
    summary = {
        "checked": len(results),
        "ok": len(results) - len(mismatches) - len(errors),
        "mismatched": len(mismatches),
        "errored": len(errors),
        "binding_errors": len(binding_errors),
        "unreachable_errors": len(unreachable_errors),
    }

    if args.json:
        print(json.dumps({"summary": summary, "results": results}, indent=2))
    else:
        print(f"[plan-node-drift] checked {summary['checked']} binding(s)")
        for r in results:
            line = f"  [{r['status']}] {r['plan_ref']}  node={r['node_id']}"
            if r["status"] != "OK":
                line += f"\n    reason: {r['reason']}"
            print(line)
        print("\n  summary:")
        for k, v in summary.items():
            print(f"    {k}={v}")

    # Exit 2 for a real detection the hook must echo: a status MISMATCH OR an actionable binding
    # error. An unreachable-only run returns 0 and stays quiet, preserving the non-fatal contract.
    return 2 if (mismatches or binding_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
