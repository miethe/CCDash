---
title: "Design Spec: Routing Feedback Window/Decay Numeric Defaults (DI-3)"
doc_type: design-spec
maturity: shaping
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
status: draft
created: 2026-07-31
updated: 2026-07-31
audience: developers
category: operational-tuning
tags:
  - routing-feedback
  - window-defaults
  - decay-function
  - empirical-tuning
  - deferred-item
related_documents:
  - docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
description: |
  Deferred item DI-3: Window length and decay-weight numeric defaults.
  Specifies the candidate values for rolling-window length (currently 30 days)
  and sample-size minimum-eligibility threshold (currently N≥5). Also documents
  decay weighting for recency bias (currently unused, proposed for Phase 7+).
  This item is deferred because empirical validation in production routing is needed
  before locking defaults. Documents current spike findings, tuning rationale,
  and promotion criteria for Phase 7+ empirical refinement.
schema_version: 2
---

# Design Spec: Routing Feedback Window/Decay Numeric Defaults (DI-3)

## Deferral Rationale

**Status**: Research-needed — The 30-day window and N≥5 sample-size thresholds are **spike-anchored
placeholders**, not locked requirements. PRD OQ-6 is explicitly unresolved. Production routing must
consume CCDash feedback and empirically validate (or invalidate) the candidates before final locking.

**CCDash's Current Approach (Phase 1–6)**:
- Rolling window: 30 days (hardcoded; see config knobs below)
- Sample-size minimum: N≥5 sessions (hardcoded; see config knobs)
- Decay function: None (all samples weighted equally within the window)
- Recency bias: Not implemented

**Trigger for Promotion**: Router-side consumption goes live and empirically validates routing
outcomes over 2–4 weeks of production traffic. Metrics (success rate, cost, feedback lag) are
collected and inform final defaults for Phase 7+ hardening.

---

## 1. Current State (Phase 1–6)

### 1.1 Rolling Window Length

**Current Default**: 30 days

**Configuration**:
```python
# backend/config.py
CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS = int(
    os.getenv("CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS", "30")
)
```

**Meaning**: A `RoutingFeedbackKeyDTO` for `(source_skill_name × model)` aggregates all sessions
from the past 30 days. Sessions older than 30 days are excluded.

**Rationale** (from value-findings spike):
- 30 days is long enough to accumulate signal (typically 50–200 sessions per model per task class)
- 30 days is recent enough to catch model drift (new Claude release, new task in production)
- Matches typical SLA review cycles (weekly to monthly)

### 1.2 Sample-Size Minimum

**Current Default**: N≥5

**Configuration**:
```python
# backend/config.py
CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE = int(
    os.getenv("CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE", "5")
)

# Usage in service
eligible_for_adjustment = (
    sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE
    and task_class not in PROTECTED_CLASSES
)
```

**Meaning**: A key is only marked `eligible_for_adjustment = true` if it has at least 5 sessions
in the window. Below 5, `eligible_for_adjustment = false` (coverage-only; metrics emit but router
should not use them for routing decisions).

**Rationale** (from value-findings spike):
- N<5 has high statistical noise (single failure = 20% error rate)
- N≥5 reduces noise to ~10% margin of error (rough rule-of-thumb)
- Typical production model usage exceeds 5 sessions per model per 30-day window

### 1.3 Decay Function (Not Implemented)

**Current State**: All samples weighted equally within the window. No recency bias.

**Candidate (Proposed for Phase 7+)**:

```python
def compute_decay_weight(session_timestamp, current_time, window_days=30):
    """
    Exponential decay: recent sessions weighted higher, older sessions lower.
    
    Example: A session from today has weight ≈ 1.0
             A session from 15 days ago has weight ≈ 0.7
             A session from 30 days ago has weight ≈ 0.5
    """
    age_days = (current_time - session_timestamp).days
    if age_days > window_days:
        return 0.0
    
    # Exponential decay: weight = exp(-age / half_life)
    # half_life = window_days / ln(2) ≈ window_days / 0.693
    half_life = window_days / 0.693
    weight = math.exp(-age_days / half_life)
    return weight
```

**Effect on Metrics**:
- `success_rate` becomes a weighted average (instead of simple mean)
- `cost_index` and `regression_rate` likewise weighted
- `confidence` increases for recent samples (lower decay weight implies lower confidence)

**Not Shipped Today**: Full decay implementation requires changes to
`backend/application/services/agent_queries/routing_rollup.py`. Phase 1–6 uses simple mean.

---

## 2. Tuning Rationale & Trade-offs

### 2.1 Window Length Trade-offs

| Window Length | Advantages | Disadvantages | Use Case |
|---------------|-----------|---------------|----------|
| 7 days | High recency; catches model drift quickly | Low sample counts; high noise | Dev/fast iteration |
| 14 days | Moderate recency; moderate sample size | May miss slow trends | Short-cycle products |
| 30 days (Current) | Good balance of recency + sample size | Slow to detect sustained drift | General production |
| 60 days | High sample count; stable signal | May miss recent regressions | Mature systems |
| 90 days | Very stable signal; long-term trends | Slow feedback loop; old data skews | Strategic review |

**Recommendation for Phase 1–6**: 30 days is appropriate. Phase 7+ empirical data informs whether
to adjust.

### 2.2 Sample-Size Threshold Trade-offs

| Min Samples | Advantages | Disadvantages | Use Case |
|-------------|-----------|---------------|----------|
| N≥1 | Catches regressions immediately | High false-positives; single failures dominate | High-risk tasks only |
| N≥3 | Rapid feedback | Still noisy (~33% margin of error) | Short-cycle tasks |
| N≥5 (Current) | Good noise-reduction balance | May delay signal for rare tasks | General production |
| N≥10 | Low false-positive rate | Slow feedback for rare tasks | Long-running projects |
| N≥20 | Very stable signal | May never trigger for rare tasks | Strategic analysis |

**Recommendation for Phase 1–6**: N≥5 is appropriate. Phase 7+ empirical data determines if raising
to N≥10 (for production stability) or lowering to N≥3 (if drift detection is critical).

### 2.3 Recency Bias (Decay Function)

**Rationale for Decay**:
- Recent samples are more indicative of current model behavior (e.g., latest Claude release)
- Old samples may reflect outdated task definitions or prior model versions
- Exponential decay gracefully down-weights stale data without hard cutoff

**When to Apply Decay**:
- High-velocity product (model/task changes weekly): use decay = yes
- Stable product (same models/tasks for months): use decay = no (or weak decay)
- Current production: unknown; empirical validation needed

**Current Configuration** (Candidate):
```python
# backend/config.py (Phase 7+ if promoted)
CCDASH_ROUTING_FEEDBACK_DECAY_ENABLED = False  # Disabled today
CCDASH_ROUTING_FEEDBACK_DECAY_HALF_LIFE_DAYS = 14  # 50% weight at 14 days
```

---

## 3. Empirical Validation Scenarios (Phase 7+)

This section describes how production routing feedback should be evaluated before locking defaults.

### 3.1 Validation Metrics

**Collect weekly during Phase 7+ pilot**:

| Metric | Query | Target | Failure Mode |
|--------|-------|--------|--------------|
| `signal_lag` | time from session to routing adjustment | < 2 days | Feedback too stale to be actionable |
| `adjustment_frequency` | # routes changed per week | stable (not oscillating) | Instability suggests N or window too small |
| `false_positive_rate` | routes downweighted but later recovered | < 5% | Window too short or N too low |
| `signal_loss` | models in production but no feedback rows | < 5% | Window too long or N too high |
| `cost_impact` | estimated cost delta from routing changes | positive (cost reduced) | Feedback not actually improving routes |
| `success_rate_trend` | trend of success rates in feedback | stable or improving | Decay is working as intended |

### 3.2 Scenario A: 30-Day Window is Too Long

**Observed**: Signal lag > 3 days; old task definitions are causing false negatives in
current task. Success rate is not improving.

**Actions**:
- Reduce window to 14–21 days
- Increase N to 10 (to compensate for smaller sample pool)
- Enable decay with half-life = 7 days (to down-weight old task data)
- Re-run pilot for 1 week

**Phase 7+ Decision**: If metrics improve, lock new defaults. Otherwise, revert.

### 3.3 Scenario B: 30-Day Window is Too Short

**Observed**: Adjustment frequency is high (route changing multiple times per week); many false
positives (downweighted models recover immediately). Cost impact is neutral or negative.

**Actions**:
- Increase window to 45–60 days
- Decrease N to 3 (model may not appear frequently)
- Disable decay (or increase half-life to 21+ days)
- Re-run pilot for 2 weeks

**Phase 7+ Decision**: If metrics stabilize, lock new defaults. Otherwise, revert.

### 3.4 Scenario C: N≥5 is Too High (Sample Starvation)

**Observed**: Many task_class × model pairs are marked `eligible_for_adjustment = false` (low
sample count). Rare models never get feedback signal.

**Actions**:
- Reduce N to 3 or 2
- Increase window to 45 days (to boost sample pool)
- Enable strong decay (half-life = 7 days) to mitigate false positives
- Add router-side re-gating: require 2+ consecutive signals before downweighting

**Phase 7+ Decision**: If signal loss drops and false positives remain low, lock new defaults.

### 3.5 Scenario D: Decay Function is Necessary

**Observed**: Model is downweighted based on 30-day history, but 25 days ago the task was different
(old version). Recent sessions (5 days old) show improvement. Simple mean skews toward the old task.

**Actions**:
- Enable decay with half-life = 14 days
- Recompute all metrics; re-run pilot

**Phase 7+ Decision**: If success-rate accuracy improves (fewer false negatives for recently-fixed
models), lock decay enabled.

---

## 4. Phase 1–6 Validation (Sanity Checks)

Even though numeric defaults are deferred, Phase 1–6 includes sanity checks to catch egregious
misconfigurations:

### 4.1 Window Size Sanity

```python
# backend/tests/test_routing_rollup_defaults.py (Proposed test)
def test_window_size_reasonable():
    """Window must be between 7 and 365 days."""
    window = config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS
    assert 7 <= window <= 365, f"Window {window} is unreasonable"
```

### 4.2 Sample Threshold Sanity

```python
def test_min_sample_reasonable():
    """Sample threshold must be between 1 and 100."""
    n_min = config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE
    assert 1 <= n_min <= 100, f"Min sample {n_min} is unreasonable"
```

### 4.3 Empirical Distribution Check

```python
def test_routing_feedback_sample_distribution():
    """
    Verify that sample counts follow expected distribution.
    
    Sanity: 80% of task_class × model pairs should be either:
    - Above N_min (eligible), or
    - Below N_min but observed in at least one window
    
    Red flag: 95%+ of pairs are sub-threshold, suggesting N_min is too high.
    """
    rollup = service.compute_routing_feedback_rollup(project_id)
    eligible = len([k for k in rollup.keys if k.eligible_for_adjustment])
    ineligible = len([k for k in rollup.keys if not k.eligible_for_adjustment])
    
    if ineligible > 0:
        ineligibility_rate = ineligible / (eligible + ineligible)
        logger.info(f"Ineligibility rate: {ineligibility_rate:.1%}")
        # Log for operator review; don't fail the test
```

---

## 5. Operator Tuning Guide (Phase 1–6)

Operators can adjust window and sample-size via environment variables:

```bash
# Shorter window for dev/rapid iteration
export CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS=7
export CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE=2

# Longer window + higher threshold for stability
export CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS=60
export CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE=10

# Restart worker or backend to apply
```

**Guidance for Adjustment**:
- Start with 30 days + N≥5 (defaults)
- Monitor ineligibility rate and adjustment frequency for 1 week
- If > 50% of task_class × model pairs are ineligible, reduce N to 3
- If adjustment frequency is > 2x per day, increase window to 45 days
- Do NOT enable decay unless you understand its impact (Phase 7+ only)

---

## 6. Decay Function Design (Phase 7+ Candidate)

If decay is promoted in Phase 7+, the following design applies:

### 6.1 Implementation

```python
# backend/application/services/agent_queries/routing_rollup.py (Phase 7+ if promoted)

def compute_rolling_window_metrics_with_decay(
    sessions: List[Session],
    current_time: datetime,
    window_days: int = 30,
    decay_enabled: bool = False,
    decay_half_life_days: float = 14.0,
) -> RoutingMetrics:
    """
    Compute routing metrics with optional exponential decay.
    
    Args:
        sessions: Sessions within the window
        current_time: Reference time (now)
        window_days: Window length (days)
        decay_enabled: Enable exponential decay?
        decay_half_life_days: Half-life for decay (days)
    
    Returns:
        RoutingMetrics with success_rate, cost_index, regression_rate, confidence
    """
    if not sessions:
        return RoutingMetrics(success_rate=0.5, cost_index=1.0, ...)
    
    weights = []
    outcomes = []
    costs = []
    
    for session in sessions:
        # Compute decay weight
        age = (current_time - session.timestamp).days
        if decay_enabled:
            weight = math.exp(-age / decay_half_life_days)
        else:
            weight = 1.0
        
        weights.append(weight)
        outcomes.append(session.success)
        costs.append(session.cost_index)
    
    # Weighted average
    total_weight = sum(weights)
    success_rate = (
        sum(w * (1 if outcome else 0) for w, outcome in zip(weights, outcomes))
        / total_weight
    )
    cost_index = (
        sum(w * cost for w, cost in zip(weights, costs))
        / total_weight
    )
    
    # Confidence is inversely proportional to average weight
    # High average weight = recent samples = high confidence
    avg_weight = total_weight / len(sessions)
    confidence = min(1.0, avg_weight * 1.2)  # 1.2 is scaling factor
    
    return RoutingMetrics(
        success_rate=success_rate,
        cost_index=cost_index,
        confidence=confidence,
        ...
    )
```

### 6.2 Configuration

```python
# backend/config.py (Phase 7+ if promoted)

CCDASH_ROUTING_FEEDBACK_DECAY_ENABLED = os.getenv(
    "CCDASH_ROUTING_FEEDBACK_DECAY_ENABLED", "false"
).lower() == "true"

CCDASH_ROUTING_FEEDBACK_DECAY_HALF_LIFE_DAYS = float(
    os.getenv("CCDASH_ROUTING_FEEDBACK_DECAY_HALF_LIFE_DAYS", "14.0")
)
```

### 6.3 Test Coverage (Phase 7+)

```python
def test_decay_function_correctness():
    """Verify exponential decay formula."""
    current = datetime.now()
    half_life = 14.0
    
    # Session from today (age=0) should have weight ≈ 1.0
    weight_today = math.exp(-0 / half_life)
    assert abs(weight_today - 1.0) < 0.01
    
    # Session from half-life ago should have weight ≈ 0.5
    weight_half = math.exp(-14 / half_life)
    assert abs(weight_half - 0.5) < 0.01
    
    # Session from 30 days should have weight ≈ 0.125
    weight_30d = math.exp(-30 / half_life)
    assert abs(weight_30d - 0.125) < 0.01
```

---

## 7. Deferred Tasks & Next Steps

### 7.1 No CCDash Changes Required Today

All numeric defaults are locked at Phase 1–6 safe values (30 days, N≥5, no decay). No new code
needed until Phase 7+.

### 7.2 Next Steps (If Promoted to Phase 7+)

1. **Router goes live** with consumption of `/api/v1/routing/rollup`
   - Collect empirical metrics (§3.1) weekly for 2–4 weeks

2. **Analyze pilot results**
   - Plot signal lag, adjustment frequency, false-positive rate
   - Identify scenarios (A–D from §3) that apply

3. **Co-author tuning recommendations**
   - CCDash owner + router owner meet to discuss findings
   - Update this spec with empirically-validated defaults

4. **Implement decay function** (if needed)
   - CCDash owner implements §6.1–6.3
   - Add comprehensive test coverage
   - Push to Phase 7 release

5. **Lock final defaults**
   - Update Phase 7 plan with new window/N values
   - Document tuning guide in `/docs/guides/routing-feedback-loop.md`
   - Backfill historical data if recomputation is needed

---

## 8. Current Configuration (Reference)

**Phase 1–6 Locked Defaults**:

```python
# backend/config.py (as of 2026-07-31)

CCDASH_ROUTING_FEEDBACK_ENABLED = os.getenv(
    "CCDASH_ROUTING_FEEDBACK_ENABLED", "false"
).lower() == "true"

CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS = int(
    os.getenv("CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS", "30")
)

CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE = int(
    os.getenv("CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE", "5")
)

# Decay (candidate for Phase 7+)
# CCDASH_ROUTING_FEEDBACK_DECAY_ENABLED = False
# CCDASH_ROUTING_FEEDBACK_DECAY_HALF_LIFE_DAYS = 14.0
```

**Operator Override**:

```bash
# To experiment in dev:
export CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS=14
export CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE=3

# Restart backend/worker to apply
npm run dev:backend
```

---

## References

- **Proof→Routing Loop PRD**: `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`
  (OQ-6, §13, value-findings spike)
- **Spike Technical Findings**: `docs/project_plans/exploration/proof-to-routing-loop/spikes/tech-findings.md`
- **Spike Value Findings**: `docs/project_plans/exploration/proof-to-routing-loop/spikes/value-findings.md`
- **Routing Rollup Service**: `backend/application/services/agent_queries/routing_rollup.py`
- **Backend Config**: `backend/config.py`
