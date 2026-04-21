# CLAUDE.md — Planning Reskin Design Handoff

This directory is the **designer handoff** for the `ccdash-planning-reskin-v2` PRD. It contains the React/Tailwind reference scaffold produced by the design pass — it is **not** production code and must not be edited as part of feature implementation.

## Scope of this directory

- `Planning Deck.html` — static design deck (source of visual truth)
- `app/`, `components/`, `src/` — reference React scaffold illustrating the target component anatomy and tokens
- `tailwind.config.js` — reference OKLCH token config; the production equivalent lives in the repo root `tailwind.config.js` and `components/Planning/primitives/planning-tokens.css`
- `uploads/` — raw design assets

## How to use it

- **Read** it when you need to understand what a planning surface should look like or what primitives exist.
- **Do not** import from this tree. Production primitives live under repo-root `components/Planning/primitives/`.
- **Do not** commit changes to this tree as part of implementation work — if a design change is needed, update the PRD and the production primitives, and note the divergence in the phase progress file.

## Authoritative docs

- **PRD**: `docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md`
- **Implementation plan**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md`
- **Progress**: `.claude/progress/ccdash-planning-reskin-v2/phase-N-progress.md`

## Phase 10 context pointer

The deferred planning follow-up specs are the production source of truth for v2 follow-on work:
`docs/project_plans/design-specs/`.

For project-wide conventions, operating procedures, agent delegation, progress tracking, and context-loading rules, defer to the **root `CLAUDE.md`** — do not duplicate those sections here.
