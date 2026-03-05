---
doc_type: report
status: active
category: data
title: "Session Signal Next Analysis + lm-assist Deep Dive Plan"
description: "Follow-up analysis roadmap after wiring new platform signals into CCDash ingestion and correlation."
author: codex
created: 2026-03-02
updated: 2026-03-02
tags: [sessions, forensics, analytics, correlation, claude-code, codex, lm-assist]
---

# Session Signal Next Analysis + lm-assist Deep Dive Plan (2026-03-02)

## Newly Wired Signals (Current State)

These are now ingested and available in CCDash session forensics:

- `resourceFootprint`: command-derived targets and scopes (`api`, `database`, `docker`, `ssh`, `service`) plus top targets and observations.
- `queuePressure`: queue operation mix, status mix, task type mix, distinct task count, and `waiting_for_task` signal.
- `subagentTopology`: Task tool fan-out metrics, linked subagent sessions, orphan links, and subagent transcript counts.
- `toolResultIntensity`: tool-result sidecar file counts/bytes/distribution and largest files.
- `platformTelemetry` (Claude): project-matched `.claude.json` metrics and MCP server inventory.
- `codexPayloadSignals` (Codex): payload and tool distributions from Codex event wrappers.

## What To Analyze Next

1. Resource Risk and Dependency Drift
- Add per-feature and per-session rollups for external targets.
- Detect new external endpoints or databases touched for first time in a feature.
- Value: catches risky integration drift and hidden dependency creep.

2. Queue Pressure vs Delivery Throughput
- Correlate queue pressure metrics with session duration, token burn, and completion outcomes.
- Flag patterns: high `waiting_for_task` + low completion + high retries.
- Value: identifies orchestration bottlenecks and wasted compute.

3. Subagent Effectiveness
- Track Task call count vs successful linked completions and artifact output.
- Compute subagent yield score per feature/phase.
- Value: improves multi-agent strategy and reduces unproductive fan-out.

4. Tool Result Quality Signals
- Add parsing/summarization on largest tool-result files (error traces, test summaries, command failures).
- Correlate heavy tool-result sessions with regressions and failed tasks.
- Value: exposes high-friction sessions and improves debugging workflows.

5. Platform Telemetry Operations View
- Surface MCP configuration drift by project and over time.
- Track platform usage counters vs team outcomes.
- Value: helps standardize environment reliability and onboarding.

## lm-assist Deep Dive: Recommended Scope

## Why It Is Worth It

Initial value is confirmed from `resource-extractor.ts` patterns and parser conventions:

- Strong resource extraction primitives that match CCDash needs.
- Useful normalization conventions for command/resource categorization.
- Cross-platform parsing ideas we can adapt without copying architecture wholesale.

A deeper dive is justified to accelerate extraction quality and reduce maintenance cost.

## Deep Dive Tracks

1. Extraction Primitive Audit
- Compare our regex and segmentation against `lm-assist` coverage for URLs, DB hosts, service targets, and command wrappers.
- Output: compatibility matrix + merged extraction spec.

2. Typed Signal Contract
- Convert current ad-hoc dictionaries into a versioned signal contract per platform.
- Output: JSON schema + validator + migration notes.

3. Adapter Boundary Design
- Keep platform-specific parsers thin and push shared extraction into reusable adapters.
- Output: `PlatformSignalAdapter` interface and shared utility package layout.

4. Benchmark and Quality Suite
- Build fixture corpus across Claude/Codex sessions with expected extraction outcomes.
- Output: precision/recall regression suite for signals.

## Proposed Implementation Sequence

1. Build fixture corpus and golden outputs for extraction behavior.
2. Run side-by-side extraction comparison with `lm-assist`-inspired rules.
3. Introduce shared extraction library behind existing parser outputs.
4. Add data quality metrics to CI (`missing_target_rate`, `unknown_category_rate`, dedupe ratio).
5. Roll out incremental UI correlation views using validated aggregates.

## Success Criteria

- >= 95% parser test pass on fixture corpus for resource and queue/subagent signals.
- <= 2% unknown-category resource observations for sampled production sessions.
- Measurable reduction in orphan Task links and unclassified queue operations.
- Cross-platform parity: same canonical categories available for Claude and Codex.
