#!/usr/bin/env python3
"""List or re-ingest Claude transcripts for a UTC date and registered projects.

Use --report to restrict a repair to UNRECONCILED_INGEST_GAP session IDs from
a night report. Dry-run performs only filesystem and read-only API access.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.project_paths.worktree_fanout import session_scan_roots  # noqa: E402


def load_projects(api_url: str, token: str) -> list[dict]:
    request = Request(
        api_url.rstrip("/") + "/api/projects",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload if isinstance(payload, list) else payload.get("items", [])


def report_ids(path: Path, target: date) -> set[str]:
    report = json.loads(path.read_text())
    since = str((report.get("window") or {}).get("since") or "")
    if not since.startswith(target.isoformat()):
        raise ValueError(f"report window {since!r} does not start on {target}")
    return {
        row["session_id"]
        for row in report.get("unreconciled", [])
        if row.get("source") == "transcript" and row.get("state") == "UNRECONCILED_INGEST_GAP"
    }


def first_record_date(path: Path) -> date | None:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    stamp = record.get("timestamp")
                    if isinstance(stamp, str) and len(stamp) >= 10:
                        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        return parsed.astimezone(timezone.utc).date()
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def candidates(projects: list[dict], target: date, missing_ids: set[str] | None) -> list[tuple[str, Path]]:
    found: dict[Path, str] = {}
    for project in projects:
        project_id = str(project.get("id") or "")
        sessions = (project.get("pathConfig") or {}).get("sessions") or {}
        raw_root = sessions.get("filesystemPath") or project.get("sessionsPath")
        if not project_id or not raw_root:
            continue
        for root in session_scan_roots(Path(raw_root).expanduser()):
            if not root.is_dir():
                continue
            for path in root.rglob("*.jsonl"):
                if missing_ids is not None:
                    if path.stem not in missing_ids:
                        continue
                elif first_record_date(path) != target:
                    continue
                # An explicitly registered child wins over parent fan-out.
                found.setdefault(path, project_id)
    return sorted(((project_id, path) for path, project_id in found.items()), key=lambda row: str(row[1]))


async def apply(rows: list[tuple[str, Path]]) -> tuple[int, int]:
    from backend import config
    from backend.db.connection import close_connection, get_connection
    from backend.db.sync_engine import SyncEngine

    if config.DB_BACKEND != "postgres":
        raise RuntimeError("Apply requires CCDASH_DB_BACKEND=postgres")
    db = await get_connection()
    engine = SyncEngine(db)
    succeeded = 0
    failed = 0
    try:
        for project_id, path in rows:
            try:
                await engine._sync_single_session(project_id, path, force=True)
                succeeded += 1
            except Exception as exc:
                failed += 1
                print(f"FAILED {project_id} {path}: {exc}", file=sys.stderr)
    finally:
        await close_connection()
    return succeeded, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="UTC date YYYY-MM-DD")
    parser.add_argument("--report", type=Path, help="night-report.json; restrict to its missing transcript IDs")
    parser.add_argument("--api-url", default=os.getenv("CCDASH_API", "http://127.0.0.1:8000"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    projects = load_projects(args.api_url, os.getenv("CCDASH_TOKEN", ""))
    ids = report_ids(args.report, args.date) if args.report else None
    rows = candidates(projects, args.date, ids)
    for project_id, path in rows:
        print(f"{project_id}\t{path}")
    print(f"candidate_count={len(rows)}")
    if args.dry_run:
        return 0
    succeeded, failed = asyncio.run(apply(rows))
    print(f"ingested={succeeded} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
