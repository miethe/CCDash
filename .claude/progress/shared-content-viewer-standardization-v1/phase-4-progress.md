---
type: progress
schema_version: 2
doc_type: progress
prd: "shared-content-viewer-standardization-v1"
feature_slug: "shared-content-viewer-standardization-v1"
prd_ref: null
plan_ref: /docs/project_plans/implementation_plans/enhancements/shared-content-viewer-standardization-v1.md
phase: 4
title: "Optional explorer unification with packaged FileTree"
status: "completed"
started: "2026-03-19"
completed: "2026-03-19"
commit_refs:
  - "2d0eec6"
pr_refs: []

overall_progress: 100
completion_estimate: "completed"

total_tasks: 4
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["frontend-platform"]
contributors: ["ai-agents"]

tasks:
  - id: "TASK-4.1"
    description: "Validate whether packaged frontmatter support can be reused directly in CCDash document panes."
    status: "completed"
    assigned_to: ["frontend-platform"]
    dependencies: ["phase-3-complete"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "TASK-4.2"
    description: "Wire explicit document frontmatter metadata through UnifiedContentViewer and preserve frontmatter when body-only edits are saved."
    status: "completed"
    assigned_to: ["frontend-platform"]
    dependencies: ["TASK-4.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-4.3"
    description: "Replace the PlanCatalog custom folder explorer with packaged FileTree via a document-tree adapter."
    status: "completed"
    assigned_to: ["frontend-platform"]
    dependencies: ["TASK-4.1"]
    estimated_effort: "2pt"
    priority: "medium"

  - id: "TASK-4.4"
    description: "Add regression coverage for frontmatter rendering and document-tree adaptation, then run focused validation."
    status: "completed"
    assigned_to: ["frontend-platform"]
    dependencies: ["TASK-4.2", "TASK-4.3"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["TASK-4.1"]
  batch_2: ["TASK-4.2", "TASK-4.3"]
  batch_3: ["TASK-4.4"]
  critical_path: ["TASK-4.1", "TASK-4.2", "TASK-4.4"]
  estimated_total_time: "6pt / ~1 day"

blockers: []

success_criteria:
  - "Document-backed panes show parsed frontmatter even when CCDash stores only the markdown body in PlanDocument.content."
  - "Saving a plan document from CCDash preserves the existing YAML frontmatter block when the editor submits body-only markdown."
  - "PlanCatalog folder mode uses packaged FileTree without losing file selection behavior."
  - "Targeted frontend and backend regression coverage validates the new viewer and adapter paths."

files_modified:
  - "backend/routers/api.py"
  - "backend/tests/test_documents_router.py"
  - "components/DocumentModal.tsx"
  - "components/PlanCatalog.tsx"
  - "components/content/UnifiedContentViewer.tsx"
  - "components/content/__tests__/UnifiedContentViewer.test.tsx"
  - "lib/contentViewer.ts"
  - "lib/__tests__/contentViewer.test.ts"
  - "lib/documentFileTree.ts"
  - "lib/__tests__/documentFileTree.test.ts"
---

# shared-content-viewer-standardization-v1 - Phase 4

Packaged frontmatter rendering is available in `@miethe/ui`, but CCDash had to pass parsed document frontmatter explicitly because backend document parsing stores body content separately from the YAML block.
