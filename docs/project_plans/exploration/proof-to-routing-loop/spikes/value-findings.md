---
leg: value
confidence: 0.75
signal_viable: conditional-on-coarsening
---

# Value Leg — Data-Signal Viability Findings

## 1. Viability verdict

**Not inert, but the nominal 4-field tuple is dead weight — signal only lives in a 2-effective-dimension, ~5-week-old, 5–23%-populated slice of the data.** With the tuple coarsened to `(skill_name, model)` — the only two fields that are both populated and independently informative — real telemetry produces 40 distinct keys, 21 of which (52%) already clear a `sample_count ≥ 5` threshold and 14 (35%) clear `≥ 10`, computed over the entire population history of the `skill_name` column (~7 weeks). Restricting to a realistic 30-day rolling window still yields 15/30 keys (50%) at N≥5 and 10/30 (33%) at N≥10. The deal-killer's *density* half is **refuted** for this coarsened tuple; it would fire as written for the spec's literal 4-field tuple, because two of the four fields are never populated.

## 2. DB reality

- Two candidate DB files exist: `.ccdash.db` (repo root) is **0 bytes, no tables** — dead/unused. The real cache is `data/ccdash_cache.db`, resolved via `backend/config.py:57` (`CCDASH_DB_PATH`, default `data/ccdash_cache.db`), SQLite backend, **13.7 GB, populated**.
- `sessions` table total row count: **14,399**.
- Columns available for the spec's tuple, per `.schema sessions`:
  - `model` (raw model string, e.g. `claude-sonnet-4-6`) — **populated**, 30+ distinct values.
  - `model_slug` — populated but mostly empty (`11,505/14,399` blank); where present, roughly mirrors `model`.
  - `model_variant` — column exists, **0/14,399 rows non-empty**. Dead column.
  - `profile` — column exists, **0/14,399 rows non-empty**. Dead column.
  - `effort_tier` — column exists, **0/14,399 rows non-empty**. Dead column.
  - `launcher` — column exists, **0/14,399 rows non-empty**. Dead column.
  - `skill_name` — the best `task_class` proxy candidate. **767/14,399 (5.3%) non-empty** overall; started being populated only **2026-06-02** (~7 weeks of history as of 2026-07-23), reaching **515/2,266 (22.7%)** density in the most recent 30-day window. Trending up, not flat.
  - `workflow_id` — populated in 2,958/14,399 rows but is a **per-run UUID** (2,066 distinct values, max count 40), not a task-class category — unusable as a rollup key directly.
  - `command_slug` — sparser than `skill_name` (143/14,399 non-empty, 1%). Worse candidate.
  - `model_provider` — **not a stored column at all**. It is derived at query time from the `model` string via `backend/db/repositories/feature_rollup.py:_derive_provider()` (substring match: `claude`→anthropic, `gpt`→openai, etc.). This is a deterministic *function of* `model`, contributing zero extra split when added to a tuple that already includes `model`.
- **Conclusion**: of the spec's stated tuple `(task_class, model, provider, profile)`, only `model` is genuinely populated as claimed. `profile`/`effort_tier`/`model_variant` are schema-present but write-path-dead (corroborates the tech leg's likely finding — flag for cross-check). `provider` is derivable but adds no independent cardinality. `task_class` has no first-class column; the only usable proxy (`skill_name`) is real but young and sparse.

## 3. Per-key density — actual GROUP BY results

Tuple as literally specified `(skill_name, model, profile)` collapses to `(skill_name, model)` since `profile` is constant (`''`) for every row — GROUP BY over it never splits a key further.

**`(skill_name, model)`, `skill_name <> ''` only (excludes the "no skill" bucket, which is not a real task_class), full history since capture began (2026-06-02 → 2026-07-22):**

```
distinct keys:            40
keys with count >= 5:     21   (52.5%)
keys with count >= 10:    14   (35.0%)
total qualifying sessions: 767
```

Top keys (skill_name | model | count):
```
symbols          | claude-haiku-4-5-20251001 | 145
skillmeat-cli     | claude-sonnet-4-6         | 114
skillmeat-cli     | claude-sonnet-5           | 71
dev-execution     | claude-opus-4-8           | 68
planning          | claude-sonnet-4-6         | 52
planning          | claude-opus-4-8           | 39
frontend-design   | claude-sonnet-5           | 34
dev-execution     | claude-sonnet-5           | 33
dev-execution     | claude-sonnet-4-6         | 28
frontend-design   | claude-sonnet-4-6         | 28
debugging         | claude-opus-4-8           | 25
planning          | claude-sonnet-5           | 17
skillmeat-cli     | claude-opus-4-8           | 14
ica-delegate      | claude-opus-4-8           | 11
release           | claude-opus-4-8           | 8   (below N=10, above N=5)
```
(remaining 25 keys tail off from 8 down to 1)

**Same tuple, restricted to a realistic 30-day rolling window (2026-06-23 → 2026-07-22)** — this is the more honest proxy for what a live rollup job would actually see, since the design spec calls for a rolling window with decay:

```
distinct keys:            30
keys with count >= 5:     15   (50.0%)
keys with count >= 10:    10   (33.3%)
total sessions in window: 2,266   (of which 515, 22.7%, have skill_name populated)
```

Density and threshold-clearing rate are essentially stable between "all history since capture start" and "last 30 days" — this is a young but not-collapsing signal, not a one-time burst.

## 4. Effect of coarsening the tuple

- **Dropping `profile`/`effort_tier`/`model_variant`**: mandatory, not optional — they contribute nothing (all rows constant/blank). This is coarsening *forced by data reality*, not a choice; it collapses the nominal 4-D tuple to effectively 2-D (`skill_name`, `model`) before any deliberate design decision is made.
- **Adding derived `provider` back in**: makes **zero difference** to key count, because provider is a many-to-one function of `model` (confirmed: all 6 distinct Claude model strings in the skill_name-populated slice map to `provider=anthropic`; the 1 remaining model family maps to `other`/openai). Provider never independently splits a key that already includes `model` — it can only ever be a *coarsening* of `model`, never a refinement.
- **Coarsening `skill_name` alone (drop `model` entirely)** — i.e., `task_class` without model discrimination:
  ```
  distinct keys:          17
  keys with count >= 5:   10   (58.8%)
  keys with count >= 10:   7   (41.2%)
  ```
  This lifts the *pass rate* modestly (58.8% vs 52.5% at N=5) but loses the entire point of the rollup — a per-model, per-provider comparison — since it no longer discriminates by model at all. Not a useful coarsening for the design spec's purpose, only useful as a sanity check that skill_name itself is the scarce resource, not model.
- **Net effect**: coarsening from the nominal spec (4 fields) down to the data-supported reality (`skill_name × model`, with `provider` riding along for free) is what makes the tuple viable at all. Any coarsening *beyond* that (dropping model too) trades away the signal's usefulness for a small density bump that isn't needed.

## 5. Bottom line on the deal-killer's density half

The deal-killer as charter-worded — "real telemetry lacks the per-tuple sample density to ever clear a minimum-sample threshold" — is **refuted for the achievable tuple**, but the charter's literal tuple (`task_class × model × provider × profile`) would trivially trigger the deal-killer as written, because `profile` (and `effort_tier`, `model_variant`) are write-path-dead columns that never split a key. The moment those dead dimensions are dropped — which they must be regardless of this spike, since they carry zero information — the remaining `(skill_name-as-task_class × model)` tuple clears N=5 for roughly half its keys and N=10 for a third, in both the full-history and a realistic 30-day rolling window. That is a real, non-trivial, currently-usable signal for a single-operator workload, not an inert one.

The caveat that keeps this from a clean "yes": `skill_name` populated rows are only 5–23% of total session volume and the capture path is ~7 weeks old. The rollup would need to either (a) accept that ~78–95% of sessions contribute to no keyed bucket at all (fine — a rollup over a subset of instrumented sessions is still a valid, if narrower, signal), or (b) wait for a different/better `task_class` derivation to broaden coverage. Task_class derivability itself (whether `skill_name` is the *right* choice, and whether it's router-joinable) is the tech leg's question, not this leg's — but this leg confirms that *whichever* field ends up chosen as `task_class`, only `skill_name` currently has enough non-blank rows to be worth aggregating over at all.

## 6. Confidence score + justification

**Confidence: 0.75.** High confidence in the empirical numbers themselves (real queries against the live 14,399-row cache, cross-checked with a full-history and a rolling-30-day cut that agree). Confidence held below 0.85 because: (a) this leg does not resolve whether `skill_name` is the task_class the router would actually want to join on (tech leg's job); (b) the young 7-week capture window for `skill_name` means the *trend* (rising density, per the month-by-month table) is favorable but not yet proven stable over multiple rolling windows; (c) sample sizes at the N=5–10 boundary (e.g., the `release|claude-opus-4-8|8` key) are individually thin enough that a single bad day could flip a key's threshold status, which is exactly the oscillation risk the risk leg needs to weigh.
