#!/usr/bin/env python3
"""register_claude_projects.py

Enumerate ~/.claude/projects/<dir> subdirectories and register each as its own
CCDash project against a target API.  Each project's sessionsPath is set to the
absolute leaf dir so the backend attributes sessions per-repo, not globally.

Default is DRY RUN — pass --apply to POST registrations.

Usage:
    python scripts/register_claude_projects.py [--apply] [OPTIONS]
    python scripts/register_claude_projects.py --min-sessions 5 --no-worktrees --apply
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Path decoding
# ---------------------------------------------------------------------------

def decode_repo_path(dirname: str) -> str:
    """Reverse-engineer an absolute repo path from a Claude project dir name.

    Claude encodes the repo path by replacing '/' (and '.') with '-', e.g.
    '/Users/foo/.claude/bar' → '-Users-foo--claude-bar'.  Path segments may
    themselves contain '-' (e.g. 'agentic-meta-dev'), making a naive split
    ambiguous.

    Strategy: strip the single leading '-', split on '-' (filtering empty
    tokens produced by '--' runs), then greedily consume the longest run of
    remaining tokens (joined by '-') that forms an existing directory at each
    level.  Falls back to single-token consumption on no match (best-effort).
    The decoded path is used only for the 'path' field; sessionsPath never
    depends on this decode being perfect.
    """
    if not dirname.startswith("-"):
        return dirname  # unexpected format; return as-is

    tokens = [t for t in dirname[1:].split("-") if t]  # strip empty from '--'
    path = "/"
    i = 0
    while i < len(tokens):
        # Try longest match first; shrink window until we find a real dir
        best_j = None
        for j in range(len(tokens), i, -1):
            candidate = os.path.join(path, "-".join(tokens[i:j]))
            if os.path.isdir(candidate):
                best_j = j
                break
        if best_j is not None:
            path = os.path.join(path, "-".join(tokens[i:best_j]))
            i = best_j
        else:
            # No filesystem match — consume one token and continue
            path = os.path.join(path, tokens[i])
            i += 1

    return path if path != "/" else dirname


def _find_deepest_ancestor(tokens: list[str]) -> tuple[str, list[str]]:
    """Find the longest prefix of tokens that forms an existing directory under '/'.

    Iterates from shortest to longest prefix (building up /t0/t1/t2/…) so every
    level is checked.  The LAST prefix that still satisfies os.path.isdir is kept
    as the deepest ancestor; the remaining tokens are returned for the caller to
    use as the project name.  Returns ('/', tokens) when nothing matches.
    """
    best_i = 0
    best_path = "/"
    for i in range(1, len(tokens) + 1):
        candidate = "/" + "/".join(tokens[:i])
        if os.path.isdir(candidate):
            best_i = i
            best_path = candidate
    return best_path, tokens[best_i:]


def derive_name(dirname: str, decoded_path: str) -> str:
    """Derive a human-readable project name via the deepest-existing-ancestor strategy.

    Claude Code encodes both '/' and '_' (and '.') as '-', so the greedy path
    decode used for the 'path' field cannot reliably recover segment boundaries.
    Instead we find the LONGEST prefix of encoded tokens that resolves to a real
    directory on disk — that ancestor is unambiguous — and use the REMAINDER
    tokens (hyphen-joined) as the name.  This correctly preserves multi-word
    names like 'agentic-meta-dev', 'citytile-pack', 'artifact-atlas', etc.

    Worktree dirs: if the remainder contains 'claude' and 'worktrees' as
    consecutive tokens (produced by dropping the empty token from '--claude'),
    renders as '<base> (wt: <suffix>)'.

    Fallbacks:
    - No ancestor found → whole dirname with leading '-' stripped.
    - Remainder empty (dir IS an existing ancestor) → basename of ancestor.
    - decoded_path parameter is kept for API compatibility but unused here.
    """
    if not dirname.startswith("-"):
        return dirname

    tokens = [t for t in dirname[1:].split("-") if t]
    if not tokens:
        return dirname

    ancestor, remaining = _find_deepest_ancestor(tokens)

    # Worktree special-case: look for consecutive 'claude', 'worktrees' tokens
    wt_idx = None
    for i in range(len(remaining) - 1):
        if remaining[i] == "claude" and remaining[i + 1] == "worktrees":
            wt_idx = i
            break

    if wt_idx is not None:
        base_tokens = remaining[:wt_idx]
        suffix = "-".join(remaining[wt_idx + 2:])
        base = "-".join(base_tokens) if base_tokens else (Path(ancestor).name or dirname)
        return f"{base} (wt: {suffix})"

    if remaining:
        return "-".join(remaining)

    # Remainder empty: the full encoded path resolves to an existing dir
    return Path(ancestor).name or dirname


def stable_project_id(dirname: str) -> str:
    """Deterministic per-dir id — same dirname always yields the same id."""
    return "ccp-" + hashlib.sha1(dirname.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib urllib only — no third-party deps)
# ---------------------------------------------------------------------------

def http_get_list(url: str, timeout: int) -> list:
    """GET url; return as a list.  Handles bare list or {"items":[...]} envelope.
    Exits non-zero on connection error (GET is required for idempotency).
    """
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach {url} — {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {url} — {exc}", file=sys.stderr)
        sys.exit(1)

    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return body.get("items", [])
    return []


def http_post(url: str, payload: dict, timeout: int) -> tuple[bool, str]:
    """POST JSON payload; returns (success, status_string).
    Does NOT call sys.exit — caller decides how to handle failures.
    """
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as _resp:
            return True, "ok"
    except urllib.error.HTTPError as exc:
        snippet = exc.read(120).decode(errors="replace").strip()
        return False, f"FAIL:{exc.code} {snippet!r}"
    except urllib.error.URLError as exc:
        return False, f"FAIL:conn {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, f"FAIL:err {exc}"


# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------

def collect_candidates(
    projects_root: Path,
    min_sessions: int,
    include: list[str],
    exclude: list[str],
    no_worktrees: bool,
) -> list[dict]:
    """Return sorted (session count desc) list of candidate project dicts.
    Dirs below min_sessions are excluded entirely (not shown in the table).
    """
    if not projects_root.is_dir():
        print(f"ERROR: projects root '{projects_root}' not found", file=sys.stderr)
        sys.exit(1)

    candidates = []
    for entry in projects_root.iterdir():
        if not entry.is_dir():
            continue
        dirname = entry.name

        # Filter: worktrees
        if no_worktrees and "--claude-worktrees-" in dirname:
            continue
        # Filter: --include (any match keeps the dir)
        if include and not any(p in dirname for p in include):
            continue
        # Filter: --exclude (any match drops the dir)
        if exclude and any(p in dirname for p in exclude):
            continue

        # Count sessions safely via pathlib (depth-1 only; leading '-' is safe)
        n = len(list(entry.glob("*.jsonl")))
        if n < min_sessions:
            continue

        decoded = decode_repo_path(dirname)
        candidates.append({
            "dirname": dirname,
            "sessions_path": str(entry.resolve()),
            "repo_path": decoded,
            "name": derive_name(dirname, decoded),
            "id": stable_project_id(dirname),
            "n_sessions": n,
            "action": "",
        })

    candidates.sort(key=lambda c: c["n_sessions"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

_COL = {"sess": 8, "act": 15, "id": 18, "name": 30}


def _print_table(rows: list[dict]) -> None:
    hdr = (
        f"{'sessions':>{_COL['sess']}}  "
        f"{'action':<{_COL['act']}}  "
        f"{'id':<{_COL['id']}}  "
        f"{'name':<{_COL['name']}}  "
        f"sessionsPath"
    )
    print(hdr)
    print("-" * max(80, len(hdr)))
    for r in rows:
        print(
            f"{r['n_sessions']:>{_COL['sess']}}  "
            f"{r['action']:<{_COL['act']}}  "
            f"{r['id']:<{_COL['id']}}  "
            f"{r['name']:<{_COL['name']}}  "
            f"{r['sessions_path']}"
        )


def _print_tally(rows: list[dict]) -> None:
    total = len(rows)
    registered = sum(1 for r in rows if r["action"] in ("would-register", "ok"))
    skipped = sum(1 for r in rows if r["action"] == "skip-exists")
    failed = sum(1 for r in rows if r["action"].startswith("FAIL"))
    print(
        f"\nTotal: {total}  "
        f"would-register/registered: {registered}  "
        f"skipped-exists: {skipped}  "
        f"failed: {failed}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Register ~/.claude/projects dirs as CCDash projects. "
            "Default is DRY RUN — pass --apply to POST registrations."
        )
    )
    ap.add_argument(
        "--projects-root", default="~/.claude/projects",
        help="Root of Claude project dirs (default: ~/.claude/projects)",
    )
    ap.add_argument(
        "--api", default="http://10.42.10.76:8090",
        help="CCDash API base URL (default: http://10.42.10.76:8090)",
    )
    ap.add_argument(
        "--min-sessions", type=int, default=1,
        help="Skip dirs with fewer than N .jsonl files (default: 1)",
    )
    ap.add_argument(
        "--include", action="append", default=[], metavar="PAT",
        help="Keep only dirs whose name contains PAT (repeatable)",
    )
    ap.add_argument(
        "--exclude", action="append", default=[], metavar="PAT",
        help="Drop dirs whose name contains PAT (repeatable)",
    )
    ap.add_argument(
        "--no-worktrees", action="store_true",
        help="Drop dirs whose name contains '--claude-worktrees-'",
    )
    ap.add_argument(
        "--limit", type=int, default=None,
        help="Cap candidates to top N by session count after sorting",
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="POST registrations (default: dry run, no POSTs)",
    )
    ap.add_argument(
        "--force", action="store_true",
        help="Register even if sessionsPath or id already exists on the server",
    )
    ap.add_argument(
        "--timeout", type=int, default=15,
        help="HTTP timeout in seconds (default: 15)",
    )
    args = ap.parse_args()

    projects_root = Path(args.projects_root).expanduser()
    api_base = args.api.rstrip("/")

    # Collect and optionally cap candidates
    rows = collect_candidates(
        projects_root=projects_root,
        min_sessions=args.min_sessions,
        include=args.include,
        exclude=args.exclude,
        no_worktrees=args.no_worktrees,
    )
    if args.limit is not None:
        rows = rows[: args.limit]

    if not rows:
        print("No candidates found (adjust --min-sessions or filters).")
        sys.exit(0)

    # Fetch existing projects for idempotency check
    existing = http_get_list(f"{api_base}/api/projects", args.timeout)
    existing_sp = {p.get("sessionsPath", "") for p in existing}
    existing_ids = {p.get("id", "") for p in existing}

    # Assign initial actions
    for r in rows:
        already = r["sessions_path"] in existing_sp or r["id"] in existing_ids
        if already and not args.force:
            r["action"] = "skip-exists"
        else:
            r["action"] = "would-register" if not args.apply else "register"

    # Dry-run path: print plan and exit
    if not args.apply:
        print("DRY RUN — pass --apply to POST registrations\n")
        _print_table(rows)
        _print_tally(rows)
        sys.exit(0)

    # Apply path: POST registrations
    any_failed = False
    post_url = f"{api_base}/api/projects"
    for r in rows:
        if r["action"] == "skip-exists":
            continue
        payload = {
            "id": r["id"],
            "name": r["name"],
            "path": r["repo_path"],
            "sessionsPath": r["sessions_path"],
            "description": "",
            "repoUrl": "",
            # repo_path is the canonical repo cwd used for Codex session attribution.
            # Uses the greedy filesystem-decoded path from decode_repo_path().
            "repoPath": r["repo_path"],
        }
        ok, msg = http_post(post_url, payload, args.timeout)
        r["action"] = "ok" if ok else msg
        if not ok:
            any_failed = True

    _print_table(rows)
    _print_tally(rows)
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
