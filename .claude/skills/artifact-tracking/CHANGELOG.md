# CHANGELOG — artifact-tracking

## v0.2.1 — 2026-08-11

- **Added `scripts/tests/test_intenttree_capture.py`** (232L, DI-107 discovery invariants), the one
  file the fleet carried that this edit point did not. It came from the `intenttree` checkout and
  covers `intenttree_capture.py`'s catch-all-directory discovery: a catch-all dir captures each
  FILE as its own feature so generic task ids (`QF-1`) reused across files never collide, a normal
  feature dir still aggregates its phase files into one feature, and fully-complete catch-all files
  are excluded. Complements the existing `test_intenttree_capture_slug.py`, which covers the M4
  creation-time `feature_slug` stamp rather than discovery.
- **No behaviour change.** This release exists so the content published to SkillMeat is the true
  fleet superset — see `node_01KZRR34A7X7EGRN7C00ASX181`. The registered artifact had been the
  stalest copy anywhere (329L `intenttree_capture.py` with no `PUBLIC_API` against this repo's
  982L reconciled shim), so any `skillmeat deploy` of it would have clobbered the DI-319/DI-323
  anti-clobber work plus the whole v0.2.0 frontmatter-write-contract set.

## v0.2.0 — 2026-08-06

- **Added `scripts/_frontmatter_edit.py`** — a shared, format-preserving frontmatter editor that
  edits LINES rather than re-emitting a parsed dict. Untouched keys are byte-identical after a
  write by construction. Preserves list indentation and per-item quoting, bare-date scalars,
  block scalars (`>`/`|`), non-ASCII characters, flow-style lists on `--append`, and the touched
  line's own quote style plus any trailing inline comment. Sniffs the file's own dominant list
  indentation for a list it does not yet have. See § Frontmatter Write Contract in SKILL.md.
- **Fixed `scripts/update-field.py` and `scripts/manage-plan-status.py` full-re-serialize**
  (`node_01KZCBKGQCJCBMZRS4T0SCTT7N`). Any `--set`/`--append`/`--status`/`--field` rewrote the
  entire frontmatter block through a `yaml.safe_dump` round-trip, so a 1-line status change
  produced a 29-insertion / 16-deletion diff with five classes of regression in keys the caller
  never named: `—` escaped to `—`, `created: 2026-07-30` requoted to a string, list
  indentation flattened, list items re-quoted and hard-wrapped mid-string, and a folded block
  scalar collapsed onto one line. All valid YAML, so no validator caught any of it — the cost was
  that the diff stopped being evidence a bookkeeping commit was only bookkeeping. Measured over
  the real corpus: a semantically-null write collaterally rewrote **200 of 212** plans before,
  **0 of 212** after, with all 212 verified semantically identical (no data loss).
- **`update-field.py` now validates the object it is about to write**, re-parsed from the edited
  lines, instead of a separately-mutated dict that could drift from the file.
- **`update-field.py --append` now fills a key declared with no items** (`pr_refs:`), which
  previously failed with "Field 'pr_refs' is not a list; cannot append."
- **`updated:` no longer flips a bare date to a quoted string** on the first write (both writers
  now pass a `date`, not a `"YYYY-MM-DD"` string); a file that already quotes it keeps its quotes.
- **Removed `write_frontmatter_and_body` from `manage-plan-status.py`** so the re-serializing
  helper cannot be reached again by a future edit; a comment marks why.

## v0.1.0 — 2026-07-31

- **Added `scripts/validate-plan-frontmatter.py`** — the plan-frontmatter linter the launchpad
  contract has long referenced but never shipped (`docs/agentic-operator/contracts/frontmatter-schema.md`
  §5c / §7 item 9). Enforces the ratified 15-value IntentTree `NodeStatus` enum (§4, OQ-2) on a
  plan's top-level `status`; derives its MUST/SHOULD/MAY field sets by parsing the machine-readable
  block in `planning/references/plan-frontmatter-schema.md` (hardcoded fallback). Modes: check
  (default), `--apply` (additive + format-preserving autofix — rewrites only the `status:` value
  token in place, preserving quoting/indent/inline comment, and inserts a `planning_maturity:` line
  when the alias implies one and the file lacks it), `--json`. Exit codes: `0` clean, `2`
  violation(s), `1` usage error. Advisory in v1 (reports; does not block commits). Delivered as part
  of the Shipped Work Ledger initiative, milestone M1.
- **Added `scripts/_status_aliases.py`** — shared status vocabulary (the ratified `NodeStatus`
  enum + the ratified + claude-decided alias map + hand-review set). Single source of truth
  imported by both `validate-plan-frontmatter.py` and `manage-plan-status.py`.
- **Reconciled `scripts/manage-plan-status.py`'s stale enum** — the CCDash-era `VALID_STATUSES`
  (`draft`/`pending`/`review`/`approved`/`superseded`/…) is replaced by the canonical 15 `NodeStatus`
  values. Legacy alias spellings are still accepted for backward compatibility but are normalized to
  their `NodeStatus` on write. `approved` / `superseded` are dropped (use `ready` / `archived`). CLI
  interface/args unchanged.
- **Added `scripts/tests/test_validate_plan_frontmatter.py`** — offline unit coverage for the alias
  map, the exit-code gate (incl. an invalid-status fixture), additive/format-preserving autofix, and
  hand-review non-mutation.
- **SKILL.md brought to `skill-dev` conformance** — added `version` / `app_version` / `updated`
  frontmatter, this CHANGELOG, `## When NOT To Use` + `## Do Not Say` sections, and a Canonical
  Status Enforcement section documenting the new linter.

> Deployment note: this skill is deployed from the **enterprise SkillMeat** instance
> (`skillmeat` federation, node `10.42.10.76:8080`) per AOS enterprise-only federation doctrine —
> edit here (the upstream), then re-project. The `.agents/` Codex mirror is generated by
> `skillmeat deploy artifact-tracking --profile codex --apply-overlay`, not hand-written.
