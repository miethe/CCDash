import type { PlanningCommandCenterItem } from '@/types';

export function appendRelatedFileToCommand(command: string, path: string): string {
  const trimmedCommand = command.trim();
  const trimmedPath = path.trim();
  if (!trimmedPath) return trimmedCommand;
  if (trimmedCommand.includes(trimmedPath)) return trimmedCommand;
  const contextArg = `--context "${trimmedPath}"`;
  return trimmedCommand ? `${trimmedCommand} ${contextArg}` : contextArg;
}

export function commandCenterItemKey(item: PlanningCommandCenterItem): string {
  return item.feature.featureId || item.feature.featureSlug || item.feature.name;
}

export function commandCenterDisplayName(item: PlanningCommandCenterItem): string {
  return item.feature.name || item.feature.featureSlug || item.feature.featureId;
}

export function commandCenterPlanPath(item: PlanningCommandCenterItem): string {
  return (
    item.command?.targetArtifactPath ||
    item.targetArtifact?.path ||
    item.artifacts.find((artifact) => artifact.docType === 'implementation_plan')?.path ||
    item.artifacts[0]?.path ||
    ''
  );
}

export function commandCenterDoneLabel(item: PlanningCommandCenterItem): string {
  const status = item.status.effectiveStatus || item.status.rawStatus;
  const branch = item.worktree?.branch;
  const head = item.gitState?.head;
  if (!/done|complete|completed|merged/i.test(status)) return '';
  const location = branch || head;
  return location ? `done on ${location}` : 'done';
}

export function commandCenterLaunchReadiness(item: PlanningCommandCenterItem): string {
  if (item.blockers.length > 0) return 'blocked';
  if (item.launchBatch?.readiness) return item.launchBatch.readiness;
  if (item.capabilities.launch) return 'ready';
  return 'needs context';
}

export function commandCenterLaunchPhase(item: PlanningCommandCenterItem): number | null {
  return item.command?.phase ?? item.phase.currentPhase ?? item.phase.nextPhase ?? null;
}

export function commandCenterLaunchBatchId(item: PlanningCommandCenterItem): string {
  return item.launchBatch?.batchId || item.worktree?.batchId || '';
}

export function canLaunchCommandCenterItem(item: PlanningCommandCenterItem): boolean {
  return Boolean(
    item.capabilities.launch &&
    item.blockers.length === 0 &&
    commandCenterLaunchPhase(item) &&
    commandCenterLaunchBatchId(item),
  );
}

export function commandCenterStatusBucket(item: PlanningCommandCenterItem): string {
  if (item.blockers.length > 0) return 'blocked';
  const signal = `${item.status.planningSignal} ${item.status.effectiveStatus} ${item.status.rawStatus}`.toLowerCase();
  if (signal.includes('complete') || signal.includes('done') || signal.includes('merged')) return 'done';
  if (signal.includes('active') || signal.includes('progress') || signal.includes('running')) return 'active';
  if (signal.includes('ready')) return 'ready';
  return 'needs plan';
}

export type CommandCenterBoardBucketId = 'needs-plan' | 'ready' | 'active' | 'blocked' | 'done';

export interface CommandCenterBoardBucket {
  id: CommandCenterBoardBucketId;
  label: string;
  description: string;
}

export const COMMAND_CENTER_BOARD_BUCKETS: CommandCenterBoardBucket[] = [
  { id: 'needs-plan', label: 'Needs Plan', description: 'Missing or incomplete planning context' },
  { id: 'ready', label: 'Ready', description: 'Ready for the next planning or execution command' },
  { id: 'active', label: 'Active Phase', description: 'Worktree or phase execution is already moving' },
  { id: 'blocked', label: 'Blocked', description: 'Requires human or dependency resolution first' },
  { id: 'done', label: 'Review/Done', description: 'Completed, committed, or review-ready work' },
];

export function bucketCommandCenterItem(item: PlanningCommandCenterItem): CommandCenterBoardBucketId {
  const bucket = commandCenterStatusBucket(item);
  if (bucket === 'blocked') return 'blocked';
  if (bucket === 'done') return 'done';
  if (bucket === 'active') return 'active';
  if (bucket === 'ready' || item.capabilities.launch || item.launchBatch?.readiness === 'ready') return 'ready';
  return 'needs-plan';
}

export function compactPath(path: string, max = 78): string {
  if (path.length <= max) return path;
  return `...${path.slice(-(max - 3))}`;
}

/**
 * Returns true when a board bucket column should start collapsed by default.
 *
 * Auto-collapse rules:
 *   - The "done" bucket always starts collapsed.
 *   - Any bucket with zero items starts collapsed.
 *
 * Once the user manually toggles a column this helper is no longer consulted
 * for that column — the userToggled guard in the component takes over.
 */
export function isBoardBucketCollapsedByDefault(
  bucketId: CommandCenterBoardBucketId,
  itemCount: number,
): boolean {
  if (itemCount === 0) return true;
  if (bucketId === 'done') return true;
  return false;
}
