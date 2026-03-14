import React from 'react';
import { AlertTriangle, ArrowRight, Clock3, Terminal } from 'lucide-react';

import { WorkflowRegistryItem } from '../../../types';
import {
  correlationBadgeClass,
  correlationStateLabel,
  formatDateTime,
  formatInteger,
  formatPercent,
  hasEffectivenessSummary,
  scoreBarClass,
} from '../workflowRegistryUtils';

const MiniScoreBar: React.FC<{
  label: string;
  value: number;
  kind: 'success' | 'efficiency' | 'quality' | 'risk';
}> = ({ label, value, kind }) => (
  <div className="space-y-1">
    <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.18em] text-slate-500">
      <span>{label}</span>
      <span className="font-mono text-slate-300">{formatPercent(value)}</span>
    </div>
    <div className="h-1.5 overflow-hidden rounded-full bg-slate-900">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${scoreBarClass(kind)}`}
        style={{ width: `${Math.max(6, Math.round(Math.max(0, Math.min(1, value)) * 100))}%` }}
      />
    </div>
  </div>
);

interface WorkflowListItemProps {
  item: WorkflowRegistryItem;
  selected: boolean;
  active: boolean;
  onSelect: (itemId: string) => void;
}

export const WorkflowListItem: React.FC<WorkflowListItemProps> = ({
  item,
  selected,
  active,
  onSelect,
}) => {
  const aliases = item.identity.observedAliases.filter(
    alias => alias && alias !== item.identity.observedWorkflowFamilyRef,
  );

  return (
    <button
      id={`workflow-catalog-item-${item.id}`}
      type="button"
      onClick={() => onSelect(item.id)}
      className={`w-full rounded-[24px] border p-4 text-left transition-all ${
        selected
          ? 'border-indigo-500/35 bg-indigo-500/10 shadow-[0_18px_50px_-26px_rgba(99,102,241,0.65)]'
          : active
            ? 'border-slate-700 bg-slate-950/75'
            : 'border-slate-800/80 bg-slate-950/50 hover:border-slate-700'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-100 [overflow-wrap:anywhere]">
            {item.identity.displayLabel || item.identity.observedWorkflowFamilyRef || item.id}
          </div>
          <div className="mt-1 text-xs text-slate-500 [overflow-wrap:anywhere]">
            {item.identity.observedWorkflowFamilyRef || item.identity.registryId}
          </div>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] font-semibold ${correlationBadgeClass(item.correlationState)}`}
        >
          {correlationStateLabel(item.correlationState)}
        </span>
      </div>

      {(item.identity.resolvedWorkflowLabel || item.identity.resolvedCommandArtifactLabel) && (
        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
          {item.identity.resolvedWorkflowLabel && (
            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-emerald-100">
              {item.identity.resolvedWorkflowLabel}
            </span>
          )}
          {item.identity.resolvedCommandArtifactLabel && (
            <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-sky-100">
              {item.identity.resolvedCommandArtifactLabel}
            </span>
          )}
        </div>
      )}

      {aliases.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {aliases.slice(0, 3).map(alias => (
            <span
              key={`${item.id}-${alias}`}
              className="rounded-full border border-slate-800 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-300"
            >
              {alias}
            </span>
          ))}
          {aliases.length > 3 && (
            <span className="rounded-full border border-slate-800 bg-slate-900/80 px-2 py-1 text-[11px] text-slate-500">
              +{aliases.length - 3} aliases
            </span>
          )}
        </div>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/65 px-3 py-3">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <Terminal size={12} />
            Commands
          </div>
          <div className="mt-2 text-lg font-semibold text-slate-100">{formatInteger(item.observedCommandCount)}</div>
          <div className="mt-1 text-xs text-slate-500 [overflow-wrap:anywhere]">
            {item.representativeCommands[0] || 'No representative command cached'}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/65 px-3 py-3">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
            <Clock3 size={12} />
            Last Seen
          </div>
          <div className="mt-2 text-sm font-semibold text-slate-100">{formatDateTime(item.lastObservedAt)}</div>
          <div className="mt-1 text-xs text-slate-500">
            Sample size {formatInteger(item.sampleSize)}
          </div>
        </div>
      </div>

      {hasEffectivenessSummary(item.effectiveness) ? (
        <div className="mt-4 space-y-3">
          <MiniScoreBar label="Success" value={item.effectiveness.successScore} kind="success" />
          <MiniScoreBar label="Efficiency" value={item.effectiveness.efficiencyScore} kind="efficiency" />
          <MiniScoreBar label="Quality" value={item.effectiveness.qualityScore} kind="quality" />
          <MiniScoreBar label="Risk" value={item.effectiveness.riskScore} kind="risk" />
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-3 text-sm text-slate-400">
          No effectiveness rollup cached for this workflow yet.
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <AlertTriangle size={12} className={item.issueCount > 0 ? 'text-amber-400' : 'text-slate-600'} />
          <span>{formatInteger(item.issueCount)} issue{item.issueCount === 1 ? '' : 's'}</span>
        </div>
        <span className="inline-flex items-center gap-1 text-slate-300">
          Open detail
          <ArrowRight size={12} />
        </span>
      </div>
    </button>
  );
};
