---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: research_prd
status: approved
category: data-platform
title: "PRD: Session Intelligence & Canonical Storage Modernization"
description: "Evolve CCDash PostgreSQL from a read-cache to a canonical storage layer to enable DX sentiment analysis, thrashing detection, scope drift quantification, and automated SkillMeat memory capture."
summary: "Pivots session storage to unlock full-stream conversational analytics, semantic search, and bi-directional intelligence loops for Agentic SDLC workflows."
created: 2026-03-23
updated: 2026-04-01
priority: high
risk_level: medium
complexity: High
track: Data
feature_slug: session-intelligence-canonical-storage-v1
feature_family: ccdash-data-platform
feature_version: v1
owner: data-platform
---

# PRD: Session Intelligence & Canonical Storage Modernization

## 1. Executive Summary
To scale this Agentic SDLC offering across a broader consulting practice, CCDash must transition from observing agent *activity* to measuring agent *friction and effectiveness*. Currently, `.jsonl` session streams are parsed into a relational read-cache, leaving rich conversational text, implicit struggle signals, and architectural decisions trapped in opaque files. 

This initiative elevates PostgreSQL to the canonical storage layer for session histories. By normalizing full conversation streams, we unlock semantic search (`pgvector`), Developer Experience (DX) sentiment tracking, code-churn diagnostics, plan-to-execution drift analysis, and the automated capture of organizational memory back into SkillMeat.

## 2. Problem Statement
* **Opaque Conversational Data:** While metadata (tools, files, tokens) is structured, the actual developer-agent dialogue is unqueryable, preventing qualitative analysis of the Agent Experience (AX).
* **Missing Friction Metrics:** Effectiveness is currently judged by explicit failures or success. We lack implicit failure metrics, such as agents repeatedly modifying the same lines of code without making progress (thrashing).
* **Unquantified Scope Drift:** We cannot currently measure when an autonomous agent operates outside its authorized blast radius defined in the implementation plans.
* **One-Way Intelligence:** CCDash consumes context from SkillMeat but relies on human intervention to write newly discovered patterns or workarounds back to the artifact registry.

## 3. Core Capabilities & Enhancements

### 3.1. Full-Stream Ingestion & Semantic Search (`pgvector`)
* **Behavior:** Normalize all session messages (human and agent) into a queryable `session_messages` table. 
* **Vectorization:** Generate embeddings for user queries, agent architectural decisions, and successful tool outputs.
* **Value:** Allows developers and operators to perform semantic searches across the entire historical session database (e.g., *"Show me all sessions where we resolved Auth0 JWT validation errors"*).

### 3.2. Developer Experience (DX) Sentiment Analysis
* **Behavior:** Run lightweight NLP sentiment scoring on user prompts stored in the `session_messages` table.
* **Metric:** Generate a "DX Score" or "CSAT" index per feature or workflow.
* **Trigger:** Flag sessions containing high frustration markers combined with high token burn for immediate review.

### 3.3. Thrashing & Code Churn Detection
* **Behavior:** Analyze line-level or function-level git diffs and file-state deltas between consecutive tool executions. 
* **Metric - Churn-to-Progress Ratio:** Measure the frequency of an agent rewriting the same code block across 3+ consecutive turns. 
* **Action:** Automatically degrade the "Efficiency" score of workflows that exhibit high thrashing, indicating missing context or hallucination loops.

### 3.4. Plan vs. Execution Drift (Scope Adherence)
* **Behavior:** Extract the anticipated "blast radius" (files, modules, domains) from linked `PlanDocuments`. Cross-reference this baseline against the actual `session_file_updates` and `resourceFootprint`.
* **Metric - Scope Adherence Score:** Flag sessions where execution strays significantly from the documented plan.
* **Action:** Provide visual drift indicators in the Session Inspector and Feature Workbench to flag autonomous sessions that may have gone rogue.

### 3.5. Automated Memory Capture (SAM)
* **Behavior:** Introduce a background reconciliation worker that scans highly successful sessions (high DX Score, low thrashing, merged PR).
* **Action:** Automatically extract the exact constraints, prompt structures, or undocumented dependencies that led to success.
* **Bi-Directional Integration:** Draft these extractions as new "Context Modules" or "Artifact Guidelines" and push them to SkillMeat via API, closing the loop so all future agents instantly inherit the knowledge.

## 4. Architecture & Data Model Adjustments

### 4.1 Schema Additions
* **`session_messages`:** Normalized table for individual turn contents, roles, timestamps, and sentiment scores.
* **`session_embeddings`:** `pgvector` enabled table linking message or block IDs to their vector representations.
* **`session_code_churn`:** Fact table tracking repeated edits to identical file paths/line ranges within the same session.

### 4.2 API Contract Updates
* **SkillMeat Client:** Upgrade from read-only to support `POST /api/v1/context-modules` for automated SAM drafts.
* **Analytics Router:** Add endpoints for `GET /api/analytics/dx-sentiment` and `GET /api/analytics/scope-drift`.

## 5. Rollout Strategy & Mitigation

1. **Phase 1: Canonical Data Foundation.** Implement `session_messages` parsing, `pgvector` setup, and backfill existing `.jsonl` histories into the new schema.
2. **Phase 2: Friction & Drift Analytics.** Implement the Churn-to-Progress and Scope Adherence calculations based on existing `session_file_updates` and `document_linking` data.
3. **Phase 3: Sentiment & Semantic Search.** Introduce the NLP scoring and UI search surfaces.
4. **Phase 4: SkillMeat Write-Back.** Enable the SAM background worker to draft and push Context Modules (requires an approval-gate UI in CCDash before publishing to SkillMeat).

## 6. Success Metrics
* **Query Latency:** Sub-100ms response times for deep conversational history searches.
* **AX Visibility:** >80% of active sessions successfully generating a DX Sentiment Score.
* **Intelligence Loop:** Generation of at least 1 actionable SkillMeat Context Module draft per successfully delivered Feature.
