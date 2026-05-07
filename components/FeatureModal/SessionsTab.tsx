/**
 * SessionsTab — forensics-owned sessions tab for FeatureDetailShell.
 *
 * Domain: forensics
 * Owned tabs: sessions
 *
 * Responsibilities:
 *   - Renders linked session cards in list or grid view
 *   - Owns local UI state: sessionViewMode, showSecondarySessions,
 *     coreSessionGroupExpanded, expandedSubthreadsBySessionId
 *   - Preserves SessionPaginationState accumulator behavior
 *   - Renders "Load more sessions" cursor-based pagination control
 *   - Preserves primary/subthread grouping (plan, execution, other)
 *   - Activates load only after the tab becomes active (caller calls
 *     sessions.load() on tab activation; this component never calls it)
 *
 * Data contract:
 *   - sessions: SectionHandle — status/error/retry from useFeatureModalForensics
 *   - sessionPagination: SessionPaginationState — accumulated page state
 *   - loadMoreSessions: () => Promise<void> — appends next page
 *   - linkedSessions: FeatureSessionLink[] — full session list sorted by caller
 *
 * Constraints (P4-004):
 *   - Does NOT call sessions.load() — that is the tab-activation effect's job
 *   - Does NOT modify useFeatureModalForensics, ProjectBoard, or TabStateView
 */

import React, { useState, useMemo, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Terminal,
  GitBranch,
  GitCommit,
  BarChart3,
  LayoutGrid,
  List,
  Link2,
  Search,
  Play,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

import { Surface } from '../ui/surface';
import { TabStateView } from './TabStateView';
import { SessionCard, type SessionCardDetailSection, deriveSessionCardTitle } from '../SessionCard';
import { getMotionPreset, useAnimatedListDiff, useReducedMotionPreference } from '../animations';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../../lib/tokenMetrics';
import { resolveDisplayCost } from '../../lib/sessionSemantics';
import type { SectionHandle, SessionPaginationState } from '../../services/useFeatureModalCore';

// ── Local type aliases (mirrors ProjectBoard.tsx) ─────────────────────────────

export interface FeatureSessionLink {
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
  modelsUsed?: Array<{
    raw: string;
    modelDisplayName?: string;
    modelProvider?: string;
    modelFamily?: string;
    modelVersion?: string;
  }>;
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

interface FeatureSessionTreeNode {
  session: FeatureSessionLink;
  children: FeatureSessionTreeNode[];
}

type CoreSessionGroupId = 'plan' | 'execution' | 'other';
type SessionViewMode = 'list' | 'grid';

interface CoreSessionGroupDefinition {
  id: CoreSessionGroupId;
  label: string;
  description: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SHORT_COMMIT_LENGTH = 7;
const WORKING_TREE_COMMIT_HASH = '__working_tree__';
const COMMIT_HASH_PATTERN = /^[0-9a-f]{7,40}$/i;

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

const DEFAULT_CORE_SESSION_GROUP_EXPANDED: Record<CoreSessionGroupId, boolean> = {
  plan: true,
  execution: true,
  other: false,
};

// ── Pure helpers (mirrors ProjectBoard.tsx module-scope helpers) ───────────────

const toShortCommitHash = (hash: string): string => hash.slice(0, SHORT_COMMIT_LENGTH);

const normalizeCommitHash = (value: string): string => {
  const raw = (value || '').trim().toLowerCase();
  if (!raw) return '';
  if (raw === WORKING_TREE_COMMIT_HASH) return raw;
  if (!COMMIT_HASH_PATTERN.test(raw)) return '';
  return raw;
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

const sessionHasLinkedSubthreads = (
  sessionId: string,
  sessions: FeatureSessionLink[],
): boolean =>
  sessions.some(
    candidate =>
      candidate.sessionId !== sessionId &&
      isSubthreadSession(candidate) &&
      (candidate.parentSessionId === sessionId || candidate.rootSessionId === sessionId),
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
  (session.relatedTasks || []).forEach(task => {
    const parsed = parsePhaseNumber(String(task.phase || task.phaseId || ''), true);
    if (parsed !== null) candidates.push(parsed);
  });
  [session.title || '', ...session.commands].forEach(value => {
    const parsed = parsePhaseNumber(value, false);
    if (parsed !== null) candidates.push(parsed);
  });
  return Array.from(new Set(candidates)).sort((a, b) => a - b);
};

const sessionStartedAtValue = (session: FeatureSessionLink): number =>
  Date.parse(session.startedAt || '') || 0;

const compareSessionsByConfidenceAndTime = (
  a: FeatureSessionLink,
  b: FeatureSessionLink,
): number => {
  if (b.confidence !== a.confidence) return b.confidence - a.confidence;
  return sessionStartedAtValue(b) - sessionStartedAtValue(a);
};

const getSessionPrimaryPhaseNumber = (session: FeatureSessionLink): number | null => {
  const nums = getSessionPhaseNumbers(session);
  return nums.length > 0 ? nums[0] : null;
};

const isPlanningSession = (session: FeatureSessionLink): boolean => {
  const wf = (session.workflowType || session.sessionType || '').toLowerCase();
  const titleLower = (session.title || '').toLowerCase();
  if (wf === 'planning' || wf === 'plan') return true;
  if (titleLower.includes('plan') || titleLower.includes('spike') || titleLower.includes('prd')) return true;
  const relatedCommand = session.sessionMetadata?.relatedCommand || '';
  if (relatedCommand.toLowerCase().includes('plan')) return true;
  return false;
};

const isExecutionSession = (session: FeatureSessionLink): boolean => {
  const wf = (session.workflowType || session.sessionType || '').toLowerCase();
  if (wf === 'execution' || wf === 'execute' || wf === 'implement' || wf === 'dev') return true;
  const phaseNum = getSessionPrimaryPhaseNumber(session);
  if (phaseNum !== null) return true;
  const titleLower = (session.title || '').toLowerCase();
  if (titleLower.includes('phase') || titleLower.includes('implement')) return true;
  return false;
};

const getCoreSessionGroupId = (session: FeatureSessionLink): CoreSessionGroupId => {
  if (isPlanningSession(session)) return 'plan';
  if (isExecutionSession(session)) return 'execution';
  return 'other';
};

const compareSessionsForGroup = (
  groupId: CoreSessionGroupId,
  a: FeatureSessionLink,
  b: FeatureSessionLink,
): number => {
  if (groupId === 'execution') {
    const aPhase = getSessionPrimaryPhaseNumber(a) ?? Infinity;
    const bPhase = getSessionPrimaryPhaseNumber(b) ?? Infinity;
    if (aPhase !== bPhase) return aPhase - bPhase;
  }
  return compareSessionsByConfidenceAndTime(a, b);
};

const sortThreadNodes = (
  nodes: FeatureSessionTreeNode[],
  comparator: (a: FeatureSessionLink, b: FeatureSessionLink) => number,
): FeatureSessionTreeNode[] =>
  [...nodes]
    .sort((a, b) => comparator(a.session, b.session))
    .map(node => ({
      ...node,
      children: sortThreadNodes(node.children, compareSessionsByConfidenceAndTime),
    }));

const countThreadNodes = (nodes: FeatureSessionTreeNode[]): number =>
  nodes.reduce((sum, node) => sum + 1 + countThreadNodes(node.children), 0);

const buildSessionThreadForest = (sessions: FeatureSessionLink[]): FeatureSessionTreeNode[] => {
  const nodes = new Map<string, FeatureSessionTreeNode>();
  for (const session of sessions) {
    const id = String(session.sessionId || '').trim();
    if (!id) continue;
    if (!nodes.has(id)) {
      nodes.set(id, { session, children: [] });
    } else {
      nodes.get(id)!.session = session;
    }
  }

  const roots: FeatureSessionTreeNode[] = [];
  for (const [, node] of nodes) {
    const parentId = String(node.session.parentSessionId || '').trim();
    if (!parentId || !nodes.has(parentId)) {
      roots.push(node);
    } else {
      nodes.get(parentId)!.children.push(node);
    }
  }
  return roots;
};

const formatSessionReason = (raw: string): string => {
  if (!raw) return '';
  return raw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

// ── FeatureMetricTile (local, identical rendering to ProjectBoard) ─────────────

interface MetricTileProps {
  label: string;
  value: React.ReactNode;
  detail?: string;
  icon?: React.ElementType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  accentClassName?: string;
}

const MetricTile: React.FC<MetricTileProps> = ({ label, value, detail, icon: Icon, accentClassName }) => (
  <Surface tone="elevated" padding="sm" className="min-h-[104px] overflow-hidden">
    <div className="mb-1.5 flex items-center gap-1.5">
      {Icon && <Icon size={13} aria-hidden="true" />}
      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</span>
    </div>
    <div className={`text-2xl font-bold tabular-nums leading-none ${accentClassName ?? 'text-panel-foreground'}`}>
      {value}
    </div>
    {detail && <div className="mt-1.5 text-[11px] text-muted-foreground">{detail}</div>}
  </Surface>
);

// ── SectionPanel (local equivalent of FeatureModalSection) ────────────────────

interface SectionPanelProps {
  title: string;
  description?: string;
  icon?: React.ElementType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  headerRight?: React.ReactNode;
  children?: React.ReactNode;
}

const SectionPanel: React.FC<SectionPanelProps> = ({
  title,
  description,
  icon: Icon,
  headerRight,
  children,
}) => (
  <Surface tone="panel" padding="md">
    <div className="mb-3 flex items-start justify-between gap-2">
      <div className="flex items-center gap-2">
        {Icon && <Icon size={14} aria-hidden="true" />}
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-panel-foreground">{title}</div>
          {description && (
            <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      {headerRight}
    </div>
    {children}
  </Surface>
);

// ── Props ─────────────────────────────────────────────────────────────────────

export interface SessionsTabProps {
  /** SectionHandle from useFeatureModalForensics().sessions */
  sessions: SectionHandle;
  /** Accumulated pagination state from useFeatureModalForensics().sessionPagination */
  sessionPagination: SessionPaginationState;
  /** Fetch next page — from useFeatureModalForensics().loadMoreSessions */
  loadMoreSessions: () => Promise<void>;
  /**
   * Sorted, deduplicated session list adapted by the caller
   * (ProjectBoard's linkedSessions memoization or equivalent).
   * This is the FeatureSessionLink[] the UI renders — not the raw DTO array.
   */
  linkedSessions: FeatureSessionLink[];
  /** Called when the user wants to navigate to the session detail page. */
  onNavigateToSession: (sessionId: string) => void;
}

// ── SessionsTab ───────────────────────────────────────────────────────────────

export const SessionsTab: React.FC<SessionsTabProps> = ({
  sessions,
  sessionPagination,
  loadMoreSessions,
  linkedSessions,
  onNavigateToSession,
}) => {
  // ── Local UI state ─────────────────────────────────────────────────────────
  const [sessionViewMode, setSessionViewMode] = useState<SessionViewMode>('list');
  const [showSecondarySessions, setShowSecondarySessions] = useState(false);
  const [coreSessionGroupExpanded, setCoreSessionGroupExpanded] = useState<
    Record<CoreSessionGroupId, boolean>
  >(() => ({ ...DEFAULT_CORE_SESSION_GROUP_EXPANDED }));
  const [expandedSubthreadsBySessionId, setExpandedSubthreadsBySessionId] = useState<
    Set<string>
  >(new Set());

  // ── Animation hooks ────────────────────────────────────────────────────────
  const prefersReducedMotion = useReducedMotionPreference();
  const listInsertPreset = getMotionPreset('listInsertTop', prefersReducedMotion);
  const animatedLinkedSessions = useAnimatedListDiff(linkedSessions, {
    getId: session => session.sessionId,
  });

  // ── Derived session groupings ──────────────────────────────────────────────
  const allSessionRoots = useMemo(
    () => buildSessionThreadForest(linkedSessions),
    [linkedSessions],
  );

  const primarySessionRoots = useMemo(
    () => allSessionRoots.filter(node => isPrimarySession(node.session)),
    [allSessionRoots],
  );

  const secondarySessionRoots = useMemo(
    () =>
      sortThreadNodes(
        allSessionRoots.filter(node => !isPrimarySession(node.session)),
        compareSessionsByConfidenceAndTime,
      ),
    [allSessionRoots],
  );

  const primarySessionCount = useMemo(
    () => countThreadNodes(primarySessionRoots),
    [primarySessionRoots],
  );

  const secondarySessionCount = useMemo(
    () => countThreadNodes(secondarySessionRoots),
    [secondarySessionRoots],
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
      roots: sortThreadNodes(grouped[group.id], (a, b) =>
        compareSessionsForGroup(group.id, a, b),
      ),
      totalSessions: countThreadNodes(grouped[group.id]),
    }));
  }, [primarySessionRoots]);

  // ── Callbacks ─────────────────────────────────────────────────────────────
  const toggleCoreSessionGroup = useCallback((groupId: CoreSessionGroupId) => {
    setCoreSessionGroupExpanded(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  }, []);

  const toggleSubthreads = useCallback((sessionId: string) => {
    setExpandedSubthreadsBySessionId(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }, []);

  // ── Session card renderer (list detail card) ───────────────────────────────
  const renderSessionCard = useCallback(
    (
      session: FeatureSessionLink,
      threadToggle?: {
        expanded: boolean;
        childCount: number;
        onToggle: () => void;
        label?: string;
      },
    ): React.ReactNode => {
      const linkRole = isPrimarySession(session) ? 'Primary' : 'Related';
      const threadLabel = isSubthreadSession(session) ? 'Sub-thread' : 'Main Thread';
      const workflow = (session.workflowType || '').trim() || 'Related';
      const displayTitle = deriveSessionCardTitle(
        session.sessionId,
        (session.title || '').trim(),
        session.sessionMetadata || null,
      );
      const sessionTokenMetrics = resolveTokenMetrics(session, {
        hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, linkedSessions),
      });
      const modelBadges =
        session.modelsUsed && session.modelsUsed.length > 0
          ? session.modelsUsed.map(mi => ({
              raw: mi.raw,
              displayName: mi.modelDisplayName,
              provider: mi.modelProvider,
              family: mi.modelFamily,
              version: mi.modelVersion,
            }))
          : [
              {
                raw: session.model,
                displayName: session.modelDisplayName,
                provider: session.modelProvider,
                family: session.modelFamily,
                version: session.modelVersion,
              },
            ];

      const detailSections: SessionCardDetailSection[] = [];
      const linkSignalItems = [
        session.linkStrategy ? formatSessionReason(session.linkStrategy) : '',
        ...session.reasons.map(formatSessionReason),
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
      const toolSummary = Array.isArray(session.toolSummary)
        ? session.toolSummary.filter(Boolean)
        : [];
      if (toolSummary.length > 0) {
        detailSections.push({
          id: `${session.sessionId}-tools`,
          label: 'Tools',
          items: toolSummary,
        });
      }

      const primaryCommit =
        session.gitCommitHash ||
        session.gitCommitHashes?.[0] ||
        normalizeCommitHash(session.commitHashes?.[0] ?? '');

      return (
        <SessionCard
          sessionId={session.sessionId}
          title={displayTitle}
          status={session.status}
          startedAt={session.startedAt}
          endedAt={session.endedAt}
          updatedAt={session.updatedAt}
          dates={{
            startedAt: session.startedAt
              ? { value: session.startedAt, confidence: 'high' }
              : undefined,
            completedAt: session.endedAt
              ? { value: session.endedAt, confidence: 'high' }
              : undefined,
            updatedAt: session.updatedAt
              ? { value: session.updatedAt, confidence: 'medium' }
              : undefined,
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
          onClick={() => onNavigateToSession(session.sessionId)}
          className="rounded-lg"
          infoBadges={
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
          }
          headerRight={
            <div className="flex items-center gap-4 text-right">
              <div>
                <div className="text-[9px] text-muted-foreground uppercase">Workload</div>
                <div className="text-xs font-mono text-sky-300">
                  {formatTokenCount(sessionTokenMetrics.workloadTokens)}
                </div>
              </div>
              <div>
                <div className="text-[9px] text-muted-foreground uppercase">Cost</div>
                <div className="text-xs font-mono text-emerald-400">
                  ${resolveDisplayCost(session).toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-[9px] text-muted-foreground uppercase">Duration</div>
                <div className="text-xs font-mono text-muted-foreground">
                  {Math.round((session.durationSeconds || 0) / 60)}m
                </div>
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
          }
        >
          <div className="mb-3 text-[10px] flex flex-wrap items-center gap-2">
            <span
              className={`px-1.5 py-0.5 rounded border ${
                linkRole === 'Primary'
                  ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
                  : 'border-panel-border text-muted-foreground bg-surface-muted/70'
              }`}
            >
              {linkRole}
            </span>
            <span
              className={`px-1.5 py-0.5 rounded border ${
                threadLabel === 'Sub-thread'
                  ? 'border-amber-500/40 text-amber-300 bg-amber-500/10'
                  : 'border-blue-500/30 text-blue-300 bg-blue-500/10'
              }`}
            >
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
        </SessionCard>
      );
    },
    [linkedSessions, onNavigateToSession],
  );

  // ── Compact session card renderer (grid view) ─────────────────────────────
  const renderCompactSessionCard = useCallback(
    (
      session: FeatureSessionLink,
      threadToggle?: {
        expanded: boolean;
        childCount: number;
        onToggle: () => void;
      },
    ): React.ReactNode => {
      const displayTitle = deriveSessionCardTitle(
        session.sessionId,
        (session.title || '').trim(),
        session.sessionMetadata || null,
      );
      const workflow = (session.workflowType || session.sessionType || '').trim() || 'Related';
      const threadLabel = isSubthreadSession(session) ? 'Sub-thread' : 'Main thread';
      const phaseNumbers = getSessionPhaseNumbers(session);
      const metrics = resolveTokenMetrics(session, {
        hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, linkedSessions),
      });
      const primaryCommit =
        session.gitCommitHash ||
        session.gitCommitHashes?.[0] ||
        normalizeCommitHash(session.commitHashes?.[0] ?? '');
      const modelBadges =
        session.modelsUsed && session.modelsUsed.length > 0
          ? session.modelsUsed.map(mi => ({
              raw: mi.raw,
              displayName: mi.modelDisplayName,
              provider: mi.modelProvider,
              family: mi.modelFamily,
              version: mi.modelVersion,
            }))
          : [
              {
                raw: session.model,
                displayName: session.modelDisplayName,
                provider: session.modelProvider,
                family: session.modelFamily,
                version: session.modelVersion,
              },
            ];

      return (
        <SessionCard
          sessionId={session.sessionId}
          title={displayTitle}
          status={session.status}
          startedAt={session.startedAt}
          endedAt={session.endedAt}
          updatedAt={session.updatedAt}
          dates={{
            startedAt: session.startedAt
              ? { value: session.startedAt, confidence: 'high' }
              : undefined,
            completedAt: session.endedAt
              ? { value: session.endedAt, confidence: 'high' }
              : undefined,
            updatedAt: session.updatedAt
              ? { value: session.updatedAt, confidence: 'medium' }
              : undefined,
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
          threadToggle={threadToggle ? { ...threadToggle, label: 'Sub-Threads' } : undefined}
          onClick={() => onNavigateToSession(session.sessionId)}
          className="h-full rounded-lg p-3 hover:border-info-border"
          infoBadges={
            <div className="flex flex-wrap items-center gap-1">
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                  isPrimarySession(session)
                    ? 'border-success-border bg-success/10 text-success'
                    : 'border-panel-border bg-panel text-muted-foreground'
                }`}
              >
                {isPrimarySession(session) ? 'Primary' : 'Related'}
              </span>
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                  isSubthreadSession(session)
                    ? 'border-warning-border bg-warning/10 text-warning'
                    : 'border-info-border bg-info/10 text-info'
                }`}
              >
                {threadLabel}
              </span>
              <span className="rounded border border-purple-500/30 bg-purple-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-purple-400">
                {workflow}
              </span>
            </div>
          }
          headerRight={
            <div className="text-right">
              <div className="font-mono text-xs font-semibold text-success">
                ${resolveDisplayCost(session).toFixed(2)}
              </div>
            </div>
          }
        >
          <div className="grid grid-cols-3 gap-2 border-t border-panel-border/70 pt-3 text-[11px]">
            <div>
              <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                Confidence
              </div>
              <div className="mt-1 font-mono text-panel-foreground">
                {Math.round(session.confidence * 100)}%
              </div>
            </div>
            <div>
              <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                Workload
              </div>
              <div className="mt-1 font-mono text-info">{formatTokenCount(metrics.workloadTokens)}</div>
            </div>
            <div>
              <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                Duration
              </div>
              <div className="mt-1 font-mono text-muted-foreground">
                {Math.round((session.durationSeconds || 0) / 60)}m
              </div>
            </div>
          </div>
          {(phaseNumbers.length > 0 || primaryCommit) && (
            <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
              {phaseNumbers.slice(0, 3).map(phase => (
                <span
                  key={`${session.sessionId}-phase-${phase}`}
                  className="rounded-full border border-panel-border bg-panel px-2 py-0.5 text-foreground"
                >
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
    },
    [linkedSessions, onNavigateToSession],
  );

  // ── Grid node renderer ─────────────────────────────────────────────────────
  const renderSessionGridNode = useCallback(
    (node: FeatureSessionTreeNode, depth = 0): React.ReactNode => {
      const hasChildren = node.children.length > 0;
      const isExpanded = expandedSubthreadsBySessionId.has(node.session.sessionId);
      return (
        <div key={`grid-${node.session.sessionId}`} className="space-y-3">
          {renderCompactSessionCard(
            node.session,
            hasChildren
              ? {
                  expanded: isExpanded,
                  childCount: countThreadNodes(node.children),
                  onToggle: () => toggleSubthreads(node.session.sessionId),
                }
              : undefined,
          )}
          {hasChildren && isExpanded && (
            <div
              className={`grid grid-cols-1 gap-3 ${depth > 0 ? 'pl-3' : ''} md:grid-cols-2 xl:grid-cols-3`}
            >
              {node.children.map(child => renderSessionGridNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    },
    [expandedSubthreadsBySessionId, renderCompactSessionCard, toggleSubthreads],
  );

  const renderSessionGrid = useCallback(
    (roots: FeatureSessionTreeNode[]) => (
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {roots.map(node => renderSessionGridNode(node))}
      </div>
    ),
    [renderSessionGridNode],
  );

  // ── Tree node renderer (list view) ────────────────────────────────────────
  const renderSessionTreeNode = useCallback(
    (node: FeatureSessionTreeNode, depth = 0): React.ReactNode => {
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
          {renderSessionCard(
            node.session,
            hasChildren
              ? {
                  expanded: isExpanded,
                  childCount: countThreadNodes(node.children),
                  onToggle: () => toggleSubthreads(node.session.sessionId),
                  label: 'Sub-Threads',
                }
              : undefined,
          )}
          <AnimatePresence initial={false}>
            {hasChildren && isExpanded && (
              <motion.div
                layout
                initial={
                  prefersReducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }
                }
                animate={
                  prefersReducedMotion ? { opacity: 1 } : { opacity: 1, height: 'auto' }
                }
                exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
                transition={listInsertPreset.transition}
                className={`mt-3 ${depth > 0 ? 'ml-2' : ''} pl-4 border-l border-panel-border/90 space-y-3 overflow-hidden`}
              >
                <AnimatePresence initial={false}>
                  {node.children.map(child => (
                    <motion.div
                      key={child.session.sessionId}
                      layout="position"
                      className="relative pl-3"
                    >
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
    },
    [
      animatedLinkedSessions.insertedIds,
      expandedSubthreadsBySessionId,
      listInsertPreset,
      prefersReducedMotion,
      renderSessionCard,
      toggleSubthreads,
    ],
  );

  // ── Observed workload aggregate ────────────────────────────────────────────
  const totalWorkloadTokens = useMemo(
    () =>
      linkedSessions.reduce(
        (sum, session) =>
          sum +
          resolveTokenMetrics(session, {
            hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, linkedSessions),
          }).workloadTokens,
        0,
      ),
    [linkedSessions],
  );

  // ── Load-more state ────────────────────────────────────────────────────────
  const { hasMore, isLoadingMore, serverTotal } = sessionPagination;
  const notYetLoaded = serverTotal > 0 ? serverTotal - linkedSessions.length : 0;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <TabStateView
      status={sessions.status}
      error={sessions.error?.message}
      onRetry={sessions.retry}
      isEmpty={
        linkedSessions.length === 0 && sessions.status === 'success'
      }
      emptyLabel="No sessions linked to this feature."
      staleLabel="Refreshing sessions…"
    >
      <div className="space-y-4">
        {linkedSessions.length === 0 && (
          <div className="text-center py-12 text-muted-foreground border border-dashed border-panel-border rounded-xl">
            <Terminal size={32} className="mx-auto mb-3 opacity-50" aria-hidden="true" />
            <p>No sessions linked to this feature.</p>
            <p className="text-xs mt-1 text-muted-foreground">
              No high-confidence session evidence found yet.
            </p>
          </div>
        )}

        {linkedSessions.length > 0 && (
          <>
            {/* ── Metric summary strip ──────────────────────────────────── */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <MetricTile
                label="Linked Sessions"
                value={linkedSessions.length}
                detail={`${primarySessionCount} primary focus sessions`}
                icon={Terminal}
              />
              <MetricTile
                label="Sub-Threads"
                value={linkedSessions.filter(isSubthreadSession).length}
                detail={`${secondarySessionCount} secondary linkages`}
                icon={GitBranch}
                accentClassName="text-warning"
              />
              <MetricTile
                label="Observed Workload"
                value={formatTokenCount(totalWorkloadTokens)}
                detail={`${linkedSessions.filter(isPrimarySession).length} primary roots`}
                icon={BarChart3}
                accentClassName="text-info"
              />
            </div>

            {/* ── View mode toggle ──────────────────────────────────────── */}
            <Surface tone="panel" padding="sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-xs font-bold uppercase tracking-wider text-panel-foreground">
                    Session Evidence
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Grid uses compact shared session cards; list keeps the full detailed session
                    cards.
                  </p>
                </div>
                <div className="inline-flex w-fit rounded-lg border border-panel-border bg-surface-muted/70 p-1">
                  <button
                    type="button"
                    onClick={() => setSessionViewMode('grid')}
                    className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                      sessionViewMode === 'grid'
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
                    className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                      sessionViewMode === 'list'
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

            {/* ── Core session groups (primary sessions) ────────────────── */}
            {coreSessionGroups.map(group => (
              <SectionPanel
                key={group.id}
                title={group.label}
                description={group.description}
                icon={group.id === 'plan' ? Search : group.id === 'execution' ? Play : Terminal}
                headerRight={
                  <button
                    type="button"
                    onClick={() => toggleCoreSessionGroup(group.id)}
                    className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:text-panel-foreground"
                  >
                    {coreSessionGroupExpanded[group.id] ? (
                      <ChevronDown size={12} />
                    ) : (
                      <ChevronRight size={12} />
                    )}
                    {group.totalSessions}
                  </button>
                }
              >
                {coreSessionGroupExpanded[group.id] &&
                  (group.roots.length === 0 ? (
                    <div className="text-xs text-muted-foreground italic">
                      No sessions currently in this group.
                    </div>
                  ) : sessionViewMode === 'grid' ? (
                    renderSessionGrid(group.roots)
                  ) : (
                    <div className="space-y-3">
                      <AnimatePresence initial={false}>
                        {group.roots.map(node => renderSessionTreeNode(node))}
                      </AnimatePresence>
                      {/* Partial-tree indicator when more pages are available */}
                      {hasMore && (
                        <p className="text-[11px] text-muted-foreground italic pl-1">
                          More sessions may appear in this group — load more below.
                        </p>
                      )}
                    </div>
                  ))}
              </SectionPanel>
            ))}

            {/* ── Secondary linkages ────────────────────────────────────── */}
            <SectionPanel
              title="Secondary Linkages"
              description="Related sessions that are useful evidence but not primary planning or execution roots."
              icon={Link2}
              headerRight={
                <button
                  type="button"
                  onClick={() => setShowSecondarySessions(prev => !prev)}
                  className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground hover:text-panel-foreground"
                >
                  {showSecondarySessions ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {secondarySessionCount}
                </button>
              }
            >
              {showSecondarySessions &&
                (secondarySessionRoots.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic">
                    No secondary linked sessions.
                  </div>
                ) : sessionViewMode === 'grid' ? (
                  renderSessionGrid(secondarySessionRoots)
                ) : (
                  <div className="space-y-3">
                    <AnimatePresence initial={false}>
                      {secondarySessionRoots.map(node => renderSessionTreeNode(node))}
                    </AnimatePresence>
                  </div>
                ))}
            </SectionPanel>

            {/* ── Load-more pagination control ─────────────────────────── */}
            {(hasMore || notYetLoaded > 0) && (
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
                    onClick={() => {
                      void loadMoreSessions();
                    }}
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
            )}
          </>
        )}
      </div>
    </TabStateView>
  );
};
