import type { PlanningCommandCenterItem } from '@/types';
import {
  bucketCommandCenterItem,
  COMMAND_CENTER_BOARD_BUCKETS,
  commandCenterItemKey,
} from './commandCenterUtils';
import { CommandCenterFeatureCard } from './CommandCenterFeatureCard';
import { Chip } from '../primitives';

interface CommandCenterBoardViewProps {
  items: PlanningCommandCenterItem[];
  commandOverrides: Record<string, string>;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

export function CommandCenterBoardView({
  items,
  commandOverrides,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: CommandCenterBoardViewProps) {
  const itemsByBucket = COMMAND_CENTER_BOARD_BUCKETS.reduce<Record<string, PlanningCommandCenterItem[]>>(
    (acc, bucket) => {
      acc[bucket.id] = [];
      return acc;
    },
    {},
  );
  items.forEach((item) => {
    itemsByBucket[bucketCommandCenterItem(item)].push(item);
  });

  return (
    // Fluid 5-column grid: allow horizontal scroll only below ~900px so columns
    // never fully collapse. The parent container controls the overall max-width.
    <div className="overflow-x-auto pb-2" data-testid="command-center-board-view">
      <div className="grid min-w-[900px] grid-cols-5 gap-3">
        {COMMAND_CENTER_BOARD_BUCKETS.map((bucket) => (
          <section
            key={bucket.id}
            className="min-h-[320px] rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-3"
          >
            <div className="mb-3 flex items-start justify-between gap-2">
              <div>
                <h3 className="text-[13px] font-semibold text-[color:var(--ink-0)]">{bucket.label}</h3>
                <p className="mt-0.5 text-[10.5px] leading-snug text-[color:var(--ink-4)]">{bucket.description}</p>
              </div>
              <Chip className="planning-mono shrink-0 text-[10px]">{itemsByBucket[bucket.id].length}</Chip>
            </div>
            <div className="space-y-3">
              {itemsByBucket[bucket.id].map((item) => {
                const key = commandCenterItemKey(item);
                return (
                  <CommandCenterFeatureCard
                    key={key}
                    item={item}
                    commandValue={commandOverrides[key] ?? item.command?.command ?? ''}
                    onCopyCommand={onCopyCommand}
                    onOpenLaunch={onOpenLaunch}
                    onOpenExecution={onOpenExecution}
                    onOpenPlan={onOpenPlan}
                    onOpenDetail={onOpenDetail}
                    onOpenPullRequest={onOpenPullRequest}
                  />
                );
              })}
              {itemsByBucket[bucket.id].length === 0 ? (
                <div className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-3 py-6 text-center text-[11px] text-[color:var(--ink-4)]">
                  No items
                </div>
              ) : null}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
