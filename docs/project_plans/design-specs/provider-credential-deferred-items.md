---
title: "Design Spec: Provider/Channel/Credential — deferred items and their dispositions"
doc_type: design-spec
maturity: shaping
feature_slug: provider-channel-credential-entities
prd_ref: docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/provider-channel-credential-entities-v1.md
status: draft
created: 2026-08-10
updated: 2026-08-10
audience: developers
category: deferred-scope
tags:
  - ccdash
  - provider-entities
  - credentials
  - deferred-scope
related_documents:
  - docs/project_plans/PRDs/enhancements/provider-channel-credential-entities-v1.md
  - docs/project_plans/implementation_plans/enhancements/provider-channel-credential-entities-v1.md
  - docs/project_plans/adrs/adr-019-provider-correlation-home-ccdash.md
description: |
  The six items the provider-channel-credential-entities-v1 plan deliberately deferred,
  each with its disposition, the reason it was NOT built in v1, and what would have to
  become true for it to be picked up. Authored at M3 per the plan's "Deferred items"
  table so the deferrals are a record rather than an omission.
---

# Deferred items — provider/channel/credential entities v1

v1 shipped the dimension tables, a declared-lineage credential entity, an idempotent
backfill, and a cross-project per-credential rollup. The following were **named and
deliberately excluded**, not overlooked. Each is recorded here with the condition that
would change the decision.

## 1. Budgets / remaining-headroom per credential

**Disposition:** follow-on feature. **Source:** PRD §7.

The rollup answers "what has this credential spent". It does not answer "how much is
left", which needs a budget value per credential and a policy for what happens at the
threshold. Neither exists anywhere in the system today, and inventing a budget number
would be fabricating an authority CCDash does not have — the real ceilings live with the
provider, not with us.

**Condition to pick up:** a source of truth for per-credential budget appears (operator
config or a provider API). The schema already accommodates it — the addition is a column
plus a rollup field, not a redesign.

## 2. Provider reliability records (429 rates, failure modes over time)

**Disposition:** needs a capture path first; separate PRD. **Source:** PRD §7.

There is no capture path for provider-side failures today. Sessions record what happened
locally, not what the provider returned when it refused. Building a reliability surface
on top of data that is not captured would produce a chart of zeros that reads as "no
failures" rather than "no data" — the failure mode this feature's rubric exists to avoid.

**Condition to pick up:** a capture path for provider error responses ships. That is its
own PRD, not a milestone here.

## 3. Subscription-seat and API-key capture paths

**Disposition:** schema accommodates; capture is out of scope. **Source:** PRD §8.

`provider_credentials` is keyed `(channel, credential_name)` and is deliberately NOT
ICA-specific, precisely so a subscription seat or a named API key is representable. What
is missing is the capture side: nothing writes those rows today because nothing observes
seat or API-key identity at launch time.

**Condition to pick up:** launch-time capture is extended to emit a credential name for
non-ICA channels. No schema change required — that was the point of the key design.

## 4. Inference-assisted rotation suggestion

**Disposition:** REJECTED for v1; rationale recorded only. **Source:** plan Decision 1.

Rotation lineage is **declared, never inferred**. A suggestion feature would reintroduce
the failure it was designed against: a wrong inferred merge asserts a continuity that
never happened, and it is invisible in the output — the series simply looks continuous.
The operator cost of declaring is one action per rotation, and rotations are rare.

**Condition to reconsider:** a suggestion surface that never writes lineage itself and
always requires an explicit confirming action could be revisited. Anything that merges
without a stored, human-originated pointer should not be.

## 5. Staged-rollout feature flag for the rollup

**Disposition:** not needed; revisit if the read proves costly. **Source:** PRD §8.

The rollup is a read behind `@memoized_query` with the same cross-project fan-out shape
as `system_metrics`. Adding a flag would add a config surface and a second code path to
test for no measured benefit. This project already carries flags whose only remaining
function is to be documented.

**Condition to pick up:** the read shows up as a cost in practice (slow fan-out on the
node's project count, or cache pressure). Then flag it — with the measurement that
motivated it.

## 6. Live-traffic demonstration of AC3

**Disposition:** BLOCKED on an external prerequisite. **Source:** PRD §8/§9.

AC3 (cumulative and periodic per-credential spend across projects, surviving rotation)
is evidenced against a **seeded fixture**, not live data, and that is a real limitation
rather than a testing shortcut. `sessions.ica_key` is NULL on essentially every real row
today because launcher activation for the ICA key name is unshipped
(`node_01KZP4D3BN6QYJAHC4FCRNGZNW`). A live series cannot be demonstrated because there
is no live series yet.

**Condition to pick up:** launcher activation ships and `ica_key` starts populating. At
that point the backfill (already idempotent) can be re-run and AC3 re-evidenced against
real rows. Nothing in this feature needs to change for that to work — but until then, do
not report AC3 as demonstrated on production data.

---

## What was NOT deferred, for contrast

Two things were considered deferrable during execution and deliberately were **not**:

- **The Postgres repository.** The backfill was initially SQLite-only. Since the node's
  Postgres is the operative database, that would have shipped three tables that exist and
  never populate. Built in v1.
- **Broadening the secret guard beyond `credential_name`.** A reviewer lens rated the gap
  acceptable because no caller wrote the other fields yet; that ceased to be true the same
  day, once the backfill began writing them. Closed in v1.
