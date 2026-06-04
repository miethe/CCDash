import { useCallback, useRef, useState } from 'react';
import { Check, Copy, ExternalLink, GitBranch, GitPullRequest, PanelRightOpen, Play, Terminal, X } from 'lucide-react';

import type { PlanningCommandCenterItem } from '@/types';
import {
  canLaunchCommandCenterItem,
  commandCenterDisplayName,
  commandCenterDoneLabel,
  commandCenterLaunchReadiness,
  commandCenterPlanPath,
  compactPath,
} from './commandCenterUtils';
import { ArtifactChip, BtnGhost, BtnPrimary, Chip, StatusPill } from '../primitives';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { formatLastActivity } from '@/lib/planningHelpers';

interface CommandCenterFeatureCardProps {
  item: PlanningCommandCenterItem;
  commandValue: string;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

// ── Provenance entry shape ────────────────────────────────────────────────────

type ProvenanceKind = 'worktree' | 'session-git-branch' | 'commit-ref' | 'pr-ref';

interface ProvenanceEntry {
  kind: ProvenanceKind;
  label: string;
  value: string;
}

/** Build the full ordered list of provenance entries from a PlanningCommandCenterItem. */
function buildProvenanceEntries(item: PlanningCommandCenterItem): ProvenanceEntry[] {
  const entries: ProvenanceEntry[] = [];

  // 1. Worktree branch (highest provenance)
  if (item.worktree?.branch) {
    entries.push({
      kind: 'worktree',
      label: 'worktree',
      value: item.worktree.branch,
    });
  }

  // 2. Git head commit from gitState
  if (item.gitState?.head) {
    entries.push({
      kind: 'session-git-branch',
      label: 'session-git-branch',
      value: item.gitState.head,
    });
  }

  // 3. commit_refs from feature doc frontmatter
  for (const ref of item.commitRefs ?? []) {
    entries.push({ kind: 'commit-ref', label: 'commit-ref', value: ref });
  }

  // 4. pr_refs from feature doc frontmatter
  for (const ref of item.prRefs ?? []) {
    entries.push({ kind: 'pr-ref', label: 'pr-ref', value: ref });
  }

  return entries;
}

// ── Kind badge styling ────────────────────────────────────────────────────────

const KIND_STYLES: Record<ProvenanceKind, string> = {
  worktree: 'bg-[color:var(--ok-bg,#0f2d1f)] text-[color:var(--ok,#22c55e)] border-[color:var(--ok,#22c55e)]',
  'session-git-branch': 'bg-[color:var(--bg-2)] text-[color:var(--ink-2)] border-[color:var(--line-2)]',
  'commit-ref': 'bg-[color:var(--bg-2)] text-[color:var(--ink-3)] border-[color:var(--line-1)]',
  'pr-ref': 'bg-[color:var(--accent-bg,#1e1b4b)] text-[color:var(--accent,#818cf8)] border-[color:var(--accent,#818cf8)]',
};

// ── Inline provenance panel (rendered in DOM, not a Portal) ───────────────────
// This approach keeps the content in the serialised HTML tree so that tests
// using renderToStaticMarkup can assert on provenance entry content.

interface BranchProvenancePanelProps {
  entries: ProvenanceEntry[];
  onClose: () => void;
}

function BranchProvenancePanel({ entries, onClose }: BranchProvenancePanelProps) {
  return (
    <div
      role="dialog"
      aria-label="Branch and commit provenance"
      className="absolute left-0 right-0 z-30 mt-1 rounded-[var(--radius-sm)] border border-[color:var(--line-2)] bg-[color:var(--bg-0)] shadow-lg"
      data-testid="branch-provenance-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[color:var(--line-1)] px-3 py-2">
        <span className="planning-caps text-[9.5px] text-[color:var(--ink-3)]">
          branch &amp; commit provenance
        </span>
        <button
          type="button"
          aria-label="Close provenance panel"
          onClick={onClose}
          className="rounded-[var(--radius-sm)] p-0.5 text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)]"
          data-testid="branch-provenance-close-btn"
        >
          <X size={11} aria-hidden />
        </button>
      </div>

      {/* Entry list */}
      <ul className="divide-y divide-[color:var(--line-1)] px-3 py-1" data-testid="branch-provenance-list">
        {entries.map((entry, idx) => (
          <li
            key={`${entry.kind}-${idx}`}
            className="flex items-center gap-2 py-1.5"
            data-testid="branch-provenance-entry"
          >
            {/* Provenance kind badge */}
            <span
              className={`planning-mono shrink-0 rounded border px-1 py-0.5 text-[9px] leading-none ${KIND_STYLES[entry.kind]}`}
              data-testid="branch-provenance-kind-label"
            >
              {entry.label}
            </span>
            {/* Value */}
            <span
              className="planning-mono min-w-0 flex-1 truncate text-[10.5px] text-[color:var(--ink-1)]"
              title={entry.value}
              data-testid="branch-provenance-value"
            >
              {entry.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Exported for testing ─────────────────────────────────────────────────────
export { BranchProvenancePanel, buildProvenanceEntries };
export type { ProvenanceEntry };

// ── Exported component ────────────────────────────────────────────────────────

export function CommandCenterFeatureCard({
  item,
  commandValue,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: CommandCenterFeatureCardProps) {
  const featureId = item.feature.featureId;
  const planPath = commandCenterPlanPath(item);
  const doneLabel = commandCenterDoneLabel(item);
  const canLaunch = canLaunchCommandCenterItem(item);

  // Last-activity display (Issue 4)
  const lastActivityTimestamp = item.lastActivity?.timestamp;
  const lastActivityDisplay = formatLastActivity(
    typeof lastActivityTimestamp === 'string' ? lastActivityTimestamp : null,
  );

  // Local copied affordance for the command copy button
  const [cmdCopied, setCmdCopied] = useState(false);
  const handleCopyCommand = useCallback(() => {
    if (!commandValue) return;
    onCopyCommand?.(commandValue);
    setCmdCopied(true);
    window.setTimeout(() => setCmdCopied(false), 1600);
  }, [commandValue, onCopyCommand]);

  // Local copied affordance for branch copy
  const [branchCopied, setBranchCopied] = useState(false);
  const handleCopyBranch = useCallback(() => {
    const branch = item.worktree?.branch;
    if (!branch) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(branch).then(() => {
        setBranchCopied(true);
        window.setTimeout(() => setBranchCopied(false), 1600);
      });
    }
  }, [item.worktree?.branch]);

  // Provenance panel open/close state
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const provenanceEntries = buildProvenanceEntries(item);
  const hasProvenanceData = provenanceEntries.length > 0;

  // Close panel when clicking outside
  const branchRowRef = useRef<HTMLDivElement>(null);

  const handleToggleProvenance = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (hasProvenanceData) {
        setProvenanceOpen((prev) => !prev);
      }
    },
    [hasProvenanceData],
  );

  const handleCloseProvenance = useCallback(() => {
    setProvenanceOpen(false);
  }, []);

  return (
    <TooltipProvider>
      <article
        className="relative flex min-h-[270px] flex-col rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-4"
        data-testid="command-center-feature-card"
      >
        {/* Status pill — absolute top-right, smaller */}
        <StatusPill
          status={item.status.effectiveStatus || item.status.rawStatus || 'unknown'}
          className="absolute top-2 right-2"
          style={{ fontSize: '9.5px', padding: '1px 5px' }}
        />

        {/* Title + slug — full-width zone, right-padded to avoid pill overlap */}
        <div className="min-w-0 pr-20">
          <h3
            className="truncate text-[14px] font-semibold text-[color:var(--ink-0)]"
            title={commandCenterDisplayName(item)}
          >
            {commandCenterDisplayName(item)}
          </h3>
          <p
            className="planning-mono mt-0.5 truncate text-[10.5px] text-[color:var(--ink-4)]"
            title={featureId}
          >
            {item.feature.featureSlug || featureId}
          </p>
        </div>

        <p className="mt-3 line-clamp-2 min-h-[34px] text-[11.5px] leading-relaxed text-[color:var(--ink-3)]">
          {item.feature.summary || 'No feature summary recorded.'}
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <Chip className="planning-mono justify-center text-[10px]">
            P{item.phase.currentPhase ?? '-'} / {item.phase.totalPhases || '-'}
          </Chip>
          <Chip className="planning-mono justify-center text-[10px]">
            {item.storyPoints.remaining}/{item.storyPoints.total} pts
          </Chip>
          <Chip className="planning-mono justify-center text-[10px]">{commandCenterLaunchReadiness(item)}</Chip>
        </div>

        {/* Next command box — tooltip wraps the whole box; copy button inside */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className="mt-3 cursor-default space-y-2 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-3"
              data-testid="command-center-next-command-box"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="planning-caps text-[9.5px] text-[color:var(--ink-4)]">next command</div>
                <button
                  type="button"
                  aria-label="Copy command"
                  disabled={!commandValue}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCopyCommand();
                  }}
                  className="shrink-0 rounded-[var(--radius-sm)] p-0.5 text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)] disabled:pointer-events-none disabled:opacity-40"
                  data-testid="command-center-copy-command-btn"
                >
                  {cmdCopied ? (
                    <Check size={11} aria-hidden style={{ color: 'var(--ok)' }} />
                  ) : (
                    <Copy size={11} aria-hidden />
                  )}
                </button>
              </div>
              <p
                className="planning-mono line-clamp-2 text-[10.5px] leading-relaxed text-[color:var(--ink-1)]"
                title={commandValue}
              >
                {commandValue || 'No next command resolved'}
              </p>
            </div>
          </TooltipTrigger>
          {commandValue ? (
            <TooltipContent
              side="bottom"
              className="max-w-[520px] whitespace-pre-wrap break-words rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-3 py-2 text-[10.5px] text-[color:var(--ink-1)] shadow-lg planning-mono"
              data-testid="command-center-command-tooltip"
            >
              {commandValue}
            </TooltipContent>
          ) : null}
        </Tooltip>

        {/* Active-session chip row — only rendered when activeSessions is non-empty.
            Each chip links to the transcript at #/sessions/{sessionId}.
            Resilience: activeSessions absent or null → row is not rendered, no throw. */}
        {(item.activeSessions?.length ?? 0) > 0 && (() => {
          const sessions = item.activeSessions!;
          const MAX_CHIPS = 3;
          const visible = sessions.slice(0, MAX_CHIPS);
          const overflow = sessions.length - MAX_CHIPS;
          return (
            <div
              className="mt-3 flex flex-wrap items-center gap-1"
              data-testid="command-center-active-sessions"
            >
              {visible.map((session) => (
                <a
                  key={session.sessionId}
                  href={`#/sessions/${session.sessionId}`}
                  className="planning-mono flex items-center gap-1 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-1.5 py-0.5 text-[10px] text-[color:var(--ink-1)] transition-colors hover:border-[color:var(--line-2)] hover:text-[color:var(--ink-0)]"
                  title={`Active session: ${session.sessionId}`}
                  data-testid="command-center-session-chip"
                  data-session-id={session.sessionId}
                >
                  <span
                    className="inline-block h-1.5 w-1.5 shrink-0 rounded-full motion-safe:animate-pulse"
                    style={{ backgroundColor: 'var(--ok)' }}
                    aria-hidden
                  />
                  <span style={{ color: 'var(--ok)' }}>
                    {session.agentName ?? 'agent'}
                  </span>
                </a>
              ))}
              {overflow > 0 && (
                <span
                  className="planning-mono text-[10px] text-[color:var(--ink-3)]"
                  data-testid="command-center-session-overflow"
                >
                  +{overflow}
                </span>
              )}
            </div>
          );
        })()}

        {/* Branch row — clickable to open provenance panel when data is available.
            AC-WORKTREE-EMPTY: when worktree is null/absent, show "No worktree registered"
            with a visible affordance — never "branch TBD", never an error state.
            Resilience: provenance panel trigger is hidden/disabled with tooltip when
            commit_refs and pr_refs are both absent or empty AND worktree/gitState absent. */}
        <div className="relative mt-3 space-y-2" ref={branchRowRef}>
          {hasProvenanceData ? (
            /* Clickable branch row — opens provenance panel */
            <button
              type="button"
              aria-label="Show branch and commit provenance"
              aria-expanded={provenanceOpen}
              onClick={handleToggleProvenance}
              className="flex min-w-0 w-full items-center gap-2 rounded-[var(--radius-sm)] px-0.5 text-[10.5px] text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)] cursor-pointer"
              data-testid="branch-provenance-trigger"
            >
              <GitBranch size={12} className="shrink-0" aria-hidden />
              {item.worktree?.branch ? (
                <span
                  className="planning-mono min-w-0 truncate text-left text-[10.5px] text-[color:var(--ink-3)]"
                  title={item.worktree.branch}
                >
                  {branchCopied ? (
                    <span className="text-[color:var(--ok)]">copied!</span>
                  ) : (
                    item.worktree.branch
                  )}
                </span>
              ) : (
                <span className="planning-mono truncate text-left" data-testid="branch-no-worktree-label">
                  No worktree registered
                </span>
              )}
              <span className="planning-mono shrink-0">{item.gitState?.head || ''}</span>
            </button>
          ) : (
            /* Disabled trigger with tooltip — no provenance data.
              The tooltip text is also set as a title attribute so that
              renderToStaticMarkup-based tests can assert on it. */
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className="flex min-w-0 items-center gap-2 text-[10.5px] text-[color:var(--ink-4)] cursor-not-allowed"
                  data-testid="branch-provenance-trigger-disabled"
                  aria-disabled="true"
                  title="No branch or commit data linked."
                  data-tooltip="No branch or commit data linked."
                >
                  <GitBranch size={12} className="shrink-0 opacity-40" aria-hidden />
                  {item.worktree?.branch ? (
                    <span className="planning-mono min-w-0 truncate opacity-60" title={item.worktree.branch}>
                      {item.worktree.branch}
                    </span>
                  ) : (
                    <span
                      className="planning-mono truncate opacity-60"
                      data-testid="branch-no-worktree-label"
                    >
                      No worktree registered
                    </span>
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent
                side="bottom"
                className="rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-2 py-1 text-[10.5px] text-[color:var(--ink-1)]"
                data-testid="branch-provenance-empty-tooltip"
              >
                No branch or commit data linked.
              </TooltipContent>
            </Tooltip>
          )}

          {/* Copy branch button — only shown when worktree branch exists */}
          {item.worktree?.branch && (
            <button
              type="button"
              aria-label="Copy branch name"
              onClick={handleCopyBranch}
              className="absolute right-0 top-0 rounded-[var(--radius-sm)] p-0.5 text-[color:var(--ink-3)] transition-colors hover:text-[color:var(--ink-0)]"
              title="Copy branch name"
              data-testid="command-center-branch-copy-btn"
            >
              {branchCopied ? (
                <Check size={11} aria-hidden style={{ color: 'var(--ok)' }} />
              ) : (
                <Copy size={11} aria-hidden />
              )}
            </button>
          )}

          {/* Inline provenance panel — rendered in DOM when open (not a Portal).
              This ensures renderToStaticMarkup and SSR can assert on entry content. */}
          {provenanceOpen && (
            <BranchProvenancePanel
              entries={provenanceEntries}
              onClose={handleCloseProvenance}
            />
          )}

          <div
            className="planning-mono truncate text-[10.5px] text-[color:var(--ink-4)]"
            title={planPath}
          >
            {planPath ? compactPath(planPath, 74) : 'target plan TBD'}
          </div>
          {/* Issue 4: Last-activity indicator */}
          {lastActivityDisplay ? (
            <div
              className="planning-mono text-[10px] text-[color:var(--ink-4)]"
              title={lastActivityDisplay.title}
              data-testid="command-center-last-activity"
            >
              {lastActivityDisplay.label}
            </div>
          ) : null}
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {item.artifacts.slice(0, 5).map((artifact) => (
            <ArtifactChip
              key={`${artifact.docType}:${artifact.path}`}
              kind={artifact.docType}
              label={artifact.docType === 'implementation_plan' ? 'plan' : artifact.docType || 'doc'}
              active={artifact.path === planPath}
            />
          ))}
        </div>
        {doneLabel ? (
          <Chip className="planning-mono mt-3 w-fit text-[10px]">{doneLabel}</Chip>
        ) : null}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
          <BtnPrimary size="sm" disabled={!canLaunch} onClick={() => onOpenLaunch?.(featureId)}>
            <Play size={13} aria-hidden />
            launch
          </BtnPrimary>
          <BtnGhost size="sm" onClick={() => onOpenExecution?.(featureId)}>
            <Terminal size={13} aria-hidden />
            workbench
          </BtnGhost>
          <BtnGhost size="sm" disabled={!planPath} onClick={() => onOpenPlan?.(planPath)}>
            <ExternalLink size={13} aria-hidden />
            plan
          </BtnGhost>
          <BtnGhost
            size="sm"
            disabled={!item.pullRequest?.url}
            onClick={() => item.pullRequest?.url && onOpenPullRequest?.(item.pullRequest.url)}
          >
            <GitPullRequest size={13} aria-hidden />
            PR
          </BtnGhost>
          <BtnGhost size="sm" onClick={() => onOpenDetail?.(featureId)}>
            <PanelRightOpen size={13} aria-hidden />
            details
          </BtnGhost>
        </div>
      </article>
    </TooltipProvider>
  );
}
