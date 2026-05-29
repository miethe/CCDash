import type { PlanningCommandCenterPhaseRow } from '@/types';
import { compactPath } from './commandCenterUtils';
import { ArtifactChip, StatusPill } from '../primitives';

interface PhasePlanTableProps {
  rows: PlanningCommandCenterPhaseRow[];
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
          {rows.map((row, index) => (
            <tr key={`${row.phaseNumber ?? 'x'}:${row.name}:${index}`} className="text-[11px] text-[color:var(--ink-2)]">
              <td className="border-b border-[color:var(--line-1)] px-2 py-2">
                <div className="planning-mono text-[10.5px] text-[color:var(--ink-1)]">
                  {row.phaseNumber ? `P${row.phaseNumber}` : 'phase'}
                </div>
                <div className="truncate text-[11px]" title={row.name}>{row.name}</div>
              </td>
              <td className="border-b border-[color:var(--line-1)] px-2 py-2">
                <StatusPill status={row.status || 'unknown'} />
              </td>
              <td className="planning-tnum border-b border-[color:var(--line-1)] px-2 py-2">
                {row.storyPoints ?? '-'}
              </td>
              <td className="border-b border-[color:var(--line-1)] px-2 py-2">
                <div className="planning-mono text-[10.5px]">{row.agents.join(', ') || 'unassigned'}</div>
                <div className="planning-mono text-[10px] text-[color:var(--ink-4)]">{row.model || row.domain || 'model TBD'}</div>
              </td>
              <td className="border-b border-[color:var(--line-1)] px-2 py-2">
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
