---
name: env-disk-full-hazard
description: CCDash dev host root volume runs at/near 100% capacity, causing ENOSPC failures in both harness scratch and the real repo filesystem — blocks Write/Bash tools mid-task, especially during frontend runtime-smoke (screenshot capture) work.
metadata:
  type: project
---

Confirmed 2026-07-21: `df -h /` showed `926Gi` size, `16Gi` used sounds wrong for 100% capacity —
actual signal is **Capacity 100%, Avail 137Mi** (iused 447k/1.4M, 24%) — i.e. the filesystem is
byte-full even though inode usage is low. This caused a documented mid-phase failure: a
`frontend-developer` task (T3-006, research-foundry-run-telemetry phase 3) got through one
Puppeteer screenshot capture, then hit ENOSPC first in the Claude Code harness's own tmp scratch
(`/private/tmp/claude-501/.../tasks/`), then in the **real repo filesystem** via the Write tool
(confirmed via two independent failed Write attempts to `.claude/progress/...` and
`.claude/evidence/phase-3/...`). This blocked progress-file updates and a second screenshot for the
rest of that session.

**Why:** disk space is host-level, not code-level — a validator or executor hitting mysterious
Write/Bash failures mid-task on this host should check `df -h /` before assuming a code or logic bug.

**How to apply:** when reviewing a "partial/blocked" completion report that cites ENOSPC or vague
Write/Bash failures, re-run `df -h /` yourself before accepting the blocker as resolved-by-now — as
of 2026-07-21 it was still at 100% capacity / ~137Mi avail, i.e. the blocker was still live at
review time, not just a stale one-off. Don't let an agent's "should be resolved once disk space
recovers" framing stand unverified.
