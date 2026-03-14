import React from 'react';

import { WorkflowRegistryCorrelationState } from '../../../types';
import { WORKFLOW_FILTER_OPTIONS } from '../workflowRegistryUtils';

interface CatalogFilterBarProps {
  activeFilter: WorkflowRegistryCorrelationState | 'all';
  counts: Partial<Record<WorkflowRegistryCorrelationState | 'all', number>>;
  onChange: (value: WorkflowRegistryCorrelationState | 'all') => void;
}

export const CatalogFilterBar: React.FC<CatalogFilterBarProps> = ({
  activeFilter,
  counts,
  onChange,
}) => (
  <div className="flex flex-wrap gap-2">
    {WORKFLOW_FILTER_OPTIONS.map(option => {
      const active = option.value === activeFilter;
      return (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={
            active
              ? 'rounded-full border border-indigo-500/30 bg-indigo-500/15 px-3 py-1 text-xs font-semibold text-indigo-200'
              : 'rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-400 transition-colors hover:border-slate-600'
          }
        >
          {option.label}
          <span className="ml-1.5 text-[11px] text-current/70">{counts[option.value] ?? 0}</span>
        </button>
      );
    })}
  </div>
);
