/**
 * execute-contract — Tier 1 sprint workflow
 *
 * Spec: .claude/specs/workflows/execute-contract-workflow-spec.md
 * Master contract: .claude/specs/workflows/workflow-authoring-spec.md
 *
 * Patterns used: reviewerGate, fixLoop, modeBoundary (inline), two-stage structuring
 * Schemas: execution-graph.schema.json (args), execution-report.schema.json (return)
 *
 * Durability design (see workflow-authoring-spec.md §16):
 *   - Sprint stage: feature-sprint-executor, NO schema. Commits checkpoints to worktree.
 *     Writes Completion Report to a deterministic path before returning plain text.
 *   - Structure stage: haiku general-purpose agent, schema: SPRINT_RESULT_SCHEMA.
 *     Reads the report from disk and derives structured fields from git state.
 *   This two-stage design prevents a terminal StructuredOutput miss from discarding
 *   the sprint's committed work. The structure stage falls back gracefully on failure.
 *
 * Four-constraints checklist:
 *   [x] No FS/shell access in script body
 *   [x] Mode D triggers early return before sprint spawns
 *   [x] All reviewer agents use edit-less agentType
 *   [x] No Date.now() / Math.random() / new Date() in script body
 *   [x] meta is a pure literal object
 *   [x] phase() titles match meta.phases exactly
 *   [x] Budget guard in fix-loop: budget.remaining() > 60_000
 *   [x] All implementation prompts include durability commit instruction
 */

// ─── meta (pure literal — no computed values, no function calls) ──────────────

export const meta = {
  name: 'execute-contract',
  description: 'Tier 1 autonomous sprint: feature-sprint-executor sprint → reviewer gate → ≤2-cycle fix-loop → structured Completion Report. Use when a Feature Contract (3–8 pts) is approved and does not touch auth/payments/migrations.',
  phases: [
    { title: 'Sprint' },
    { title: 'Review' },
    { title: 'Fix cycle 1' },
    { title: 'Fix cycle 2' },
  ],
  whenToUse: 'Feature Contract approved, 3–8 story points, no Mode D paths (auth/payments/migrations/deletion). Invoke as: workflow execute-contract with args envelope built by Opus pre-flight.',
}

// ─── inline schemas ───────────────────────────────────────────────────────────

const SPRINT_RESULT_SCHEMA = {
  type: 'object',
  required: ['completion_report_path', 'ac_verdicts', 'commit_sha', 'files_touched'],
  additionalProperties: false,
  properties: {
    completion_report_path: { type: 'string' },
    ac_verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['criterion', 'met'],
        additionalProperties: false,
        properties: {
          criterion: { type: 'string' },
          met: { type: 'boolean' },
          notes: { type: 'string' },
        },
      },
    },
    commit_sha: { type: 'string', pattern: '^[0-9a-f]{7,40}$' },
    files_touched: { type: 'array', items: { type: 'string' } },
    blockers: {
      type: 'array',
      items: {
        type: 'object',
        required: ['description'],
        additionalProperties: false,
        properties: {
          description: { type: 'string' },
          resolution_hint: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['approved', 'reviewer_type'],
  additionalProperties: false,
  properties: {
    approved: { type: 'boolean' },
    reviewer_type: {
      type: 'string',
      enum: [
        'task-completion-validator',
        'karen',
        'council-review',
        'code-reviewer',
        'senior-code-reviewer',
      ],
    },
    required_fixes: {
      type: 'array',
      items: { type: 'string' },
    },
    council_artifacts: {
      type: 'object',
      properties: {
        run_dir: { type: 'string' },
        findings_yaml: { type: 'string' },
        scorecard_json: { type: 'string' },
        risk_register_yaml: { type: 'string' },
        decision_record_md: { type: 'string' },
        validation_plan_md: { type: 'string' },
      },
    },
  },
}

// ─── helpers (pure functions — no primitives called here) ─────────────────────

/**
 * Route reviewer agentType from review_intensity + tier.
 * Mirrors authoring-spec §8 and councilEscalation pattern.
 * Always returns an edit-less agentType (constraint 3).
 */
function reviewerAgentType(reviewIntensity, tier) {
  if (reviewIntensity === 'council') return 'council-review'
  if (reviewIntensity === 'tier3' || tier === 3) return 'karen'
  return 'task-completion-validator'
}

/**
 * Derive the deterministic completion report path for a contract.
 * Returns parsed.completion_report_path if provided in args, otherwise derives
 * .claude/worknotes/<slug>/completion-report.md where <slug> is the contract
 * filename without directory or .md extension (string ops only — no FS).
 */
function reportPathForContract(parsed) {
  if (parsed.completion_report_path) return parsed.completion_report_path
  // Derive slug from contract_path: strip directory and .md extension.
  const contractPath = parsed.contract_path || ''
  const basename = contractPath.split('/').pop() || 'contract'
  const slug = basename.replace(/\.md$/, '')
  return `.claude/worknotes/${slug}/completion-report.md`
}

/**
 * Build the sprint agent prompt (Stage A — no schema, plain text output).
 * Includes Mode marker, contract path, context paths, budget hint.
 * DURABILITY: sprint agent must commit each logical unit AND write the Completion
 * Report to the deterministic path BEFORE returning. Final message is a human
 * summary only — a downstream structurer emits the machine-readable result.
 */
function sprintPrompt(parsed, reportPath) {
  const contextSection = parsed.context_paths && parsed.context_paths.length > 0
    ? `\nRelevant context paths (read before implementing):\n${parsed.context_paths.map(p => `  - ${p}`).join('\n')}`
    : ''

  return `Mode: C — Autonomous Feature Sprint

Contract: ${parsed.contract_path}
Completion Report path (write here BEFORE finishing): ${reportPath}
Budget hint: ~${parsed.budget_total || 50000} tokens${contextSection}

Run the full Tier 1 sprint:
  1. Read and internalise the Feature Contract at the path above.
  2. Explore the codebase for relevant patterns (symbols-first, then targeted file reads).
  3. Implement all Acceptance Criteria.
  4. DURABILITY: commit each logical unit of work to the current worktree branch as you go.
     This is REQUIRED so your work survives a mid-run crash and is visible to the reviewer.
     Commit message format: "feat(<slug>): <what was done>". Do NOT push, merge, stash,
     or touch other branches.
  5. Run validation commands (pytest / pnpm test + type-check + lint as applicable).
  6. Write the Completion Report to: ${reportPath}
     The report MUST be written to disk before you return. Use the standard template from
     your agent definition (Summary, Files Changed, AC Status, Validation Run, Deviations,
     Risks, Follow-Up, Memory Candidates).
  7. Your final message is a human-readable summary of what was done and what AC passed/failed.
     A downstream structurer agent will read the report file and git log to emit the
     machine-readable SprintResult — you do NOT need to emit structured output yourself.

Do NOT push, merge, stash, or touch branches other than your current worktree branch.
Do NOT install new dependencies without justification in the Completion Report.`
}

/**
 * Build the structure agent prompt (Stage B — haiku, schema: SPRINT_RESULT_SCHEMA).
 * Reads the Completion Report from the deterministic path, runs git commands to
 * derive commit_sha and files_touched, parses AC verdicts from the report.
 */
function structurePrompt(parsed, reportPath) {
  const branchBase = parsed.branch_base || 'HEAD~10'
  return `Mode: A — Exploration Only

Read the Completion Report at: ${reportPath}

If the file does not exist, set commit_sha to "" and return a result with:
  - completion_report_path: "${reportPath}"
  - ac_verdicts: []
  - files_touched: []
  - blockers: [{description: "Completion report not found — sprint may have failed to write it"}]

If the file exists:
  1. Run: git log --oneline "${branchBase}..HEAD"
     and: git rev-parse HEAD
     to get the latest commit SHA. If no new commits exist since the branch base,
     set a blocker: "No commits found since branch base — sprint work may be uncommitted."
  2. Run: git diff --name-only "${branchBase}..HEAD"
     to get files_touched.
  3. Parse the "### Acceptance Criteria Status" section of the report.
     For each line starting with "- [x]" set met:true; "- [ ]" set met:false.
     Extract the criterion text after the checkbox.
  4. Set completion_report_path to the exact path you read.
  5. Return the structured SprintResult conforming to the schema.

Do NOT edit any files. Read only.`
}

/**
 * Build the reviewer prompt.
 * Includes Mode marker, contract path, completion report path, and commit SHA.
 * Reviewer must NOT produce code changes — enforced by agentType definition.
 */
function reviewPrompt(parsed, sprintResult) {
  return `Mode: E — Reviewer

Contract: ${parsed.contract_path}
Completion Report: ${sprintResult.completion_report_path}
Sprint commit SHA: ${sprintResult.commit_sha}

Review the sprint output against all Acceptance Criteria in the Feature Contract.
Diff the commit SHA against the branch base to verify the changes match the contract scope.

Return a structured VERDICT:
  - approved: true only when ALL Acceptance Criteria are met with no required fixes outstanding.
  - reviewer_type: your agentType string.
  - required_fixes: if approved is false, list each required fix as a clear, actionable instruction for the fix agent.

Do NOT modify any source files. Read only.`
}

/**
 * Build the fix-cycle agent prompt.
 * Receives the reviewer's required_fixes list and applies targeted patches only.
 * DURABILITY: fix agent must commit its fixes to the worktree branch.
 */
function fixPrompt(parsed, requiredFixes, cycleNumber) {
  return `Mode: C — Autonomous Feature Sprint (Fix cycle ${cycleNumber})

Contract: ${parsed.contract_path}
Fix cycle: ${cycleNumber} of 2

The reviewer found the following issues that must be resolved:
${requiredFixes.map((f, i) => `  ${i + 1}. ${f}`).join('\n')}

Apply targeted fixes ONLY for the issues listed above. Do not re-implement areas the reviewer approved.
Run relevant validation commands after fixing (pytest / pnpm test + type-check as applicable).

DURABILITY: commit your fixes to the current worktree branch before returning.
This is REQUIRED so your work survives a session interruption.
Do NOT push, merge, stash, or touch other branches.`
}

/**
 * Build the reviewer prompt.
 * Includes Mode marker, contract path, completion report path, and commit SHA.
 * Reviewer must NOT produce code changes — enforced by agentType definition.
 */
function reviewPrompt(parsed, sprintResult) {
  return `Mode: E — Reviewer

Contract: ${parsed.contract_path}
Completion Report: ${sprintResult.completion_report_path}
Sprint commit SHA: ${sprintResult.commit_sha}

Review the sprint output against all Acceptance Criteria in the Feature Contract.
Diff the commit SHA against the branch base to verify the changes match the contract scope.

Return a structured VERDICT:
  - approved: true only when ALL Acceptance Criteria are met with no required fixes outstanding.
  - reviewer_type: your agentType string.
  - required_fixes: if approved is false, list each required fix as a clear, actionable instruction for the fix agent.

Do NOT modify any source files. Read only.`
}

/**
 * Build the fix-cycle agent prompt.
 * Receives the reviewer's required_fixes list and applies targeted patches only.
 */
function fixPrompt(parsed, requiredFixes, cycleNumber) {
  return `Mode: C — Autonomous Feature Sprint (Fix cycle ${cycleNumber})

Contract: ${parsed.contract_path}
Fix cycle: ${cycleNumber} of 2

The reviewer found the following issues that must be resolved:
${requiredFixes.map((f, i) => `  ${i + 1}. ${f}`).join('\n')}

Apply targeted fixes ONLY for the issues listed above. Do not re-implement areas the reviewer approved.
Run relevant validation commands after fixing (pytest / pnpm test + type-check as applicable).
Commit your fixes. Return nothing — the reviewer will re-evaluate after this agent completes.

Do NOT git add/commit/push/stash beyond your own fix commits. Do NOT merge to main.`
}

// ─── Mode D boundary detection ────────────────────────────────────────────────

/**
 * High-risk path heuristic for implicit Mode D detection.
 * Mirrors modeBoundary pattern in workflow-patterns.md.
 * Returns true if any path in filesAffected matches a high-risk pattern.
 */
const HIGH_RISK_PATTERNS = [
  /auth/i, /payment/i, /billing/i, /migration/i, /alembic/i,
  /delete/i, /drop_table/i, /secret/i, /token/i,
]

function hasHighRiskPaths(filesAffected) {
  if (!Array.isArray(filesAffected)) return false
  return filesAffected.some(f =>
    HIGH_RISK_PATTERNS.some(pat => pat.test(f))
  )
}

// ─── workflow body ────────────────────────────────────────────────────────────

// Parse args defensively: the Workflow tool may deliver args as a JSON string or object.
const parsed = typeof args === 'string' ? JSON.parse(args) : args

// ── dry-run short-circuit ─────────────────────────────────────────────────────
if (parsed.dry_run === true) {
  log('Dry-run mode — returning parsed args envelope without spawning agents.')
  return {
    status: 'complete',
    report: [],
    _dry_run: true,
    _parsed_args: parsed,
  }
}

// ── Mode D boundary check (before any agents spawn) ──────────────────────────
// Explicit flag first, then implicit heuristic on files_affected.
// Per constraint 2: no mid-run sign-off — Mode D must be a workflow boundary.
const contractMeta = parsed.contract_metadata || {}
const modeD =
  contractMeta.mode === 'D' ||
  hasHighRiskPaths(contractMeta.files_affected)

if (modeD) {
  log('Mode D boundary detected — returning to Opus before spawning any agents.')
  return {
    status: 'needs_opus',
    reason: 'mode_d',
    blocked_phase: 'sprint',
    report: [],
  }
}

// ── Phase 1: Sprint (two-stage: executor + structurer) ───────────────────────
// Stage A: feature-sprint-executor, NO schema. Heavy executor commits checkpoints
// to the worktree branch and writes the Completion Report to a deterministic path
// before returning plain text. This decouples durable work from terminal output.
// Stage B: haiku general-purpose structurer reads the report + git state and emits
// the machine-readable SprintResult. Isolated from the sprint so a schema miss in
// Stage B cannot discard Stage A's committed work.
phase('Sprint')
log(`Starting Tier 1 sprint for contract: ${parsed.contract_path}`)

const reportPath = reportPathForContract(parsed)
log(`Completion report path: ${reportPath}`)

// Stage A — sprint (no schema, plain text output)
const sprintText = await agent(sprintPrompt(parsed, reportPath), {
  label: 'sprint',
  phase: 'Sprint',
  agentType: 'feature-sprint-executor',
  // No schema: heavy executor must not carry a terminal StructuredOutput call.
  // The structurer (Stage B) emits the machine-readable result.
})

// If the user skipped the sprint agent, return blocked.
if (!sprintText) {
  log('Sprint agent was skipped — returning to Opus.')
  return {
    status: 'needs_opus',
    reason: 'reviewer_unresolved',
    blocked_phase: 'sprint',
    report: [],
  }
}

log('Sprint stage complete. Running structure stage.')

// Stage B — structurer (haiku, schema: SPRINT_RESULT_SCHEMA)
// Reads the report file and git state to fill structured fields.
// Wrapped in try/catch so a structure failure degrades gracefully rather than crashing.
let sprintResult
try {
  sprintResult = await agent(structurePrompt(parsed, reportPath), {
    label: 'sprint-structurer',
    phase: 'Sprint',
    agentType: 'general-purpose',
    model: 'haiku',
    schema: SPRINT_RESULT_SCHEMA,
  })
} catch (structureErr) {
  log(`WARNING: Structure stage threw (${structureErr && structureErr.message ? structureErr.message : structureErr}). Falling back to minimal result.`)
  // Fallback: minimal result; Opus can inspect the report on disk.
  sprintResult = {
    completion_report_path: reportPath,
    commit_sha: '',
    ac_verdicts: [],
    files_touched: [],
    blockers: [{ description: 'Structure stage failed — inspect completion report on disk.', resolution_hint: 'Run: git log --oneline to find sprint commits; read ' + reportPath }],
  }
}

if (!sprintResult) {
  log('Structure stage returned null. Using minimal fallback.')
  sprintResult = {
    completion_report_path: reportPath,
    commit_sha: '',
    ac_verdicts: [],
    files_touched: [],
    blockers: [{ description: 'Structure stage returned null — inspect completion report on disk.', resolution_hint: 'Read ' + reportPath }],
  }
}

// Build the base task result from the sprint.
const sprintTaskResult = {
  id: 'SPRINT',
  assigned_to: 'feature-sprint-executor',
  status: 'completed',
  commit_sha: sprintResult.commit_sha,
  summary: `Sprint complete. AC verdicts: ${sprintResult.ac_verdicts.filter(v => v.met).length}/${sprintResult.ac_verdicts.length} met. Completion report: ${sprintResult.completion_report_path}`,
}

// ── Phase 2: Review ───────────────────────────────────────────────────────────
phase('Review')
log('Running reviewer gate.')

const reviewerType = reviewerAgentType(
  parsed.review_intensity || 'standard',
  parsed.tier || 1
)

let verdict = await agent(reviewPrompt(parsed, sprintResult), {
  label: 'review',
  phase: 'Review',
  agentType: reviewerType,
  schema: VERDICT_SCHEMA,
})

// ── Phase 3+: Fix-loop (≤2 cycles, budget-guarded) ───────────────────────────
// Pattern: fixLoop from workflow-patterns.md
// Cap: 2 cycles. Guard: budget.remaining() > 60_000.
// Fix agent defaults to feature-sprint-executor; override via args.fix_agent.
const fixAgentType = parsed.fix_agent || 'feature-sprint-executor'
let cycles = 0

while (verdict && !verdict.approved && cycles < 2 && budget.remaining() > 60_000) {
  const cycleNumber = cycles + 1
  phase(`Fix cycle ${cycleNumber}`)
  log(`Fix cycle ${cycleNumber}: applying ${(verdict.required_fixes || []).length} required fix(es).`)

  await agent(fixPrompt(parsed, verdict.required_fixes || [], cycleNumber), {
    label: `fix-cycle-${cycleNumber}`,
    phase: `Fix cycle ${cycleNumber}`,
    agentType: fixAgentType,
    model: parsed.fix_model || undefined,
  })

  // Re-run reviewer after each fix cycle.
  verdict = await agent(reviewPrompt(parsed, sprintResult), {
    label: `review-cycle-${cycleNumber}`,
    phase: 'Review',
    agentType: reviewerType,
    schema: VERDICT_SCHEMA,
  })

  cycles++
}

// ── Determine final status ────────────────────────────────────────────────────
const approved = verdict?.approved === true
const budgetExhausted = !approved && cycles < 2 && budget.remaining() <= 60_000

let finalStatus = 'complete'
let reason

if (!approved) {
  finalStatus = 'needs_opus'
  reason = budgetExhausted ? 'budget_exhausted' : 'reviewer_unresolved'
  log(`Escalating to Opus — reason: ${reason} (cycles: ${cycles}).`)
} else {
  log('Reviewer approved. Sprint complete.')
}

// ── Build ExecutionReport conforming to execution-report.schema.json ──────────
const phaseResult = {
  phase: 'sprint',
  tasks: [sprintTaskResult],
  verdict: verdict || { approved: false, reviewer_type: reviewerType, required_fixes: ['Sprint agent returned null'] },
  fix_cycles: cycles,
  escalate: !approved,
  files_touched: sprintResult.files_touched || [],
  blockers: sprintResult.blockers || [],
}

const report = [
  {
    wave: 'wave-1',
    phases: [phaseResult],
  },
]

const result = { status: finalStatus, report }
if (reason) result.reason = reason
if (finalStatus === 'needs_opus' && reason === 'mode_d') result.blocked_phase = 'sprint'

return result
