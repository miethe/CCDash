# Memory — task-completion-validator (CCDash)

- [Disk-full env hazard](env-disk-full-hazard.md) — confirmed 2026-07-21, still active: root vol at 100% capacity, ~137Mi avail; blocks Write/Bash (ENOSPC) mid frontend-smoke work
- [Progress-file discipline gaps observed](progress-file-discipline-gaps.md) — recurring pattern: tasks claimed "completed" in agent summaries without progress YAML update; blockers:[] left stale after a reported blocker
