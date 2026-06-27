import type { PlanningCommandCenterItem } from '@/types';
import { commandCenterItemKey } from './commandCenterUtils';
import { CommandCenterFeatureRow } from './CommandCenterFeatureRow';

interface CommandCenterListViewProps {
  items: PlanningCommandCenterItem[];
  expandedIds: Set<string>;
  commandOverrides: Record<string, string>;
  onToggleExpanded: (featureId: string) => void;
  onCommandChange: (featureId: string, command: string) => void;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

export function CommandCenterListView({
  items,
  expandedIds,
  commandOverrides,
  onToggleExpanded,
  onCommandChange,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: CommandCenterListViewProps) {
  if (items.length === 0) {
    return (
      <div
        className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-4 py-8 text-center text-[12px] text-[color:var(--ink-3)]"
        data-testid="command-center-empty"
      >
        No planning items match the current filters.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="command-center-list-view">
      <div className="grid grid-cols-[minmax(220px,1.5fr)_minmax(120px,0.55fr)_minmax(120px,0.55fr)_minmax(140px,0.7fr)_minmax(220px,1fr)_minmax(180px,0.8fr)] gap-0 px-3 text-[9.5px] max-xl:hidden">
        {['feature', 'status', 'phase', 'worktree', 'next command', 'context'].map((label) => (
          <div key={label} className="planning-caps pb-2 text-[color:var(--ink-4)]">{label}</div>
        ))}
      </div>
      {items.map((item) => {
        const key = commandCenterItemKey(item);
        return (
          <CommandCenterFeatureRow
            key={key}
            item={item}
            expanded={expandedIds.has(key)}
            commandValue={commandOverrides[key] ?? item.command?.command ?? ''}
            onToggleExpanded={onToggleExpanded}
            onCommandChange={onCommandChange}
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
