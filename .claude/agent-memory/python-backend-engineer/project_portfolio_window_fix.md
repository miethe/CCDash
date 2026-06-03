---
name: project-portfolio-window-fix
description: Portfolio board always showed zero active sessions — fixed by widening the active-session window from 600s to 30d for the multi-project service
metadata:
  type: project
---

Portfolio board (`MultiProjectActiveSessionBoardQueryService`) was gated on a 600s freshness window inherited from `CCDASH_LIVE_AGENTS_WINDOW_SECONDS`. Newest active DB rows were ~8h old so the window returned 0 for every project.

**Why:** The 600s window is correct for the live-agents chip (real-time heartbeat), but wrong for the portfolio board which indexes sessions from the last hours/days.

**Fix applied:**
- `backend/config.py`: added `CCDASH_PLANNING_PORTFOLIO_ACTIVE_WINDOW_SECONDS` (default 30 days = 2592000s) next to `CCDASH_LIVE_AGENTS_WINDOW_SECONDS`.
- `multi_project_planning_sessions.py:_ACTIVE_SESSION_WINDOW`: now reads from `CCDASH_PLANNING_PORTFOLIO_ACTIVE_WINDOW_SECONDS` instead of `CCDASH_LIVE_AGENTS_WINDOW_SECONDS`.
- `_build_session_project_summary` accepts `window_seconds` kwarg and passes it to `count_active` so badge and board agree.
- Both fast-path and normal-path `_build_session_project_summary` callsites pass `window_seconds=effective_window`.
- Router `window_seconds` query param was already present (no change needed).
- Single-project board intentionally left unchanged.

**How to apply:** When tuning "active" windows — keep the live-agents 600s constant and the portfolio 30d constant SEPARATE. The 30d default excludes 57–93d phantom rows from switched-away projects.
