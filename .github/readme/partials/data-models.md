---

## Data Models

### Feature
The primary unit of delivery. Aggregates linked documents (PRDs, implementation plans, reports), implementation phases with granular tasks, and related feature variants. Includes rollup metadata for priority, risk, complexity, and execution readiness.

### AgentSession
The atomic unit of work. Contains the conversation/tool execution stream, impact history, updated files, linked artifacts (skills, commands, agents, hooks, test runs), and structured forensic payloads including queue pressure, resource footprint, and subagent topology.

### ProjectTask
A specific unit of implementation with status mapping (pending, in-progress, review, completed, deferred) and estimated effort cost.

### PlanDocument
Markdown documentation with typed identity/classification metadata, canonical delivery fields, and normalized linking for features, related docs, commits, and PRs.
