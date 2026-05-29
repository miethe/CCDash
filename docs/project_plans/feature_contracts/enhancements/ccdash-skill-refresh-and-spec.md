---
title: "Feature Contract: CCDash Skill Refresh and SPEC.md Authorship"
schema_version: 2
doc_type: feature_contract
status: draft
created: 2026-05-29
updated: 2026-05-29
feature_slug: "ccdash-skill-refresh-and-spec"
category: "enhancements"
estimated_points: 4
tier: 1
owner: null
priority: medium
risk_level: low
changelog_required: false
related_documents:
  - "docs/project_plans/feature_contracts/features/ccdash-cli-project-init.md"
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected:
  - "/Users/miethe/dev/homelab/development/MeatySkills/skills/ccdash/SPEC.md"
  - "/Users/miethe/dev/homelab/development/MeatySkills/skills/ccdash/SKILL.md"
  - "/Users/miethe/dev/homelab/development/MeatySkills/skills/ccdash/scripts/router-table.json"
  - "/Users/miethe/dev/homelab/development/MeatySkills/skills/ccdash/CHANGELOG.md"
---

# Feature Contract: CCDash Skill Refresh and SPEC.md Authorship

## EXECUTOR NOTICE — SYMLINK ALERT

The ccdash skill is symlinked. The `.claude/skills/ccdash/` path in the CCDash repo is a symlink into the MeatySkills monorepo. All edits in this contract target the **real** files at:

```
/Users/miethe/dev/homelab/development/MeatySkills/skills/ccdash/
```

Do NOT edit the CCDash repo itself. No app code changes are in scope. Verify the symlink target with `readlink .claude/skills/ccdash` before writing any file.

---

## 1. Goal

Bring the `ccdash` skill fully current with the shipped CCDash app surface (as of 2026-05-20), add the missing `SPEC.md` following the SkillMeat skill-spec convention, and purge phantom in-repo command references from `router-table.json` so agents route only to surfaces that actually exist.

---

## 2. User / Actor

- **Primary user**: Agents and operators invoking the `ccdash` skill for project-intelligence routing; they trust the skill's routing table to reflect real, callable surfaces.
- **Secondary users**: Skill maintainers who need a durable, machine-readable capability contract (`SPEC.md`) to know what the skill covers and detect future drift.

---

## 3. Job To Be Done

When an agent uses the ccdash skill to route a query, it wants accurate, current tool/command mappings so it routes to surfaces that actually exist — and doesn't reference phantom commands or miss 3 shipped MCP tools that have no routing entries today.

---

## 4. Scope

### In Scope

- **Author `SPEC.md`** at the ccdash skill root, following the structural convention modeled in `MeatySkills/skills/release/SPEC.md`: frontmatter (`schema_version 2`, `doc_type: skill_spec`, required fields), Purpose & Scope, Capability Matrix, Invariants & Constraints, Enhancement Backlog, Changelog.
- **Update `SKILL.md` Confidence Anchor**: add the 3 missing MCP tools (`artifact_recommendations`, `ccdash_live_active_count`, `ccdash_system_active_count`); bump `app_version` to `2026-05-20`; bump `version` and `updated` fields; add in-repo CLI command groups `artifact`, `live`, `system`.
- **Update `scripts/router-table.json`**: add intent entries for `artifact`, `live`, and `system` query surfaces; remove or correct phantom in-repo entries (`feature list`, `feature show`, `feature sessions`, `feature documents` — these live only in the standalone CLI); ensure every entry carries a `transport` array tag (`mcp`, `in-repo-cli`, `standalone-cli`).
- **Update `CHANGELOG.md`**: append a dated entry for the 2026-05-29 refresh covering all changes made.
- **Light-touch reference doc review**: fix any factual drift (wrong tool names, missing command groups) in the `references/` docs only where they assert tool/command surface that is now wrong. Do not rewrite docs where the substance is still correct.

### Out of Scope

- Any change to the CCDash application itself (no new MCP tools, CLI commands, or backend routes).
- The `ccdash-cli-project-init` work (sibling contract) — if that feature ships before this refresh, the executor should add the new `ccdash project` commands to the capability matrix as an addendum, then cross-reference the sibling contract in `SPEC.md`. Otherwise, note the gap in the Enhancement Backlog.
- Wholesale rewrite of any of the 11+ reference docs — fix only demonstrably wrong surface assertions.
- Adding new routing capabilities beyond what is already shipped.

---

## 5. UX / Behavior Requirements

These are authoring behavior requirements (the "user" is an agent reading the skill):

- An agent reading `SKILL.md` sees exactly 7 MCP tools listed in the Confidence Anchor, matching all tools registered in `backend/mcp/tools/__init__.py`.
- An agent reading `router-table.json` sees no entry whose `transport` includes `in-repo-cli` for a command that does not exist in `backend/cli/main.py`.
- Every intent entry in `router-table.json` carries a `transport` array; no entry is missing this field.
- An agent reading `SPEC.md` can determine the full transport-to-capability mapping from the Capability Matrix alone, without cross-reading `SKILL.md`.
- The `SPEC.md` Capability Matrix enumerates all 7 MCP tools, all in-repo CLI command groups, and all standalone CLI command groups with their transport tags.
- The `SPEC.md` Invariants section includes: "router-table.json is the routing source of truth; update it whenever the query surface changes" and "Keep aligned with shipped runtime — skill claims must not outpace or lag the app by more than one shipped version."

---

## 6. Data Requirements

- **Entities affected**: Skill artifact files only (no database or app schema impact).
- **New files**: `SPEC.md` at `MeatySkills/skills/ccdash/SPEC.md`.
- **Modified files**:
  - `SKILL.md`: frontmatter version fields, Confidence Anchor section.
  - `scripts/router-table.json`: `app_version`, `skill_version`, `updated`; new intent entries; corrected transport tags on existing entries; removal of phantom in-repo entries.
  - `CHANGELOG.md`: new dated entry appended.
  - Up to 3-4 `references/` files where surface claims are factually wrong (surface-only fixes, not prose rewrites).
- **State changes**: None beyond file contents.
- **Storage implications**: None.

---

## 7. API / Integration Requirements

**No new or modified API endpoints.** This is a documentation-only contract.

**Runtime truth sources** (read-only, used for verification):

| Source | Purpose |
|--------|---------|
| `backend/mcp/tools/__init__.py` -> `register_tools()` | Canonical list of all 7 registered MCP tool names |
| `backend/cli/main.py` -> `add_typer()` calls | Canonical list of in-repo CLI command groups: `status`, `feature`, `workflow`, `report`, `artifact`, `live`, `system` |
| `packages/ccdash_cli/` | Standalone CLI command groups: all in-repo groups + `session`, `target`, `doctor`, `diagnostics`, `version` |
| `MeatySkills/skills/release/SPEC.md` | Structural exemplar for `SPEC.md` authorship |

**Internal service dependencies**: None beyond reading the above files for verification.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `MeatySkills/skills/release/SPEC.md` — structural exemplar. Mirror its frontmatter schema, section names, and Capability Matrix table shape exactly.
- `MeatySkills/skills/ccdash/CHANGELOG.md` — append-only; prepend new dated entry at top.
- `MeatySkills/skills/ccdash/scripts/router-table.json` — preserve existing schema (`$schema_version`, top-level metadata fields, `intents` array with consistent per-entry fields).

**Must not change** (protected areas):
- CCDash application code (`backend/`, `packages/`, `components/`, etc.).
- The ccdash skill's recipe files (`.../recipes/`) — these document multi-step flows and are not surface-assertion docs.
- The `_meta/` directory — skill authoring guide; out of scope.
- Any SkillMeat skill other than `ccdash`.

**New dependencies:**
- Allowed? **No.** This is a documentation refresh; no new libraries, tools, or external dependencies are introduced.

---

## 9. Acceptance Criteria

**SPEC.md**
- [ ] `SPEC.md` exists at `MeatySkills/skills/ccdash/SPEC.md` with required frontmatter: `schema_version: 2`, `doc_type: skill_spec`, `skill_name: ccdash`, `skill_version`, `status`, `created`, `updated`, `source_docs` (pointing to authoritative app paths), `related_skills`, `affects_commands`.
- [ ] `SPEC.md` contains all required sections: Purpose & Scope, Capability Coverage (matrix), Invariants & Constraints, Enhancement Backlog, Changelog — matching the structural shape of `release/SPEC.md`.
- [ ] The Capability Matrix in `SPEC.md` enumerates all 7 currently registered MCP tools: `ccdash_project_status`, `ccdash_feature_forensics`, `ccdash_workflow_failure_patterns`, `ccdash_generate_aar`, `artifact_recommendations`, `ccdash_live_active_count`, `ccdash_system_active_count`.
- [ ] The Capability Matrix enumerates all 7 in-repo CLI command groups: `status`, `feature`, `workflow`, `report`, `artifact`, `live`, `system`, each with their known subcommands.
- [ ] The Capability Matrix enumerates standalone CLI groups with transport tag `standalone-cli` (minimum: `session`, `target`, `doctor`, `diagnostics`, `version`).
- [ ] Every row in the Capability Matrix carries a transport designation (`mcp`, `in-repo-cli`, `standalone-cli`, or a multi-value combination).

**SKILL.md**
- [ ] The Confidence Anchor in `SKILL.md` lists all 7 MCP tools (no omissions, no phantom tools).
- [ ] The Confidence Anchor lists all 7 in-repo CLI command groups with at least one representative subcommand each.
- [ ] `app_version` is bumped to `2026-05-20` (or the actual verified shipped date if different), `version` is incremented, and `updated` reflects the edit date.

**router-table.json**
- [ ] `router-table.json` contains NO intent entry with `transport` including `in-repo-cli` for `feature list`, `feature show`, `feature sessions`, or `feature documents` — these commands exist only in the standalone CLI and must be tagged `standalone-cli` only (or removed if superseded by existing entries).
- [ ] New intent entries exist for the `artifact` (rankings, recommendations), `live` (active-count), and `system` (active-count) surfaces, each with correct transport tags.
- [ ] Every intent entry in the `intents` array carries a `transport` field (no missing-transport entries introduced or left).
- [ ] `app_version` and `updated` metadata fields are bumped in the top-level JSON object.

**CHANGELOG.md**
- [ ] `CHANGELOG.md` has a new dated entry (`## 2026-05-29` or execution date) describing the SPEC.md authorship, SKILL.md Confidence Anchor additions, router-table corrections, and reference doc fixes.

**Cross-check (no orphan claims)**
- [ ] A manual diff confirms: every MCP tool registered in `backend/mcp/tools/__init__.py` appears in both `SPEC.md` and `SKILL.md`; no tool in `SPEC.md` or `SKILL.md` is absent from `__init__.py`.
- [ ] Every CLI group in `backend/cli/main.py` `add_typer()` calls appears in `SPEC.md`; no in-repo CLI group in `SPEC.md` is absent from `main.py`.
- [ ] No reference doc updated under this contract introduces a new phantom command or tool claim.

---

## 10. Validation Requirements

- [ ] **No app build required** — this is a documentation-only artifact. No `npm run build`, `pytest`, or backend startup needed.
- [ ] **Symlink verified**: `readlink /Users/miethe/dev/homelab/development/CCDash/.claude/skills/ccdash` resolves to the MeatySkills path before any file is written.
- [ ] **SPEC.md frontmatter validates**: run `python .claude/skills/artifact-tracking/scripts/validate_artifact.py -f MeatySkills/skills/ccdash/SPEC.md` (or equivalent) — no schema errors.
- [ ] **Runtime truth cross-check**: executor reads `backend/mcp/tools/__init__.py` and `backend/cli/main.py` and confirms the counts match the skill artifacts (7 MCP tools, 7 in-repo CLI groups).
- [ ] **No unrelated changes** introduced (no app code, no other skills, no extra docs beyond the 4 ccdash skill files + up to 4 reference doc fixes).
- [ ] **JSON lint**: `router-table.json` parses cleanly with `python -m json.tool`.

---

## 11. Risk Areas

- **Symlink vs real file confusion**: The executor may inadvertently edit the CCDash-repo symlink path instead of the MeatySkills real path. Mitigation: verify `readlink` before writing; use absolute paths to `MeatySkills/`.
- **In-repo vs standalone CLI confusion (re-introduction)**: The primary drift vector for this skill is conflating in-repo and standalone CLI surfaces. Mitigation: for every command entry added or modified in `router-table.json`, the executor must trace the command back to either `backend/cli/main.py` (in-repo) or `packages/ccdash_cli/` (standalone) before assigning a transport tag.
- **Over-editing reference docs**: Reference docs document behaviors and context, not just surface assertions. Mitigation: scope reference doc changes strictly to lines that assert a tool name or command that is factually wrong; do not restructure or rewrite narrative sections.
- **SPEC.md structural mismatch**: A SPEC.md that does not match the `release/SPEC.md` convention will not be recognized by future tooling. Mitigation: read `release/SPEC.md` first; mirror its heading names and matrix columns exactly.
- **Capability matrix drift recurrence**: SPEC.md may drift again as new tools ship. Mitigation: add an Invariant in `SPEC.md` requiring the matrix to be updated on every skill version bump, and note the verification command in the Invariants section.

---

## 12. Implementation Notes

**Suggested approach** (agent may improve):

1. Resolve the symlink: `readlink /Users/miethe/dev/homelab/development/CCDash/.claude/skills/ccdash` and confirm it points to `MeatySkills/skills/ccdash/`.
2. Gather runtime truth (read-only):
   - `backend/mcp/tools/__init__.py` — extract 7 tool names from `register_tools()`.
   - `backend/cli/main.py` — extract 7 command groups from `add_typer()` calls.
   - Each `backend/cli/commands/*.py` — confirm subcommand names for `artifact`, `live`, `system`.
   - `packages/ccdash_cli/` — confirm standalone-only groups (`session`, `target`, `doctor`, `diagnostics`, `version`).
3. Read `MeatySkills/skills/release/SPEC.md` — capture the frontmatter schema, section names, and matrix column headers verbatim.
4. Author `SPEC.md` at `MeatySkills/skills/ccdash/SPEC.md` using the release SPEC structure. Suggested Capability Matrix columns: `Capability | MCP Tool | In-Repo CLI | Standalone CLI | REST Endpoint`.
5. Edit `SKILL.md`: update frontmatter fields; replace the MCP tool list in the Confidence Anchor (4 -> 7 tools); add the 3 missing in-repo CLI groups to the in-repo CLI list.
6. Edit `router-table.json`:
   - Fix `feature-list`, `feature-show`, `feature-sessions`, `feature-documents` transport tags to `["standalone-cli"]` only.
   - Add entries: `artifact-rankings`, `artifact-recommendations`, `live-active-count`, `system-active-count` with correct transport arrays.
   - Bump `app_version`, `skill_version`, `updated`.
7. Review `references/` for factual wrong surface claims; fix only those lines.
8. Append CHANGELOG entry.
9. Verify cross-check: diff the 7 MCP tool names and 7 CLI groups against each updated file.

**Similar existing code**:
- `MeatySkills/skills/release/SPEC.md` — primary structural exemplar (read first).
- `MeatySkills/skills/changelog-sync/SPEC.md` and `MeatySkills/skills/claude-agent-sdk/SPEC.md` — secondary exemplars for Capability Matrix variation.
- `MeatySkills/skills/ccdash/SKILL.md` — existing skill routing doc; update, do not replace.

**Known gotchas**:
- `artifact_recommendations` is the MCP tool name (no `ccdash_` prefix) — confirmed from `backend/mcp/tools/artifacts.py` `@mcp.tool(name="artifact_recommendations")`. Do not normalize the name.
- The in-repo `feature` CLI group has only one subcommand (`report`) — `feature list`, `feature show`, `feature sessions`, `feature documents` exist only in the standalone CLI. This is the core phantom-command bug.
- The sibling contract (`ccdash-cli-project-init`) may add a `project` command group. If it has shipped by execution time, include it in the capability matrix. If not, add it to the Enhancement Backlog in `SPEC.md`.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason (real paths under `MeatySkills/`, not CCDash symlink paths).
- **Runtime truth cross-check result**: Explicit confirmation of 7 MCP tools and 7 CLI groups matched in all updated artifacts.
- **Phantom commands removed**: List of router-table.json entries whose transport was corrected (in-repo -> standalone-cli).
- **New entries added**: List of new intent IDs added to router-table.json.
- **Validation results**: Table of validation commands and their results (symlink check, JSON lint, frontmatter validation, cross-check).
- **Deviations from contract**: Any material changes to the contract during execution and justification.
- **Risks / Limitations**: Any remaining risks or known limitations (e.g., if sibling contract `ccdash-cli-project-init` has not shipped, note the Enhancement Backlog entry).
- **Follow-up recommendations**: Suggest a preflight script or CI check that can auto-detect future skill drift.

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (3-8 points; estimated 4 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents**:
- `docs/project_plans/feature_contracts/features/ccdash-cli-project-init.md` — sibling contract; if shipped, its `project` command group belongs in this skill's capability matrix
- `MeatySkills/skills/release/SPEC.md` — structural exemplar for `SPEC.md` authorship
- `backend/mcp/tools/__init__.py` — canonical MCP tool registration
- `backend/cli/main.py` — canonical in-repo CLI command group registration
- `MeatySkills/skills/ccdash/SKILL.md` — skill routing doc being updated
- `MeatySkills/skills/ccdash/scripts/router-table.json` — routing table being corrected

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Make a conservative assumption and note it in the Completion Report. The most common ambiguity is "is this command in-repo or standalone?" — trace it to `backend/cli/main.py` (in-repo) or `packages/ccdash_cli/` (standalone) before deciding.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. Do not refactor skill narrative prose, add new recipes, or change CCDash application code. The reviewer will check for scope drift and for the phantom-command elimination specifically.
