---
title: Multi-Project Command Center — Rollout & Fallback Strategy
description: Staged rollout procedures, fallback conditions, and instant rollback for the multi-project planning feature.
audience: operators, release engineers
tags:
  - multi-project
  - planning
  - rollout
  - feature-flags
  - fallback
  - release
created: 2026-05-30
updated: 2026-05-30
category: guides
status: published
related_documents:
  - docs/guides/multi-project-command-center-guide.md
  - docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
  - docs/project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md
---

# Multi-Project Command Center — Rollout & Fallback Strategy

Last updated: 2026-05-30

This guide documents the staged rollout approach, feature-flag disable strategy, and instant fallback procedures for the Multi-Project Planning Command Center (MPCC). The design ensures **zero-downtime rollback** — disabling either flag fully reverts to the single-project v1 experience without a code revert.

---

## Safety-by-Default: Release Branch

**On the release branch, both flags default to False (disabled).**

This ensures:
- The v1 single-project experience is the default in production.
- MPCC is an opt-in enhancement; no users are surprised by UI changes.
- If issues are discovered post-merge, operators can safely leave the feature disabled.

To enable MPCC in a deployed environment, explicitly set:

```bash
# Backend environment
export CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true

# Frontend build
export VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
npm run build
```

---

## Staged Rollout (Recommended)

A three-phase approach minimizes risk and allows early detection of edge cases:

### Phase 1: Alpha (Operator/Internal Testing)

**Scope:** 1–2 internal multi-project deployments.
**Duration:** 1–2 weeks.

**Steps:**

1. Deploy a dedicated test environment (or a feature branch).
2. Enable both flags:
   ```bash
   export CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
   export VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
   npm run build && npm run dev
   ```
3. Populate `projects.json` with 3–5 test projects.
4. (Optional) Customize `ProjectDisplayConfig` for a few projects to test color/group customization.
5. **Test scenarios:**
   - Switch between Portfolio and Current Project modes.
   - Filter projects on/off; verify board updates.
   - Change grouping (by state, project, feature, phase, agent, model).
   - Open a session detail from a non-active project; verify active project doesn't change.
   - Wait 5+ minutes; check staleness indicators turn yellow.
   - (Backend) Run the performance test with 10–20 concurrent sessions:
     ```bash
     backend/.venv/bin/python -m pytest backend/tests/test_multi_project_command_center_perf.py -v
     ```
6. **Monitoring:** Check backend logs for aggregation latency, API error rates, and any partial-failure responses.
7. **Go/No-Go Decision:** If no blockers, proceed to Phase 2. If issues, either fix and re-test or escalate to Phase 0 (patch).

### Phase 2: Beta (Limited Production Rollout)

**Scope:** 1–3 customer deployments (or internal staging) with early adopters.
**Duration:** 2–4 weeks.

**Steps:**

1. Deploy to beta environments:
   ```bash
   CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true \
   VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true \
   npm run build
   ```
2. Announce the beta feature; encourage feedback.
3. **Monitor:**
   - API response times (target: <500ms for <250 sessions).
   - Error rates in the command-center endpoint.
   - User-reported issues (via issue tracker or Slack).
   - Staleness signal accuracy.
4. **Gather telemetry:**
   - How often is Portfolio mode used vs. Current Project?
   - Which grouping option is most popular?
   - How many projects do typical users toggle on/off?
5. **Go/No-Go Decision:**
   - No blockers + positive feedback → proceed to Phase 3.
   - Non-critical issues → fix in a patch, loop back to beta testing.
   - Critical issue (e.g., data corruption, >1s latency spike) → trigger immediate fallback (see **Fallback Procedures** below).

### Phase 3: General Availability (GA)

**Scope:** All CCDash deployments (default-off until explicitly enabled).
**Duration:** Ongoing.

**Steps:**

1. Merge to main with both flags default-off.
2. **Release notes:**
   - Document the new feature.
   - Provide enable/disable instructions (operator guide).
   - Link to rollout guide and troubleshooting.
3. **Communication:**
   - Email/Slack: "MPCC is now available. Enable it in production with two env vars (see docs)."
   - Provide a quick-start: "Copy/paste the env vars, rebuild, and restart the backend."
4. **Ongoing support:**
   - Monitor production for issues.
   - Update documentation based on operator feedback.
   - Plan deferrals (e.g., >100 project support) for v1.1.

---

## Feature Flags: Independent Disable

The two flags work independently. Disabling either one fully disables MPCC:

| Backend Flag | Frontend Flag | MPCC Status | Behavior |
|--------------|---------------|------------|----------|
| Enabled | Enabled | **ON** | Portfolio toggle visible; multi-project endpoints available. |
| Enabled | Disabled | **OFF** | Backend is ready, but frontend doesn't expose the UI. Portfolio toggle hidden; single-project v1 experience. |
| Disabled | Enabled | **OFF** | Frontend UI is compiled, but backend returns 404 on multi-project endpoints. Portfolio toggle visible but non-functional. |
| Disabled | Disabled | **OFF** | Fully disabled; all MPCC code paths are unreachable. Single-project v1 experience. |

**Recommended:** Always disable both flags together. However, if one flag is misconfigured, the other provides a safety fallback.

### Disabling the Backend Flag

**Immediate effect (no restart required if using hot reload):**

```bash
# In .env or .env.local:
CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false

# Or unset (defaults to False):
unset CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED
```

The backend will return `404` on:
- `GET /api/agent/planning/multi-project/command-center`
- `GET /api/agent/planning/multi-project/session-board`

Existing connections are unaffected; the single-project API (`/api/agent/planning/...` without `/multi-project/`) continues to work.

### Disabling the Frontend Flag

**Requires a rebuild and redeploy:**

```bash
# In .env.local or CI/CD:
VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false

# Rebuild:
npm run build

# Redeploy the new build.
```

After redeploy, users see the Planning Command Center without the Portfolio/Current Project toggle. Multi-project UI code is not executed.

---

## Fallback Procedures

If a critical issue is detected during or after rollout, use these steps to disable MPCC instantly.

### Scenario 1: Response Time Regression (>1s for >100 sessions)

**Problem:** The multi-project aggregation endpoint is slow; planning page is sluggish.

**Immediate Action:**

1. Disable the backend flag:
   ```bash
   CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false
   ```
2. Restart the backend (or wait for env var hot-reload if available).
3. Existing Portfolio mode tabs will receive 404 responses; users automatically fall back to Current Project mode.
4. The single-project planning page is responsive again.

**Root Cause Analysis:**
- Check if a new project with >1000 sessions was added; reduce pagination page size or increase concurrency.
- Review backend logs for slow repository queries.
- Run the performance test:
  ```bash
  backend/.venv/bin/python -m pytest backend/tests/test_multi_project_command_center_perf.py -v
  ```

**Re-enable:**
Once fixed, re-enable the backend flag and monitor for 24+ hours before expanding to additional environments.

### Scenario 2: Partial-Failure Cascade (>30% of projects failing)

**Problem:** Many projects report staleness (red indicators); board is incomplete or misleading.

**Immediate Action:**

1. Check the file watcher health:
   ```bash
   # Backend logs should show periodic watcher ticks
   grep "FileWatcher" logs/ccdash.log | tail -20
   ```
2. If file watcher is stuck, restart the worker:
   ```bash
   npm run dev:worker &
   ```
3. Wait 2–3 minutes for rescans to complete.
4. If issues persist, disable the backend flag:
   ```bash
   CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false
   ```

**Root Cause Analysis:**
- Verify each project's filesystem is readable and not locked.
- Check for permission issues on `.claude/progress/` directories.
- Ensure `projects.json` paths are correct.

**Re-enable:**
After fixing project accessibility, re-enable the flag and validate with a manual rescan.

### Scenario 3: Data Corruption or Contract Violations

**Problem:** A project_id is missing from session records, or the grouping logic produces duplicate cards.

**Immediate Action:**

1. Disable the backend flag:
   ```bash
   CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false
   ```
2. Clear the query cache:
   ```bash
   export CCDASH_QUERY_CACHE_TTL_SECONDS=0
   npm run dev:backend  # or restart your production backend
   ```
3. Users will see the single-project v1 experience; no data is lost.

**Root Cause Analysis:**
- Review recent changes to `backend/application/services/agent_queries/planning.py` or `backend/routers/agent.py`.
- Check if a migration script or schema change introduced inconsistent data.
- Run the contract-validation test:
  ```bash
  backend/.venv/bin/python -m pytest backend/tests/test_multi_project_contracts.py -v
  ```

**Re-enable:**
After fixes are validated via unit tests and staged re-testing, re-enable the flag with increased monitoring.

---

## Rollback Timeline

| Trigger | Time to Action | Scope |
|---------|---|--------|
| Response time >1s detected | <1 hour | Disable backend flag; diagnose. |
| >30% project staleness reported | <30 minutes | Restart worker; check filesystem. If unresolved, disable backend flag. |
| Contract validation failure | <15 minutes | Disable both flags; investigate data schema. |
| User-reported critical bug | <1 hour | Assess scope; if widespread, disable backend flag and plan a patch. |

**All rollbacks are instantaneous:** no code revert, no database migration, no data loss.

---

## Monitoring & Alerting (Recommended)

Set up monitoring for these metrics during rollout:

| Metric | Healthy Range | Action If Unhealthy |
|--------|---|---|
| **Command-center endpoint response time (p95)** | <500ms | Investigate query performance; disable flag if >1s. |
| **Multi-project API error rate** | <1% | Check logs for partial failures; disable flag if >5%. |
| **Staleness indicator accuracy** | >95% correct | Verify file watcher; restart worker if >5% mismatch. |
| **Portfolio mode usage** | N/A (informational) | Expected to grow post-launch. |
| **Backend CPU during aggregation** | <20% spike | Reduce concurrency if sustained >30%. |

**Alert Thresholds:**
- Response time >1s for 5+ minutes → page operator.
- Error rate >5% → disable backend flag and alert engineering.
- Staleness false positive >10% → check file watcher health.

---

## Post-Rollout Validation Checklist

Before marking rollout complete, verify:

- [ ] Alpha testing passed with no blockers.
- [ ] Beta testing completed; feedback addressed.
- [ ] Both flags are set to False (disabled) on release branch.
- [ ] Documentation (operator guide, rollout guide) is published.
- [ ] Release notes mention the opt-in feature and provide enable instructions.
- [ ] Monitoring/alerting is configured.
- [ ] Support team is trained on enable/disable procedures.
- [ ] Known limitations are documented (see `docs/guides/multi-project-command-center-guide.md` § Known Limitations).

---

## Reference: Instant Disable Cheat Sheet

### For Operators

To disable MPCC in production without a code revert:

**Step 1: Disable the backend**
```bash
# SSH into your backend server
ssh ops@production-backend

# Edit the environment configuration
sudo vim /etc/ccdash/.env.production

# Add or update:
# CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false

# Restart the backend service
sudo systemctl restart ccdash-backend
```

**Step 2: Disable the frontend (optional, if you want to be thorough)**
```bash
# Trigger a rebuild with the flag disabled
git clone <repo> && cd <repo>
VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false npm run build

# Deploy the new build
./deploy.sh build/dist/
```

**Step 3: Verify**
```bash
# Check the Planning page loads without errors
curl -s http://production-planning/api/agent/planning/command-center | jq .

# The multi-project endpoint should return 404
curl -s http://production-planning/api/agent/planning/multi-project/command-center
# Expected: HTTP 404
```

### For Developers

To rapidly test disable/enable locally:

```bash
# Disable
CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false npm run dev

# Enable
CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true npm run dev

# Changes take effect immediately (no rebuild if hot reload is enabled).
```

---

## Related Documentation

- **Operator Guide:** `docs/guides/multi-project-command-center-guide.md` — How to enable, configure, and operate MPCC.
- **PRD:** `docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md` — Feature requirements.
- **Implementation Plan:** `docs/project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md` — Technical architecture.
- **Feature Guide:** `.claude/worknotes/multi-project-planning-command-center-v1/feature-guide.md` — Closeout summary and test coverage.
