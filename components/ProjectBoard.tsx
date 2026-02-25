
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useData } from '../contexts/DataContext';
import { Feature, FeaturePhase, LinkedDocument, PlanDocument, ProjectTask, SessionModelInfo } from '../types';
import { SessionCard, SessionCardDetailSection, deriveSessionCardTitle } from './SessionCard';
import { DocumentModal } from './DocumentModal';
import { SidebarFiltersPortal, SidebarFiltersSection } from './SidebarFilters';
import {
  X, FileText, Calendar, ChevronRight, ChevronDown, LayoutGrid, List,
  Search, Filter, CheckCircle2, Circle, CircleDashed, Layers, Box,
  FolderOpen, ExternalLink, Tag, ClipboardList, BarChart3, RefreshCw,
  Terminal, GitCommit,
} from 'lucide-react';
import { FEATURE_STATUS_OPTIONS, getFeatureStatusStyle } from './featureStatus';

interface FeatureSessionLink {
  sessionId: string;
  title?: string;
  titleSource?: string;
  titleConfidence?: number;
  confidence: number;
  reasons: string[];
  commands: string[];
  commitHashes: string[];
  status: string;
  model: string;
  modelDisplayName?: string;
  modelProvider?: string;
  modelFamily?: string;
  modelVersion?: string;
  modelsUsed?: SessionModelInfo[];
  agentsUsed?: string[];
  skillsUsed?: string[];
  toolSummary?: string[];
  startedAt: string;
  endedAt?: string;
  createdAt?: string;
  updatedAt?: string;
  totalCost: number;
  durationSeconds: number;
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  sessionType?: string;
  parentSessionId?: string | null;
  rootSessionId?: string;
  agentId?: string | null;
  isSubthread?: boolean;
  isPrimaryLink?: boolean;
  linkStrategy?: string;
  workflowType?: string;
  sessionMetadata?: {
    sessionTypeId: string;
    sessionTypeLabel: string;
    mappingId: string;
    relatedCommand: string;
    relatedPhases: string[];
    relatedFilePath?: string;
    fields: Array<{
      id: string;
      label: string;
      value: string;
    }>;
  } | null;
}

type CoreSessionGroupId = 'plan' | 'execution' | 'other';
type DocGroupId = 'initialPlanning' | 'prd' | 'plans' | 'progress' | 'context';

interface CoreSessionGroupDefinition {
  id: CoreSessionGroupId;
  label: string;
  description: string;
}

interface DocGroupDefinition {
  id: DocGroupId;
  label: string;
  description: string;
}

interface FeatureSessionTreeNode {
  session: FeatureSessionLink;
  children: FeatureSessionTreeNode[];
}

interface FeatureSessionSummary {
  total: number;
  mainThreads: number;
  subThreads: number;
  unresolvedSubThreads: number;
  byType: Array<{ type: string; count: number }>;
}

const SHORT_COMMIT_LENGTH = 7;

const toShortCommitHash = (hash: string): string => hash.slice(0, SHORT_COMMIT_LENGTH);
const normalizePath = (value: string): string => (value || '').replace(/\\/g, '/').replace(/^\.?\//, '');
const CORE_SESSION_GROUPS: CoreSessionGroupDefinition[] = [
  {
    id: 'plan',
    label: 'Planning Sessions',
    description: 'Planning tasks, discovery, analysis, and scope definition.',
  },
  {
    id: 'execution',
    label: 'Execution Sessions',
    description: 'Implementation work, sorted by phase order.',
  },
  {
    id: 'other',
    label: 'Other Core Sessions',
    description: 'Primary linked sessions that do not fit planning or phase execution.',
  },
];
const DOC_GROUPS: DocGroupDefinition[] = [
  {
    id: 'initialPlanning',
    label: 'Initial Planning Docs',
    description: 'Reports, SPIKEs, ADRs, analysis, and discovery artifacts.',
  },
  {
    id: 'prd',
    label: 'PRD',
    description: 'Product requirements and primary feature definition docs.',
  },
  {
    id: 'plans',
    label: 'Plans',
    description: 'Implementation and phase plans.',
  },
  {
    id: 'progress',
    label: 'Progress Files',
    description: 'Phase and execution progress tracking.',
  },
  {
    id: 'context',
    label: 'Context & Worknotes',
    description: 'Additional context docs, notes, and supporting references.',
  },
];
const DEFAULT_CORE_SESSION_GROUP_EXPANDED: Record<CoreSessionGroupId, boolean> = {
  plan: true,
  execution: true,
  other: true,
};
const DEFAULT_DOC_GROUP_EXPANDED: Record<DocGroupId, boolean> = {
  initialPlanning: true,
  prd: true,
  plans: true,
  progress: true,
  context: true,
};

const formatSessionReason = (reason: string): string => {
  const normalized = (reason || '').trim();
  if (!normalized) return 'related';
  if (normalized === 'task_frontmatter') return 'task linkage';
  if (normalized === 'session_evidence') return 'session evidence';
  if (normalized === 'command_args_path') return 'command path';
  if (normalized === 'file_write') return 'file write';
  if (normalized === 'shell_reference') return 'shell reference';
  if (normalized === 'search_reference') return 'search reference';
  if (normalized === 'file_read') return 'file read';
  return normalized.replace(/_/g, ' ');
};

const isSubthreadSession = (session: FeatureSessionLink): boolean => {
  if (session.isSubthread) return true;
  if (session.parentSessionId) return true;
  return (session.sessionType || '').toLowerCase() === 'subagent';
};

const isPrimarySession = (session: FeatureSessionLink): boolean => {
  if (session.isPrimaryLink) return true;
  return session.confidence >= 0.9;
};

const parsePhaseNumber = (value: string, allowBareNumber = false): number | null => {
  const normalized = (value || '').trim();
  if (!normalized) return null;
  const phaseMatch = normalized.match(/\bphase[\s:_-]*(\d+)\b/i);
  if (phaseMatch) {
    const parsed = Number(phaseMatch[1]);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (allowBareNumber && /^\d+$/.test(normalized)) {
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const getSessionPhaseNumbers = (session: FeatureSessionLink): number[] => {
  const candidates: number[] = [];
  const relatedPhases = session.sessionMetadata?.relatedPhases || [];
  relatedPhases.forEach(phase => {
    const parsed = parsePhaseNumber(String(phase || ''), true);
    if (parsed !== null) candidates.push(parsed);
  });
  [session.title || '', ...session.commands].forEach(value => {
    const parsed = parsePhaseNumber(value, false);
    if (parsed !== null) candidates.push(parsed);
  });
  return Array.from(new Set(candidates)).sort((a, b) => a - b);
};

const getSessionPrimaryPhaseNumber = (session: FeatureSessionLink): number | null => {
  const values = getSessionPhaseNumbers(session);
  return values.length > 0 ? values[0] : null;
};

const getSessionClassificationText = (session: FeatureSessionLink): string =>
  [
    session.workflowType || '',
    session.sessionType || '',
    session.sessionMetadata?.sessionTypeLabel || '',
    session.title || '',
    ...session.reasons,
    ...session.commands,
  ]
    .join(' ')
    .toLowerCase();

const isPlanningSession = (session: FeatureSessionLink): boolean => {
  const haystack = getSessionClassificationText(session);
  const workflow = (session.workflowType || '').toLowerCase();
  if (workflow === 'planning') return true;
  return [
    '/plan:',
    'planning',
    'analysis',
    'spike',
    'adr',
    'discovery',
    'research',
    'scoping',
  ].some(token => haystack.includes(token));
};

const isExecutionSession = (session: FeatureSessionLink): boolean => {
  const workflow = (session.workflowType || '').toLowerCase();
  if (workflow === 'execution' || workflow === 'debug' || workflow === 'enhancement') return true;
  const haystack = getSessionClassificationText(session);
  if ([
    '/dev:execute-phase',
    'execute-phase',
    'execution',
    'implement',
    'implementation',
    'quick-feature',
  ].some(token => haystack.includes(token))) {
    return true;
  }
  return getSessionPrimaryPhaseNumber(session) !== null;
};

const getCoreSessionGroupId = (session: FeatureSessionLink): CoreSessionGroupId => {
  if (isPlanningSession(session)) return 'plan';
  if (isExecutionSession(session)) return 'execution';
  return 'other';
};

const sessionStartedAtValue = (session: FeatureSessionLink): number => Date.parse(session.startedAt || '') || 0;
const compareSessionsByConfidenceAndTime = (a: FeatureSessionLink, b: FeatureSessionLink): number => {
  if (b.confidence !== a.confidence) return b.confidence - a.confidence;
  return sessionStartedAtValue(b) - sessionStartedAtValue(a);
};

const compareSessionsForGroup = (groupId: CoreSessionGroupId, a: FeatureSessionLink, b: FeatureSessionLink): number => {
  if (groupId === 'execution') {
    const aPhase = getSessionPrimaryPhaseNumber(a) ?? Number.POSITIVE_INFINITY;
    const bPhase = getSessionPrimaryPhaseNumber(b) ?? Number.POSITIVE_INFINITY;
    if (aPhase !== bPhase) return aPhase - bPhase;
  }
  return compareSessionsByConfidenceAndTime(a, b);
};

const sortThreadNodes = (
  nodes: FeatureSessionTreeNode[],
  comparator: (a: FeatureSessionLink, b: FeatureSessionLink) => number,
): FeatureSessionTreeNode[] => {
  const sortedRoots = [...nodes]
    .sort((a, b) => comparator(a.session, b.session))
    .map(node => ({
      ...node,
      children: sortThreadNodes(node.children, compareSessionsByConfidenceAndTime),
    }));
  return sortedRoots;
};

const countThreadNodes = (nodes: FeatureSessionTreeNode[]): number =>
  nodes.reduce((sum, node) => sum + 1 + countThreadNodes(node.children), 0);

const buildSessionThreadForest = (sessions: FeatureSessionLink[]): FeatureSessionTreeNode[] => {
  const nodes = new Map<string, FeatureSessionTreeNode>();
  sessions.forEach(session => {
    nodes.set(session.sessionId, { session, children: [] });
  });

  const attached = new Set<string>();
  sessions.forEach(session => {
    const node = nodes.get(session.sessionId);
    if (!node || !isSubthreadSession(session)) return;

    const candidateParents = [
      session.parentSessionId || '',
      session.rootSessionId && session.rootSessionId !== session.sessionId ? session.rootSessionId : '',
    ];
    const parentId = candidateParents.find(id => !!id && nodes.has(id));
    if (!parentId || parentId === session.sessionId) return;
    const parentNode = nodes.get(parentId);
    if (!parentNode) return;
    parentNode.children.push(node);
    attached.add(session.sessionId);
  });

  const roots: FeatureSessionTreeNode[] = [];
  sessions.forEach(session => {
    if (!attached.has(session.sessionId)) {
      const node = nodes.get(session.sessionId);
      if (node) roots.push(node);
    }
  });
  return roots;
};

const sessionTypeBucketLabel = (session: FeatureSessionLink): string => {
  const workflow = (session.workflowType || '').trim();
  if (workflow) return workflow;
  const metadataLabel = (session.sessionMetadata?.sessionTypeLabel || '').trim();
  if (metadataLabel) return metadataLabel;
  const sessionType = (session.sessionType || '').trim();
  if (sessionType) return sessionType === 'subagent' ? 'Sub-thread' : sessionType;
  return 'Other';
};

const buildFeatureSessionSummary = (sessions: FeatureSessionLink[]): FeatureSessionSummary => {
  const typeCounts = new Map<string, number>();
  const idSet = new Set(sessions.map(session => session.sessionId));
  let mainThreads = 0;
  let subThreads = 0;
  let unresolvedSubThreads = 0;

  sessions.forEach(session => {
    const typeLabel = sessionTypeBucketLabel(session);
    typeCounts.set(typeLabel, (typeCounts.get(typeLabel) || 0) + 1);

    if (isSubthreadSession(session)) {
      subThreads += 1;
      const parentId = session.parentSessionId || '';
      const rootId = session.rootSessionId || '';
      const hasKnownMain = (!!parentId && idSet.has(parentId)) || (!!rootId && rootId !== session.sessionId && idSet.has(rootId));
      if (!hasKnownMain) unresolvedSubThreads += 1;
    } else {
      mainThreads += 1;
    }
  });

  const byType = Array.from(typeCounts.entries())
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));

  return {
    total: sessions.length,
    mainThreads,
    subThreads,
    unresolvedSubThreads,
    byType,
  };
};

const getDocumentClassificationText = (doc: LinkedDocument): string =>
  [doc.docType || '', doc.title || '', doc.filePath || '', doc.category || ''].join(' ').toLowerCase();

const isInitialPlanningDoc = (doc: LinkedDocument): boolean => {
  const type = (doc.docType || '').toLowerCase();
  const haystack = getDocumentClassificationText(doc);
  if (type === 'report') return true;
  if ([
    'spike',
    'adr',
    'analysis',
    'discovery',
    'research',
    'investigation',
    'architecture decision',
  ].some(token => haystack.includes(token))) {
    return true;
  }
  return type === 'spec';
};

const getDocGroupId = (doc: LinkedDocument): DocGroupId => {
  const type = (doc.docType || '').toLowerCase();
  if (isInitialPlanningDoc(doc)) return 'initialPlanning';
  if (type === 'prd') return 'prd';
  if (type === 'implementation_plan' || type === 'phase_plan') return 'plans';
  if (type === 'progress' || normalizePath(doc.filePath).toLowerCase().includes('/progress/')) return 'progress';
  return 'context';
};

const getDocPhaseNumber = (doc: LinkedDocument): number | null => {
  const fromTitle = parsePhaseNumber(doc.title || '', false);
  if (fromTitle !== null) return fromTitle;
  return parsePhaseNumber(doc.filePath || '', false);
};

const compareDocsByTitle = (a: LinkedDocument, b: LinkedDocument): number => {
  const titleDiff = (a.title || '').localeCompare((b.title || ''), undefined, { numeric: true, sensitivity: 'base' });
  if (titleDiff !== 0) return titleDiff;
  return normalizePath(a.filePath || '').localeCompare(normalizePath(b.filePath || ''), undefined, { numeric: true, sensitivity: 'base' });
};

const initialPlanningDocPriority = (doc: LinkedDocument): number => {
  const haystack = getDocumentClassificationText(doc);
  if (haystack.includes('adr') || haystack.includes('architecture decision')) return 0;
  if (haystack.includes('spike')) return 1;
  if (haystack.includes('report')) return 2;
  if (haystack.includes('analysis') || haystack.includes('discovery') || haystack.includes('research')) return 3;
  if ((doc.docType || '').toLowerCase() === 'spec') return 4;
  return 5;
};

const sortDocsWithinGroup = (groupId: DocGroupId, docs: LinkedDocument[]): LinkedDocument[] => {
  return [...docs].sort((a, b) => {
    if (groupId === 'initialPlanning') {
      const priorityDiff = initialPlanningDocPriority(a) - initialPlanningDocPriority(b);
      if (priorityDiff !== 0) return priorityDiff;
    }
    if (groupId === 'plans' || groupId === 'progress') {
      const aPhase = getDocPhaseNumber(a) ?? Number.POSITIVE_INFINITY;
      const bPhase = getDocPhaseNumber(b) ?? Number.POSITIVE_INFINITY;
      if (aPhase !== bPhase) return aPhase - bPhase;
    }
    return compareDocsByTitle(a, b);
  });
};

// ── Status helpers ─────────────────────────────────────────────────
const getStatusStyle = getFeatureStatusStyle;
const TERMINAL_PHASE_STATUSES = new Set(['done', 'deferred']);

const getPhaseDeferredCount = (phase: FeaturePhase): number => Math.max(phase.deferredTasks || 0, 0);

const getPhaseCompletedCount = (phase: FeaturePhase): number => {
  const completed = Math.max(phase.completedTasks || 0, 0);
  return Math.max(completed, getPhaseDeferredCount(phase));
};

const getFeatureDeferredCount = (feature: Feature): number => {
  if (typeof feature.deferredTasks === 'number') return Math.max(feature.deferredTasks, 0);
  return (feature.phases || []).reduce((sum, phase) => sum + getPhaseDeferredCount(phase), 0);
};

const getFeatureCompletedCount = (feature: Feature): number => {
  const completed = Math.max(feature.completedTasks || 0, 0);
  return Math.max(completed, getFeatureDeferredCount(feature));
};

const hasDeferredCaveat = (feature: Feature): boolean =>
  feature.status === 'deferred' || getFeatureDeferredCount(feature) > 0;

const aggregateFeatureFromPhases = (feature: Feature, phases: FeaturePhase[]): Feature => {
  const normalizedPhases = phases.map(phase => {
    const total = Math.max(phase.totalTasks || 0, (phase.tasks || []).length);
    let deferred = Math.max(phase.deferredTasks || 0, 0);
    let completed = Math.max(phase.completedTasks || 0, 0);
    if (phase.tasks && phase.tasks.length > 0) {
      const doneCount = phase.tasks.filter(task => task.status === 'done').length;
      deferred = phase.tasks.filter(task => task.status === 'deferred').length;
      completed = doneCount + deferred;
    }
    if (phase.status === 'deferred' && total > 0) {
      completed = total;
      deferred = total;
    }
    if (total > 0 && completed > total) completed = total;
    if (deferred > completed) deferred = completed;
    return { ...phase, totalTasks: total, completedTasks: completed, deferredTasks: deferred };
  });

  const totalTasks = normalizedPhases.reduce((sum, phase) => sum + Math.max(phase.totalTasks || 0, 0), 0);
  const completedTasks = normalizedPhases.reduce((sum, phase) => sum + getPhaseCompletedCount(phase), 0);
  const deferredTasks = normalizedPhases.reduce((sum, phase) => sum + getPhaseDeferredCount(phase), 0);
  const allTerminal = normalizedPhases.length > 0 && normalizedPhases.every(phase => TERMINAL_PHASE_STATUSES.has(phase.status));
  const anyInProgress = normalizedPhases.some(phase => phase.status === 'in-progress');
  const anyReview = normalizedPhases.some(phase => phase.status === 'review');

  const status = totalTasks > 0 && completedTasks >= totalTasks
    ? 'done'
    : allTerminal
      ? 'done'
      : anyInProgress
        ? 'in-progress'
        : anyReview
          ? 'review'
          : 'backlog';

  return {
    ...feature,
    status,
    phases: normalizedPhases,
    totalTasks,
    completedTasks,
    deferredTasks,
  };
};

const syncDetailFeatureWithLiveFeature = (detail: Feature, liveFeature: Feature): Feature => {
  const livePhasesByKey = new Map<string, FeaturePhase>();
  (liveFeature.phases || []).forEach(phase => {
    if (phase.id) livePhasesByKey.set(phase.id, phase);
    livePhasesByKey.set(phase.phase, phase);
  });

  const phases = (detail.phases || []).map(phase => {
    const live = (phase.id && livePhasesByKey.get(phase.id)) || livePhasesByKey.get(phase.phase);
    if (!live) return phase;
    return {
      ...phase,
      status: live.status,
      progress: live.progress,
      totalTasks: live.totalTasks,
      completedTasks: live.completedTasks,
      deferredTasks: live.deferredTasks,
    };
  });

  return {
    ...detail,
    status: liveFeature.status,
    totalTasks: liveFeature.totalTasks,
    completedTasks: liveFeature.completedTasks,
    deferredTasks: liveFeature.deferredTasks,
    updatedAt: liveFeature.updatedAt,
    phases,
  };
};

const getFeatureBoardStage = (feature: Feature): string => {
  if (feature.status === 'deferred') return 'done';
  return feature.status;
};

const getFeatureBaseSlug = (featureId: string): string =>
  featureId.toLowerCase().replace(/-v\d+(?:\.\d+)?$/, '');

const toEpoch = (value?: string): number => {
  const parsed = Date.parse(value || '');
  return Number.isNaN(parsed) ? 0 : parsed;
};

const inDateRange = (value: string, from?: string, to?: string): boolean => {
  if (!from && !to) return true;
  const target = toEpoch(value);
  if (!target) return false;
  const fromEpoch = from ? toEpoch(from) : 0;
  const toEpochValue = to ? toEpoch(to) + 86_399_000 : Number.POSITIVE_INFINITY;
  return target >= fromEpoch && target <= toEpochValue;
};

const getFeatureDateValue = (
  feature: Feature,
  key: 'plannedAt' | 'startedAt' | 'completedAt' | 'updatedAt' | 'lastActivityAt',
): { value: string; confidence?: string } => {
  const fromDates = feature.dates?.[key];
  if (fromDates?.value) return { value: fromDates.value, confidence: fromDates.confidence };
  if (key === 'plannedAt') return { value: feature.plannedAt || '' };
  if (key === 'startedAt') return { value: feature.startedAt || '' };
  if (key === 'completedAt') return { value: feature.completedAt || '' };
  if (key === 'updatedAt' || key === 'lastActivityAt') return { value: feature.updatedAt || '' };
  return { value: '' };
};

const getFeaturePrimaryDate = (feature: Feature): { label: string; value: string; confidence?: string } => {
  const stage = getFeatureBoardStage(feature);
  if (stage === 'backlog') {
    const planned = getFeatureDateValue(feature, 'plannedAt');
    if (planned.value) return { label: 'Planned', ...planned };
  }
  if (stage === 'in-progress' || stage === 'review') {
    const started = getFeatureDateValue(feature, 'startedAt');
    if (started.value) return { label: 'Started', ...started };
  }
  if (stage === 'done') {
    const completed = getFeatureDateValue(feature, 'completedAt');
    if (completed.value) return { label: 'Completed', ...completed };
  }
  const updated = getFeatureDateValue(feature, 'updatedAt');
  return { label: 'Updated', ...updated };
};

const ProgressBar = ({
  completed,
  deferred = 0,
  total,
}: {
  completed: number;
  deferred?: number;
  total: number;
}) => {
  const safeTotal = Math.max(total || 0, 0);
  const safeCompleted = Math.max(completed || 0, 0);
  const safeDeferred = Math.min(Math.max(deferred || 0, 0), safeCompleted);
  const doneCount = Math.max(safeCompleted - safeDeferred, 0);
  const pct = safeTotal > 0 ? Math.round((safeCompleted / safeTotal) * 100) : 0;
  const donePct = safeTotal > 0 ? (doneCount / safeTotal) * 100 : 0;
  const deferredPct = safeTotal > 0 ? (safeDeferred / safeTotal) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        {pct > 0 ? (
          <div className="h-full w-full flex rounded-full overflow-hidden">
            {donePct > 0 && <div className="h-full bg-emerald-500 transition-all" style={{ width: `${donePct}%` }} />}
            {deferredPct > 0 && <div className="h-full bg-amber-400 transition-all" style={{ width: `${deferredPct}%` }} />}
          </div>
        ) : (
          <div className="h-full bg-slate-700 transition-all" style={{ width: '100%' }} />
        )}
      </div>
      <span className="text-[10px] text-slate-500 font-mono min-w-[64px] text-right">
        {safeCompleted}/{safeTotal}
      </span>
    </div>
  );
};

const DocTypeIcon = ({ docType }: { docType: string }) => {
  switch (docType) {
    case 'prd': return <ClipboardList size={12} className="text-purple-400" />;
    case 'implementation_plan': return <Layers size={12} className="text-blue-400" />;
    case 'phase_plan': return <FileText size={12} className="text-amber-400" />;
    case 'progress': return <Terminal size={12} className="text-cyan-400" />;
    case 'report': return <BarChart3 size={12} className="text-emerald-400" />;
    default: return <FileText size={12} className="text-slate-400" />;
  }
};

const DocTypeBadge = ({ docType }: { docType: string }) => {
  const labels: Record<string, string> = {
    prd: 'PRD',
    implementation_plan: 'Plan',
    phase_plan: 'Phase',
    progress: 'Progress',
    report: 'Report',
    spec: 'Spec',
  };
  return <span className="text-[9px] uppercase font-bold">{labels[docType] || docType}</span>;
};

// ── Status Dropdown ────────────────────────────────────────────────

const StatusDropdown = ({
  status,
  onStatusChange,
  size = 'sm',
}: {
  status: string;
  onStatusChange: (newStatus: string) => void;
  size?: 'sm' | 'xs';
}) => {
  const style = getStatusStyle(status);
  const sizeClasses = size === 'xs' ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2 py-1';

  return (
    <select
      value={status}
      onChange={(e) => {
        e.stopPropagation();
        onStatusChange(e.target.value);
      }}
      onClick={(e) => e.stopPropagation()}
      className={`font-bold uppercase rounded cursor-pointer border-0 appearance-none ${sizeClasses} ${style.color} bg-transparent hover:ring-1 hover:ring-slate-600 focus:ring-1 focus:ring-indigo-500 focus:outline-none transition-all`}
      style={{ WebkitAppearance: 'none' }}
    >
      {FEATURE_STATUS_OPTIONS.map(s => (
        <option key={s} value={s} className="bg-slate-900 text-slate-300">
          {getStatusStyle(s).label}
        </option>
      ))}
    </select>
  );
};

// ── Task Source Dialog ─────────────────────────────────────────────

const TaskSourceDialog = ({ task, onClose }: { task: ProjectTask; onClose: () => void }) => {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!task.sourceFile) {
      setError('No source file linked to this task.');
      setLoading(false);
      return;
    }
    fetch(`/api/features/task-source?file=${encodeURIComponent(task.sourceFile)}`)
      .then(r => {
        if (!r.ok) throw new Error(`Failed to load (${r.status})`);
        return r.json();
      })
      .then(data => { setContent(data.content); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [task.sourceFile]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-3xl h-[70vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-950">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2 truncate">
              <FileText size={16} className="text-indigo-400 flex-shrink-0" />
              {task.title}
            </h3>
            <div className="flex items-center gap-3 mt-1">
              <span className="font-mono text-[10px] text-slate-500">{task.id}</span>
              {task.sourceFile && (
                <span className="text-[10px] text-slate-600 font-mono truncate flex items-center gap-1">
                  <FolderOpen size={10} />
                  {task.sourceFile}
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors p-1">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">
          {loading && (
            <div className="flex items-center justify-center h-full text-slate-500">
              <RefreshCw size={20} className="animate-spin mr-2" /> Loading source file…
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <FileText size={32} className="mb-3 opacity-30" />
              <p className="text-sm">{error}</p>
            </div>
          )}
          {content && (
            <pre className="text-sm text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">{content}</pre>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Feature Detail Modal ───────────────────────────────────────────

const FeatureModal = ({
  feature,
  onClose,
}: {
  feature: Feature;
  onClose: () => void;
}) => {
  const navigate = useNavigate();
  const { updateFeatureStatus, updatePhaseStatus, updateTaskStatus, documents } = useData();
  const [activeTab, setActiveTab] = useState<'overview' | 'phases' | 'docs' | 'sessions' | 'history'>('overview');
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [viewingTask, setViewingTask] = useState<ProjectTask | null>(null);
  const [viewingDoc, setViewingDoc] = useState<PlanDocument | null>(null);
  const [fullFeature, setFullFeature] = useState<Feature | null>(null);
  const [phaseStatusFilter, setPhaseStatusFilter] = useState<string>('all');
  const [taskStatusFilter, setTaskStatusFilter] = useState<string>('all');
  const [linkedSessionLinks, setLinkedSessionLinks] = useState<FeatureSessionLink[]>([]);
  const [coreSessionGroupExpanded, setCoreSessionGroupExpanded] = useState<Record<CoreSessionGroupId, boolean>>(
    () => ({ ...DEFAULT_CORE_SESSION_GROUP_EXPANDED })
  );
  const [docGroupExpanded, setDocGroupExpanded] = useState<Record<DocGroupId, boolean>>(
    () => ({ ...DEFAULT_DOC_GROUP_EXPANDED })
  );
  const [showSecondarySessions, setShowSecondarySessions] = useState(false);
  const [expandedSubthreadsBySessionId, setExpandedSubthreadsBySessionId] = useState<Set<string>>(new Set());

  const refreshFeatureDetail = useCallback(async () => {
    try {
      const res = await fetch(`/api/features/${feature.id}`);
      if (!res.ok) throw new Error(`Failed to load feature detail (${res.status})`);
      setFullFeature(await res.json());
    } catch {
      // Keep existing detail snapshot on transient failures.
    }
  }, [feature.id]);

  const refreshLinkedSessions = useCallback(async () => {
    try {
      const res = await fetch(`/api/features/${feature.id}/linked-sessions`);
      if (!res.ok) throw new Error(`Failed to load linked sessions (${res.status})`);
      const data = await res.json();
      setLinkedSessionLinks(Array.isArray(data) ? data : []);
    } catch {
      setLinkedSessionLinks([]);
    }
  }, [feature.id]);

  useEffect(() => {
    setFullFeature(null);
    setLinkedSessionLinks([]);
    setCoreSessionGroupExpanded({ ...DEFAULT_CORE_SESSION_GROUP_EXPANDED });
    setDocGroupExpanded({ ...DEFAULT_DOC_GROUP_EXPANDED });
    setShowSecondarySessions(false);
    setExpandedSubthreadsBySessionId(new Set());
    setPhaseStatusFilter('all');
    setTaskStatusFilter('all');
    setViewingDoc(null);
    refreshFeatureDetail();
    refreshLinkedSessions();
  }, [feature.id, refreshFeatureDetail, refreshLinkedSessions]);

  useEffect(() => {
    const interval = setInterval(() => {
      refreshFeatureDetail();
      refreshLinkedSessions();
    }, 5_000);
    return () => clearInterval(interval);
  }, [refreshFeatureDetail, refreshLinkedSessions]);

  const togglePhase = (phaseKey: string) => {
    setExpandedPhases(prev => {
      const next = new Set(prev);
      if (next.has(phaseKey)) next.delete(phaseKey);
      else next.add(phaseKey);
      return next;
    });
  };

  useEffect(() => {
    if (updatingStatus) return;
    setFullFeature(prev => {
      if (!prev || prev.id !== feature.id) return prev;
      return syncDetailFeatureWithLiveFeature(prev, feature);
    });
  }, [feature, updatingStatus]);

  const activeFeature = fullFeature || feature;
  const phases = activeFeature.phases || [];
  const featureDeferredTasks = getFeatureDeferredCount(activeFeature);
  const featureCompletedTasks = getFeatureCompletedCount(activeFeature);
  const featureDoneTasks = Math.max(featureCompletedTasks - featureDeferredTasks, 0);
  const pct = activeFeature.totalTasks > 0 ? Math.round((featureCompletedTasks / activeFeature.totalTasks) * 100) : 0;
  const linkedDocs = activeFeature.linkedDocs || [];
  const filteredPhases = useMemo(() => {
    return phases.filter(phase => {
      if (phaseStatusFilter !== 'all' && phase.status !== phaseStatusFilter) return false;
      if (taskStatusFilter === 'all') return true;
      return (phase.tasks || []).some(task => task.status === taskStatusFilter);
    });
  }, [phases, phaseStatusFilter, taskStatusFilter]);

  const handleFeatureStatusChange = async (newStatus: string) => {
    let previousFeatureSnapshot: Feature | null = null;
    setFullFeature(prev => {
      if (!prev || prev.id !== feature.id || prev.status === newStatus) return prev;
      previousFeatureSnapshot = prev;
      return { ...prev, status: newStatus };
    });
    setUpdatingStatus(true);
    try {
      await updateFeatureStatus(feature.id, newStatus);
    } catch (error) {
      if (previousFeatureSnapshot) {
        setFullFeature(previousFeatureSnapshot);
      }
      throw error;
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handlePhaseStatusChange = async (phaseId: string, newStatus: string) => {
    let previousFeatureSnapshot: Feature | null = null;
    setFullFeature(prev => {
      if (!prev || prev.id !== feature.id) return prev;
      const hasPhase = (prev.phases || []).some(phase => phase.phase === phaseId || phase.id === phaseId);
      if (!hasPhase) return prev;

      previousFeatureSnapshot = prev;
      const nextPhases = (prev.phases || []).map(phase => (
        phase.phase === phaseId || phase.id === phaseId
          ? { ...phase, status: newStatus }
          : phase
      ));
      return aggregateFeatureFromPhases(prev, nextPhases);
    });
    setUpdatingStatus(true);
    try {
      await updatePhaseStatus(feature.id, phaseId, newStatus);
    } catch (error) {
      if (previousFeatureSnapshot) {
        setFullFeature(previousFeatureSnapshot);
      }
      throw error;
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleTaskStatusChange = async (phaseId: string, taskId: string, newStatus: string) => {
    let previousFeatureSnapshot: Feature | null = null;
    let previousTaskStatus: string | undefined;
    setFullFeature(prev => {
      if (!prev || prev.id !== feature.id) return prev;
      let changed = false;
      const nextPhases = (prev.phases || []).map(phase => {
        if (phase.phase !== phaseId && phase.id !== phaseId) return phase;
        const nextTasks = (phase.tasks || []).map(task => {
          if (task.id !== taskId) return task;
          changed = true;
          previousTaskStatus = task.status;
          return { ...task, status: newStatus };
        });
        return { ...phase, tasks: nextTasks };
      });
      if (!changed) return prev;
      previousFeatureSnapshot = prev;
      return aggregateFeatureFromPhases(prev, nextPhases);
    });
    setUpdatingStatus(true);
    try {
      await updateTaskStatus(feature.id, phaseId, taskId, newStatus, previousTaskStatus);
    } catch (error) {
      if (previousFeatureSnapshot) {
        setFullFeature(previousFeatureSnapshot);
      }
      throw error;
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleDocClick = (doc: LinkedDocument) => {
    const docPath = normalizePath(doc.filePath);
    const matchedDoc = documents.find(candidate => (
      candidate.id === doc.id
      || candidate.canonicalPath === docPath
      || normalizePath(candidate.filePath) === docPath
    ));
    if (matchedDoc) {
      setViewingDoc(matchedDoc);
      return;
    }
    setViewingDoc({
      id: doc.id || `DOC-${docPath.replace(/\//g, '-').replace(/\.md$/i, '')}`,
      title: doc.title,
      filePath: doc.filePath,
      status: 'active',
      lastModified: '',
      author: '',
      docType: doc.docType,
      category: doc.category || '',
      pathSegments: [],
      featureCandidates: [],
      frontmatter: {
        tags: [],
      },
    });
  };

  const linkedSessions = useMemo(() => {
    return [...linkedSessionLinks].sort((a, b) => {
      if (b.confidence !== a.confidence) return b.confidence - a.confidence;
      const aTime = Date.parse(a.startedAt || '') || 0;
      const bTime = Date.parse(b.startedAt || '') || 0;
      return bTime - aTime;
    });
  }, [linkedSessionLinks]);
  const primaryFeatureDate = getFeaturePrimaryDate(activeFeature);
  const featureHistoryEvents = useMemo(() => {
    const events: Array<{
      id: string;
      timestamp: string;
      label: string;
      kind: string;
      confidence: string;
      source: string;
      description?: string;
    }> = [];

    (activeFeature.timeline || []).forEach((event, idx) => {
      if (!event || !event.timestamp) return;
      events.push({
        id: event.id || `feature-${idx}`,
        timestamp: event.timestamp,
        label: event.label || 'Feature event',
        kind: event.kind || 'feature',
        confidence: event.confidence || 'low',
        source: event.source || 'feature',
        description: event.description,
      });
    });

    linkedDocs.forEach((doc, docIndex) => {
      (doc.timeline || []).forEach((event, idx) => {
        if (!event || !event.timestamp) return;
        events.push({
          id: `${doc.id || docIndex}-${event.id || idx}`,
          timestamp: event.timestamp,
          label: `${event.label || 'Doc update'} (${doc.docType || 'doc'})`,
          kind: event.kind || 'document',
          confidence: event.confidence || 'low',
          source: event.source || `document:${doc.filePath}`,
          description: event.description,
        });
      });
    });

    linkedSessions.forEach((session) => {
      if (session.startedAt) {
        events.push({
          id: `${session.sessionId}-started`,
          timestamp: session.startedAt,
          label: `Session Started (${session.workflowType || session.sessionType || 'related'})`,
          kind: 'session_started',
          confidence: 'high',
          source: `session:${session.sessionId}`,
        });
      }
      if (session.endedAt) {
        events.push({
          id: `${session.sessionId}-completed`,
          timestamp: session.endedAt,
          label: `Session Completed (${session.workflowType || session.sessionType || 'related'})`,
          kind: 'session_completed',
          confidence: 'high',
          source: `session:${session.sessionId}`,
        });
      }
    });

    return events
      .filter(event => !!event.timestamp)
      .sort((a, b) => toEpoch(b.timestamp) - toEpoch(a.timestamp));
  }, [activeFeature.timeline, linkedDocs, linkedSessions]);

  const allSessionRoots = useMemo(
    () => buildSessionThreadForest(linkedSessions),
    [linkedSessions]
  );

  const primarySessionRoots = useMemo(
    () => allSessionRoots.filter(node => isPrimarySession(node.session)),
    [allSessionRoots]
  );

  const secondarySessionRoots = useMemo(
    () => sortThreadNodes(allSessionRoots.filter(node => !isPrimarySession(node.session)), compareSessionsByConfidenceAndTime),
    [allSessionRoots]
  );

  const primarySessionCount = useMemo(
    () => countThreadNodes(primarySessionRoots),
    [primarySessionRoots]
  );

  const secondarySessionCount = useMemo(
    () => countThreadNodes(secondarySessionRoots),
    [secondarySessionRoots]
  );

  const coreSessionGroups = useMemo(() => {
    const grouped: Record<CoreSessionGroupId, FeatureSessionTreeNode[]> = {
      plan: [],
      execution: [],
      other: [],
    };
    primarySessionRoots.forEach(root => {
      grouped[getCoreSessionGroupId(root.session)].push(root);
    });
    return CORE_SESSION_GROUPS.map(group => ({
      ...group,
      roots: sortThreadNodes(grouped[group.id], (a, b) => compareSessionsForGroup(group.id, a, b)),
      totalSessions: countThreadNodes(grouped[group.id]),
    }));
  }, [primarySessionRoots]);

  const groupedDocs = useMemo(() => {
    const grouped: Record<DocGroupId, LinkedDocument[]> = {
      initialPlanning: [],
      prd: [],
      plans: [],
      progress: [],
      context: [],
    };
    linkedDocs.forEach(doc => {
      grouped[getDocGroupId(doc)].push(doc);
    });
    return DOC_GROUPS.map(group => ({
      ...group,
      docs: sortDocsWithinGroup(group.id, grouped[group.id]),
    })).filter(group => group.docs.length > 0);
  }, [linkedDocs]);

  const orderedLinkedDocs = useMemo(
    () => groupedDocs.flatMap(group => group.docs),
    [groupedDocs]
  );

  const toggleCoreSessionGroup = (groupId: CoreSessionGroupId) => {
    setCoreSessionGroupExpanded(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const toggleDocGroup = (groupId: DocGroupId) => {
    setDocGroupExpanded(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const toggleSubthreads = (sessionId: string) => {
    setExpandedSubthreadsBySessionId(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Box },
    { id: 'phases', label: `Phases (${phases.length})`, icon: Layers },
    { id: 'docs', label: `Documents (${linkedDocs.length})`, icon: FileText },
    { id: 'sessions', label: `Sessions (${linkedSessions.length})`, icon: Terminal },
    { id: 'history', label: 'History', icon: Calendar },
  ];

  const renderSessionCard = (
    session: FeatureSessionLink,
    threadToggle?: {
      expanded: boolean;
      childCount: number;
      onToggle: () => void;
      label?: string;
    }
  ) => {
    const openSession = () => {
      onClose();
      navigate(`/sessions?session=${encodeURIComponent(session.sessionId)}`);
    };
    const relatedTasks = phases.flatMap(p =>
      p.tasks.filter(t => t.sessionId === session.sessionId).map(t => ({ phase: p, task: t }))
    );
    const primaryCommit = session.gitCommitHash || session.gitCommitHashes?.[0] || session.commitHashes?.[0];
    const threadLabel = isSubthreadSession(session) ? 'Sub-thread' : 'Main Thread';
    const linkRole = isPrimarySession(session) ? 'Primary' : 'Related';
    const workflow = (session.workflowType || '').trim() || 'Related';
    const displayTitle = deriveSessionCardTitle(session.sessionId, (session.title || '').trim(), session.sessionMetadata || null);
    const modelBadges = (session.modelsUsed && session.modelsUsed.length > 0)
      ? session.modelsUsed.map(modelInfo => ({
        raw: modelInfo.raw,
        displayName: modelInfo.modelDisplayName,
        provider: modelInfo.modelProvider,
        family: modelInfo.modelFamily,
        version: modelInfo.modelVersion,
      }))
      : [{
        raw: session.model,
        displayName: session.modelDisplayName,
        provider: session.modelProvider,
        family: session.modelFamily,
        version: session.modelVersion,
      }];
    const detailSections: SessionCardDetailSection[] = [];
    const linkSignalItems = [
      session.linkStrategy ? formatSessionReason(session.linkStrategy) : '',
      ...session.reasons.map(reason => formatSessionReason(reason)),
    ].filter(Boolean);
    if (linkSignalItems.length > 0) {
      detailSections.push({
        id: `${session.sessionId}-link-signals`,
        label: 'Link Signals',
        items: Array.from(new Set(linkSignalItems)),
      });
    }
    if (session.commands.length > 0) {
      detailSections.push({
        id: `${session.sessionId}-commands`,
        label: 'Commands',
        items: Array.from(new Set(session.commands)),
      });
    }
    const toolSummary = Array.isArray(session.toolSummary) ? session.toolSummary.filter(Boolean) : [];
    if (toolSummary.length > 0) {
      detailSections.push({
        id: `${session.sessionId}-tools`,
        label: 'Tools',
        items: toolSummary,
      });
    }

    return (
      <SessionCard
        sessionId={session.sessionId}
        title={displayTitle}
        status={session.status}
        startedAt={session.startedAt}
        endedAt={session.endedAt}
        updatedAt={session.updatedAt}
        dates={{
          startedAt: session.startedAt ? { value: session.startedAt, confidence: 'high' } : undefined,
          completedAt: session.endedAt ? { value: session.endedAt, confidence: 'high' } : undefined,
          updatedAt: session.updatedAt ? { value: session.updatedAt, confidence: 'medium' } : undefined,
        }}
        model={{
          raw: session.model,
          displayName: session.modelDisplayName,
          provider: session.modelProvider,
          family: session.modelFamily,
          version: session.modelVersion,
        }}
        models={modelBadges}
        agentBadges={session.agentsUsed || []}
        skillBadges={session.skillsUsed || []}
        detailSections={detailSections}
        metadata={session.sessionMetadata || null}
        threadToggle={threadToggle}
        onClick={openSession}
        className="rounded-lg"
        infoBadges={(
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 text-indigo-300 bg-indigo-500/10">
            {Math.round(session.confidence * 100)}% confidence
          </span>
        )}
        headerRight={(
          <div className="flex items-center gap-4 text-right">
            <div>
              <div className="text-[9px] text-slate-600 uppercase">Cost</div>
              <div className="text-xs font-mono text-emerald-400">${session.totalCost.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-[9px] text-slate-600 uppercase">Duration</div>
              <div className="text-xs font-mono text-slate-400">{Math.round(session.durationSeconds / 60)}m</div>
            </div>
            {primaryCommit && (
              <span
                title={primaryCommit}
                className="flex items-center gap-1 text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-mono"
              >
                <GitCommit size={10} />
                {toShortCommitHash(primaryCommit)}
              </span>
            )}
          </div>
        )}
      >
        <div className="mb-3 text-[10px] flex flex-wrap items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded border ${linkRole === 'Primary' ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' : 'border-slate-700 text-slate-400 bg-slate-800/60'}`}>
            {linkRole}
          </span>
          <span className={`px-1.5 py-0.5 rounded border ${threadLabel === 'Sub-thread' ? 'border-amber-500/40 text-amber-300 bg-amber-500/10' : 'border-blue-500/30 text-blue-300 bg-blue-500/10'}`}>
            {threadLabel}
          </span>
          <span className="px-1.5 py-0.5 rounded border border-purple-500/30 text-purple-300 bg-purple-500/10">
            {workflow}
          </span>
        </div>

        {relatedTasks.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-800/60">
            <div className="text-[10px] text-slate-600 uppercase font-bold mb-2">Linked Tasks</div>
            <div className="space-y-1">
              {relatedTasks.map(({ phase, task }) => (
                <div key={task.id} className="flex items-center gap-2 text-xs">
                  <span className="text-slate-600">Phase {phase.phase}</span>
                  <span className="text-slate-700">→</span>
                  <span className="font-mono text-slate-500">{task.id}</span>
                  <span className="text-slate-400 truncate">{task.title}</span>
                  <span className={`text-[9px] uppercase font-bold ml-auto ${getStatusStyle(task.status).color}`}>
                    {getStatusStyle(task.status).label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </SessionCard>
    );
  };

  const renderSessionTreeNode = (node: FeatureSessionTreeNode, depth = 0): React.ReactNode => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedSubthreadsBySessionId.has(node.session.sessionId);

    return (
      <div key={node.session.sessionId} className="space-y-2">
        {renderSessionCard(node.session, hasChildren ? {
          expanded: isExpanded,
          childCount: countThreadNodes(node.children),
          onToggle: () => toggleSubthreads(node.session.sessionId),
          label: 'Sub-Threads',
        } : undefined)}
        {hasChildren && isExpanded && (
          <div className={`mt-3 ${depth > 0 ? 'ml-2' : ''} pl-4 border-l border-slate-700/80 space-y-3`}>
            {node.children.map(child => (
              <div key={child.session.sessionId} className="relative pl-3">
                <div className="absolute left-0 top-5 w-3 border-t border-slate-700/80" />
                {renderSessionTreeNode(child, depth + 1)}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-4xl h-[80vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="p-6 border-b border-slate-800 bg-slate-900">
          <div className="flex justify-between items-start">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 truncate max-w-[200px]">{feature.id}</span>
                <StatusDropdown status={activeFeature.status} onStatusChange={handleFeatureStatusChange} />
                {updatingStatus && <RefreshCw size={14} className="text-indigo-400 animate-spin" />}
                {activeFeature.category && (
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                    {activeFeature.category}
                  </span>
                )}
                {featureDeferredTasks > 0 && (
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300">
                    Done With Deferrals
                  </span>
                )}
              </div>
              <h2 className="text-xl font-bold text-slate-100 truncate">{activeFeature.name}</h2>
              <div className="mt-2 flex items-center gap-4 text-xs text-slate-500">
                <span>{pct}% complete</span>
                <span>{featureCompletedTasks}/{activeFeature.totalTasks} tasks</span>
                {featureDeferredTasks > 0 && (
                  <span className="text-amber-300">{featureDeferredTasks} deferred</span>
                )}
                {primaryFeatureDate.value && (
                  <span className="flex items-center gap-1">
                    <Calendar size={12} />
                    {primaryFeatureDate.label}: {new Date(primaryFeatureDate.value).toLocaleDateString()}
                    {primaryFeatureDate.confidence ? ` (${primaryFeatureDate.confidence})` : ''}
                  </span>
                )}
              </div>
            </div>
            <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1 hover:bg-slate-800 rounded ml-4">
              <X size={24} />
            </button>
          </div>
          <div className="mt-3">
            <ProgressBar completed={featureCompletedTasks} deferred={featureDeferredTasks} total={activeFeature.totalTasks} />
          </div>
        </div>

        {/* Tab Nav */}
        <div className="px-6 border-b border-slate-800 bg-slate-900/50 flex gap-6">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
                }`}
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">

          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Stats Grid */}
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Total Tasks</div>
                  <div className="text-slate-100 font-bold text-2xl">{activeFeature.totalTasks}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Completed</div>
                  <div className="text-emerald-400 font-bold text-2xl">{featureDoneTasks}</div>
                  {featureDeferredTasks > 0 && (
                    <div className="text-[11px] mt-1 text-amber-300">{featureDeferredTasks} deferred</div>
                  )}
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Phases</div>
                  <div className="text-indigo-400 font-bold text-2xl">{phases.length}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Documents</div>
                  <div className="text-purple-400 font-bold text-2xl">{linkedDocs.length}</div>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                <h3 className="text-sm font-semibold text-slate-200 mb-3">Date Signals</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                  {[
                    { label: 'Planned', value: getFeatureDateValue(activeFeature, 'plannedAt') },
                    { label: 'Started', value: getFeatureDateValue(activeFeature, 'startedAt') },
                    { label: 'Completed', value: getFeatureDateValue(activeFeature, 'completedAt') },
                    { label: 'Updated', value: getFeatureDateValue(activeFeature, 'updatedAt') },
                  ].map(item => (
                    <div key={item.label} className="p-2 rounded border border-slate-800 bg-slate-950">
                      <div className="text-slate-500 uppercase">{item.label}</div>
                      <div className="text-slate-200 mt-1">
                        {item.value.value ? new Date(item.value.value).toLocaleDateString() : '-'}
                        {item.value.confidence ? ` (${item.value.confidence})` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Linked Documents — clickable */}
              {linkedDocs.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-3">Linked Documents</h3>
                  <div className="space-y-2">
                    {orderedLinkedDocs.map(doc => (
                      <button
                        key={doc.id}
                        onClick={() => handleDocClick(doc)}
                        className="w-full flex items-center gap-3 bg-slate-900 border border-slate-800 rounded-lg p-3 hover:border-indigo-500/50 hover:bg-slate-800/50 transition-all text-left group"
                      >
                        <DocTypeIcon docType={doc.docType} />
                        <span className="text-sm text-slate-300 flex-1 truncate group-hover:text-indigo-400 transition-colors">{doc.title}</span>
                        <DocTypeBadge docType={doc.docType} />
                        <ExternalLink size={12} className="text-slate-600 group-hover:text-indigo-400 transition-colors" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Related Features */}
              {activeFeature.relatedFeatures.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-3">Related Features</h3>
                  <div className="flex flex-wrap gap-2">
                    {activeFeature.relatedFeatures.map(rel => (
                      <span key={rel} className="text-xs bg-slate-800 text-indigo-400 px-2 py-1 rounded border border-slate-700">
                        {rel}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Tags */}
              {activeFeature.tags.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-3">Tags</h3>
                  <div className="flex flex-wrap gap-2">
                    {activeFeature.tags.map(tag => (
                      <span key={tag} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700 flex items-center gap-1">
                        <Tag size={10} />{tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Phases Tab */}
          {activeTab === 'phases' && (
            <div className="space-y-3">
              {phases.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-3 rounded-lg border border-slate-800 bg-slate-900/60">
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block uppercase">Phase Status</label>
                    <select
                      value={phaseStatusFilter}
                      onChange={(e) => setPhaseStatusFilter(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="all">All</option>
                      {FEATURE_STATUS_OPTIONS.map(status => (
                        <option key={`phase-filter-${status}`} value={status}>{getStatusStyle(status).label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block uppercase">Task Status</label>
                    <select
                      value={taskStatusFilter}
                      onChange={(e) => setTaskStatusFilter(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="all">All</option>
                      {FEATURE_STATUS_OPTIONS.map(status => (
                        <option key={`task-filter-${status}`} value={status}>{getStatusStyle(status).label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
              {filteredPhases.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <Layers size={32} className="mx-auto mb-3 opacity-50" />
                  <p>{phases.length === 0 ? 'No phases tracked for this feature.' : 'No phases match your filters.'}</p>
                </div>
              )}
              {filteredPhases.map(phase => {
                const phaseStatus = getStatusStyle(phase.status);
                const phaseKey = phase.id || phase.phase;
                const isExpanded = expandedPhases.has(phaseKey);
                const phaseCompletedTasks = getPhaseCompletedCount(phase);
                const phaseDeferredTasks = getPhaseDeferredCount(phase);
                const visibleTasks = taskStatusFilter === 'all'
                  ? phase.tasks
                  : phase.tasks.filter(task => task.status === taskStatusFilter);
                return (
                  <div key={phaseKey} className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                    <div className="flex items-center gap-3 p-4 hover:bg-slate-800/50 transition-colors">
                      <button
                        onClick={() => togglePhase(phaseKey)}
                        className="flex items-center gap-3 flex-1 min-w-0 text-left"
                      >
                        {isExpanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                        <div className={`w-2 h-2 rounded-full ${phaseStatus.dot}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-200">Phase {phase.phase}</span>
                            {phase.title && (
                              <span className="text-sm text-slate-400 truncate">- {phase.title}</span>
                            )}
                            {phaseDeferredTasks > 0 && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10 uppercase">
                                Deferred
                              </span>
                            )}
                          </div>
                          <div className="mt-1">
                            <ProgressBar completed={phaseCompletedTasks} deferred={phaseDeferredTasks} total={phase.totalTasks} />
                          </div>
                        </div>
                      </button>
                      <StatusDropdown
                        status={phase.status}
                        onStatusChange={(s) => handlePhaseStatusChange(phase.phase, s)}
                        size="xs"
                      />
                    </div>

                    {/* Expanded task list */}
                    {isExpanded && visibleTasks.length > 0 && (
                      <div className="border-t border-slate-800 px-4 py-3 space-y-1.5 bg-slate-950/30">
                        {visibleTasks.map(task => {
                          const normalizedStatus = (task.status || '').toLowerCase();
                          const taskDone = normalizedStatus === 'done';
                          const taskDeferred = normalizedStatus === 'deferred';
                          const nextStatus = taskDone ? 'deferred' : taskDeferred ? 'backlog' : 'done';
                          const markTitle = taskDone ? 'Mark deferred' : taskDeferred ? 'Mark backlog' : 'Mark done';
                          const taskTextClass = taskDone
                            ? 'text-slate-500 line-through'
                            : taskDeferred
                              ? 'text-amber-300/90 italic'
                              : 'text-slate-300';
                          return (
                            <div key={task.id} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-slate-900 transition-colors">
                              <button
                                onClick={() => handleTaskStatusChange(phase.phase, task.id, nextStatus)}
                                className="flex-shrink-0 hover:scale-110 transition-transform"
                                title={markTitle}
                              >
                                {taskDone ? (
                                  <CheckCircle2 size={14} className="text-emerald-500" />
                                ) : taskDeferred ? (
                                  <CircleDashed size={14} className="text-amber-400" />
                                ) : (
                                  <Circle size={14} className="text-slate-600 hover:text-indigo-400" />
                                )}
                              </button>
                              <button
                                onClick={() => setViewingTask(task)}
                                className="font-mono text-[10px] text-slate-500 w-16 flex-shrink-0 hover:text-indigo-400 transition-colors cursor-pointer text-left"
                                title="View source file"
                              >
                                {task.id}
                              </button>
                              <button
                                onClick={() => setViewingTask(task)}
                                className={`text-sm flex-1 truncate text-left hover:text-indigo-400 transition-colors ${taskTextClass}`}
                                title="View source file"
                              >
                                {task.title}
                              </button>
                              {task.commitHash && (
                                <span className="flex items-center gap-1 text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-mono flex-shrink-0" title={`Commit: ${task.commitHash}`}>
                                  <GitCommit size={10} />
                                  {task.commitHash.slice(0, 7)}
                                </span>
                              )}
                              {task.sessionId && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); onClose(); navigate(`/sessions?session=${encodeURIComponent(task.sessionId!)}`); }}
                                  className="flex items-center gap-1 text-[10px] bg-indigo-500/10 text-indigo-400 px-1.5 py-0.5 rounded border border-indigo-500/30 font-mono hover:bg-indigo-500/20 transition-colors flex-shrink-0"
                                  title="Go to session"
                                >
                                  <Terminal size={10} />
                                  {task.sessionId}
                                </button>
                              )}
                              {task.owner && (
                                <span className="text-[10px] text-slate-600 truncate max-w-[100px] flex-shrink-0">{task.owner}</span>
                              )}
                              <StatusDropdown
                                status={task.status}
                                onStatusChange={(s) => handleTaskStatusChange(phase.phase, task.id, s)}
                                size="xs"
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {isExpanded && visibleTasks.length === 0 && (
                      <div className="border-t border-slate-800 px-4 py-3 text-xs text-slate-600 italic">
                        No task details match the current task filter.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Documents Tab — clickable */}
          {activeTab === 'docs' && (
            <div className="space-y-3">
              {linkedDocs.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <FileText size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No documents linked to this feature.</p>
                </div>
              )}
              {groupedDocs.map(group => (
                <div key={group.id} className="space-y-2">
                  <button
                    onClick={() => toggleDocGroup(group.id)}
                    className="w-full flex items-center justify-between bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-left hover:border-slate-700 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
                        {docGroupExpanded[group.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        {group.label}
                      </div>
                      <p className="text-[11px] text-slate-500 mt-1">{group.description}</p>
                    </div>
                    <span className="text-[11px] text-slate-500">{group.docs.length}</span>
                  </button>

                  {docGroupExpanded[group.id] && (
                    <div className="space-y-3">
                      {group.docs.map(doc => (
                        <button
                          key={doc.id}
                          onClick={() => handleDocClick(doc)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-indigo-500/50 hover:bg-slate-800/50 transition-all text-left group"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <DocTypeIcon docType={doc.docType} />
                              <span className="text-sm font-medium text-slate-200 group-hover:text-indigo-400 transition-colors">{doc.title}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${doc.docType === 'prd' ? 'bg-purple-500/10 text-purple-400' : 'bg-blue-500/10 text-blue-400'}`}>
                                <DocTypeBadge docType={doc.docType} />
                              </span>
                              <ExternalLink size={12} className="text-slate-600 group-hover:text-indigo-400 transition-colors" />
                            </div>
                          </div>
                          <div className="text-xs text-slate-500 font-mono truncate flex items-center gap-1.5">
                            <FolderOpen size={12} />
                            {doc.filePath}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {/* Sessions Tab */}
          {activeTab === 'sessions' && (
            <div className="space-y-3">
              {linkedSessions.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <Terminal size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No sessions linked to this feature.</p>
                  <p className="text-xs mt-1 text-slate-600">No high-confidence session evidence found yet.</p>
                </div>
              )}
              {linkedSessions.length > 0 && (
                <>
                  <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-bold uppercase tracking-wider text-emerald-300">Core Focus Sessions</div>
                      <div className="text-[11px] text-emerald-200/80">
                        {primarySessionCount}
                      </div>
                    </div>
                    <p className="text-[11px] text-emerald-200/70 mt-1">Likely primary execution/planning sessions for this feature.</p>
                  </div>

                  {coreSessionGroups.map(group => (
                    <div key={group.id} className="space-y-2">
                      <button
                        onClick={() => toggleCoreSessionGroup(group.id)}
                        className="w-full flex items-center justify-between bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-left hover:border-slate-700 transition-colors"
                      >
                        <div>
                          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
                            {coreSessionGroupExpanded[group.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            {group.label}
                          </div>
                          <p className="text-[11px] text-slate-500 mt-1">{group.description}</p>
                        </div>
                        <span className="text-[11px] text-slate-500">{group.totalSessions}</span>
                      </button>

                      {coreSessionGroupExpanded[group.id] && (
                        <div className="space-y-3">
                          {group.roots.length === 0 && (
                            <div className="text-xs text-slate-600 italic px-1">
                              No sessions currently in this group.
                            </div>
                          )}
                          {group.roots.map(node => renderSessionTreeNode(node))}
                        </div>
                      )}
                    </div>
                  ))}

                  <div className="space-y-2 pt-2">
                    <button
                      onClick={() => setShowSecondarySessions(prev => !prev)}
                      className="w-full flex items-center justify-between bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-left hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                        {showSecondarySessions ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        Secondary Linkages
                      </div>
                      <span className="text-[11px] text-slate-500">{secondarySessionCount}</span>
                    </button>

                    {showSecondarySessions && (
                      <div className="space-y-3">
                        {secondarySessionRoots.length === 0 && (
                          <div className="text-xs text-slate-600 italic px-1">
                            No secondary linked sessions.
                          </div>
                        )}
                        {secondarySessionRoots.map(node => renderSessionTreeNode(node))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
          {activeTab === 'history' && (
            <div className="space-y-3">
              {featureHistoryEvents.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <Calendar size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No timeline events available yet.</p>
                </div>
              )}
              {featureHistoryEvents.length > 0 && (
                <div className="space-y-2">
                  {featureHistoryEvents.map(event => (
                    <div key={event.id} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm text-slate-200">{event.label}</div>
                        <div className="text-xs text-slate-500">
                          {new Date(event.timestamp).toLocaleString()}
                        </div>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500 flex flex-wrap items-center gap-2">
                        <span className="uppercase px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/70">
                          {event.kind}
                        </span>
                        <span className="uppercase px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/70">
                          {event.confidence}
                        </span>
                        <span className="font-mono truncate">{event.source}</span>
                      </div>
                      {event.description && (
                        <p className="mt-2 text-xs text-slate-500">{event.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Task Source Dialog */}
        {viewingTask && <TaskSourceDialog task={viewingTask} onClose={() => setViewingTask(null)} />}
        {viewingDoc && (
          <DocumentModal
            doc={viewingDoc}
            onClose={() => setViewingDoc(null)}
            onBack={() => setViewingDoc(null)}
            backLabel="Back to feature"
            zIndexClassName="z-[60]"
          />
        )}
      </div>
    </div>
  );
};

// ── Feature Card ───────────────────────────────────────────────────

const FeatureSessionIndicator = ({
  summary,
  loading,
}: {
  summary?: FeatureSessionSummary;
  loading: boolean;
}) => {
  const total = summary?.total ?? 0;
  const typeRows = (summary?.byType || []).slice(0, 5);

  return (
    <div
      className="relative group/session-indicator"
      onClick={(e) => e.stopPropagation()}
      title="Linked session summary"
    >
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-md border border-slate-700 bg-slate-900/80 text-slate-300">
        <Terminal size={11} />
        {loading ? <RefreshCw size={10} className="animate-spin" /> : total}
      </span>

      <div className="pointer-events-none absolute right-0 top-[calc(100%+8px)] w-60 rounded-lg border border-slate-700 bg-slate-950/95 shadow-2xl px-3 py-2 opacity-0 translate-y-1 group-hover/session-indicator:opacity-100 group-hover/session-indicator:translate-y-0 transition-all duration-150 z-20">
        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Linked Sessions</div>
        <div className="space-y-1 text-[11px] text-slate-300">
          <div className="flex items-center justify-between">
            <span>Total</span>
            <span className="font-mono">{total}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Main Threads</span>
            <span className="font-mono">{summary?.mainThreads ?? 0}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Sub-Threads</span>
            <span className="font-mono">{summary?.subThreads ?? 0}</span>
          </div>
          {(summary?.unresolvedSubThreads || 0) > 0 && (
            <div className="flex items-center justify-between text-amber-300">
              <span>Unresolved Sub-Threads</span>
              <span className="font-mono">{summary?.unresolvedSubThreads ?? 0}</span>
            </div>
          )}
        </div>
        {typeRows.length > 0 && (
          <div className="mt-2 pt-2 border-t border-slate-800">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Types</div>
            <div className="space-y-1">
              {typeRows.map(row => (
                <div key={row.type} className="flex items-center justify-between text-[11px] text-slate-300">
                  <span className="truncate pr-2">{row.type}</span>
                  <span className="font-mono text-slate-400">{row.count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const FeatureCard = ({
  feature,
  sessionSummary,
  sessionSummaryLoading,
  onClick,
  onStatusChange,
  onDragStart,
  onDragEnd,
  isDragging,
}: {
  feature: Feature;
  sessionSummary?: FeatureSessionSummary;
  sessionSummaryLoading: boolean;
  onClick: () => void;
  onStatusChange: (newStatus: string) => void;
  onDragStart: (featureId: string) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}) => {
  const prdDoc = feature.linkedDocs.find(d => d.docType === 'prd');
  const planDoc = feature.linkedDocs.find(d => d.docType === 'implementation_plan');
  const featureDeferredTasks = getFeatureDeferredCount(feature);
  const featureCompletedTasks = getFeatureCompletedCount(feature);
  const featureHasDeferred = hasDeferredCaveat(feature);
  const primaryDate = getFeaturePrimaryDate(feature);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', feature.id);
        e.dataTransfer.effectAllowed = 'move';
        onDragStart(feature.id);
      }}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className={`bg-slate-900 border border-slate-800 p-4 rounded-lg shadow-sm hover:border-indigo-500/50 transition-all group cursor-pointer hover:shadow-lg hover:-translate-y-0.5 ${isDragging ? 'opacity-60 ring-1 ring-indigo-500/40' : ''}`}
    >
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <span className="font-mono text-[10px] text-slate-500 truncate max-w-[180px]">{feature.id}</span>
        <div className="flex items-center gap-2">
          <FeatureSessionIndicator summary={sessionSummary} loading={sessionSummaryLoading} />
          <StatusDropdown status={feature.status} onStatusChange={onStatusChange} size="xs" />
        </div>
      </div>

      <h4 className="font-medium text-slate-200 mb-2 line-clamp-2 group-hover:text-indigo-400 transition-colors text-sm">{feature.name}</h4>
      {featureHasDeferred && (
        <div className="mb-2">
          <span className="text-[9px] uppercase px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10">
            Includes deferred steps
          </span>
        </div>
      )}

      {/* Progress */}
      <div className="mb-3">
        <ProgressBar completed={featureCompletedTasks} deferred={featureDeferredTasks} total={feature.totalTasks} />
      </div>

      {/* Linked Doc chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {prdDoc && (
          <span className="text-[9px] flex items-center gap-1 bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20">
            <ClipboardList size={10} /> PRD
          </span>
        )}
        {planDoc && (
          <span className="text-[9px] flex items-center gap-1 bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/20">
            <Layers size={10} /> Plan
          </span>
        )}
        {feature.phases.length > 0 && (
          <span className="text-[9px] flex items-center gap-1 bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700">
            {feature.phases.length} phase{feature.phases.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800">
        <div className="flex flex-col min-w-0">
          {feature.category ? (
            <span className="text-[10px] text-slate-500 truncate capitalize">{feature.category}</span>
          ) : <span />}
          {primaryDate.value && (
            <span className="text-[10px] text-slate-600 truncate">
              {primaryDate.label}: {new Date(primaryDate.value).toLocaleDateString()}
            </span>
          )}
        </div>
        <span className="text-[10px] text-slate-600 flex items-center gap-1 group-hover:text-indigo-400 transition-colors">
          Details <ChevronRight size={10} />
        </span>
      </div>
    </div>
  );
};

// ── List View Card ─────────────────────────────────────────────────

const FeatureListCard = ({
  feature,
  sessionSummary,
  sessionSummaryLoading,
  onClick,
  onStatusChange,
}: {
  feature: Feature;
  sessionSummary?: FeatureSessionSummary;
  sessionSummaryLoading: boolean;
  onClick: () => void;
  onStatusChange: (newStatus: string) => void;
}) => {
  const featureDeferredTasks = getFeatureDeferredCount(feature);
  const featureCompletedTasks = getFeatureCompletedCount(feature);
  const featureHasDeferred = hasDeferredCaveat(feature);
  const primaryDate = getFeaturePrimaryDate(feature);

  return (
    <div
      onClick={onClick}
      className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group shadow-sm hover:shadow-md"
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <span className="font-mono text-xs text-slate-500 border border-slate-800 px-1.5 py-0.5 rounded truncate max-w-[200px]">{feature.id}</span>
            <FeatureSessionIndicator summary={sessionSummary} loading={sessionSummaryLoading} />
            <StatusDropdown status={feature.status} onStatusChange={onStatusChange} size="xs" />
            {feature.category && (
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 capitalize">{feature.category}</span>
            )}
          </div>
          <h3 className="font-bold text-slate-200 text-lg group-hover:text-indigo-400 transition-colors truncate">{feature.name}</h3>
        </div>
        <div className="text-right ml-4 flex-shrink-0">
          <div className="text-indigo-400 font-mono font-bold text-sm">{featureCompletedTasks}/{feature.totalTasks}</div>
          {primaryDate.value && (
            <div className="text-[10px] text-slate-500">
              {primaryDate.label}: {new Date(primaryDate.value).toLocaleDateString()}
              {primaryDate.confidence ? ` (${primaryDate.confidence})` : ''}
            </div>
          )}
        </div>
      </div>
      {featureHasDeferred && (
        <div className="mb-2">
          <span className="text-[9px] uppercase px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10">
            Includes deferred steps
          </span>
        </div>
      )}

      <div className="mb-3">
        <ProgressBar completed={featureCompletedTasks} deferred={featureDeferredTasks} total={feature.totalTasks} />
      </div>

      <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
        <div className="flex gap-2">
          {feature.linkedDocs.map(doc => (
            <span key={doc.id} className="text-[10px] flex items-center gap-1 bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700">
              <DocTypeIcon docType={doc.docType} />
              <DocTypeBadge docType={doc.docType} />
            </span>
          ))}
        </div>
        {feature.phases.length > 0 && (
          <span className="text-xs text-slate-500">{feature.phases.length} phase{feature.phases.length !== 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  );
};

// ── Status Column (Board View) ─────────────────────────────────────

const StatusColumn = ({
  title,
  status,
  features,
  featureSessionSummaries,
  loadingFeatureSessionSummaries,
  onFeatureClick,
  onStatusChange,
  onCardDragStart,
  onCardDragEnd,
  onCardDrop,
  onColumnDragOver,
  onColumnDragLeave,
  isDropTarget,
  draggedFeatureId,
}: {
  title: string;
  status: string;
  features: Feature[];
  featureSessionSummaries: Record<string, FeatureSessionSummary>;
  loadingFeatureSessionSummaries: Set<string>;
  onFeatureClick: (f: Feature) => void;
  onStatusChange: (featureId: string, newStatus: string) => void;
  onCardDragStart: (featureId: string) => void;
  onCardDragEnd: () => void;
  onCardDrop: (featureId: string, newStatus: string) => void;
  onColumnDragOver: (status: string) => void;
  onColumnDragLeave: (status: string) => void;
  isDropTarget: boolean;
  draggedFeatureId: string | null;
}) => {
  const style = getStatusStyle(status);

  return (
    <div className="flex flex-col gap-4 min-w-[300px] w-full lg:w-1/4">
      <div className="flex items-center justify-between px-2">
        <h3 className="font-semibold text-slate-300 text-sm uppercase tracking-wider flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${style.dot}`} />
          {title}
        </h3>
        <span className="text-slate-600 text-xs font-mono bg-slate-900 px-2 py-1 rounded">{features.length}</span>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
          onColumnDragOver(status);
        }}
        onDragEnter={() => onColumnDragOver(status)}
        onDragLeave={() => onColumnDragLeave(status)}
        onDrop={(e) => {
          e.preventDefault();
          onCardDrop(e.dataTransfer.getData('text/plain'), status);
        }}
        className={`flex flex-col gap-3 min-h-[200px] rounded-lg bg-slate-900/30 p-2 border overflow-y-auto max-h-[calc(100vh-280px)] transition-colors ${isDropTarget ? 'border-indigo-500/60 bg-indigo-500/5' : 'border-slate-800/30'}`}
      >
        {features.map(f => (
          <FeatureCard
            key={f.id}
            feature={f}
            sessionSummary={featureSessionSummaries[f.id]}
            sessionSummaryLoading={loadingFeatureSessionSummaries.has(f.id)}
            onClick={() => onFeatureClick(f)}
            onStatusChange={(newStatus) => onStatusChange(f.id, newStatus)}
            onDragStart={onCardDragStart}
            onDragEnd={onCardDragEnd}
            isDragging={draggedFeatureId === f.id}
          />
        ))}
        {features.length === 0 && (
          <div className="h-full flex items-center justify-center text-slate-700 text-sm border-2 border-dashed border-slate-800 rounded-lg p-4">
            No features
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────

export const ProjectBoard: React.FC = () => {
  const { features: apiFeatures, updateFeatureStatus } = useData();
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [selectedFeature, setSelectedFeature] = useState<Feature | null>(null);
  const [draggedFeatureId, setDraggedFeatureId] = useState<string | null>(null);
  const [dragOverStatus, setDragOverStatus] = useState<string | null>(null);
  const [featureSessionSummaries, setFeatureSessionSummaries] = useState<Record<string, FeatureSessionSummary>>({});
  const [loadingFeatureSessionSummaries, setLoadingFeatureSessionSummaries] = useState<Set<string>>(new Set());

  // Auto-select feature from URL search params
  useEffect(() => {
    const featureId = searchParams.get('feature');
    if (featureId && apiFeatures.length > 0) {
      const featureBase = getFeatureBaseSlug(featureId);
      const feat = apiFeatures.find(f => f.id === featureId)
        || apiFeatures.find(f => getFeatureBaseSlug(f.id) === featureBase);
      if (feat) {
        setSelectedFeature(feat);
        // Clear param to avoid re-triggering, or keep it for sharable URLs?
        // Let's clear it to keep URL clean after opening, similar to PlanCatalog
        setSearchParams({}, { replace: true });
      }
    }
  }, [searchParams, apiFeatures, setSearchParams]);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'date' | 'progress' | 'tasks'>('date');
  const [plannedFrom, setPlannedFrom] = useState('');
  const [plannedTo, setPlannedTo] = useState('');
  const [startedFrom, setStartedFrom] = useState('');
  const [startedTo, setStartedTo] = useState('');
  const [completedFrom, setCompletedFrom] = useState('');
  const [completedTo, setCompletedTo] = useState('');
  const [updatedFrom, setUpdatedFrom] = useState('');
  const [updatedTo, setUpdatedTo] = useState('');
  const [draftSearchQuery, setDraftSearchQuery] = useState('');
  const [draftStatusFilter, setDraftStatusFilter] = useState<string>('all');
  const [draftCategoryFilter, setDraftCategoryFilter] = useState<string>('all');
  const [draftSortBy, setDraftSortBy] = useState<'date' | 'progress' | 'tasks'>('date');
  const [draftPlannedFrom, setDraftPlannedFrom] = useState('');
  const [draftPlannedTo, setDraftPlannedTo] = useState('');
  const [draftStartedFrom, setDraftStartedFrom] = useState('');
  const [draftStartedTo, setDraftStartedTo] = useState('');
  const [draftCompletedFrom, setDraftCompletedFrom] = useState('');
  const [draftCompletedTo, setDraftCompletedTo] = useState('');
  const [draftUpdatedFrom, setDraftUpdatedFrom] = useState('');
  const [draftUpdatedTo, setDraftUpdatedTo] = useState('');
  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState({
    general: true,
    dates: true,
    sort: true,
  });

  // Derive unique categories
  const categories = useMemo(() => {
    const cats = new Set(apiFeatures.map(f => f.category).filter(Boolean));
    return Array.from(cats).sort();
  }, [apiFeatures]);

  const filteredFeatures = useMemo(() => {
    let result = apiFeatures;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(f =>
        f.name.toLowerCase().includes(q) ||
        f.id.toLowerCase().includes(q) ||
        f.tags.some(t => t.toLowerCase().includes(q))
      );
    }

    if (statusFilter !== 'all') {
      if (statusFilter === 'deferred') {
        result = result.filter(f => hasDeferredCaveat(f));
      } else {
        result = result.filter(f => getFeatureBoardStage(f) === statusFilter);
      }
    }

    if (categoryFilter !== 'all') {
      result = result.filter(f => f.category === categoryFilter);
    }

    result = result.filter(feature => {
      const planned = getFeatureDateValue(feature, 'plannedAt').value;
      const started = getFeatureDateValue(feature, 'startedAt').value;
      const completed = getFeatureDateValue(feature, 'completedAt').value;
      const updated = getFeatureDateValue(feature, 'updatedAt').value;
      if (!inDateRange(planned, plannedFrom || undefined, plannedTo || undefined)) return false;
      if (!inDateRange(started, startedFrom || undefined, startedTo || undefined)) return false;
      if (!inDateRange(updated, updatedFrom || undefined, updatedTo || undefined)) return false;
      if ((completedFrom || completedTo) && !inDateRange(completed, completedFrom || undefined, completedTo || undefined)) {
        return false;
      }
      return true;
    });

    return result.sort((a, b) => {
      if (sortBy === 'progress') {
        const pctA = a.totalTasks > 0 ? getFeatureCompletedCount(a) / a.totalTasks : 0;
        const pctB = b.totalTasks > 0 ? getFeatureCompletedCount(b) / b.totalTasks : 0;
        return pctB - pctA;
      }
      if (sortBy === 'tasks') return b.totalTasks - a.totalTasks;
      // date sort (default)
      return toEpoch(getFeatureDateValue(b, 'updatedAt').value) - toEpoch(getFeatureDateValue(a, 'updatedAt').value);
    });
  }, [
    apiFeatures,
    searchQuery,
    statusFilter,
    categoryFilter,
    sortBy,
    plannedFrom,
    plannedTo,
    startedFrom,
    startedTo,
    completedFrom,
    completedTo,
    updatedFrom,
    updatedTo,
  ]);

  const handleStatusChange = useCallback(async (featureId: string, newStatus: string) => {
    const feature = apiFeatures.find(f => f.id === featureId);
    if (!feature || feature.status === newStatus) return;
    await updateFeatureStatus(featureId, newStatus);
  }, [apiFeatures, updateFeatureStatus]);

  const loadFeatureSessionSummary = useCallback(async (featureId: string) => {
    if (!featureId || featureSessionSummaries[featureId] || loadingFeatureSessionSummaries.has(featureId)) return;

    setLoadingFeatureSessionSummaries(prev => {
      if (prev.has(featureId)) return prev;
      const next = new Set(prev);
      next.add(featureId);
      return next;
    });

    try {
      const res = await fetch(`/api/features/${encodeURIComponent(featureId)}/linked-sessions`);
      if (!res.ok) throw new Error(`Failed to load linked sessions (${res.status})`);
      const data = await res.json();
      const sessions = Array.isArray(data) ? (data as FeatureSessionLink[]) : [];
      const summary = buildFeatureSessionSummary(sessions);
      setFeatureSessionSummaries(prev => ({ ...prev, [featureId]: summary }));
    } catch {
      setFeatureSessionSummaries(prev => ({ ...prev, [featureId]: buildFeatureSessionSummary([]) }));
    } finally {
      setLoadingFeatureSessionSummaries(prev => {
        const next = new Set(prev);
        next.delete(featureId);
        return next;
      });
    }
  }, [featureSessionSummaries, loadingFeatureSessionSummaries]);

  const handleCardDragStart = useCallback((featureId: string) => {
    setDraggedFeatureId(featureId);
  }, []);

  const handleCardDragEnd = useCallback(() => {
    setDraggedFeatureId(null);
    setDragOverStatus(null);
  }, []);

  const handleColumnDragOver = useCallback((status: string) => {
    if (!draggedFeatureId) return;
    setDragOverStatus(status);
  }, [draggedFeatureId]);

  const handleColumnDragLeave = useCallback((status: string) => {
    setDragOverStatus(prev => (prev === status ? null : prev));
  }, []);

  const handleCardDrop = useCallback(async (featureId: string, newStatus: string) => {
    setDragOverStatus(null);
    setDraggedFeatureId(null);
    if (!featureId) return;
    await handleStatusChange(featureId, newStatus);
  }, [handleStatusChange]);

  useEffect(() => {
    filteredFeatures.forEach(feature => {
      void loadFeatureSessionSummary(feature.id);
    });
  }, [filteredFeatures, loadFeatureSessionSummary]);

  // Keep selected feature in sync with API data
  useEffect(() => {
    if (selectedFeature) {
      const selectedBase = getFeatureBaseSlug(selectedFeature.id);
      const updated = apiFeatures.find(f => f.id === selectedFeature.id)
        || apiFeatures.find(f => getFeatureBaseSlug(f.id) === selectedBase);
      if (updated) {
        setSelectedFeature(updated);
      } else if (apiFeatures.length > 0) {
        setSelectedFeature(null);
      }
    }
  }, [apiFeatures, selectedFeature]);

  const hasPendingFilterChanges = (
    draftSearchQuery !== searchQuery
    || draftStatusFilter !== statusFilter
    || draftCategoryFilter !== categoryFilter
    || draftSortBy !== sortBy
    || draftPlannedFrom !== plannedFrom
    || draftPlannedTo !== plannedTo
    || draftStartedFrom !== startedFrom
    || draftStartedTo !== startedTo
    || draftCompletedFrom !== completedFrom
    || draftCompletedTo !== completedTo
    || draftUpdatedFrom !== updatedFrom
    || draftUpdatedTo !== updatedTo
  );
  const hasActiveDraftFilters = Boolean(
    draftSearchQuery.trim()
    || draftStatusFilter !== 'all'
    || draftCategoryFilter !== 'all'
    || draftSortBy !== 'date'
    || draftPlannedFrom
    || draftPlannedTo
    || draftStartedFrom
    || draftStartedTo
    || draftCompletedFrom
    || draftCompletedTo
    || draftUpdatedFrom
    || draftUpdatedTo
  );
  const toggleSidebarSection = (key: keyof typeof collapsedSidebarSections) => {
    setCollapsedSidebarSections(prev => ({
      ...prev,
      [key]: !prev[key],
    }));
  };
  const applySidebarFilters = () => {
    setSearchQuery(draftSearchQuery);
    setStatusFilter(draftStatusFilter);
    setCategoryFilter(draftCategoryFilter);
    setSortBy(draftSortBy);
    setPlannedFrom(draftPlannedFrom);
    setPlannedTo(draftPlannedTo);
    setStartedFrom(draftStartedFrom);
    setStartedTo(draftStartedTo);
    setCompletedFrom(draftCompletedFrom);
    setCompletedTo(draftCompletedTo);
    setUpdatedFrom(draftUpdatedFrom);
    setUpdatedTo(draftUpdatedTo);
  };
  const clearSidebarFilters = () => {
    setDraftSearchQuery('');
    setDraftStatusFilter('all');
    setDraftCategoryFilter('all');
    setDraftSortBy('date');
    setDraftPlannedFrom('');
    setDraftPlannedTo('');
    setDraftStartedFrom('');
    setDraftStartedTo('');
    setDraftCompletedFrom('');
    setDraftCompletedTo('');
    setDraftUpdatedFrom('');
    setDraftUpdatedTo('');

    setSearchQuery('');
    setStatusFilter('all');
    setCategoryFilter('all');
    setSortBy('date');
    setPlannedFrom('');
    setPlannedTo('');
    setStartedFrom('');
    setStartedTo('');
    setCompletedFrom('');
    setCompletedTo('');
    setUpdatedFrom('');
    setUpdatedTo('');
  };

  return (
    <div className="h-full flex flex-col relative">

      <SidebarFiltersPortal>
          <SidebarFiltersSection title="Filters" icon={Filter}>
            <div className="space-y-2">
              <button
                onClick={() => toggleSidebarSection('general')}
                className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400 border border-slate-800 rounded-md px-2.5 py-2 hover:text-slate-200 hover:border-slate-700 transition-colors"
              >
                <span>General</span>
                {collapsedSidebarSections.general ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </button>
              {!collapsedSidebarSections.general && (
                <div className="pl-1 space-y-2">
                  <div className="relative">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                      type="text"
                      placeholder="Search features..."
                      value={draftSearchQuery}
                      onChange={e => setDraftSearchQuery(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none transition-colors"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">Status</label>
                    <select
                      value={draftStatusFilter}
                      onChange={e => setDraftStatusFilter(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="all">All Statuses</option>
                      <option value="backlog">Backlog</option>
                      <option value="in-progress">In Progress</option>
                      <option value="review">Review</option>
                      <option value="done">Done</option>
                      <option value="deferred">Deferred Caveat</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-500 mb-1 block">Category</label>
                    <select
                      value={draftCategoryFilter}
                      onChange={e => setDraftCategoryFilter(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="all">All Categories</option>
                      {categories.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              <button
                onClick={() => toggleSidebarSection('dates')}
                className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400 border border-slate-800 rounded-md px-2.5 py-2 hover:text-slate-200 hover:border-slate-700 transition-colors"
              >
                <span>Date Ranges</span>
                {collapsedSidebarSections.dates ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </button>
              {!collapsedSidebarSections.dates && (
                <div className="pl-1 space-y-2">
                  <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">Planned</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">From</span>
                      <input
                        type="date"
                        value={draftPlannedFrom}
                        onChange={e => setDraftPlannedFrom(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">To</span>
                      <input
                        type="date"
                        value={draftPlannedTo}
                        onChange={e => setDraftPlannedTo(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">Started</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">From</span>
                      <input
                        type="date"
                        value={draftStartedFrom}
                        onChange={e => setDraftStartedFrom(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">To</span>
                      <input
                        type="date"
                        value={draftStartedTo}
                        onChange={e => setDraftStartedTo(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">Completed</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">From</span>
                      <input
                        type="date"
                        value={draftCompletedFrom}
                        onChange={e => setDraftCompletedFrom(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">To</span>
                      <input
                        type="date"
                        value={draftCompletedTo}
                        onChange={e => setDraftCompletedTo(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400">Updated</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">From</span>
                      <input
                        type="date"
                        value={draftUpdatedFrom}
                        onChange={e => setDraftUpdatedFrom(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">To</span>
                      <input
                        type="date"
                        value={draftUpdatedTo}
                        onChange={e => setDraftUpdatedTo(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>
                </div>
              )}

              <button
                onClick={() => toggleSidebarSection('sort')}
                className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400 border border-slate-800 rounded-md px-2.5 py-2 hover:text-slate-200 hover:border-slate-700 transition-colors"
              >
                <span>Sort</span>
                {collapsedSidebarSections.sort ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </button>
              {!collapsedSidebarSections.sort && (
                <div className="pl-1 flex flex-col gap-1.5">
                  {[
                    { key: 'date', label: 'Recent' },
                    { key: 'progress', label: 'Progress' },
                    { key: 'tasks', label: 'Task Count' },
                  ].map(s => (
                    <button
                      key={s.key}
                      onClick={() => setDraftSortBy(s.key as any)}
                      className={`py-1.5 px-3 text-xs rounded border text-left transition-colors ${draftSortBy === s.key ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'bg-slate-900 border-slate-800 text-slate-400'}`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                onClick={clearSidebarFilters}
                className="w-full inline-flex items-center justify-center rounded-md border border-rose-500/30 bg-rose-500/15 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-rose-200 hover:bg-rose-500/25 hover:border-rose-400/50 disabled:opacity-40"
                disabled={!hasActiveDraftFilters}
              >
                Clear
              </button>
              <button
                onClick={applySidebarFilters}
                className="w-full inline-flex items-center justify-center rounded-md border border-indigo-500/40 bg-indigo-500/25 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-100 hover:bg-indigo-500/35 hover:border-indigo-400/60 disabled:opacity-40"
                disabled={!hasPendingFilterChanges}
              >
                Apply
              </button>
            </div>
          </SidebarFiltersSection>
      </SidebarFiltersPortal>

      {/* Page Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Feature Board</h2>
          <p className="text-slate-400 text-sm">
            {filteredFeatures.length} features · Synced from project plans &amp; progress files
          </p>
        </div>
        <div className="flex gap-3">
          <div className="bg-slate-900 border border-slate-800 p-1 rounded-lg flex gap-1">
            <button
              onClick={() => setViewMode('board')}
              className={`p-1.5 rounded-md transition-all ${viewMode === 'board' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
              title="Kanban View"
            >
              <LayoutGrid size={18} />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-1.5 rounded-md transition-all ${viewMode === 'list' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
              title="List View"
            >
              <List size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-x-auto">
        {viewMode === 'board' ? (
          <div className="flex gap-6 min-w-[1200px] h-full pb-4">
            <StatusColumn
              title="Backlog"
              status="backlog"
              features={filteredFeatures.filter(f => getFeatureBoardStage(f) === 'backlog')}
              featureSessionSummaries={featureSessionSummaries}
              loadingFeatureSessionSummaries={loadingFeatureSessionSummaries}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
              onCardDragStart={handleCardDragStart}
              onCardDragEnd={handleCardDragEnd}
              onCardDrop={handleCardDrop}
              onColumnDragOver={handleColumnDragOver}
              onColumnDragLeave={handleColumnDragLeave}
              isDropTarget={dragOverStatus === 'backlog'}
              draggedFeatureId={draggedFeatureId}
            />
            <StatusColumn
              title="In Progress"
              status="in-progress"
              features={filteredFeatures.filter(f => getFeatureBoardStage(f) === 'in-progress')}
              featureSessionSummaries={featureSessionSummaries}
              loadingFeatureSessionSummaries={loadingFeatureSessionSummaries}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
              onCardDragStart={handleCardDragStart}
              onCardDragEnd={handleCardDragEnd}
              onCardDrop={handleCardDrop}
              onColumnDragOver={handleColumnDragOver}
              onColumnDragLeave={handleColumnDragLeave}
              isDropTarget={dragOverStatus === 'in-progress'}
              draggedFeatureId={draggedFeatureId}
            />
            <StatusColumn
              title="Review"
              status="review"
              features={filteredFeatures.filter(f => getFeatureBoardStage(f) === 'review')}
              featureSessionSummaries={featureSessionSummaries}
              loadingFeatureSessionSummaries={loadingFeatureSessionSummaries}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
              onCardDragStart={handleCardDragStart}
              onCardDragEnd={handleCardDragEnd}
              onCardDrop={handleCardDrop}
              onColumnDragOver={handleColumnDragOver}
              onColumnDragLeave={handleColumnDragLeave}
              isDropTarget={dragOverStatus === 'review'}
              draggedFeatureId={draggedFeatureId}
            />
            <StatusColumn
              title="Done"
              status="done"
              features={filteredFeatures.filter(f => getFeatureBoardStage(f) === 'done')}
              featureSessionSummaries={featureSessionSummaries}
              loadingFeatureSessionSummaries={loadingFeatureSessionSummaries}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
              onCardDragStart={handleCardDragStart}
              onCardDragEnd={handleCardDragEnd}
              onCardDrop={handleCardDrop}
              onColumnDragOver={handleColumnDragOver}
              onColumnDragLeave={handleColumnDragLeave}
              isDropTarget={dragOverStatus === 'done'}
              draggedFeatureId={draggedFeatureId}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-6">
            {filteredFeatures.map(f => (
              <FeatureListCard
                key={f.id}
                feature={f}
                sessionSummary={featureSessionSummaries[f.id]}
                sessionSummaryLoading={loadingFeatureSessionSummaries.has(f.id)}
                onClick={() => setSelectedFeature(f)}
                onStatusChange={(newStatus) => handleStatusChange(f.id, newStatus)}
              />
            ))}
            {filteredFeatures.length === 0 && (
              <div className="col-span-full py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                No features match your filters.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Feature Detail Modal */}
      {selectedFeature && (
        <FeatureModal
          feature={selectedFeature}
          onClose={() => setSelectedFeature(null)}
        />
      )}
    </div>
  );
};
