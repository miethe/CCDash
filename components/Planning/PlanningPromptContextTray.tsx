/**
 * PASB-403: PlanningPromptContextTray
 *
 * A context-management tray that sits alongside the PlanningNextRunPreview
 * panel. Users curate which sessions, phases, tasks, and artifacts should be
 * injected into the next-run prompt skeleton.
 *
 * Features:
 *   - Shows selected context items as removable chips (grouped by type)
 *   - "Add Context" button per section to open a lightweight selection UI
 *   - Lifting state via `onSelectionChange` callback
 *   - Keyboard accessible: Tab through chips, Delete/Backspace to remove
 *
 * Integration note:
 *   This component is intentionally standalone — wiring it into the board is
 *   handled separately (PASB-404). Import and compose with PlanningNextRunPreview.
 */

import { useState, useCallback, useRef, useId, type JSX, type KeyboardEvent, type DragEvent } from 'react';
import {
  GitCommit,
  Layers,
  Tag,
  FileBox,
  FileText,
  X,
  PlusCircle,
  LayoutList,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { trackContextAdded } from '@/services/planningTelemetry';
import type { PromptContextSelection } from '@/types';

// ── Context item shape ────────────────────────────────────────────────────────

export interface ContextTrayItem {
  id: string;
  label: string;
  kind: 'session' | 'phase' | 'task' | 'artifact' | 'transcript';
  /** Optional human-readable subtitle (e.g. feature name, path) */
  subtitle?: string;
}

// ── Style constants ───────────────────────────────────────────────────────────

const KIND_ICON: Record<ContextTrayItem['kind'], JSX.Element> = {
  session: <GitCommit size={9} aria-hidden />,
  phase: <Layers size={9} aria-hidden />,
  task: <Tag size={9} aria-hidden />,
  artifact: <FileBox size={9} aria-hidden />,
  transcript: <FileText size={9} aria-hidden />,
};

const KIND_COLOR: Record<ContextTrayItem['kind'], string> = {
  session: 'var(--brand)',
  phase: 'var(--info, #60a5fa)',
  task: 'var(--ok)',
  artifact: 'var(--warn)',
  transcript: 'var(--ink-3)',
};

const KIND_LABEL: Record<ContextTrayItem['kind'], string> = {
  session: 'Sessions',
  phase: 'Phases',
  task: 'Tasks',
  artifact: 'Artifacts',
  transcript: 'Transcripts',
};

const SECTION_ORDER: ContextTrayItem['kind'][] = [
  'session',
  'phase',
  'task',
  'artifact',
  'transcript',
];

// ── buildSelection: derive PromptContextSelection from tray items ──────────────

function buildSelection(items: ContextTrayItem[]): PromptContextSelection {
  const byKind = (kind: ContextTrayItem['kind']) =>
    items.filter((i) => i.kind === kind).map((i) => i.id);

  return {
    sessionIds: byKind('session'),
    phaseRefs: byKind('phase'),
    taskRefs: byKind('task'),
    artifactRefs: byKind('artifact'),
    transcriptRefs: byKind('transcript'),
  };
}

// ── RemovableChip ─────────────────────────────────────────────────────────────

function RemovableChip({
  item,
  onRemove,
}: {
  item: ContextTrayItem;
  onRemove: (id: string) => void;
}) {
  const color = KIND_COLOR[item.kind];

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLSpanElement>) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        onRemove(item.id);
      }
    },
    [item.id, onRemove],
  );

  return (
    <span
      className="planning-mono group inline-flex max-w-[200px] items-center gap-1 rounded px-1.5 py-0.5 text-[9.5px] font-medium leading-none"
      style={{
        color,
        background: `color-mix(in oklab, ${color} 10%, transparent)`,
        border: `1px solid color-mix(in oklab, ${color} 25%, transparent)`,
      }}
      role="listitem"
      tabIndex={0}
      aria-label={`${item.kind}: ${item.label}. Press Delete to remove.`}
      onKeyDown={handleKeyDown}
      data-testid={`context-chip-${item.kind}-${item.id}`}
    >
      <span style={{ display: 'flex', color, flexShrink: 0 }}>
        {KIND_ICON[item.kind]}
      </span>
      <span className="truncate" title={item.subtitle ?? item.label}>
        {item.label}
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(item.id);
        }}
        className={cn(
          'ml-0.5 flex-shrink-0 rounded-full p-px opacity-60 transition-opacity hover:opacity-100',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
        )}
        style={{ color }}
        aria-label={`Remove ${item.kind} ${item.label}`}
        tabIndex={-1}
      >
        <X size={8} aria-hidden />
      </button>
    </span>
  );
}

// ── AddContextButton ──────────────────────────────────────────────────────────
//
// Opens a minimal inline text-field to paste / type an item ID.
// In a full integration this would be replaced by a search popover that
// queries sessions/phases/tasks from the planning API.

function AddContextButton({
  kind,
  onAdd,
}: {
  kind: ContextTrayItem['kind'];
  onAdd: (item: ContextTrayItem) => void;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const color = KIND_COLOR[kind];

  const handleOpen = useCallback(() => {
    setOpen(true);
    // Focus on next tick after render
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  const handleCommit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) {
      setOpen(false);
      setValue('');
      return;
    }
    onAdd({
      id: trimmed,
      label: trimmed,
      kind,
    });
    setValue('');
    setOpen(false);
  }, [value, kind, onAdd]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleCommit();
      } else if (e.key === 'Escape') {
        setOpen(false);
        setValue('');
      }
    },
    [handleCommit],
  );

  if (open) {
    return (
      <div className="flex items-center gap-1">
        <label htmlFor={inputId} className="sr-only">
          Add {kind} ID
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleCommit}
          placeholder={`${kind} ID…`}
          className={cn(
            'planning-mono rounded border px-1.5 py-0.5 text-[9.5px]',
            'bg-[color:var(--bg-2)] text-[color:var(--ink-1)]',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
          )}
          style={{
            borderColor: 'var(--line-1)',
            width: 120,
          }}
          aria-label={`Add ${kind} by ID`}
          data-testid={`add-context-input-${kind}`}
        />
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleOpen}
      className={cn(
        'planning-mono inline-flex items-center gap-0.5 rounded px-1 py-0.5',
        'text-[9px] font-medium leading-none transition-opacity',
        'opacity-50 hover:opacity-100',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
      )}
      style={{ color }}
      aria-label={`Add ${kind} to context`}
      data-testid={`add-context-btn-${kind}`}
    >
      <PlusCircle size={8} aria-hidden />
      Add
    </button>
  );
}

// ── Context section ───────────────────────────────────────────────────────────

function ContextSection({
  kind,
  items,
  onRemove,
  onAdd,
}: {
  kind: ContextTrayItem['kind'];
  items: ContextTrayItem[];
  onRemove: (id: string) => void;
  onAdd: (item: ContextTrayItem) => void;
}) {
  const color = KIND_COLOR[kind];
  const isEmpty = items.length === 0;

  return (
    <div className="space-y-1">
      {/* Section header row */}
      <div className="flex items-center gap-1.5">
        <span
          className="planning-mono text-[9px] uppercase tracking-wider"
          style={{ color: 'var(--ink-4)' }}
        >
          {KIND_LABEL[kind]}
        </span>
        <span
          className="planning-mono text-[9px] tabular-nums"
          style={{ color: 'var(--ink-4)' }}
          aria-label={`${items.length} item${items.length === 1 ? '' : 's'}`}
        >
          {items.length > 0 ? `(${items.length})` : ''}
        </span>
        <span className="ml-auto">
          <AddContextButton kind={kind} onAdd={onAdd} />
        </span>
      </div>

      {/* Chip list */}
      {!isEmpty && (
        <div
          className="flex flex-wrap gap-1"
          role="list"
          aria-label={`Selected ${KIND_LABEL[kind].toLowerCase()}`}
        >
          {items.map((item) => (
            <RemovableChip key={item.id} item={item} onRemove={onRemove} />
          ))}
        </div>
      )}

      {/* Empty hint with muted border */}
      {isEmpty && (
        <div
          className="planning-mono rounded border border-dashed px-2 py-1.5 text-[9.5px]"
          style={{
            borderColor: `color-mix(in oklab, ${color} 15%, var(--line-1))`,
            color: 'var(--ink-4)',
          }}
        >
          No {KIND_LABEL[kind].toLowerCase()} selected
        </div>
      )}
    </div>
  );
}

// ── Props ──────────────────────────────────────────────────────────────────────

export interface PlanningPromptContextTrayProps {
  /** Controlled: external items list. Use with onSelectionChange for lift. */
  items?: ContextTrayItem[];
  /** Called whenever the selection changes. Receives derived PromptContextSelection. */
  onSelectionChange?: (selection: PromptContextSelection, items: ContextTrayItem[]) => void;
  /** Optional pre-seed: items to initialize the uncontrolled state with. */
  defaultItems?: ContextTrayItem[];
  /**
   * Called when a session card is dropped onto the tray from an external
   * drag source (e.g. PlanningAgentSessionBoard). The parent may use this
   * to update its own trayItems state if operating in controlled mode.
   */
  onExternalDrop?: (item: ContextTrayItem) => void;
  className?: string;
}

// ── Main component ────────────────────────────────────────────────────────────

// ── Session card drag payload shape (mirrors PlanningAgentSessionBoard.tsx) ─────

interface SessionCardDragPayload {
  sessionId: string;
  agentName: string | null;
  transcriptHref?: string | null;
  correlation?: {
    featureId?: string;
    featureName?: string;
    phaseNumber?: number;
    taskId?: string;
  } | null;
}

export function PlanningPromptContextTray({
  items: controlledItems,
  onSelectionChange,
  defaultItems = [],
  onExternalDrop,
  className,
}: PlanningPromptContextTrayProps): JSX.Element {
  const [internalItems, setInternalItems] = useState<ContextTrayItem[]>(defaultItems);

  const isControlled = controlledItems !== undefined;
  const items = isControlled ? controlledItems : internalItems;

  // Drop zone visual state
  const [isDragOver, setIsDragOver] = useState(false);
  // Track drag-enter depth to handle nested element transitions correctly
  const dragDepthRef = useRef(0);

  const updateItems = useCallback(
    (next: ContextTrayItem[]) => {
      if (!isControlled) setInternalItems(next);
      onSelectionChange?.(buildSelection(next), next);
    },
    [isControlled, onSelectionChange],
  );

  const handleRemove = useCallback(
    (id: string) => {
      updateItems(items.filter((item) => item.id !== id));
    },
    [items, updateItems],
  );

  const handleAdd = useCallback(
    (item: ContextTrayItem, method: 'manual' | 'drag' = 'manual') => {
      // Deduplicate by id within same kind
      if (items.some((i) => i.id === item.id && i.kind === item.kind)) return;
      const nextItems = [...items, item];
      updateItems(nextItems);
      trackContextAdded({ kind: item.kind, method, trayCountAfter: nextItems.length });
    },
    [items, updateItems],
  );

  const handleClearAll = useCallback(() => {
    updateItems([]);
  }, [updateItems]);

  // ── Drag-and-drop handlers ────────────────────────────────────────────────

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    if (e.dataTransfer.types.includes('application/x-ccdash-session-card')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }
  }, []);

  const handleDragEnter = useCallback((e: DragEvent<HTMLDivElement>) => {
    if (e.dataTransfer.types.includes('application/x-ccdash-session-card')) {
      dragDepthRef.current += 1;
      setIsDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((_e: DragEvent<HTMLDivElement>) => {
    dragDepthRef.current -= 1;
    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setIsDragOver(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      dragDepthRef.current = 0;
      setIsDragOver(false);

      const raw = e.dataTransfer.getData('application/x-ccdash-session-card');
      if (!raw) return;

      let payload: SessionCardDragPayload;
      try {
        payload = JSON.parse(raw) as SessionCardDragPayload;
      } catch {
        return;
      }

      const sessionItem: ContextTrayItem = {
        id: payload.sessionId,
        label: payload.agentName ?? payload.sessionId.slice(-10),
        kind: 'session',
        subtitle: payload.correlation?.featureName ?? payload.correlation?.featureId,
      };

      // Add session chip (dedup handled inside handleAdd)
      handleAdd(sessionItem, 'drag');
      onExternalDrop?.(sessionItem);

      // Also add transcript chip if available
      if (payload.transcriptHref) {
        const transcriptItem: ContextTrayItem = {
          id: payload.transcriptHref,
          label: `transcript:${payload.sessionId.slice(-8)}`,
          kind: 'transcript',
          subtitle: payload.sessionId,
        };
        handleAdd(transcriptItem, 'drag');
        onExternalDrop?.(transcriptItem);
      }
    },
    [handleAdd, onExternalDrop],
  );

  const totalCount = items.length;

  return (
    <div
      className={cn(
        'rounded-[var(--radius)] border bg-[color:var(--bg-1)]',
        'transition-[border-color,box-shadow,background-color] duration-150',
        isDragOver
          ? [
              'border-[color:var(--brand)]',
              'shadow-[0_0_0_2px_color-mix(in_oklab,var(--brand)_25%,transparent),inset_0_0_12px_color-mix(in_oklab,var(--brand)_6%,transparent)]',
              'bg-[color:color-mix(in_oklab,var(--brand)_3%,var(--bg-1))]',
            ]
          : 'border-[color:var(--line-1)]',
        className,
      )}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      data-testid="prompt-context-tray"
      aria-label="Context tray — drop session cards here to add them"
    >
      {/* ── Tray header ───────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between gap-2 px-3 py-2"
        style={{ borderBottom: '1px solid var(--line-1, #2d3347)' }}
      >
        <div className="flex items-center gap-1.5">
          <LayoutList
            size={11}
            style={{ color: 'var(--ink-3)' }}
            aria-hidden
          />
          <span
            className="planning-mono text-[10.5px] font-medium"
            style={{ color: 'var(--ink-2)' }}
          >
            Context Selection
          </span>
          {totalCount > 0 && (
            <span
              className="planning-mono inline-flex items-center rounded-full px-1.5 py-0.5 text-[8.5px] font-semibold leading-none"
              style={{
                background: 'color-mix(in oklab, var(--brand) 15%, transparent)',
                color: 'var(--brand)',
              }}
              aria-label={`${totalCount} item${totalCount === 1 ? '' : 's'} selected`}
            >
              {totalCount}
            </span>
          )}
        </div>

        {totalCount > 0 && (
          <button
            type="button"
            onClick={handleClearAll}
            className={cn(
              'planning-mono inline-flex items-center gap-1 rounded px-1.5 py-0.5',
              'text-[9px] text-[color:var(--ink-4)] transition-colors',
              'hover:text-[color:var(--ink-2)]',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
            )}
            aria-label="Clear all context selections"
            data-testid="context-tray-clear-all"
          >
            <X size={8} aria-hidden />
            Clear all
          </button>
        )}
      </div>

      {/* ── Sections ──────────────────────────────────────────────────── */}
      <div className="space-y-3 px-3 py-3">
        {SECTION_ORDER.map((kind) => (
          <ContextSection
            key={kind}
            kind={kind}
            items={items.filter((i) => i.kind === kind)}
            onRemove={handleRemove}
            onAdd={handleAdd}
          />
        ))}
      </div>

      {/* ── Drop zone hint ────────────────────────────────────────────── */}
      {isDragOver && (
        <div
          className="mx-3 mb-3 rounded border-2 border-dashed flex items-center justify-center py-3"
          style={{
            borderColor: 'var(--brand)',
            background: 'color-mix(in oklab, var(--brand) 8%, transparent)',
          }}
          aria-live="polite"
          aria-label="Drop to add session to context"
        >
          <span
            className="planning-mono text-[9.5px] font-medium"
            style={{ color: 'var(--brand)' }}
          >
            Drop to add session context
          </span>
        </div>
      )}

      {/* ── Footer hint ───────────────────────────────────────────────── */}
      {totalCount === 0 && !isDragOver && (
        <div
          className="px-3 pb-2.5"
        >
          <p
            className="planning-mono text-[9px] leading-relaxed"
            style={{ color: 'var(--ink-4)' }}
          >
            Add sessions, phases, tasks, or artifacts to refine the prompt context.
            Changes trigger a live preview refresh. You can also drag session cards from the board.
          </p>
        </div>
      )}
    </div>
  );
}
