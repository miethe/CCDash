import type { PlanningPhaseBatchReadinessState } from '../../../types';
import { StatusChip } from './StatusChip';
import { readinessVariant } from './variants';

export interface BatchReadinessPillProps {
  readinessState: PlanningPhaseBatchReadinessState | string;
  blockingNodeIds?: string[];
  blockingTaskIds?: string[];
}

/**
 * Renders the batch readiness chip with optional blocker details shown inline
 * below the chip when blockingNodeIds or blockingTaskIds are present.
 */
export function BatchReadinessPill({
  readinessState,
  blockingNodeIds,
  blockingTaskIds,
}: BatchReadinessPillProps) {
  return (
    <div className="inline-flex flex-col gap-1">
      <StatusChip label={readinessState} variant={readinessVariant(readinessState)} />
      {blockingNodeIds && blockingNodeIds.length > 0 && (
        <div className="text-[10px] text-rose-400/80 truncate">
          Blocking nodes: {blockingNodeIds.join(', ')}
        </div>
      )}
      {blockingTaskIds && blockingTaskIds.length > 0 && (
        <div className="text-[10px] text-rose-400/80 truncate">
          Blocking tasks: {blockingTaskIds.join(', ')}
        </div>
      )}
    </div>
  );
}
