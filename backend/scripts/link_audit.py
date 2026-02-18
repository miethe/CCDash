#!/usr/bin/env python3
"""Audit feature<->session mappings for likely mis-links.

Usage:
  python backend/scripts/link_audit.py
  python backend/scripts/link_audit.py --feature marketplace-source-detection-improvements-v1
  python backend/scripts/link_audit.py --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


def _canonical_slug(value: str) -> str:
    token = (value or "").strip().lower()
    if not token:
        return ""
    # strip trailing version suffixes like -v1 or -v1.2
    if "-v" in token:
        base, _, suffix = token.rpartition("-v")
        if base and suffix.replace(".", "").isdigit():
            return base
    return token


def _normalize_path(path: str) -> str:
    value = (path or "").strip().strip("\"'`<>[](),;")
    if not value:
        return ""
    return value.replace("\\", "/").lower()


@dataclass
class Suspect:
    feature_id: str
    session_id: str
    confidence: float
    ambiguity_share: float
    title: str
    signal_type: str
    signal_path: str
    commands: list[str]
    reason: str
    fanout_count: int


def _contains_feature_hint(feature_id: str, text: str) -> bool:
    blob = (text or "").lower()
    if not blob:
        return False
    fid = feature_id.lower()
    fid_base = _canonical_slug(fid)
    return fid in blob or (fid_base and fid_base in blob)


def _to_float(raw: Any) -> float:
    try:
        return float(raw or 0.0)
    except Exception:
        return 0.0


def _load_links(conn: sqlite3.Connection, feature: str | None) -> list[dict[str, Any]]:
    where = """
        source_type = 'feature'
        AND target_type = 'session'
        AND link_type = 'related'
        AND (json_extract(metadata_json, '$.linkStrategy') = 'session_evidence' OR metadata_json LIKE '%session_evidence%')
    """
    params: list[Any] = []
    if feature:
        where += " AND source_id = ?"
        params.append(feature)
    query = f"""
        SELECT source_id AS feature_id, target_id AS session_id, confidence, metadata_json
        FROM entity_links
        WHERE {where}
    """
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _fanout_map(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT target_id AS session_id, COUNT(*) AS feature_count
        FROM entity_links
        WHERE source_type = 'feature' AND target_type = 'session' AND link_type = 'related'
        GROUP BY target_id
        """
    ).fetchall()
    return {str(row["session_id"]): int(row["feature_count"]) for row in rows}


def _analyze(rows: list[dict[str, Any]], fanout: dict[str, int], primary_floor: float, fanout_floor: int) -> list[Suspect]:
    suspects: list[Suspect] = []
    for row in rows:
        feature_id = str(row["feature_id"])
        session_id = str(row["session_id"])
        confidence = _to_float(row["confidence"])
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except Exception:
            metadata = {}

        commands = metadata.get("commands", [])
        if not isinstance(commands, list):
            commands = []
        commands = [str(c) for c in commands if isinstance(c, str)]

        signals = metadata.get("signals", [])
        if not isinstance(signals, list):
            signals = []
        signal0 = signals[0] if signals and isinstance(signals[0], dict) else {}
        signal_type = str(signal0.get("type") or "")
        signal_path = _normalize_path(str(signal0.get("path") or ""))
        title = str(metadata.get("title") or "")
        ambiguity_share = _to_float(metadata.get("ambiguityShare"))
        fanout_count = fanout.get(session_id, 0)

        has_feature_path_hint = _contains_feature_hint(feature_id, signal_path)
        has_feature_title_hint = _contains_feature_hint(feature_id, title)
        primary_like = confidence >= primary_floor
        key_cmd = any(cmd.startswith("/dev:execute-phase") or cmd.startswith("/dev:quick-feature") or cmd.startswith("/plan:plan-feature") for cmd in commands)

        reasons: list[str] = []
        if fanout_count >= fanout_floor:
            reasons.append(f"high_fanout({fanout_count})")
        if primary_like and not has_feature_path_hint and signal_type == "command_args_path":
            reasons.append("primary_like_command_path_mismatch")
        if primary_like and key_cmd and not has_feature_title_hint and not has_feature_path_hint:
            reasons.append("primary_like_title_path_mismatch")

        if reasons:
            suspects.append(
                Suspect(
                    feature_id=feature_id,
                    session_id=session_id,
                    confidence=round(confidence, 3),
                    ambiguity_share=round(ambiguity_share, 3),
                    title=title,
                    signal_type=signal_type,
                    signal_path=signal_path,
                    commands=commands[:5],
                    reason=";".join(reasons),
                    fanout_count=fanout_count,
                )
            )
    suspects.sort(key=lambda s: (s.fanout_count, s.confidence), reverse=True)
    return suspects


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/ccdash_cache.db")
    parser.add_argument("--feature", default="")
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
        rows = _load_links(conn, args.feature or None)
        fanout = _fanout_map(conn)
        suspects = _analyze(rows, fanout, args.primary_floor, args.fanout_floor)
        suspects = suspects[: max(1, args.limit)]

        if args.json:
            payload = {
                "db": str(db_path),
                "feature_filter": args.feature or None,
                "row_count": len(rows),
                "suspect_count": len(suspects),
                "suspects": [asdict(s) for s in suspects],
            }
            print(json.dumps(payload, indent=2))
            return 0

        print(f"DB: {db_path}")
        if args.feature:
            print(f"Feature filter: {args.feature}")
        print(f"Analyzed links: {len(rows)}")
        print(f"Suspects: {len(suspects)}")
        print("")
        for idx, s in enumerate(suspects, start=1):
            print(
                f"{idx:02d}. feature={s.feature_id} session={s.session_id} "
                f"conf={s.confidence} fanout={s.fanout_count} share={s.ambiguity_share}"
            )
            print(f"    reason={s.reason}")
            print(f"    title={s.title}")
            print(f"    signal={s.signal_type} path={s.signal_path}")
            if s.commands:
                print(f"    commands={', '.join(s.commands)}")
            print("")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
