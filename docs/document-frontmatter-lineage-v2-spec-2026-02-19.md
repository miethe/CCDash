# Document Frontmatter Lineage v2 Spec

Last updated: 2026-02-19
Status: Proposed (recommended for all expansion/iteration features)

## 1. Goal

Provide first-class lineage metadata so a feature can be tracked separately while remaining explicitly connected to its predecessor/successor chain.

## 2. New Lineage Fields

Use these in PRDs, implementation plans, phase plans, and progress docs:

```yaml
lineage_family: ""      # versionless family slug (e.g. composite-artifact)
lineage_parent: ""      # parent feature slug or path (e.g. composite-artifact-infrastructure-v1)
lineage_children: []    # optional child feature slugs
lineage_type: ""        # expansion|iteration|supersedes|followup|spike
```

Compatibility aliases that map to the same intent:

- `feature_family` -> `lineage_family`
- `parent_feature`, `parent_feature_slug`, `extends_feature`, `derived_from`, `supersedes` -> `lineage_parent`
- `child_features`, `superseded_by` -> `lineage_children`

## 3. Validation Rules

- `lineage_family` should be versionless kebab-case.
- `lineage_parent` and `lineage_children[]` should reference feature slugs (or paths that resolve to slugs).
- `lineage_type` should be one of the approved values above.
- Lineage references must not change document ownership; ownership is still path/feature-slug based.

## 4. Example (Composite Artifact UX v2)

```yaml
doc_type: implementation_plan
feature_slug: composite-artifact-ux-v2
feature_version: v2
feature_family: composite-artifact

lineage_family: composite-artifact
lineage_parent: composite-artifact-infrastructure-v1
lineage_type: expansion
lineage_children: []

prd_ref: /docs/project_plans/PRDs/features/composite-artifact-ux-v2.md
plan_ref: /docs/project_plans/implementation_plans/features/composite-artifact-ux-v2.md
```

## 5. CCDash Utilization

When these fields are present, CCDash should:

1. Index lineage refs in `document_refs` for search/filter.
2. Expose lineage fields in `PlanDocument.frontmatter`.
3. Use lineage refs to enrich `Feature.relatedFeatures`.
4. Preserve completion write-through safety via ownership guards.
