
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useData } from '../contexts/DataContext';
import { useFeatureSurface } from '../services/useFeatureSurface';
import {
  ExecutionGateStateValue,
  Feature,
  FeatureDependencyEvidence,
  FeatureFamilyItem,
  FeatureFamilyPosition,
  FeaturePhase,
  FeatureTestHealth,
  LinkedDocument,
  PlanDocument,
  ProjectTask,
  SessionModelInfo,
} from '../types';
import { trackExecutionEvent } from '../services/execution';
import { getFeatureHealth } from '../services/testVisualizer';
import { SessionCard, SessionCardDetailSection, deriveSessionCardTitle } from './SessionCard';
import { DocumentModal } from './DocumentModal';
import { UnifiedContentViewer } from './content/UnifiedContentViewer';
import { SidebarFiltersPortal, SidebarFiltersSection } from './SidebarFilters';
import { FeatureModalTestStatus } from './TestVisualizer/FeatureModalTestStatus';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Surface } from './ui/surface';
import {
  X, FileText, Calendar, ChevronRight, ChevronDown, LayoutGrid, List,
  Search, Filter, CheckCircle2, Circle, CircleDashed, Layers, Box,
  FolderOpen, ExternalLink, Tag, ClipboardList, BarChart3, RefreshCw,
  Terminal, GitCommit, GitBranch, Link2, Play, TestTube2,
} from 'lucide-react';
import { FEATURE_STATUS_OPTIONS, getFeatureStatusStyle } from './featureStatus';
import { EffectiveStatusChips, MismatchBadge, PlanningNodeTypeIcon } from '@/components/shared/PlanningMetadata';
import { getMotionPreset, useAnimatedListDiff, useReducedMotionPreference } from './animations';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../lib/tokenMetrics';
import { resolveDisplayCost } from '../lib/sessionSemantics';
import {
  featureTopic,
  isFeatureLiveUpdatesEnabled,
  projectFeaturesTopic,
  useLiveInvalidation,
} from '../services/live';
import {
  isPlanningFeatureModalTab,
  planningFeatureDetailHref,
  planningFeatureModalHref,
  type PlanningFeatureModalTab,
} from '../services/planningRoutes';
import { invalidateFeatureSurface } from '../services/featureSurfaceCache';
// P4-011: publish feature-write events so BOTH caches are invalidated via the
// featureCacheBus.  The explicit invalidateFeatureSurface() call below is kept
// as a belt-and-suspenders guard for React state reset; the bus handles the
// planning cache.  See feature-surface-planning-cache-coordination.md
import { publishFeatureWriteEvent } from '../services/featureCacheBus';
import {
  cardDTOBoardStage,
  cardDTOToFeature,
  rollupToSessionSummary,
} from './featureCardAdapters';
import type { FeatureCardDTO } from '../services/featureSurface';
import { getLegacyFeatureDetail, getFeatureLinkedSessionPage, getFeatureTaskSource } from '../services/featureSurface';
import { useFeatureModalData, type ModalTabId } from '../services/useFeatureModalData';
import { TabStateView } from './FeatureModal/TabStateView';
import { isFeatureSurfaceV2Enabled } from '../services/featureSurfaceFlag';
import { useAppRuntime } from '../contexts/AppRuntimeContext';

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
  tokensIn?: number;
  tokensOut?: number;
  modelIOTokens?: number;
  cacheCreationInputTokens?: number;
  cacheReadInputTokens?: number;
  cacheInputTokens?: number;
  observedTokens?: number;
  toolReportedTokens?: number;
  currentContextTokens?: number;
  contextWindowSize?: number;
  contextUtilizationPct?: number;
  cacheShare?: number;
  outputShare?: number;
  reportedCostUsd?: number | null;
  recalculatedCostUsd?: number | null;
  displayCostUsd?: number | null;
  costProvenance?: 'reported' | 'recalculated' | 'estimated' | 'unknown';
  costConfidence?: number;
  costMismatchPct?: number | null;
  pricingModelSource?: string;
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  gitBranch?: string;
  pullRequests?: Array<{
    prNumber?: string;
    prUrl?: string;
    prRepository?: string;
  }>;
  sessionType?: string;
  parentSessionId?: string | null;
  rootSessionId?: string;
  agentId?: string | null;
  isSubthread?: boolean;
  isPrimaryLink?: boolean;
  linkStrategy?: string;
  workflowType?: string;
  relatedPhases?: string[];
  relatedTasks?: Array<{
    taskId: string;
    taskTitle?: string;
    phaseId?: string;
    phase?: string;
    matchedBy?: string;
    linkedSessionId?: string;
  }>;
  sessionMetadata?: {
    sessionTypeId: string;
    sessionTypeLabel: string;
    mappingId: string;
    relatedCommand: string;
    relatedPhases: string[];
    relatedFilePath?: string;
    prLinks?: Array<{
      prNumber?: string;
      prUrl?: string;
      prRepository?: string;
    }>;
    commitCorrelations?: Array<{
      commitHash?: string;
      windowStart?: string;
      windowEnd?: string;
      eventCount?: number;
      toolCallCount?: number;
      commandCount?: number;
      artifactCount?: number;
      tokenInput?: number;
      tokenOutput?: number;
      fileCount?: number;
      additions?: number;
      deletions?: number;
      costUsd?: number;
      featureIds?: string[];
      phases?: string[];
      taskIds?: string[];
      filePaths?: string[];
      provisional?: boolean;
    }>;
    fields: Array<{
      id: string;
      label: string;
      value: string;
    }>;
  } | null;
}

interface PullRequestRef {
  prNumber?: string;
  prUrl?: string;
  prRepository?: string;
}

interface CommitCorrelationRef {
  commitHash: string;
  sessionId: string;
  branch?: string;
  windowStart?: string;
  windowEnd?: string;
  eventCount: number;
  toolCallCount: number;
  commandCount: number;
  artifactCount: number;
  tokenInput: number;
  tokenOutput: number;
  fileCount: number;
  additions: number;
  deletions: number;
  costUsd: number;
  featureIds: string[];
  phases: string[];
  taskIds: string[];
  filePaths: string[];
  provisional: boolean;
}

interface GitCommitAggregate {
  commitHash: string;
  sessionIds: string[];
  branches: string[];
  phases: string[];
  taskIds: string[];
  filePaths: string[];
  pullRequests: PullRequestRef[];
  tokenInput: number;
  tokenOutput: number;
  fileCount: number;
  additions: number;
  deletions: number;
  costUsd: number;
  eventCount: number;
  toolCallCount: number;
  commandCount: number;
  artifactCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  provisional: boolean;
}

type CoreSessionGroupId = 'plan' | 'execution' | 'other';
type DocGroupId = 'initialPlanning' | 'prd' | 'plans' | 'progress' | 'context';
type SessionViewMode = 'list' | 'grid';
export type FeatureModalTab = PlanningFeatureModalTab;

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
  workloadTokens: number;
  modelIOTokens: number;
  cacheInputTokens: number;
  byType: Array<{ type: string; count: number }>;
}

const SHORT_COMMIT_LENGTH = 7;
const FEATURE_MODAL_POLL_INTERVAL_MS = 15_000;
const WORKING_TREE_COMMIT_HASH = '__working_tree__';
const COMMIT_HASH_PATTERN = /^[0-9a-f]{7,40}$/i;

const toShortCommitHash = (hash: string): string => hash.slice(0, SHORT_COMMIT_LENGTH);
const normalizePath = (value: string): string => (value || '').replace(/\\/g, '/').replace(/^\.?\//, '');
const normalizeCommitHash = (value: string): string => {
  const raw = (value || '').trim().toLowerCase();
  if (!raw) return '';
  if (raw === WORKING_TREE_COMMIT_HASH) return raw;
  if (!COMMIT_HASH_PATTERN.test(raw)) return '';
  return raw;
};
const getPullRequestStableKey = (pr: PullRequestRef): string => (
  String(pr.prUrl || '').trim()
  || `pr:${String(pr.prRepository || '').trim()}:${String(pr.prNumber || '').trim()}`
  || `pr:${String(pr.prNumber || '').trim()}`
  || `repo:${String(pr.prRepository || '').trim()}`
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

const sessionHasLinkedSubthreads = (sessionId: string, sessions: FeatureSessionLink[]): boolean => (
  sessions.some(candidate => (
    candidate.sessionId !== sessionId
    && isSubthreadSession(candidate)
    && (
      candidate.parentSessionId === sessionId
      || candidate.rootSessionId === sessionId
    )
  ))
);

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

const getDocSequenceOrder = (doc: LinkedDocument): number | null => (
  typeof doc.sequenceOrder === 'number' ? doc.sequenceOrder : null
);

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
    const aSequence = getDocSequenceOrder(a);
    const bSequence = getDocSequenceOrder(b);
    if (aSequence !== null || bSequence !== null) {
      const normalizedA = aSequence ?? Number.POSITIVE_INFINITY;
      const normalizedB = bSequence ?? Number.POSITIVE_INFINITY;
      if (normalizedA !== normalizedB) return normalizedA - normalizedB;
    }
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

const getTaskIdentity = (task: ProjectTask): string => {
  const taskId = String(task.id || '').trim().toLowerCase();
  if (taskId) return taskId;
  return String(task.title || '').trim().toLowerCase();
};

const dedupePhaseTasks = (tasks: ProjectTask[]): ProjectTask[] => {
  const byIdentity = new Map<string, ProjectTask>();
  tasks.forEach(task => {
    const identity = getTaskIdentity(task);
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

const normalizeFeatureForModal = (feature: Feature): Feature => {
  const normalizedPhases = (feature.phases || []).map(phase => ({
    ...phase,
    tasks: dedupePhaseTasks(phase.tasks || []),
  }));
  return aggregateFeatureFromPhases(feature, normalizedPhases);
};

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
    };
  });

  return {
    ...detail,
    status: liveFeature.status,
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

const getFeatureCoverageSummary = (feature: Feature): string => {
  const coverage = feature.documentCoverage;
  if (!coverage) return 'Docs: n/a';
  const present = coverage.present?.length || 0;
  const total = present + (coverage.missing?.length || 0);
  if (total <= 0) return 'Docs: n/a';
  return `Docs: ${present}/${total}`;
};

const getFeatureLinkedFeatureCount = (feature: Feature): number => {
  const typedCount = feature.linkedFeatures?.length || 0;
  if (typedCount > 0) return typedCount;
  return feature.relatedFeatures?.length || 0;
};

const EXECUTION_GATE_LABELS: Record<ExecutionGateStateValue, string> = {
  ready: 'Ready',
  blocked_dependency: 'Blocked by dependency',
  waiting_on_family_predecessor: 'Waiting on family predecessor',
  unknown_dependency_state: 'Dependency state unknown',
};

const EXECUTION_GATE_STYLES: Record<ExecutionGateStateValue, string> = {
  ready: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  blocked_dependency: 'bg-rose-500/10 text-rose-200 border-rose-500/30',
  waiting_on_family_predecessor: 'bg-amber-500/10 text-amber-200 border-amber-500/30',
  unknown_dependency_state: 'bg-slate-500/10 text-slate-200 border-slate-500/30',
};

const getExecutionGateLabel = (gate?: ExecutionGateStateValue | string | null): string => {
  if (!gate) return 'Unknown';
  return EXECUTION_GATE_LABELS[gate as ExecutionGateStateValue] || gate;
};

const getExecutionGateStyle = (gate?: ExecutionGateStateValue | string | null): string => {
  if (!gate) return EXECUTION_GATE_STYLES.unknown_dependency_state;
  return EXECUTION_GATE_STYLES[gate as ExecutionGateStateValue] || EXECUTION_GATE_STYLES.unknown_dependency_state;
};

const getDependencyEvidenceLabel = (evidence: FeatureDependencyEvidence): string => {
  const parts = [
    evidence.dependencyFeatureName || evidence.dependencyFeatureId || 'Unknown dependency',
    evidence.dependencyStatus || 'unknown',
  ].filter(Boolean);
  return parts.join(' • ');
};

const getFamilyPositionLabel = (position?: FeatureFamilyPosition | null): string => {
  if (!position) return 'Unsequenced';
  if (position.display) return position.display;
  if (!position.currentIndex) return 'Unsequenced';
  return `${position.currentIndex} of ${position.totalItems || position.currentIndex}`;
};

const getFamilyItemLabel = (item?: FeatureFamilyItem | null): string => {
  if (!item) return 'No family recommendation';
  const parts = [
    item.featureName || item.featureId,
    item.sequenceOrder !== null && item.sequenceOrder !== undefined ? `seq ${item.sequenceOrder}` : '',
    item.isBlocked ? 'blocked' : '',
    item.isBlockedUnknown ? 'blocked unknown' : '',
  ].filter(Boolean);
  return parts.join(' • ');
};

const resolveNextFamilyItem = (
  feature: Feature,
): FeatureFamilyItem | null => {
  const summary = feature.familySummary;
  const fromSummary = summary?.nextRecommendedFamilyItem || null;
  if (fromSummary) return fromSummary;
  const recommendedId = feature.executionGate?.recommendedFamilyItemId || feature.familyPosition?.nextItemId || '';
  if (!recommendedId) return null;
  return summary?.items?.find(item => item.featureId === recommendedId) || null;
};

const DOC_TYPE_LABELS: Record<string, string> = {
  prd: 'PRD',
  implementation_plan: 'Plan',
  phase_plan: 'Phase',
  progress: 'Progress',
  report: 'Report',
  spec: 'Spec',
};

const getDocTypeLabel = (docType: string): string => DOC_TYPE_LABELS[docType] || docType;

const toDateDayIndex = (value: string): number | null => {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth(), parsed.getUTCDate()) / 86_400_000;
};

const getDaysBetween = (startValue: string, endValue: string): number | null => {
  const startDay = toDateDayIndex(startValue);
  const endDay = toDateDayIndex(endValue);
  if (startDay === null || endDay === null || endDay < startDay) return null;
  return endDay - startDay;
};

const formatFeatureDate = (value?: string): string => {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unavailable';
  return parsed.toLocaleDateString();
};

const formatFeatureDateCompact = (value?: string): string => {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '--';
  return parsed.toLocaleDateString(undefined, {
    month: 'numeric',
    day: 'numeric',
    year: '2-digit',
  });
};

const buildLinkedDocTypeCounts = (docs: LinkedDocument[]): Array<{ docType: string; count: number }> => {
  const counts = new Map<string, number>();
  docs.forEach((doc) => {
    const key = (doc.docType || 'document').toLowerCase();
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([docType, count]) => ({ docType, count }))
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      return getDocTypeLabel(a.docType).localeCompare(getDocTypeLabel(b.docType));
    });
};

const getFeatureDateModule = (feature: Feature): {
  first: { label: 'Planned' | 'Started'; value: string; confidence?: string };
  completed: { label: 'Completed'; value: string; confidence?: string };
  daysBetween: number | null;
} => {
  const planned = getFeatureDateValue(feature, 'plannedAt');
  const started = getFeatureDateValue(feature, 'startedAt');
  const completed = getFeatureDateValue(feature, 'completedAt');
  const first = planned.value
    ? { label: 'Planned' as const, value: planned.value, confidence: planned.confidence }
    : { label: 'Started' as const, value: started.value, confidence: started.confidence };
  return {
    first,
    completed: { label: 'Completed', value: completed.value, confidence: completed.confidence },
    daysBetween: first.value && completed.value ? getDaysBetween(first.value, completed.value) : null,
  };
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
      <div className="flex-1 h-1.5 bg-surface-muted rounded-full overflow-hidden">
        {pct > 0 ? (
          <div className="h-full w-full flex rounded-full overflow-hidden">
            {donePct > 0 && <div className="h-full bg-emerald-500 transition-all" style={{ width: `${donePct}%` }} />}
            {deferredPct > 0 && <div className="h-full bg-amber-400 transition-all" style={{ width: `${deferredPct}%` }} />}
          </div>
        ) : (
          <div className="h-full bg-surface-muted transition-all" style={{ width: '100%' }} />
        )}
      </div>
      <span className="text-[10px] text-muted-foreground font-mono min-w-[64px] text-right">
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
    default: return <FileText size={12} className="text-muted-foreground" />;
  }
};

const DocTypeBadge = ({ docType }: { docType: string }) => {
  return <span className="text-[9px] uppercase font-bold">{getDocTypeLabel(docType)}</span>;
};

const FeatureDateStack = ({ feature }: { feature: Feature }) => {
  const dateModule = getFeatureDateModule(feature);
  return (
    <div className="rounded-md border border-panel-border bg-surface-overlay/70 px-2.5 py-2">
      <div className="text-[10px] text-muted-foreground">
        <span className="uppercase tracking-wider">{dateModule.first.label}</span>
        <span className="ml-1 font-mono text-muted-foreground">{formatFeatureDate(dateModule.first.value)}</span>
      </div>
      <div className="mt-1 text-[10px] text-muted-foreground">
        <span className="uppercase tracking-wider">Completed</span>
        <span className="ml-1 font-mono text-muted-foreground">{formatFeatureDate(dateModule.completed.value)}</span>
      </div>
    </div>
  );
};

const FeatureKanbanDateModule = ({ feature }: { feature: Feature }) => {
  const dateModule = getFeatureDateModule(feature);
  const firstLabel = dateModule.first.label === 'Planned' ? 'P' : 'S';
  const firstDate = formatFeatureDateCompact(dateModule.first.value);
  const completedDate = formatFeatureDateCompact(dateModule.completed.value);
  return (
    <div className="ml-auto mt-1 w-[52%] max-w-[170px] min-w-[124px]">
      <div className="mb-0.5 text-center text-[8px] font-semibold uppercase tracking-wide text-indigo-300">
        {dateModule.daysBetween !== null ? `${dateModule.daysBetween}d` : '--'}
      </div>
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-1">
        <span className="whitespace-nowrap text-[9px] font-mono text-foreground">
          {firstLabel} {firstDate}
        </span>
        <span className="relative h-px bg-gradient-to-r from-panel-border to-indigo-400">
          <ChevronRight size={10} className="absolute -right-0.5 top-1/2 -translate-y-1/2 text-indigo-400" />
        </span>
        <span className="whitespace-nowrap text-[9px] font-mono text-foreground">
          C {completedDate}
        </span>
      </div>
    </div>
  );
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
      className={`font-bold uppercase rounded cursor-pointer border-0 appearance-none ${sizeClasses} ${style.color} bg-transparent hover:ring-1 hover:ring-hover focus:ring-1 focus:ring-focus focus:outline-none transition-all`}
      style={{ WebkitAppearance: 'none' }}
    >
      {FEATURE_STATUS_OPTIONS.map(s => (
        <option key={s} value={s} className="bg-panel text-foreground">
          {getStatusStyle(s).label}
        </option>
      ))}
    </select>
  );
};

const featureValue = (value?: string | number | null): string => {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
};

const FeatureMetricTile = ({
  label,
  value,
  detail,
  icon: Icon,
  accentClassName = 'text-panel-foreground',
}: {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accentClassName?: string;
}) => (
  <Surface tone="elevated" padding="sm" className="min-h-[104px] overflow-hidden">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
        <div className={`mt-2 text-2xl font-semibold leading-none ${accentClassName}`}>{value}</div>
      </div>
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-panel-border bg-surface-overlay/80 text-muted-foreground">
        <Icon size={15} />
      </span>
    </div>
    {detail ? <div className="mt-2 text-[11px] leading-4 text-muted-foreground">{detail}</div> : null}
  </Surface>
);

const FeatureModalSection = ({
  title,
  description,
  icon: Icon,
  children,
  className = '',
  headerRight,
}: {
  title: string;
  description?: React.ReactNode;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  children: React.ReactNode;
  className?: string;
  headerRight?: React.ReactNode;
}) => (
  <Surface tone="panel" padding="md" className={className}>
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        {Icon ? (
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-panel-border bg-surface-muted text-muted-foreground">
            <Icon size={15} />
          </span>
        ) : null}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-panel-foreground">{title}</h3>
          {description ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p> : null}
        </div>
      </div>
      {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
    </div>
    {children}
  </Surface>
);

const FeatureField = ({
  label,
  value,
  mono = false,
}: {
  label: string;
  value?: React.ReactNode;
  mono?: boolean;
}) => (
  <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2">
    <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
    <div className={`mt-1 min-h-[18px] text-sm text-panel-foreground ${mono ? 'font-mono text-xs' : ''}`}>
      {value || '-'}
    </div>
  </div>
);

const getDocTypeTone = (docType: string): string => {
  switch ((docType || '').toLowerCase()) {
    case 'prd':
      return 'border-purple-500/30 bg-purple-500/10 text-purple-400';
    case 'implementation_plan':
      return 'border-info-border bg-info/10 text-info';
    case 'phase_plan':
      return 'border-warning-border bg-warning/10 text-warning';
    case 'progress':
      return 'border-success-border bg-success/10 text-success';
    case 'report':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500';
    case 'spec':
      return 'border-cyan-500/30 bg-cyan-500/10 text-cyan-500';
    default:
      return 'border-panel-border bg-surface-muted text-muted-foreground';
  }
};

const getDocGroupIcon = (groupId: DocGroupId): React.ComponentType<{ size?: number; className?: string }> => {
  switch (groupId) {
    case 'initialPlanning': return Search;
    case 'prd': return ClipboardList;
    case 'plans': return Layers;
    case 'progress': return Terminal;
    case 'context': return FileText;
    default: return FileText;
  }
};

const getDocPhaseLabel = (doc: LinkedDocument): string => {
  const phase = getDocPhaseNumber(doc);
  return phase === null ? 'Unassigned progress' : `Phase ${phase}`;
};

const groupDocsByPhaseLabel = (docs: LinkedDocument[]): Array<{ label: string; docs: LinkedDocument[] }> => {
  const buckets = new Map<string, LinkedDocument[]>();
  docs.forEach(doc => {
    const label = getDocPhaseLabel(doc);
    buckets.set(label, [...(buckets.get(label) || []), doc]);
  });
  return Array.from(buckets.entries())
    .map(([label, rows]) => ({ label, docs: rows }))
    .sort((a, b) => {
      const aPhase = parsePhaseNumber(a.label, false) ?? Number.POSITIVE_INFINITY;
      const bPhase = parsePhaseNumber(b.label, false) ?? Number.POSITIVE_INFINITY;
      if (aPhase !== bPhase) return aPhase - bPhase;
      return a.label.localeCompare(b.label);
    });
};

const FeatureDocCard = ({
  doc,
  primary,
  compact = false,
  onClick,
}: {
  doc: LinkedDocument;
  primary: boolean;
  compact?: boolean;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`group flex h-full w-full flex-col rounded-lg border border-panel-border bg-surface-overlay/70 text-left transition-all hover:border-info-border hover:bg-surface-muted/70 ${compact ? 'p-3' : 'p-4'}`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-2">
        <span className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border ${getDocTypeTone(doc.docType)}`}>
          <DocTypeIcon docType={doc.docType} />
        </span>
        <div className="min-w-0">
          <div className="line-clamp-2 text-sm font-semibold leading-5 text-panel-foreground group-hover:text-info">
            {doc.title}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${getDocTypeTone(doc.docType)}`}>
              <DocTypeBadge docType={doc.docType} />
            </span>
            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${primary
              ? 'border-success-border bg-success/10 text-success'
              : 'border-panel-border bg-surface-muted text-muted-foreground'
              }`}>
              {primary ? 'Primary' : 'Supporting'}
            </span>
          </div>
        </div>
      </div>
      <ExternalLink size={13} className="shrink-0 text-muted-foreground transition-colors group-hover:text-info" />
    </div>
    <div className="mt-3 flex min-w-0 items-center gap-1.5 truncate text-xs text-muted-foreground">
      <FolderOpen size={12} className="shrink-0" />
      <span className="truncate font-mono">{doc.filePath}</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
      {doc.featureFamily && (
        <span className="rounded-full border border-panel-border bg-panel px-2 py-0.5 text-foreground">
          {doc.featureFamily}
        </span>
      )}
      {typeof doc.sequenceOrder === 'number' && (
        <span className="rounded-full border border-info-border bg-info/10 px-2 py-0.5 text-info">
          Seq {doc.sequenceOrder}
        </span>
      )}
      {(doc.blockedBy || []).map(featureId => (
        <span key={`${doc.id}-blocked-${featureId}`} className="rounded-full border border-danger-border bg-danger/10 px-2 py-0.5 text-danger">
          Blocked by {featureId}
        </span>
      ))}
      {(doc.prdRef || '').trim() && (
        <span className="rounded-full border border-panel-border bg-panel px-2 py-0.5 text-muted-foreground">
          PRD <span className="font-mono text-foreground">{doc.prdRef}</span>
        </span>
      )}
    </div>
  </button>
);

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
    // P4-010: replaced raw /api/features/task-source fetch with typed client.
    getFeatureTaskSource(task.sourceFile)
      .then(data => { setContent(data.content); setLoading(false); })
      .catch(e => { setError((e as Error).message); setLoading(false); });
  }, [task.sourceFile]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-surface-overlay/90 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-panel border border-panel-border rounded-xl w-full max-w-3xl h-[70vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b border-panel-border flex justify-between items-center bg-surface-overlay">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-panel-foreground flex items-center gap-2 truncate">
              <FileText size={16} className="text-indigo-400 flex-shrink-0" />
              {task.title}
            </h3>
            <div className="flex items-center gap-3 mt-1">
              <span className="font-mono text-[10px] text-muted-foreground">{task.id}</span>
              {task.sourceFile && (
                <span className="text-[10px] text-muted-foreground font-mono truncate flex items-center gap-1">
                  <FolderOpen size={10} />
                  {task.sourceFile}
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-panel-foreground transition-colors p-1">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-surface-overlay/60">
        {loading && (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <RefreshCw size={20} className="animate-spin mr-2" /> Loading source file…
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <FileText size={32} className="mb-3 opacity-30" />
              <p className="text-sm">{error}</p>
            </div>
          )}
          {content !== null && !loading && !error && (
            <UnifiedContentViewer
              path={task.sourceFile || null}
              content={content}
              readOnly
              className="h-full"
            />
          )}
        </div>
      </div>
    </div>
  );
};

// ── Feature Detail Modal ───────────────────────────────────────────

export const ProjectBoardFeatureModal = ({
  feature,
  onClose,
  initialTab = 'overview',
}: {
  feature: Feature;
  onClose: () => void;
  initialTab?: FeatureModalTab;
}) => {
  const navigate = useNavigate();
  const { activeProject, updateFeatureStatus, updatePhaseStatus, updateTaskStatus, documents } = useData();
  // P5-005: Read the v2 flag once at mount so both the modal section hook and
  // the legacy refresh callbacks pick a consistent path for this modal instance.
  const { runtimeStatus: modalRuntimeStatus } = useAppRuntime();
  const modalV2Enabled = isFeatureSurfaceV2Enabled(modalRuntimeStatus);
  const [activeTab, setActiveTab] = useState<FeatureModalTab>(initialTab);
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
  const [gitHistoryCommitFilter, setGitHistoryCommitFilter] = useState<string>('');
  const [showSecondarySessions, setShowSecondarySessions] = useState(false);
  const [sessionViewMode, setSessionViewMode] = useState<SessionViewMode>('list');
  const [expandedSubthreadsBySessionId, setExpandedSubthreadsBySessionId] = useState<Set<string>>(new Set());
  const [featureTestHealth, setFeatureTestHealth] = useState<FeatureTestHealth | null>(null);
  const featureDetailRequestIdRef = useRef(0);
  const linkedSessionsRequestIdRef = useRef(0);
  // P4-003: tracks whether linked sessions have been fetched for the current
  // feature.  Reset on feature change.  Prevents eager fetch on modal open.
  const sessionsFetchedRef = useRef(false);

  // P4-010: per-section hook for typed, lazy modal data loading.
  // Each section (overview, phases, docs, relations, sessions, test-status,
  // history) has independent status/error/retry lifecycle via useFeatureModalData.
  // `fullFeature` + `linkedSessionLinks` state above remain for compatibility with
  // existing sub-components; sections loaded here provide supplementary TabStateView
  // states without replacing the existing data flow in this task.
  // P5-005: Pass v2 flag so the hook picks legacy path when disabled.
  const modalSections = useFeatureModalData(feature.id, { featureSurfaceV2Enabled: modalV2Enabled });

  const refreshFeatureDetail = useCallback(async () => {
    const requestId = ++featureDetailRequestIdRef.current;
    try {
      const data = await getLegacyFeatureDetail<Feature>(feature.id);
      if (requestId !== featureDetailRequestIdRef.current) return;
      setFullFeature(normalizeFeatureForModal(data));
    } catch {
      // Keep existing detail snapshot on transient failures.
    }
  }, [feature.id]);

  // P5-006: refreshLinkedSessions now uses the paginated v2 API (getFeatureLinkedSessionPage)
  // instead of the retired legacy endpoint. The existing lazy gate (activeTab === 'sessions' &&
  // !sessionsFetchedRef.current) is preserved unchanged.  We fetch the first page (limit 50)
  // for the initial load; subsequent pages are pulled by the pagination accumulator in P4-004.
  const refreshLinkedSessions = useCallback(async () => {
    const requestId = ++linkedSessionsRequestIdRef.current;
    try {
      const page = await getFeatureLinkedSessionPage(feature.id, { limit: 50, offset: 0 });
      if (requestId !== linkedSessionsRequestIdRef.current) return;
      const bestBySession = new Map<string, FeatureSessionLink>();
      for (const dto of page.items) {
        const sessionId = String(dto.sessionId || '').trim();
        if (!sessionId) continue;
        const confidence = dto.isPrimaryLink ? 0.9 : 0.5;
        const existing = bestBySession.get(sessionId);
        if (!existing || confidence > existing.confidence) {
          bestBySession.set(sessionId, {
            sessionId: dto.sessionId,
            title: dto.title,
            confidence,
            reasons: dto.reasons ?? [],
            commands: dto.commands ?? [],
            commitHashes: [],
            status: dto.status,
            model: dto.model,
            modelProvider: dto.modelProvider,
            modelFamily: dto.modelFamily,
            startedAt: dto.startedAt,
            endedAt: dto.endedAt,
            updatedAt: dto.updatedAt,
            totalCost: dto.totalCost,
            observedTokens: dto.observedTokens,
            durationSeconds: 0,
            parentSessionId: dto.parentSessionId ?? null,
            rootSessionId: dto.rootSessionId,
            isSubthread: dto.isSubthread,
            isPrimaryLink: dto.isPrimaryLink,
            workflowType: dto.workflowType,
            relatedPhases: [],
            relatedTasks: (dto.relatedTasks ?? []).map(t => ({
              taskId: t.taskId,
              taskTitle: t.taskTitle,
              phaseId: t.phaseId,
              phase: t.phase,
              matchedBy: t.matchedBy,
            })),
          });
        }
      }
      setLinkedSessionLinks(Array.from(bestBySession.values()));
    } catch {
      // Keep previous linked sessions on transient failures.
    }
  }, [feature.id]);

  useEffect(() => {
    setFullFeature(null);
    setLinkedSessionLinks([]);
    setFeatureTestHealth(null);
    setCoreSessionGroupExpanded({ ...DEFAULT_CORE_SESSION_GROUP_EXPANDED });
    setDocGroupExpanded({ ...DEFAULT_DOC_GROUP_EXPANDED });
    setGitHistoryCommitFilter('');
    setShowSecondarySessions(false);
    setExpandedSubthreadsBySessionId(new Set());
    setPhaseStatusFilter('all');
    setTaskStatusFilter('all');
    setViewingDoc(null);
    // P4-003: Reset session fetch guard so Sessions tab re-fetches for the new feature.
    sessionsFetchedRef.current = false;
    // P4-004: Reset pagination accumulator pointer on feature change.
    prevAccumulatedCountRef.current = 0;
    refreshFeatureDetail();
    // NOTE: linked sessions are NOT fetched here (P4-003).
    // They are loaded lazily on first Sessions tab activation.
  }, [feature.id, refreshFeatureDetail]);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [feature.id, initialTab]);

  // P4-003: Lazy Sessions Tab — fetch linked sessions ONLY on first Sessions tab
  // activation for this feature.  Subsequent switches to the sessions tab reuse
  // the already-fetched data (cache guard via sessionsFetchedRef).
  useEffect(() => {
    if (activeTab === 'sessions' && !sessionsFetchedRef.current) {
      sessionsFetchedRef.current = true;
      void refreshLinkedSessions();
    }
  }, [activeTab, refreshLinkedSessions]);

  // P4-004: Adapt LinkedFeatureSessionDTO items from the paginated accumulator
  // into FeatureSessionLink and merge into linkedSessionLinks when new pages load.
  // Only items not already present (by sessionId) are appended; the first-page
  // load via refreshLinkedSessions (P5-006: now v2 getFeatureLinkedSessionPage)
  // remains authoritative for the initial result set.
  const prevAccumulatedCountRef = useRef(0);
  useEffect(() => {
    const { accumulatedItems } = modalSections.sessionPagination;
    if (accumulatedItems.length <= prevAccumulatedCountRef.current) {
      // No net new items; also handle reset (accumulator cleared on feature change).
      prevAccumulatedCountRef.current = accumulatedItems.length;
      return;
    }
    const newItems = accumulatedItems.slice(prevAccumulatedCountRef.current);
    prevAccumulatedCountRef.current = accumulatedItems.length;

    setLinkedSessionLinks(prev => {
      const existingIds = new Set(prev.map(s => s.sessionId));
      const toAppend: FeatureSessionLink[] = newItems
        .filter(dto => !existingIds.has(dto.sessionId))
        .map(dto => ({
          sessionId: dto.sessionId,
          title: dto.title,
          confidence: dto.isPrimaryLink ? 0.9 : 0.5,
          reasons: dto.reasons ?? [],
          commands: dto.commands ?? [],
          commitHashes: [],
          status: dto.status,
          model: dto.model,
          modelProvider: dto.modelProvider,
          modelFamily: dto.modelFamily,
          startedAt: dto.startedAt,
          endedAt: dto.endedAt,
          updatedAt: dto.updatedAt,
          totalCost: dto.totalCost,
          observedTokens: dto.observedTokens,
          durationSeconds: 0,
          parentSessionId: dto.parentSessionId ?? null,
          rootSessionId: dto.rootSessionId,
          isSubthread: dto.isSubthread,
          isPrimaryLink: dto.isPrimaryLink,
          workflowType: dto.workflowType,
          relatedPhases: [],
          relatedTasks: (dto.relatedTasks ?? []).map(t => ({
            taskId: t.taskId,
            taskTitle: t.taskTitle,
            phaseId: t.phaseId,
            phase: t.phase,
            matchedBy: t.matchedBy,
          })),
        }));
      if (toAppend.length === 0) return prev;
      return [...prev, ...toAppend];
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modalSections.sessionPagination.accumulatedItems]);

  // P4-010: Trigger useFeatureModalData section loads on tab activation.
  // Overview loads on mount; each other tab loads when first activated.
  // Sections that are already 'loading' or 'success'/'stale' are no-ops (handled
  // inside the hook's load() guard).  The existing fullFeature / linkedSessionLinks
  // state paths remain the authoritative data source for sub-components; these
  // load() calls provide the TabStateView status signals for each tab.
  useEffect(() => {
    if (activeTab === 'overview') {
      modalSections.overview.load();
    } else if (activeTab === 'phases') {
      modalSections.phases.load();
    } else if (activeTab === 'docs') {
      modalSections.docs.load();
    } else if (activeTab === 'relations') {
      modalSections.relations.load();
    } else if (activeTab === 'sessions') {
      modalSections.sessions.load();
    } else if (activeTab === 'test-status') {
      modalSections['test-status'].load();
    } else if (activeTab === 'history') {
      modalSections.history.load();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);
  // Note: modalSections intentionally excluded from deps — the hook reference is
  // stable per feature; including it would cause double-loads on every render.

  const refreshFeatureTestHealth = useCallback(async () => {
    if (!activeProject?.id) {
      setFeatureTestHealth(null);
      return;
    }

    try {
      const payload = await getFeatureHealth(activeProject.id, { featureId: feature.id, limit: 200 });
      const health = payload.items.find(item => item.featureId === feature.id) || null;
      setFeatureTestHealth(health);
    } catch {
      setFeatureTestHealth(null);
    }
  }, [activeProject?.id, feature.id]);

  useEffect(() => {
    void refreshFeatureTestHealth();
  }, [refreshFeatureTestHealth]);

  useEffect(() => {
    if (activeTab === 'test-status' && (!featureTestHealth || featureTestHealth.totalTests <= 0)) {
      setActiveTab('overview');
    }
  }, [activeTab, featureTestHealth]);

  // ── P4-006: Live-refresh policy ───────────────────────────────────────────────
  //
  // Overview shell is ALWAYS refreshed (it is the open-cost; always considered
  // "active" for refresh purposes).
  //
  // For every other section on a live-invalidation event OR a polling tick:
  //
  //   ACTIVE tab  →  call the legacy refresh function immediately.  The user is
  //                  looking at this data; stale results are visible.
  //
  //   INACTIVE tab, section.status === 'success' | 'stale'
  //               →  call markStale(section) ONLY.  Do NOT fetch.  The section
  //                  will re-fetch automatically on next tab activation via the
  //                  existing tab-activation useEffect (P4-010).
  //
  //   INACTIVE tab, section.status === 'idle' | 'loading' | 'error'
  //               →  do NOTHING.  'idle' was never loaded; 'loading' is already
  //                  in-flight; 'error' waits for user-driven retry.  Pre-fetching
  //                  unloaded heavy sections on behalf of background refresh is
  //                  exactly what P4-006 prohibits.
  //
  // The heavy sections subject to this policy are:
  //   phases, sessions, docs, relations, history, test-status
  // (overview is always refreshed; sessions also uses the legacy sessionsFetchedRef guard)
  //
  // "ACTIVE" is defined as: the section whose tab is currently open in the modal.
  // A section may be loaded (status === 'success') but inactive if the user has
  // navigated away from its tab.
  // ─────────────────────────────────────────────────────────────────────────────

  /**
   * Applies the P4-006 live-refresh policy for a single non-overview section.
   * Returns a Promise<void> so it can be composed in Promise.all / setInterval.
   *
   * @param section   - The ModalTabId of the section to evaluate.
   * @param refreshFn - The legacy async refresh to call when the section is active.
   */
  const applyLiveRefreshPolicy = useCallback(
    (
      section: Exclude<ModalTabId, 'overview'>,
      refreshFn: () => Promise<void>,
    ): Promise<void> => {
      const isActive = activeTab === section;
      const sectionStatus = modalSections[section].status;

      if (isActive) {
        // Active tab: fetch immediately so the user sees fresh data.
        return refreshFn();
      }

      // Inactive tab: only promote loaded sections to stale; never pre-fetch.
      if (sectionStatus === 'success' || sectionStatus === 'stale') {
        modalSections.markStale(section);
      }
      // 'idle' | 'loading' | 'error' → no-op
      return Promise.resolve();
    },
    [activeTab, modalSections],
  );

  const featureLiveEnabled = Boolean(activeProject?.id && isFeatureLiveUpdatesEnabled());
  const featureLiveStatus = useLiveInvalidation({
    topics: featureLiveEnabled && activeProject?.id ? [featureTopic(feature.id), projectFeaturesTopic(activeProject.id)] : [],
    enabled: featureLiveEnabled,
    pauseWhenHidden: true,
    onInvalidate: async () => {
      // Overview shell always refreshes (open-cost; always "active").
      // Heavy sections follow the P4-006 policy via applyLiveRefreshPolicy.
      await Promise.all([
        refreshFeatureDetail(),
        applyLiveRefreshPolicy(
          'phases',
          () => Promise.resolve(), // phases currently wired through refreshFeatureDetail; no dedicated legacy fn
        ),
        // P4-003 / P4-006: sessions — guard both the legacy fetch ref AND the
        // section status so we never fetch sessions that were never loaded.
        applyLiveRefreshPolicy(
          'sessions',
          () => sessionsFetchedRef.current ? refreshLinkedSessions() : Promise.resolve(),
        ),
        applyLiveRefreshPolicy(
          'docs',
          () => Promise.resolve(), // docs currently wired through refreshFeatureDetail; no dedicated legacy fn
        ),
        applyLiveRefreshPolicy(
          'relations',
          () => Promise.resolve(), // relations currently wired through refreshFeatureDetail; no dedicated legacy fn
        ),
        applyLiveRefreshPolicy(
          'history',
          () => Promise.resolve(), // history currently wired through refreshFeatureDetail; no dedicated legacy fn
        ),
        applyLiveRefreshPolicy(
          'test-status',
          () => refreshFeatureTestHealth(),
        ),
      ]);
    },
  });

  useEffect(() => {
    if (featureLiveEnabled && !['backoff', 'closed'].includes(featureLiveStatus)) {
      return undefined;
    }
    const interval = setInterval(() => {
      // Overview shell always refreshes (open-cost; always "active").
      void refreshFeatureDetail();

      // Heavy sections follow the P4-006 policy via applyLiveRefreshPolicy.
      // P4-003 / P4-006: sessions — guard both the legacy fetch ref AND the
      // section status so we never fetch sessions that were never loaded.
      void applyLiveRefreshPolicy(
        'sessions',
        () => sessionsFetchedRef.current ? refreshLinkedSessions() : Promise.resolve(),
      );
      void applyLiveRefreshPolicy('phases', () => Promise.resolve());
      void applyLiveRefreshPolicy('docs', () => Promise.resolve());
      void applyLiveRefreshPolicy('relations', () => Promise.resolve());
      void applyLiveRefreshPolicy('history', () => Promise.resolve());
      void applyLiveRefreshPolicy('test-status', () => refreshFeatureTestHealth());
    }, FEATURE_MODAL_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [activeTab, applyLiveRefreshPolicy, featureLiveEnabled, featureLiveStatus, refreshFeatureDetail, refreshFeatureTestHealth, refreshLinkedSessions]);

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
  const dependencyState = activeFeature.dependencyState || null;
  const familySummary = activeFeature.familySummary || null;
  const familyPosition = activeFeature.familyPosition || activeFeature.executionGate?.familyPosition || null;
  const executionGate = activeFeature.executionGate || null;
  const blockingEvidence = activeFeature.blockingFeatures?.length
    ? activeFeature.blockingFeatures
    : dependencyState?.dependencies || [];
  const nextFamilyItem = resolveNextFamilyItem(activeFeature);
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
      // P4-011: invalidate both planning + surface caches via the cross-cache bus.
      publishFeatureWriteEvent({ projectId: activeProject?.id, featureIds: [feature.id], kind: 'status' });
    } catch (error) {
      if (previousFeatureSnapshot) {
        setFullFeature(previousFeatureSnapshot);
      }
      throw error;
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleBeginWork = useCallback(() => {
    void trackExecutionEvent({
      eventType: 'execution_begin_work_clicked',
      featureId: activeFeature.id,
      metadata: { source: 'feature_modal' },
    });
    navigate(`/execution?feature=${encodeURIComponent(activeFeature.id)}`);
    onClose();
  }, [activeFeature.id, navigate, onClose]);

  const openGitCommitInHistory = useCallback((commitHash: string) => {
    const normalized = normalizeCommitHash(commitHash);
    if (!normalized) return;
    setGitHistoryCommitFilter(normalized);
    setActiveTab('history');
  }, []);

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
      // P4-011: invalidate both planning + surface caches via the cross-cache bus.
      publishFeatureWriteEvent({ projectId: activeProject?.id, featureIds: [feature.id], kind: 'phase' });
    } catch (error) {
      if (previousFeatureSnapshot) {
        setFullFeature(previousFeatureSnapshot);
      }
      throw error;
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleTaskStatusChange = async (phaseId: string, taskId: string, newStatus: ProjectTask['status']) => {
    let previousFeatureSnapshot: Feature | null = null;
    let previousTaskStatus: ProjectTask['status'] | undefined;
    setFullFeature(prev => {
      if (!prev || prev.id !== feature.id) return prev;
      let changed = false;
      const nextPhases = (prev.phases || []).map(phase => {
        if (phase.phase !== phaseId && phase.id !== phaseId) return phase;
        const nextTasks = (phase.tasks || []).map(task => {
          if (task.id !== taskId) return task;
          changed = true;
          previousTaskStatus = task.status;
          return { ...task, status: newStatus as ProjectTask['status'] };
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
      // P4-011: invalidate both planning + surface caches via the cross-cache bus.
      publishFeatureWriteEvent({ projectId: activeProject?.id, featureIds: [feature.id], kind: 'task' });
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
  const prefersReducedMotion = useReducedMotionPreference();
  const listInsertPreset = getMotionPreset('listInsertTop', prefersReducedMotion);
  const animatedLinkedSessions = useAnimatedListDiff(linkedSessions, {
    getId: session => session.sessionId,
  });

  const phaseSessionLinks = useMemo(() => {
    const byPhase = new Map<string, FeatureSessionLink[]>();
    const add = (phaseToken: string, session: FeatureSessionLink) => {
      const key = (phaseToken || '').trim();
      if (!key) return;
      const existing = byPhase.get(key) || [];
      if (!existing.some(item => item.sessionId === session.sessionId)) {
        byPhase.set(key, [...existing, session]);
      }
    };

    linkedSessions.forEach(session => {
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
  }, [linkedSessions, phases]);

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
      }
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

    linkedSessions.forEach(session => {
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
  }, [linkedSessions, phases]);

  const gitHistoryData = useMemo(() => {
    type CommitAccumulator = {
      commitHash: string;
      sessionIds: Set<string>;
      branches: Set<string>;
      phases: Set<string>;
      taskIds: Set<string>;
      filePaths: Set<string>;
      pullRequestKeys: Set<string>;
      tokenInput: number;
      tokenOutput: number;
      fileCount: number;
      additions: number;
      deletions: number;
      costUsd: number;
      eventCount: number;
      toolCallCount: number;
      commandCount: number;
      artifactCount: number;
      firstSeenAt: string;
      lastSeenAt: string;
      provisional: boolean;
    };

    const commitMap = new Map<string, CommitAccumulator>();
    const pullRequestMap = new Map<string, PullRequestRef>();
    const branchSet = new Set<string>();

    const addPullRequest = (candidate: PullRequestRef) => {
      const prNumber = String(candidate.prNumber || '').trim();
      const prUrl = String(candidate.prUrl || '').trim();
      const prRepository = String(candidate.prRepository || '').trim();
      const key = (prUrl || prNumber || prRepository).toLowerCase();
      if (!key) return;
      const existing = pullRequestMap.get(key);
      if (existing) {
        if (!existing.prUrl && prUrl) existing.prUrl = prUrl;
        if (!existing.prNumber && prNumber) existing.prNumber = prNumber;
        if (!existing.prRepository && prRepository) existing.prRepository = prRepository;
        return;
      }
      pullRequestMap.set(key, {
        prNumber: prNumber || undefined,
        prUrl: prUrl || undefined,
        prRepository: prRepository || undefined,
      });
    };

    const addCommitRow = ({
      session,
      commitHash,
      phases,
      taskIds,
      filePaths,
      tokenInput,
      tokenOutput,
      fileCount,
      additions,
      deletions,
      costUsd,
      eventCount,
      toolCallCount,
      commandCount,
      artifactCount,
      windowStart,
      windowEnd,
      provisional,
      pullRequests,
    }: {
      session: FeatureSessionLink;
      commitHash: string;
      phases?: string[];
      taskIds?: string[];
      filePaths?: string[];
      tokenInput?: number;
      tokenOutput?: number;
      fileCount?: number;
      additions?: number;
      deletions?: number;
      costUsd?: number;
      eventCount?: number;
      toolCallCount?: number;
      commandCount?: number;
      artifactCount?: number;
      windowStart?: string;
      windowEnd?: string;
      provisional?: boolean;
      pullRequests?: PullRequestRef[];
    }) => {
      const normalizedHash = normalizeCommitHash(commitHash);
      if (!normalizedHash) return;

      let current = commitMap.get(normalizedHash);
      if (!current) {
        current = {
          commitHash: normalizedHash,
          sessionIds: new Set<string>(),
          branches: new Set<string>(),
          phases: new Set<string>(),
          taskIds: new Set<string>(),
          filePaths: new Set<string>(),
          pullRequestKeys: new Set<string>(),
          tokenInput: 0,
          tokenOutput: 0,
          fileCount: 0,
          additions: 0,
          deletions: 0,
          costUsd: 0,
          eventCount: 0,
          toolCallCount: 0,
          commandCount: 0,
          artifactCount: 0,
          firstSeenAt: '',
          lastSeenAt: '',
          provisional: false,
        };
        commitMap.set(normalizedHash, current);
      }

      const sessionId = String(session.sessionId || '').trim();
      if (sessionId) current.sessionIds.add(sessionId);

      const branch = String(session.gitBranch || '').trim();
      if (branch) {
        current.branches.add(branch);
        branchSet.add(branch);
      }

      (phases || []).forEach(phase => {
        const token = String(phase || '').trim();
        if (token) current?.phases.add(token);
      });
      (taskIds || []).forEach(taskId => {
        const token = String(taskId || '').trim();
        if (token) current?.taskIds.add(token);
      });
      (filePaths || []).forEach(path => {
        const token = normalizePath(String(path || ''));
        if (token) current?.filePaths.add(token);
      });

      current.tokenInput += Number(tokenInput || 0);
      current.tokenOutput += Number(tokenOutput || 0);
      current.fileCount += Number(fileCount || 0);
      current.additions += Number(additions || 0);
      current.deletions += Number(deletions || 0);
      current.costUsd += Number(costUsd || 0);
      current.eventCount += Number(eventCount || 0);
      current.toolCallCount += Number(toolCallCount || 0);
      current.commandCount += Number(commandCount || 0);
      current.artifactCount += Number(artifactCount || 0);

      const startedAt = String(windowStart || session.startedAt || '').trim();
      const endedAt = String(windowEnd || session.endedAt || session.startedAt || '').trim();
      if (startedAt && (!current.firstSeenAt || toEpoch(startedAt) < toEpoch(current.firstSeenAt))) {
        current.firstSeenAt = startedAt;
      }
      if (endedAt && (!current.lastSeenAt || toEpoch(endedAt) > toEpoch(current.lastSeenAt))) {
        current.lastSeenAt = endedAt;
      }

      if (provisional) current.provisional = true;

      (pullRequests || []).forEach(pr => {
        addPullRequest(pr);
        const key = (String(pr.prUrl || '').trim() || String(pr.prNumber || '').trim() || String(pr.prRepository || '').trim()).toLowerCase();
        if (key) current?.pullRequestKeys.add(key);
      });
    };

    linkedSessions.forEach(session => {
      const metadata = session.sessionMetadata;
      const metadataPrLinks = Array.isArray(metadata?.prLinks) ? metadata.prLinks as PullRequestRef[] : [];
      const sessionPrLinks = Array.isArray(session.pullRequests) ? session.pullRequests : [];
      const mergedPrLinks = [...sessionPrLinks, ...metadataPrLinks];

      mergedPrLinks.forEach(addPullRequest);

      const correlationRows = Array.isArray(metadata?.commitCorrelations)
        ? metadata.commitCorrelations
        : [];

      if (correlationRows.length > 0) {
        correlationRows.forEach(rawRow => {
          if (!rawRow || typeof rawRow !== 'object') return;
          const commitHash = String(rawRow.commitHash || '').trim();
          const phases = Array.isArray(rawRow.phases)
            ? rawRow.phases.map(value => String(value || '').trim()).filter(Boolean)
            : [];
          const taskIds = Array.isArray(rawRow.taskIds)
            ? rawRow.taskIds.map(value => String(value || '').trim()).filter(Boolean)
            : [];
          const filePaths = Array.isArray(rawRow.filePaths)
            ? rawRow.filePaths.map(value => String(value || '')).filter(Boolean)
            : [];
          addCommitRow({
            session,
            commitHash,
            phases: phases.length > 0 ? phases : (session.relatedPhases || []),
            taskIds,
            filePaths,
            tokenInput: Number(rawRow.tokenInput || 0),
            tokenOutput: Number(rawRow.tokenOutput || 0),
            fileCount: Number(rawRow.fileCount || 0),
            additions: Number(rawRow.additions || 0),
            deletions: Number(rawRow.deletions || 0),
            costUsd: Number(rawRow.costUsd || 0),
            eventCount: Number(rawRow.eventCount || 0),
            toolCallCount: Number(rawRow.toolCallCount || 0),
            commandCount: Number(rawRow.commandCount || 0),
            artifactCount: Number(rawRow.artifactCount || 0),
            windowStart: String(rawRow.windowStart || ''),
            windowEnd: String(rawRow.windowEnd || ''),
            provisional: Boolean(rawRow.provisional),
            pullRequests: mergedPrLinks,
          });
        });
        return;
      }

      const commitHashes = Array.from(new Set([
        String(session.gitCommitHash || '').trim(),
        ...(session.gitCommitHashes || []),
        ...(session.commitHashes || []),
      ]))
        .map(normalizeCommitHash)
        .filter(Boolean);

      commitHashes.forEach(commitHash => {
        addCommitRow({
          session,
          commitHash,
          phases: session.relatedPhases || [],
          taskIds: [],
          filePaths: [],
          windowStart: session.startedAt,
          windowEnd: session.endedAt || session.startedAt,
          pullRequests: mergedPrLinks,
          provisional: commitHash === WORKING_TREE_COMMIT_HASH,
        });
      });
    });

    const pullRequests = Array.from(pullRequestMap.values()).sort((a, b) => {
      const aNumber = Number.parseInt(String(a.prNumber || ''), 10);
      const bNumber = Number.parseInt(String(b.prNumber || ''), 10);
      const aHas = Number.isFinite(aNumber);
      const bHas = Number.isFinite(bNumber);
      if (aHas && bHas && bNumber !== aNumber) return bNumber - aNumber;
      return String(a.prUrl || a.prRepository || '').localeCompare(String(b.prUrl || b.prRepository || ''));
    });

    const commits: GitCommitAggregate[] = Array.from(commitMap.values())
      .map(commit => ({
        commitHash: commit.commitHash,
        sessionIds: Array.from(commit.sessionIds),
        branches: Array.from(commit.branches).sort((a, b) => a.localeCompare(b)),
        phases: Array.from(commit.phases).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
        taskIds: Array.from(commit.taskIds).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
        filePaths: Array.from(commit.filePaths).sort((a, b) => a.localeCompare(b)),
        pullRequests: Array.from(commit.pullRequestKeys)
          .map(key => pullRequestMap.get(key))
          .filter((value): value is PullRequestRef => Boolean(value)),
        tokenInput: commit.tokenInput,
        tokenOutput: commit.tokenOutput,
        fileCount: commit.fileCount,
        additions: commit.additions,
        deletions: commit.deletions,
        costUsd: commit.costUsd,
        eventCount: commit.eventCount,
        toolCallCount: commit.toolCallCount,
        commandCount: commit.commandCount,
        artifactCount: commit.artifactCount,
        firstSeenAt: commit.firstSeenAt,
        lastSeenAt: commit.lastSeenAt,
        provisional: commit.provisional,
      }))
      .sort((a, b) => {
        const aTime = toEpoch(a.lastSeenAt || a.firstSeenAt);
        const bTime = toEpoch(b.lastSeenAt || b.firstSeenAt);
        if (aTime !== bTime) return bTime - aTime;
        return a.commitHash.localeCompare(b.commitHash);
      });

    const branches = Array.from(branchSet).sort((a, b) => a.localeCompare(b));
    return { commits, pullRequests, branches };
  }, [linkedSessions]);

  const filteredGitCommits = useMemo(() => {
    const normalized = normalizeCommitHash(gitHistoryCommitFilter);
    if (!normalized) return gitHistoryData.commits;
    return gitHistoryData.commits.filter(commit => commit.commitHash === normalized);
  }, [gitHistoryCommitFilter, gitHistoryData.commits]);
  const animatedPullRequests = useAnimatedListDiff(gitHistoryData.pullRequests, {
    getId: pr => getPullRequestStableKey(pr),
  });
  const animatedGitCommits = useAnimatedListDiff(filteredGitCommits, {
    getId: commit => commit.commitHash,
  });

  const phaseCommitLinks = useMemo(() => {
    const byPhase = new Map<string, GitCommitAggregate[]>();
    const addPhaseCommit = (phaseToken: string, commit: GitCommitAggregate) => {
      const key = String(phaseToken || '').trim();
      if (!key) return;
      const existing = byPhase.get(key) || [];
      if (existing.some(item => item.commitHash === commit.commitHash)) return;
      byPhase.set(key, [...existing, commit]);
    };

    gitHistoryData.commits.forEach(commit => {
      commit.phases.forEach(phase => {
        if (String(phase || '').toLowerCase() === 'all') {
          phases.forEach(row => addPhaseCommit(String(row.phase || ''), commit));
          return;
        }
        addPhaseCommit(phase, commit);
      });
    });

    return byPhase;
  }, [gitHistoryData.commits, phases]);

  const taskCommitLinksByTaskId = useMemo(() => {
    const byTask = new Map<string, GitCommitAggregate[]>();
    const canonicalTaskIdByLower = new Map<string, string>();
    const taskIdsByPhase = new Map<string, string[]>();

    phases.forEach(phase => {
      const phaseToken = String(phase.phase || '').trim();
      (phase.tasks || []).forEach(task => {
        const taskId = String(task.id || '').trim();
        if (!taskId) return;
        canonicalTaskIdByLower.set(taskId.toLowerCase(), taskId);
        if (phaseToken) {
          taskIdsByPhase.set(phaseToken, [...(taskIdsByPhase.get(phaseToken) || []), taskId]);
        }
      });
    });

    const addTaskCommit = (taskId: string, commit: GitCommitAggregate) => {
      const key = String(taskId || '').trim();
      if (!key) return;
      const existing = byTask.get(key) || [];
      if (existing.some(item => item.commitHash === commit.commitHash)) return;
      byTask.set(key, [...existing, commit]);
    };

    gitHistoryData.commits.forEach(commit => {
      const explicitTaskIds = commit.taskIds
        .map(taskId => canonicalTaskIdByLower.get(String(taskId || '').toLowerCase()) || String(taskId || '').trim())
        .filter(Boolean);

      explicitTaskIds.forEach(taskId => addTaskCommit(taskId, commit));
      if (explicitTaskIds.length > 0) return;

      commit.phases.forEach(phase => {
        const phaseToken = String(phase || '').trim();
        if (!phaseToken) return;
        (taskIdsByPhase.get(phaseToken) || []).forEach(taskId => addTaskCommit(taskId, commit));
      });
    });

    return byTask;
  }, [gitHistoryData.commits, phases]);

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

  const docsByGroup = useMemo(() => {
    const byGroup = new Map<DocGroupId, LinkedDocument[]>();
    groupedDocs.forEach(group => byGroup.set(group.id, group.docs));
    return byGroup;
  }, [groupedDocs]);

  const orderedLinkedDocs = useMemo(
    () => groupedDocs.flatMap(group => group.docs),
    [groupedDocs]
  );
  const docTypeCounts = useMemo(
    () => buildLinkedDocTypeCounts(linkedDocs),
    [linkedDocs]
  );
  const primaryDocIds = useMemo(() => {
    const ids = new Set<string>();
    const primary = activeFeature.primaryDocuments;
    const pushDoc = (doc?: LinkedDocument | null) => {
      if (!doc) return;
      if (doc.id) ids.add(doc.id);
      if (doc.filePath) ids.add(normalizePath(doc.filePath));
    };
    pushDoc(primary?.prd || null);
    pushDoc(primary?.implementationPlan || null);
    (primary?.phasePlans || []).forEach(pushDoc);
    (primary?.progressDocs || []).forEach(pushDoc);
    return ids;
  }, [activeFeature.primaryDocuments]);
  const progressDocPhaseBuckets = useMemo(
    () => groupDocsByPhaseLabel(docsByGroup.get('progress') || []),
    [docsByGroup]
  );
  const isPrimaryDoc = useCallback((doc: LinkedDocument) => (
    primaryDocIds.has(doc.id) || primaryDocIds.has(normalizePath(doc.filePath))
  ), [primaryDocIds]);
  const blockedByRelations = useMemo(
    () => (activeFeature.linkedFeatures || []).filter(relation => (relation.type || '').toLowerCase() === 'blocked_by'),
    [activeFeature.linkedFeatures]
  );
  const sequenceDocs = useMemo(
    () => linkedDocs.filter(doc => typeof doc.sequenceOrder === 'number'),
    [linkedDocs]
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

  const tabs = useMemo(() => {
    const base: Array<{ id: FeatureModalTab; label: string; icon: React.ComponentType<{ size?: number }> }> = [
      { id: 'overview', label: 'Overview', icon: Box },
      { id: 'phases', label: `Phases (${phases.length})`, icon: Layers },
      { id: 'docs', label: `Documents (${linkedDocs.length})`, icon: FileText },
      { id: 'relations', label: `Relations (${getFeatureLinkedFeatureCount(activeFeature)})`, icon: Link2 },
      {
        id: 'sessions',
        // P4-004: prefer server-reported total (from rollup/page) over materialized count.
        // Falls back to the local list length while first page is loading.
        label: `Sessions (${modalSections.sessionPagination.serverTotal > 0 ? modalSections.sessionPagination.serverTotal : linkedSessions.length})`,
        icon: Terminal,
      },
      { id: 'history', label: 'Git History', icon: Calendar },
    ];
    if ((featureTestHealth?.totalTests || 0) > 0) {
      base.push({ id: 'test-status', label: 'Test Status', icon: TestTube2 });
    }
    return base;
  }, [activeFeature, featureTestHealth?.totalTests, linkedDocs.length, linkedSessions.length, phases.length]);
  const modalTitleId = `feature-modal-title-${activeFeature.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const renderDocGrid = (docs: LinkedDocument[], compact = false) => (
    <div className={`grid grid-cols-1 gap-3 ${compact ? 'lg:grid-cols-2' : 'md:grid-cols-2 xl:grid-cols-3'}`}>
      {docs.map(doc => (
        <FeatureDocCard
          key={doc.id}
          doc={doc}
          primary={isPrimaryDoc(doc)}
          compact={compact}
          onClick={() => handleDocClick(doc)}
        />
      ))}
    </div>
  );

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
    const sessionTokenMetrics = resolveTokenMetrics(session, {
      hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, linkedSessions),
    });
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
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 text-indigo-300 bg-indigo-500/10">
              {Math.round(session.confidence * 100)}% confidence
            </span>
            {session.currentContextTokens && session.contextWindowSize ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-sky-500/25 text-sky-200 bg-sky-500/10">
                Context {Number(session.contextUtilizationPct || 0).toFixed(1)}%
              </span>
            ) : null}
          </div>
        )}
        headerRight={(
          <div className="flex items-center gap-4 text-right">
            <div>
              <div className="text-[9px] text-muted-foreground uppercase">Workload</div>
              <div className="text-xs font-mono text-sky-300">{formatTokenCount(sessionTokenMetrics.workloadTokens)}</div>
            </div>
            <div>
              <div className="text-[9px] text-muted-foreground uppercase">Cost</div>
              <div className="text-xs font-mono text-emerald-400">${resolveDisplayCost(session).toFixed(2)}</div>
            </div>
            <div>
              <div className="text-[9px] text-muted-foreground uppercase">Duration</div>
              <div className="text-xs font-mono text-muted-foreground">{Math.round(session.durationSeconds / 60)}m</div>
            </div>
            {primaryCommit && (
              <span
                title={primaryCommit}
                className="flex items-center gap-1 text-[10px] bg-surface-muted text-muted-foreground px-1.5 py-0.5 rounded border border-panel-border font-mono"
              >
                <GitCommit size={10} />
                {toShortCommitHash(primaryCommit)}
              </span>
            )}
          </div>
        )}
      >
        <div className="mb-3 text-[10px] flex flex-wrap items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded border ${linkRole === 'Primary' ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' : 'border-panel-border text-muted-foreground bg-surface-muted/70'}`}>
            {linkRole}
          </span>
          <span className={`px-1.5 py-0.5 rounded border ${threadLabel === 'Sub-thread' ? 'border-amber-500/40 text-amber-300 bg-amber-500/10' : 'border-blue-500/30 text-blue-300 bg-blue-500/10'}`}>
            {threadLabel}
          </span>
          <span className="px-1.5 py-0.5 rounded border border-purple-500/30 text-purple-300 bg-purple-500/10">
            {workflow}
          </span>
          {sessionTokenMetrics.cacheInputTokens > 0 && (
            <span className="px-1.5 py-0.5 rounded border border-cyan-500/25 text-cyan-200 bg-cyan-500/10">
              Cache {formatPercent(sessionTokenMetrics.cacheShare, 0)}
            </span>
          )}
        </div>

        {relatedTasks.length > 0 && (
          <div className="mt-3 pt-3 border-t border-panel-border/70">
            <div className="text-[10px] text-muted-foreground uppercase font-bold mb-2">Linked Tasks</div>
            <div className="space-y-1">
              {relatedTasks.map(({ phase, task }) => (
                <div key={task.id} className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">Phase {phase.phase}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="font-mono text-muted-foreground">{task.id}</span>
                  <span className="text-muted-foreground truncate">{task.title}</span>
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
    const shouldAnimateIn = animatedLinkedSessions.insertedIds.has(node.session.sessionId);

    return (
      <motion.div
        key={node.session.sessionId}
        layout="position"
        initial={shouldAnimateIn ? listInsertPreset.initial : false}
        animate={shouldAnimateIn ? listInsertPreset.animate : undefined}
        exit={listInsertPreset.exit}
        transition={listInsertPreset.transition}
        className="space-y-2"
      >
        {renderSessionCard(node.session, hasChildren ? {
          expanded: isExpanded,
          childCount: countThreadNodes(node.children),
          onToggle: () => toggleSubthreads(node.session.sessionId),
          label: 'Sub-Threads',
        } : undefined)}
        <AnimatePresence initial={false}>
          {hasChildren && isExpanded && (
            <motion.div
              layout
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, height: 'auto' }}
              exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
              transition={listInsertPreset.transition}
              className={`mt-3 ${depth > 0 ? 'ml-2' : ''} pl-4 border-l border-panel-border/90 space-y-3 overflow-hidden`}
            >
              <AnimatePresence initial={false}>
                {node.children.map(child => (
                  <motion.div key={child.session.sessionId} layout="position" className="relative pl-3">
                    <div className="absolute left-0 top-5 w-3 border-t border-panel-border/90" />
                    {renderSessionTreeNode(child, depth + 1)}
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    );
  };

  const renderCompactSessionCard = (
    session: FeatureSessionLink,
    threadToggle?: {
      expanded: boolean;
      childCount: number;
      onToggle: () => void;
    }
  ) => {
    const openSession = () => {
      onClose();
      navigate(`/sessions?session=${encodeURIComponent(session.sessionId)}`);
    };
    const displayTitle = deriveSessionCardTitle(session.sessionId, (session.title || '').trim(), session.sessionMetadata || null);
    const workflow = (session.workflowType || session.sessionType || '').trim() || 'Related';
    const threadLabel = isSubthreadSession(session) ? 'Sub-thread' : 'Main thread';
    const phaseNumbers = getSessionPhaseNumbers(session);
    const metrics = resolveTokenMetrics(session, {
      hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, linkedSessions),
    });
    const primaryCommit = session.gitCommitHash || session.gitCommitHashes?.[0] || session.commitHashes?.[0];
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
        metadata={session.sessionMetadata || null}
        threadToggle={threadToggle ? {
          ...threadToggle,
          label: 'Sub-Threads',
        } : undefined}
        onClick={openSession}
        className="h-full rounded-lg p-3 hover:border-info-border"
        infoBadges={(
          <div className="flex flex-wrap items-center gap-1">
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${isPrimarySession(session)
              ? 'border-success-border bg-success/10 text-success'
              : 'border-panel-border bg-panel text-muted-foreground'
              }`}>
              {isPrimarySession(session) ? 'Primary' : 'Related'}
            </span>
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${isSubthreadSession(session)
              ? 'border-warning-border bg-warning/10 text-warning'
              : 'border-info-border bg-info/10 text-info'
              }`}>
              {threadLabel}
            </span>
            <span className="rounded border border-purple-500/30 bg-purple-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-purple-400">
              {workflow}
            </span>
          </div>
        )}
        headerRight={(
          <div className="text-right">
            <div className="font-mono text-xs font-semibold text-success">${resolveDisplayCost(session).toFixed(2)}</div>
          </div>
        )}
      >
        <div className="grid grid-cols-3 gap-2 border-t border-panel-border/70 pt-3 text-[11px]">
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Confidence</div>
            <div className="mt-1 font-mono text-panel-foreground">{Math.round(session.confidence * 100)}%</div>
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Workload</div>
            <div className="mt-1 font-mono text-info">{formatTokenCount(metrics.workloadTokens)}</div>
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Duration</div>
            <div className="mt-1 font-mono text-muted-foreground">{Math.round((session.durationSeconds || 0) / 60)}m</div>
          </div>
        </div>
        {(phaseNumbers.length > 0 || primaryCommit) && (
          <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
            {phaseNumbers.slice(0, 3).map(phase => (
              <span key={`${session.sessionId}-phase-${phase}`} className="rounded-full border border-panel-border bg-panel px-2 py-0.5 text-foreground">
                Phase {phase}
              </span>
            ))}
            {primaryCommit ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-panel px-2 py-0.5 font-mono text-muted-foreground">
                <GitCommit size={10} />
                {toShortCommitHash(primaryCommit)}
              </span>
            ) : null}
          </div>
        )}
      </SessionCard>
    );
  };

  const renderSessionGridNode = (node: FeatureSessionTreeNode, depth = 0): React.ReactNode => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedSubthreadsBySessionId.has(node.session.sessionId);
    return (
      <div key={`grid-${node.session.sessionId}`} className="space-y-3">
        {renderCompactSessionCard(node.session, hasChildren ? {
          expanded: isExpanded,
          childCount: countThreadNodes(node.children),
          onToggle: () => toggleSubthreads(node.session.sessionId),
        } : undefined)}
        {hasChildren && isExpanded && (
          <div className={`grid grid-cols-1 gap-3 ${depth > 0 ? 'pl-3' : ''} md:grid-cols-2 xl:grid-cols-3`}>
            {node.children.map(child => renderSessionGridNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  const renderSessionGrid = (roots: FeatureSessionTreeNode[]) => (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {roots.map(node => renderSessionGridNode(node))}
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-surface-overlay/90 p-3 backdrop-blur-sm animate-in fade-in duration-200 sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={modalTitleId}
        className="flex h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-panel-border bg-panel text-panel-foreground shadow-[var(--viewer-shell-shadow)]"
        onClick={e => e.stopPropagation()}
      >

        {/* Header */}
        <div className="border-b border-panel-border bg-surface-overlay/95 px-4 py-4 sm:px-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone="muted" mono className="max-w-full truncate rounded-md px-2 py-1 text-[11px]">
                  {feature.id}
                </Badge>
                <StatusDropdown status={activeFeature.status} onStatusChange={handleFeatureStatusChange} />
                {updatingStatus && <RefreshCw size={14} className="text-info animate-spin" />}
                {activeFeature.category && (
                  <Badge tone="outline" className="uppercase tracking-wide">
                    {activeFeature.category}
                  </Badge>
                )}
                {featureDeferredTasks > 0 && (
                  <Badge tone="warning" className="uppercase tracking-wide">
                    Done with deferrals
                  </Badge>
                )}
              </div>
              <h2 id={modalTitleId} className="text-balance text-2xl font-semibold leading-tight text-panel-foreground">
                {activeFeature.name}
              </h2>
              <div className="mt-3 grid gap-3 text-xs text-muted-foreground sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <ProgressBar completed={featureCompletedTasks} deferred={featureDeferredTasks} total={activeFeature.totalTasks} />
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-medium text-panel-foreground">{pct}% complete</span>
                  <span>{featureCompletedTasks}/{activeFeature.totalTasks} tasks</span>
                  {featureDeferredTasks > 0 && (
                    <span className="text-warning">{featureDeferredTasks} deferred</span>
                  )}
                  {primaryFeatureDate.value && (
                    <span className="inline-flex items-center gap-1">
                      <Calendar size={12} />
                      {primaryFeatureDate.label}: {new Date(primaryFeatureDate.value).toLocaleDateString()}
                      {primaryFeatureDate.confidence ? ` (${primaryFeatureDate.confidence})` : ''}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={handleBeginWork}
                className="border border-info-border bg-info/10 text-info shadow-sm hover:bg-info/20"
              >
                <Play size={14} />
                Begin Work
              </Button>
              <Button
                type="button"
                size="sm"
                variant="panel"
                onClick={() => {
                  navigate(planningFeatureDetailHref(feature.id));
                  onClose();
                }}
                title="Open full planning detail"
              >
                <ExternalLink size={13} />
                Expand
              </Button>
              <Button type="button" size="icon" variant="ghost" onClick={onClose} aria-label="Close feature modal">
                <X size={18} />
              </Button>
            </div>
          </div>
        </div>

        {/* Tab Nav */}
        <div className="border-b border-panel-border bg-panel px-3 py-2 sm:px-6">
          <div className="flex gap-1 overflow-x-auto rounded-lg border border-panel-border bg-surface-muted/70 p-1">
            {tabs.map(tab => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id as any)}
                className={`inline-flex min-h-9 shrink-0 items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold transition-colors ${activeTab === tab.id
                  ? 'bg-panel text-panel-foreground shadow-sm'
                  : 'text-muted-foreground hover:bg-hover/70 hover:text-foreground'
                  }`}
              >
                <tab.icon size={15} />
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto bg-surface-muted/45 p-4 sm:p-6">

          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Stats Grid */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <FeatureMetricTile
                  label="Total Tasks"
                  value={activeFeature.totalTasks}
                  detail={`${pct}% overall progress`}
                  icon={ClipboardList}
                />
                <FeatureMetricTile
                  label="Completed"
                  value={featureDoneTasks}
                  detail={featureDeferredTasks > 0 ? `${featureDeferredTasks} deferred count as complete` : 'No deferred completion caveats'}
                  icon={CheckCircle2}
                  accentClassName="text-success"
                />
                <FeatureMetricTile
                  label="Phases"
                  value={phases.length}
                  detail={`${filteredPhases.length} visible with current filters`}
                  icon={Layers}
                  accentClassName="text-info"
                />
                <FeatureMetricTile
                  label="Documents"
                  value={linkedDocs.length}
                  detail={`${groupedDocs.length} document groups`}
                  icon={FileText}
                  accentClassName="text-warning"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
                <FeatureModalSection
                  title="Delivery Metadata"
                  description="Planning attributes that explain priority, ownership, release fit, and execution readiness."
                  icon={LayoutGrid}
                >
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    <FeatureField label="Priority" value={featureValue(activeFeature.priority)} />
                    <FeatureField label="Risk" value={featureValue(activeFeature.riskLevel)} />
                    <FeatureField label="Complexity" value={featureValue(activeFeature.complexity)} />
                    <FeatureField label="Track" value={featureValue(activeFeature.track)} />
                    <FeatureField label="Family" value={featureValue(activeFeature.featureFamily)} mono />
                    <FeatureField label="Target" value={featureValue(activeFeature.targetRelease)} />
                    <FeatureField label="Milestone" value={featureValue(activeFeature.milestone)} />
                    <FeatureField label="Readiness" value={featureValue(activeFeature.executionReadiness)} />
                    <FeatureField label="Coverage" value={getFeatureCoverageSummary(activeFeature)} />
                  </div>
                </FeatureModalSection>
                <FeatureModalSection
                  title="Quality Signals"
                  description="Risk and integrity signals that deserve attention before execution."
                  icon={BarChart3}
                >
                  <div className="grid grid-cols-2 gap-2">
                    <FeatureField label="Blockers" value={activeFeature.qualitySignals?.blockerCount ?? 0} />
                    <FeatureField label="At Risk" value={activeFeature.qualitySignals?.atRiskTaskCount ?? 0} />
                    <FeatureField label="Blocked By" value={blockedByRelations.length} />
                    <FeatureField label="Test Impact" value={featureValue(activeFeature.testImpact || activeFeature.qualitySignals?.testImpact)} />
                    <FeatureField label="Relations" value={getFeatureLinkedFeatureCount(activeFeature)} />
                  </div>
                  {(activeFeature.qualitySignals?.integritySignalRefs || []).length > 0 && (
                    <div className="mt-3 rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2 text-[11px] text-muted-foreground">
                      <span className="font-semibold text-panel-foreground">Integrity refs:</span> {(activeFeature.qualitySignals?.integritySignalRefs || []).join(', ')}
                    </div>
                  )}
                </FeatureModalSection>
              </div>

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
                <FeatureModalSection
                  title="Execution Gate"
                  description={executionGate?.reason || dependencyState?.blockingReason || 'No gate reason available.'}
                  icon={Play}
                  headerRight={(
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${getExecutionGateStyle(executionGate?.state)}`}>
                      {getExecutionGateLabel(executionGate?.state)}
                    </span>
                  )}
                >
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 xl:grid-cols-1">
                    <FeatureField label="Ready" value={executionGate?.isReady ? 'Yes' : 'No'} />
                    <FeatureField label="Waiting on family" value={executionGate?.waitingOnFamilyPredecessor ? 'Yes' : 'No'} />
                    <FeatureField label="Next item" value={familyPosition?.nextItemLabel || nextFamilyItem?.featureName || '-'} mono />
                  </div>
                </FeatureModalSection>
                <FeatureModalSection
                  title="Family Position"
                  description="Where this feature sits in its execution family."
                  icon={Link2}
                  headerRight={(
                    <Badge tone="outline" mono className="max-w-[160px] truncate rounded-md border-info-border bg-info/10 text-info uppercase">
                      {familySummary?.featureFamily || activeFeature.featureFamily || '-'}
                    </Badge>
                  )}
                >
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                    <FeatureField label="Position" value={getFamilyPositionLabel(familyPosition)} />
                    <FeatureField label="Sequenced" value={familySummary?.sequencedItems ?? familyPosition?.sequencedItems ?? 0} />
                    <FeatureField label="Unsequenced" value={familySummary?.unsequencedItems ?? familyPosition?.unsequencedItems ?? 0} />
                    <FeatureField label="Next feature" value={familySummary?.nextRecommendedFeatureId || nextFamilyItem?.featureId || '-'} mono />
                  </div>
                </FeatureModalSection>
                <FeatureModalSection
                  title="Blocker Evidence"
                  description="Dependency evidence attached to this feature."
                  icon={Filter}
                  headerRight={(
                    <Badge
                      tone="outline"
                      mono
                      className={blockingEvidence.length > 0
                        ? 'border-danger-border bg-danger/10 text-danger'
                        : 'border-success-border bg-success/10 text-success'
                      }
                    >
                      {blockingEvidence.length}
                    </Badge>
                  )}
                >
                  {blockingEvidence.length > 0 ? (
                    <div className="space-y-2">
                      {blockingEvidence.slice(0, 3).map(evidence => (
                        <div key={evidence.dependencyFeatureId} className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-[11px]">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-foreground truncate">{getDependencyEvidenceLabel(evidence)}</span>
                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${evidence.state === 'complete'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                              : evidence.state === 'blocked_unknown'
                                ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                                : 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                              }`}>
                              {evidence.state}
                            </span>
                          </div>
                          {evidence.blockingReason && (
                            <div className="mt-1 text-muted-foreground">{evidence.blockingReason}</div>
                          )}
                          {(evidence.blockingDocumentIds || []).length > 0 && (
                            <div className="mt-1 text-muted-foreground">
                              Docs: <span className="font-mono text-foreground">{evidence.blockingDocumentIds.join(', ')}</span>
                            </div>
                          )}
                        </div>
                      ))}
                      {blockingEvidence.length > 3 && (
                        <div className="text-[11px] text-muted-foreground">+{blockingEvidence.length - 3} more blocker entries</div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground italic">No blocker evidence is attached.</p>
                  )}
                </FeatureModalSection>
              </div>

              <FeatureModalSection title="Date Signals" icon={Calendar}>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    { label: 'Planned', value: getFeatureDateValue(activeFeature, 'plannedAt') },
                    { label: 'Started', value: getFeatureDateValue(activeFeature, 'startedAt') },
                    { label: 'Completed', value: getFeatureDateValue(activeFeature, 'completedAt') },
                    { label: 'Updated', value: getFeatureDateValue(activeFeature, 'updatedAt') },
                  ].map(item => (
                    <div key={item.label} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3 text-xs">
                      <div className="font-bold uppercase tracking-wider text-muted-foreground">{item.label}</div>
                      <div className="mt-1 text-sm text-panel-foreground">
                        {item.value.value ? new Date(item.value.value).toLocaleDateString() : '-'}
                        {item.value.confidence ? ` (${item.value.confidence})` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </FeatureModalSection>

              {(blockedByRelations.length > 0 || sequenceDocs.length > 0) && (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FeatureModalSection title="Hard Dependencies" icon={Link2}>
                    <div className="flex flex-wrap gap-2">
                      {blockedByRelations.map((relation, index) => (
                        <button
                          key={`${relation.feature}-${index}`}
                          onClick={() => { onClose(); navigate(planningFeatureModalHref(relation.feature)); }}
                          className="rounded-full border border-danger-border bg-danger/10 px-2 py-1 text-[10px] font-semibold text-danger"
                        >
                          {relation.feature}
                        </button>
                      ))}
                      {blockedByRelations.length === 0 && <span className="text-xs text-muted-foreground italic">No hard feature dependencies captured.</span>}
                    </div>
                  </FeatureModalSection>
                  <FeatureModalSection title="Family Sequence" icon={Layers}>
                    <div className="grid grid-cols-2 gap-2">
                      <FeatureField label="Family" value={activeFeature.featureFamily || '-'} mono />
                      <FeatureField label="Sequenced docs" value={sequenceDocs.length} />
                    </div>
                    {sequenceDocs.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {sequenceDocs.slice(0, 6).map(doc => (
                          <button
                            key={`seq-doc-${doc.id}`}
                            onClick={() => handleDocClick(doc)}
                            className="rounded-full border border-panel-border bg-surface-overlay px-2 py-1 text-[10px] text-foreground hover:border-info-border"
                          >
                            #{doc.sequenceOrder} {doc.title}
                          </button>
                        ))}
                      </div>
                    )}
                  </FeatureModalSection>
                </div>
              )}

              {/* Linked Documents — clickable */}
              {linkedDocs.length > 0 && (
                <FeatureModalSection title="Linked Documents" icon={FileText}>
                  <div className="space-y-2">
                    {orderedLinkedDocs.map(doc => (
                      <button
                        key={doc.id}
                        onClick={() => handleDocClick(doc)}
                        className="group flex w-full items-center gap-3 rounded-lg border border-panel-border bg-surface-overlay/70 p-3 text-left transition-all hover:border-info-border hover:bg-surface-muted/70"
                      >
                        <DocTypeIcon docType={doc.docType} />
                        <span className="flex-1 truncate text-sm text-foreground transition-colors group-hover:text-info">{doc.title}</span>
                        <DocTypeBadge docType={doc.docType} />
                        <ExternalLink size={12} className="text-muted-foreground transition-colors group-hover:text-info" />
                      </button>
                    ))}
                  </div>
                </FeatureModalSection>
              )}

              {/* Related Features */}
              {activeFeature.relatedFeatures.length > 0 && (
                <FeatureModalSection title="Related Features" icon={Link2}>
                  <div className="flex flex-wrap gap-2">
                    {activeFeature.relatedFeatures.map(rel => (
                      <span key={rel} className="rounded border border-panel-border bg-surface-muted px-2 py-1 text-xs text-info">
                        {rel}
                      </span>
                    ))}
                  </div>
                </FeatureModalSection>
              )}

              {/* Tags */}
              {activeFeature.tags.length > 0 && (
                <FeatureModalSection title="Tags" icon={Tag}>
                  <div className="flex flex-wrap gap-2">
                    {activeFeature.tags.map(tag => (
                      <span key={tag} className="flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] text-muted-foreground">
                        <Tag size={10} />{tag}
                      </span>
                    ))}
                  </div>
                </FeatureModalSection>
              )}
            </div>
          )}

          {/* Phases Tab */}
          {activeTab === 'phases' && (
            <TabStateView
              status={modalSections.phases.status}
              error={modalSections.phases.error?.message}
              onRetry={modalSections.phases.retry}
              isEmpty={phases.length === 0 && modalSections.phases.status === 'success'}
              emptyLabel="No phases tracked for this feature."
              staleLabel="Refreshing phases…"
            >
            <div className="space-y-3">
              {phases.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-3 rounded-lg border border-panel-border bg-panel/70">
                  <div>
                    <label className="text-[10px] text-muted-foreground mb-1 block uppercase">Phase Status</label>
                    <select
                      value={phaseStatusFilter}
                      onChange={(e) => setPhaseStatusFilter(e.target.value)}
                      className="w-full bg-surface-overlay border border-panel-border rounded px-2 py-1 text-xs text-panel-foreground focus:border-focus focus:outline-none"
                    >
                      <option value="all">All</option>
                      {FEATURE_STATUS_OPTIONS.map(status => (
                        <option key={`phase-filter-${status}`} value={status}>{getStatusStyle(status).label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground mb-1 block uppercase">Task Status</label>
                    <select
                      value={taskStatusFilter}
                      onChange={(e) => setTaskStatusFilter(e.target.value)}
                      className="w-full bg-surface-overlay border border-panel-border rounded px-2 py-1 text-xs text-panel-foreground focus:border-focus focus:outline-none"
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
                <div className="text-center py-12 text-muted-foreground border border-dashed border-panel-border rounded-xl">
                  <Layers size={32} className="mx-auto mb-3 opacity-50" />
                  <p>{phases.length === 0 ? 'No phases tracked for this feature.' : 'No phases match your filters.'}</p>
                </div>
              )}
              {filteredPhases.map(phase => {
                const phaseStatus = getStatusStyle(phase.status);
                const phaseKey = phase.id || phase.phase;
                const isExpanded = expandedPhases.has(phaseKey);
                const phaseTasks = dedupePhaseTasks(phase.tasks || []);
                const phaseDoneTasks = phaseTasks.filter(task => task.status === 'done').length;
                const phaseDeferredTasks = phaseTasks.filter(task => task.status === 'deferred').length;
                const phaseCompletedTasks = phaseTasks.length > 0 ? phaseDoneTasks + phaseDeferredTasks : getPhaseCompletedCount(phase);
                const phaseTotalTasks = phaseTasks.length > 0 ? Math.max(phase.totalTasks || 0, phaseTasks.length) : phase.totalTasks;
                const phaseRelatedSessions = phaseSessionLinks.get(String(phase.phase || '').trim()) || [];
                const phaseRelatedCommits = phaseCommitLinks.get(String(phase.phase || '').trim()) || [];
                const visibleTasks = taskStatusFilter === 'all'
                  ? phaseTasks
                  : phaseTasks.filter(task => task.status === taskStatusFilter);
                return (
                  <div key={phaseKey} className="bg-panel border border-panel-border rounded-lg overflow-hidden">
                    <div className="flex items-start gap-3 p-4 hover:bg-surface-muted/60 transition-colors">
                      <div className="flex-1 min-w-0">
                        <button
                          onClick={() => togglePhase(phaseKey)}
                          className="w-full flex items-center gap-3 text-left"
                        >
                          {isExpanded ? <ChevronDown size={16} className="text-muted-foreground" /> : <ChevronRight size={16} className="text-muted-foreground" />}
                          <div className={`w-2 h-2 rounded-full ${phaseStatus.dot}`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-panel-foreground">Phase {phase.phase}</span>
                              {phase.title && (
                                <span className="text-sm text-muted-foreground truncate">- {phase.title}</span>
                              )}
                              {phaseDeferredTasks > 0 && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10 uppercase">
                                  Deferred
                                </span>
                              )}
                            </div>
                            <div className="mt-1">
                              <ProgressBar completed={phaseCompletedTasks} deferred={phaseDeferredTasks} total={phaseTotalTasks} />
                            </div>
                          </div>
                        </button>
                        {phaseRelatedSessions.length > 0 && (
                          <div className="mt-2 ml-7 flex flex-wrap items-center gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Sessions</span>
                            {phaseRelatedSessions.slice(0, 3).map(sessionLink => (
                              <button
                                key={`phase-${phaseKey}-session-${sessionLink.sessionId}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onClose();
                                  navigate(`/sessions?session=${encodeURIComponent(sessionLink.sessionId)}`);
                                }}
                                className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 font-mono hover:bg-indigo-500/20 transition-colors"
                                title="Go to linked session"
                              >
                                {sessionLink.sessionId}
                              </button>
                            ))}
                            {phaseRelatedSessions.length > 3 && (
                              <span className="text-[10px] text-muted-foreground">+{phaseRelatedSessions.length - 3} more</span>
                            )}
                          </div>
                        )}
                        {phaseRelatedCommits.length > 0 && (
                          <div className="mt-2 ml-7 flex flex-wrap items-center gap-1">
                            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Commits</span>
                            {phaseRelatedCommits.slice(0, 5).map(commitRef => (
                              <button
                                key={`phase-${phaseKey}-commit-${commitRef.commitHash}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openGitCommitInHistory(commitRef.commitHash);
                                }}
                                className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 font-mono hover:bg-emerald-500/20 transition-colors"
                                title={`Open ${commitRef.commitHash} in Git history`}
                              >
                                {toShortCommitHash(commitRef.commitHash)}
                              </button>
                            ))}
                            {phaseRelatedCommits.length > 5 && (
                              <span className="text-[10px] text-muted-foreground">+{phaseRelatedCommits.length - 5} more</span>
                            )}
                          </div>
                        )}
                      </div>
                      <StatusDropdown
                        status={phase.status}
                        onStatusChange={(s) => handlePhaseStatusChange(phase.phase, s)}
                        size="xs"
                      />
                    </div>

                    {/* Expanded task list */}
                    {isExpanded && visibleTasks.length > 0 && (
                      <div className="border-t border-panel-border px-4 py-3 space-y-1.5 bg-surface-overlay/60">
                        {visibleTasks.map(task => {
                          const normalizedStatus = (task.status || '').toLowerCase();
                          const taskDone = normalizedStatus === 'done';
                          const taskDeferred = normalizedStatus === 'deferred';
                          const nextStatus = taskDone ? 'deferred' : taskDeferred ? 'backlog' : 'done';
                          const markTitle = taskDone ? 'Mark deferred' : taskDeferred ? 'Mark backlog' : 'Mark done';
                          const taskSessionLinks = taskSessionLinksByTaskId.get(String(task.id || '').trim()) || [];
                          const taskTextClass = taskDone
                            ? 'text-muted-foreground line-through'
                            : taskDeferred
                              ? 'text-amber-300/90 italic'
                              : 'text-foreground';
                          const correlatedCommits = taskCommitLinksByTaskId.get(String(task.id || '').trim()) || [];
                          const taskCommitHashes = Array.from(
                            new Set(
                              [
                                normalizeCommitHash(String(task.commitHash || '')),
                                ...correlatedCommits.map(commit => normalizeCommitHash(commit.commitHash)),
                              ].filter(Boolean)
                            )
                          );
                          return (
                            <div key={`${task.id}-${task.sourceFile || ''}`} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-panel transition-colors">
                              <button
                                onClick={() => handleTaskStatusChange(phase.phase, task.id, nextStatus as ProjectTask['status'])}
                                className="flex-shrink-0 hover:scale-110 transition-transform"
                                title={markTitle}
                              >
                                {taskDone ? (
                                  <CheckCircle2 size={14} className="text-emerald-500" />
                                ) : taskDeferred ? (
                                  <CircleDashed size={14} className="text-amber-400" />
                                ) : (
                                  <Circle size={14} className="text-muted-foreground hover:text-indigo-400" />
                                )}
                              </button>
                              <button
                                onClick={() => setViewingTask(task)}
                                className="font-mono text-[10px] text-muted-foreground w-16 flex-shrink-0 hover:text-indigo-400 transition-colors cursor-pointer text-left"
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
                              {taskCommitHashes.length > 0 && (
                                <div className="flex items-center gap-1 flex-wrap">
                                  {taskCommitHashes.slice(0, 3).map(hash => (
                                    <button
                                      key={`${task.id}-commit-${hash}`}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        openGitCommitInHistory(hash);
                                      }}
                                      className="flex items-center gap-1 text-[10px] bg-surface-muted text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/30 font-mono flex-shrink-0 hover:bg-emerald-500/20 transition-colors"
                                      title={`Open ${hash} in Git history`}
                                    >
                                      <GitCommit size={10} />
                                      {toShortCommitHash(hash)}
                                    </button>
                                  ))}
                                  {taskCommitHashes.length > 3 && (
                                    <span className="text-[10px] text-muted-foreground">+{taskCommitHashes.length - 3} more</span>
                                  )}
                                </div>
                              )}
                              {taskSessionLinks.length > 0 && (
                                <div className="flex items-center gap-1 flex-wrap">
                                  {taskSessionLinks.slice(0, 3).map(link => (
                                    <button
                                      key={`${task.id}-session-${link.sessionId}-${link.source}`}
                                      onClick={(e) => { e.stopPropagation(); onClose(); navigate(`/sessions?session=${encodeURIComponent(link.sessionId)}`); }}
                                      className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-mono transition-colors flex-shrink-0 ${link.isSubthread
                                        ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20'
                                        : 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30 hover:bg-indigo-500/20'
                                        }`}
                                      title={link.isSubthread ? 'Go to linked sub-thread session' : 'Go to linked session'}
                                    >
                                      <Terminal size={10} />
                                      {link.sessionId}
                                    </button>
                                  ))}
                                  {taskSessionLinks.length > 3 && (
                                    <span className="text-[10px] text-muted-foreground">+{taskSessionLinks.length - 3} more</span>
                                  )}
                                </div>
                              )}
                              {task.owner && (
                                <span className="text-[10px] text-muted-foreground truncate max-w-[100px] flex-shrink-0">{task.owner}</span>
                              )}
                              <StatusDropdown
                                status={task.status}
                                onStatusChange={(s) => handleTaskStatusChange(phase.phase, task.id, s as ProjectTask['status'])}
                                size="xs"
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {isExpanded && visibleTasks.length === 0 && (
                      <div className="border-t border-panel-border px-4 py-3 text-xs text-muted-foreground italic">
                        No task details match the current task filter.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            </TabStateView>
          )}

          {/* Documents Tab — clickable */}
          {activeTab === 'docs' && (
            <TabStateView
              status={modalSections.docs.status}
              error={modalSections.docs.error?.message}
              onRetry={modalSections.docs.retry}
              isEmpty={linkedDocs.length === 0 && modalSections.docs.status === 'success'}
              emptyLabel="No documents linked to this feature."
              staleLabel="Refreshing documents…"
            >
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <FeatureMetricTile
                  label="Document Groups"
                  value={groupedDocs.length}
                  detail={`${linkedDocs.length} linked documents`}
                  icon={FileText}
                />
                <FeatureMetricTile
                  label="Family Position"
                  value={getFamilyPositionLabel(familyPosition)}
                  detail={familySummary?.featureFamily || activeFeature.featureFamily || 'No family assigned'}
                  icon={Link2}
                  accentClassName="text-info"
                />
                <FeatureMetricTile
                  label="Execution Gate"
                  value={getExecutionGateLabel(executionGate?.state)}
                  detail={executionGate?.reason || dependencyState?.blockingReason || 'No gate reason available'}
                  icon={Play}
                  accentClassName="text-warning"
                />
              </div>

              {docTypeCounts.length > 0 && (
                <Surface tone="panel" padding="sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Types</span>
                    {docTypeCounts.map(row => (
                      <span
                        key={`doc-type-count-${row.docType}`}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-bold uppercase ${getDocTypeTone(row.docType)}`}
                      >
                        <DocTypeIcon docType={row.docType} />
                        {getDocTypeLabel(row.docType)}
                        <span className="font-mono">{row.count}</span>
                      </span>
                    ))}
                  </div>
                </Surface>
              )}

              {linkedDocs.length === 0 && (
                <div className="text-center py-12 text-muted-foreground border border-dashed border-panel-border rounded-xl">
                  <FileText size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No documents linked to this feature.</p>
                </div>
              )}

              {DOC_GROUPS.filter(group => group.id !== 'progress').map(group => {
                const docs = docsByGroup.get(group.id) || [];
                if (docs.length === 0) return null;
                const Icon = getDocGroupIcon(group.id);
                const implementationPlans = group.id === 'plans'
                  ? docs.filter(doc => (doc.docType || '').toLowerCase() === 'implementation_plan')
                  : [];
                const phasePlans = group.id === 'plans'
                  ? docs.filter(doc => (doc.docType || '').toLowerCase() === 'phase_plan')
                  : [];
                return (
                  <FeatureModalSection
                    key={group.id}
                    title={group.label}
                    description={group.description}
                    icon={Icon}
                    headerRight={(
                      <button
                        type="button"
                        onClick={() => toggleDocGroup(group.id)}
                        className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:text-panel-foreground"
                      >
                        {docGroupExpanded[group.id] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        {docs.length}
                      </button>
                    )}
                  >
                    {docGroupExpanded[group.id] && (
                      group.id === 'plans' ? (
                        <div className="space-y-4">
                          {implementationPlans.length > 0 && (
                            <div>
                              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Implementation Plans</div>
                              {renderDocGrid(implementationPlans)}
                            </div>
                          )}
                          {phasePlans.length > 0 && (
                            <div>
                              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Phase Plans</div>
                              {renderDocGrid(phasePlans)}
                            </div>
                          )}
                          {implementationPlans.length === 0 && phasePlans.length === 0 && renderDocGrid(docs)}
                        </div>
                      ) : renderDocGrid(docs)
                    )}
                  </FeatureModalSection>
                );
              })}

              {(docsByGroup.get('progress') || []).length > 0 && (
                <FeatureModalSection
                  title="Progress Files"
                  description="Execution and phase progress files, grouped under their detected phase when available."
                  icon={Terminal}
                  headerRight={(
                    <button
                      type="button"
                      onClick={() => toggleDocGroup('progress')}
                      className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:text-panel-foreground"
                    >
                      {docGroupExpanded.progress ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      {(docsByGroup.get('progress') || []).length}
                    </button>
                  )}
                >
                  {docGroupExpanded.progress && (
                    <div className="space-y-4">
                      {progressDocPhaseBuckets.map(bucket => (
                        <div key={`progress-${bucket.label}`} className="rounded-lg border border-panel-border bg-surface-muted/55 p-3">
                          <div className="mb-3 flex items-center justify-between gap-3">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-panel-foreground">{bucket.label}</div>
                            <span className="font-mono text-[10px] text-muted-foreground">{bucket.docs.length}</span>
                          </div>
                          {renderDocGrid(bucket.docs, true)}
                        </div>
                      ))}
                    </div>
                  )}
                </FeatureModalSection>
              )}
            </div>
            </TabStateView>
          )}
          {activeTab === 'relations' && (
            <TabStateView
              status={modalSections.relations.status}
              error={modalSections.relations.error?.message}
              onRetry={modalSections.relations.retry}
              isEmpty={(activeFeature.linkedFeatures || []).length === 0 && activeFeature.relatedFeatures.length === 0 && modalSections.relations.status === 'success'}
              emptyLabel="No relations found for this feature."
              staleLabel="Refreshing relations…"
            >
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-panel border border-panel-border rounded-lg p-4">
                  <h3 className="text-xs font-bold text-muted-foreground uppercase mb-3">Dependency Evidence</h3>
                  <div className="space-y-2">
                    {blockingEvidence.length > 0 ? blockingEvidence.map(evidence => (
                      <div key={`dependency-${evidence.dependencyFeatureId}`} className="rounded border border-panel-border bg-surface-overlay px-3 py-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <button
                            onClick={() => {
                              if (!evidence.dependencyFeatureId) return;
                              onClose();
                              navigate(planningFeatureModalHref(evidence.dependencyFeatureId));
                            }}
                            className="font-mono text-indigo-300 hover:text-indigo-200 text-left truncate"
                          >
                            {evidence.dependencyFeatureName || evidence.dependencyFeatureId}
                          </button>
                          <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border ${evidence.state === 'complete'
                            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                            : evidence.state === 'blocked_unknown'
                              ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                              : 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                            }`}>
                            {evidence.state}
                          </span>
                        </div>
                        <div className="mt-1 text-muted-foreground">{evidence.blockingReason || 'No blocker reason recorded.'}</div>
                        {evidence.dependencyCompletionEvidence.length > 0 && (
                          <div className="mt-1 text-muted-foreground">
                            Evidence: <span className="font-mono text-foreground">{evidence.dependencyCompletionEvidence.join(', ')}</span>
                          </div>
                        )}
                        {(evidence.blockingDocumentIds || []).length > 0 && (
                          <div className="mt-1 text-muted-foreground">
                            Documents: <span className="font-mono text-foreground">{evidence.blockingDocumentIds.join(', ')}</span>
                          </div>
                        )}
                      </div>
                    )) : (
                      <p className="text-xs text-muted-foreground italic">No dependency evidence is attached.</p>
                    )}
                  </div>
                </div>
                <div className="bg-panel border border-panel-border rounded-lg p-4">
                  <h3 className="text-xs font-bold text-muted-foreground uppercase mb-3">Family Order</h3>
                  <div className="space-y-2 text-xs">
                    <div className="text-muted-foreground">Family <span className="text-panel-foreground ml-1 font-mono">{familySummary?.featureFamily || activeFeature.featureFamily || '-'}</span></div>
                    <div className="text-muted-foreground">Position <span className="text-panel-foreground ml-1">{getFamilyPositionLabel(familyPosition)}</span></div>
                    <div className="text-muted-foreground">Next item <span className="text-panel-foreground ml-1 font-mono">{familyPosition?.nextItemLabel || nextFamilyItem?.featureName || '-'}</span></div>
                    <div className="text-muted-foreground">Recommended feature <span className="text-panel-foreground ml-1 font-mono">{familySummary?.nextRecommendedFeatureId || nextFamilyItem?.featureId || '-'}</span></div>
                  </div>
                </div>
              </div>

              <div className="bg-panel border border-panel-border rounded-lg p-4">
                <h3 className="text-xs font-bold text-muted-foreground uppercase mb-3">Typed Feature Relations</h3>
                <div className="space-y-2">
                  {(activeFeature.linkedFeatures || []).map((relation, index) => (
                    <div key={`${relation.feature}-${relation.type}-${relation.source}-${index}`} className="flex flex-wrap items-center gap-2 rounded border border-panel-border bg-surface-overlay px-3 py-2 text-xs">
                      <button
                        onClick={() => { onClose(); navigate(planningFeatureModalHref(relation.feature)); }}
                        className="font-mono text-indigo-300 hover:text-indigo-200"
                      >
                        {relation.feature}
                      </button>
                      <span className="uppercase px-1.5 py-0.5 rounded border border-panel-border bg-surface-muted text-foreground">{relation.type || 'related'}</span>
                      <span className="uppercase px-1.5 py-0.5 rounded border border-panel-border bg-surface-muted text-muted-foreground">{relation.source || 'unknown'}</span>
                      {typeof relation.confidence === 'number' && (
                        <span className="text-muted-foreground">{Math.round(relation.confidence * 100)}%</span>
                      )}
                      {relation.notes && <span className="text-muted-foreground">{relation.notes}</span>}
                    </div>
                  ))}
                  {(activeFeature.linkedFeatures || []).length === 0 && (
                    <p className="text-xs text-muted-foreground italic">No typed feature relations available.</p>
                  )}
                </div>
              </div>
              <div className="bg-panel border border-panel-border rounded-lg p-4">
                <h3 className="text-xs font-bold text-muted-foreground uppercase mb-3">Related Features</h3>
                <div className="flex flex-wrap gap-2">
                  {activeFeature.relatedFeatures.map(rel => (
                    <button
                      key={rel}
                      onClick={() => { onClose(); navigate(planningFeatureModalHref(rel)); }}
                      className="text-xs bg-surface-muted text-indigo-400 px-2 py-1 rounded border border-panel-border"
                    >
                      {rel}
                    </button>
                  ))}
                  {activeFeature.relatedFeatures.length === 0 && (
                    <span className="text-xs text-muted-foreground italic">No related features.</span>
                  )}
                </div>
              </div>
              <div className="bg-panel border border-panel-border rounded-lg p-4">
                <h3 className="text-xs font-bold text-muted-foreground uppercase mb-3">Lineage Signals</h3>
                <div className="space-y-2">
                  {linkedDocs
                    .filter(doc => doc.lineageFamily || doc.lineageParent || (doc.lineageChildren || []).length > 0)
                    .map(doc => (
                      <div key={`lineage-${doc.id}`} className="text-xs rounded border border-panel-border bg-surface-overlay p-2">
                        <div className="text-foreground">{doc.title}</div>
                        <div className="text-muted-foreground mt-1">Family: <span className="font-mono">{doc.lineageFamily || '-'}</span></div>
                        <div className="text-muted-foreground">Parent: <span className="font-mono">{doc.lineageParent || '-'}</span></div>
                        <div className="text-muted-foreground">Children: <span className="font-mono">{(doc.lineageChildren || []).join(', ') || '-'}</span></div>
                      </div>
                    ))}
                  {!linkedDocs.some(doc => doc.lineageFamily || doc.lineageParent || (doc.lineageChildren || []).length > 0) && (
                    <p className="text-xs text-muted-foreground italic">No lineage metadata detected.</p>
                  )}
                </div>
              </div>
            </div>
            </TabStateView>
          )}
          {/* Sessions Tab */}
          {activeTab === 'sessions' && (
            <TabStateView
              status={modalSections.sessions.status}
              error={modalSections.sessions.error?.message}
              onRetry={modalSections.sessions.retry}
              isEmpty={linkedSessions.length === 0 && modalSections.sessions.status === 'success'}
              emptyLabel="No sessions linked to this feature."
              staleLabel="Refreshing sessions…"
            >
            <div className="space-y-4">
              {linkedSessions.length === 0 && (
                <div className="text-center py-12 text-muted-foreground border border-dashed border-panel-border rounded-xl">
                  <Terminal size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No sessions linked to this feature.</p>
                  <p className="text-xs mt-1 text-muted-foreground">No high-confidence session evidence found yet.</p>
                </div>
              )}
              {linkedSessions.length > 0 && (
                <>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <FeatureMetricTile
                      label="Linked Sessions"
                      value={linkedSessions.length}
                      detail={`${primarySessionCount} primary focus sessions`}
                      icon={Terminal}
                    />
                    <FeatureMetricTile
                      label="Sub-Threads"
                      value={linkedSessions.filter(isSubthreadSession).length}
                      detail={`${secondarySessionCount} secondary linkages`}
                      icon={GitBranch}
                      accentClassName="text-warning"
                    />
                    <FeatureMetricTile
                      label="Observed Workload"
                      value={formatTokenCount(linkedSessions.reduce((sum, session) => (
                        sum + resolveTokenMetrics(session, {
                          hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, linkedSessions),
                        }).workloadTokens
                      ), 0))}
                      detail={`${linkedSessions.filter(isPrimarySession).length} primary roots`}
                      icon={BarChart3}
                      accentClassName="text-info"
                    />
                  </div>

                  <Surface tone="panel" padding="sm">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="text-xs font-bold uppercase tracking-wider text-panel-foreground">Session Evidence</div>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          Grid uses compact shared session cards; list keeps the full detailed session cards.
                        </p>
                      </div>
                      <div className="inline-flex w-fit rounded-lg border border-panel-border bg-surface-muted/70 p-1">
                        <button
                          type="button"
                          onClick={() => setSessionViewMode('grid')}
                          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${sessionViewMode === 'grid'
                            ? 'bg-panel text-panel-foreground shadow-sm'
                            : 'text-muted-foreground hover:bg-hover/70 hover:text-foreground'
                            }`}
                        >
                          <LayoutGrid size={14} />
                          Grid
                        </button>
                        <button
                          type="button"
                          onClick={() => setSessionViewMode('list')}
                          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${sessionViewMode === 'list'
                            ? 'bg-panel text-panel-foreground shadow-sm'
                            : 'text-muted-foreground hover:bg-hover/70 hover:text-foreground'
                            }`}
                        >
                          <List size={14} />
                          List
                        </button>
                      </div>
                    </div>
                  </Surface>

                  {coreSessionGroups.map(group => (
                    <FeatureModalSection
                      key={group.id}
                      title={group.label}
                      description={group.description}
                      icon={group.id === 'plan' ? Search : group.id === 'execution' ? Play : Terminal}
                      headerRight={(
                        <button
                          type="button"
                          onClick={() => toggleCoreSessionGroup(group.id)}
                          className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:text-panel-foreground"
                        >
                          {coreSessionGroupExpanded[group.id] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          {group.totalSessions}
                        </button>
                      )}
                    >
                      {coreSessionGroupExpanded[group.id] && (
                        group.roots.length === 0 ? (
                          <div className="text-xs text-muted-foreground italic">No sessions currently in this group.</div>
                        ) : sessionViewMode === 'grid' ? (
                          renderSessionGrid(group.roots)
                        ) : (
                          <div className="space-y-3">
                            <AnimatePresence initial={false}>
                              {group.roots.map(node => renderSessionTreeNode(node))}
                            </AnimatePresence>
                            {/* P4-004: partial-tree indicator when more pages are available */}
                            {modalSections.sessionPagination.hasMore && (
                              <p className="text-[11px] text-muted-foreground italic pl-1">
                                More sessions may appear in this group — load more below.
                              </p>
                            )}
                          </div>
                        )
                      )}
                    </FeatureModalSection>
                  ))}

                  <FeatureModalSection
                    title="Secondary Linkages"
                    description="Related sessions that are useful evidence but not primary planning or execution roots."
                    icon={Link2}
                    headerRight={(
                      <button
                        type="button"
                        onClick={() => setShowSecondarySessions(prev => !prev)}
                        className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:text-panel-foreground"
                      >
                        {showSecondarySessions ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        {secondarySessionCount}
                      </button>
                    )}
                  >
                    {showSecondarySessions && (
                      secondarySessionRoots.length === 0 ? (
                        <div className="text-xs text-muted-foreground italic">No secondary linked sessions.</div>
                      ) : sessionViewMode === 'grid' ? (
                        renderSessionGrid(secondarySessionRoots)
                      ) : (
                        <div className="space-y-3">
                          <AnimatePresence initial={false}>
                            {secondarySessionRoots.map(node => renderSessionTreeNode(node))}
                          </AnimatePresence>
                        </div>
                      )
                    )}
                  </FeatureModalSection>

                  {/* P4-004: Load-more pagination control */}
                  {(() => {
                    const { hasMore, isLoadingMore, serverTotal } = modalSections.sessionPagination;
                    const notYetLoaded = serverTotal > 0 ? serverTotal - linkedSessions.length : 0;
                    if (!hasMore && notYetLoaded <= 0) return null;
                    return (
                      <div className="flex flex-col items-center gap-2 pt-2 pb-1">
                        {notYetLoaded > 0 && !hasMore && (
                          <p className="text-[11px] text-muted-foreground">
                            {notYetLoaded} more session{notYetLoaded !== 1 ? 's' : ''} not yet loaded
                          </p>
                        )}
                        {hasMore && (
                          <button
                            type="button"
                            disabled={isLoadingMore}
                            onClick={() => { void modalSections.loadMoreSessions(); }}
                            className="inline-flex items-center gap-2 rounded-lg border border-panel-border bg-surface-muted px-4 py-2 text-xs font-semibold text-muted-foreground transition-colors hover:bg-hover hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isLoadingMore ? (
                              <>
                                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                                Loading…
                              </>
                            ) : (
                              <>
                                <ChevronDown size={13} />
                                Load more sessions
                                {notYetLoaded > 0 && (
                                  <span className="rounded-full bg-panel px-1.5 py-0.5 text-[10px] font-bold text-panel-foreground">
                                    {notYetLoaded}
                                  </span>
                                )}
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    );
                  })()}
                </>
              )}
            </div>
            </TabStateView>
          )}
          {activeTab === 'test-status' && featureTestHealth && (
            <TabStateView
              status={modalSections['test-status'].status}
              error={modalSections['test-status'].error?.message}
              onRetry={modalSections['test-status'].retry}
              isEmpty={false}
              staleLabel="Refreshing test status…"
            >
            <FeatureModalTestStatus
              featureId={activeFeature.id}
              health={featureTestHealth}
              onNavigateToExecution={() => {
                onClose();
                navigate(`/execution?feature=${encodeURIComponent(activeFeature.id)}&tab=test-status`);
              }}
            />
            </TabStateView>
          )}
          {activeTab === 'history' && (
            <TabStateView
              status={modalSections.history.status}
              error={modalSections.history.error?.message}
              onRetry={modalSections.history.retry}
              isEmpty={gitHistoryData.commits.length === 0 && gitHistoryData.pullRequests.length === 0 && modalSections.history.status === 'success'}
              emptyLabel="No git history found for this feature."
              staleLabel="Refreshing git history…"
            >
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-panel border border-panel-border rounded-lg p-3">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Linked Commits</div>
                  <div className="text-xl font-semibold text-emerald-300 mt-1">{gitHistoryData.commits.length}</div>
                </div>
                <div className="bg-panel border border-panel-border rounded-lg p-3">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Linked PRs</div>
                  <div className="text-xl font-semibold text-blue-300 mt-1">{gitHistoryData.pullRequests.length}</div>
                </div>
                <div className="bg-panel border border-panel-border rounded-lg p-3">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Linked Branches</div>
                  <div className="text-xl font-semibold text-purple-300 mt-1">{gitHistoryData.branches.length}</div>
                </div>
              </div>

              {gitHistoryCommitFilter && (
                <div className="flex items-center justify-between bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
                  <div className="text-xs text-emerald-200">
                    Filtering to commit <span className="font-mono">{gitHistoryCommitFilter}</span>
                  </div>
                  <button
                    onClick={() => setGitHistoryCommitFilter('')}
                    className="text-[11px] px-2 py-1 rounded border border-emerald-400/40 text-emerald-200 hover:bg-emerald-500/20 transition-colors"
                  >
                    Clear Filter
                  </button>
                </div>
              )}

              {gitHistoryData.branches.length > 0 && (
                <div className="bg-panel border border-panel-border rounded-lg p-3">
                  <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Branches</div>
                  <div className="flex flex-wrap gap-2">
                    {gitHistoryData.branches.map(branch => (
                      <span
                        key={`branch-${branch}`}
                        className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-purple-500/30 bg-purple-500/10 text-purple-200 font-mono"
                      >
                        <GitBranch size={12} />
                        {branch}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {gitHistoryData.pullRequests.length > 0 && (
                <div className="bg-panel border border-panel-border rounded-lg p-3">
                  <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Pull Requests</div>
                  <div className="space-y-2">
                    <AnimatePresence initial={false}>
                      {animatedPullRequests.items.map((pr, index) => {
                      const label = pr.prNumber ? `#${pr.prNumber}` : (pr.prUrl || pr.prRepository || `PR ${index + 1}`);
                      const href = pr.prUrl || '';
                      const prKey = getPullRequestStableKey(pr) || `pr-row-${label}`;
                      const shouldAnimateIn = animatedPullRequests.insertedIds.has(prKey);
                      return (
                        <motion.div
                          key={prKey}
                          layout="position"
                          initial={shouldAnimateIn ? listInsertPreset.initial : false}
                          animate={shouldAnimateIn ? listInsertPreset.animate : undefined}
                          exit={listInsertPreset.exit}
                          transition={listInsertPreset.transition}
                          className="flex items-center justify-between gap-3 text-xs"
                        >
                          <div className="text-foreground flex items-center gap-2">
                            <span className="font-mono text-blue-300">{label}</span>
                            {pr.prRepository && <span className="text-muted-foreground">{pr.prRepository}</span>}
                          </div>
                          {href ? (
                            <a
                              href={href}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-blue-300 hover:text-blue-200"
                            >
                              Open <ExternalLink size={12} />
                            </a>
                          ) : (
                            <span className="text-muted-foreground">No URL</span>
                          )}
                        </motion.div>
                      );
                    })}
                    </AnimatePresence>
                  </div>
                </div>
              )}

              {filteredGitCommits.length === 0 && (
                <div className="text-center py-12 text-muted-foreground border border-dashed border-panel-border rounded-xl">
                  <GitCommit size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No linked Git commits available yet.</p>
                  <p className="text-xs mt-1 text-muted-foreground">Commit correlations are derived from session evidence and forensics metadata.</p>
                </div>
              )}

              {filteredGitCommits.length > 0 && (
                <div className="space-y-2">
                  <AnimatePresence initial={false}>
                    {animatedGitCommits.items.map(commit => {
                      const shouldAnimateIn = animatedGitCommits.insertedIds.has(commit.commitHash);
                      return (
                    <motion.div
                      key={commit.commitHash}
                      layout="position"
                      initial={shouldAnimateIn ? listInsertPreset.initial : false}
                      animate={shouldAnimateIn ? listInsertPreset.animate : undefined}
                      exit={listInsertPreset.exit}
                      transition={listInsertPreset.transition}
                      className="bg-panel border border-panel-border rounded-lg p-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <button
                          onClick={() => setGitHistoryCommitFilter(commit.commitHash === gitHistoryCommitFilter ? '' : commit.commitHash)}
                          className="inline-flex items-center gap-2 text-sm text-emerald-300 font-mono hover:text-emerald-200 transition-colors"
                          title="Filter to this commit"
                        >
                          <GitCommit size={14} />
                          {toShortCommitHash(commit.commitHash)}
                        </button>
                        <div className="text-xs text-muted-foreground">
                          {commit.lastSeenAt ? `Last seen ${new Date(commit.lastSeenAt).toLocaleString()}` : 'No timestamp'}
                        </div>
                      </div>

                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                        {commit.provisional && (
                          <span className="px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 uppercase">
                            Provisional
                          </span>
                        )}
                        {commit.branches.map(branch => (
                          <span key={`${commit.commitHash}-branch-${branch}`} className="px-2 py-0.5 rounded border border-purple-500/30 bg-purple-500/10 text-purple-200 font-mono">
                            {branch}
                          </span>
                        ))}
                        {commit.pullRequests.map((pr, idx) => (
                          <span key={`${commit.commitHash}-pr-${getPullRequestStableKey(pr) || idx}`} className="px-2 py-0.5 rounded border border-blue-500/30 bg-blue-500/10 text-blue-200 font-mono">
                            {pr.prNumber ? `PR #${pr.prNumber}` : 'PR'}
                          </span>
                        ))}
                        {commit.phases.map(phase => (
                          <span key={`${commit.commitHash}-phase-${phase}`} className="px-2 py-0.5 rounded border border-panel-border bg-surface-muted/90 text-foreground">
                            Phase {phase}
                          </span>
                        ))}
                        {commit.taskIds.slice(0, 6).map(taskId => (
                          <span key={`${commit.commitHash}-task-${taskId}`} className="px-2 py-0.5 rounded border border-panel-border bg-surface-muted/90 text-foreground font-mono">
                            {taskId}
                          </span>
                        ))}
                        {commit.taskIds.length > 6 && (
                          <span className="text-muted-foreground">+{commit.taskIds.length - 6} tasks</span>
                        )}
                      </div>

                      <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 text-[11px]">
                        <div className="text-muted-foreground">Sessions: <span className="text-panel-foreground">{commit.sessionIds.length}</span></div>
                        <div className="text-muted-foreground">Files: <span className="text-panel-foreground">{commit.fileCount}</span></div>
                        <div className="text-muted-foreground">+/-: <span className="text-panel-foreground">{commit.additions}/{commit.deletions}</span></div>
                        <div className="text-muted-foreground">Model IO: <span className="text-panel-foreground">{(commit.tokenInput + commit.tokenOutput).toLocaleString()}</span></div>
                        <div className="text-muted-foreground">Events: <span className="text-panel-foreground">{commit.eventCount}</span></div>
                        <div className="text-muted-foreground">Cost: <span className="text-panel-foreground">${commit.costUsd.toFixed(2)}</span></div>
                      </div>
                    </motion.div>
                  )})}
                  </AnimatePresence>
                </div>
              )}
            </div>
            </TabStateView>
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

/**
 * Lightweight linked-doc count badge driven from rollup data.
 * Shows a neutral '—' while rollup is still loading (count === null).
 */
const RollupLinkedDocsBadge = ({
  count,
  loading,
  onClick,
  compact = false,
}: {
  count: number | null;
  loading: boolean;
  onClick: () => void;
  compact?: boolean;
}) => {
  if (!loading && count === null) return null;
  if (!loading && count === 0) return null;
  return (
    <button
      type="button"
      draggable={false}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="relative inline-flex items-center gap-1 rounded-md border border-panel-border bg-panel/85 px-2 py-1 text-[10px] font-semibold text-foreground hover:border-indigo-500/60 hover:text-indigo-200 transition-colors"
      title="Open linked documents"
    >
      <FileText size={compact ? 10 : 11} />
      <span className="uppercase tracking-wide">Docs</span>
      <span className="font-mono">{loading && count === null ? '—' : count}</span>
    </button>
  );
};

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
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-md border border-panel-border bg-panel/80 text-foreground">
        <Terminal size={11} />
        {loading ? <RefreshCw size={10} className="animate-spin" /> : total}
      </span>

      <div className="pointer-events-none absolute right-0 top-[calc(100%+8px)] w-60 rounded-lg border border-panel-border bg-surface-overlay/95 shadow-2xl px-3 py-2 opacity-0 translate-y-1 group-hover/session-indicator:opacity-100 group-hover/session-indicator:translate-y-0 transition-all duration-150 z-20">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Linked Sessions</div>
        <div className="space-y-1 text-[11px] text-foreground">
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
          <div className="flex items-center justify-between">
            <span>Observed Workload</span>
            <span className="font-mono">{formatTokenCount(summary?.workloadTokens)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Cache Input</span>
            <span className="font-mono">
              {formatTokenCount(summary?.cacheInputTokens)}
              {(summary?.workloadTokens || 0) > 0 ? ` (${formatPercent((summary?.cacheInputTokens || 0) / Math.max(summary?.workloadTokens || 0, 1), 0)})` : ''}
            </span>
          </div>
          {(summary?.unresolvedSubThreads || 0) > 0 && (
            <div className="flex items-center justify-between text-amber-300">
              <span>Unresolved Sub-Threads</span>
              <span className="font-mono">{summary?.unresolvedSubThreads ?? 0}</span>
            </div>
          )}
        </div>
        {typeRows.length > 0 && (
          <div className="mt-2 pt-2 border-t border-panel-border">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Types</div>
            <div className="space-y-1">
              {typeRows.map(row => (
                <div key={row.type} className="flex items-center justify-between text-[11px] text-foreground">
                  <span className="truncate pr-2">{row.type}</span>
                  <span className="font-mono text-muted-foreground">{row.count}</span>
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
  card,
  rollup,
  rollupLoading,
  onClick,
  onOpenDocs,
  onStatusChange,
  onDragStart,
  onDragEnd,
  isDragging,
}: {
  card: FeatureCardDTO;
  rollup?: import('../services/featureSurface').FeatureRollupDTO;
  rollupLoading: boolean;
  onClick: () => void;
  onOpenDocs: () => void;
  onStatusChange: (newStatus: string) => void;
  onDragStart: (featureId: string) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}) => {
  // Convert DTO to a minimal Feature for helper functions and sub-components.
  const feature = cardDTOToFeature(card);
  const sessionSummary = rollupToSessionSummary(rollup);
  const sessionSummaryLoading = rollupLoading && !rollup;
  const featureDeferredTasks = getFeatureDeferredCount(feature);
  const featureCompletedTasks = getFeatureCompletedCount(feature);
  const featureHasDeferred = hasDeferredCaveat(feature);

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
      className={`bg-panel border border-panel-border p-4 rounded-lg shadow-sm hover:border-indigo-500/50 transition-all group cursor-pointer hover:shadow-lg hover:-translate-y-0.5 ${isDragging ? 'opacity-60 ring-1 ring-focus/30' : ''}`}
    >
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[180px]">{feature.id}</span>
        <div className="flex items-center gap-2">
          <FeatureSessionIndicator summary={sessionSummary} loading={sessionSummaryLoading} />
          <StatusDropdown status={feature.status} onStatusChange={onStatusChange} size="xs" />
          {feature.planningStatus && (
            <EffectiveStatusChips
              rawStatus={feature.planningStatus.rawStatus}
              effectiveStatus={feature.planningStatus.effectiveStatus}
              isMismatch={Boolean(feature.planningStatus.mismatchState?.isMismatch)}
              provenance={feature.planningStatus.provenance}
            />
          )}
        </div>
      </div>
      {feature.planningStatus?.mismatchState?.isMismatch && (
        <div className="mb-1.5 flex items-center gap-1.5 flex-wrap">
          <MismatchBadge
            compact
            state={feature.planningStatus.mismatchState.state}
            reason={feature.planningStatus.mismatchState.reason}
          />
          <Link
            to={planningFeatureDetailHref(feature.id)}
            onClick={e => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-[10px] text-indigo-400/70 hover:text-indigo-300"
            title="View in planning graph"
          >
            <PlanningNodeTypeIcon type="implementation_plan" size={10} className="text-indigo-400/70" />
          </Link>
        </div>
      )}

      <h4 className="font-medium text-panel-foreground mb-2 line-clamp-2 group-hover:text-indigo-400 transition-colors text-sm">{feature.name}</h4>
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

      {/* Linked doc summary — count from rollup when available */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        <RollupLinkedDocsBadge count={rollup?.linkedDocCount ?? null} loading={sessionSummaryLoading} onClick={onOpenDocs} compact />
        {card.phaseCount > 0 && (
          <span className="text-[9px] flex items-center gap-1 bg-surface-muted text-muted-foreground px-1.5 py-0.5 rounded border border-panel-border">
            {card.phaseCount} phase{card.phaseCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5 mb-3 text-[9px]">
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">{card.priority || 'priority n/a'}</span>
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">readiness n/a</span>
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">{getFeatureCoverageSummary(feature)}</span>
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">links {card.relatedFeatureCount}</span>
      </div>

      {/* Footer */}
      <div className="pt-2 border-t border-panel-border">
        <div className="flex items-center justify-between">
          <div className="flex flex-col min-w-0">
            {feature.category ? (
              <span className="text-[10px] text-muted-foreground truncate capitalize">{feature.category}</span>
            ) : <span />}
          </div>
          <span className="text-[10px] text-muted-foreground flex items-center gap-1 group-hover:text-indigo-400 transition-colors">
            Details <ChevronRight size={10} />
          </span>
        </div>
        <FeatureKanbanDateModule feature={feature} />
      </div>
    </div>
  );
};

// ── List View Card ─────────────────────────────────────────────────

const FeatureListCard = ({
  card,
  rollup,
  rollupLoading,
  onClick,
  onOpenDocs,
  onStatusChange,
}: {
  card: FeatureCardDTO;
  rollup?: import('../services/featureSurface').FeatureRollupDTO;
  rollupLoading: boolean;
  onClick: () => void;
  onOpenDocs: () => void;
  onStatusChange: (newStatus: string) => void;
}) => {
  const feature = cardDTOToFeature(card);
  const sessionSummary = rollupToSessionSummary(rollup);
  const sessionSummaryLoading = rollupLoading && !rollup;
  const featureDeferredTasks = getFeatureDeferredCount(feature);
  const featureCompletedTasks = getFeatureCompletedCount(feature);
  const featureHasDeferred = hasDeferredCaveat(feature);

  return (
    <div
      onClick={onClick}
      className="bg-panel border border-panel-border rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group shadow-sm hover:shadow-md"
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <span className="font-mono text-xs text-muted-foreground border border-panel-border px-1.5 py-0.5 rounded truncate max-w-[200px]">{card.id}</span>
            <FeatureSessionIndicator summary={sessionSummary} loading={sessionSummaryLoading} />
            <StatusDropdown status={card.status} onStatusChange={onStatusChange} size="xs" />
            {card.category && (
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-surface-muted text-muted-foreground capitalize">{card.category}</span>
            )}
          </div>
          <h3 className="font-bold text-panel-foreground text-lg group-hover:text-indigo-400 transition-colors truncate">{card.name}</h3>
        </div>
        <div className="text-right ml-4 flex-shrink-0">
          <div className="text-indigo-400 font-mono font-bold text-sm">{featureCompletedTasks}/{card.totalTasks}</div>
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
        <ProgressBar completed={featureCompletedTasks} deferred={featureDeferredTasks} total={card.totalTasks} />
      </div>

      <div className="mb-3">
        <FeatureDateStack feature={feature} />
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5 text-[10px]">
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">{card.priority || 'priority n/a'}</span>
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">readiness n/a</span>
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">{getFeatureCoverageSummary(feature)}</span>
        <span className="px-1.5 py-0.5 rounded border border-panel-border bg-panel text-foreground">links {card.relatedFeatureCount}</span>
      </div>

      <div className="pt-3 border-t border-panel-border flex items-center justify-between">
        <div className="flex gap-2">
          <RollupLinkedDocsBadge count={rollup?.linkedDocCount ?? null} loading={sessionSummaryLoading} onClick={onOpenDocs} />
        </div>
        {card.phaseCount > 0 && (
          <span className="text-xs text-muted-foreground">{card.phaseCount} phase{card.phaseCount !== 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  );
};

// ── Status Column (Board View) ─────────────────────────────────────

const StatusColumn = ({
  title,
  status,
  cards,
  rollups,
  rollupLoading,
  onCardClick,
  onCardDocsClick,
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
  cards: FeatureCardDTO[];
  rollups: Map<string, import('../services/featureSurface').FeatureRollupDTO>;
  rollupLoading: boolean;
  onCardClick: (cardId: string) => void;
  onCardDocsClick: (cardId: string) => void;
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
        <h3 className="font-semibold text-foreground text-sm uppercase tracking-wider flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${style.dot}`} />
          {title}
        </h3>
        <span className="text-muted-foreground text-xs font-mono bg-panel px-2 py-1 rounded">{cards.length}</span>
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
        className={`flex flex-col gap-3 min-h-[200px] rounded-lg bg-panel/40 p-2 border overflow-y-auto max-h-[calc(100vh-280px)] transition-colors ${isDropTarget ? 'border-indigo-500/60 bg-indigo-500/5' : 'border-panel-border/40'}`}
      >
        {cards.map(c => (
          <FeatureCard
            key={c.id}
            card={c}
            rollup={rollups.get(c.id)}
            rollupLoading={rollupLoading}
            onClick={() => onCardClick(c.id)}
            onOpenDocs={() => onCardDocsClick(c.id)}
            onStatusChange={(newStatus) => onStatusChange(c.id, newStatus)}
            onDragStart={onCardDragStart}
            onDragEnd={onCardDragEnd}
            isDragging={draggedFeatureId === c.id}
          />
        ))}
        {cards.length === 0 && (
          <div className="h-full flex items-center justify-center text-muted-foreground text-sm border-2 border-dashed border-panel-border rounded-lg p-4">
            No features
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────

// ── Sort mapping: board sort options → hook sortBy param ─────────────────────
// The board uses 'date' | 'progress' | 'tasks'; the hook/API uses string keys.
function boardSortToApiSort(sort: 'date' | 'progress' | 'tasks'): string {
  switch (sort) {
    case 'progress': return 'progress_pct';
    case 'tasks': return 'total_tasks';
    case 'date':
    default: return 'updated_at';
  }
}

export const ProjectBoard: React.FC = () => {
  const { features: apiFeatures, activeProject, updateFeatureStatus } = useData();
  // P5-005: Read the v2 flag once at mount so the hook picks a path and keeps it.
  const { runtimeStatus } = useAppRuntime();
  const v2Enabled = isFeatureSurfaceV2Enabled(runtimeStatus);
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [selectedFeature, setSelectedFeature] = useState<Feature | null>(null);
  const [selectedFeatureTab, setSelectedFeatureTab] = useState<FeatureModalTab>('overview');
  const [draggedFeatureId, setDraggedFeatureId] = useState<string | null>(null);
  const [dragOverStatus, setDragOverStatus] = useState<string | null>(null);
  // P3-005: featureSessionSummaries removed — session data now comes from
  // FeatureRollupDTO via rollupToSessionSummary() in the render path.

  // Auto-select feature from URL search params
  useEffect(() => {
    const featureId = searchParams.get('feature');
    const tabParam = (searchParams.get('tab') || '').trim().toLowerCase();
    const requestedTab = isPlanningFeatureModalTab(tabParam) ? tabParam : 'overview';
    if (featureId && apiFeatures.length > 0) {
      const featureBase = getFeatureBaseSlug(featureId);
      const feat = apiFeatures.find(f => f.id === featureId)
        || apiFeatures.find(f => getFeatureBaseSlug(f.id) === featureBase);
      if (feat) {
        setSelectedFeature(feat);
        setSelectedFeatureTab(requestedTab);
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

  // ── P3-005: Board data from useFeatureSurface (cards + rollups) ──────────────
  // Cards come from the batched list endpoint; rollups from the batched rollup
  // endpoint.  apiFeatures (from useData) is kept only for:
  //   1. Modal data path — openFeatureModalById resolves Feature from apiFeatures
  //   2. handleStatusChange status-check guard (falls back to apiFeatures.find)
  //   3. selectedFeature sync useEffect
  //   4. Category dropdown derivation (falls back before surfaceCards available)
  // The board and list render exclusively from hook.cards + hook.rollups.
  const {
    setQuery: setSurfaceQuery,
    totals: surfaceTotals,
    listState: surfaceListState,
    rollupState: surfaceRollupState,
    cards: surfaceCards,
    rollups: surfaceRollups,
  } = useFeatureSurface({
    initialQuery: {
      projectId: activeProject?.id,
      search: '',
      status: [],
      stage: [],
      tags: [],
      sortBy: 'updated_at',
      sortDirection: 'desc',
    },
    noCache: false,
    // P5-005: flag frozen at mount; hook picks v2 or legacy path once.
    featureSurfaceV2Enabled: v2Enabled,
  });

  // Derive unique categories from surfaceCards (v1 source) when available,
  // falling back to apiFeatures so the dropdown is populated even before the
  // first list response arrives.
  const categories = useMemo(() => {
    const source = surfaceCards.length > 0 ? surfaceCards : apiFeatures;
    const cats = new Set(source.map((f: { category?: string | null }) => f.category).filter(Boolean));
    return Array.from(cats).sort();
  }, [surfaceCards, apiFeatures]);

  // P3-005: filteredFeatures (apiFeatures-derived local filter) removed.
  // Filtering/sorting is now delegated to the server via setSurfaceQuery (applied
  // on sidebar Apply).  The board and list render from surfaceCards directly.

  const activeProjectId = activeProject?.id;
  const handleStatusChange = useCallback(async (featureId: string, newStatus: string) => {
    // Check current status from surfaceCards (v1 source) first; fall back to apiFeatures.
    const card = surfaceCards.find(c => c.id === featureId);
    const legacyFeature = apiFeatures.find(f => f.id === featureId);
    const currentStatus = card?.status ?? legacyFeature?.status;
    if (currentStatus === undefined || currentStatus === newStatus) return;
    await updateFeatureStatus(featureId, newStatus);
    // P4-011: publish to the cross-cache bus (invalidates planning + surface caches).
    publishFeatureWriteEvent({ projectId: activeProjectId, featureIds: [featureId], kind: 'status' });
    // Belt-and-suspenders: also call the surface helper directly for React state reset.
    invalidateFeatureSurface({ projectId: activeProjectId, featureIds: [featureId] });
  }, [surfaceCards, apiFeatures, updateFeatureStatus, activeProjectId]);

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

  const openFeatureModal = useCallback((feature: Feature, initialTab: FeatureModalTab = 'overview') => {
    setSelectedFeatureTab(initialTab);
    setSelectedFeature(feature);
  }, []);

  /** Opens the feature modal by card ID — resolves the full Feature from apiFeatures. */
  const openFeatureModalById = useCallback((featureId: string, initialTab: FeatureModalTab = 'overview') => {
    const featureBase = getFeatureBaseSlug(featureId);
    const feature = apiFeatures.find(f => f.id === featureId)
      || apiFeatures.find(f => getFeatureBaseSlug(f.id) === featureBase);
    if (feature) {
      openFeatureModal(feature, initialTab);
    }
  }, [apiFeatures, openFeatureModal]);

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

    // P3-003: Push applied filters into the server-backed hook (one request per apply).
    // Draft state above stays local; only the applied values reach the API.
    setSurfaceQuery({
      projectId: activeProject?.id,
      search: draftSearchQuery,
      // status and stage: the board's statusFilter is a board-stage string (backlog /
      // in-progress / review / done) rather than a raw API status value.  Pass it as
      // a stage filter so the backend can narrow by board stage; category maps to
      // the hook's category field.  Reset to page 1 on every filter change.
      stage: draftStatusFilter !== 'all' ? [draftStatusFilter] : [],
      status: [],
      tags: [],
      category: draftCategoryFilter !== 'all' ? draftCategoryFilter : undefined,
      sortBy: boardSortToApiSort(draftSortBy),
      sortDirection: 'desc',
      plannedFrom: draftPlannedFrom || undefined,
      plannedTo: draftPlannedTo || undefined,
      startedFrom: draftStartedFrom || undefined,
      startedTo: draftStartedTo || undefined,
      completedFrom: draftCompletedFrom || undefined,
      completedTo: draftCompletedTo || undefined,
      updatedFrom: draftUpdatedFrom || undefined,
      updatedTo: draftUpdatedTo || undefined,
      page: 1,
    });
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

    // P3-003: Reset hook query to cleared state (page 1, no filters).
    setSurfaceQuery({
      projectId: activeProject?.id,
      search: '',
      stage: [],
      status: [],
      tags: [],
      category: undefined,
      sortBy: 'updated_at',
      sortDirection: 'desc',
      plannedFrom: undefined,
      plannedTo: undefined,
      startedFrom: undefined,
      startedTo: undefined,
      completedFrom: undefined,
      completedTo: undefined,
      updatedFrom: undefined,
      updatedTo: undefined,
      page: 1,
    });
  };

  return (
    <div className="h-full flex flex-col relative">

      <SidebarFiltersPortal>
          <SidebarFiltersSection title="Filters" icon={Filter}>
            <div className="space-y-2">
              <button
                onClick={() => toggleSidebarSection('general')}
                className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border border-panel-border rounded-md px-2.5 py-2 hover:text-panel-foreground hover:border-panel-border transition-colors"
              >
                <span>General</span>
                {collapsedSidebarSections.general ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </button>
              {!collapsedSidebarSections.general && (
                <div className="pl-1 space-y-2">
                  <div className="relative">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Search features..."
                      value={draftSearchQuery}
                      onChange={e => setDraftSearchQuery(e.target.value)}
                      className="w-full bg-surface-overlay border border-panel-border rounded-lg pl-9 pr-3 py-2 text-xs text-panel-foreground focus:border-focus focus:outline-none transition-colors"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] text-muted-foreground mb-1 block">Status</label>
                    <select
                      value={draftStatusFilter}
                      onChange={e => setDraftStatusFilter(e.target.value)}
                      className="w-full bg-surface-overlay border border-panel-border rounded-lg px-3 py-2 text-xs text-panel-foreground focus:border-focus focus:outline-none"
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
                    <label className="text-[10px] text-muted-foreground mb-1 block">Category</label>
                    <select
                      value={draftCategoryFilter}
                      onChange={e => setDraftCategoryFilter(e.target.value)}
                      className="w-full bg-surface-overlay border border-panel-border rounded-lg px-3 py-2 text-xs text-panel-foreground focus:border-focus focus:outline-none"
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
                className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border border-panel-border rounded-md px-2.5 py-2 hover:text-panel-foreground hover:border-panel-border transition-colors"
              >
                <span>Date Ranges</span>
                {collapsedSidebarSections.dates ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </button>
              {!collapsedSidebarSections.dates && (
                <div className="pl-1 space-y-2">
                  <div className="rounded-lg border border-panel-border bg-panel/40 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Planned</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">From</span>
                      <input
                        type="date"
                        value={draftPlannedFrom}
                        onChange={e => setDraftPlannedFrom(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">To</span>
                      <input
                        type="date"
                        value={draftPlannedTo}
                        onChange={e => setDraftPlannedTo(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="rounded-lg border border-panel-border bg-panel/40 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Started</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">From</span>
                      <input
                        type="date"
                        value={draftStartedFrom}
                        onChange={e => setDraftStartedFrom(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">To</span>
                      <input
                        type="date"
                        value={draftStartedTo}
                        onChange={e => setDraftStartedTo(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="rounded-lg border border-panel-border bg-panel/40 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Completed</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">From</span>
                      <input
                        type="date"
                        value={draftCompletedFrom}
                        onChange={e => setDraftCompletedFrom(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">To</span>
                      <input
                        type="date"
                        value={draftCompletedTo}
                        onChange={e => setDraftCompletedTo(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="rounded-lg border border-panel-border bg-panel/40 p-2 space-y-1.5">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Updated</p>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">From</span>
                      <input
                        type="date"
                        value={draftUpdatedFrom}
                        onChange={e => setDraftUpdatedFrom(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                    <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">To</span>
                      <input
                        type="date"
                        value={draftUpdatedTo}
                        onChange={e => setDraftUpdatedTo(e.target.value)}
                        className="w-full bg-surface-overlay border border-panel-border rounded-lg px-2 py-1.5 text-[11px] text-panel-foreground focus:border-focus focus:outline-none"
                      />
                    </div>
                  </div>
                </div>
              )}

              <button
                onClick={() => toggleSidebarSection('sort')}
                className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border border-panel-border rounded-md px-2.5 py-2 hover:text-panel-foreground hover:border-panel-border transition-colors"
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
                      className={`py-1.5 px-3 text-xs rounded border text-left transition-colors ${draftSortBy === s.key ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'bg-panel border-panel-border text-muted-foreground'}`}
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
          <h2 className="text-2xl font-bold text-panel-foreground">Feature Board</h2>
          <p className="text-muted-foreground text-sm">
            {/* P3-005: authoritative count from hook totals (filteredTotal when filtered, else total) */}
            {surfaceListState === 'loading' ? (
              <span className="text-muted-foreground/60">Loading…</span>
            ) : (
              <span>{surfaceTotals.filteredTotal ?? surfaceTotals.total} features</span>
            )}
            {' '}· Synced from project plans &amp; progress files
          </p>
        </div>
        <div className="flex gap-3">
          <div className="bg-panel border border-panel-border p-1 rounded-lg flex gap-1">
            <button
              onClick={() => setViewMode('board')}
              className={`p-1.5 rounded-md transition-all ${viewMode === 'board' ? 'bg-indigo-600 text-white shadow' : 'text-muted-foreground hover:text-panel-foreground'}`}
              title="Kanban View"
            >
              <LayoutGrid size={18} />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-1.5 rounded-md transition-all ${viewMode === 'list' ? 'bg-indigo-600 text-white shadow' : 'text-muted-foreground hover:text-panel-foreground'}`}
              title="List View"
            >
              <List size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Content Area — P3-005: renders from surfaceCards + surfaceRollups */}
      <div className="flex-1 overflow-x-auto">
        {viewMode === 'board' ? (
          <div className="flex gap-6 min-w-[1200px] h-full pb-4">
            <StatusColumn
              title="Backlog"
              status="backlog"
              cards={surfaceCards.filter(c => cardDTOBoardStage(c) === 'backlog')}
              rollups={surfaceRollups}
              rollupLoading={surfaceRollupState === 'loading'}
              onCardClick={(id) => openFeatureModalById(id, 'overview')}
              onCardDocsClick={(id) => openFeatureModalById(id, 'docs')}
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
              cards={surfaceCards.filter(c => cardDTOBoardStage(c) === 'in-progress')}
              rollups={surfaceRollups}
              rollupLoading={surfaceRollupState === 'loading'}
              onCardClick={(id) => openFeatureModalById(id, 'overview')}
              onCardDocsClick={(id) => openFeatureModalById(id, 'docs')}
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
              cards={surfaceCards.filter(c => cardDTOBoardStage(c) === 'review')}
              rollups={surfaceRollups}
              rollupLoading={surfaceRollupState === 'loading'}
              onCardClick={(id) => openFeatureModalById(id, 'overview')}
              onCardDocsClick={(id) => openFeatureModalById(id, 'docs')}
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
              cards={surfaceCards.filter(c => cardDTOBoardStage(c) === 'done')}
              rollups={surfaceRollups}
              rollupLoading={surfaceRollupState === 'loading'}
              onCardClick={(id) => openFeatureModalById(id, 'overview')}
              onCardDocsClick={(id) => openFeatureModalById(id, 'docs')}
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
            {surfaceCards.map(c => (
              <FeatureListCard
                key={c.id}
                card={c}
                rollup={surfaceRollups.get(c.id)}
                rollupLoading={surfaceRollupState === 'loading'}
                onClick={() => openFeatureModalById(c.id, 'overview')}
                onOpenDocs={() => openFeatureModalById(c.id, 'docs')}
                onStatusChange={(newStatus) => handleStatusChange(c.id, newStatus)}
              />
            ))}
            {surfaceCards.length === 0 && surfaceListState !== 'loading' && (
              <div className="col-span-full py-12 text-center text-muted-foreground border border-dashed border-panel-border rounded-xl">
                No features match your filters.
              </div>
            )}
            {surfaceListState === 'loading' && surfaceCards.length === 0 && (
              <div className="col-span-full py-12 text-center text-muted-foreground border border-dashed border-panel-border rounded-xl">
                Loading features…
              </div>
            )}
          </div>
        )}
      </div>

      {/* Feature Detail Modal */}
      {selectedFeature && (
        <ProjectBoardFeatureModal
          feature={selectedFeature}
          initialTab={selectedFeatureTab}
          onClose={() => setSelectedFeature(null)}
        />
      )}
    </div>
  );
};
