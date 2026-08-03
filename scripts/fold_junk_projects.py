#!/usr/bin/env python3
"""One-shot fold of catch-all "junk" project rows onto their real projects.

Re-points ``sessions.project_id`` from a junk bucket to the registered project its
``cwd`` actually belongs to. Evidence-based only: a session is moved iff its ``cwd``
matches a rule below. Rows with no ``cwd`` (or an unmapped one) are left in place and
reported -- never guessed at.

Deliberately does NOT delete any ``projects`` row. A junk project may only be deleted
once it owns zero sessions; that decision is left to the operator after reading the
residue report this script prints.

Usage:
    python scripts/fold_junk_projects.py [--database-url DSN] [--apply]
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("ERROR: psycopg (v3) is required. `pip install psycopg[binary]`.")

DEV = "/Users/miethe/dev/homelab/development"

# (junk_project_id, kind, needle, target_project_id)
#   kind="dir"   -> cwd = needle OR cwd LIKE needle/%   (a repo dir and anything under it)
#   kind="codex" -> cwd ~ ^/Users/miethe/\.codex/worktrees/[^/]+/needle(/|$)
RULES: list[tuple[str, str, str, str]] = [
    # --- ccp-3f61311bd972 "development" (the parent dir, not a repo) ---
    ("ccp-3f61311bd972", "dir", f"{DEV}/chat-history-corpus-workbench", "ccp-c6b40279d595"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/boxbrain-2", "ccp-daf209286d5c"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/codebase-map", "ccp-3a68745764ae"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/family-shopping-dashboard", "ccp-10cb2f1c763b"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/signal_to_system", "ccp-695d1ee3cf7d"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/meatyprompts", "ccp-d85cde44eb2e"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/meatycapture", "ccp-5ad480610580"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/MeatySkills", "ccp-5e802e903202"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/MeatyMusic", "ccp-ef9d5a88f64b"),
    ("ccp-3f61311bd972", "dir", f"{DEV}/pediatric-anemia-site", "ccp-6faa31ef917f"),
    # --- ccp-61d5a4bb0de5 "miethe" ($HOME): codex worktrees of real repos ---
    # Same convention as .claude/worktrees: a worktree session belongs to its parent repo.
    ("ccp-61d5a4bb0de5", "codex", "research-foundry", "ccp-1e9106790b62"),
    ("ccp-61d5a4bb0de5", "codex", "CCDash", "ccp-2a984316f63a"),
    ("ccp-61d5a4bb0de5", "codex", "skillmeat", "ccp-3c5f7843344b"),
    ("ccp-61d5a4bb0de5", "codex", "agentic-research", "ccp-ca3b0fe0e4ba"),
    ("ccp-61d5a4bb0de5", "codex", "citytile_pack", "ccp-e9fa5b25eeff"),
]

JUNK = ["ccp-3f61311bd972", "ccp-61d5a4bb0de5", "ccp-daf209286d5c", "ccp-89da067a7379"]


def predicate(kind: str, needle: str) -> tuple[str, list]:
    if kind == "dir":
        return "(cwd = %s OR cwd LIKE %s)", [needle, needle + "/%"]
    if kind == "codex":
        return "(cwd ~ %s)", [rf"^/Users/miethe/\.codex/worktrees/[^/]+/{needle}(/|$)"]
    raise ValueError(kind)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=os.environ.get("CCDASH_DATABASE_URL"))
    ap.add_argument("--apply", action="store_true", help="Commit. Default is dry-run.")
    args = ap.parse_args()
    if not args.database_url:
        return int(bool(sys.stderr.write("ERROR: --database-url or $CCDASH_DATABASE_URL\n"))) or 2

    dsn = args.database_url.replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()

        cur.execute("SELECT count(*) FROM sessions")
        pre_total = cur.fetchone()[0]
        print(f"pre-check: sessions total = {pre_total}")

        # Every target must actually exist in the registry.
        targets = sorted({r[3] for r in RULES})
        cur.execute("SELECT id FROM projects WHERE id = ANY(%s)", (targets,))
        known = {r[0] for r in cur.fetchall()}
        if missing := set(targets) - known:
            return int(bool(sys.stderr.write(f"ERROR: unknown target project(s): {sorted(missing)}\n"))) or 3

        moved_total = 0
        for junk, kind, needle, target in RULES:
            pred, params = predicate(kind, needle)

            # PK is (project_id, id): a re-point collides if the target already owns that id.
            cur.execute(
                f"SELECT count(*) FROM sessions s WHERE s.project_id = %s AND {pred}"
                "  AND EXISTS (SELECT 1 FROM sessions t WHERE t.project_id = %s AND t.id = s.id)",
                [junk, *params, target],
            )
            collisions = cur.fetchone()[0]

            cur.execute(
                f"SELECT count(*) FROM sessions WHERE project_id = %s AND {pred}", [junk, *params]
            )
            n = cur.fetchone()[0]
            if not n:
                continue
            if collisions:
                print(f"  SKIP  {junk} -> {target}  {needle}  ({n} rows, {collisions} PK COLLISIONS)")
                continue

            print(f"  MOVE  {junk} -> {target}  {needle}  ({n} rows)")
            if args.apply:
                cur.execute(
                    f"UPDATE sessions SET project_id = %s WHERE project_id = %s AND {pred}",
                    [target, junk, *params],
                )
            moved_total += n

        # Residue: what is left on each junk bucket, and why it could not be mapped.
        print("\nresidue (left in place, NOT reassigned):")
        for junk in JUNK:
            cur.execute(
                "SELECT coalesce(nullif(cwd, ''), '<no cwd>'), count(*) FROM sessions"
                " WHERE project_id = %s GROUP BY 1 ORDER BY 2 DESC",
                (junk,),
            )
            rows = cur.fetchall()
            total = sum(r[1] for r in rows)
            print(f"  {junk}: {total} remaining")
            for cwd, n in rows:
                print(f"      {n:>4}  {cwd}")

        cur.execute("SELECT count(*) FROM sessions")
        post_total = cur.fetchone()[0]
        print(f"\npost-check: sessions total = {post_total} (delta = {post_total - pre_total})")
        if post_total < pre_total:
            conn.rollback()
            return int(bool(sys.stderr.write("ERROR: row count dropped -- rolled back.\n"))) or 4

        if args.apply:
            conn.commit()
            print(f"applied: {moved_total} sessions re-pointed.")
        else:
            conn.rollback()
            print(f"dry-run: no changes committed ({moved_total} would move).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
