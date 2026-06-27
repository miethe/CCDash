/**
 * MPCC-504: Work item card with project identity for the multi-project
 * consolidated command center.
 *
 * Wraps CommandCenterFeatureCard with a project identity header strip
 * (color accent + label) so the originating project is immediately clear.
 * All V1 card actions are preserved.
 *
 * Resilience-by-default: activeSessions is optional on AggregateWorkItem.
 * primarySession may be undefined (zero active sessions is a valid state).
 * Every access to primarySession uses optional chaining — the card renders
 * project identity + work-item info correctly when there are no active sessions.
 */
import type { AggregateWorkItem } from '@/types';
import { CommandCenterFeatureCard } from './CommandCenterFeatureCard';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fallbackColor(projectId: string): string {
  let hash = 0;
  for (let i = 0; i < projectId.length; i++) {
    hash = projectId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `oklch(65% 0.18 ${h})`;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface MultiProjectWorkItemCardProps {
  workItem: AggregateWorkItem;
  commandValue: string;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string, projectId: string) => void;
  onOpenExecution?: (featureId: string, projectId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string, projectId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

export function MultiProjectWorkItemCard({
  workItem,
  commandValue,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: MultiProjectWorkItemCardProps) {
  const { project, item } = workItem;
  const color = project.projectColor || fallbackColor(project.projectId);
  const label = project.projectName;

  // activeSessions is optional — may be absent or empty.  primarySession is
  // undefined when there are no active sessions; all accesses below use
  // optional chaining to avoid "Cannot read properties of undefined" throws.
  const primarySession = workItem.activeSessions?.[0];
  const sessionCount = workItem.activeSessions?.length ?? 0;

  return (
    <div
      className="rounded-[var(--radius)] overflow-hidden"
      style={{ border: '1px solid var(--line-1)' }}
      data-testid="multi-project-work-item-card"
      data-project-id={project.projectId}
    >
      {/* Project identity strip */}
      <div
        className="flex items-center gap-1.5 px-3 py-1"
        style={{
          backgroundColor: `color-mix(in oklab, ${color} 12%, var(--bg-2))`,
          borderBottom: '1px solid var(--line-1)',
        }}
      >
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden
        />
        <span
          className="planning-mono text-[10px] truncate max-w-[200px]"
          style={{ color: 'var(--ink-2)' }}
          title={label}
        >
          {label}
        </span>
        {project.projectGroup && (
          <span
            className="planning-mono text-[10px]"
            style={{ color: 'var(--ink-4)' }}
          >
            · {project.projectGroup}
          </span>
        )}

        {/* Active session indicator — only rendered when sessions are present.
            Uses optional chaining on every primarySession field access so the
            card never throws when activeSessions is absent or empty. */}
        {primarySession?.sessionId != null && (
          <span
            className="planning-mono text-[10px] ml-auto shrink-0 flex items-center gap-1"
            style={{ color: 'var(--ok)' }}
            title={
              sessionCount > 1
                ? `${sessionCount} active sessions — primary: ${primarySession.sessionId}`
                : `Active session: ${primarySession.sessionId}`
            }
            data-testid="multi-project-work-item-card-session-indicator"
            data-session-id={primarySession.sessionId}
          >
            <span
              className="inline-block h-1.5 w-1.5 shrink-0 rounded-full motion-safe:animate-pulse"
              style={{ backgroundColor: 'var(--ok)' }}
              aria-hidden
            />
            {primarySession.agentName ?? 'agent'}
            {sessionCount > 1 && (
              <span style={{ color: 'var(--ink-3)' }}>
                +{sessionCount - 1}
              </span>
            )}
          </span>
        )}
      </div>

      {/* V1 card — no border since wrapper provides it */}
      <div
        style={{
          borderRadius: 0,
        }}
      >
        <CommandCenterFeatureCard
          item={item}
          commandValue={commandValue}
          onCopyCommand={onCopyCommand}
          onOpenLaunch={
            onOpenLaunch
              ? (featureId) => onOpenLaunch(featureId, project.projectId)
              : undefined
          }
          onOpenExecution={
            onOpenExecution
              ? (featureId) => onOpenExecution(featureId, project.projectId)
              : undefined
          }
          onOpenPlan={onOpenPlan}
          onOpenDetail={
            onOpenDetail
              ? (featureId) => onOpenDetail(featureId, project.projectId)
              : undefined
          }
          onOpenPullRequest={onOpenPullRequest}
        />
      </div>
    </div>
  );
}
