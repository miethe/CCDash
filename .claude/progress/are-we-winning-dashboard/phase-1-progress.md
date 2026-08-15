---
type: progress
schema_version: 2
doc_type: progress
prd: "are-we-winning-dashboard"
feature_slug: "are-we-winning-dashboard"
phase: 1
milestone: "M1"
title: "M1 — IntentTree lifecycle events are durable in CCDash"
status: not_started
created: 2026-08-14
updated: 2026-08-14
prd_ref: docs/project_plans/PRDs/features/are-we-winning-dashboard-v1.md
plan_ref: docs/project_plans/implementation_plans/features/are-we-winning-dashboard-v1.md
itt_node_id: node_01M009H6DGAKD5VCC8QCM0KP0K
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
commit_refs: []
pr_refs: []
depends_on: []
owners: ["opus-orchestrator"]
contributors: []
tasks:
  - id: "T1-001"
    title: "Config, dual-DDL event cache table, cursor-paginated fail-soft ingestion, scheduled job, tests"
    status: "pending"
    assigned_to: ["ica-executor"]
    routing: "ica / claude-sonnet-5[1m] (offload-eligible per plan routing_constraints)"
    dependencies: []
  - id: "T1-002"
    title: "AC validation gate (dual DDL parity, pagination, fail-soft)"
    status: "pending"
    assigned_to: ["codex-executor"]
    routing: "codex / gpt-5.6-terra (read-only)"
    dependencies: ["T1-001"]
---

# M1 — IntentTree lifecycle events are durable in CCDash

Milestone execution record. Acceptance criteria live in the implementation plan
(`docs/project_plans/implementation_plans/features/are-we-winning-dashboard-v1.md`);
deviations are logged to `.claude/worknotes/are-we-winning-dashboard/implementation-notes.md`.
