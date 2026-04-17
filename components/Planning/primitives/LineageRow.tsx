import { Clock } from 'lucide-react';

import type { PlanningNode } from '../../../types';
import { PlanningNodeTypeIcon, StatusChip, statusVariant } from '@miethe/ui/primitives';

export interface LineageRowProps {
  node: PlanningNode;
}

function formatTimestamp(value?: string): string {
  if (!value) return 'n/a';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

/**
 * Renders a single planning node as a lineage row: icon, title, path,
 * optional timestamp, and raw + effective status chips. Identical to the
 * row rendered inside LineagePanel in PlanningNodeDetail.
 */
export function LineageRow({ node }: LineageRowProps) {
  const isMismatch = node.mismatchState?.isMismatch;

  return (
    <div className="flex items-start gap-3 px-4 py-3 bg-surface-elevated">
      <div className="mt-0.5">
        <PlanningNodeTypeIcon type={node.type} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-panel-foreground truncate" title={node.title}>
          {node.title || node.id}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground/70 truncate" title={node.path}>
          {node.path}
        </p>
        {node.updatedAt && (
          <p className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground/50">
            <Clock size={9} />
            {formatTimestamp(node.updatedAt)}
          </p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <StatusChip label={node.rawStatus} variant={statusVariant(node.rawStatus)} />
        {node.effectiveStatus && node.effectiveStatus !== node.rawStatus && (
          <StatusChip
            label={`eff: ${node.effectiveStatus}`}
            variant={isMismatch ? 'warn' : statusVariant(node.effectiveStatus)}
          />
        )}
      </div>
    </div>
  );
}
