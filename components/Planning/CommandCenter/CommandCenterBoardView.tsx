import { memo, useCallback, useState } from 'react';
import { ChevronRight } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { PlanningCommandCenterItem } from '@/types';
import {
  bucketCommandCenterItem,
  COMMAND_CENTER_BOARD_BUCKETS,
  commandCenterItemKey,
  isBoardBucketCollapsedByDefault,
  type CommandCenterBoardBucket,
  type CommandCenterBoardBucketId,
} from './commandCenterUtils';
import { CommandCenterFeatureCard } from './CommandCenterFeatureCard';
import { Chip } from '../primitives';

// ── Column strip width ────────────────────────────────────────────────────────

/** Width of a collapsed column strip in px. */
const COLLAPSED_WIDTH_PX = 44;

/** Minimum width of an expanded column so cards stay readable. */
const EXPANDED_MIN_WIDTH_PX = 200;

// ── Board bucket column ───────────────────────────────────────────────────────

interface BucketColumnProps {
  bucket: CommandCenterBoardBucket;
  items: PlanningCommandCenterItem[];
  commandOverrides: Record<string, string>;
  onCopyCommand?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: (featureId: string) => void;
  onOpenPullRequest?: (url: string) => void;
}

const BucketColumn = memo(function BucketColumn({
  bucket,
  items,
  commandOverrides,
  onCopyCommand,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: BucketColumnProps) {
  const [collapsed, setCollapsed] = useState(() =>
    isBoardBucketCollapsedByDefault(bucket.id, items.length),
  );
  const [userToggled, setUserToggled] = useState(false);

  // Re-evaluate auto-default only before the first user toggle.
  // (If item count flips to 0 after initial render, auto-collapse fires.)
  // We deliberately do NOT use useEffect here to avoid a flash — the initial
  // state already accounts for item count at mount time. For card-count changes
  // after mount (e.g. filter changes) the parent re-mounts via key change.

  const handleToggle = useCallback(() => {
    setCollapsed((prev) => !prev);
    setUserToggled(true);
  }, []);

  // ── Collapsed strip ──────────────────────────────────────────────────────
  if (collapsed) {
    return (
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={false}
        aria-label={`Expand ${bucket.label} column (${items.length} items)`}
        data-testid="board-bucket-column-collapsed"
        data-bucket-id={bucket.id}
        className={cn(
          'flex flex-col items-center justify-start gap-2',
          'rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)]',
          'cursor-pointer pt-3 pb-2',
          'transition-colors duration-150',
          'hover:bg-[color:var(--bg-1)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
        )}
        style={{ flex: `0 0 ${COLLAPSED_WIDTH_PX}px`, minWidth: COLLAPSED_WIDTH_PX }}
      >
        <ChevronRight
          size={12}
          aria-hidden
          className="flex-shrink-0 text-[color:var(--ink-3)]"
        />
        <Chip className="planning-mono flex-shrink-0 text-[10px]">{items.length}</Chip>
        <span
          className="planning-mono text-[11px] font-semibold text-[color:var(--ink-2)]"
          style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
        >
          {bucket.label}
        </span>
      </button>
    );
  }

  // ── Expanded column ──────────────────────────────────────────────────────
  void userToggled; // suppress unused-var lint; guards future auto-re-evaluation
  return (
    <section
      data-testid="board-bucket-column-expanded"
      data-bucket-id={bucket.id}
      aria-label={bucket.label}
      className="min-h-[320px] rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] p-3"
      style={{ flex: '1 1 0', minWidth: EXPANDED_MIN_WIDTH_PX }}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-[13px] font-semibold text-[color:var(--ink-0)]">{bucket.label}</h3>
          <p className="mt-0.5 text-[10.5px] leading-snug text-[color:var(--ink-4)]">{bucket.description}</p>
        </div>
        <div className="flex flex-shrink-0 items-center gap-1">
          <Chip className="planning-mono text-[10px]">{items.length}</Chip>
          {/* Collapse toggle */}
          <button
            type="button"
            onClick={handleToggle}
            aria-expanded={true}
            aria-label={`Collapse ${bucket.label} column`}
            className={cn(
              'flex h-5 w-5 items-center justify-center rounded',
              'text-[color:var(--ink-4)] hover:bg-[color:var(--bg-3)] hover:text-[color:var(--ink-2)]',
              'transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
            )}
          >
            <ChevronRight
              size={11}
              aria-hidden
              className="rotate-90 transition-transform duration-150 motion-reduce:transition-none"
            />
          </button>
        </div>
      </div>

      {/* Card list */}
      <div className="space-y-3">
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
        {items.length === 0 && (
          <div className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-3 py-6 text-center text-[11px] text-[color:var(--ink-4)]">
            No items
          </div>
        )}
      </div>
    </section>
  );
});

// ── Board view ────────────────────────────────────────────────────────────────

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
  // Bucket items in a single pass.
  const itemsByBucket = COMMAND_CENTER_BOARD_BUCKETS.reduce<
    Record<CommandCenterBoardBucketId, PlanningCommandCenterItem[]>
  >(
    (acc, bucket) => {
      acc[bucket.id] = [];
      return acc;
    },
    {} as Record<CommandCenterBoardBucketId, PlanningCommandCenterItem[]>,
  );
  items.forEach((item) => {
    itemsByBucket[bucketCommandCenterItem(item)].push(item);
  });

  return (
    // Outer wrapper: horizontal scroll kicks in below ~900px of expanded content.
    <div
      className="overflow-x-auto pb-2"
      data-testid="command-center-board-view"
    >
      {/*
        Flex row: collapsed columns take fixed narrow width, expanded columns
        share remaining space equally. Horizontal scroll on small viewports.
      */}
      <div
        className="flex gap-3"
        style={{ minWidth: `${COMMAND_CENTER_BOARD_BUCKETS.length * COLLAPSED_WIDTH_PX + 4 * (EXPANDED_MIN_WIDTH_PX + 12)}px` }}
      >
        {COMMAND_CENTER_BOARD_BUCKETS.map((bucket) => (
          <BucketColumn
            key={bucket.id}
            bucket={bucket}
            items={itemsByBucket[bucket.id]}
            commandOverrides={commandOverrides}
            onCopyCommand={onCopyCommand}
            onOpenLaunch={onOpenLaunch}
            onOpenExecution={onOpenExecution}
            onOpenPlan={onOpenPlan}
            onOpenDetail={onOpenDetail}
            onOpenPullRequest={onOpenPullRequest}
          />
        ))}
      </div>
    </div>
  );
}
