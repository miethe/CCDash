import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  BookOpen,
  Bot,
  Boxes,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Code2,
  FileSearch,
  Gauge,
  GitBranch,
  Github,
  Layers3,
  LineChart,
  Network,
  PanelRight,
  Play,
  Radar,
  Route,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../lib/utils';

const assetUrl = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`;
const GITHUB_URL = 'https://github.com/miethe/CCDash';
const repoUrl = (path: string) => `${GITHUB_URL}/blob/main/${path.replace(/^\/+/, '')}`;

const navItems = [
  { label: 'Features', target: 'features' },
  { label: 'Personas', target: 'personas' },
  { label: 'Docs', target: 'docs' },
  { label: 'Deploy', target: 'deploy' },
];

const proofPoints = [
  { label: 'Agent Sessions', value: 'Claude Code + Codex', icon: Bot },
  { label: 'Traceability', value: 'tasks, docs, commits', icon: GitBranch },
  { label: 'Telemetry', value: 'cost, tokens, velocity', icon: Activity },
  { label: 'Runtime', value: 'local-first control', icon: ShieldCheck },
];

const featureViews = [
  {
    id: 'forensics',
    label: 'Session Forensics',
    icon: FileSearch,
    headline: 'Read every agent session like a delivery trace.',
    description:
      'Expand transcript blocks, correlate tool calls, inspect token flow, and isolate where work drifted before it reaches the repo.',
    stats: [
      ['Trace depth', '3-pane'],
      ['Signals', 'tools + files'],
      ['Lens', 'cost + quality'],
    ],
    callouts: ['Transcript timeline', 'Tool-call expansion', 'Session block insights', 'File impact table'],
    chart: 'timeline',
  },
  {
    id: 'planning',
    label: 'Planning Control',
    icon: Route,
    headline: 'Keep plans, features, and execution gates aligned.',
    description:
      'Move from PRD to implementation with dependency-aware views, live agent rosters, and evidence-backed feature status.',
    stats: [
      ['Artifacts', 'PRD / RFC / plan'],
      ['Flow', 'dependency DAG'],
      ['State', 'ready / blocked'],
    ],
    callouts: ['Planning graph', 'Feature drawer', 'Blocked-by chips', 'Execution gate summary'],
    chart: 'lanes',
  },
  {
    id: 'workflow',
    label: 'Workflow Intelligence',
    icon: Workflow,
    headline: 'Rank workflows by what actually worked.',
    description:
      'Compare workflow effectiveness, recurring failure modes, representative sessions, and stack recommendations from observed runs.',
    stats: [
      ['Ranking', 'success + risk'],
      ['Patterns', 'clustered failures'],
      ['Action', 'registry handoff'],
    ],
    callouts: ['Leaderboard', 'Failure clustering', 'SkillMeat resolution', 'AAR generation'],
    chart: 'leaderboard',
  },
  {
    id: 'execution',
    label: 'Execution Workbench',
    icon: Terminal,
    headline: 'Launch agent work with a visible safety pipeline.',
    description:
      'Review commands, choose runtime profiles, inspect stack recommendations, and keep run output attached to the feature context.',
    stats: [
      ['Controls', 'allow / review / deny'],
      ['Output', 'streamed'],
      ['Context', 'feature-scoped'],
    ],
    callouts: ['Pre-run review', 'Command policy', 'Run history', 'Recommended stack'],
    chart: 'pipeline',
  },
];

const personas = [
  {
    id: 'maintainer',
    label: 'Maintainers',
    icon: Github,
    title: 'See what changed, why it changed, and which session owns the evidence.',
    points: ['Map session output to files and docs', 'Review cost and velocity before merging', 'Open local files and linked plans quickly'],
  },
  {
    id: 'agent-operator',
    label: 'Agent Operators',
    icon: Radar,
    title: 'Run agents with guardrails instead of chasing logs after the fact.',
    points: ['Preflight commands and runtime context', 'Detect blocked work before a run starts', 'Compare workflows from observed outcomes'],
  },
  {
    id: 'engineering-lead',
    label: 'Engineering Leads',
    icon: LineChart,
    title: 'Turn AI delivery activity into project intelligence.',
    points: ['Track token spend against delivery motion', 'Spot workflow churn and quality risk', 'Generate after-action reports from real sessions'],
  },
];

const docsLinks = [
  { title: 'Quickstart', body: 'Install dependencies and run the full local stack.', href: repoUrl('docs/guides/setup.md'), icon: Play },
  { title: 'Operator Guides', body: 'Execution, telemetry, planning, and session intelligence guides.', href: repoUrl('docs/README.md'), icon: BookOpen },
  { title: 'CLI', body: 'Use CCDash from scripts, terminals, and automation.', href: repoUrl('docs/guides/standalone-cli-guide.md'), icon: Terminal },
  { title: 'MCP/API', body: 'Query project status, forensics, workflow diagnostics, and AARs.', href: repoUrl('docs/guides/agent-query-surfaces-guide.md'), icon: Code2 },
  { title: 'Architecture', body: 'Understand data domains, runtime profiles, and integrations.', href: repoUrl('docs/guides/data-domain-ownership-matrix.md'), icon: Layers3 },
];

const intelligenceCards: Array<{ title: string; body: string; icon: LucideIcon }> = [
  {
    title: 'Evidence graph',
    body: 'Connect docs, features, files, sessions, and workflow identity.',
    icon: Network,
  },
  {
    title: 'Cost intelligence',
    body: 'Attribute model IO, cache input, and observed workload to delivery motion.',
    icon: CircleDollarSign,
  },
  {
    title: 'Quality gates',
    body: 'Surface blocked work, testing context, and approval-required commands.',
    icon: ShieldCheck,
  },
  {
    title: 'Delivery analytics',
    body: 'Rank workflow families by success, efficiency, quality, and risk.',
    icon: Gauge,
  },
];

const ViewGraph = ({ type }: { type: string }) => {
  if (type === 'lanes') {
    return (
      <div className="grid h-full grid-cols-4 gap-3">
        {['Spec', 'Plan', 'Build', 'Verify'].map((lane, laneIndex) => (
          <div key={lane} className="flex min-h-0 flex-col rounded-lg border border-slate-700/70 bg-slate-950/55 p-3">
            <span className="mb-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">{lane}</span>
            {[0, 1, 2].map((item) => (
              <div
                key={item}
                className={cn(
                  'mb-2 h-10 rounded-md border bg-slate-900/90',
                  laneIndex === 2 && item === 1 ? 'border-cyan-400/70 shadow-[0_0_22px_rgba(34,211,238,0.12)]' : 'border-slate-700/60',
                )}
              />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (type === 'leaderboard') {
    return (
      <div className="space-y-3">
        {[
          ['spec-to-implementation', '91%', 'bg-emerald-400'],
          ['execution-workbench', '84%', 'bg-cyan-400'],
          ['workflow-registry', '73%', 'bg-amber-400'],
          ['session-repair', '68%', 'bg-violet-400'],
        ].map(([name, score, color]) => (
          <div key={name} className="rounded-lg border border-slate-700/70 bg-slate-950/60 p-3">
            <div className="mb-2 flex items-center justify-between gap-4 text-xs">
              <span className="font-medium text-slate-200">{name}</span>
              <span className="font-mono text-slate-400">{score}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div className={cn('h-full rounded-full', color)} style={{ width: score }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (type === 'pipeline') {
    return (
      <div className="flex h-full flex-col justify-center gap-4">
        {[
          ['context', 'ready', 'border-cyan-400/50'],
          ['policy', 'review', 'border-amber-400/60'],
          ['run output', 'streaming', 'border-emerald-400/50'],
        ].map(([title, status, border], index) => (
          <div key={title} className="relative rounded-lg border border-slate-700/70 bg-slate-950/70 p-4">
            {index < 2 && <div className="absolute left-7 top-full h-4 w-px bg-slate-700" />}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className={cn('flex h-7 w-7 items-center justify-center rounded-md border bg-slate-900', border)}>
                  <CheckCircle2 className="h-4 w-4 text-cyan-300" />
                </span>
                <span className="text-sm font-medium text-slate-100">{title}</span>
              </div>
              <span className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
                {status}
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="relative h-full overflow-hidden rounded-lg border border-slate-700/60 bg-slate-950/70 p-4">
      <div className="absolute inset-x-4 top-1/2 h-px bg-cyan-400/25" />
      <div className="absolute inset-y-4 left-1/3 w-px bg-slate-700/60" />
      <div className="absolute inset-y-4 left-2/3 w-px bg-slate-700/60" />
      {[18, 32, 48, 64, 78].map((left, index) => (
        <div
          key={left}
          className="absolute top-[calc(50%-5px)] h-2.5 w-2.5 rounded-full border border-cyan-300 bg-slate-950 shadow-[0_0_18px_rgba(34,211,238,0.5)]"
          style={{ left: `${left}%` }}
        />
      ))}
      <div className="absolute bottom-4 left-4 right-4 grid grid-cols-10 items-end gap-1.5">
        {[28, 44, 35, 64, 58, 80, 52, 68, 47, 76].map((height, index) => (
          <div
            key={index}
            className={cn('rounded-t-sm', index % 3 === 0 ? 'bg-cyan-400' : index % 3 === 1 ? 'bg-blue-500' : 'bg-indigo-500')}
            style={{ height }}
          />
        ))}
      </div>
    </div>
  );
};

export const LandingPage: React.FC = () => {
  const [activeViewId, setActiveViewId] = useState(featureViews[0].id);
  const [activePersonaId, setActivePersonaId] = useState(personas[0].id);

  const activeView = useMemo(
    () => featureViews.find((view) => view.id === activeViewId) ?? featureViews[0],
    [activeViewId],
  );
  const activePersona = useMemo(
    () => personas.find((persona) => persona.id === activePersonaId) ?? personas[0],
    [activePersonaId],
  );

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="h-screen overflow-y-auto bg-[#f7f9fc] text-slate-950 antialiased">
      <section className="relative min-h-[92vh] overflow-hidden bg-[#030814] text-white">
        <img
          src={assetUrl('/branding/ccdash-telemetry-background.png')}
          alt=""
          className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-35"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(3,8,20,0.98)_0%,rgba(3,8,20,0.88)_44%,rgba(3,8,20,0.64)_100%)]" />
        <div className="relative mx-auto flex min-h-[92vh] max-w-7xl flex-col px-5 sm:px-6 lg:px-8">
          <header className="flex items-center justify-between border-b border-white/10 py-5">
            <Link to="/" className="flex items-center gap-3">
              <img src={assetUrl('/branding/ccdash-app-icon.png')} alt="" className="h-9 w-9 object-contain" />
              <span className="text-lg font-semibold tracking-tight">CCDash</span>
            </Link>
            <nav className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
              {navItems.map((item) => (
                <button key={item.target} type="button" onClick={() => scrollTo(item.target)} className="transition hover:text-white">
                  {item.label}
                </button>
              ))}
            </nav>
            <div className="flex items-center gap-2">
              <a
                href={GITHUB_URL}
                className="hidden h-9 items-center gap-2 rounded-lg border border-white/15 px-3 text-sm text-slate-200 transition hover:border-cyan-300/50 hover:text-white sm:inline-flex"
              >
                <Github className="h-4 w-4" />
                GitHub
              </a>
              <Link
                to="/dashboard"
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-white px-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-100"
              >
                Open app
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </header>

          <div className="grid flex-1 items-center gap-12 py-16 lg:grid-cols-[0.92fr_1.08fr] lg:py-20">
            <div className="max-w-3xl">
              <div className="mb-7 inline-flex items-center gap-2 rounded-lg border border-cyan-300/25 bg-cyan-300/8 px-3 py-1.5 text-sm text-cyan-100">
                <Sparkles className="h-4 w-4 text-cyan-300" />
                Local-first observability for agentic delivery
              </div>
              <h1 className="max-w-4xl text-5xl font-semibold leading-[0.95] tracking-tight text-white sm:text-6xl lg:text-7xl">
                Observe agent work. Ship with evidence.
              </h1>
              <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300">
                CCDash turns Claude Code and Codex sessions into a project control plane: trace work from plan to commit, understand token spend, and compare workflows against real delivery outcomes.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link
                  to="/dashboard"
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-cyan-300 px-5 text-sm font-semibold text-slate-950 shadow-[0_0_32px_rgba(34,211,238,0.25)] transition hover:bg-cyan-200"
                >
                  Open dashboard
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <a
                  href={repoUrl('docs/README.md')}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-5 text-sm font-semibold text-white transition hover:border-cyan-300/60 hover:bg-white/10"
                >
                  Read docs
                  <BookOpen className="h-4 w-4" />
                </a>
              </div>
              <div className="mt-9 grid gap-3 sm:grid-cols-2">
                {proofPoints.map((point) => (
                  <div key={point.label} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                    <point.icon className="mb-3 h-5 w-5 text-cyan-300" />
                    <div className="text-sm font-semibold text-white">{point.label}</div>
                    <div className="mt-1 text-sm text-slate-400">{point.value}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="absolute -left-8 top-8 hidden h-24 w-24 border-l border-t border-cyan-300/30 lg:block" />
              <div className="rounded-lg border border-white/12 bg-slate-950/72 p-3 shadow-[0_32px_120px_rgba(0,0,0,0.42)] backdrop-blur">
                <div className="flex items-center justify-between border-b border-white/10 px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
                  </div>
                  <span className="font-mono text-xs text-slate-500">ccdash.local / sessions</span>
                </div>
                <div className="grid gap-3 p-3 lg:grid-cols-[0.8fr_1.2fr]">
                  <div className="space-y-3">
                    {['Overview', 'Planning', 'Execution', 'Analytics'].map((item, index) => (
                      <div
                        key={item}
                        className={cn(
                          'flex items-center gap-3 rounded-lg border px-3 py-3 text-sm',
                          index === 1 ? 'border-cyan-400/45 bg-cyan-400/10 text-cyan-100' : 'border-slate-800 bg-slate-900/60 text-slate-400',
                        )}
                      >
                        <span className="h-7 w-7 rounded-md border border-slate-700 bg-slate-950" />
                        {item}
                      </div>
                    ))}
                  </div>
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        ['Token burn', '$18.42', 'text-cyan-200'],
                        ['Velocity', '+31%', 'text-emerald-200'],
                        ['Risk', '2 gates', 'text-amber-200'],
                      ].map(([label, value, color]) => (
                        <div key={label} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
                          <div className={cn('mt-3 text-xl font-semibold', color)}>{value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="h-52 rounded-lg border border-slate-800 bg-slate-950/70 p-4">
                      <ViewGraph type="timeline" />
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
                          <Network className="h-4 w-4 text-cyan-300" />
                          Subagent topology
                        </div>
                        <div className="grid grid-cols-4 gap-2">
                          {[0, 1, 2, 3, 4, 5, 6, 7].map((item) => (
                            <span key={item} className="h-8 rounded-md border border-slate-700 bg-slate-950" />
                          ))}
                        </div>
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
                          <CircleDollarSign className="h-4 w-4 text-emerald-300" />
                          Model allocation
                        </div>
                        <div className="space-y-2">
                          {['w-11/12 bg-cyan-400', 'w-8/12 bg-blue-500', 'w-5/12 bg-violet-400'].map((bar) => (
                            <div key={bar} className="h-2 rounded-full bg-slate-800">
                              <div className={cn('h-full rounded-full', bar)} />
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="scroll-mt-0 border-b border-slate-200 bg-white py-20">
        <div className="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr]">
            <div>
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-cyan-700">
                <PanelRight className="h-4 w-4" />
                Product views
              </div>
              <h2 className="text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
                Different routes for different decisions.
              </h2>
              <p className="mt-5 text-lg leading-8 text-slate-600">
                The landing page mirrors the app: dense where it needs to be, quiet where decisions matter, and organized around the surfaces operators actually use.
              </p>
              <div className="mt-8 grid gap-2">
                {featureViews.map((view) => (
                  <button
                    key={view.id}
                    type="button"
                    onClick={() => setActiveViewId(view.id)}
                    className={cn(
                      'flex items-center justify-between rounded-lg border p-4 text-left transition',
                      activeView.id === view.id
                        ? 'border-cyan-300 bg-cyan-50 text-slate-950 shadow-sm'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50',
                    )}
                  >
                    <span className="flex items-center gap-3">
                      <view.icon className={cn('h-5 w-5', activeView.id === view.id ? 'text-cyan-700' : 'text-slate-400')} />
                      <span className="font-semibold">{view.label}</span>
                    </span>
                    <ChevronRight className="h-4 w-4" />
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-950 p-4 text-white shadow-xl shadow-slate-200/70">
              <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-5">
                  <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-lg border border-cyan-400/45 bg-cyan-400/10">
                    <activeView.icon className="h-5 w-5 text-cyan-200" />
                  </div>
                  <h3 className="text-2xl font-semibold tracking-tight">{activeView.headline}</h3>
                  <p className="mt-4 leading-7 text-slate-400">{activeView.description}</p>
                  <div className="mt-6 grid grid-cols-3 gap-2">
                    {activeView.stats.map(([label, value]) => (
                      <div key={label} className="rounded-lg border border-slate-800 bg-slate-950/65 p-3">
                        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
                        <div className="mt-2 text-sm font-semibold text-slate-100">{value}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-6 space-y-2">
                    {activeView.callouts.map((callout) => (
                      <div key={callout} className="flex items-center gap-2 text-sm text-slate-300">
                        <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                        {callout}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="min-h-[380px] rounded-lg border border-slate-800 bg-slate-900/55 p-4">
                  <ViewGraph type={activeView.chart} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="personas" className="bg-[#f7f9fc] py-20">
        <div className="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          <div className="mb-10 flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
            <div>
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-cyan-700">
                <Boxes className="h-4 w-4" />
                Personas
              </div>
              <h2 className="text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
                Built for the people between agents and production.
              </h2>
            </div>
            <div className="flex flex-wrap gap-2">
              {personas.map((persona) => (
                <button
                  key={persona.id}
                  type="button"
                  onClick={() => setActivePersonaId(persona.id)}
                  className={cn(
                    'inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold transition',
                    activePersona.id === persona.id
                      ? 'border-slate-950 bg-slate-950 text-white'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-950',
                  )}
                >
                  <persona.icon className="h-4 w-4" />
                  {persona.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
              <activePersona.icon className="mb-6 h-8 w-8 text-cyan-700" />
              <h3 className="text-3xl font-semibold tracking-tight text-slate-950">{activePersona.title}</h3>
              <div className="mt-8 space-y-4">
                {activePersona.points.map((point) => (
                  <div key={point} className="flex items-start gap-3 text-slate-700">
                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
                    <span>{point}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {intelligenceCards.map((card) => (
                <div key={card.title} className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                  <card.icon className="mb-5 h-6 w-6 text-cyan-700" />
                  <h4 className="text-lg font-semibold text-slate-950">{card.title}</h4>
                  <p className="mt-3 leading-7 text-slate-600">{card.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="docs" className="border-y border-slate-200 bg-white py-20">
        <div className="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          <div className="mb-10 max-w-3xl">
            <div className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-cyan-700">
              <ScrollText className="h-4 w-4" />
              Documentation gateway
            </div>
            <h2 className="text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">Make the repo navigable on first visit.</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {docsLinks.map((item) => (
              <a key={item.title} href={item.href} className="group rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-300 hover:shadow-lg hover:shadow-cyan-100/50">
                <item.icon className="mb-5 h-6 w-6 text-cyan-700" />
                <h3 className="flex items-center justify-between gap-3 text-lg font-semibold text-slate-950">
                  {item.title}
                  <ArrowRight className="h-4 w-4 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-cyan-700" />
                </h3>
                <p className="mt-3 text-sm leading-6 text-slate-600">{item.body}</p>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section id="deploy" className="bg-slate-950 py-20 text-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 sm:px-6 lg:grid-cols-[0.88fr_1.12fr] lg:px-8">
          <div>
            <div className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-cyan-300">
              <GitBranch className="h-4 w-4" />
              Static hosting ready
            </div>
            <h2 className="text-4xl font-semibold tracking-tight sm:text-5xl">Designed for GitHub Pages or Cloudflare Pages.</h2>
            <p className="mt-5 text-lg leading-8 text-slate-400">
              The page runs as part of the existing Vite frontend and keeps routing hash-based, so docs links and app routes remain friendly to static hosts.
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Terminal className="h-4 w-4 text-cyan-300" />
                Start locally
              </div>
              <span className="rounded-md border border-slate-700 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
                Vite
              </span>
            </div>
            <div className="space-y-3 font-mono text-sm">
              {['npm install', 'npm run setup', 'npm run dev', 'npm run build'].map((command) => (
                <div key={command} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950 px-4 py-3 text-slate-300">
                  <span className="text-cyan-300">$</span>
                  {command}
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row">
              <Link to="/dashboard" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-cyan-300 px-4 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200">
                Open app route
                <ArrowRight className="h-4 w-4" />
              </Link>
              <a href={repoUrl('README.md')} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-700 px-4 text-sm font-semibold text-slate-200 transition hover:border-cyan-300/60 hover:text-white">
                Repo README
                <BookOpen className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
