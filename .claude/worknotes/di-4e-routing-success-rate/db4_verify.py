import asyncio, os, asyncpg
from collections import defaultdict

DSN = os.environ["CCDASH_DSN"]

QUERY = """
WITH per_session AS (
  SELECT session_id, SUM(call_count) AS calls, SUM(success_count) AS successes
  FROM session_tool_usage GROUP BY session_id),
win AS (
  SELECT s.id, s.project_id, s.skill_name, s.model FROM sessions s
  WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS'))
SELECT w.project_id, w.skill_name, w.model, w.id, ps.calls, ps.successes
FROM win w LEFT JOIN per_session ps ON ps.session_id = w.id;
"""

def classify_family(model: str) -> str:
    m = (model or "").strip().lower()
    if not m:
        return "empty model"
    if m.startswith("claude"):
        return "claude-family"
    if m.startswith("gpt") or m.startswith("codex") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return "gpt/codex-family"
    if "synthetic" in m or m in {"unknown", "test"}:
        return "synthetic"
    return "other"

async def main():
    conn = await asyncpg.connect(DSN)
    try:
        rows = await conn.fetch(QUERY)
    finally:
        await conn.close()

    keys = defaultdict(lambda: {"calls": 0, "successes": 0, "sessions": 0})
    for r in rows:
        k = (r["project_id"], r["skill_name"], r["model"])
        d = keys[k]
        d["sessions"] += 1
        calls = r["calls"] or 0
        succ = r["successes"] or 0
        d["calls"] += calls
        d["successes"] += succ

    fam_stats = defaultdict(lambda: {"keys": 0, "informative": 0, "zero_mean": 0, "no_data": 0, "calls": 0, "errors": 0})
    total_sessions_in_window = len(rows)
    total_keys = 0
    keys_clearing_min5 = 0
    sessions_in_clearing_keys = 0
    for (proj, skill, model), d in keys.items():
        total_keys += 1
        if d["sessions"] < 5:
            continue
        keys_clearing_min5 += 1
        sessions_in_clearing_keys += d["sessions"]
        fam = classify_family(model)
        fs = fam_stats[fam]
        fs["keys"] += 1
        errors = d["calls"] - d["successes"]
        fs["calls"] += d["calls"]
        fs["errors"] += errors
        if d["calls"] == 0:
            fs["no_data"] += 1
        elif errors == 0:
            fs["zero_mean"] += 1
        else:
            fs["informative"] += 1

    print(f"total_sessions_in_30d_window={total_sessions_in_window}")
    print(f"total_keys={total_keys} keys_clearing_min5={keys_clearing_min5} sessions_in_clearing_keys={sessions_in_clearing_keys}")
    print()
    header = f"{'family':<18}{'keys':>6}{'informative':>16}{'zero_mean':>11}{'no_data':>9}{'calls':>10}{'errors':>9}{'err_rate':>10}"
    print(header)
    for fam, fs in sorted(fam_stats.items()):
        err_rate = (fs["errors"] / fs["calls"] * 100) if fs["calls"] else float("nan")
        inf_pct = fs["informative"] / fs["keys"] * 100 if fs["keys"] else float("nan")
        print(
            f"{fam:<18}{fs['keys']:>6}{fs['informative']:>6}({inf_pct:5.1f}%){fs['zero_mean']:>11}{fs['no_data']:>9}{fs['calls']:>10}{fs['errors']:>9}{err_rate:>9.2f}%"
        )

asyncio.run(main())
