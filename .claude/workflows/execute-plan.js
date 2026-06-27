// execute-plan.js — Tier 2/3 plan execution workflow.
//
// Spec:     .claude/specs/workflows/execute-plan-workflow-spec.md
// Contract: .claude/specs/workflows/workflow-authoring-spec.md
// Patterns: .claude/skills/dev-execution/orchestration/workflow-patterns.md
// Schemas:  .claude/specs/workflows/schemas/execution-graph.schema.json
//           .claude/specs/workflows/schemas/execution-report.schema.json
//
// Forbidden in this file: Date.now(), Math.random(), new Date() (no args), any FS/shell call.
// All timestamps come from args.timestamp (set by Opus pre-flight).

export const meta = {
  name: 'execute-plan',
  description: 'Execute a Tier 2/3 implementation plan wave-by-wave with per-task specialists. Opus builds the ExecutionGraph pre-flight and passes it as args. Use when running a multi-wave plan that has wave_plan frontmatter.',
  phases: [
    { title: 'Dry run' },
    { title: 'Wave wave-1' },
    { title: 'Wave wave-2' },
    { title: 'Wave wave-3' },
    { title: 'Wave wave-4' },
    { title: 'Wave wave-5' },
    { title: 'Review' },
    { title: 'Fix cycle 1' },
    { title: 'Fix cycle 2' },
    { title: 'Progress update' },
  ],
  whenToUse: 'Invoke via /dev:execute-plan after Opus builds the ExecutionGraph from wave_plan frontmatter. Use dry_run:true first to inspect the graph. Keep the manual /dev:execute-plan loop as fallback until Phase 6.',
}

// ---------------------------------------------------------------------------
// JSON Schemas for structured agent output (passed via schema: option to agent()).
// These are inline because the script cannot read files (constraint 1).
// ---------------------------------------------------------------------------

const TASK_RESULT_SCHEMA = {
  type: 'object',
  required: ['id', 'assigned_to', 'status'],
  additionalProperties: false,
  properties: {
    id: { type: 'string' },
    assigned_to: { type: 'string' },
    status: { type: 'string', enum: ['completed', 'skipped', 'failed'] },
    commit_sha: { type: 'string', pattern: '^[0-9a-f]{7,40}$' },
    summary: { type: 'string' },
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
      enum: ['task-completion-validator', 'karen', 'council-review', 'code-reviewer', 'senior-code-reviewer'],
    },
    required_fixes: { type: 'array', items: { type: 'string' } },
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
      required: ['run_dir'],
    },
  },
}

// ---------------------------------------------------------------------------
// Pattern: councilEscalation — reviewer agentType routing per authoring-spec §8.
// ---------------------------------------------------------------------------

// Reviewer routing is driven PURELY by the per-phase review_intensity field
// (schema default 'standard'), NOT by plan tier. The previous `tier === 3 → karen`
// rule fired on every tier-3 phase and silently overrode the per-phase 'standard'
// default — making karen (opus) the reviewer for all phases of a tier-3 plan
// regardless of intent. Opus pre-flight now sets review_intensity:'tier3' only on
// milestone phases (e.g. end-of-feature, security cutover); everything else stays
// 'standard' → task-completion-validator. `tier` is retained for signature
// compatibility but no longer changes the default.
function councilEscalation(p, _tier) {
  if (p.review_intensity === 'council') return 'council-review'
  if (p.review_intensity === 'tier3') return 'karen'
  return 'task-completion-validator'
}

// ---------------------------------------------------------------------------
// HITL detection — tasks assigned to a human (not a registered agentType) are
// never dispatched via agent() (that would try to spawn an agent literally named
// e.g. "nick"). They are collected as HITL gates and bubbled up to Opus after the
// wave's agent work completes (reason:'hitl_required'). Until the external task
// tracker (intent-tree) is wired in, this is the human-in-the-loop gate. A task is
// HITL when explicitly flagged (t.hitl === true) or its assigned_to is not a known agent.
// ---------------------------------------------------------------------------

const KNOWN_AGENT_TYPES = new Set([
  'python-backend-engineer', 'ui-engineer-enhanced', 'ui-engineer', 'frontend-developer',
  'frontend-architect', 'backend-architect', 'backend-typescript-architect',
  'nextjs-architecture-expert', 'data-layer-expert', 'refactoring-expert', 'openapi-expert',
  'ai-engineer', 'documentation-complex', 'documentation-writer', 'documentation-expert',
  'api-documenter', 'changelog-generator', 'feature-sprint-executor', 'phase-owner',
  'codebase-explorer', 'search-specialist', 'symbols-engineer', 'artifact-tracker',
  'task-completion-validator', 'karen', 'council-review', 'code-reviewer',
  'senior-code-reviewer', 'api-librarian', 'telemetry-auditor', 'prd-writer',
  'feature-planner', 'general-purpose',
])

function isHitlTask(t) {
  return t?.hitl === true || (!!t?.assigned_to && !KNOWN_AGENT_TYPES.has(t.assigned_to))
}

// ---------------------------------------------------------------------------
// Pattern: modeBoundary — detect Mode D before spawning any agents for a wave.
// Returns an early-exit ExecutionReport or null (continue).
// ---------------------------------------------------------------------------

const HIGH_RISK_PATTERNS = [
  /auth/i, /payment/i, /billing/i, /migration/i, /alembic/i,
  /delete/i, /drop_table/i, /secret/i, /token/i,
]

function modeBoundary(wave, report) {
  // Explicit Mode D flag on any phase in this wave.
  const modeD = wave.phases.find(p => p.mode === 'D')
  if (modeD) {
    return { status: 'blocked', reason: 'mode_d', blocked_phase: modeD.id, report }
  }

  // Implicit Mode D: files_affected heuristic for high-risk paths.
  // Fires needs_opus (not blocked) so Opus can inspect before deciding.
  const riskyPhase = wave.phases.find(p =>
    (p.files_affected ?? []).some(f =>
      HIGH_RISK_PATTERNS.some(pat => pat.test(f))
    )
  )
  if (riskyPhase) {
    return { status: 'needs_opus', reason: 'mode_d', blocked_phase: riskyPhase.id, report }
  }

  return null // No boundary — continue execution.
}

// ---------------------------------------------------------------------------
// Durability footer — appended to all implementation/sprint/fix agent prompts.
// Encodes the commit-checkpoint invariant (workflow-authoring-spec.md §16):
//   - Isolated worktree branch: commit each logical unit as you go.
//   - Do NOT push, merge, stash, or touch other branches.
// Reviewer and tracker agents do NOT use this footer (they are edit-less).
// ---------------------------------------------------------------------------

const DURABILITY_FOOTER = `

DURABILITY: You are on an isolated worktree branch you own. Commit each logical unit of your work to this branch as you go (this is required so your work survives a mid-run crash and is visible to the reviewer/resume). Do NOT push, do NOT merge, do NOT stash, do NOT touch other branches.`

// ---------------------------------------------------------------------------
// Per-task fallback structurer schema and prompt.
// Used when a task agent throws on its terminal StructuredOutput call (schema miss).
// A cheap haiku structurer reads git state and emits a minimal TASK_RESULT_SCHEMA result
// so the task is not silently dropped from the phase's taskOut array.
// ---------------------------------------------------------------------------

function fallbackStructurePrompt(t) {
  return `Mode: A — Exploration Only

A task agent completed its work but failed to emit structured output.
Recover its result by reading git state.

Task id: ${t.id}
Agent: ${t.assigned_to}

Run:
  git log -1 --oneline
  git rev-parse HEAD

Return a TASK_RESULT_SCHEMA result:
  - id: "${t.id}"
  - assigned_to: "${t.assigned_to}"
  - status: "completed"
  - commit_sha: <the HEAD sha you found, or "" if no new commits>
  - summary: "recovered from disk after StructuredOutput miss"

Do NOT edit any files. Read only.`
}

// ---------------------------------------------------------------------------
// Prompt builders — pure string construction, no FS access.
// ---------------------------------------------------------------------------

function reviewPrompt(p, taskOut) {
  const taskSummaries = taskOut
    .filter(Boolean)
    .map(t => `- ${t.id} (${t.assigned_to}): ${t.summary ?? 'no summary'} [${t.status}]${t.commit_sha ? ' commit:' + t.commit_sha : ''}`)
    .join('\n')

  return `Mode: E — Reviewer

Review the completed phase and determine whether acceptance criteria are met.

Phase: ${p.id} — ${p.title}
Plan reference: ${planRef}

Completed tasks:
${taskSummaries || '(no tasks completed)'}

Return a verdict conforming to the VERDICT_SCHEMA. Set approved:true only if all tasks completed
successfully and no blockers remain. If approved:false, provide actionable required_fixes.
Do NOT git add/commit/push/stash.`
}

function fixPrompt(p, requiredFixes) {
  const fixList = (requiredFixes ?? []).map((f, i) => `${i + 1}. ${f}`).join('\n')

  return `Mode: C — Autonomous Feature Sprint

Fix the following issues identified by the reviewer for phase ${p.id} — ${p.title}.

Required fixes:
${fixList || '(see phase context for issues)'}

Apply all fixes.` + DURABILITY_FOOTER
}

function trackerPrompt(progressFile, completedTaskIds) {
  const updateArg = completedTaskIds.map(id => `${id}:completed`).join(',')
  return `Run the following command and return the exit code:

python .claude/skills/artifact-tracking/scripts/update-batch.py \\
  -f ${progressFile} \\
  --updates "${updateArg}"

Do NOT git add/commit/push/stash.`
}

function adaptivePhasePrompt(p, planRef) {
  const taskList = (p.tasks ?? [])
    .map(t => `- ${t.id} (${t.assigned_to}): ${t.prompt.slice(0, 120)}...`)
    .join('\n')

  return `Mode: C — Autonomous Feature Sprint

You are the phase orchestrator for an adaptive phase that cannot enumerate tasks up front.

Phase: ${p.id} — ${p.title}
Plan reference: ${planRef}
Isolation: ${p.isolation ?? 'shared'}

Known tasks (may be partial):
${taskList || '(derive from plan context)'}

Explore the plan, implement the phase tasks with appropriate file-ownership batching.` + DURABILITY_FOOTER
}

// ---------------------------------------------------------------------------
// Pattern: fixLoop — fix → re-review, max 2 cycles, budget-guarded.
// ---------------------------------------------------------------------------

async function fixLoop(p, taskOut, initialVerdict, reviewerType) {
  let verdict = initialVerdict
  let cycles = 0

  while (!verdict?.approved && cycles < 2 && budget.remaining() > 60_000) {
    await agent(fixPrompt(p, verdict?.required_fixes), {
      phase: `Fix cycle ${cycles + 1}`,
      agentType: p.fix_agent || taskOut.filter(Boolean)[0]?.assigned_to || 'python-backend-engineer',
      model: p.model,
    })

    verdict = await agent(reviewPrompt(p, taskOut), {
      phase: 'Review',
      agentType: reviewerType,
      schema: VERDICT_SCHEMA,
    })

    cycles++
  }

  return {
    phase: p.id,
    tasks: taskOut,
    verdict: verdict ?? { approved: false, reviewer_type: reviewerType },
    fix_cycles: cycles,
    escalate: !verdict?.approved,
    files_touched: taskOut.filter(Boolean).flatMap(t => t.files_affected ?? []),
    blockers: verdict?.approved
      ? []
      : [{ description: 'Reviewer did not approve after fix-loop cycles.', resolution_hint: 'Opus adjudication required.' }],
  }
}

// ---------------------------------------------------------------------------
// Pattern: reviewerGate — select reviewer, run, hand off to fixLoop on rejection.
//
// For review_intensity:'council' phases, invokes the review-council sub-workflow
// via workflow('review-council', ...) (one nesting level — execute-plan is the top
// workflow; review-council is the only sub-workflow it may nest).
// For all other phases, falls back to a plain agent() call with an edit-less agentType.
// ---------------------------------------------------------------------------

async function reviewerGate(p, taskOut, tier) {
  // Council path: invoke review-council sub-workflow for core-path / high-risk phases.
  // This codifies the "[Pair adversarial reviewer with AC validator]" lesson:
  // deterministically runs diverse-lens reviewers + adversarial code-tracer in parallel.
  if (p.review_intensity === 'council') {
    const councilVerdict = await workflow('review-council', {
      target: { type: 'phase-taskout', ref: p.id, description: p.title || p.id },
      task_summaries: JSON.stringify(taskOut.filter(Boolean)),
      plan_ref: planRef,
      phase_id: p.id,
      timestamp: graph.timestamp,
      intensity: 'standard',
    })

    // workflow() returns null if the user skips. Treat as a non-approval requiring escalation.
    const verdict = councilVerdict
      ? { ...councilVerdict, reviewer_type: 'council-review' }
      : { approved: false, reviewer_type: 'council-review', required_fixes: ['Council workflow was skipped — manual review required.'] }

    if (!verdict.approved) {
      return fixLoop(p, taskOut, verdict, 'council-review')
    }

    return {
      phase: p.id,
      tasks: taskOut,
      verdict,
      fix_cycles: 0,
      escalate: false,
      files_touched: taskOut.filter(Boolean).flatMap(t => t.files_affected ?? []),
      blockers: [],
    }
  }

  // Standard / tier3 path: single edit-less reviewer agent.
  const reviewerType = councilEscalation(p, tier)

  const verdict = await agent(reviewPrompt(p, taskOut), {
    phase: 'Review',
    agentType: reviewerType,
    schema: VERDICT_SCHEMA,
  })

  if (!verdict?.approved) {
    return fixLoop(p, taskOut, verdict, reviewerType)
  }

  return {
    phase: p.id,
    tasks: taskOut,
    verdict: verdict,
    fix_cycles: 0,
    escalate: false,
    files_touched: taskOut.filter(Boolean).flatMap(t => t.files_affected ?? []),
    blockers: [],
  }
}

// ---------------------------------------------------------------------------
// Pattern: trackerStep — update progress YAML via artifact-tracker agent.
// ---------------------------------------------------------------------------

async function trackerStep(progressFile, completedTaskIds) {
  if (!progressFile || completedTaskIds.length === 0) return

  await agent(trackerPrompt(progressFile, completedTaskIds), {
    phase: 'Progress update',
    agentType: 'artifact-tracker',
    model: 'haiku',
  })
}

// ---------------------------------------------------------------------------
// Main script body
// ---------------------------------------------------------------------------

// Defensive args parsing: the workflow runtime may pass args as a JSON string.
const graph = typeof args === 'string' ? JSON.parse(args) : args

const {
  waves,
  tier,
  plan_ref: planRef,
  dry_run: dryRun,
  progressFile,
} = graph

// ---------------------------------------------------------------------------
// dryRun short-circuit — FIRST conditional after graph parsing, before any agent() calls.
// Returns the parsed graph for Opus inspection. Not an ExecutionReport.
// ---------------------------------------------------------------------------
if (dryRun) {
  phase('Dry run')
  log('dry_run=true — returning parsed graph for inspection, no agents spawned.')
  return { status: 'dry_run', graph }
}

// ---------------------------------------------------------------------------
// Pattern: waveFanout — sequential waves, parallel phases, file-ownership batches.
// ---------------------------------------------------------------------------

const report = []

for (const wave of waves) {
  log(`Starting Wave ${wave.id}`)
  phase(`Wave ${wave.id}`)

  // Pattern: modeBoundary — detect Mode D before spawning any agents for this wave.
  // Mode D phases are NEVER executed inside the workflow (constraint 2).
  const boundary = modeBoundary(wave, report)
  if (boundary) return boundary

  // Budget exhaustion guard before dispatching an entire wave.
  if (budget.remaining() < 60_000) {
    log(`Budget exhausted before Wave ${wave.id} — returning to Opus.`)
    return { status: 'needs_opus', reason: 'budget_exhausted', report }
  }

  // All phases in this wave run concurrently (parallel barrier).
  const waveResults = await parallel(wave.phases.map(p => async () => {

    // Adaptive phases: task list cannot be enumerated up front; dispatch a phase-owner.
    if (p.phase_strategy === 'adaptive') {
      log(`Phase ${p.id} is adaptive — dispatching phase-owner.`)
      const poResult = await agent(adaptivePhasePrompt(p, planRef), {
        label: p.id,
        phase: `Wave ${wave.id}`,
        agentType: 'phase-owner',
        model: p.model,
        isolation: p.isolation === 'worktree' ? 'worktree' : undefined,
      })

      // Adaptive phases get a reviewer gate on the phase-owner's output.
      const taskOut = poResult
        ? [{ id: p.id, assigned_to: 'phase-owner', status: 'completed', summary: poResult }]
        : []
      const phaseResult = await reviewerGate(p, taskOut, tier)

      if (progressFile) {
        await trackerStep(progressFile, taskOut.map(t => t.id))
      }
      return phaseResult
    }

    // Static phases: per-task specialist dispatch via file-ownership batches.
    const batches = p.batches && p.batches.length > 0
      ? p.batches
      : [p.tasks] // Fallback: treat all tasks as one batch if batches not precomputed.

    // Partition out human-assigned (HITL) tasks: they are gates, not dispatchable agent work.
    const hitlGates = (p.tasks ?? [])
      .filter(t => isHitlTask(t) && t.status !== 'completed')
      .map(t => ({ phase: p.id, id: t.id, assigned_to: t.assigned_to, prompt: t.prompt }))

    const taskOut = []

    for (const batch of batches) {
      // Inner parallel: only tasks with disjoint files_affected are in the same batch.
      // HITL tasks are skipped here — never passed to agent() as an agentType.
      const dispatchable = batch.filter(t => !isHitlTask(t))
      if (dispatchable.length === 0) continue
      const batchOut = await parallel(dispatchable.map(t => async () => {
        // Happy path: task agent emits structured output directly.
        // Durability footer appended to every task prompt (see DURABILITY_FOOTER).
        let result
        try {
          result = await agent(t.prompt + DURABILITY_FOOTER, {
            label: `${p.id}:${t.id}`,
            phase: `Wave ${wave.id}`,
            agentType: t.assigned_to,
            model: t.model,
            isolation: (t.isolation ?? p.isolation) === 'worktree' ? 'worktree' : undefined,
            schema: TASK_RESULT_SCHEMA,
          })
        } catch (_schemaErr) {
          // Per-task fallback structurer: task did work but missed terminal StructuredOutput.
          // A cheap haiku structurer reads git state and emits a minimal TASK_RESULT_SCHEMA result
          // so the task is not silently dropped. Keeps happy path single-agent.
          log(`Task ${t.id} schema miss — running fallback structurer.`)
          try {
            result = await agent(fallbackStructurePrompt(t), {
              label: `${p.id}:${t.id}:struct`,
              phase: `Wave ${wave.id}`,
              agentType: 'general-purpose',
              model: 'haiku',
              schema: TASK_RESULT_SCHEMA,
            })
          } catch (_fallbackErr) {
            log(`Task ${t.id} fallback structurer also failed — task will be dropped.`)
            result = null
          }
        }
        return result
      }))
      taskOut.push(...batchOut.filter(Boolean))
    }

    // Reviewer gate + fix-loop (edit-less agentType only — constraint 3).
    // Skip the reviewer when the phase had no agent work (pure-HITL phase) — there is
    // nothing to review; the human gate is surfaced via hitl_gates below.
    const phaseResult = taskOut.length > 0
      ? await reviewerGate(p, taskOut, tier)
      : { phase: p.id, tasks: [], verdict: { approved: true, reviewer_type: 'none' }, fix_cycles: 0, escalate: false, files_touched: [], blockers: [] }

    phaseResult.hitl_gates = hitlGates

    // trackerStep: one per phase (no FS in script — via artifact-tracker agent).
    if (progressFile) {
      const completedIds = taskOut.filter(t => t?.status === 'completed').map(t => t.id)
      if (completedIds.length > 0) {
        await trackerStep(progressFile, completedIds)
      }
    }

    return phaseResult
  }))

  const completedWaveResults = waveResults.filter(Boolean)
  report.push({ wave: wave.id, phases: completedWaveResults })

  // Escalate if any phase's fix-loop exhausted without reviewer approval.
  if (completedWaveResults.some(r => r?.escalate)) {
    log(`Wave ${wave.id}: reviewer escalation unresolved — returning to Opus.`)
    return { status: 'needs_opus', reason: 'reviewer_unresolved', report }
  }

  // HITL gate: if any phase in this wave has pending human-assigned tasks, the wave's
  // agent work + reviewer gates are done, but we cannot advance past a human sign-off
  // inside the workflow (constraint 2 — no mid-run human approval). Bubble up to Opus,
  // which coordinates the human review (future: external task-tracker / intent-tree
  // review request), then relaunches with the HITL tasks marked complete / trimmed.
  const hitlTasks = completedWaveResults.flatMap(r => r?.hitl_gates ?? [])
  if (hitlTasks.length > 0) {
    log(`Wave ${wave.id}: ${hitlTasks.length} human-assigned task(s) require HITL gating — returning to Opus.`)
    return { status: 'needs_opus', reason: 'hitl_required', hitl_tasks: hitlTasks, report }
  }

  // NB: cross-wave worktree merge happens in Opus post-wave (no git in script — constraint 1).
  log(`Wave ${wave.id} complete. Opus: run git merge --squash on worktree branches before next wave.`)
}

return { status: 'complete', report }
