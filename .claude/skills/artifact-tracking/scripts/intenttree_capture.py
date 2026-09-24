#!/usr/bin/env python3
"""IntentTree SDLC capture/sync — orchestrates plan & progress artifacts into IntentTree nodes.

Thin shim (normalization is server-side — DI-103/104/105 resolved 2026-06-20)
----------------------------------------------------------------------------
The backend now parses raw file content (PyYAML) and owns ALL task normalization: title
fallback from description (DI-104), points-alias/unit parsing (DI-104), and status→progress
derivation (DI-105). This script no longer normalizes; it only *orchestrates* the native server
sync path — the same ``/source-artifacts`` register + ``/work-item-sync/import`` endpoints
``itt sync import`` uses. It discovers which files belong to which feature (aggregating a
feature's phase files, and capturing catch-all dirs per-file — DI-107), then POSTs the raw
aggregated tasks for the backend to normalize and graft. It also forwards the plan/PRD
*structural* frontmatter and a per-phase frontmatter map (``open_questions``, ``decisions``,
``meta_plan_refs``, ``wave_plan``, ``origin``/``planning_maturity``) — extracting a "Decisions"
table from the plan body when frontmatter omits it — so the backend fills the plan-lens container
aggregates instead of leaving them hollow (P1/P2, DI-134).

Retirement: this shim is slated for removal after a burn-in release (OQ-4; see
``docs/project_plans/design-specs/awpr-v2-shim-removal.md``). Source of truth stays the markdown:
this only does source → node (a derived projection).

ANTI-CLOBBER NOTICE (DI-323)
-----------------------------
This file was silently overwritten wholesale by a deployed->canonical artifact sync
(commit ``e8b8bb2``), which dropped the DI-134/142/144/161 helpers below (structural
frontmatter forwarding, decisions-table extraction, flat-plan containers, specs-awaiting-plan
discovery) while it happened to be carrying genuine new work of its own (creation-time slug
stamping, ``_itt_client`` integration, the ``wave_plan.phases[]`` fallback). DI-323 reconciled
both lineages by hand. The actual deployed<->canonical sync tool lives in a separate repo
(``agentic_meta_dev`` — see ``docs/ARTIFACT-UPSTREAM-REGISTRY.md``'s "edit upstream, never a
deployed copy" rule); **do not let a future sync replace this file wholesale again** — any
future reconciliation MUST take the union of both lineages' additions, never a one-sided
overwrite. ``PUBLIC_API`` below + its regression test
(``backend/tests/unit/test_intenttree_capture_shim.py``) exist to catch a silent recurrence.

Modes
-----
  # one artifact (used by the auto-sync hook on a status write):
  intenttree_capture.py sync   <plan-or-progress-file> --tree <tree_id> [--apply]

  # backfill every in-flight feature in a repo (one-time / periodic):
  intenttree_capture.py backfill --repo-root <path> --tree <tree_id> [--apply] [--cutoff YYYY-MM-DD]

Config (CLI flag > env > default):
  --api-url   / INTENTTREE_API_URL    (default http://10.42.10.76:8032)
  --workspace / INTENTTREE_WORKSPACE
  --tree      / INTENTTREE_TREE

A feature = one plan/PRD (the container, idempotency key = its path) + all tasks aggregated
from its `.claude/progress/<feature_slug>/phase-*.md` files. Each task is grafted under a
"Phase N" container beneath the feature. Re-running is idempotent (keyed on
(source_artifact_id, source_task_id)); completed leaves are marked done so rollups are faithful.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("intenttree_capture: PyYAML required (pip install pyyaml)\n")
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _itt_client as itc  # noqa: E402

DEFAULT_API = os.environ.get("INTENTTREE_API_URL", "http://10.42.10.76:8032")
COMPLETE = {"completed", "complete", "done", "superseded", "archived",
            "cancelled", "merged", "shipped", "resolved"}
VALID_KINDS = {"prd", "implementation_plan", "phase_plan", "feature_contract", "spike",
               "design_spec", "progress", "worknote", "report", "human_brief",
               "meta_plan", "exploration_charter", "decisions_block", "context_file",
               "charter", "other"}


# --------------------------------------------------------------- creation-time slug stamp
# M4 L4: stamp ``meta.feature_slug`` (+``meta.plan_ref``) onto the nodes a capture just created,
# so the ledger join never reopens the gap. The read-merge-write-via-PATCH discipline and the
# FR-7 conflict rule are load-bearing — we REUSE ``stamp-node-slug.py`` verbatim rather than
# re-implement either (``itt node update --meta`` REPLACES the whole meta dict server-side, so a
# naive write would destroy ``plan_ref``/``fingerprint``). The stamper filename has hyphens, so
# it is loaded via importlib rather than a plain import.
_STAMP_MOD: Any = None


def _stamp_module() -> Any:
    global _STAMP_MOD
    if _STAMP_MOD is None:
        path = Path(__file__).resolve().parent / "stamp-node-slug.py"
        spec = importlib.util.spec_from_file_location("stamp_node_slug_mod", path)
        if spec is None or spec.loader is None:  # pragma: no cover - packaging guard
            raise RuntimeError(f"cannot load stamper module at {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _STAMP_MOD = mod
    return _STAMP_MOD


def stamp_created_nodes(
    tree: str,
    slug: str,
    *,
    repo_root: str | None,
    plan_root: str | None,
    api_url: str,
    itt_client: itc.IttClient | None = None,
) -> dict:
    """Stamp ``meta.feature_slug`` (+``plan_ref``) onto the nodes just created for *slug*.

    Reuses ``stamp-node-slug.py``'s ``gather``/``classify``/``apply_stamps`` pipeline unchanged —
    including its anchor/subtree resolution, its FR-7 "never overwrite a differing feature_slug"
    conflict rule, its read-merge-write PATCH, and its idempotency — then narrows the resolved
    candidate set to the single feature captured this run (``c.slug == slug``). Callers invoke
    this only after a successful ``--apply`` import; dry-run never reaches here.
    """
    stamp = _stamp_module()
    client = itt_client or itc.IttClient(api_url=api_url)
    root = Path(repo_root or ".").resolve()
    proot = Path(plan_root) if plan_root else root / "docs" / "project_plans"
    if not proot.is_absolute():
        proot = root / proot

    nodes, candidates, _rejected, _ambiguous = stamp.gather(client, tree, proot, root)
    scoped = {nid: cand for nid, cand in candidates.items() if cand.slug == slug}
    would_stamp, already_correct, conflicts = stamp.classify(nodes, scoped)
    applied = stamp.apply_stamps(client, would_stamp)
    return {
        "ok": not conflicts,
        "slug": slug,
        "stamped": applied,
        "would_stamp": len(would_stamp),
        "already_correct": len(already_correct),
        "conflicts": conflicts,
    }


# --------------------------------------------------------------------------- HTTP
def _req(api: str, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    data = json.dumps(body, default=str).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(api + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, None


# --------------------------------------------------------------------- frontmatter
def load_fm(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        fm = yaml.safe_load(text[3:end])
        return fm if isinstance(fm, dict) else {}
    except Exception:
        return {}


def to_date(v: Any) -> datetime.date | None:
    if v is None:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v))
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except Exception:
        return None


def phase_label(fm: dict, path: Path) -> str:
    p = fm.get("phase")
    if p is not None and str(p).strip():
        return f"Phase {p}"
    m = re.search(r"phase-(\w+)", path.name)
    return f"Phase {m.group(1)}" if m else "Phase 1"


def _collect_phase(p: dict, plan_status: str, seen: set[str]) -> dict | None:
    """Map a ``wave_plan.phases[]`` milestone entry into the task-shaped dict `capture_feature()`
    already consumes unchanged (this fallback fires when a doctrine-conformant plan has no
    ``tasks[]`` — see `plan-doctrine.md` rule 2, "milestones, not phases").

    Unlike ``_collect_task()`` (a thin passthrough — the backend normalizes everything a task row
    carries), this is a deliberate narrow *allowlist*: a phase entry can carry ``depends_on``,
    ``gate_lens``, ``required_artifacts``, ``context_class``, etc. that have no analog in the
    task-shaped import contract. Only the fields the contract's mapping specifies are copied, so
    ``depends_on`` structurally never reaches ``capture_feature()`` / the import call — this is how
    Risk Area R2 (no dependency-edge wiring in this pass) is satisfied: by construction, not by a
    filter that could be bypassed or forgotten at a second call site.

    Status (Risk Area R1): plan doctrine's ``wave_plan.phases[]`` has no per-phase status field.
    Rather than defaulting every milestone to ``not_started`` forever (the original defect this
    contract exists to fix), this derives a coarse but real signal from the *plan's own*
    frontmatter ``status``: once the plan itself reaches a ``COMPLETE`` value (the same transition
    ``complete-phase.py`` performs on ship, and the same moment the standard `/dev:execute-phase`
    workflow re-runs ``intenttree_capture.py --apply`` — see Risk Area R4), every phase flips to
    "completed" in one shot. While the plan is still open, every phase reads "not_started". Finer,
    mid-plan, per-milestone granularity (cross-referencing
    ``.claude/progress/<slug>/phase-N-progress.md``) is deliberately deferred: those files are
    numbered ``phase-N`` under the OLDER doctrine this plan shape replaced, and new-doctrine plans
    using ``wave_plan.phases[]`` milestone ids (``M1``/``M2``/…) have no reliable mapping to that
    naming scheme. See the Completion Report for the full rationale.
    """
    pid = p.get("id")
    if not pid:
        return None
    pid = str(pid)
    if pid in seen:
        pid = f"phase-{pid}"
    seen.add(pid)
    exit_criteria = p.get("exit_criteria")
    return {
        "id": pid,
        "title": p.get("title") or pid,
        "acceptance_criteria": exit_criteria if isinstance(exit_criteria, list) else [],
        "node_type": "milestone",
        "status": "completed" if plan_status.strip().lower() in COMPLETE else "not_started",
    }


def _collect_task(t: dict, plabel: str, seen: set[str]) -> dict | None:
    """Forward a raw progress-file task with orchestration-only fixups (thin shim).

    The backend owns ALL normalization (title fallback, points/unit parsing, status→progress —
    DI-104/105). This only ensures task *identity* for aggregation, forwarding every other field
    verbatim for the backend to normalize:
    - require an id (skip rows without one),
    - disambiguate ids that repeat across a feature's phase files (``Phase1-QF-1``),
    - tag the originating phase so the backend builds the right Phase container,
    - default a missing status so the in-flight filter has a value to read.
    """
    tid = t.get("id") or t.get("task_id") or t.get("key")
    if not tid:
        return None
    tid = str(tid)
    if tid in seen:
        tid = f"{plabel.replace(' ', '')}-{tid}"
    seen.add(tid)
    out: dict[str, Any] = dict(t)
    out["id"] = tid
    out["status"] = t.get("status") or "not_started"
    out.setdefault("phase", plabel)
    return out


# ------------------------------------------------------------------- feature build
def tasks_from_progress_dir(
    prog_dir: Path,
) -> tuple[list[dict], str | None, str | None, datetime.date | None, dict[str, dict]]:
    """Aggregate tasks across a feature's phase-progress files (backend normalizes).

    Also builds a per-phase frontmatter map (P2.2): each progress file's frontmatter (minus
    ``tasks``) keyed by the phase label *and* the raw ``phase`` token, so the backend can attach
    phase-level fields to the matching Phase container however its tasks name their phase.
    """
    tasks: list[dict] = []
    seen: set[str] = set()
    feature_slug = plan_ref = None
    newest = None
    phases_fm: dict[str, dict] = {}
    for pf in sorted(prog_dir.glob("*.md")):
        fm = load_fm(pf)
        upd = to_date(fm.get("updated")) or to_date(fm.get("created"))
        if upd and (newest is None or upd > newest):
            newest = upd
        feature_slug = fm.get("feature_slug") or feature_slug
        plan_ref = plan_ref or fm.get("plan_ref") or fm.get("prd_ref")
        raw = fm.get("tasks")
        if not isinstance(raw, list):
            continue
        pl = phase_label(fm, pf)
        ph_meta = {k: v for k, v in fm.items() if k != "tasks"}
        if ph_meta:
            keys = {pl}
            raw_phase = fm.get("phase")
            if raw_phase is not None and str(raw_phase).strip():
                keys.add(str(raw_phase).strip())
            for key in keys:
                phases_fm.setdefault(key, {}).update(ph_meta)
        for rt in raw:
            if isinstance(rt, dict):
                nt = _collect_task(rt, pl, seen)
                if nt:
                    tasks.append(nt)
    return tasks, feature_slug, plan_ref, newest, phases_fm


def feature_from_file(
    path: Path, repo_root: Path | None = None, *, allow_taskless: bool = False
) -> dict | None:
    """Build a feature payload from a single plan/progress file's own tasks[], falling back to
    wave_plan.phases[] milestones when tasks[] is absent/not a list (doctrine-conformant Tier 2/3
    plans deliberately carry no tasks[] — plan-doctrine.md rule 2, "milestones, not phases").

    With ``allow_taskless=True`` (DI-139 flat-plan container), a plan-level file that carries a
    ``feature_slug`` but no ``tasks[]``/``wave_plan.phases[]`` still yields a container payload
    (empty ``tasks``) so a flat plan with no ``.claude/progress/<slug>/`` directory gets a single
    feature container.
    """
    fm = load_fm(path)
    raw = fm.get("tasks")
    seen: set[str] = set()
    pl = phase_label(fm, path)
    tasks: list[dict] = []
    if isinstance(raw, list):
        if raw:  # tasks[] present and non-empty — existing path, unchanged.
            tasks = [
                nt for rt in raw if isinstance(rt, dict) and (nt := _collect_task(rt, pl, seen))
            ]
        # else: tasks[] present but explicitly empty — nothing to capture from this shape; no
        # wave_plan fallback is attempted (an explicit empty list is not "absent").
    else:
        wave_plan = fm.get("wave_plan")
        phases = wave_plan.get("phases") if isinstance(wave_plan, dict) else None
        if isinstance(phases, list) and phases:
            plan_status = str(fm.get("status") or "")
            tasks = [
                nt for rp in phases
                if isinstance(rp, dict) and (nt := _collect_phase(rp, plan_status, seen))
            ]
    if not tasks and not (allow_taskless and fm.get("feature_slug")):
        return None
    slug = fm.get("feature_slug") or path.stem
    plan_fm = {k: v for k, v in fm.items() if k != "tasks"}
    ph_keys = {pl}
    if fm.get("phase") is not None and str(fm.get("phase")).strip():
        ph_keys.add(str(fm["phase"]).strip())
    return {
        "slug": slug,
        "title": fm.get("title") or slug.replace("-", " ").title(),
        "kind": (fm.get("doc_type") or fm.get("kind") or "implementation_plan"),
        "artifact_path": str(path),
        "tasks": tasks,
        "plan_frontmatter": plan_fm,
        "phases_frontmatter": {key: plan_fm for key in ph_keys} if plan_fm else {},
        "decisions_from_body": extract_decisions_from_body(_body_of(path)),
        "decisions_from_links": decisions_from_meta_plan_refs(plan_fm, repo_root),
    }


def discover_features(repo_root: Path, cutoff: datetime.date) -> list[dict]:
    pdir = repo_root / ".claude/progress"
    feats: list[dict] = []
    if not pdir.is_dir():
        return feats
    for sub in sorted(d for d in pdir.iterdir() if d.is_dir()):
        slugs = {fm["feature_slug"] for pf in sub.glob("*.md")
                 if (fm := load_fm(pf)).get("feature_slug")}
        if len(slugs) > 2 or sub.name in ("quick-features", "quick-wins"):
            # DI-107: a catch-all dir holds independent progress files that reuse generic task
            # ids (QF-1, TASK-1). Capture each FILE as its own feature (artifact_path = the file
            # → a unique source_artifact_id) so (source_artifact_id, source_task_id) never
            # collides across files; idempotent on re-run.
            print(f"   (catch-all dir '{sub.name}': capturing per-file)")
            for pf in sorted(sub.glob("*.md")):
                feat = feature_from_file(pf, repo_root)
                if feat is None:
                    continue
                pf_fm = load_fm(pf)
                pf_newest = to_date(pf_fm.get("updated")) or to_date(pf_fm.get("created"))
                if pf_newest is None or pf_newest < cutoff:
                    continue
                if all(str(t["status"]).lower() in COMPLETE for t in feat["tasks"]):
                    continue  # fully complete → not in-flight
                feat["newest"] = pf_newest
                feats.append(feat)
            continue
        tasks, fslug, plan_ref, newest, phases_fm = tasks_from_progress_dir(sub)
        if not tasks:
            continue
        if newest is None or newest < cutoff:
            continue
        if all(str(t["status"]).lower() in COMPLETE for t in tasks):
            continue  # fully complete → not in-flight
        fslug = fslug or sub.name
        # resolve plan/PRD file for a clean container path + title + structural frontmatter (P2)
        path, kind, title = f".claude/progress/{fslug}/_feature.md", "implementation_plan", \
            fslug.replace("-", " ").title()
        plan_fm: dict = {}
        decisions_body: list[dict] = []
        decisions_links: list[dict] = []
        if plan_ref and (repo_root / plan_ref).exists():
            plan_path = repo_root / plan_ref
            pf_fm = load_fm(plan_path)
            path = plan_ref
            kind = "prd" if "/PRD" in plan_ref else "implementation_plan"
            title = pf_fm.get("title") or title
            plan_fm = {k: v for k, v in pf_fm.items() if k != "tasks"}
            decisions_body = extract_decisions_from_body(_body_of(plan_path))
            decisions_links = decisions_from_meta_plan_refs(plan_fm, repo_root)
        feats.append({"slug": fslug, "title": str(title),
                      "kind": kind if kind in VALID_KINDS else "implementation_plan",
                      "artifact_path": path, "tasks": tasks, "newest": newest,
                      "plan_frontmatter": plan_fm, "phases_frontmatter": phases_fm,
                      "decisions_from_body": decisions_body,
                      "decisions_from_links": decisions_links})
    return feats


def discover_flat_plans(repo_root: Path, captured_slugs: set[str]) -> list[dict]:
    """DI-144: discover flat plans with no progress dir.

    Scans ``docs/project_plans/`` recursively for ``*.md`` files that carry both ``it_schema``
    and ``feature_slug`` frontmatter but whose ``feature_slug`` is not already captured (i.e. has
    no ``.claude/progress/<slug>/`` dir, which the progress-dir scan in ``discover_features`` owns).
    Each is captured as a taskless feature container via ``feature_from_file(allow_taskless=True)``.
    Opt-in only; the default backfill behaviour is unchanged.
    """
    base = repo_root / "docs" / "project_plans"
    feats: list[dict] = []
    if not base.is_dir():
        return feats
    seen: set[str] = set(captured_slugs)
    for path in sorted(base.rglob("*.md")):
        fm = load_fm(path)
        if fm.get("it_schema") is None or not fm.get("feature_slug"):
            continue
        slug = str(fm["feature_slug"])
        if slug in seen:
            continue
        feat = feature_from_file(path, repo_root, allow_taskless=True)
        if feat is None:
            continue
        seen.add(slug)
        feats.append(feat)
    return feats


# ----------------------------------------------------------------- frontmatter fwd
# Curated structural plan-frontmatter keys forwarded to the backend (P1 consumes these to fill
# the plan-lens; DI-134). Curated, not arbitrary, so the register payload stays bounded.
_FORWARD_PLAN_KEYS = (
    # identity & lifecycle (shipped)
    "it_schema", "status", "effort_estimate", "points", "tier", "priority", "risk_level",
    "origin", "planning_maturity", "maturity", "lifecycle_pinned", "feature_version", "milestone",
    "doc_type", "owner", "tags",
    # prose description (DI-161) → Node.description on the feature/phase container (authored-wins
    # over the agent_summary fallback applied backend-side in feature_container_columns).
    "description", "summary", "overview",
    # structural planning lens (shipped + widened)
    "open_questions", "decisions", "decision_gates", "meta_plan_refs", "meta_plans", "wave_plan",
    "references", "related_documents", "prd_ref", "plan_ref", "spike_ref", "charter_ref",
    "adr_refs", "findings_doc_ref", "test_plan_ref",
    "success_metrics", "success_criteria", "entry_criteria", "exit_criteria", "contributors",
    "changelog_required",
    # CR-1 model-backed fields (P4-003): forwarded so the backend can map onto node columns (P5-001)
    "acceptance_criteria", "definition_of_done", "execution_mode", "scores", "target_date",
    "estimate_minutes", "impact", "branch", "repo", "node_type",
    # agent-facing context (CR-1 → Node.agent_* columns)
    "agent_title", "agent_summary", "agent_context", "agent_instructions", "delegation_mode",
    "reviewer_actor", "proposed_by_actor",
    # CR-2 child-row sources (P4-004): pr/commit -> ExternalLink, blockers -> Edge, val -> ValidationRun
    "pr_refs", "commit_refs", "blockers", "validation_commands",
)
_DECISION_HEADING = re.compile(r"^#{1,6}\s+.*decision", re.IGNORECASE)
_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def extract_decisions_from_body(body: str, *, max_rows: int = 50) -> list[dict[str, str]]:
    """Best-effort parse of a 'Decisions' markdown table from a plan body (P2 table-aware, DI-134).

    Finds a heading matching ``/decisions?/`` (e.g. ``## Locked decisions``, ``### Recommended
    decisions``) followed by a GFM table and returns one dict per data row, keyed by the table's
    (lowercased) header columns with markdown bold/backticks stripped. Returns ``[]`` when none is
    found — these decisions are exactly what the plan-lens ``decision_gates`` aggregate counts.
    """
    if not body:
        return []
    lines = body.splitlines()
    out: list[dict[str, str]] = []
    i, n = 0, len(lines)
    while i < n and len(out) < max_rows:
        if not _DECISION_HEADING.match(lines[i]):
            i += 1
            continue
        # Find the table header within the following lines (stop at the next heading).
        j = i + 1
        while j < n and not lines[j].lstrip().startswith("|"):
            if re.match(r"^#{1,6}\s", lines[j]):
                break
            j += 1
        if j + 1 < n and lines[j].lstrip().startswith("|") and _TABLE_SEP.match(lines[j + 1]):
            header = [h.lower() for h in _split_row(lines[j])]
            k = j + 2
            while k < n and lines[k].lstrip().startswith("|") and len(out) < max_rows:
                row = _split_row(lines[k])
                if any(row):
                    rec = {
                        header[c]: re.sub(r"\*\*|`", "", row[c]).strip()
                        for c in range(min(len(header), len(row)))
                    }
                    out.append(rec)
                k += 1
            i = k
            continue
        i = j
    return out


def _decision_key(d: Any) -> str:
    """Stable identity for a decision row (used to merge sources without duplicating)."""
    if isinstance(d, dict):
        val = d.get("decision") or d.get("gate") or next(iter(d.values()), "")
        return re.sub(r"\s+", " ", str(val)).strip().lower()
    return re.sub(r"\s+", " ", str(d)).strip().lower()


def decisions_from_meta_plan_refs(plan_fm: dict, repo_root: Path | None) -> list[dict]:
    """Follow ``meta_plan_refs``/``meta_plans`` links and extract their ``## Decisions`` tables (DI-140).

    Resilient: a missing/unreadable link logs a warning and is skipped (capture continues). Returns
    a flat list of decision-row dicts; de-dup/merge against same-body decisions happens in
    ``build_register_frontmatter``.
    """
    refs: list[str] = []
    for key in ("meta_plan_refs", "meta_plans"):
        v = plan_fm.get(key)
        if isinstance(v, list):
            refs.extend(str(x) for x in v)
        elif isinstance(v, str) and v.strip():
            refs.append(v)
    out: list[dict] = []
    for ref in refs:
        ref = ref.strip().lstrip("/") if not ref.strip().startswith("/") else ref.strip()
        if not ref:
            continue
        candidate = Path(ref)
        if not candidate.is_absolute() and repo_root is not None:
            candidate = repo_root / ref
        if not candidate.exists():
            print(f"   (link-follow DI-140: meta_plan_ref not found, skipping: {ref})")
            continue
        rows = extract_decisions_from_body(_body_of(candidate))
        if isinstance(rows, list):
            out.extend(d for d in rows if isinstance(d, dict))
    return out


def build_register_frontmatter(feat: dict) -> dict:
    """Assemble the structural frontmatter forwarded in the register payload (P2/P4, DI-134/DI-140).

    Forwards the curated plan-frontmatter subset, the per-phase frontmatter map, and merges
    ``decisions`` from three sources without clobbering: frontmatter ``decisions``/``decision_gates``,
    a same-body ``## Decisions`` table, and decisions followed from ``meta_plan_refs`` links.
    ``tasks`` are NOT included here (they travel as the top-level ``tasks`` field).
    """
    plan_fm = feat.get("plan_frontmatter") or {}
    fwd: dict[str, Any] = {k: plan_fm[k] for k in _FORWARD_PLAN_KEYS if plan_fm.get(k) is not None}

    # Decisions: frontmatter wins over same-body (existing contract); linked decisions (DI-140) are
    # APPENDED to whichever base wins, de-duplicated, never clobbering the base.
    fm_decisions = fwd.get("decisions") if isinstance(fwd.get("decisions"), list) else None
    base = fm_decisions if fm_decisions else (feat.get("decisions_from_body") or [])
    merged: list[Any] = list(base)
    seen: set[str] = {_decision_key(d) for d in merged}
    for d in (feat.get("decisions_from_links") or []):
        key = _decision_key(d)
        if key and key not in seen:
            seen.add(key)
            merged.append(d)
    if merged:
        fwd["decisions"] = merged

    if feat.get("phases_frontmatter"):
        fwd["phases"] = feat["phases_frontmatter"]
    fwd["feature_slug"] = feat["slug"]
    return fwd


# -------------------------------------------------------------------------- apply
def capture_feature(
    api: str,
    workspace: str,
    tree: str,
    feat: dict,
    apply: bool,
    *,
    repo_root: str | None = None,
    plan_root: str | None = None,
    itt_client: itc.IttClient | None = None,
) -> dict:
    plan_fm = feat.get("plan_frontmatter") or {}
    reg_body = {
        "workspace_id": workspace, "tree_id": tree, "path": feat["artifact_path"],
        "kind": feat["kind"], "title": feat["title"], "feature_slug": feat["slug"],
        "status": plan_fm.get("status"),
        "frontmatter": build_register_frontmatter(feat),
        "tasks": feat["tasks"], "apply": apply,
    }
    code, reg = _req(api, "POST", "/api/v1/source-artifacts", reg_body)
    if code != 200 or not isinstance(reg, dict):
        return {"ok": False, "stage": "register", "code": code, "body": reg}
    if not apply:
        return {"ok": True, "dry_run": True, "tasks": len(feat["tasks"])}
    sid = reg.get("source_artifact_id")
    if not sid:
        return {"ok": False, "stage": "register", "reason": "no source_artifact_id", "body": reg}
    for _ in range(10):  # poll until the registered artifact is visible (commit-lag guard)
        c, _b = _req(api, "GET", f"/api/v1/source-artifacts/{sid}")
        if c == 200:
            break
        time.sleep(0.4)
    imp = None
    for attempt in range(4):
        c, body = _req(api, "POST", "/api/v1/work-item-sync/import", {
            "source_artifact_id": sid, "tree_id": tree, "tasks": feat["tasks"],
            "apply": True, "ac_as_steps": False})
        if c == 200:
            imp = body
            break
        if c == 404:
            time.sleep(0.5 * (attempt + 1))
            continue
        return {"ok": False, "stage": "import", "code": c, "body": body}
    if not isinstance(imp, dict):
        return {"ok": False, "stage": "import", "reason": "failed after retries"}
    # Progress is derived server-side from task status (DI-105) — no /complete post-pass needed.
    counts = imp.get("counts", {})
    result = {"ok": True, "artifact": sid, "inserts": counts.get("inserts", 0),
              "updates": counts.get("updates", 0), "edges": counts.get("edges_created", 0)}
    # M4 L4: stamp the feature_slug onto the just-created nodes at creation time, so the ledger
    # join is established up front instead of by a later stamp-node-slug.py pass. A stamp conflict
    # (FR-7) or an unreachable server surfaces as ok=False rather than a silent success.
    try:
        stamp = stamp_created_nodes(
            tree, feat["slug"], repo_root=repo_root, plan_root=plan_root,
            api_url=api, itt_client=itt_client,
        )
    except itc.IttError as exc:
        result["ok"] = False
        result["stamp"] = {"ok": False, "error": str(exc)}
        return result
    result["stamp"] = stamp
    if not stamp["ok"]:
        result["ok"] = False
    return result


# --------------------------------------------------------------------- thin audit
# Structural fields the plan-lens surfaces but capture has historically dropped (DI-134).
STRUCTURAL_FIELDS = [
    # original 6 (audit logic unchanged → baseline counts stable)
    "points", "origin", "planning_maturity", "meta_plan_refs", "open_questions", "decisions",
    # widened to the full §5 MUST/SHOULD set (P4-005)
    "it_schema", "status", "tier", "priority", "risk_level", "decision_gates", "wave_plan",
    "references", "related_documents", "owner", "tags", "success_metrics", "contributors",
    "blockers", "acceptance_criteria", "definition_of_done", "execution_mode", "scores",
    "target_date", "impact", "agent_title", "agent_summary", "agent_context",
]
# Body-prose hints: if a field is absent from frontmatter, a match here means it lives in the body
# (a P3 enrichment-agent target); no match means it is absent entirely (needs authoring).
_BODY_HINTS: dict[str, list[str]] = {
    "points": [r"\beffort\b", r"\bpoints?\b", r"\bpts\b"],
    "origin": [r"\borigin\b"],
    "planning_maturity": [r"planning[_ ]maturity", r"\bmaturity\b"],
    "meta_plan_refs": [r"meta[_ -]?plan"],
    "open_questions": [r"(?im)^#+\s*open\s+questions", r"(?im)^#+\s*questions", r"\bOQ-\d"],
    "decisions": [r"(?im)^#+\s*(locked\s+)?decisions?", r"decision\s+gate", r"\bDG-\d"],
    "decision_gates": [r"decision\s+gate", r"\bDG-\d"],
    "success_metrics": [r"(?im)^#+\s*success\s+(metrics|criteria)", r"success\s+criteria"],
    "blockers": [r"(?im)^#+\s*blockers?", r"\bblocked\s+by\b"],
    "acceptance_criteria": [r"(?im)^#+\s*acceptance\s+criteria", r"\bAC-?\d"],
    "definition_of_done": [r"definition\s+of\s+done", r"\bDoD\b"],
    "agent_context": [r"(?im)^#+\s*agent\s+context", r"agent[_ ]context"],
}


def _fm_has_points(fm: dict, tasks: list[dict]) -> bool:
    if fm.get("effort_estimate") or fm.get("points"):
        return True
    wp = fm.get("wave_plan")
    phases = wp.get("phases") if isinstance(wp, dict) else None
    if isinstance(phases, list) and any(
        isinstance(p, dict) and p.get("effort") is not None for p in phases
    ):
        return True
    return any(
        isinstance(t, dict) and (t.get("points") or t.get("estimated_effort") or t.get("estimate"))
        for t in tasks
    )


def _audit_field(field: str, fm: dict, tasks: list[dict], body: str) -> str:
    """Where a field is sourced: 'FM' frontmatter, 'BODY' prose-only, '-' absent."""
    if field == "points":
        present = _fm_has_points(fm, tasks)
    elif field == "meta_plan_refs":
        present = bool(fm.get("meta_plan_refs") or fm.get("meta_plans"))
    elif field == "decisions":
        present = bool(fm.get("decisions") or fm.get("decision_gates"))
    else:
        present = bool(fm.get(field))
    if present:
        return "FM"
    if any(re.search(pat, body) for pat in _BODY_HINTS.get(field, [])):
        return "BODY"
    return "-"


def _body_of(path: Path) -> str:
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if txt.startswith("---"):
        end = txt.find("\n---", 3)
        if end != -1:
            return txt[end + 4:]
    return txt


def report_thin(repo_root: Path, cutoff: datetime.date) -> None:
    """Read-only audit (no network): per in-flight feature, where each structural field is sourced.

    FM = in frontmatter (deterministic capture carries it once the shim forwards frontmatter).
    BODY = only in prose (a P3 enrichment-agent target — lift into frontmatter).
    -  = absent entirely (needs authoring).
    """
    feats = discover_features(repo_root, cutoff)
    print(f"THIN-FRONTMATTER AUDIT  {repo_root}  ({len(feats)} in-flight features)")
    print("  ADVISORY — run validate-plan-frontmatter.py for per-plan MUST-field lint (non-blocking).")
    print(f"  cols (left->right): {STRUCTURAL_FIELDS}")
    tally = {f: {"FM": 0, "BODY": 0, "-": 0} for f in STRUCTURAL_FIELDS}
    for feat in feats:
        path = repo_root / feat["artifact_path"]
        exists = path.exists()
        fm = load_fm(path) if exists else {}
        body = _body_of(path) if exists else ""
        cells = []
        for f in STRUCTURAL_FIELDS:
            v = _audit_field(f, fm, feat["tasks"], body)
            tally[f][v] += 1
            cells.append(f"{v:>4s}")
        note = "" if exists else "  (no plan file)"
        print(f"  {feat['slug']:38s} {' '.join(cells)}{note}")
    print("  " + "-" * 70)
    print("  TALLY (FM / BODY / absent):")
    for f in STRUCTURAL_FIELDS:
        t = tally[f]
        print(f"    {f:18s} FM={t['FM']:3d}  BODY={t['BODY']:3d}  absent={t['-']:3d}")


# ----------------------------------------------------------- specs awaiting plan (P4)
# Specs (PRD/design-spec/charter/spike) authored but never turned into an implementation plan are
# invisible to planning. This detector surfaces them as a durable, idempotent "needs-plan" signal
# (DI-137 captured the one-time reconciled list; this keeps it self-maintaining).
_SPEC_DIRS = (
    "docs/project_plans/design-specs",
    "docs/project_plans/PRDs",
    "docs/project_plans/charters",
    "docs/project_plans/spikes",
)
# Planning-artifact kinds the detector treats as "could become a plan". Files under the spec dirs
# with another kind (skill, context_file, …) or no planning identity at all are ignored as noise.
_SPEC_KINDS = {
    "prd", "design_spec", "spike", "charter", "exploration_charter", "feature_contract",
}


def _planned_slugs(repo_root: Path) -> set[str]:
    """feature_slugs that already have an implementation plan (any nesting)."""
    slugs: set[str] = set()
    plan_dir = repo_root / "docs/project_plans/implementation_plans"
    if plan_dir.is_dir():
        for pf in plan_dir.rglob("*.md"):
            slug = load_fm(pf).get("feature_slug")
            if slug:
                slugs.add(str(slug))
    return slugs


def discover_specs_awaiting_plan(repo_root: Path) -> list[dict]:
    """Specs with no implementation plan and no progress dir (status not terminal).

    A spec is *awaiting-plan* when its status is not terminal (completed/superseded/… per
    ``COMPLETE``) AND no implementation plan shares its ``feature_slug`` AND no
    ``.claude/progress/<slug>/`` dir exists. Drift-aware by construction — re-derived from the
    live tree on every run, so a spec drops off the list the moment its plan lands.
    """
    planned = _planned_slugs(repo_root)
    progress_root = repo_root / ".claude/progress"
    out: list[dict] = []
    seen: set[str] = set()
    for rel in _SPEC_DIRS:
        d = repo_root / rel
        if not d.is_dir():
            continue
        for sf in sorted(d.rglob("*.md")):
            fm = load_fm(sf)
            if not fm:
                continue
            raw_kind = fm.get("doc_type") or fm.get("kind")
            # Ignore non-planning files (skills, context files) and bare frontmatter with no
            # planning identity (no kind and no feature_slug) that happen to live under a spec dir.
            if raw_kind is not None and str(raw_kind).strip().lower() not in _SPEC_KINDS:
                continue
            if raw_kind is None and fm.get("feature_slug") is None:
                continue
            status = str(fm.get("status") or "").strip().lower()
            if status in COMPLETE:
                continue
            slug = str(fm.get("feature_slug") or sf.stem)
            if slug in planned or (progress_root / slug).is_dir() or slug in seen:
                continue
            seen.add(slug)
            kind = str(raw_kind or "design_spec")
            try:
                rel_path = str(sf.relative_to(repo_root))
            except ValueError:
                rel_path = str(sf)
            out.append({
                "slug": slug,
                "title": fm.get("title") or slug.replace("-", " ").title(),
                "kind": kind if kind in VALID_KINDS else "design_spec",
                "status": status or "unknown",
                "artifact_path": rel_path,
            })
    return out


def register_spec(api: str, workspace: str, tree: str, spec: dict, apply: bool) -> dict:
    """Register an unplanned spec as a (task-less) source-artifact → a needs-plan lens signal.

    Idempotent on ``(workspace, path)`` like every register; the artifact lands unbound (no tasks
    imported) so the plan-lens surfaces it under ``recent_imports``/``backlog`` with the
    ``unbound_source`` reason — i.e. "registered but not planned".
    """
    reg_body = {
        "workspace_id": workspace, "tree_id": tree, "path": spec["artifact_path"],
        "kind": spec["kind"], "title": spec["title"], "feature_slug": spec["slug"],
        "status": spec["status"],
        "frontmatter": {"needs_plan": True, "awaiting_plan": True,
                        "feature_slug": spec["slug"], "status": spec["status"]},
        "tasks": [], "apply": apply,
    }
    code, reg = _req(api, "POST", "/api/v1/source-artifacts", reg_body)
    if code != 200 or not isinstance(reg, dict):
        return {"ok": False, "stage": "register", "code": code, "body": reg}
    return {"ok": True, "action": reg.get("action"), "artifact": reg.get("source_artifact_id")}


# --------------------------------------------------------- anti-clobber guard (DI-323)
# The public API this shim must ALWAYS expose. A future deployed->canonical sync that silently
# drops any of these (exactly the DI-323 failure mode) is caught by the sibling regression test
# in backend/tests/unit/test_intenttree_capture_shim.py, which asserts every name below is present
# as a module attribute after loading the shim by path. Keep this list in sync when adding or
# removing a public helper — see the ANTI-CLOBBER NOTICE in the module docstring above.
PUBLIC_API = frozenset({
    # HTTP + frontmatter primitives
    "load_fm", "to_date", "phase_label",
    # task/phase collection
    "_collect_task", "_collect_phase", "tasks_from_progress_dir",
    # feature discovery
    "feature_from_file", "discover_features", "discover_flat_plans",
    # decisions-table extraction (DI-134/DI-140)
    "_split_row", "extract_decisions_from_body", "_decision_key",
    "decisions_from_meta_plan_refs", "build_register_frontmatter",
    # apply path (register + import + creation-time slug stamp)
    "capture_feature", "stamp_created_nodes", "_stamp_module",
    # thin-frontmatter audit (DI-134)
    "STRUCTURAL_FIELDS", "_BODY_HINTS", "_fm_has_points", "_audit_field", "_body_of",
    "report_thin",
    # specs-awaiting-plan discovery (P4/DI-137)
    "_planned_slugs", "discover_specs_awaiting_plan", "register_spec",
    # CLI entry point
    "main",
})


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="IntentTree SDLC capture/sync")
    ap.add_argument("mode", choices=["sync", "backfill", "report-thin", "specs-awaiting-plan"])
    ap.add_argument("file", nargs="?", help="plan/progress file (sync mode)")
    ap.add_argument("--repo-root", default=".", help="repo root (backfill mode)")
    ap.add_argument("--plan-root", default=None,
                    help="plan corpus root for the creation-time slug stamp "
                         "(default: <repo-root>/docs/project_plans)")
    ap.add_argument("--api-url", default=DEFAULT_API)
    ap.add_argument("--workspace", default=os.environ.get("INTENTTREE_WORKSPACE"))
    ap.add_argument("--tree", default=os.environ.get("INTENTTREE_TREE"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--cutoff", default="2026-05-30")
    ap.add_argument(
        "--include-flat-plans",
        action="store_true",
        help="backfill: also discover plans under docs/project_plans/ that carry it_schema+feature_slug but have no .claude/progress/<slug>/ dir",
    )
    args = ap.parse_args()

    if args.mode == "report-thin":
        # Local, read-only audit — no --tree/--workspace/network needed.
        cutoff = to_date(args.cutoff) or datetime.date(2026, 1, 1)
        report_thin(Path(args.repo_root), cutoff)
        return 0

    if args.mode == "specs-awaiting-plan":
        # Discovery is local; network is only used on --apply (to register the needs-plan signal).
        specs = discover_specs_awaiting_plan(Path(args.repo_root))
        print(f"SPECS AWAITING PLAN  {args.repo_root}  ({len(specs)} found)")
        for s in specs:
            print(f"  - {s['slug']:42s} [{s['status']:>10s}] {s['kind']:16s} {s['artifact_path']}")
        if args.apply:
            if not args.tree:
                sys.stderr.write("error: --apply needs --tree (or INTENTTREE_TREE)\n")
                return 2
            api = args.api_url.rstrip("/")
            ws = args.workspace or ""
            for s in specs:
                res = register_spec(api, ws, args.tree, s, True)
                print(f"    {'OK ' if res.get('ok') else '!! '}{s['slug']:42s} {res}")
        return 0

    if not args.tree:
        sys.stderr.write("error: --tree (or INTENTTREE_TREE) required\n")
        return 2
    api = args.api_url.rstrip("/")
    ws = args.workspace or ""

    if args.mode == "sync":
        if not args.file:
            sys.stderr.write("error: sync mode needs a <file>\n")
            return 2
        feat = feature_from_file(Path(args.file), Path(args.repo_root))
        if feat is None:
            print(f"no tasks[] or wave_plan.phases[] in {args.file}; nothing to sync")
            return 0
        res = capture_feature(api, ws, args.tree, feat, args.apply,
                              repo_root=args.repo_root, plan_root=args.plan_root)
        print(json.dumps(res))
        return 0 if res.get("ok") else 1

    cutoff = to_date(args.cutoff) or datetime.date(2026, 1, 1)
    feats = discover_features(Path(args.repo_root), cutoff)
    if args.include_flat_plans:
        captured_slugs = {f["slug"] for f in feats}
        flat = discover_flat_plans(Path(args.repo_root), captured_slugs)
        print(f"   (--include-flat-plans: {len(flat)} flat plan(s) with no progress dir)")
        feats.extend(flat)
    print(f"{'APPLY' if args.apply else 'DRY-RUN'} {args.repo_root} -> {args.tree}: "
          f"{len(feats)} in-flight features")
    ok = True
    for f in feats:
        res = capture_feature(api, ws, args.tree, f, args.apply,
                              repo_root=args.repo_root, plan_root=args.plan_root)
        flag = "OK " if res.get("ok") else "!! "
        ok = ok and res.get("ok", False)
        print(f"  {flag}{f['slug']:42s} tasks={len(f['tasks']):3d} "
              f"{ {k: v for k, v in res.items() if k != 'ok'} }")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
