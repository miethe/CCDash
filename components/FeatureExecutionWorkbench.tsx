import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  BookOpen,
  Calendar,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Command,
  ExternalLink,
  FileText,
  GitCommit,
  Layers,
  LineChart,
  Loader2,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Terminal,
  TestTube2,
  Users,
  X,
} from 'lucide-react';

import { useData } from '../contexts/DataContext';
import {
  AgentSession,
  ExecutionPolicyResult,
  ExecutionRun,
  ExecutionRunEvent,
  Feature,
  FeatureExecutionContext,
  FeatureExecutionSessionLink,
  FeaturePhase,
  LinkedDocument,
  PlanDocument,
  ProjectTask,
} from '../types';
import {
  approveExecutionRun,
  cancelExecutionRun,
  checkExecutionPolicy,
  createExecutionRun,
  getExecutionRun,
  getFeatureExecutionContext,
  listExecutionRunEvents,
  listExecutionRuns,
  retryExecutionRun,
  trackExecutionEvent,
} from '../services/execution';
import { isStackRecommendationsEnabled, isWorkflowAnalyticsEnabled } from '../services/agenticIntelligence';
import { listTestRuns } from '../services/testVisualizer';
import { SessionCard, SessionCardDetailSection, deriveSessionCardTitle } from './SessionCard';
import { SessionArtifactsView } from './SessionArtifactsView';
import { DocumentModal } from './DocumentModal';
import { getFeatureStatusStyle } from './featureStatus';
import { TestStatusView } from './TestVisualizer/TestStatusView';
import { ExecutionApprovalDialog } from './execution/ExecutionApprovalDialog';
import { RecommendedStackCard } from './execution/RecommendedStackCard';
import { ExecutionRunHistory } from './execution/ExecutionRunHistory';
import { ExecutionRunPanel } from './execution/ExecutionRunPanel';
import { WorkflowEffectivenessSurface } from './execution/WorkflowEffectivenessSurface';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../lib/tokenMetrics';

const TERMINAL_PHASE_STATUSES = new Set(['done', 'deferred']);
const SHORT_COMMIT_LENGTH = 7;

type WorkbenchTab = 'overview' | 'runs' | 'phases' | 'documents' | 'sessions' | 'artifacts' | 'history' | 'analytics' | 'test-status';
type FeatureModalTab = 'overview' | 'phases' | 'docs' | 'relations' | 'sessions' | 'history';
type CoreSessionGroupId = 'plan' | 'execution' | 'other';

interface CoreSessionGroupDefinition {
  id: CoreSessionGroupId;
  label: string;
  description: string;
}

interface FeatureSessionTreeNode {
  session: FeatureExecutionSessionLink;
  children: FeatureSessionTreeNode[];
}

interface FeatureHistoryEvent {
  id: string;
  timestamp: string;
  label: string;
  kind: string;
  confidence: string;
  source: string;
  description?: string;
}

const TAB_ITEMS: Array<{ id: WorkbenchTab; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: 'overview', label: 'Overview', icon: Layers },
  { id: 'runs', label: 'Runs', icon: Command },
  { id: 'phases', label: 'Phases', icon: Play },
  { id: 'documents', label: 'Documents', icon: BookOpen },
  { id: 'sessions', label: 'Sessions', icon: Terminal },
  { id: 'artifacts', label: 'Artifacts', icon: Users },
  { id: 'history', label: 'History', icon: Calendar },
  { id: 'analytics', label: 'Analytics', icon: LineChart },
  { id: 'test-status', label: 'Test Status', icon: TestTube2 },
];

const WORKBENCH_TAB_IDS = new Set<WorkbenchTab>(TAB_ITEMS.map(item => item.id));

const isWorkbenchTab = (value: string | null): value is WorkbenchTab => (
  Boolean(value) && WORKBENCH_TAB_IDS.has(value as WorkbenchTab)
);

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

const IntelligenceDisabledNotice: React.FC<{ title: string; message: string }> = ({ title, message }) => (
  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
    <p className="font-semibold">{title}</p>
    <p className="mt-1 text-amber-100/80">{message}</p>
  </div>
);

const DEFAULT_CORE_SESSION_GROUP_EXPANDED: Record<CoreSessionGroupId, boolean> = {
  plan: true,
  execution: true,
  other: true,
};

const toShortCommitHash = (hash: string): string => hash.slice(0, SHORT_COMMIT_LENGTH);
const normalizePath = (value: string): string => (value || '').replace(/\\/g, '/').replace(/^\.?\//, '');

const isPathLike = (value: string): boolean => {
  const text = (value || '').trim();
  if (!text) return false;
  return text.includes('/') || text.includes('\\') || text.endsWith('.md');
};

const fileNameFromPath = (path: string): string => {
  const normalized = normalizePath(path);
  if (!normalized) return '';
  const tokens = normalized.split('/').filter(Boolean);
  return tokens[tokens.length - 1] || normalized;
};

const toTitleCase = (value: string): string =>
  value
    .split(/\s+/)
    .filter(Boolean)
    .map(token => token.charAt(0).toUpperCase() + token.slice(1))
    .join(' ');

const EVIDENCE_KEY_LABELS: Record<string, string> = {
  feature: 'Feature',
  active_phase: 'Active Phase',
  next_phase: 'Next Phase',
  highest_completed_phase: 'Highest Completed Phase',
  completed_phases: 'Completed Phases',
  missing: 'Missing',
  evidence: 'Evidence',
};

const parseEvidenceToken = (value: string): { key: string; tokenValue: string } => {
  const raw = (value || '').trim();
  const idx = raw.indexOf(':');
  if (idx <= 0) return { key: '', tokenValue: raw };
  return {
    key: raw.slice(0, idx).trim().toLowerCase(),
    tokenValue: raw.slice(idx + 1).trim(),
  };
};

const humanizeEvidenceKey = (key: string): string => {
  const normalized = (key || '').trim().toLowerCase();
  if (!normalized) return '';
  if (EVIDENCE_KEY_LABELS[normalized]) return EVIDENCE_KEY_LABELS[normalized];
  return toTitleCase(normalized.replace(/_/g, ' '));
};

const TASK_STATUS_PRIORITY: Record<string, number> = {
  done: 5,
  deferred: 4,
  review: 3,
  'in-progress': 2,
  backlog: 1,
  todo: 1,
};

const taskUpdatedAtEpoch = (task: ProjectTask): number => {
  const parsed = Date.parse(task.updatedAt || '');
  return Number.isNaN(parsed) ? 0 : parsed;
};

const taskStatusPriority = (task: ProjectTask): number =>
  TASK_STATUS_PRIORITY[String(task.status || '').toLowerCase()] || 0;

const taskSignalScore = (task: ProjectTask): number => {
  let score = 0;
  if ((task.sessionId || '').trim()) score += 2;
  if ((task.commitHash || '').trim()) score += 2;
  const sourcePath = normalizePath(task.sourceFile || '').toLowerCase();
  if (sourcePath.includes('/progress/')) score += 1;
  if (sourcePath.includes('/project_plans/')) score += 0.5;
  return score;
};

const pickFresherTask = (existing: ProjectTask, candidate: ProjectTask): ProjectTask => {
  const existingUpdated = taskUpdatedAtEpoch(existing);
  const candidateUpdated = taskUpdatedAtEpoch(candidate);
  if (candidateUpdated !== existingUpdated) return candidateUpdated > existingUpdated ? candidate : existing;

  const existingStatus = taskStatusPriority(existing);
  const candidateStatus = taskStatusPriority(candidate);
  if (candidateStatus !== existingStatus) return candidateStatus > existingStatus ? candidate : existing;

  const existingSignals = taskSignalScore(existing);
  const candidateSignals = taskSignalScore(candidate);
  if (candidateSignals !== existingSignals) return candidateSignals > existingSignals ? candidate : existing;

  return existing;
};

const formatDateTime = (value?: string): string => {
  if (!value) return '—';
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
};

const toEpoch = (value?: string): number => {
  const parsed = Date.parse(value || '');
  return Number.isNaN(parsed) ? 0 : parsed;
};

const formatStatus = (value: string): string => {
  const normalized = (value || 'unknown').replace(/-/g, ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

const getFeatureCoverageSummary = (feature: Feature): string => {
  const coverage = feature.documentCoverage;
  if (!coverage) return 'Docs n/a';
  const present = coverage.present?.length || 0;
  const total = present + (coverage.missing?.length || 0);
  if (total <= 0) return 'Docs n/a';
  return `${present}/${total}`;
};

const getFeatureLinkedFeatureCount = (feature: Feature): number => {
  const typedCount = feature.linkedFeatures?.length || 0;
  if (typedCount > 0) return typedCount;
  return feature.relatedFeatures?.length || 0;
};

const executionVerdictClass = (value?: string): string => {
  const normalized = (value || '').toLowerCase();
  if (normalized === 'allow') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  if (normalized === 'requires_approval') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (normalized === 'deny') return 'border-rose-500/40 bg-rose-500/10 text-rose-200';
  return 'border-slate-600 bg-slate-800/60 text-slate-200';
};

const executionRiskClass = (value?: string): string => {
  const normalized = (value || '').toLowerCase();
  if (normalized === 'low') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  if (normalized === 'medium') return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  if (normalized === 'high') return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
  return 'border-slate-600 bg-slate-800/60 text-slate-200';
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

const getSessionPhaseNumbers = (session: FeatureExecutionSessionLink): number[] => {
  const candidates: number[] = [];
  const relatedPhases = session.sessionMetadata?.relatedPhases || [];
  relatedPhases.forEach(phase => {
    const parsed = parsePhaseNumber(String(phase || ''), true);
    if (parsed !== null) candidates.push(parsed);
  });
  [session.title || '', ...(session.commands || [])].forEach(value => {
    const parsed = parsePhaseNumber(value, false);
    if (parsed !== null) candidates.push(parsed);
  });
  return Array.from(new Set(candidates)).sort((a, b) => a - b);
};

const getSessionPrimaryPhaseNumber = (session: FeatureExecutionSessionLink): number | null => {
  const values = getSessionPhaseNumbers(session);
  return values.length > 0 ? values[0] : null;
};

const getSessionClassificationText = (session: FeatureExecutionSessionLink): string =>
  [
    session.workflowType || '',
    session.sessionType || '',
    session.sessionMetadata?.sessionTypeLabel || '',
    session.title || '',
    ...(session.reasons || []),
    ...(session.commands || []),
  ]
    .join(' ')
    .toLowerCase();

const isPlanningSession = (session: FeatureExecutionSessionLink): boolean => {
  const haystack = getSessionClassificationText(session);
  const workflow = (session.workflowType || '').toLowerCase();
  if (workflow === 'planning') return true;
  return ['/plan:', 'planning', 'analysis', 'spike', 'adr', 'discovery', 'research', 'scoping'].some(token => haystack.includes(token));
};

const isExecutionSession = (session: FeatureExecutionSessionLink): boolean => {
  const workflow = (session.workflowType || '').toLowerCase();
  if (workflow === 'execution' || workflow === 'debug' || workflow === 'enhancement') return true;
  const haystack = getSessionClassificationText(session);
  if (['/dev:execute-phase', 'execute-phase', 'execution', 'implement', 'implementation', 'quick-feature'].some(token => haystack.includes(token))) {
    return true;
  }
  return getSessionPrimaryPhaseNumber(session) !== null;
};

const getCoreSessionGroupId = (session: FeatureExecutionSessionLink): CoreSessionGroupId => {
  if (isPlanningSession(session)) return 'plan';
  if (isExecutionSession(session)) return 'execution';
  return 'other';
};

const isSubthreadSession = (session: FeatureExecutionSessionLink): boolean => {
  if (session.isSubthread) return true;
  if (session.parentSessionId) return true;
  return (session.sessionType || '').toLowerCase() === 'subagent';
};

const isPrimarySession = (session: FeatureExecutionSessionLink): boolean => {
  if (session.isPrimaryLink) return true;
  return (session.confidence || 0) >= 0.9;
};

const sessionHasLinkedSubthreads = (sessionId: string, sessions: FeatureExecutionSessionLink[]): boolean => (
  sessions.some(candidate => (
    candidate.sessionId !== sessionId
    && isSubthreadSession(candidate)
    && (
      candidate.parentSessionId === sessionId
      || candidate.rootSessionId === sessionId
    )
  ))
);

const compareSessionsByConfidenceAndTime = (a: FeatureExecutionSessionLink, b: FeatureExecutionSessionLink): number => {
  if ((b.confidence || 0) !== (a.confidence || 0)) return (b.confidence || 0) - (a.confidence || 0);
  return toEpoch(b.startedAt) - toEpoch(a.startedAt);
};

const compareSessionsForGroup = (groupId: CoreSessionGroupId, a: FeatureExecutionSessionLink, b: FeatureExecutionSessionLink): number => {
  if (groupId === 'execution') {
    const aPhase = getSessionPrimaryPhaseNumber(a) ?? Number.POSITIVE_INFINITY;
    const bPhase = getSessionPrimaryPhaseNumber(b) ?? Number.POSITIVE_INFINITY;
    if (aPhase !== bPhase) return aPhase - bPhase;
  }
  return compareSessionsByConfidenceAndTime(a, b);
};

const sortThreadNodes = (
  nodes: FeatureSessionTreeNode[],
  comparator: (a: FeatureExecutionSessionLink, b: FeatureExecutionSessionLink) => number,
): FeatureSessionTreeNode[] => {
  return [...nodes]
    .sort((a, b) => comparator(a.session, b.session))
    .map(node => ({
      ...node,
      children: sortThreadNodes(node.children, compareSessionsByConfidenceAndTime),
    }));
};

const countThreadNodes = (nodes: FeatureSessionTreeNode[]): number =>
  nodes.reduce((sum, node) => sum + 1 + countThreadNodes(node.children), 0);

const buildSessionThreadForest = (sessions: FeatureExecutionSessionLink[]): FeatureSessionTreeNode[] => {
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

const dedupePhaseTasks = (tasks: ProjectTask[]): ProjectTask[] => {
  const byIdentity = new Map<string, ProjectTask>();
  tasks.forEach(task => {
    const taskId = String(task.id || '').trim().toLowerCase();
    const title = String(task.title || '').trim().toLowerCase();
    const identity = taskId || title;
    if (!identity) return;

    const existing = byIdentity.get(identity);
    if (!existing) {
      byIdentity.set(identity, task);
      return;
    }

    const preferred = pickFresherTask(existing, task);
    const other = preferred === existing ? task : existing;
    byIdentity.set(identity, {
      ...other,
      ...preferred,
      title: preferred.title || other.title,
      description: preferred.description || other.description,
      sourceFile: preferred.sourceFile || other.sourceFile,
      sessionId: preferred.sessionId || other.sessionId,
      commitHash: preferred.commitHash || other.commitHash,
      relatedFiles: (preferred.relatedFiles && preferred.relatedFiles.length > 0) ? preferred.relatedFiles : other.relatedFiles,
      updatedAt: preferred.updatedAt || other.updatedAt,
      status: preferred.status || other.status,
    });
  });
  return Array.from(byIdentity.values());
};

const getPhasePendingTasks = (phase: FeaturePhase): number => {
  if (Array.isArray(phase.tasks) && phase.tasks.length > 0) {
    return phase.tasks.filter(task => !TERMINAL_PHASE_STATUSES.has(task.status)).length;
  }
  const total = Math.max(phase.totalTasks || 0, 0);
  const completed = Math.max(
    Math.max(phase.completedTasks || 0, 0),
    Math.max(phase.deferredTasks || 0, 0),
  );
  return Math.max(total - completed, 0);
};

const createFallbackDocument = (doc: LinkedDocument): PlanDocument => ({
  id: doc.id || `DOC-${normalizePath(doc.filePath || doc.title || '').replace(/\//g, '-')}`,
  title: doc.title || fileNameFromPath(doc.filePath || ''),
  filePath: doc.filePath || '',
  canonicalPath: normalizePath(doc.filePath || ''),
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

const copyText = async (value: string): Promise<void> => {
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
};

export const FeatureExecutionWorkbench: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { activeProject, features, refreshFeatures, documents, getSessionById } = useData();
  const stackRecommendationsAvailable = isStackRecommendationsEnabled(activeProject);
  const workflowAnalyticsAvailable = isWorkflowAnalyticsEnabled(activeProject);
  const featureParam = searchParams.get('feature') || '';
  const tabParam = searchParams.get('tab');

  const [selectedFeatureId, setSelectedFeatureId] = useState<string>(featureParam);
  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState<WorkbenchTab>(() => {
    return isWorkbenchTab(tabParam) ? tabParam : 'overview';
  });
  const [context, setContext] = useState<FeatureExecutionContext | null>(null);
  const [fullFeature, setFullFeature] = useState<Feature | null>(null);
  const [loading, setLoading] = useState(false);
  const [fullFeatureLoading, setFullFeatureLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [copiedCommand, setCopiedCommand] = useState('');
  const [viewingDoc, setViewingDoc] = useState<PlanDocument | null>(null);
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());
  const [coreSessionGroupExpanded, setCoreSessionGroupExpanded] = useState<Record<CoreSessionGroupId, boolean>>(
    () => ({ ...DEFAULT_CORE_SESSION_GROUP_EXPANDED }),
  );
  const [showSecondarySessions, setShowSecondarySessions] = useState(false);
  const [expandedSubthreadsBySessionId, setExpandedSubthreadsBySessionId] = useState<Set<string>>(new Set());
  const [artifactSourceSessions, setArtifactSourceSessions] = useState<AgentSession[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [hasFeatureTestRuns, setHasFeatureTestRuns] = useState(false);
  const [executionRuns, setExecutionRuns] = useState<ExecutionRun[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState('');
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedRunEvents, setSelectedRunEvents] = useState<ExecutionRunEvent[]>([]);
  const [selectedRunEventsLoading, setSelectedRunEventsLoading] = useState(false);
  const [selectedRunNextSequence, setSelectedRunNextSequence] = useState(0);
  const [runActionLoading, setRunActionLoading] = useState(false);
  const [runActionError, setRunActionError] = useState('');
  const [reviewCommand, setReviewCommand] = useState('');
  const [reviewRuleId, setReviewRuleId] = useState('');
  const [reviewCwd, setReviewCwd] = useState('.');
  const [reviewEnvProfile, setReviewEnvProfile] = useState('default');
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewPolicy, setReviewPolicy] = useState<ExecutionPolicyResult | null>(null);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approvalRun, setApprovalRun] = useState<ExecutionRun | null>(null);
  const selectedRunNextSequenceRef = useRef(0);
  const initialHasQueryFeatureRef = useRef(Boolean(searchParams.get('feature')));

  useEffect(() => {
    if (features.length === 0) {
      void refreshFeatures();
    }
  }, [features.length, refreshFeatures]);

  const filteredFeatures = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = [...features].sort((a, b) => a.name.localeCompare(b.name));
    if (!needle) return rows;
    return rows.filter(feature => {
      const haystack = [feature.id, feature.name, feature.category, ...(feature.tags || [])].join(' ').toLowerCase();
      return haystack.includes(needle);
    });
  }, [features, query]);

  useEffect(() => {
    if (featureParam) {
      setSelectedFeatureId(prev => (prev === featureParam ? prev : featureParam));
      return;
    }
    if (features.length === 0) return;
    setSelectedFeatureId(prev => {
      if (prev) return prev;
      const first = [...features].sort((a, b) => a.name.localeCompare(b.name))[0];
      return first?.id || prev;
    });
  }, [featureParam, features]);

  useEffect(() => {
    if (isWorkbenchTab(tabParam)) {
      setActiveTab(prev => (prev === tabParam ? prev : tabParam));
    }
  }, [tabParam]);

  useEffect(() => {
    const currentTab = tabParam;
    if (activeTab === 'overview' && !currentTab) return;
    if (activeTab === currentTab) return;
    const nextParams = new URLSearchParams(searchParams);
    if (activeTab === 'overview') {
      nextParams.delete('tab');
    } else {
      nextParams.set('tab', activeTab);
    }
    if (nextParams.toString() === searchParams.toString()) return;
    setSearchParams(nextParams, { replace: true });
  }, [activeTab, searchParams, setSearchParams, tabParam]);

  const selectFeature = useCallback(
    (featureId: string) => {
      setSelectedFeatureId(featureId);
      const nextParams = new URLSearchParams(searchParams);
      if (featureId) {
        nextParams.set('feature', featureId);
      } else {
        nextParams.delete('feature');
      }
      setSearchParams(nextParams, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const upsertExecutionRun = useCallback((nextRun: ExecutionRun) => {
    setExecutionRuns(prev => {
      const idx = prev.findIndex(run => run.id === nextRun.id);
      const next = idx >= 0
        ? [...prev.slice(0, idx), nextRun, ...prev.slice(idx + 1)]
        : [nextRun, ...prev];
      return next.sort((a, b) => toEpoch(b.createdAt) - toEpoch(a.createdAt));
    });
  }, []);

  const refreshExecutionRuns = useCallback(async (featureId: string = selectedFeatureId) => {
    if (!featureId) {
      setExecutionRuns([]);
      setRunsError('');
      return;
    }
    setRunsLoading(true);
    try {
      const rows = await listExecutionRuns({ featureId, limit: 60, offset: 0 });
      setExecutionRuns(rows);
      setRunsError('');
    } catch (err) {
      setRunsError(err instanceof Error ? err.message : 'Failed to load run history');
    } finally {
      setRunsLoading(false);
    }
  }, [selectedFeatureId]);

  useEffect(() => {
    if (!selectedFeatureId) {
      setExecutionRuns([]);
      setSelectedRunId('');
      setSelectedRunEvents([]);
      setSelectedRunNextSequence(0);
      selectedRunNextSequenceRef.current = 0;
      return;
    }
    void refreshExecutionRuns(selectedFeatureId);
  }, [refreshExecutionRuns, selectedFeatureId]);

  useEffect(() => {
    setSelectedRunId(prev => {
      if (prev && executionRuns.some(run => run.id === prev)) return prev;
      return executionRuns[0]?.id || '';
    });
  }, [executionRuns]);

  const selectedRun = useMemo(
    () => executionRuns.find(run => run.id === selectedRunId) || null,
    [executionRuns, selectedRunId],
  );

  useEffect(() => {
    selectedRunNextSequenceRef.current = selectedRunNextSequence;
  }, [selectedRunNextSequence]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRunEvents([]);
      setSelectedRunNextSequence(0);
      selectedRunNextSequenceRef.current = 0;
      return;
    }

    let cancelled = false;
    setSelectedRunEventsLoading(true);
    void listExecutionRunEvents(selectedRunId, { afterSequence: 0, limit: 400 })
      .then(page => {
        if (cancelled) return;
        setSelectedRunEvents(page.items);
        setSelectedRunNextSequence(page.nextSequence);
        selectedRunNextSequenceRef.current = page.nextSequence;
      })
      .catch(() => {
        if (cancelled) return;
        setSelectedRunEvents([]);
        setSelectedRunNextSequence(0);
        selectedRunNextSequenceRef.current = 0;
      })
      .finally(() => {
        if (!cancelled) setSelectedRunEventsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRun || (selectedRun.status !== 'queued' && selectedRun.status !== 'running')) return;

    let cancelled = false;
    const runId = selectedRun.id;
    const poll = async () => {
      try {
        const [latestRun, page] = await Promise.all([
          getExecutionRun(runId),
          listExecutionRunEvents(runId, {
            afterSequence: selectedRunNextSequenceRef.current,
            limit: 120,
          }),
        ]);
        if (cancelled) return;
        upsertExecutionRun(latestRun);
        if (page.items.length > 0) {
          setSelectedRunEvents(prev => [...prev, ...page.items]);
          setSelectedRunNextSequence(page.nextSequence);
          selectedRunNextSequenceRef.current = page.nextSequence;
        }
      } catch {
        // Polling failures should not break the page.
      }
    };

    const timer = window.setInterval(() => {
      void poll();
    }, 900);
    void poll();

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedRun, upsertExecutionRun]);

  const openRunReview = useCallback(async (command: string, ruleId: string) => {
    setReviewCommand(command);
    setReviewRuleId(ruleId);
    setReviewPolicy(null);
    setReviewOpen(true);
    setRunActionError('');
    setReviewLoading(true);
    try {
      const policy = await checkExecutionPolicy({
        command,
        cwd: reviewCwd,
        envProfile: reviewEnvProfile,
      });
      setReviewPolicy(policy);
    } catch (err) {
      setReviewPolicy(null);
      setRunActionError(err instanceof Error ? err.message : 'Policy check failed');
    } finally {
      setReviewLoading(false);
    }
  }, [reviewCwd, reviewEnvProfile]);

  const recheckReviewPolicy = useCallback(async () => {
    if (!reviewCommand.trim()) return;
    setReviewLoading(true);
    try {
      const policy = await checkExecutionPolicy({
        command: reviewCommand,
        cwd: reviewCwd,
        envProfile: reviewEnvProfile,
      });
      setReviewPolicy(policy);
      setRunActionError('');
    } catch (err) {
      setReviewPolicy(null);
      setRunActionError(err instanceof Error ? err.message : 'Policy check failed');
    } finally {
      setReviewLoading(false);
    }
  }, [reviewCommand, reviewCwd, reviewEnvProfile]);

  const handleLaunchReviewRun = useCallback(async () => {
    if (!reviewCommand.trim() || !context?.feature.id) return;
    if (reviewPolicy?.verdict === 'deny') {
      setRunActionError('Command is denied by execution policy. Update command or working directory before running.');
      return;
    }
    setRunActionLoading(true);
    try {
      const run = await createExecutionRun({
        command: reviewCommand,
        cwd: reviewCwd,
        envProfile: reviewEnvProfile,
        featureId: context.feature.id,
        recommendationRuleId: reviewRuleId,
        metadata: {
          launchedFrom: 'execution-workbench',
        },
      });
      upsertExecutionRun(run);
      setSelectedRunId(run.id);
      setActiveTab('runs');
      setReviewOpen(false);
      setRunActionError('');
      if (run.requiresApproval && run.status === 'blocked') {
        setApprovalRun(run);
        setApprovalOpen(true);
      }
      await refreshExecutionRuns(context.feature.id);
    } catch (err) {
      setRunActionError(err instanceof Error ? err.message : 'Failed to start run');
    } finally {
      setRunActionLoading(false);
    }
  }, [context?.feature.id, refreshExecutionRuns, reviewCommand, reviewCwd, reviewEnvProfile, reviewPolicy?.verdict, reviewRuleId, upsertExecutionRun]);

  const handleApprovalSubmit = useCallback(async (decision: 'approved' | 'denied', reason: string) => {
    if (!approvalRun) return;
    setRunActionLoading(true);
    try {
      const updated = await approveExecutionRun(approvalRun.id, {
        decision,
        reason,
        actor: 'user',
      });
      upsertExecutionRun(updated);
      setSelectedRunId(updated.id);
      setApprovalOpen(false);
      setApprovalRun(null);
      if (context?.feature.id) await refreshExecutionRuns(context.feature.id);
    } catch (err) {
      setRunActionError(err instanceof Error ? err.message : 'Failed to resolve approval');
    } finally {
      setRunActionLoading(false);
    }
  }, [approvalRun, context?.feature.id, refreshExecutionRuns, upsertExecutionRun]);

  const handleCancelRun = useCallback(async (run: ExecutionRun) => {
    setRunActionLoading(true);
    try {
      const updated = await cancelExecutionRun(run.id, { reason: 'Canceled from workbench', actor: 'user' });
      upsertExecutionRun(updated);
      setSelectedRunId(updated.id);
    } catch (err) {
      setRunActionError(err instanceof Error ? err.message : 'Failed to cancel run');
    } finally {
      setRunActionLoading(false);
    }
  }, [upsertExecutionRun]);

  const handleRetryRun = useCallback(async (run: ExecutionRun) => {
    if (run.status === 'failed') {
      const confirmed = window.confirm('Retry failed run? This will launch a new execution run.');
      if (!confirmed) return;
    }
    setRunActionLoading(true);
    try {
      const retried = await retryExecutionRun(run.id, {
        acknowledgeFailure: true,
        actor: 'user',
        metadata: { retriedFrom: run.id },
      });
      upsertExecutionRun(retried);
      setSelectedRunId(retried.id);
      setActiveTab('runs');
      if (retried.requiresApproval && retried.status === 'blocked') {
        setApprovalRun(retried);
        setApprovalOpen(true);
      }
      if (context?.feature.id) await refreshExecutionRuns(context.feature.id);
    } catch (err) {
      setRunActionError(err instanceof Error ? err.message : 'Failed to retry run');
    } finally {
      setRunActionLoading(false);
    }
  }, [context?.feature.id, refreshExecutionRuns, upsertExecutionRun]);

  useEffect(() => {
    if (!selectedFeatureId) {
      setContext(null);
      setFullFeature(null);
      setHasFeatureTestRuns(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError('');
    setFullFeature(null);
    setExpandedPhases(new Set());
    setCoreSessionGroupExpanded({ ...DEFAULT_CORE_SESSION_GROUP_EXPANDED });
    setShowSecondarySessions(false);
    setExpandedSubthreadsBySessionId(new Set());
    setArtifactSourceSessions([]);

    void trackExecutionEvent({
      eventType: 'execution_workbench_opened',
      featureId: selectedFeatureId,
      metadata: { hasQueryFeature: initialHasQueryFeatureRef.current },
    });

    void getFeatureExecutionContext(selectedFeatureId)
      .then(payload => {
        if (cancelled) return;
        setContext(payload);
        void trackExecutionEvent({
          eventType: 'execution_recommendation_generated',
          featureId: selectedFeatureId,
          recommendationRuleId: payload.recommendations.ruleId,
          command: payload.recommendations.primary.command,
          metadata: { confidence: payload.recommendations.confidence },
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setContext(null);
        setError(err instanceof Error ? err.message : 'Failed to load execution context');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedFeatureId]);

  useEffect(() => {
    if (!selectedFeatureId || !activeProject?.id) {
      setHasFeatureTestRuns(false);
      return;
    }

    let cancelled = false;
    void listTestRuns({
      projectId: activeProject.id,
      featureId: selectedFeatureId,
      limit: 1,
    })
      .then(payload => {
        if (!cancelled) {
          setHasFeatureTestRuns(payload.items.length > 0);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHasFeatureTestRuns(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeProject?.id, selectedFeatureId]);

  useEffect(() => {
    const featureId = context?.feature.id || '';
    if (!featureId || activeTab !== 'phases' || (fullFeature && fullFeature.id === featureId)) return;

    let cancelled = false;
    setFullFeatureLoading(true);
    fetch(`/api/features/${encodeURIComponent(featureId)}`)
      .then(res => {
        if (!res.ok) throw new Error(`Failed to load feature detail (${res.status})`);
        return res.json();
      })
      .then(payload => {
        if (cancelled) return;
        setFullFeature(payload as Feature);
      })
      .catch(() => {
        if (cancelled) return;
        setFullFeature(null);
      })
      .finally(() => {
        if (!cancelled) setFullFeatureLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, context?.feature.id, fullFeature]);

  const documentByPath = useMemo(() => {
    const map = new Map<string, PlanDocument>();
    documents.forEach(doc => {
      const canonical = normalizePath(doc.canonicalPath || doc.filePath || '');
      const file = normalizePath(doc.filePath || '');
      if (canonical) map.set(canonical.toLowerCase(), doc);
      if (file) map.set(file.toLowerCase(), doc);
    });
    return map;
  }, [documents]);

  const linkedDocumentsByPath = useMemo(() => {
    const map = new Map<string, LinkedDocument>();
    (context?.documents || []).forEach(doc => {
      const file = normalizePath(doc.filePath || '');
      if (!file) return;
      map.set(file.toLowerCase(), doc);
    });
    return map;
  }, [context?.documents]);

  const openBoardFeature = useCallback(
    (featureId: string, tab: FeatureModalTab = 'overview') => {
      navigate(`/board?feature=${encodeURIComponent(featureId)}&tab=${encodeURIComponent(tab)}`);
    },
    [navigate],
  );

  const openSession = useCallback(
    (sessionId: string) => {
      navigate(`/sessions?session=${encodeURIComponent(sessionId)}`);
    },
    [navigate],
  );

  const openDocFromPath = useCallback(
    (rawPath: string) => {
      const normalized = normalizePath(rawPath);
      if (!normalized) return false;
      const direct = documentByPath.get(normalized.toLowerCase());
      if (direct) {
        setViewingDoc(direct);
        return true;
      }
      const linked = linkedDocumentsByPath.get(normalized.toLowerCase());
      if (linked) {
        setViewingDoc(createFallbackDocument(linked));
        return true;
      }
      setViewingDoc(createFallbackDocument({
        id: '',
        title: fileNameFromPath(normalized),
        filePath: normalized,
        docType: 'spec',
      }));
      return true;
    },
    [documentByPath, linkedDocumentsByPath],
  );

  const openLinkedDoc = useCallback(
    (doc: LinkedDocument) => {
      const matched = documentByPath.get(normalizePath(doc.filePath).toLowerCase());
      setViewingDoc(matched || createFallbackDocument(doc));
    },
    [documentByPath],
  );

  const sourceDocPath = useMemo(
    () => context?.recommendations.evidence.find(item => item.sourcePath)?.sourcePath || '',
    [context],
  );

  const handleCopyCommand = useCallback(
    async (command: string) => {
      try {
        await copyText(command);
        setCopiedCommand(command);
        setTimeout(() => setCopiedCommand(''), 1200);
        void trackExecutionEvent({
          eventType: 'execution_command_copied',
          featureId: context?.feature.id,
          recommendationRuleId: context?.recommendations.ruleId,
          command,
        });
      } catch {
        setCopiedCommand('');
      }
    },
    [context],
  );

  const openEvidenceLink = useCallback((value: string) => {
    const text = (value || '').trim();
    if (!text) return;
    if (isPathLike(text)) {
      const opened = openDocFromPath(text);
      if (opened) return;
    }
    if (text.startsWith('feature:')) {
      openBoardFeature(text.slice('feature:'.length), 'overview');
      return;
    }
    if (text.startsWith('active_phase:') || text.startsWith('next_phase:') || text.startsWith('highest_completed_phase:')) {
      if (context?.feature.id) openBoardFeature(context.feature.id, 'phases');
      return;
    }
  }, [context?.feature.id, openBoardFeature, openDocFromPath]);

  const openSourceDoc = useCallback(() => {
    if (!sourceDocPath) return;
    void trackExecutionEvent({
      eventType: 'execution_source_link_clicked',
      featureId: context?.feature.id,
      recommendationRuleId: context?.recommendations.ruleId,
      metadata: { path: sourceDocPath },
    });
    openDocFromPath(sourceDocPath);
  }, [context, openDocFromPath, sourceDocPath]);

  const executionSessions = useMemo(() => {
    const rows = Array.isArray(context?.sessions) ? context.sessions : [];
    const typed = rows as FeatureExecutionSessionLink[];
    const bestBySession = new Map<string, FeatureExecutionSessionLink>();
    typed.forEach(row => {
      const sessionId = String(row.sessionId || '').trim();
      if (!sessionId) return;
      const existing = bestBySession.get(sessionId);
      if (!existing || (row.confidence || 0) > (existing.confidence || 0)) {
        bestBySession.set(sessionId, row);
      }
    });
    return Array.from(bestBySession.values()).sort(compareSessionsByConfidenceAndTime);
  }, [context?.sessions]);

  const executionWorkload = useMemo(
    () => executionSessions.reduce(
      (acc, session) => {
        const metrics = resolveTokenMetrics(session, {
          hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, executionSessions),
        });
        acc.workloadTokens += metrics.workloadTokens;
        acc.modelIOTokens += metrics.modelIOTokens;
        acc.cacheInputTokens += metrics.cacheInputTokens;
        acc.toolFallbackSessions += metrics.usedToolFallback ? 1 : 0;
        return acc;
      },
      { workloadTokens: 0, modelIOTokens: 0, cacheInputTokens: 0, toolFallbackSessions: 0 },
    ),
    [executionSessions],
  );

  const featureDetail = useMemo(() => {
    if (!context) return null;
    if (fullFeature && fullFeature.id === context.feature.id) return fullFeature;
    return context.feature;
  }, [context, fullFeature]);

  const phases = useMemo(
    () => featureDetail?.phases || [],
    [featureDetail],
  );

  const phaseSessionLinks = useMemo(() => {
    const byPhase = new Map<string, FeatureExecutionSessionLink[]>();
    const add = (phaseToken: string, session: FeatureExecutionSessionLink) => {
      const key = (phaseToken || '').trim();
      if (!key) return;
      const existing = byPhase.get(key) || [];
      if (!existing.some(item => item.sessionId === session.sessionId)) {
        byPhase.set(key, [...existing, session]);
      }
    };

    executionSessions.forEach(session => {
      const related = Array.isArray(session.relatedPhases) ? session.relatedPhases : [];
      related.forEach(phaseToken => {
        const normalized = String(phaseToken || '').trim();
        if (!normalized) return;
        if (normalized.toLowerCase() === 'all') {
          phases.forEach(phase => add(String(phase.phase || '').trim(), session));
          return;
        }
        add(normalized, session);
      });
    });

    return byPhase;
  }, [executionSessions, phases]);

  const taskSessionLinksByTaskId = useMemo(() => {
    const byTask = new Map<string, Array<{
      sessionId: string;
      isSubthread: boolean;
      confidence: number;
      matchedBy: string;
      source: 'task_frontmatter' | 'task_tool';
    }>>();
    const taskIdLookup = new Map<string, string>();

    phases.forEach(phase => {
      (phase.tasks || []).forEach(task => {
        const taskId = String(task.id || '').trim();
        if (!taskId) return;
        taskIdLookup.set(taskId.toLowerCase(), taskId);
      });
    });

    const addTaskSession = (
      taskId: string,
      value: {
        sessionId: string;
        isSubthread: boolean;
        confidence: number;
        matchedBy: string;
        source: 'task_frontmatter' | 'task_tool';
      },
    ) => {
      const existing = byTask.get(taskId) || [];
      if (existing.some(item => item.sessionId === value.sessionId && item.source === value.source)) {
        return;
      }
      byTask.set(taskId, [...existing, value]);
    };

    phases.forEach(phase => {
      (phase.tasks || []).forEach(task => {
        const taskId = String(task.id || '').trim();
        const sessionId = String(task.sessionId || '').trim();
        if (!taskId || !sessionId) return;
        addTaskSession(taskId, {
          sessionId,
          isSubthread: false,
          confidence: 1,
          matchedBy: 'task_frontmatter',
          source: 'task_frontmatter',
        });
      });
    });

    executionSessions.forEach(session => {
      const relatedTasks = Array.isArray(session.relatedTasks) ? session.relatedTasks : [];
      relatedTasks.forEach(taskRef => {
        const rawTaskId = String(taskRef.taskId || '').trim().toLowerCase();
        if (!rawTaskId) return;
        const resolvedTaskId = taskIdLookup.get(rawTaskId);
        if (!resolvedTaskId) return;

        const targetSessionId = String(taskRef.linkedSessionId || session.sessionId || '').trim();
        if (!targetSessionId) return;

        addTaskSession(resolvedTaskId, {
          sessionId: targetSessionId,
          isSubthread: Boolean(taskRef.linkedSessionId) || Boolean(session.isSubthread),
          confidence: session.confidence || 0,
          matchedBy: String(taskRef.matchedBy || ''),
          source: 'task_tool',
        });
      });
    });

    return byTask;
  }, [executionSessions, phases]);

  const featureHistoryEvents = useMemo(() => {
    if (!featureDetail) return [];
    const events: FeatureHistoryEvent[] = [];

    (featureDetail.timeline || []).forEach((event, idx) => {
      if (!event || !event.timestamp) return;
      events.push({
        id: event.id || `feature-${idx}`,
        timestamp: event.timestamp,
        label: event.label || 'Feature event',
        kind: event.kind || 'feature',
        confidence: event.confidence || 'low',
        source: event.source || `feature:${featureDetail.id}`,
        description: event.description,
      });
    });

    (context?.documents || []).forEach((doc, docIndex) => {
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

    executionSessions.forEach(session => {
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
  }, [context?.documents, executionSessions, featureDetail]);

  const allSessionRoots = useMemo(
    () => buildSessionThreadForest(executionSessions),
    [executionSessions],
  );

  const primarySessionRoots = useMemo(
    () => allSessionRoots.filter(node => isPrimarySession(node.session)),
    [allSessionRoots],
  );

  const secondarySessionRoots = useMemo(
    () => sortThreadNodes(allSessionRoots.filter(node => !isPrimarySession(node.session)), compareSessionsByConfidenceAndTime),
    [allSessionRoots],
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

  const primarySessionCount = useMemo(
    () => countThreadNodes(primarySessionRoots),
    [primarySessionRoots],
  );

  const secondarySessionCount = useMemo(
    () => countThreadNodes(secondarySessionRoots),
    [secondarySessionRoots],
  );

  useEffect(() => {
    if (activeTab !== 'artifacts') return;

    const primarySessionIds = Array.from(new Set(executionSessions.map(session => String(session.sessionId || '').trim()).filter(Boolean)));
    if (primarySessionIds.length === 0) {
      setArtifactSourceSessions([]);
      setArtifactsLoading(false);
      return;
    }

    let cancelled = false;
    setArtifactsLoading(true);

    const loadSessions = async (sessionIds: string[]): Promise<Map<string, AgentSession>> => {
      const sessionMap = new Map<string, AgentSession>();
      const rows = await Promise.all(
        sessionIds.map(async sessionId => {
          try {
            return await getSessionById(sessionId);
          } catch {
            return null;
          }
        }),
      );
      rows.forEach(row => {
        if (row) sessionMap.set(row.id, row);
      });
      return sessionMap;
    };

    void (async () => {
      const sessionMap = await loadSessions(primarySessionIds);
      const linkedThreadIds = new Set<string>();

      sessionMap.forEach(session => {
        (session.logs || []).forEach(log => {
          const linkedId = String(log.linkedSessionId || '').trim();
          if (linkedId) linkedThreadIds.add(linkedId);
        });
      });

      const missingThreadIds = Array.from(linkedThreadIds).filter(sessionId => !sessionMap.has(sessionId));
      if (missingThreadIds.length > 0) {
        const threadMap = await loadSessions(missingThreadIds);
        threadMap.forEach((session, sessionId) => sessionMap.set(sessionId, session));
      }

      if (cancelled) return;
      setArtifactSourceSessions(Array.from(sessionMap.values()));
      setArtifactsLoading(false);
    })().catch(() => {
      if (cancelled) return;
      setArtifactSourceSessions([]);
      setArtifactsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [activeTab, executionSessions, getSessionById]);

  const mergedArtifactSession = useMemo<AgentSession | null>(() => {
    const featureId = context?.feature.id || '';
    if (!featureId || artifactSourceSessions.length === 0) return null;

    const mergedLogs = artifactSourceSessions.flatMap(session =>
      (session.logs || []).map(log => ({
        ...log,
        id: `${session.id}:${log.id}`,
      })),
    );

    const mergedArtifacts = artifactSourceSessions.flatMap(session =>
      (session.linkedArtifacts || []).map(artifact => ({
        ...artifact,
        sourceLogId: artifact.sourceLogId ? `${session.id}:${artifact.sourceLogId}` : artifact.sourceLogId,
      })),
    );

    const startedAtEpochs = artifactSourceSessions
      .map(session => Date.parse(session.startedAt || ''))
      .filter(value => Number.isFinite(value) && value > 0);
    const endedAtEpochs = artifactSourceSessions
      .map(session => Date.parse(session.endedAt || ''))
      .filter(value => Number.isFinite(value) && value > 0);

    const earliestStartedAt = startedAtEpochs.length > 0 ? new Date(Math.min(...startedAtEpochs)).toISOString() : '';
    const latestEndedAt = endedAtEpochs.length > 0 ? new Date(Math.max(...endedAtEpochs)).toISOString() : '';
    const latestUpdatedAt = artifactSourceSessions
      .map(session => session.updatedAt || '')
      .filter(Boolean)
      .sort((a, b) => Date.parse(b) - Date.parse(a))[0] || '';
    const mergedAgents = Array.from(
      new Set(artifactSourceSessions.flatMap(session => session.agentsUsed || []).filter(Boolean)),
    );
    const mergedSkills = Array.from(
      new Set(artifactSourceSessions.flatMap(session => session.skillsUsed || []).filter(Boolean)),
    );

    return {
      id: `feature-artifacts:${featureId}`,
      taskId: featureId,
      status: 'completed',
      model: 'mixed',
      modelDisplayName: 'Mixed Models',
      durationSeconds: artifactSourceSessions.reduce((sum, session) => sum + Number(session.durationSeconds || 0), 0),
      tokensIn: artifactSourceSessions.reduce((sum, session) => sum + Number(session.tokensIn || 0), 0),
      tokensOut: artifactSourceSessions.reduce((sum, session) => sum + Number(session.tokensOut || 0), 0),
      modelIOTokens: artifactSourceSessions.reduce((sum, session) => sum + Number(session.modelIOTokens || 0), 0),
      cacheCreationInputTokens: artifactSourceSessions.reduce((sum, session) => sum + Number(session.cacheCreationInputTokens || 0), 0),
      cacheReadInputTokens: artifactSourceSessions.reduce((sum, session) => sum + Number(session.cacheReadInputTokens || 0), 0),
      cacheInputTokens: artifactSourceSessions.reduce((sum, session) => sum + Number(session.cacheInputTokens || 0), 0),
      observedTokens: artifactSourceSessions.reduce((sum, session) => sum + Number(session.observedTokens || 0), 0),
      toolReportedTokens: artifactSourceSessions.reduce((sum, session) => sum + Number(session.toolReportedTokens || 0), 0),
      totalCost: artifactSourceSessions.reduce((sum, session) => sum + Number(session.totalCost || 0), 0),
      startedAt: earliestStartedAt,
      endedAt: latestEndedAt || undefined,
      updatedAt: latestUpdatedAt || undefined,
      toolsUsed: [],
      logs: mergedLogs,
      linkedArtifacts: mergedArtifacts,
      sessionType: 'feature-artifacts',
      agentsUsed: mergedAgents,
      skillsUsed: mergedSkills,
    };
  }, [artifactSourceSessions, context?.feature.id]);

  const artifactThreadSessions = useMemo(
    () => artifactSourceSessions.filter(session => Boolean(session.parentSessionId) || (session.sessionType || '').toLowerCase() === 'subagent'),
    [artifactSourceSessions],
  );

  const artifactSubagentNameBySessionId = useMemo(() => {
    const names = new Map<string, string>();
    artifactSourceSessions.forEach(session => {
      const label = (session.agentId ? `agent-${session.agentId}` : '') || session.sessionType || '';
      if (label) names.set(session.id, label);
    });
    return names;
  }, [artifactSourceSessions]);

  const renderSessionCard = useCallback((session: FeatureExecutionSessionLink, threadToggle?: {
    expanded: boolean;
    childCount: number;
    onToggle: () => void;
    label?: string;
  }) => {
    const modelBadges = (session.modelsUsed && session.modelsUsed.length > 0)
      ? session.modelsUsed.map(modelInfo => ({
        raw: modelInfo.raw,
        displayName: modelInfo.modelDisplayName,
        provider: modelInfo.modelProvider,
        family: modelInfo.modelFamily,
        version: modelInfo.modelVersion,
      }))
      : [{
        raw: session.model || '',
        displayName: session.modelDisplayName,
        provider: session.modelProvider,
        family: session.modelFamily,
        version: session.modelVersion,
      }];

    const detailSections: SessionCardDetailSection[] = [];
    const linkSignalItems = [
      session.linkStrategy ? formatSessionReason(session.linkStrategy) : '',
      ...(session.reasons || []).map(reason => formatSessionReason(reason)),
    ].filter(Boolean);
    if (linkSignalItems.length > 0) {
      detailSections.push({
        id: `${session.sessionId}-link-signals`,
        label: 'Link Signals',
        items: Array.from(new Set(linkSignalItems)),
      });
    }
    if ((session.commands || []).length > 0) {
      detailSections.push({
        id: `${session.sessionId}-commands`,
        label: 'Commands',
        items: Array.from(new Set(session.commands || [])),
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

    const primaryCommit = session.gitCommitHash || session.gitCommitHashes?.[0] || session.commitHashes?.[0];
    const displayTitle = deriveSessionCardTitle(
      session.sessionId,
      (session.title || '').trim(),
      session.sessionMetadata || null,
    );
    const sessionTokenMetrics = resolveTokenMetrics(session, {
      hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, executionSessions),
    });

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
          raw: session.model || '',
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
        onClick={() => openSession(session.sessionId)}
        className="rounded-lg"
        infoBadges={(
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 text-indigo-300 bg-indigo-500/10">
              {Math.round((session.confidence || 0) * 100)}% confidence
            </span>
            {sessionTokenMetrics.cacheInputTokens > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/25 text-cyan-200 bg-cyan-500/10">
                Cache {formatPercent(sessionTokenMetrics.cacheShare, 0)}
              </span>
            )}
          </div>
        )}
        headerRight={(
          <div className="flex items-center gap-3 text-right">
            <div>
              <div className="text-[9px] text-slate-600 uppercase">Workload</div>
              <div className="text-xs font-mono text-sky-300">{formatTokenCount(sessionTokenMetrics.workloadTokens)}</div>
            </div>
            <div>
              <div className="text-[9px] text-slate-600 uppercase">Cost</div>
              <div className="text-xs font-mono text-emerald-400">${Number(session.totalCost || 0).toFixed(2)}</div>
            </div>
            <div>
              <div className="text-[9px] text-slate-600 uppercase">Duration</div>
              <div className="text-xs font-mono text-slate-400">{Math.round(Number(session.durationSeconds || 0) / 60)}m</div>
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
      />
    );
  }, [openSession]);

  const renderSessionTreeNode = useCallback((node: FeatureSessionTreeNode, depth = 0): React.ReactNode => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedSubthreadsBySessionId.has(node.session.sessionId);

    return (
      <div key={node.session.sessionId} className="space-y-2">
        {renderSessionCard(
          node.session,
          hasChildren ? {
            expanded: isExpanded,
            childCount: countThreadNodes(node.children),
            onToggle: () => {
              setExpandedSubthreadsBySessionId(prev => {
                const next = new Set(prev);
                if (next.has(node.session.sessionId)) next.delete(node.session.sessionId);
                else next.add(node.session.sessionId);
                return next;
              });
            },
            label: 'Sub-Threads',
          } : undefined,
        )}
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
  }, [expandedSubthreadsBySessionId, renderSessionCard]);

  const isSessionActive = useMemo(
    () => executionSessions.some(session => {
      const normalized = String(session.status || '').toLowerCase();
      return normalized === 'active' || normalized === 'running';
    }),
    [executionSessions],
  );

  const visibleTabItems = useMemo(
    () => TAB_ITEMS.filter(tab => tab.id !== 'test-status' || hasFeatureTestRuns),
    [hasFeatureTestRuns],
  );

  useEffect(() => {
    if (activeTab === 'test-status' && !hasFeatureTestRuns) {
      setActiveTab('overview');
    }
  }, [activeTab, hasFeatureTestRuns]);

  if (!loading && !context && !error) {
    return (
      <div className="space-y-5">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 md:p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-xl md:text-2xl font-bold text-slate-100">Feature Execution Workbench</h1>
              <p className="text-sm text-slate-400 mt-1">
                Unified context and deterministic next-command guidance for feature delivery.
              </p>
            </div>
            <div className="w-full md:w-[460px] grid grid-cols-1 md:grid-cols-[1fr_180px] gap-2">
              <label className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="Search feature"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-9 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </label>
              <select
                value={selectedFeatureId}
                onChange={event => selectFeature(event.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
              >
                {!selectedFeatureId && <option value="">Select feature</option>}
                {filteredFeatures.map(feature => (
                  <option key={feature.id} value={feature.id}>{feature.name}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-400 flex items-center gap-2">
          <Command size={16} />
          Select a feature to load execution guidance.
          <button
            onClick={() => void refreshFeatures()}
            className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-slate-700 text-slate-300 hover:border-slate-500 text-xs"
          >
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 md:p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-100">Feature Execution Workbench</h1>
            <p className="text-sm text-slate-400 mt-1">
              Unified context and deterministic next-command guidance for feature delivery.
            </p>
          </div>

          <div className="w-full md:w-[460px] grid grid-cols-1 md:grid-cols-[1fr_180px] gap-2">
            <label className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Search feature"
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-9 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
              />
            </label>

            <select
              value={selectedFeatureId}
              onChange={event => selectFeature(event.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            >
              {!selectedFeatureId && <option value="">Select feature</option>}
              {filteredFeatures.map(feature => (
                <option key={feature.id} value={feature.id}>
                  {feature.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <Link to="/board" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Board</Link>
          <Link to="/plans" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Plans</Link>
          <Link to="/sessions" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Sessions</Link>
          <Link to="/analytics" className="px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500">Analytics</Link>
        </div>
      </div>

      {loading && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-400 flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" />
          Loading execution context...
        </div>
      )}

      {!loading && error && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 text-rose-200 text-sm">
          {error}
        </div>
      )}

      {!loading && context && (
        <div className="space-y-4">
          {context.warnings.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 space-y-1">
              {context.warnings.map((warning, idx) => (
                <p key={`${warning.section}-${idx}`} className="text-xs text-amber-200">
                  <span className="font-semibold uppercase mr-2">{warning.section}</span>
                  {warning.message}
                </p>
              ))}
            </div>
          )}

          <div className="space-y-4">
            <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[390px_minmax(0,1fr)]">
            <section className="h-fit space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-4 xl:sticky xl:top-0">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-slate-400">Recommendation</p>
                  <h2 className="text-lg font-semibold text-slate-100 mt-1">Next Command</h2>
                </div>
                <span className="text-[10px] font-bold px-2 py-1 rounded border border-indigo-500/40 text-indigo-200 bg-indigo-500/20">
                  {context.recommendations.ruleId}
                </span>
              </div>

              <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-2">Primary</p>
                <code className="text-sm text-emerald-300 block whitespace-pre-wrap break-all">{context.recommendations.primary.command}</code>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => void openRunReview(context.recommendations.primary.command, context.recommendations.primary.ruleId)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-500/40 bg-emerald-500/20 text-emerald-100 text-xs font-semibold hover:bg-emerald-500/30"
                >
                  <Play size={14} />
                  Run in Workbench
                </button>
                <button
                  onClick={() => handleCopyCommand(context.recommendations.primary.command)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-indigo-500/40 bg-indigo-500/20 text-indigo-100 text-xs font-semibold hover:bg-indigo-500/30"
                >
                  <Clipboard size={14} />
                  {copiedCommand === context.recommendations.primary.command ? 'Copied' : 'Copy Command'}
                </button>
                <button
                  onClick={openSourceDoc}
                  disabled={!sourceDocPath}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-700 text-slate-200 text-xs font-semibold enabled:hover:border-slate-500 disabled:opacity-50"
                >
                  <ExternalLink size={14} />
                  Open Source Doc
                </button>
              </div>

              <p className="text-sm text-slate-300 leading-relaxed">{context.recommendations.explanation}</p>

              {context.recommendations.alternatives.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Alternatives</p>
                  {context.recommendations.alternatives.map(option => (
                    <div key={option.command} className="rounded-lg border border-slate-700/80 p-2.5 bg-slate-950/70">
                      <code className="text-xs text-cyan-200 block whitespace-pre-wrap break-all">{option.command}</code>
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <span className="text-[10px] text-slate-500">{option.ruleId}</span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => void openRunReview(option.command, option.ruleId)}
                            className="text-[11px] text-emerald-300 hover:text-emerald-200"
                          >
                            Run
                          </button>
                          <button
                            onClick={() => handleCopyCommand(option.command)}
                            className="text-[11px] text-slate-300 hover:text-white"
                          >
                            Copy
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {runActionError && (
                <div className="rounded border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-200">
                  {runActionError}
                </div>
              )}

              <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Evidence</p>
                <ul className="space-y-1.5">
                  {context.recommendations.evidence.map(item => {
                    const rawPath = (item.sourcePath || (isPathLike(item.value) ? item.value : '')).trim();
                    const parsed = parseEvidenceToken(item.value);
                    const structuredLabel = rawPath
                      ? (humanizeEvidenceKey(parsed.key) || 'Document')
                      : (humanizeEvidenceKey(parsed.key) || item.label?.trim() || 'Evidence');
                    const structuredValue = parsed.key ? parsed.tokenValue : item.value;
                    const displayValue = rawPath ? fileNameFromPath(rawPath) : structuredValue;
                    const tooltipValue = rawPath || structuredValue || item.value;
                    const clickableToken = rawPath || (parsed.key ? `${parsed.key}:${parsed.tokenValue}` : item.value);
                    const isClickable = Boolean(rawPath)
                      || parsed.key === 'feature'
                      || parsed.key === 'active_phase'
                      || parsed.key === 'next_phase'
                      || parsed.key === 'highest_completed_phase';
                    return (
                      <li key={item.id} className="text-xs text-slate-300 flex items-center gap-2 min-w-0">
                        <span className="shrink-0 max-w-[140px] truncate text-[11px] text-slate-500" title={structuredLabel}>
                          {structuredLabel}:
                        </span>
                        {isClickable ? (
                          <button
                            onClick={() => openEvidenceLink(clickableToken)}
                            title={tooltipValue}
                            className="min-w-0 flex-1 truncate text-left text-cyan-200 hover:text-cyan-100"
                          >
                            {displayValue}
                          </button>
                        ) : (
                          <span className="min-w-0 flex-1 truncate" title={tooltipValue}>
                            {displayValue}
                          </span>
                        )}
                        <span className="shrink-0 max-w-[96px] truncate text-[10px] uppercase text-slate-500" title={item.sourceType}>
                          {item.sourceType}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>

            </section>

            <section className="min-w-0 overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-4 min-h-[42rem] h-[clamp(42rem,74vh,58rem)] flex flex-col">
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
                {visibleTabItems.map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border ${
                      activeTab === tab.id
                        ? 'border-indigo-500/50 bg-indigo-500/20 text-indigo-100'
                        : 'border-slate-700 text-slate-300 hover:border-slate-500'
                    }`}
                  >
                    <tab.icon size={13} />
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="mt-4 min-h-0 flex-1 overflow-hidden">
              {activeTab === 'overview' && featureDetail && (
                <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pr-1 xl:grid xl:grid-cols-[minmax(0,1.12fr)_minmax(20rem,0.88fr)] xl:overflow-hidden xl:pr-0">
                  <div className="space-y-4 xl:min-h-0 xl:overflow-y-auto xl:pr-1">
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                    <button
                      onClick={() => openBoardFeature(featureDetail.id, 'overview')}
                      className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-left hover:border-indigo-500/40"
                    >
                      <p className="text-[11px] text-slate-500 uppercase">Feature</p>
                      <p className="text-sm text-slate-100 font-semibold mt-1 truncate">{featureDetail.name}</p>
                      <p className="text-xs text-slate-500 mt-1 truncate">{featureDetail.id}</p>
                    </button>
                    <button
                      onClick={() => openBoardFeature(featureDetail.id, 'overview')}
                      className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-left hover:border-indigo-500/40"
                    >
                      <p className="text-[11px] text-slate-500 uppercase">Status</p>
                      <p className="text-sm text-slate-100 font-semibold mt-1">{formatStatus(featureDetail.status)}</p>
                      <p className="text-xs text-slate-500 mt-1">Updated {formatDateTime(featureDetail.updatedAt)}</p>
                    </button>
                    <button
                      onClick={() => openBoardFeature(featureDetail.id, 'phases')}
                      className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-left hover:border-indigo-500/40"
                    >
                      <p className="text-[11px] text-slate-500 uppercase">Tasks</p>
                      <p className="text-sm text-slate-100 font-semibold mt-1">
                        {featureDetail.completedTasks}/{featureDetail.totalTasks}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">Across {featureDetail.phases.length} phases</p>
                    </button>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Generated</p>
                      <p className="text-sm text-slate-100 font-semibold mt-1">{formatDateTime(context.generatedAt)}</p>
                      <p className="text-xs text-slate-500 mt-1">Rule confidence {Math.round(context.recommendations.confidence * 100)}%</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Feature Metadata</p>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="text-slate-400">Priority <span className="text-slate-200 ml-1">{featureDetail.priority || '-'}</span></div>
                        <div className="text-slate-400">Risk <span className="text-slate-200 ml-1">{featureDetail.riskLevel || '-'}</span></div>
                        <div className="text-slate-400">Complexity <span className="text-slate-200 ml-1">{featureDetail.complexity || '-'}</span></div>
                        <div className="text-slate-400">Track <span className="text-slate-200 ml-1">{featureDetail.track || '-'}</span></div>
                        <div className="text-slate-400">Readiness <span className="text-slate-200 ml-1">{featureDetail.executionReadiness || '-'}</span></div>
                        <div className="text-slate-400">Coverage <span className="text-slate-200 ml-1">{getFeatureCoverageSummary(featureDetail)}</span></div>
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Relation Signals</p>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="text-slate-400">Typed links <span className="text-slate-200 ml-1">{getFeatureLinkedFeatureCount(featureDetail)}</span></div>
                        <div className="text-slate-400">Related IDs <span className="text-slate-200 ml-1">{featureDetail.relatedFeatures.length}</span></div>
                        <div className="text-slate-400">Blockers <span className="text-slate-200 ml-1">{featureDetail.qualitySignals?.blockerCount ?? 0}</span></div>
                        <div className="text-slate-400">At Risk <span className="text-slate-200 ml-1">{featureDetail.qualitySignals?.atRiskTaskCount ?? 0}</span></div>
                      </div>
                      {(featureDetail.qualitySignals?.integritySignalRefs || []).length > 0 && (
                        <p className="text-[11px] text-slate-500 mt-2">
                          Integrity refs: {(featureDetail.qualitySignals?.integritySignalRefs || []).join(', ')}
                        </p>
                      )}
                    </div>
                  </div>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4 xl:min-w-0">
                    <div className="flex min-h-[16rem] flex-1 flex-col overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Typed Related Features</p>
                      {(featureDetail.linkedFeatures || []).length > 0 ? (
                        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
                          {(featureDetail.linkedFeatures || []).map((relation, index) => (
                            <div key={`${relation.feature}-${relation.type}-${relation.source}-${index}`} className="flex flex-wrap items-center gap-2 text-xs">
                              <button
                                onClick={() => openBoardFeature(relation.feature, 'overview')}
                                className="font-mono text-indigo-300 hover:text-indigo-200 [overflow-wrap:anywhere]"
                              >
                                {relation.feature}
                              </button>
                              <span className="uppercase px-1.5 py-0.5 rounded border border-slate-700 bg-slate-900 text-slate-300">{relation.type || 'related'}</span>
                              <span className="uppercase px-1.5 py-0.5 rounded border border-slate-700 bg-slate-900 text-slate-400">{relation.source || 'unknown'}</span>
                              {typeof relation.confidence === 'number' && (
                                <span className="text-slate-500">{Math.round(relation.confidence * 100)}%</span>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex flex-1 items-center rounded-lg border border-dashed border-slate-800 px-3 text-sm text-slate-500">
                          No typed feature relations were detected for this feature.
                        </div>
                      )}
                    </div>

                    <div className="shrink-0 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Related Features</p>
                      {featureDetail.relatedFeatures.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {featureDetail.relatedFeatures.map(featureId => (
                            <button
                              key={featureId}
                              onClick={() => openBoardFeature(featureId, 'overview')}
                              className="text-xs px-2 py-1 rounded border border-slate-700 bg-slate-900 text-indigo-300 hover:border-indigo-500/40 [overflow-wrap:anywhere]"
                            >
                              {featureId}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-500">No secondary related feature IDs were attached.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'runs' && (
                <div className="h-full overflow-y-auto pr-1 space-y-3">
                  {runsError && (
                    <div className="rounded border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-200">
                      {runsError}
                    </div>
                  )}
                  <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-3">
                    <ExecutionRunHistory
                      runs={executionRuns}
                      selectedRunId={selectedRunId}
                      loading={runsLoading}
                      onSelect={setSelectedRunId}
                      onRefresh={() => { void refreshExecutionRuns(context.feature.id); }}
                    />
                    <ExecutionRunPanel
                      run={selectedRun}
                      events={selectedRunEvents}
                      loading={selectedRunEventsLoading || runActionLoading}
                      onCancel={run => { void handleCancelRun(run); }}
                      onRetry={run => { void handleRetryRun(run); }}
                      onOpenApproval={run => {
                        setApprovalRun(run);
                        setApprovalOpen(true);
                      }}
                    />
                  </div>
                </div>
              )}

              {activeTab === 'phases' && (
                <div className="h-full overflow-y-auto pr-1 space-y-3">
                  {fullFeatureLoading && (
                    <div className="text-xs text-slate-400 flex items-center gap-2">
                      <Loader2 size={13} className="animate-spin" />
                      Loading full phase/task detail...
                    </div>
                  )}
                  {phases.length === 0 && (
                    <p className="text-sm text-slate-400">No phase details available.</p>
                  )}
                  {phases.map(phase => {
                    const phaseKey = phase.id || phase.phase;
                    const isExpanded = expandedPhases.has(phaseKey);
                    const phaseTasks = dedupePhaseTasks(phase.tasks || []);
                    const phaseRelatedSessions = phaseSessionLinks.get(String(phase.phase || '').trim()) || [];
                    const pendingTasks = getPhasePendingTasks(phase);
                    return (
                      <div key={phaseKey} className="rounded-lg border border-slate-800 bg-slate-950/40 overflow-hidden">
                        <div className="w-full px-3 py-3 text-left hover:bg-slate-900/60">
                          <div className="flex items-start gap-2">
                            <button
                              onClick={() => {
                                setExpandedPhases(prev => {
                                  const next = new Set(prev);
                                  if (next.has(phaseKey)) next.delete(phaseKey);
                                  else next.add(phaseKey);
                                  return next;
                                });
                              }}
                              className="mt-0.5 text-slate-400 hover:text-slate-200"
                              title={isExpanded ? 'Collapse phase' : 'Expand phase'}
                            >
                              {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-2">
                                <button
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    if (featureDetail) openBoardFeature(featureDetail.id, 'phases');
                                  }}
                                  className="text-sm font-semibold text-slate-100 hover:text-indigo-300 truncate"
                                >
                                  Phase {phase.phase}: {phase.title || 'Untitled'}
                                </button>
                                <span className="text-xs text-slate-300 shrink-0">
                                  {phase.completedTasks}/{phase.totalTasks}
                                </span>
                              </div>
                              <p className="text-xs text-slate-400 mt-1">Status: {formatStatus(phase.status)}</p>
                              <div className="mt-2 h-2 rounded bg-slate-800 overflow-hidden">
                                <div className="h-full bg-indigo-500" style={{ width: `${Math.max(0, Math.min(100, phase.progress || 0))}%` }} />
                              </div>
                              <p className="text-xs text-slate-400 mt-2">Next unresolved tasks: {pendingTasks}</p>
                              {phaseRelatedSessions.length > 0 && (
                                <div className="mt-2 flex flex-wrap items-center gap-1">
                                  <span className="text-[10px] uppercase tracking-wider text-slate-500">Sessions</span>
                                  {phaseRelatedSessions.slice(0, 4).map(link => (
                                    <button
                                      key={`${phaseKey}-${link.sessionId}`}
                                      onClick={event => {
                                        event.stopPropagation();
                                        openSession(link.sessionId);
                                      }}
                                      className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 font-mono hover:bg-indigo-500/20"
                                    >
                                      {link.sessionId}
                                    </button>
                                  ))}
                                  {phaseRelatedSessions.length > 4 && (
                                    <span className="text-[10px] text-slate-500">+{phaseRelatedSessions.length - 4} more</span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className="border-t border-slate-800 px-3 py-2 bg-slate-950/60 space-y-1.5 overflow-hidden">
                            {phaseTasks.length === 0 && (
                              <p className="text-xs text-slate-500 italic">No task details currently available for this phase.</p>
                            )}
                            {phaseTasks.map(task => {
                              const taskLinks = taskSessionLinksByTaskId.get(String(task.id || '').trim()) || [];
                              const statusStyle = getFeatureStatusStyle(task.status || 'backlog');
                              return (
                                <div key={`${phaseKey}-${task.id}`} className="w-full max-w-full rounded px-2 py-1.5 hover:bg-slate-900/70 min-w-0 overflow-hidden">
                                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 min-w-0 w-full max-w-full overflow-hidden">
                                    <div className="flex items-center gap-2 min-w-0 overflow-hidden">
                                      <button
                                        onClick={() => featureDetail && openBoardFeature(featureDetail.id, 'phases')}
                                        className="font-mono text-[10px] text-slate-500 max-w-16 shrink-0 text-left hover:text-indigo-300 truncate"
                                        title={task.id}
                                      >
                                        {task.id}
                                      </button>
                                      <button
                                        onClick={() => featureDetail && openBoardFeature(featureDetail.id, 'phases')}
                                        className="text-sm text-slate-300 flex-1 min-w-0 truncate text-left hover:text-indigo-300 block w-full"
                                        title={task.title}
                                      >
                                        {task.title}
                                      </button>
                                    </div>
                                    <span className={`text-[10px] uppercase font-bold shrink-0 ${statusStyle.color}`}>
                                      {statusStyle.label}
                                    </span>
                                  </div>
                                  {taskLinks.length > 0 && (
                                    <div className="mt-1 pl-16 min-w-0 max-w-full overflow-hidden">
                                      <div className="flex items-center gap-1 flex-wrap min-w-0 max-w-full">
                                      {taskLinks.slice(0, 3).map(link => (
                                        <button
                                          key={`${task.id}-session-${link.sessionId}-${link.source}`}
                                          onClick={() => openSession(link.sessionId)}
                                          className={`text-[10px] px-1.5 py-0.5 rounded border font-mono truncate max-w-[150px] ${link.isSubthread
                                            ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                                            : 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30'
                                            }`}
                                          title={link.sessionId}
                                        >
                                          {link.sessionId}
                                        </button>
                                      ))}
                                      {taskLinks.length > 3 && (
                                        <span className="text-[10px] text-slate-500">+{taskLinks.length - 3}</span>
                                      )}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {activeTab === 'documents' && (
                <div className="h-full overflow-y-auto pr-1 space-y-2">
                  {context.documents.length === 0 && <p className="text-sm text-slate-400">No correlated documents found.</p>}
                  {context.documents.map(doc => (
                    <button
                      key={doc.id}
                      onClick={() => {
                        void trackExecutionEvent({
                          eventType: 'execution_source_link_clicked',
                          featureId: context.feature.id,
                          metadata: { path: doc.filePath },
                        });
                        openLinkedDoc(doc);
                      }}
                      className="w-full text-left rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 hover:border-slate-600"
                    >
                      <p className="text-sm text-slate-100 font-medium">{doc.title}</p>
                      <p className="text-xs text-slate-400 mt-1 truncate">{doc.docType} · {doc.filePath}</p>
                    </button>
                  ))}
                </div>
              )}

              {activeTab === 'sessions' && (
                <div className="h-full overflow-y-auto pr-1 space-y-3">
                  {executionSessions.length === 0 && <p className="text-sm text-slate-400">No linked sessions available.</p>}
                  {executionSessions.length > 0 && (
                    <>
                      <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-bold uppercase tracking-wider text-emerald-300">Core Focus Sessions</div>
                          <div className="text-[11px] text-emerald-200/80">{primarySessionCount}</div>
                        </div>
                        <p className="text-[11px] text-emerald-200/70 mt-1">Likely primary execution/planning sessions for this feature.</p>
                      </div>

                      {coreSessionGroups.map(group => (
                        <div key={group.id} className="space-y-2">
                          <button
                            onClick={() => setCoreSessionGroupExpanded(prev => ({ ...prev, [group.id]: !prev[group.id] }))}
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

              {activeTab === 'artifacts' && (
                <div className="h-full overflow-y-auto pr-1 space-y-3">
                  {artifactsLoading && (
                    <div className="text-xs text-slate-400 flex items-center gap-2">
                      <Loader2 size={13} className="animate-spin" />
                      Loading linked session artifacts...
                    </div>
                  )}
                  {!artifactsLoading && mergedArtifactSession && (
                    <SessionArtifactsView
                      session={mergedArtifactSession}
                      threadSessions={artifactThreadSessions}
                      subagentNameBySessionId={artifactSubagentNameBySessionId}
                      onOpenThread={openSession}
                    />
                  )}
                  {!artifactsLoading && !mergedArtifactSession && (
                    <div className="text-sm text-slate-400">No linked artifacts found for this feature yet.</div>
                  )}
                </div>
              )}

              {activeTab === 'history' && (
                <div className="h-full overflow-y-auto pr-1 space-y-3">
                  {featureHistoryEvents.length === 0 && (
                    <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                      <Calendar size={32} className="mx-auto mb-3 opacity-50" />
                      <p>No timeline events available yet.</p>
                    </div>
                  )}
                  {featureHistoryEvents.map(event => {
                    const source = (event.source || '').trim();
                    const isSession = source.startsWith('session:');
                    const isDocument = source.startsWith('document:');
                    const isFeature = source.startsWith('feature:');
                    const onOpen = () => {
                      if (isSession) {
                        openSession(source.slice('session:'.length));
                        return;
                      }
                      if (isDocument) {
                        openDocFromPath(source.slice('document:'.length));
                        return;
                      }
                      if (isFeature && featureDetail) {
                        openBoardFeature(featureDetail.id, 'history');
                      }
                    };
                    return (
                      <button
                        key={event.id}
                        onClick={onOpen}
                        className={`w-full text-left bg-slate-900 border border-slate-800 rounded-lg p-3 ${isSession || isDocument || isFeature ? 'hover:border-indigo-500/30' : ''}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm text-slate-200">{event.label}</div>
                          <div className="text-xs text-slate-500">{new Date(event.timestamp).toLocaleString()}</div>
                        </div>
                        <div className="mt-1 text-[11px] text-slate-500 flex flex-wrap items-center gap-2">
                          <span className="uppercase px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/70">{event.kind}</span>
                          <span className="uppercase px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/70">{event.confidence}</span>
                          <span className="font-mono truncate">{event.source}</span>
                        </div>
                        {event.description && <p className="mt-2 text-xs text-slate-500">{event.description}</p>}
                      </button>
                    );
                  })}
                </div>
              )}

              {activeTab === 'analytics' && (
                <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Sessions</p>
                      <p className="text-lg text-slate-100 font-semibold mt-1">{context.analytics.sessionCount}</p>
                      <p className="text-xs text-slate-500 mt-1">Primary {context.analytics.primarySessionCount}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Observed Workload</p>
                      <p className="text-lg text-slate-100 font-semibold mt-1">{formatTokenCount(executionWorkload.workloadTokens)}</p>
                      <p className="text-xs text-slate-500 mt-1">
                        {formatTokenCount(executionWorkload.cacheInputTokens)} cache input
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Session Cost</p>
                      <p className="text-lg text-slate-100 font-semibold mt-1">${context.analytics.totalSessionCost.toFixed(2)}</p>
                      <p className="text-xs text-slate-500 mt-1">{formatTokenCount(executionWorkload.modelIOTokens)} model IO tokens</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Telemetry</p>
                      <p className="text-lg text-slate-100 font-semibold mt-1">{context.analytics.artifactEventCount} artifacts</p>
                      <p className="text-xs text-slate-500 mt-1">
                        {context.analytics.commandEventCount} command events
                        {executionWorkload.toolFallbackSessions > 0 ? ` • ${executionWorkload.toolFallbackSessions} tool fallback` : ''}
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-[11px] text-slate-500 uppercase">Last Event</p>
                      <p className="text-sm text-slate-100 mt-1">{formatDateTime(context.analytics.lastEventAt)}</p>
                    </div>
                  </div>

                  <div className="min-h-0 overflow-hidden">
                    {workflowAnalyticsAvailable ? (
                      <WorkflowEffectivenessSurface
                        embedded
                        featureId={context.feature.id}
                        description="Feature-scoped effectiveness rolls historical stack evidence, observed workflow quality, and failure patterns into one comparison surface."
                        onOpenSession={openSession}
                      />
                    ) : (
                      <IntelligenceDisabledNotice
                        title="Workflow Intelligence Disabled"
                        message="Workflow effectiveness analytics are disabled for this project. Session and execution summaries are still available."
                      />
                    )}
                  </div>

                  {workflowAnalyticsAvailable && (
                    <div className="flex justify-end">
                      <button
                        onClick={() => navigate('/analytics?tab=workflow_intelligence')}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500"
                      >
                        <ExternalLink size={13} />
                        Open Full Analytics
                      </button>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'test-status' && context.feature && (
                <div className="h-full overflow-y-auto pr-1">
                  {activeProject?.id ? (
                    <TestStatusView
                      projectId={activeProject.id}
                      filter={{ featureId: context.feature.id }}
                      mode="tab"
                      isLive={isSessionActive}
                      onNavigateToTestingPage={() => navigate(`/tests?featureId=${encodeURIComponent(context.feature.id)}`)}
                    />
                  ) : (
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
                      Select an active project to view test status.
                    </div>
                  )}
                </div>
              )}
              </div>
            </section>
            </div>

            {stackRecommendationsAvailable ? (
              <RecommendedStackCard
                recommendedStack={context.recommendedStack}
                stackAlternatives={context.stackAlternatives}
                stackEvidence={context.stackEvidence}
                definitionResolutionWarnings={context.definitionResolutionWarnings}
                onOpenSession={openSession}
                onOpenFeature={(featureId) => openBoardFeature(featureId, 'overview')}
              />
            ) : (
              <IntelligenceDisabledNotice
                title="Recommended Stack Disabled"
                message="Project settings have disabled historical stack recommendations. Command guidance and execution runs remain available."
              />
            )}
          </div>
        </div>
      )}

      {reviewOpen && (
        <div className="fixed inset-0 z-[75] bg-black/50 backdrop-blur-[1px] flex items-center justify-center p-4">
          <div className="w-full max-w-3xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-100">
                <Terminal size={15} />
                <h3 className="text-sm font-semibold">Review and Launch Run</h3>
              </div>
              <button
                onClick={() => setReviewOpen(false)}
                disabled={runActionLoading}
                className="p-1 rounded border border-slate-700 text-slate-300 hover:border-slate-500 disabled:opacity-50"
                aria-label="Close review dialog"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-4">
              <label className="block">
                <span className="text-[11px] uppercase tracking-wide text-slate-500">Command</span>
                <textarea
                  rows={3}
                  value={reviewCommand}
                  onChange={event => setReviewCommand(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </label>

              <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-3">
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wide text-slate-500">Working Directory</span>
                  <input
                    value={reviewCwd}
                    onChange={event => setReviewCwd(event.target.value)}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] uppercase tracking-wide text-slate-500">Env Profile</span>
                  <select
                    value={reviewEnvProfile}
                    onChange={event => setReviewEnvProfile(event.target.value)}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  >
                    <option value="default">default</option>
                    <option value="minimal">minimal</option>
                    <option value="project">project</option>
                    <option value="ci">ci</option>
                  </select>
                </label>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Policy Evaluation</p>
                  <button
                    onClick={() => { void recheckReviewPolicy(); }}
                    disabled={reviewLoading || runActionLoading}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-700 text-slate-300 text-[11px] hover:border-slate-500 disabled:opacity-50"
                  >
                    <RefreshCw size={12} className={reviewLoading ? 'animate-spin' : ''} />
                    Re-check
                  </button>
                </div>

                {reviewLoading && (
                  <div className="text-xs text-slate-400 inline-flex items-center gap-1.5">
                    <Loader2 size={12} className="animate-spin" />
                    Evaluating command policy...
                  </div>
                )}

                {!reviewLoading && reviewPolicy && (
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`text-[10px] uppercase px-2 py-0.5 rounded border font-semibold ${executionVerdictClass(reviewPolicy.verdict)}`}>
                        verdict: {reviewPolicy.verdict}
                      </span>
                      <span className={`text-[10px] uppercase px-2 py-0.5 rounded border font-semibold ${executionRiskClass(reviewPolicy.riskLevel)}`}>
                        risk: {reviewPolicy.riskLevel}
                      </span>
                      {reviewPolicy.requiresApproval && (
                        <span className="text-[10px] uppercase px-2 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-200">
                          approval required
                        </span>
                      )}
                    </div>
                    {reviewPolicy.reasonCodes.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {reviewPolicy.reasonCodes.map(reason => (
                          <span
                            key={reason}
                            className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 bg-slate-900 text-slate-300 font-mono"
                          >
                            {reason}
                          </span>
                        ))}
                      </div>
                    )}
                    {reviewPolicy.verdict === 'deny' && (
                      <div className="rounded border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-200 inline-flex items-start gap-2">
                        <ShieldAlert size={13} className="mt-0.5 shrink-0" />
                        Command is blocked by policy. Adjust command, cwd, or env profile and re-check before running.
                      </div>
                    )}
                  </div>
                )}
              </div>

              {runActionError && (
                <div className="rounded border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-200">
                  {runActionError}
                </div>
              )}
            </div>

            <div className="px-4 py-3 border-t border-slate-800 flex items-center justify-between gap-2">
              <div className="text-[11px] text-slate-500">
                Rule: <span className="font-mono text-slate-400">{reviewRuleId || 'manual'}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setReviewOpen(false)}
                  disabled={runActionLoading}
                  className="px-3 py-1.5 rounded border border-slate-700 text-slate-200 text-xs hover:border-slate-500 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => { void handleLaunchReviewRun(); }}
                  disabled={runActionLoading || reviewLoading || !reviewCommand.trim() || reviewPolicy?.verdict === 'deny'}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-emerald-500/40 bg-emerald-500/15 text-emerald-100 text-xs disabled:opacity-50"
                >
                  {runActionLoading ? <Loader2 size={12} className="animate-spin" /> : <Play size={13} />}
                  Launch Run
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ExecutionApprovalDialog
        open={approvalOpen}
        run={approvalRun}
        loading={runActionLoading}
        onClose={() => {
          if (runActionLoading) return;
          setApprovalOpen(false);
          setApprovalRun(null);
        }}
        onSubmit={(decision, reason) => {
          void handleApprovalSubmit(decision, reason);
        }}
      />

      {viewingDoc && (
        <DocumentModal
          doc={viewingDoc}
          onClose={() => setViewingDoc(null)}
          onBack={() => setViewingDoc(null)}
          backLabel="Back to execution"
          zIndexClassName="z-[60]"
        />
      )}
    </div>
  );
};
