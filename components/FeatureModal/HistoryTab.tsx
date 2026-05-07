/**
 * HistoryTab — forensics-owned git history tab for FeatureDetailShell.
 *
 * Domain: forensics
 * Owned tabs: history
 *
 * Responsibilities:
 *   - Renders git commits, pull requests, and branches linked to the feature
 *   - Derives gitHistoryData (commits, PRs, branches) client-side from
 *     the linkedSessions list (mirrors ProjectBoard.tsx gitHistoryData useMemo)
 *   - Owns gitHistoryCommitFilter local state for client-side commit filtering
 *   - Uses useFeatureModalForensics().history SectionHandle for load status
 *
 * Data contract:
 *   - history: SectionHandle — status/error/retry from useFeatureModalForensics
 *   - linkedSessions: FeatureSessionLink[] — full session list used for derivation
 *
 * Constraints (P4-004):
 *   - Does NOT call history.load() — that is the tab-activation effect's job
 *   - Does NOT modify useFeatureModalForensics, ProjectBoard, or TabStateView
 *   - Does NOT re-export FeatureSessionLink — import from SessionsTab
 */

import React, { useState, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { GitCommit, GitBranch, ExternalLink } from 'lucide-react';

import { TabStateView } from './TabStateView';
import { getMotionPreset, useAnimatedListDiff, useReducedMotionPreference } from '../animations';
import type { SectionHandle } from '../../services/useFeatureModalCore';
import type { FeatureSessionLink } from './SessionsTab';

// ── Types ─────────────────────────────────────────────────────────────────────

interface PullRequestRef {
  prNumber?: string;
  prUrl?: string;
  prRepository?: string;
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

// ── Constants ─────────────────────────────────────────────────────────────────

const SHORT_COMMIT_LENGTH = 7;
const WORKING_TREE_COMMIT_HASH = '__working_tree__';
const COMMIT_HASH_PATTERN = /^[0-9a-f]{7,40}$/i;

// ── Pure helpers ──────────────────────────────────────────────────────────────

const toShortCommitHash = (hash: string): string => hash.slice(0, SHORT_COMMIT_LENGTH);

const normalizePath = (value: string): string =>
  (value || '').replace(/\\/g, '/').replace(/^\.?\//, '');

const normalizeCommitHash = (value: string): string => {
  const raw = (value || '').trim().toLowerCase();
  if (!raw) return '';
  if (raw === WORKING_TREE_COMMIT_HASH) return raw;
  if (!COMMIT_HASH_PATTERN.test(raw)) return '';
  return raw;
};

const getPullRequestStableKey = (pr: PullRequestRef): string =>
  String(pr.prUrl || '').trim() ||
  `pr:${String(pr.prRepository || '').trim()}:${String(pr.prNumber || '').trim()}` ||
  `pr:${String(pr.prNumber || '').trim()}` ||
  `repo:${String(pr.prRepository || '').trim()}`;

const toEpoch = (value?: string): number => {
  if (!value) return 0;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : 0;
};

// ── gitHistoryData derivation (mirrors ProjectBoard.tsx gitHistoryData useMemo) ──

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

interface DeriveGitHistoryParams {
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
}

function deriveGitHistory(linkedSessions: FeatureSessionLink[]): {
  commits: GitCommitAggregate[];
  pullRequests: PullRequestRef[];
  branches: string[];
} {
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
  }: DeriveGitHistoryParams) => {
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
      const key = (
        String(pr.prUrl || '').trim() ||
        String(pr.prNumber || '').trim() ||
        String(pr.prRepository || '').trim()
      ).toLowerCase();
      if (key) current?.pullRequestKeys.add(key);
    });
  };

  linkedSessions.forEach(session => {
    const metadata = session.sessionMetadata;
    const metadataPrLinks = Array.isArray(metadata?.prLinks)
      ? (metadata.prLinks as PullRequestRef[])
      : [];
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

    const commitHashes = Array.from(
      new Set([
        String(session.gitCommitHash || '').trim(),
        ...(session.gitCommitHashes || []),
        ...(session.commitHashes || []),
      ]),
    )
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
    return String(a.prUrl || a.prRepository || '').localeCompare(
      String(b.prUrl || b.prRepository || ''),
    );
  });

  const commits: GitCommitAggregate[] = Array.from(commitMap.values())
    .map(commit => ({
      commitHash: commit.commitHash,
      sessionIds: Array.from(commit.sessionIds),
      branches: Array.from(commit.branches).sort((a, b) => a.localeCompare(b)),
      phases: Array.from(commit.phases).sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true }),
      ),
      taskIds: Array.from(commit.taskIds).sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true }),
      ),
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
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface HistoryTabProps {
  /** SectionHandle from useFeatureModalForensics().history */
  history: SectionHandle;
  /**
   * Full session list. Git history is derived client-side from this array —
   * the same derivation logic used in ProjectBoard.tsx's gitHistoryData useMemo.
   */
  linkedSessions: FeatureSessionLink[];
}

// ── HistoryTab ────────────────────────────────────────────────────────────────

export const HistoryTab: React.FC<HistoryTabProps> = ({ history, linkedSessions }) => {
  // ── Local filter state ────────────────────────────────────────────────────
  const [gitHistoryCommitFilter, setGitHistoryCommitFilter] = useState<string>('');

  // ── Animation hooks ────────────────────────────────────────────────────────
  const prefersReducedMotion = useReducedMotionPreference();
  const listInsertPreset = getMotionPreset('listInsertTop', prefersReducedMotion);

  // ── Derived git history ────────────────────────────────────────────────────
  const gitHistoryData = useMemo(
    () => deriveGitHistory(linkedSessions),
    [linkedSessions],
  );

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

  const isEmpty =
    gitHistoryData.commits.length === 0 &&
    gitHistoryData.pullRequests.length === 0 &&
    history.status === 'success';

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <TabStateView
      status={history.status}
      error={history.error?.message}
      onRetry={history.retry}
      isEmpty={isEmpty}
      emptyLabel="No git history found for this feature."
      staleLabel="Refreshing git history…"
    >
      <div className="space-y-3">
        {/* ── Metric summary strip ──────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-panel border border-panel-border rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Linked Commits
            </div>
            <div className="text-xl font-semibold text-emerald-300 mt-1">
              {gitHistoryData.commits.length}
            </div>
          </div>
          <div className="bg-panel border border-panel-border rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Linked PRs
            </div>
            <div className="text-xl font-semibold text-blue-300 mt-1">
              {gitHistoryData.pullRequests.length}
            </div>
          </div>
          <div className="bg-panel border border-panel-border rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Linked Branches
            </div>
            <div className="text-xl font-semibold text-purple-300 mt-1">
              {gitHistoryData.branches.length}
            </div>
          </div>
        </div>

        {/* ── Active commit filter banner ───────────────────────────────── */}
        {gitHistoryCommitFilter && (
          <div className="flex items-center justify-between bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
            <div className="text-xs text-emerald-200">
              Filtering to commit{' '}
              <span className="font-mono">{gitHistoryCommitFilter}</span>
            </div>
            <button
              type="button"
              onClick={() => setGitHistoryCommitFilter('')}
              className="text-[11px] px-2 py-1 rounded border border-emerald-400/40 text-emerald-200 hover:bg-emerald-500/20 transition-colors"
            >
              Clear Filter
            </button>
          </div>
        )}

        {/* ── Branches ─────────────────────────────────────────────────── */}
        {gitHistoryData.branches.length > 0 && (
          <div className="bg-panel border border-panel-border rounded-lg p-3">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Branches
            </div>
            <div className="flex flex-wrap gap-2">
              {gitHistoryData.branches.map(branch => (
                <span
                  key={`branch-${branch}`}
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-purple-500/30 bg-purple-500/10 text-purple-200 font-mono"
                >
                  <GitBranch size={12} aria-hidden="true" />
                  {branch}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── Pull Requests ─────────────────────────────────────────────── */}
        {gitHistoryData.pullRequests.length > 0 && (
          <div className="bg-panel border border-panel-border rounded-lg p-3">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Pull Requests
            </div>
            <div className="space-y-2">
              <AnimatePresence initial={false}>
                {animatedPullRequests.items.map((pr, index) => {
                  const label =
                    pr.prNumber
                      ? `#${pr.prNumber}`
                      : pr.prUrl || pr.prRepository || `PR ${index + 1}`;
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
                        {pr.prRepository && (
                          <span className="text-muted-foreground">{pr.prRepository}</span>
                        )}
                      </div>
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-blue-300 hover:text-blue-200"
                        >
                          Open <ExternalLink size={12} aria-hidden="true" />
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

        {/* ── Empty commits state ───────────────────────────────────────── */}
        {filteredGitCommits.length === 0 && (
          <div className="text-center py-12 text-muted-foreground border border-dashed border-panel-border rounded-xl">
            <GitCommit size={32} className="mx-auto mb-3 opacity-50" aria-hidden="true" />
            <p>No linked Git commits available yet.</p>
            <p className="text-xs mt-1 text-muted-foreground">
              Commit correlations are derived from session evidence and forensics metadata.
            </p>
          </div>
        )}

        {/* ── Commit rows ───────────────────────────────────────────────── */}
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
                        type="button"
                        onClick={() =>
                          setGitHistoryCommitFilter(
                            commit.commitHash === gitHistoryCommitFilter
                              ? ''
                              : commit.commitHash,
                          )
                        }
                        className="inline-flex items-center gap-2 text-sm text-emerald-300 font-mono hover:text-emerald-200 transition-colors"
                        title="Filter to this commit"
                      >
                        <GitCommit size={14} aria-hidden="true" />
                        {toShortCommitHash(commit.commitHash)}
                      </button>
                      <div className="text-xs text-muted-foreground">
                        {commit.lastSeenAt
                          ? `Last seen ${new Date(commit.lastSeenAt).toLocaleString()}`
                          : 'No timestamp'}
                      </div>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                      {commit.provisional && (
                        <span className="px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 uppercase">
                          Provisional
                        </span>
                      )}
                      {commit.branches.map(branch => (
                        <span
                          key={`${commit.commitHash}-branch-${branch}`}
                          className="px-2 py-0.5 rounded border border-purple-500/30 bg-purple-500/10 text-purple-200 font-mono"
                        >
                          {branch}
                        </span>
                      ))}
                      {commit.pullRequests.map((pr, idx) => (
                        <span
                          key={`${commit.commitHash}-pr-${getPullRequestStableKey(pr) || idx}`}
                          className="px-2 py-0.5 rounded border border-blue-500/30 bg-blue-500/10 text-blue-200 font-mono"
                        >
                          {pr.prNumber ? `PR #${pr.prNumber}` : 'PR'}
                        </span>
                      ))}
                      {commit.phases.map(phase => (
                        <span
                          key={`${commit.commitHash}-phase-${phase}`}
                          className="px-2 py-0.5 rounded border border-panel-border bg-surface-muted/90 text-foreground"
                        >
                          Phase {phase}
                        </span>
                      ))}
                      {commit.taskIds.slice(0, 6).map(taskId => (
                        <span
                          key={`${commit.commitHash}-task-${taskId}`}
                          className="px-2 py-0.5 rounded border border-panel-border bg-surface-muted/90 text-foreground font-mono"
                        >
                          {taskId}
                        </span>
                      ))}
                      {commit.taskIds.length > 6 && (
                        <span className="text-muted-foreground">
                          +{commit.taskIds.length - 6} tasks
                        </span>
                      )}
                    </div>

                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 text-[11px]">
                      <div className="text-muted-foreground">
                        Sessions:{' '}
                        <span className="text-panel-foreground">{commit.sessionIds.length}</span>
                      </div>
                      <div className="text-muted-foreground">
                        Files:{' '}
                        <span className="text-panel-foreground">{commit.fileCount}</span>
                      </div>
                      <div className="text-muted-foreground">
                        +/-:{' '}
                        <span className="text-panel-foreground">
                          {commit.additions}/{commit.deletions}
                        </span>
                      </div>
                      <div className="text-muted-foreground">
                        Model IO:{' '}
                        <span className="text-panel-foreground">
                          {(commit.tokenInput + commit.tokenOutput).toLocaleString()}
                        </span>
                      </div>
                      <div className="text-muted-foreground">
                        Events:{' '}
                        <span className="text-panel-foreground">{commit.eventCount}</span>
                      </div>
                      <div className="text-muted-foreground">
                        Cost:{' '}
                        <span className="text-panel-foreground">
                          ${commit.costUsd.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>
    </TabStateView>
  );
};
