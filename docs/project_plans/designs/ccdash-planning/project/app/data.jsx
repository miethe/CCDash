// Sample planning data. Extended: multi-doc artifacts (specs[], prds[], plans[]),
// SPIKEs, Open Questions, and task dependencies for the dependency DAG view.

const ARTIFACTS = {
  spec:  { key: 'spec',  label: 'Design Spec',  short: 'SPEC', color: 'var(--spec)',  glyph: '◇' },
  spk:   { key: 'spk',   label: 'SPIKE',        short: 'SPIKE',color: 'var(--spk)',   glyph: '✦' },
  prd:   { key: 'prd',   label: 'PRD',          short: 'PRD',  color: 'var(--prd)',   glyph: '◼' },
  plan:  { key: 'plan',  label: 'Impl Plan',    short: 'PLAN', color: 'var(--plan)',  glyph: '▲' },
  prog:  { key: 'prog',  label: 'Progress',     short: 'PHASE',color: 'var(--prog)',  glyph: '●' },
  ctx:   { key: 'ctx',   label: 'Context',      short: 'CTX',  color: 'var(--ctx)',   glyph: '◉' },
  trk:   { key: 'trk',   label: 'Tracker',      short: 'TRK',  color: 'var(--trk)',   glyph: '◆' },
  rep:   { key: 'rep',   label: 'Report',       short: 'REP',  color: 'var(--rep)',   glyph: '▣' },
};

const AGENTS = {
  'python-backend-engineer':   { short: 'py-be',    tier: 'exec',  model: 'sonnet' },
  'ui-engineer-enhanced':      { short: 'ui-eng+',  tier: 'exec',  model: 'sonnet' },
  'data-layer-expert':         { short: 'data',     tier: 'exec',  model: 'sonnet' },
  'openapi-expert':            { short: 'oapi',     tier: 'exec',  model: 'sonnet' },
  'nextjs-architecture-expert':{ short: 'next-arch',tier: 'exec',  model: 'sonnet' },
  'task-completion-validator': { short: 'validator',tier: 'review',model: 'sonnet' },
  'senior-code-reviewer':      { short: 'reviewer', tier: 'review',model: 'sonnet' },
  'karen':                     { short: 'karen',    tier: 'review',model: 'opus'   },
  'documentation-writer':      { short: 'docs',     tier: 'docs',  model: 'haiku'  },
  'implementation-planner':    { short: 'impl-plan',tier: 'plan',  model: 'haiku'  },
  'prd-writer':                { short: 'prd-writer',tier:'plan',  model: 'sonnet' },
  'lead-pm':                   { short: 'lead-pm',  tier: 'orch',  model: 'opus'   },
};

// Features — artifacts are ARRAYS for spec/prd/plan/ctx/rep; spikes[] and openQuestions[] first-class.
const FEATURES = [
  {
    id: 'dvcs-enterprise-federation',
    slug: 'dvcs-enterprise-federation',
    title: 'DVCS Enterprise Federation',
    category: 'features',
    owner: 'lead-pm',
    tags: ['federation', 'multi-tenant', 'L'],
    raw: 'in-progress', effective: 'in-progress', complexity: 'L',
    updated: '2026-04-18',
    artifacts: {
      specs: [
        { id: 'spec-1', status: 'ready', updated: '2026-03-02', path: 'docs/project_plans/design-specs/dvcs-enterprise-federation.md', title: 'Primary design spec' },
        { id: 'spec-2', status: 'ready', updated: '2026-03-08', path: 'docs/project_plans/design-specs/dvcs-ef-trust.md', title: 'Trust-store deep-dive' },
      ],
      prds: [
        { id: 'prd-1', status: 'approved', updated: '2026-03-15', path: 'docs/project_plans/PRDs/features/dvcs-enterprise-federation.md', title: 'Federation · core PRD' },
      ],
      plans: [
        { id: 'plan-1', status: 'in-progress', updated: '2026-04-10', path: 'docs/project_plans/implementation_plans/features/dvcs-enterprise-federation.md', title: 'Federation backend plan' },
        { id: 'plan-2', status: 'draft',       updated: '2026-04-02', path: 'docs/project_plans/implementation_plans/features/dvcs-ef-ui.md',            title: 'Federation UI plan' },
      ],
      ctxs: [
        { id: 'ctx-1', status: 'in-progress', updated: '2026-04-18', path: '.claude/worknotes/dvcs-enterprise-federation/context.md', title: 'Working context' },
      ],
      reports: [],
    },
    spikes: [
      { id: 'SPK-01', title: 'Multi-tenant trust key rotation', status: 'completed', updated: '2026-02-14', path: 'docs/dev/spikes/ef-trust-rotation.md' },
      { id: 'SPK-02', title: 'Cross-region replication latency', status: 'in-progress', updated: '2026-04-17', path: 'docs/dev/spikes/ef-replication.md' },
    ],
    openQuestions: [
      { id: 'OQ-01', text: 'Should tenant isolation default to strict for free tier?', owner: 'lead-pm', severity: 'high', status: 'open' },
      { id: 'OQ-02', text: 'Are regional failover SLAs contractual or best-effort?', owner: 'prd-writer', severity: 'medium', status: 'open' },
      { id: 'OQ-03', text: 'Confirm SCIM v2 adequacy vs custom provisioning.', owner: 'lead-pm', severity: 'medium', status: 'resolved' },
    ],
    phases: [
      { n: 1, name: 'DB + Repository', status: 'completed', progress: 100, tasks: [
        { id: 'FED-1.1', title: 'Migration: federation_tenants', status: 'completed', agent: 'python-backend-engineer', points: 2, batch: 1, deps: [], tokens: 12400 },
        { id: 'FED-1.2', title: 'Migration: trust_store', status: 'completed', agent: 'python-backend-engineer', points: 1, batch: 1, deps: [], tokens: 8200 },
        { id: 'FED-1.3', title: 'Tenant repository', status: 'completed', agent: 'data-layer-expert', points: 2, batch: 2, deps: ['FED-1.1'], tokens: 14800 },
      ]},
      { n: 2, name: 'Service layer', status: 'completed', progress: 100, tasks: [
        { id: 'FED-2.1', title: 'Tenant resolution service', status: 'completed', agent: 'python-backend-engineer', points: 3, batch: 1, deps: ['FED-1.3'] },
        { id: 'FED-2.2', title: 'Trust broker', status: 'completed', agent: 'python-backend-engineer', points: 3, batch: 1, deps: ['FED-1.2'] },
        { id: 'FED-2.3', title: 'Replication policy', status: 'completed', agent: 'data-layer-expert', points: 2, batch: 2, deps: ['FED-2.1', 'FED-2.2'] },
      ]},
      { n: 3, name: 'API routers', status: 'completed', progress: 100, tasks: [
        { id: 'FED-3.1', title: 'FastAPI /federation/tenants', status: 'completed', agent: 'openapi-expert', points: 2, batch: 1, deps: ['FED-2.1'] },
        { id: 'FED-3.2', title: 'Trust handshake endpoint', status: 'completed', agent: 'python-backend-engineer', points: 2, batch: 1, deps: ['FED-2.2'] },
      ]},
      { n: 4, name: 'UI surfaces', status: 'in-progress', progress: 55, tasks: [
        { id: 'FED-4.1', title: 'Federation settings page',      status: 'completed',   agent: 'ui-engineer-enhanced', points: 3, batch: 1, deps: ['FED-3.1'] },
        { id: 'FED-4.2', title: 'Trust-store inspector',         status: 'completed',   agent: 'ui-engineer-enhanced', points: 2, batch: 1, deps: ['FED-3.2'] },
        { id: 'FED-4.3', title: 'Tenant switcher in header',     status: 'in-progress', agent: 'ui-engineer-enhanced', points: 2, batch: 2, deps: ['FED-4.1'] },
        { id: 'FED-4.4', title: 'Replication health widget',     status: 'blocked',     agent: 'ui-engineer-enhanced', points: 2, batch: 2, deps: ['FED-4.2'], blocker: 'Awaiting OpenAPI contract freeze' },
        { id: 'FED-4.5', title: 'Next.js route group',           status: 'ready',       agent: 'nextjs-architecture-expert', points: 1, batch: 3, deps: ['FED-4.3', 'FED-4.4'] },
      ]},
      { n: 5, name: 'Testing', status: 'ready', progress: 0, tasks: [
        { id: 'FED-5.1', title: 'Tenant isolation integration', status: 'ready', agent: 'python-backend-engineer', points: 3, batch: 1, deps: ['FED-4.5'] },
        { id: 'FED-5.2', title: 'E2E federation handshake',     status: 'ready', agent: 'python-backend-engineer', points: 3, batch: 1, deps: ['FED-4.5'] },
      ]},
      { n: 6, name: 'Docs', status: 'ready', progress: 0, tasks: [
        { id: 'FED-6.1', title: 'Operator guide', status: 'ready', agent: 'documentation-writer', points: 2, batch: 1, deps: ['FED-5.1', 'FED-5.2'] },
      ]},
    ],
  },
  {
    id: 'planning-graph-ui',
    slug: 'planning-graph-ui',
    title: 'Planning Graph UI v2',
    category: 'features',
    owner: 'lead-pm',
    tags: ['ui', 'planning', 'M'],
    raw: 'in-progress', effective: 'in-progress', complexity: 'M',
    updated: '2026-04-19',
    artifacts: {
      specs: [
        { id: 'spec-1', status: 'ready', updated: '2026-03-28', path: 'docs/project_plans/design-specs/planning-graph-ui.md', title: 'Design spec' },
      ],
      prds: [
        { id: 'prd-1', status: 'approved', updated: '2026-04-02', path: 'docs/project_plans/PRDs/features/planning-graph-ui.md', title: 'PRD v1' },
      ],
      plans: [
        { id: 'plan-1', status: 'in-progress', updated: '2026-04-14', path: 'docs/project_plans/implementation_plans/features/planning-graph-ui.md', title: 'Graph UI plan' },
      ],
      ctxs: [
        { id: 'ctx-1', status: 'in-progress', updated: '2026-04-19', path: '.claude/worknotes/planning-graph-ui/context.md', title: 'Context notes' },
      ],
      reports: [],
    },
    spikes: [
      { id: 'SPK-03', title: 'DAG layout algorithm eval', status: 'completed', updated: '2026-03-18', path: 'docs/dev/spikes/dag-layout.md' },
    ],
    openQuestions: [
      { id: 'OQ-10', text: 'Virtualize at >200 features or always?', owner: 'ui-engineer-enhanced', severity: 'low', status: 'open' },
    ],
    phases: [
      { n: 1, name: 'Graph API', status: 'completed', progress: 100, tasks: [
        { id: 'PGU-1.1', title: 'Node/edge resolver', status: 'completed', agent: 'python-backend-engineer', points: 3, batch: 1, deps: [] },
      ]},
      { n: 2, name: 'Graph UI', status: 'in-progress', progress: 40, tasks: [
        { id: 'PGU-2.1', title: 'DAG renderer',         status: 'in-progress', agent: 'ui-engineer-enhanced', points: 3, batch: 1, deps: ['PGU-1.1'] },
        { id: 'PGU-2.2', title: 'Node detail drawer',   status: 'ready',       agent: 'ui-engineer-enhanced', points: 2, batch: 2, deps: ['PGU-2.1'] },
        { id: 'PGU-2.3', title: 'Lineage virtualization',status: 'ready',      agent: 'ui-engineer-enhanced', points: 2, batch: 2, deps: ['PGU-2.1'] },
      ]},
    ],
  },
  {
    id: 'ai-merge-suggestions',
    slug: 'ai-merge-suggestions',
    title: 'AI Merge Suggestions',
    category: 'features',
    owner: 'lead-pm',
    tags: ['ai', 'L'],
    raw: 'shaping', effective: 'shaping', complexity: 'L',
    updated: '2026-03-04',
    stale: true,
    artifacts: {
      specs: [{ id: 'spec-1', status: 'shaping', updated: '2026-03-04', path: 'docs/project_plans/design-specs/ai-merge-suggestions.md', title: 'Exploration spec' }],
      prds: [], plans: [], ctxs: [], reports: [],
    },
    spikes: [
      { id: 'SPK-04', title: 'Model latency bake-off (Haiku/Sonnet)', status: 'draft', updated: '2026-03-01', path: 'docs/dev/spikes/merge-model-bakeoff.md' },
    ],
    openQuestions: [
      { id: 'OQ-20', text: 'Minimum confidence for auto-merge?', owner: 'lead-pm', severity: 'high', status: 'open' },
      { id: 'OQ-21', text: 'Opt-in per repo or per org?', owner: 'prd-writer', severity: 'medium', status: 'open' },
    ],
    phases: [],
  },
  {
    id: 'fs-watcher-sync',
    slug: 'dvcs-fs-watcher-sync',
    title: 'FS Watcher Sync Engine',
    category: 'refactors',
    owner: 'lead-pm',
    tags: ['sync', 'ready-to-promote', 'M'],
    raw: 'ready', effective: 'ready', complexity: 'M',
    updated: '2026-04-05',
    readyToPromote: true,
    artifacts: {
      specs: [{ id: 'spec-1', status: 'ready', updated: '2026-04-05', path: 'docs/project_plans/design-specs/dvcs-fs-watcher-sync.md', title: 'FS Watcher spec' }],
      prds: [], plans: [], ctxs: [], reports: [],
    },
    spikes: [],
    openQuestions: [],
    phases: [],
  },
  {
    id: 'token-telemetry',
    slug: 'token-telemetry-dashboard',
    title: 'Token Telemetry Dashboard',
    category: 'enhancements',
    owner: 'lead-pm',
    tags: ['observability', 'S'],
    raw: 'in-progress', effective: 'completed', complexity: 'S',
    updated: '2026-04-17',
    mismatch: { kind: 'reversed', reason: 'All phases completed; raw PRD status still in-progress.' },
    artifacts: {
      specs: [{ id: 'spec-1', status: 'ready',       updated: '2026-01-12', path: 'docs/project_plans/design-specs/token-telemetry.md', title: 'Telemetry spec' }],
      prds:  [{ id: 'prd-1',  status: 'in-progress', updated: '2026-02-01', path: 'docs/project_plans/PRDs/enhancements/token-telemetry.md', title: 'Telemetry PRD' }],
      plans: [{ id: 'plan-1', status: 'completed',   updated: '2026-04-17', path: 'docs/project_plans/implementation_plans/enhancements/token-telemetry.md', title: 'Plan' }],
      ctxs:  [{ id: 'ctx-1',  status: 'completed',   updated: '2026-04-17', path: '.claude/worknotes/token-telemetry/context.md', title: 'Context' }],
      reports: [],
    },
    spikes: [],
    openQuestions: [],
    phases: [
      { n: 1, name: 'Metrics + UI', status: 'completed', progress: 100, tasks: [
        { id: 'TT-1.1', title: 'Token counter middleware', status: 'completed', agent: 'python-backend-engineer', points: 2, batch: 1, deps: [] },
        { id: 'TT-1.2', title: 'Prometheus exporter',      status: 'completed', agent: 'python-backend-engineer', points: 2, batch: 1, deps: [] },
        { id: 'TT-1.3', title: 'Dashboard panel',          status: 'completed', agent: 'ui-engineer-enhanced', points: 2, batch: 2, deps: ['TT-1.2'] },
      ]},
    ],
  },
  {
    id: 'doc-policy-v3',
    slug: 'doc-policy-spec-v3',
    title: 'Doc Policy Spec v3',
    category: 'refactors',
    owner: 'lead-pm',
    tags: ['policy', 'schema', 'M'],
    raw: 'in-progress', effective: 'blocked', complexity: 'M',
    updated: '2026-04-16',
    mismatch: { kind: 'blocked', reason: 'Phase 2 batch 2 blocked on upstream schema registry.' },
    artifacts: {
      specs: [
        { id: 'spec-1', status: 'ready',      updated: '2026-02-10', path: 'docs/project_plans/design-specs/doc-policy-v3.md', title: 'Policy v3 spec' },
        { id: 'spec-2', status: 'superseded', updated: '2025-12-04', path: 'docs/project_plans/design-specs/doc-policy-v2.md', title: 'Policy v2 (superseded)' },
      ],
      prds: [{ id: 'prd-1', status: 'approved', updated: '2026-02-18', path: 'docs/project_plans/PRDs/refactors/doc-policy-v3.md', title: 'PRD' }],
      plans: [{ id: 'plan-1', status: 'in-progress', updated: '2026-04-16', path: 'docs/project_plans/implementation_plans/refactors/doc-policy-v3.md', title: 'Migration plan' }],
      ctxs: [{ id: 'ctx-1', status: 'in-progress', updated: '2026-04-16', path: '.claude/worknotes/doc-policy-v3/context.md', title: 'Context' }],
      reports: [],
    },
    spikes: [
      { id: 'SPK-05', title: 'Schema registry contract', status: 'in-progress', updated: '2026-04-15', path: 'docs/dev/spikes/schema-registry.md' },
    ],
    openQuestions: [
      { id: 'OQ-30', text: 'Breaking change window for migration?', owner: 'lead-pm', severity: 'high', status: 'open' },
    ],
    phases: [
      { n: 1, name: 'Schema', status: 'completed', progress: 100, tasks: [
        { id: 'DP-1.1', title: 'Update 14 JSON schemas', status: 'completed', agent: 'python-backend-engineer', points: 3, batch: 1, deps: [] },
      ]},
      { n: 2, name: 'Migration', status: 'blocked', progress: 35, tasks: [
        { id: 'DP-2.1', title: 'Frontmatter migrator',  status: 'completed', agent: 'python-backend-engineer', points: 2, batch: 1, deps: ['DP-1.1'] },
        { id: 'DP-2.2', title: 'Registry integration',  status: 'blocked',   agent: 'python-backend-engineer', points: 3, batch: 2, deps: ['DP-2.1'], blocker: 'Registry API contract unresolved' },
        { id: 'DP-2.3', title: 'Validator rewrite',     status: 'blocked',   agent: 'python-backend-engineer', points: 2, batch: 2, deps: ['DP-2.2'], blocker: 'Waiting on 2.2' },
      ]},
    ],
  },
  {
    id: 'karen-agent-v2',
    slug: 'karen-agent-v2',
    title: 'Karen Reality-Check v2',
    category: 'enhancements',
    owner: 'lead-pm',
    tags: ['agents', 'review', 'S'],
    raw: 'draft', effective: 'draft', complexity: 'S',
    updated: '2026-04-12',
    artifacts: {
      specs: [{ id: 'spec-1', status: 'ready', updated: '2026-04-02', path: 'docs/project_plans/design-specs/karen-agent-v2.md', title: 'Karen v2 spec' }],
      prds:  [{ id: 'prd-1',  status: 'draft', updated: '2026-04-12', path: 'docs/project_plans/PRDs/enhancements/karen-agent-v2.md', title: 'Karen v2 PRD draft' }],
      plans: [], ctxs: [], reports: [],
    },
    spikes: [],
    openQuestions: [
      { id: 'OQ-40', text: 'Reality check runs pre- or post-validator?', owner: 'karen', severity: 'medium', status: 'open' },
    ],
    phases: [],
  },
  {
    id: 'spike-sync-arch',
    slug: 'spike-sync-architecture',
    title: 'SPIKE: Sync Architecture',
    category: 'spikes',
    owner: 'spike-writer',
    tags: ['spike', 'architecture', 'L'],
    raw: 'completed', effective: 'completed', complexity: 'L',
    updated: '2026-02-28',
    artifacts: {
      specs: [{ id: 'spec-1', status: 'completed', updated: '2026-02-28', path: 'docs/dev/architecture/spikes/sync-architecture.md', title: 'Sync arch spec' }],
      prds: [], plans: [], ctxs: [],
      reports: [{ id: 'rep-1', status: 'completed', updated: '2026-03-01', path: 'docs/project_plans/reports/investigations/sync-architecture-findings.md', title: 'Findings report' }],
    },
    spikes: [
      { id: 'SPK-00', title: 'Canonical sync arch spike', status: 'completed', updated: '2026-02-28', path: 'docs/dev/spikes/sync-architecture.md' },
    ],
    openQuestions: [],
    phases: [],
  },
  {
    id: 'cli-first-era5',
    slug: 'cli-first-orchestration',
    title: 'CLI-First Orchestration',
    category: 'refactors',
    owner: 'lead-pm',
    tags: ['tokens', 'orchestration', 'XL'],
    raw: 'completed', effective: 'completed', complexity: 'XL',
    updated: '2026-01-30',
    artifacts: {
      specs: [{ id: 'spec-1', status: 'completed', updated: '2025-12-18', path: 'docs/project_plans/design-specs/cli-first.md', title: 'CLI-first spec' }],
      prds:  [{ id: 'prd-1',  status: 'completed', updated: '2025-12-22', path: 'docs/project_plans/PRDs/refactors/cli-first.md', title: 'PRD' }],
      plans: [{ id: 'plan-1', status: 'completed', updated: '2026-01-30', path: 'docs/project_plans/implementation_plans/refactors/cli-first.md', title: 'Plan' }],
      ctxs:  [{ id: 'ctx-1',  status: 'completed', updated: '2026-01-30', path: '.claude/worknotes/cli-first/context.md', title: 'Context' }],
      reports: [{ id: 'rep-1', status: 'completed', updated: '2026-02-02', path: 'docs/project_plans/reports/post-mortems/cli-first.md', title: 'Post-mortem' }],
    },
    spikes: [],
    openQuestions: [],
    phases: [],
  },
  {
    id: 'agent-teams',
    slug: 'agent-teams-coordination',
    title: 'Agent Teams Coordination',
    category: 'features',
    owner: 'lead-pm',
    tags: ['agents', 'orchestration', 'L'],
    raw: 'approved', effective: 'approved', complexity: 'L',
    updated: '2026-04-15',
    artifacts: {
      specs: [
        { id: 'spec-1', status: 'ready', updated: '2026-03-20', path: 'docs/project_plans/design-specs/agent-teams.md', title: 'Teams coordination spec' },
        { id: 'spec-2', status: 'draft', updated: '2026-04-08', path: 'docs/project_plans/design-specs/agent-teams-protocol.md', title: 'Protocol addendum' },
      ],
      prds: [
        { id: 'prd-1', status: 'approved', updated: '2026-04-15', path: 'docs/project_plans/PRDs/features/agent-teams.md', title: 'PRD · core' },
        { id: 'prd-2', status: 'draft',    updated: '2026-04-14', path: 'docs/project_plans/PRDs/features/agent-teams-handoffs.md', title: 'PRD · handoffs' },
      ],
      plans: [
        { id: 'plan-1', status: 'draft', updated: '2026-04-15', path: 'docs/project_plans/implementation_plans/features/agent-teams.md', title: 'Orchestration plan' },
      ],
      ctxs: [], reports: [],
    },
    spikes: [
      { id: 'SPK-06', title: 'Handoff protocol: JSON vs event-sourced', status: 'in-progress', updated: '2026-04-12', path: 'docs/dev/spikes/handoff-protocol.md' },
    ],
    openQuestions: [
      { id: 'OQ-50', text: 'Do teams share worknotes or keep per-agent?', owner: 'lead-pm', severity: 'high', status: 'open' },
      { id: 'OQ-51', text: 'Limit team size or let orchestrator grow?', owner: 'lead-pm', severity: 'medium', status: 'open' },
    ],
    phases: [],
  },
];

// Trackers — deferred-work registry
const TRACKERS = [
  { id: 'T-001', title: 'DVCS future work', entries: 14, feature: 'dvcs-enterprise-federation', updated: '2026-04-17', path: 'docs/project_plans/reports/trackers/dvcs-future-work.md' },
  { id: 'T-002', title: 'Observability backlog', entries: 7, feature: null, updated: '2026-04-11', path: 'docs/project_plans/reports/trackers/observability.md' },
  { id: 'T-003', title: 'UI polish debt', entries: 22, feature: null, updated: '2026-04-03', path: 'docs/project_plans/reports/trackers/ui-polish.md' },
];

// Helpers to pick a "representative" artifact status for a feature + type
function reprStatus(list) {
  if (!list || !list.length) return null;
  // prefer in-progress > blocked > ready > approved > draft > shaping > completed
  const order = ['in-progress','blocked','ready','approved','draft','shaping','completed','superseded'];
  return list.slice().sort((a,b)=> order.indexOf(a.status) - order.indexOf(b.status))[0];
}

// Triage items synthesized from features
function buildTriage() {
  const items = [];
  for (const f of FEATURES) {
    if (f.mismatch) {
      items.push({ id: `mm-${f.id}`, kind: 'mismatch',
        severity: f.mismatch.kind === 'blocked' ? 'high' : 'medium',
        feature: f,
        title: f.mismatch.kind === 'reversed' ? `Raw status ${f.raw} but effective ${f.effective}` : `Blocked batch — ${f.mismatch.reason}`,
        reason: f.mismatch.reason, actions: ['Remediate', 'Dismiss', 'Open feature'],
      });
    }
    if (f.stale) {
      items.push({ id: `st-${f.id}`, kind: 'stale', severity: 'low', feature: f,
        title: `Shaping ${Math.round((new Date('2026-04-20') - new Date(f.updated)) / 86400000)}d without updates`,
        reason: 'Shaping > 30d, no recent commits', actions: ['Archive', 'Resume shaping', 'Open spec'],
      });
    }
    if (f.readyToPromote) {
      items.push({ id: `pr-${f.id}`, kind: 'ready', severity: 'info', feature: f,
        title: 'Ready for promotion to PRD', reason: 'Design spec reached ready state',
        actions: ['Promote to PRD', 'Assign PM', 'Open spec'],
      });
    }
    // Open questions with high severity escalate to triage
    for (const q of (f.openQuestions || [])) {
      if (q.status === 'open' && q.severity === 'high') {
        items.push({ id: `oq-${f.id}-${q.id}`, kind: 'question', severity: 'medium', feature: f,
          title: q.text, reason: `Open question · owner ${q.owner}`,
          actions: ['Resolve', 'Reassign', 'Open spec'],
        });
      }
    }
    for (const p of (f.phases || [])) {
      for (const t of (p.tasks || [])) {
        if (t.status === 'blocked') {
          items.push({ id: `bl-${f.id}-${t.id}`, kind: 'blocked', severity: 'high',
            feature: f, phase: p, task: t,
            title: `${t.id}: ${t.title}`, reason: t.blocker || 'blocked',
            actions: ['Unblock', 'Reassign', 'Open phase'],
          });
        }
      }
    }
  }
  const sevOrder = { high: 0, medium: 1, low: 2, info: 3 };
  items.sort((a, b) => (sevOrder[a.severity] - sevOrder[b.severity]));
  return items;
}

// Live agent activity — simulated orchestration state
const LIVE_AGENTS = [
  { agent: 'lead-pm',                  state: 'thinking',  task: 'Classifying incoming request', since: '2s' },
  { agent: 'ui-engineer-enhanced',     state: 'running',   task: 'FED-4.3 Tenant switcher',      since: '47s' },
  { agent: 'python-backend-engineer',  state: 'running',   task: 'DP-2.1 Frontmatter migrator',  since: '1m 12s' },
  { agent: 'task-completion-validator',state: 'idle',      task: '—',                             since: '—' },
  { agent: 'karen',                    state: 'queued',    task: 'Plan reality check · agent-teams', since: '—' },
];

// Aggregate metrics
function buildMetrics() {
  const total = FEATURES.length;
  const active   = FEATURES.filter(f => f.effective === 'in-progress').length;
  const blocked  = FEATURES.filter(f => f.effective === 'blocked').length;
  const stale    = FEATURES.filter(f => f.stale).length;
  const mismatch = FEATURES.filter(f => f.mismatch).length;
  const completed = FEATURES.filter(f => f.effective === 'completed').length;
  const readyPromo = FEATURES.filter(f => f.readyToPromote).length;
  const counts = {
    spec: FEATURES.reduce((n, f) => n + (f.artifacts?.specs?.length || 0), 0),
    spk:  FEATURES.reduce((n, f) => n + (f.spikes?.length || 0), 0),
    prd:  FEATURES.reduce((n, f) => n + (f.artifacts?.prds?.length || 0), 0),
    plan: FEATURES.reduce((n, f) => n + (f.artifacts?.plans?.length || 0), 0),
    prog: FEATURES.reduce((n, f) => n + (f.phases?.length || 0), 0),
    ctx:  FEATURES.reduce((n, f) => n + (f.artifacts?.ctxs?.length || 0), 0),
    trk:  TRACKERS.length,
    rep:  FEATURES.reduce((n, f) => n + (f.artifacts?.reports?.length || 0), 0),
  };
  const corpus = {
    completed: 814, inferred: 214, draft: 134,
    progressFolders: 175, schemas: 14, agents: 25,
    tokensSaved: 99.8, contextPerPhase: '25–30K',
  };
  return { total, active, blocked, stale, mismatch, completed, readyPromo, counts, corpus };
}

// Model color tokens — mapped in CSS
const MODELS = {
  opus:   { label: 'Opus',   color: 'var(--m-opus)' },
  sonnet: { label: 'Sonnet', color: 'var(--m-sonnet)' },
  haiku:  { label: 'Haiku',  color: 'var(--m-haiku)' },
};

// Deterministic token estimate if not provided
function tokenEstimate(task, agentModel) {
  if (typeof task.tokens === 'number') return task.tokens;
  const base = { haiku: 6000, sonnet: 11000, opus: 22000 }[agentModel] || 10000;
  return Math.round(base * (task.points || 2) * (0.7 + ((task.id?.charCodeAt(task.id.length - 1) || 50) % 60) / 100));
}

// Per-feature rollup: points, tokens (by model), task counts.
function rollupFeature(f) {
  const tasks = (f.phases || []).flatMap(p => p.tasks || []);
  let points = 0;
  const tokensByModel = { opus: 0, sonnet: 0, haiku: 0 };
  let tokens = 0;
  tasks.forEach(t => {
    points += (t.points || 0);
    const a = AGENTS[t.agent] || { model: 'sonnet' };
    // Only count tokens for completed + in-progress tasks (actuals)
    if (t.status === 'completed' || t.status === 'in-progress') {
      const est = tokenEstimate(t, a.model);
      tokensByModel[a.model] = (tokensByModel[a.model] || 0) + est;
      tokens += est;
    }
  });
  return { points, tokens, tokensByModel, taskCount: tasks.length };
}

window.APP_DATA = { ARTIFACTS, AGENTS, MODELS, FEATURES, TRACKERS, LIVE_AGENTS, buildTriage, buildMetrics, reprStatus, rollupFeature, tokenEstimate };
