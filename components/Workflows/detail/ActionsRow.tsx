import React from 'react';
import { ArrowRight, ExternalLink } from 'lucide-react';

import { WorkflowRegistryAction } from '../../../types';

interface ActionsRowProps {
  actions: WorkflowRegistryAction[];
  onOpenAction: (action: WorkflowRegistryAction) => void;
}

export const ActionsRow: React.FC<ActionsRowProps> = ({ actions, onOpenAction }) => (
  <section className="rounded-[28px] border border-panel-border bg-surface-overlay/70 px-5 py-5">
    <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Actions</div>
    <h3 className="mt-2 text-xl font-semibold tracking-tight text-panel-foreground">Follow the workflow across systems</h3>

    <div className="mt-4 flex flex-wrap gap-2.5">
      {actions.length > 0 ? (
        actions.map(action => (
          <button
            key={action.id}
            type="button"
            disabled={action.disabled}
            onClick={() => onOpenAction(action)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              action.disabled
                ? 'cursor-not-allowed border border-panel-border bg-panel text-muted-foreground'
                : action.target === 'external'
                  ? 'border border-sky-500/30 bg-sky-500/10 text-sky-100 hover:bg-sky-500/20'
                  : 'border border-indigo-500/30 bg-indigo-500/10 text-indigo-100 hover:bg-indigo-500/20'
            }`}
            title={action.reason || action.label}
          >
            {action.label}
            {action.target === 'external' ? <ExternalLink size={12} /> : <ArrowRight size={12} />}
          </button>
        ))
      ) : (
        <div className="text-sm text-muted-foreground">No follow-up actions are currently available.</div>
      )}
    </div>
  </section>
);
