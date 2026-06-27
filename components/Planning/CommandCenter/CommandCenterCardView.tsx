import type { PlanningCommandCenterItem } from '@/types';
import { commandCenterItemKey } from './commandCenterUtils';
import { CommandCenterFeatureCard } from './CommandCenterFeatureCard';

interface CommandCenterCardViewProps {
  items: PlanningCommandCenterItem[];
  commandOverrides: Record<string, string>;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

export function CommandCenterCardView({
  items,
  commandOverrides,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: CommandCenterCardViewProps) {
  if (items.length === 0) {
    return (
      <div
        className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-4 py-8 text-center text-[12px] text-[color:var(--ink-3)]"
        data-testid="command-center-card-empty"
      >
        No planning items match the current filters.
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3" data-testid="command-center-card-view">
      {items.map((item) => {
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
    </div>
  );
}
