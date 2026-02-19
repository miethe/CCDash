#!/usr/bin/env python3
"""Audit feature<->session mappings for likely mis-links.

Usage:
  python backend/scripts/link_audit.py
  python backend/scripts/link_audit.py --feature marketplace-source-detection-improvements-v1
  python backend/scripts/link_audit.py --project <project-id>
  python backend/scripts/link_audit.py --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.link_audit import analyze_suspect_links, suspects_as_dicts


def _load_links(
    conn: sqlite3.Connection,
    feature: str | None,
    project_id: str | None,
) -> list[dict[str, Any]]:
    where = """
        el.source_type = 'feature'
        AND el.target_type = 'session'
        AND el.link_type = 'related'
        AND (json_extract(el.metadata_json, '$.linkStrategy') = 'session_evidence' OR el.metadata_json LIKE '%session_evidence%')
    """
    params: list[Any] = []
    if feature:
        where += " AND el.source_id = ?"
        params.append(feature)
    if project_id:
        where += " AND f.project_id = ?"
        params.append(project_id)
    query = f"""
        SELECT
            el.source_id AS feature_id,
            el.target_id AS session_id,
            el.confidence AS confidence,
            el.metadata_json AS metadata_json
        FROM entity_links el
        JOIN features f ON f.id = el.source_id
        WHERE {where}
    """
    rows = conn.execute(query, params).fetchall()
    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        metadata_raw = row["metadata_json"]
        try:
            metadata = json.loads(metadata_raw) if metadata_raw else {}
        except Exception:
            metadata = {}
        parsed_rows.append({
            "feature_id": row["feature_id"],
            "session_id": row["session_id"],
            "confidence": row["confidence"],
            "metadata": metadata,
        })
    return parsed_rows


def _fanout_map(conn: sqlite3.Connection, project_id: str | None) -> dict[str, int]:
    params: list[Any] = []
    where = """
        el.source_type = 'feature'
        AND el.target_type = 'session'
        AND el.link_type = 'related'
    """
    if project_id:
        where += " AND f.project_id = ?"
        params.append(project_id)
    rows = conn.execute(
        f"""
        SELECT el.target_id AS session_id, COUNT(*) AS feature_count
        FROM entity_links el
        JOIN features f ON f.id = el.source_id
        WHERE {where}
        GROUP BY el.target_id
        """,
        params,
    ).fetchall()
    return {str(row["session_id"]): int(row["feature_count"]) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/ccdash_cache.db")
    parser.add_argument("--feature", default="")
    parser.add_argument("--project", default="")
    parser.add_argument("--primary-floor", type=float, default=0.55)
    parser.add_argument("--fanout-floor", type=int, default=10)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = _load_links(conn, args.feature or None, args.project or None)
        fanout = _fanout_map(conn, args.project or None)
        suspects = analyze_suspect_links(rows, fanout, args.primary_floor, args.fanout_floor)
        suspects = suspects[: max(1, args.limit)]

        if args.json:
            payload = {
                "db": str(db_path),
                "feature_filter": args.feature or None,
                "project_filter": args.project or None,
                "row_count": len(rows),
                "suspect_count": len(suspects),
                "suspects": suspects_as_dicts(suspects),
            }
            print(json.dumps(payload, indent=2))
            return 0

        print(f"DB: {db_path}")
        if args.project:
            print(f"Project filter: {args.project}")
        if args.feature:
            print(f"Feature filter: {args.feature}")
        print(f"Analyzed links: {len(rows)}")
        print(f"Suspects: {len(suspects)}")
        print("")
        for idx, suspect in enumerate(suspects, start=1):
            print(
                f"{idx:02d}. feature={suspect.feature_id} session={suspect.session_id} "
                f"conf={suspect.confidence} fanout={suspect.fanout_count} share={suspect.ambiguity_share}"
            )
            print(f"    reason={suspect.reason}")
            print(f"    title={suspect.title}")
            print(f"    signal={suspect.signal_type} path={suspect.signal_path}")
            if suspect.commands:
                print(f"    commands={', '.join(suspect.commands)}")
            print("")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
