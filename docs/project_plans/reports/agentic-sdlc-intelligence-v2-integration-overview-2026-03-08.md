---
doc_type: report
status: active
category: product
title: "Agentic SDLC Intelligence V2 Integration Overview"
description: "Plain-English overview of the current CCDash x SkillMeat integration, the target state after V2, and the value of SkillMeat-side follow-on requests."
author: codex
created: 2026-03-08
updated: 2026-03-08
tags: [agentic-sdlc, skillmeat, integration, report, overview]
related:
  - docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
  - docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
  - docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v2.md
  - .claude/worknotes/ccdash-integration/integration-audit.md
---

# Agentic SDLC Intelligence V2 Integration Overview

## Executive Summary

CCDash already has a real first-wave integration with SkillMeat. It can sync definitions, infer observed stacks from session behavior, score workflow effectiveness, and show recommended stacks in the execution workbench.

V2 is about turning that into a cleaner and more comprehensive cross-app integration. It aligns CCDash to SkillMeat's actual API and project model, improves authentication and connection setup, adds richer workflow/context/bundle awareness, and starts incorporating SkillMeat workflow execution state into CCDash's recommendation and analytics loop.

The end goal is for CCDash to act as the operational intelligence layer for agentic SDLC while SkillMeat remains the source of truth for reusable definitions and workflow structures.

## Current State

Today, CCDash already supports a meaningful SkillMeat integration.

It can:

1. connect to SkillMeat as a read-only source of definitions
2. sync artifacts, workflows, and context modules into CCDash
3. infer "stacks" from observed session behavior
4. score workflow effectiveness using real CCDash telemetry
5. show recommended stacks in the execution workbench
6. surface workflow-effectiveness and failure-pattern analytics

This means the foundational intelligence loop already exists. CCDash is not just linking out to SkillMeat; it is already using SkillMeat definitions as part of its reasoning model.

However, the current integration still has important limitations:

1. parts of the integration were built before the exact SkillMeat contract was fully audited
2. config and auth behavior are not yet fully aligned to real SkillMeat deployment modes
3. project mapping is not yet normalized to SkillMeat's actual project model
4. workflow matching is still more approximate than it should be
5. CCDash is not yet taking full advantage of workflow plans, bundles, context-pack previews, and workflow executions

In practical terms, the current system is useful, but it still behaves like a strong first pass rather than a polished, fully contract-aligned integration.

## State After V2

Once V2 is complete, CCDash should behave much more like a true cross-app intelligence layer sitting on top of SkillMeat.

### What V2 Will Enable

V2 will let CCDash:

1. connect cleanly to both local SkillMeat instances and AAA-enabled/protected instances
2. let users verify from Settings that:
   - the SkillMeat server is reachable
   - the configured SkillMeat project path is valid
   - the API key/credential is accepted when auth is enabled
3. understand SkillMeat's actual model of:
   - artifacts
   - workflows
   - context modules
   - bundles
   - workflow executions
4. determine which workflow is the effective workflow for a project instead of treating every matching workflow as equal
5. use SkillMeat workflow plans to understand real execution structure:
   - stages
   - gates
   - fan-out
   - dependencies
6. resolve context references more accurately so CCDash can understand not just which workflow exists, but which context modules and knowledge packs are behind it
7. use bundles as curated stack definitions so recommendations are less ad hoc and more aligned to reusable packaged patterns
8. incorporate SkillMeat workflow execution state so CCDash can reason about both static definitions and live/recent execution behavior
9. produce stronger stack recommendations based on:
   - real SkillMeat definitions
   - effective workflow selection
   - bundle alignment
   - context availability
   - execution awareness
   - CCDash's own historical delivery evidence

### The Practical Shift

The simplest way to describe the shift is:

**Today:** CCDash mostly says, "Based on what I observed in sessions, here is what seems to work."

**After V2:** CCDash says, "Based on what happened historically, what SkillMeat defines, what workflow is actually active for this project, what context is available, and what executions are happening now, here is the best stack to use next, and here is why."

That is a materially more complete operating loop.

### What This Means For Users

Today, a user may see:

1. a recommended stack inferred from prior sessions
2. links to some SkillMeat definitions
3. effectiveness metrics based mostly on CCDash's own observations

After V2, that same user should be able to:

1. configure SkillMeat confidently from Settings and immediately verify that the connection works
2. know whether auth is required and whether their credential is valid
3. know CCDash is using the correct SkillMeat project scope
4. get stack recommendations tied to actual SkillMeat workflows, bundles, and context modules
5. understand why a workflow is being recommended
6. see whether the workflow includes gates, fan-out stages, or approvals
7. see what context modules it depends on and how much context they provide
8. see recent SkillMeat executions related to that workflow
9. follow reliable deep links directly into the right SkillMeat pages

This makes the two apps feel much closer to a single coherent operating environment rather than two separate tools with partial overlap.

## Review of SkillMeat-Side Follow-On Requests

The V2 plan also identifies several SkillMeat-side follow-on requests. These are not required for CCDash V2, but they would improve the integration further.

## 1) Effective Workflow Endpoint

### What It Would Entail

SkillMeat would expose an endpoint that directly answers the question:

"What workflow should be considered effective for this project?"

Instead of CCDash fetching global workflows and project workflows separately and applying precedence logic itself, SkillMeat would return the already-resolved answer.

### What It Would Enable

1. simpler workflow-selection logic in CCDash
2. fewer client-side edge cases
3. more trustworthy workflow resolution
4. less duplicated business logic between the apps

## 2) Context-Module Deep-Link Route

### What It Would Entail

SkillMeat would add a dedicated UI route for individual context modules, or at least a stable route/query-param pattern that jumps directly to a specific module in the memory/context UI.

### What It Would Enable

1. direct navigation from CCDash into the exact context module being referenced
2. clearer explanation of why a context module appears in a recommendation
3. stronger trust in cross-app evidence because users can inspect the underlying source directly

## 3) Richer Bundle Composition Contract

### What It Would Entail

SkillMeat would expose bundle membership and composition more explicitly and more stably.

Bundles are a strong fit for CCDash because they represent curated, reusable combinations of artifacts. But CCDash needs a clear contract for what is inside a bundle in order to use it as a reliable stack definition.

### What It Would Enable

1. mapping observed stacks to curated bundle definitions
2. recommending named bundles instead of only inferred combinations
3. comparing "what users actually do" against "what the curated standard stack is"
4. better standardization of successful delivery patterns

## 4) Webhook/Event Support For Change Notifications

### What It Would Entail

SkillMeat would emit change notifications when artifacts, workflows, bundles, or context modules change.

Without this, CCDash has to poll for updates or rely on manual sync behavior.

### What It Would Enable

1. fresher cache state in CCDash
2. lower latency between SkillMeat changes and CCDash awareness
3. less wasteful sync behavior
4. better real-time coherence between the two apps

## 5) Workflow Execution Outcome Metadata Write-Back

### What It Would Entail

SkillMeat would support attaching structured outcome metadata to workflow execution records.

That means executions would carry richer delivery-oriented information beyond status and timestamps.

### What It Would Enable

1. tighter closed-loop evaluation of workflow performance
2. stronger cross-app correlation between "workflow ran" and "workflow actually succeeded in delivery terms"
3. richer analytics around execution quality, not just execution status
4. a path toward round-trip intelligence where CCDash measures outcomes and SkillMeat retains more of that quality signal on its own execution objects

## Overall Impact of the Follow-On Requests

If CCDash V2 is completed, the integration will already become much more contract-aligned, explainable, and useful.

If the SkillMeat-side follow-on requests also happen, the integration becomes more native and more maintainable:

1. less guesswork in workflow resolution
2. better deep-link fidelity
3. better support for curated reusable stacks
4. better real-time synchronization
5. tighter connection between execution state and measured delivery outcomes

The progression looks like this:

1. **Current state:** useful first integration
2. **After CCDash V2:** high-quality, contract-aligned, evidence-rich integration
3. **After SkillMeat follow-ons:** a much more first-class cross-app intelligence loop with cleaner contracts and stronger real-time fidelity

## Final Takeaway

The main value of V2 is not just "more integration." It is better integration quality.

It moves CCDash from:

1. partially contract-aligned
2. mostly observation-driven
3. loosely linked to SkillMeat

to:

1. contract-aligned with real SkillMeat behaviors
2. aware of effective workflows, curated bundles, and context availability
3. increasingly able to recommend the right next stack with concrete, inspectable evidence

That is what makes CCDash more useful as an operating intelligence layer for agentic SDLC rather than just a forensic dashboard.
