# Document Frontmatter Current Implementation Spec

Last updated: 2026-02-19
Status: Implemented

This spec describes what CCDash currently ingests, how fields are transformed, and where each normalized field is used in the app.

## 1. Ingestion Pipeline (Current)

1. Files are scanned from both roots:
   - `docs/project_plans/...`
   - `.claude/progress/...`
2. Parser normalizes frontmatter/path metadata into `PlanDocument` fields.
3. Repository persists typed columns to `documents` and extracted refs to `document_refs`.
4. Link rebuild creates:
   - `document -> feature`
   - `document -> document`
   - `document -> task`
   - `document -> session`
5. API serves paginated/filterable document lists and per-document links.

Primary code paths:

- `backend/parsers/documents.py`
- `backend/document_linking.py`
- `backend/db/repositories/documents.py`
- `backend/db/sync_engine.py`
- `backend/routers/api.py`

## 2. Current Runtime Document Object

Current app object (`PlanDocument`) includes:

```yaml
id: string
title: string
filePath: string
canonicalPath: string

status: string
statusNormalized: string
lastModified: string
author: string

docType: string
docSubtype: string
rootKind: project_plans|progress|document
category: string

hasFrontmatter: boolean
frontmatterType: string

featureSlugHint: string
featureSlugCanonical: string
prdRef: string
phaseToken: string
phaseNumber: number|null

overallProgress: number|null
totalTasks: number
completedTasks: number
inProgressTasks: number
blockedTasks: number

pathSegments: [string]
featureCandidates: [string]

frontmatter:
  tags: [string]
  linkedFeatures: [string]
  linkedSessions: [string]
  version: string|null
  commits: [string]
  prs: [string]
  relatedRefs: [string]
  pathRefs: [string]
  slugRefs: [string]
  prd: string
  prdRefs: [string]
  fieldKeys: [string]
  raw: object

metadata:
  phase: string
  phaseNumber: number|null
  overallProgress: number|null
  taskCounts:
    total: number
    completed: number
    inProgress: number
    blocked: number
  owners: [string]
  contributors: [string]
  requestLogIds: [string]
  commitRefs: [string]
  featureSlugHint: string
  canonicalPath: string

linkCounts:
  features: number
  tasks: number
  sessions: number
  documents: number

content: string|null
```

## 3. Current Type and Subtype Classification

## 3.1 `docType`

Path/frontmatter-derived values:

- `progress`
- `prd`
- `implementation_plan`
- `phase_plan`
- `report`
- `spec`
- `document` (fallback)

## 3.2 `docSubtype`

Values currently produced:

- `implementation_plan`
- `phase_plan`
- `prd`
- `report`
- `spec`
- `design_spec`
- `design_doc`
- `spike`
- `idea`
- `bug_doc`
- `progress_phase`
- `progress_all_phases`
- `progress_quick_feature`
- `progress_other`
- `document`

## 4. Current Frontmatter Extraction Keys

These key families are currently harvested into normalized refs.

```yaml
related_keys:
  - related
  - related_documents
  - related_specs
  - related_prd
  - parent_prd
  - related_request_logs
  - references
  - reference
  - links
  - plan_ref
  - prd_link
  - source_document
  - linked_docs
  - linkeddocs
  - source_docs
  - sources
  - artifacts

prd_keys:
  - prd
  - prd_reference
  - prdreference
  - prd_ref
  - prdref
  - related_prd
  - parent_prd
  - prd_link

session_keys:
  - session
  - session_id
  - sessionid
  - sessions
  - linked_sessions
  - linkedsessions

request_keys:
  - request_log
  - request_log_id
  - source_req
  - source_request
  - related_request_logs

commit_keys:
  - commit
  - commits
  - git_commit
  - git_commits
  - git_commit_hashes
  - git_commit_hash
  - commit_refs
  - commithash

file_keys:
  - files
  - files_modified
  - files_affected
  - files_created
  - context_files
  - source_document
  - plan_ref
  - file
  - file_path

owner_keys:
  - owner
  - owners
  - assigned_to
  - contributors
  - maintainers

feature_keys:
  - feature
  - feature_slug
  - feature_ref
  - feature_id
  - feature_slug_hint
  - linked_features
  - linkedfeatures
```

## 5. Current Normalization Mapping (Field -> Target -> Usage)

## 5.1 Core metadata mapping

| Source | Target field(s) | Transform | Used in app |
| --- | --- | --- | --- |
| `title` or filename stem | `title` | fallback title-case stem | cards/list/modal title |
| `status` | `status`, `statusNormalized` | canonical enum normalization (`draft -> pending`, `done -> completed`, `inferred complete -> inferred_complete`, etc.) | filters, badges |
| `author` or `audience[0]` | `author` | first audience entry wins | modal/list metadata |
| file path | `canonicalPath`, `id` | project-relative canonical path + `DOC-` id | identity/deep-linking |
| `doc_type`/`doctype` + path | `docType` | explicit override else path classification | scopes/filters |
| path + `type` | `docSubtype`, `rootKind` | subtype logic (`progress_phase`, etc.) | scope tabs, filters |
| `category` or path segment | `category` | explicit else inferred | filters |

Status canonical set:

- `pending`
- `in_progress`
- `review`
- `completed`
- `deferred`
- `blocked`
- `archived`
- `inferred_complete`

Subtype canonical set:

- `implementation_plan`
- `phase_plan`
- `prd`
- `report`
- `spec`
- `design_spec`
- `design_doc`
- `spike`
- `idea`
- `bug_doc`
- `progress_phase`
- `progress_all_phases`
- `progress_quick_feature`
- `progress_other`
- `document`

## 5.2 Relationship extraction mapping

| Source fields | Target | Transform | Usage |
| --- | --- | --- | --- |
| related keys | `frontmatter.relatedRefs` | flatten + dedupe | search, doc-doc linking |
| path-like refs | `frontmatter.pathRefs` | path normalization | doc-doc linking |
| slug-like refs | `frontmatter.slugRefs` | token extraction | feature inference/search |
| feature keys + inferred path slug | `frontmatter.linkedFeatures`, `featureCandidates`, `featureSlugHint` | feature token validation + canonicalization | feature filters + doc-feature linking |
| session keys | `frontmatter.linkedSessions` | string/list flatten | doc-session linking |
| prd keys | `prdRef`, `frontmatter.prd`, `frontmatter.prdRefs` | primary + list | filters + feature matching |
| request keys | `metadata.requestLogIds` | flatten + dedupe | search |
| commit keys | `frontmatter.commits`, `metadata.commitRefs` | flatten + combine direct/parsed refs | search/modal |
| owner keys | `metadata.owners`, `metadata.contributors` | merge/dedupe | modal metadata |

## 5.3 Progress/task counter mapping

| Source | Target | Transform | Usage |
| --- | --- | --- | --- |
| `phase`, `phase_id`, `phase_token`, filename regex | `phaseToken`, `phaseNumber`, `metadata.phase` | numeric parse fallback from filename | phase filter/modal |
| `overall_progress` or `progress` | `overallProgress`, `metadata.overallProgress` | numeric parse supports `%` string | modal metrics |
| `total_tasks`, `completed_tasks`, `deferred_tasks`, `in_progress_tasks`, `blocked_tasks` | task counters | numeric parse | progress metrics |
| `tasks[]` list | task counters | derive counts when explicit counters absent | progress metrics |

## 6. Current Per-Doc-Type Frontmatter Specs

These are not strict validators; they represent currently recognized fields and mapping behavior.

## 6.1 PRD (current recognized)

```yaml
doc_type: prd            # or inferred from path
status: draft|active|in-progress|completed|blocked|archived
category: ""

title: ""
author: ""
audience: []
created: ""
updated: ""

tags: []
feature_slug: ""
linked_features: []
prd: ""                 # self or related prd ref
related: []
related_documents: []
plan_ref: ""
linked_sessions: []

request_log_id: ""
request_log: ""
commits: []
prs: []

owner: ""
owners: []
contributors: []
```

## 6.2 Implementation Plan (current recognized)

```yaml
doc_type: implementation_plan   # often inferred from path
status: draft|active|in-progress|completed|blocked|archived
category: ""

title: ""
author: ""
audience: []
created: ""
updated: ""

tags: []
feature_slug: ""
linked_features: []
prd: ""
prd_ref: ""
related: []
related_documents: []
plan_ref: ""
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: ""
owners: []
contributors: []
```

## 6.3 Phase Plan (current recognized)

```yaml
doc_type: phase_plan            # typically inferred by filename/path
status: draft|active|in-progress|completed|blocked|archived
category: ""

phase: "1"                     # optional; filename fallback exists
phase_id: ""
phase_token: ""

title: ""
feature_slug: ""
linked_features: []
prd: ""
related: []
plan_ref: ""
linked_sessions: []

commits: []
request_log_id: ""
```

## 6.4 Report (current recognized)

```yaml
doc_type: report                # often inferred from reports/ path
status: draft|active|in-progress|completed|blocked|archived
category: ""

title: ""
feature_slug: ""
linked_features: []
prd: ""
related: []
related_documents: []
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: ""
contributors: []
```

## 6.5 Progress Phase (current recognized)

```yaml
doc_type: progress              # inferred from .claude/progress path
status: pending|in-progress|completed|deferred|blocked|review|active
category: ""

title: ""
phase: 1
phase_id: ""
phase_token: ""
progress: 0                     # or overall_progress
overall_progress: 0

total_tasks: 0
completed_tasks: 0
deferred_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0

tasks:
  - id: ""
    title: ""
    status: pending|in-progress|completed|deferred|blocked|review
    assigned_to: []
    session_id: ""
    git_commit: ""
    dependencies: []
    deliverables: []

feature_slug: ""               # optional; often inferred from path
linked_features: []
prd: ""
plan_ref: ""
linked_sessions: []

request_log_id: ""
commits: []
files_modified: []
context_files: []
owner: ""
contributors: []
```

## 6.6 Progress All-Phases / Quick-Feature / Other (current recognized)

```yaml
doc_type: progress
# doc_subtype inferred by filename/parent dir:
# - progress_all_phases ("all-phases" in filename)
# - progress_quick_feature (quick-features parent or type)
# - progress_other (fallback)

status: pending|in-progress|completed|deferred|blocked|review|active
title: ""
progress: 0
overall_progress: 0

total_tasks: 0
completed_tasks: 0
deferred_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0

tasks: []
linked_features: []
linked_sessions: []
prd: ""
related: []
commits: []
request_log_id: ""
```

## 7. Current Linking Logic and Confidence

Document link strategies used during rebuild:

```yaml
document_to_feature:
  explicit_frontmatter_ref:
    confidence: 0.98
    inputs: [linkedFeatures, featureRefs, prd]
  path_feature_hint:
    confidence: 0.74
    inputs: [feature_slug_hint, feature_slug_canonical, feature_slug_from_path]
  referenced_document_inheritance:
    confidence: 0.64
    condition: "only when doc has no direct feature links"

document_to_document:
  document_ref_path:
    confidence: 0.90
    inputs: [pathRefs, fileRefs]

document_to_task:
  progress_source_task:
    confidence: 1.0
    condition: "task.source_file matches document file_path"

document_to_session:
  task_session_ref:
    confidence: 0.96
    source: "session_id on linked tasks"
  explicit_session_ref:
    confidence: 1.0
    source: [sessionRefs, linkedSessions]
```

## 8. Current API/Filter Usage

`GET /api/documents` supports:

- `q`, `doc_subtype`, `root_kind`, `doc_type`, `category`, `status`, `feature`, `prd`, `phase`, `include_progress`, `offset`, `limit`

Filter behavior:

- `include_progress=false` excludes `root_kind='progress'`
- `feature` matches `feature_slug_*` and `document_refs` feature/prd refs
- `q` searches typed columns + json payloads + `document_refs`

Supporting endpoints:

- `GET /api/documents/catalog` returns facet counts from DB
- `GET /api/documents/{doc_id}/links` returns linked features/tasks/sessions/docs

## 9. Current UI Utilization

- `/plans` uses scope tabs + faceted filters + metadata-aware search.
- Document modal shows typed metadata, progress counters, owners/contributors, request IDs/commits, and linked entities.
- Feature board resolves linked docs by ID, canonical path, then normalized file path fallback.

## 10. Feature Completion Equivalence

Feature completion inference treats these document collections as equivalent:

- PRD completion
- Plan completion (implementation plan, or all phase-plan docs when phase plans are present)
- Completion across all linked progress phase docs

If any equivalent collection is complete, the feature status is treated as `done` even when other linked docs are stale.

When this inference occurs, CCDash writes through `status: inferred_complete` to linked PRD/Plan docs that are not already completion-equivalent.

## 11. Known Current Gaps

- No strict frontmatter schema validation/linting at ingest time.
- No standalone `RequestLog` entity table (request IDs are indexed strings only).
- Long-tail metadata remains in `frontmatter.raw` / `metadata_json` and is not fully first-class in UI facets.
