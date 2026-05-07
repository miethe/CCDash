/**
 * PhasesTab — planning-owned tab component for the phases section.
 *
 * Domain: planning
 * Tab ID: 'phases'
 * Data: useFeatureModalPlanning().phases (SectionHandle)
 *
 * Renders phase accordion cards with task lists, phase status controls,
 * and session/commit linkage badges. The caller owns the SectionHandle and
 * is responsible for calling handle.load() on tab activation.
 *
 * Design decisions:
 * - All phase/task state (filters, expanded set) is local — no global state.
 * - Navigation side-effects (session deep-link, git history) are provided via
 *   callback props so this component stays independently testable.
 * - Phase-status mutation and task-status mutation are also callback props;
 *   the component does not write data directly.
 * - planningNavigate is an optional override for planning-route-aware
 *   navigation (planningRouteFeatureModalHref). Defaults to navigate.
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Circle,
  CircleDashed,
  ChevronDown,
  ChevronRight,
  GitCommit,
  Layers,
  Terminal,
} from 'lucide-react';

import { TabStateView } from './TabStateView';
import type { SectionHandle } from '../../services/useFeatureModalCore';
import type { FeaturePhase, ProjectTask } from '../../types';
import { FEATURE_STATUS_OPTIONS, getFeatureStatusStyle } from '../featureStatus';

// ── Re-used local primitives (duplicated from ProjectBoard to remain self-contained) ──

const getStatusStyle = getFeatureStatusStyle;

// ── Prop types ────────────────────────────────────────────────────────────────

export interface PhasesTabCallbacks {
  /** Navigate to the sessions inspector for a given session ID. */
  onSessionNavigate: (sessionId: string) => void;
  /** Open a commit hash in the git-history view. */
  onCommitNavigate: (commitHash: string) => void;
  /** Persist a phase status change. */
  onPhaseStatusChange: (phaseId: string, status: string) => void;
  /** Persist a task status change. */
  onTaskStatusChange: (phaseId: string, taskId: string, status: string) => void;
  /** Open a task source file for preview. */
  onTaskView: (task: ProjectTask) => void;
}

export interface PhasesTabProps {
  /** Planning-domain section handle from useFeatureModalPlanning(). */
  handle: SectionHandle;
  /**
   * The feature's phases array. Derived by the caller from the legacy
   * fullFeature path during P4; migrated to FeatureModalSectionDTO items in P5.
   */
  phases: FeaturePhase[];
  /**
   * Per-phase session link map. Key: phase label string (phase.phase).
   * Provided by caller — this component does not fetch links.
   */
  phaseSessionLinks?: Map<string, Array<{ sessionId: string }>>;
  /**
   * Per-phase commit link map. Key: phase label string (phase.phase).
   */
  phaseCommitLinks?: Map<string, Array<{ commitHash: string }>>;
  /**
   * Per-task session link map. Key: task.id string.
   */
  taskSessionLinks?: Map<string, Array<{ sessionId: string; isSubthread?: boolean; source?: string }>>;
  /**
   * Per-task commit hash map. Key: task.id string.
   */
  taskCommitLinks?: Map<string, Array<{ commitHash: string }>>;
  /** Navigation and mutation callbacks. */
  callbacks: PhasesTabCallbacks;
}

// ── Internal helpers ──────────────────────────────────────────────────────────

const toShortHash = (hash: string): string => hash.slice(0, 7);

function dedupeTasks(tasks: ProjectTask[]): ProjectTask[] {
  const seen = new Map<string, ProjectTask>();
  tasks.forEach((task) => {
    const key = task.id;
    if (!key) return;
    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, task);
      return;
    }
    // Prefer the one with an updatedAt, then take the incoming if newer.
    const existingTs = existing.updatedAt ? Date.parse(existing.updatedAt) : 0;
    const incomingTs = task.updatedAt ? Date.parse(task.updatedAt) : 0;
    if (incomingTs > existingTs) {
      seen.set(key, { ...existing, ...task, title: task.title || existing.title });
    }
  });
  return Array.from(seen.values());
}

function getPhaseCompletedCount(phase: FeaturePhase): number {
  const completed = Math.max(phase.completedTasks || 0, 0);
  const deferred = Math.max(phase.deferredTasks || 0, 0);
  return Math.max(completed, deferred);
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface ProgressBarProps {
  completed: number;
  deferred: number;
  total: number;
}

const ProgressBar: React.FC<ProgressBarProps> = ({ completed, deferred, total }) => {
  const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const defPct = total > 0 ? Math.min(100, Math.round((deferred / total) * 100)) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
        <div
          className="flex h-full"
          style={{ width: `${pct}%` }}
        >
          {defPct > 0 && (
            <div
              className="h-full bg-amber-400/70"
              style={{ width: `${total > 0 ? (defPct / pct) * 100 : 0}%` }}
            />
          )}
          <div className="h-full flex-1 bg-emerald-500" />
        </div>
      </div>
      <span className="min-w-[2.5rem] text-right font-mono text-[10px] text-muted-foreground">
        {completed}/{total}
      </span>
    </div>
  );
};

interface StatusDropdownProps {
  status: string;
  size?: 'xs' | 'sm';
  onStatusChange: (status: string) => void;
}

const StatusDropdown: React.FC<StatusDropdownProps> = ({ status, size = 'xs', onStatusChange }) => {
  const style = getStatusStyle(status);
  const cls = size === 'xs' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs';
  return (
    <select
      value={status}
      onChange={(e) => onStatusChange(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      className={`${cls} shrink-0 cursor-pointer rounded border border-panel-border bg-surface-overlay font-semibold transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-info/60 ${style.color}`}
      aria-label={`Phase status: ${style.label}`}
    >
      {FEATURE_STATUS_OPTIONS.map((s) => (
        <option key={s} value={s}>
          {getStatusStyle(s).label}
        </option>
      ))}
    </select>
  );
};

// ── Phase card ────────────────────────────────────────────────────────────────

interface PhaseCardProps {
  phase: FeaturePhase;
  isExpanded: boolean;
  taskStatusFilter: string;
  sessionLinks: Array<{ sessionId: string }>;
  commitLinks: Array<{ commitHash: string }>;
  taskSessionLinks: Map<string, Array<{ sessionId: string; isSubthread?: boolean; source?: string }>>;
  taskCommitLinks: Map<string, Array<{ commitHash: string }>>;
  onToggle: (key: string) => void;
  callbacks: PhasesTabCallbacks;
}

const PhaseCard: React.FC<PhaseCardProps> = ({
  phase,
  isExpanded,
  taskStatusFilter,
  sessionLinks,
  commitLinks,
  taskSessionLinks,
  taskCommitLinks,
  onToggle,
  callbacks,
}) => {
  const phaseKey = phase.id || phase.phase;
  const phaseStatus = getStatusStyle(phase.status);
  const tasks = dedupeTasks(phase.tasks || []);
  const doneTasks = tasks.filter((t) => t.status === 'done').length;
  const deferredTasks = tasks.filter((t) => t.status === 'deferred').length;
  const completed =
    tasks.length > 0 ? doneTasks + deferredTasks : getPhaseCompletedCount(phase);
  const total =
    tasks.length > 0 ? Math.max(phase.totalTasks || 0, tasks.length) : phase.totalTasks;

  const visibleTasks =
    taskStatusFilter === 'all'
      ? tasks
      : tasks.filter((t) => t.status === taskStatusFilter);

  return (
    <div className="overflow-hidden rounded-lg border border-panel-border bg-panel">
      {/* Phase header row */}
      <div className="flex items-start gap-3 p-4 transition-colors hover:bg-surface-muted/60">
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => onToggle(phaseKey)}
            className="flex w-full items-center gap-3 text-left"
            aria-expanded={isExpanded}
            aria-controls={`phase-tasks-${phaseKey}`}
          >
            {isExpanded ? (
              <ChevronDown size={16} className="shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight size={16} className="shrink-0 text-muted-foreground" />
            )}
            <div className={`h-2 w-2 shrink-0 rounded-full ${phaseStatus.dot}`} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-panel-foreground">
                  Phase {phase.phase}
                </span>
                {phase.title && (
                  <span className="truncate text-sm text-muted-foreground">
                    — {phase.title}
                  </span>
                )}
                {deferredTasks > 0 && (
                  <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] uppercase text-amber-300">
                    Deferred
                  </span>
                )}
              </div>
              <div className="mt-1.5">
                <ProgressBar completed={completed} deferred={deferredTasks} total={total} />
              </div>
            </div>
          </button>

          {/* Session badges */}
          {sessionLinks.length > 0 && (
            <div className="ml-7 mt-2 flex flex-wrap items-center gap-1">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Sessions
              </span>
              {sessionLinks.slice(0, 3).map((link) => (
                <button
                  key={`phase-${phaseKey}-session-${link.sessionId}`}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    callbacks.onSessionNavigate(link.sessionId);
                  }}
                  className="rounded border border-indigo-500/30 bg-indigo-500/10 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300 transition-colors hover:bg-indigo-500/20"
                  title="Go to linked session"
                >
                  {link.sessionId}
                </button>
              ))}
              {sessionLinks.length > 3 && (
                <span className="text-[10px] text-muted-foreground">
                  +{sessionLinks.length - 3} more
                </span>
              )}
            </div>
          )}

          {/* Commit badges */}
          {commitLinks.length > 0 && (
            <div className="ml-7 mt-2 flex flex-wrap items-center gap-1">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Commits
              </span>
              {commitLinks.slice(0, 5).map((ref) => (
                <button
                  key={`phase-${phaseKey}-commit-${ref.commitHash}`}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    callbacks.onCommitNavigate(ref.commitHash);
                  }}
                  className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] text-emerald-300 transition-colors hover:bg-emerald-500/20"
                  title={`Open ${ref.commitHash} in Git history`}
                >
                  {toShortHash(ref.commitHash)}
                </button>
              ))}
              {commitLinks.length > 5 && (
                <span className="text-[10px] text-muted-foreground">
                  +{commitLinks.length - 5} more
                </span>
              )}
            </div>
          )}
        </div>

        <StatusDropdown
          status={phase.status}
          onStatusChange={(s) => callbacks.onPhaseStatusChange(phase.phase, s)}
          size="xs"
        />
      </div>

      {/* Expanded task list */}
      {isExpanded && (
        <div
          id={`phase-tasks-${phaseKey}`}
          className="border-t border-panel-border bg-surface-overlay/60 px-4 py-3"
        >
          {visibleTasks.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">
              No task details match the current task filter.
            </p>
          ) : (
            <ul className="space-y-1.5" role="list">
              {visibleTasks.map((task) => {
                const normalizedStatus = (task.status || '').toLowerCase();
                const taskDone = normalizedStatus === 'done';
                const taskDeferred = normalizedStatus === 'deferred';
                const nextStatus = taskDone ? 'deferred' : taskDeferred ? 'backlog' : 'done';
                const markTitle = taskDone
                  ? 'Mark deferred'
                  : taskDeferred
                    ? 'Mark backlog'
                    : 'Mark done';
                const textClass = taskDone
                  ? 'text-muted-foreground line-through'
                  : taskDeferred
                    ? 'italic text-amber-300/90'
                    : 'text-foreground';

                const taskSessions = taskSessionLinks.get(String(task.id || '').trim()) || [];
                const taskCommits = taskCommitLinks.get(String(task.id || '').trim()) || [];
                const commitHashes = Array.from(
                  new Set(
                    [
                      task.commitHash ? task.commitHash.slice(0, 40) : '',
                      ...taskCommits.map((c) => c.commitHash),
                    ].filter(Boolean),
                  ),
                );

                return (
                  <li
                    key={`${task.id}-${task.sourceFile || ''}`}
                    className="flex items-center gap-3 rounded px-2 py-1.5 transition-colors hover:bg-panel"
                  >
                    {/* Status toggle */}
                    <button
                      type="button"
                      onClick={() =>
                        callbacks.onTaskStatusChange(
                          phase.phase,
                          task.id,
                          nextStatus as ProjectTask['status'],
                        )
                      }
                      className="shrink-0 transition-transform hover:scale-110"
                      title={markTitle}
                      aria-label={markTitle}
                    >
                      {taskDone ? (
                        <CheckCircle2 size={14} className="text-emerald-500" />
                      ) : taskDeferred ? (
                        <CircleDashed size={14} className="text-amber-400" />
                      ) : (
                        <Circle
                          size={14}
                          className="text-muted-foreground hover:text-indigo-400"
                        />
                      )}
                    </button>

                    {/* Task ID */}
                    <button
                      type="button"
                      onClick={() => callbacks.onTaskView(task)}
                      className="w-16 shrink-0 text-left font-mono text-[10px] text-muted-foreground transition-colors hover:text-indigo-400"
                      title="View source file"
                    >
                      {task.id}
                    </button>

                    {/* Task title */}
                    <button
                      type="button"
                      onClick={() => callbacks.onTaskView(task)}
                      className={`flex-1 truncate text-left text-sm transition-colors hover:text-indigo-400 ${textClass}`}
                      title="View source file"
                    >
                      {task.title}
                    </button>

                    {/* Commit pills */}
                    {commitHashes.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1">
                        {commitHashes.slice(0, 3).map((hash) => (
                          <button
                            key={`${task.id}-commit-${hash}`}
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              callbacks.onCommitNavigate(hash);
                            }}
                            className="flex shrink-0 items-center gap-1 rounded border border-emerald-500/30 bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-emerald-300 transition-colors hover:bg-emerald-500/20"
                            title={`Open ${hash} in Git history`}
                          >
                            <GitCommit size={10} aria-hidden="true" />
                            {toShortHash(hash)}
                          </button>
                        ))}
                        {commitHashes.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">
                            +{commitHashes.length - 3} more
                          </span>
                        )}
                      </div>
                    )}

                    {/* Session pills */}
                    {taskSessions.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1">
                        {taskSessions.slice(0, 3).map((link) => (
                          <button
                            key={`${task.id}-session-${link.sessionId}-${link.source ?? ''}`}
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              callbacks.onSessionNavigate(link.sessionId);
                            }}
                            className={`flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] transition-colors ${
                              link.isSubthread
                                ? 'border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
                                : 'border-indigo-500/30 bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20'
                            }`}
                            title={
                              link.isSubthread
                                ? 'Go to linked sub-thread session'
                                : 'Go to linked session'
                            }
                          >
                            <Terminal size={10} aria-hidden="true" />
                            {link.sessionId}
                          </button>
                        ))}
                        {taskSessions.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">
                            +{taskSessions.length - 3} more
                          </span>
                        )}
                      </div>
                    )}

                    {/* Owner */}
                    {task.owner && (
                      <span className="max-w-[100px] shrink-0 truncate text-[10px] text-muted-foreground">
                        {task.owner}
                      </span>
                    )}

                    <StatusDropdown
                      status={task.status}
                      onStatusChange={(s) =>
                        callbacks.onTaskStatusChange(
                          phase.phase,
                          task.id,
                          s as ProjectTask['status'],
                        )
                      }
                      size="xs"
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * PhasesTab — planning-owned tab content for the 'phases' ModalTabId.
 *
 * Accepts the SectionHandle from useFeatureModalPlanning().phases and the
 * phases array derived from the legacy fullFeature path (P4 bridge). The
 * FeatureDetailShell wraps this in TabStateView via its renderTabContent prop;
 * PhasesTab wraps with its own inner TabStateView for isEmpty/filter states.
 */
export const PhasesTab: React.FC<PhasesTabProps> = ({
  handle,
  phases,
  phaseSessionLinks = new Map(),
  phaseCommitLinks = new Map(),
  taskSessionLinks = new Map(),
  taskCommitLinks = new Map(),
  callbacks,
}) => {
  const [phaseStatusFilter, setPhaseStatusFilter] = useState('all');
  const [taskStatusFilter, setTaskStatusFilter] = useState('all');
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());

  const togglePhase = useCallback((key: string) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const filteredPhases = useMemo(() => {
    if (phaseStatusFilter === 'all' && taskStatusFilter === 'all') return phases;
    return phases.filter((phase) => {
      if (phaseStatusFilter !== 'all' && phase.status !== phaseStatusFilter) return false;
      if (taskStatusFilter === 'all') return true;
      return (phase.tasks || []).some((t) => t.status === taskStatusFilter);
    });
  }, [phases, phaseStatusFilter, taskStatusFilter]);

  const isEmpty = phases.length === 0 && handle.status === 'success';

  return (
    <TabStateView
      status={handle.status}
      error={handle.error?.message ?? null}
      onRetry={handle.retry}
      isEmpty={isEmpty}
      emptyLabel="No phases tracked for this feature."
      staleLabel="Refreshing phases…"
    >
      <div className="space-y-3">
        {/* Filters */}
        {phases.length > 0 && (
          <div className="grid grid-cols-1 gap-2 rounded-lg border border-panel-border bg-panel/70 p-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="phases-tab-phase-filter"
                className="mb-1 block text-[10px] uppercase text-muted-foreground"
              >
                Phase Status
              </label>
              <select
                id="phases-tab-phase-filter"
                value={phaseStatusFilter}
                onChange={(e) => setPhaseStatusFilter(e.target.value)}
                className="w-full rounded border border-panel-border bg-surface-overlay px-2 py-1 text-xs text-panel-foreground focus:border-focus focus:outline-none"
              >
                <option value="all">All</option>
                {FEATURE_STATUS_OPTIONS.map((s) => (
                  <option key={`phase-filter-${s}`} value={s}>
                    {getStatusStyle(s).label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="phases-tab-task-filter"
                className="mb-1 block text-[10px] uppercase text-muted-foreground"
              >
                Task Status
              </label>
              <select
                id="phases-tab-task-filter"
                value={taskStatusFilter}
                onChange={(e) => setTaskStatusFilter(e.target.value)}
                className="w-full rounded border border-panel-border bg-surface-overlay px-2 py-1 text-xs text-panel-foreground focus:border-focus focus:outline-none"
              >
                <option value="all">All</option>
                {FEATURE_STATUS_OPTIONS.map((s) => (
                  <option key={`task-filter-${s}`} value={s}>
                    {getStatusStyle(s).label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Empty filter result */}
        {filteredPhases.length === 0 && phases.length > 0 && (
          <div className="rounded-xl border border-dashed border-panel-border py-12 text-center text-muted-foreground">
            <Layers size={32} className="mx-auto mb-3 opacity-50" aria-hidden="true" />
            <p>No phases match your filters.</p>
          </div>
        )}

        {/* Phase cards */}
        {filteredPhases.map((phase) => (
          <PhaseCard
            key={phase.id || phase.phase}
            phase={phase}
            isExpanded={expandedPhases.has(phase.id || phase.phase)}
            taskStatusFilter={taskStatusFilter}
            sessionLinks={phaseSessionLinks.get(String(phase.phase || '').trim()) || []}
            commitLinks={phaseCommitLinks.get(String(phase.phase || '').trim()) || []}
            taskSessionLinks={taskSessionLinks}
            taskCommitLinks={taskCommitLinks}
            onToggle={togglePhase}
            callbacks={callbacks}
          />
        ))}
      </div>
    </TabStateView>
  );
};

export default PhasesTab;
