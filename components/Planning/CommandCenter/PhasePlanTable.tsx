import { Fragment } from 'react';
import type { PlanningCommandCenterPhaseRow, SessionLink } from '@/types';
import { compactPath } from './commandCenterUtils';
import { ArtifactChip, StatusPill } from '../primitives';

interface PhasePlanTableProps {
  rows: PlanningCommandCenterPhaseRow[];
}

/** Formats an ISO-8601 timestamp to a compact local time string. */
function formatSessionTime(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/** Derives a transcript href for a session, preferring the backend-supplied
 *  transcriptHref but falling back to the hash-based session route. */
function resolveTranscriptHref(session: SessionLink): string {
  if (session.transcriptHref) return session.transcriptHref;
  return `#/sessions/${encodeURIComponent(session.sessionId)}`;
}

export function PhasePlanTable({ rows }: PhasePlanTableProps) {
  if (rows.length === 0) {
    return (
      <div className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-3 py-2 text-[11px] text-[color:var(--ink-4)]">
        No phase table is available yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="command-center-phase-table">
      <table className="w-full min-w-[780px] border-separate border-spacing-0 text-left">
        <thead>
          <tr className="planning-caps text-[9.5px] text-[color:var(--ink-4)]">
            <th className="border-b border-[color:var(--line-1)] px-2 py-2 font-medium">phase</th>
            <th className="border-b border-[color:var(--line-1)] px-2 py-2 font-medium">status</th>
            <th className="border-b border-[color:var(--line-1)] px-2 py-2 font-medium">points</th>
            <th className="border-b border-[color:var(--line-1)] px-2 py-2 font-medium">agent/model</th>
            <th className="border-b border-[color:var(--line-1)] px-2 py-2 font-medium">files</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const sessions = row.linkedSessions ?? [];
            const hasSessions = sessions.length > 0;
            const rowKey = `${row.phaseNumber ?? 'x'}:${row.name}:${index}`;

            return (
              <Fragment key={rowKey}>
                <tr className="text-[11px] text-[color:var(--ink-2)]">
                  <td className={hasSessions ? 'px-2 pt-2 pb-0' : 'border-b border-[color:var(--line-1)] px-2 py-2'}>
                    <div className="planning-mono text-[10.5px] text-[color:var(--ink-1)]">
                      {row.phaseNumber ? `P${row.phaseNumber}` : 'phase'}
                    </div>
                    <div className="truncate text-[11px]" title={row.name}>{row.name}</div>
                  </td>
                  <td className={hasSessions ? 'px-2 pt-2 pb-0' : 'border-b border-[color:var(--line-1)] px-2 py-2'}>
                    <StatusPill status={row.status || 'unknown'} />
                  </td>
                  <td className={`planning-tnum ${hasSessions ? 'px-2 pt-2 pb-0' : 'border-b border-[color:var(--line-1)] px-2 py-2'}`}>
                    {row.storyPoints ?? '-'}
                  </td>
                  <td className={hasSessions ? 'px-2 pt-2 pb-0' : 'border-b border-[color:var(--line-1)] px-2 py-2'}>
                    <div className="planning-mono text-[10.5px]">{row.agents.join(', ') || 'unassigned'}</div>
                    <div className="planning-mono text-[10px] text-[color:var(--ink-4)]">{row.model || row.domain || 'model TBD'}</div>
                  </td>
                  <td className={hasSessions ? 'px-2 pt-2 pb-0' : 'border-b border-[color:var(--line-1)] px-2 py-2'}>
                    <div className="flex max-w-[320px] flex-wrap gap-1">
                      {row.phaseFiles.slice(0, 3).map((path) => (
                        <ArtifactChip key={path} kind="progress" label={compactPath(path, 34)} />
                      ))}
                      {row.phaseFiles.length > 3 ? (
                        <span className="planning-mono text-[10px] text-[color:var(--ink-4)]">
                          +{row.phaseFiles.length - 3}
                        </span>
                      ) : null}
                    </div>
                  </td>
                </tr>
                {hasSessions ? (
                  <tr data-testid="command-center-phase-session-links">
                    <td
                      colSpan={5}
                      className="border-b border-[color:var(--line-1)] px-2 pb-2 pt-1"
                    >
                      <div className="flex flex-wrap gap-x-4 gap-y-1">
                        {sessions.map((session) => (
                          <a
                            key={session.sessionId}
                            href={resolveTranscriptHref(session)}
                            className="planning-mono flex items-baseline gap-1 text-[10px] text-[color:var(--brand)] underline-offset-2 hover:underline"
                            aria-label={`Open transcript for session ${session.agentName ?? session.sessionId}`}
                          >
                            <span>{session.agentName || 'agent'}</span>
                            {session.startTime ? (
                              <span className="text-[color:var(--ink-4)]">
                                {formatSessionTime(session.startTime)}
                              </span>
                            ) : null}
                          </a>
                        ))}
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
