// services/planningTelemetry.ts — PASB-503: Planning session board telemetry
//
// Lightweight, typed wrappers over the base `emitTelemetry` helper.
//
// Design constraints:
//   - NEVER include full prompt text, transcript content, file contents, or any
//     user-generated text beyond IDs and counts.
//   - Zero runtime cost when debug mode is off (inherited from emitTelemetry).
//   - Each exported function is a single-call, strongly-typed event emitter.
//   - The event-name scheme is "planning_board.<verb>" for consistency.
//
// Wire-up summary:
//   PlanningAgentSessionBoard  → trackBoardOpened, trackGroupingChanged,
//                                trackCardOpened, trackTranscriptLinkClicked,
//                                trackReducedMotionFallback
//   PlanningNextRunPreview     → trackPromptCopied
//   PlanningPromptContextTray  → trackContextAdded

import { emitTelemetry } from '@/services/telemetry';
import type { PlanningBoardGroupingMode } from '@/types';

// ── Shared grouping-mode type ─────────────────────────────────────────────────

export type { PlanningBoardGroupingMode };

// ── Event: board opened ───────────────────────────────────────────────────────

export interface BoardOpenedProperties {
  /** The active project ID at mount time. */
  projectId: string | null;
  /** Grouping mode read from the URL at mount time. */
  groupingMode: PlanningBoardGroupingMode;
}

/**
 * Emitted once when PlanningAgentSessionBoard mounts and initiates its first
 * data fetch. Safe to call before data arrives.
 */
export function trackBoardOpened(props: BoardOpenedProperties): void {
  emitTelemetry('planning_board', 'opened', {
    projectId: props.projectId ?? '',
    groupingMode: props.groupingMode,
  });
}

// ── Event: grouping changed ───────────────────────────────────────────────────

export interface GroupingChangedProperties {
  /** The newly selected grouping mode. */
  nextMode: PlanningBoardGroupingMode;
  /** The previous grouping mode before this change. */
  prevMode: PlanningBoardGroupingMode;
}

/**
 * Emitted when the user switches the grouping mode via the board toolbar.
 */
export function trackGroupingChanged(props: GroupingChangedProperties): void {
  emitTelemetry('planning_board', 'grouping_changed', {
    nextMode: props.nextMode,
    prevMode: props.prevMode,
  });
}

// ── Event: card opened ────────────────────────────────────────────────────────

export interface CardOpenedProperties {
  /** The state of the session when the card was opened. */
  sessionState: string;
  /** Whether the card has a feature correlation. */
  hasFeatureCorrelation: boolean;
  /** Correlation confidence tier, if present ('high' | 'medium' | 'low' | 'unknown'). */
  correlationConfidence: string | null;
  /** Whether the card has any relationship links. */
  hasRelationships: boolean;
  /** Number of relationships on the card. */
  relationshipCount: number;
}

/**
 * Emitted when the user clicks (or keyboard-activates) a session card to open
 * its detail panel. Never includes the session ID or agent name.
 */
export function trackCardOpened(props: CardOpenedProperties): void {
  emitTelemetry('planning_board', 'card_opened', {
    sessionState: props.sessionState,
    hasFeatureCorrelation: props.hasFeatureCorrelation,
    correlationConfidence: props.correlationConfidence ?? '',
    hasRelationships: props.hasRelationships,
    relationshipCount: props.relationshipCount,
  });
}

// ── Event: transcript link clicked ───────────────────────────────────────────

export interface TranscriptLinkClickedProperties {
  /**
   * Where the link was triggered from:
   *   'card'         — action row on the session card itself
   *   'detail_panel' — link inside the PlanningAgentSessionDetailPanel
   */
  source: 'card' | 'detail_panel';
}

/**
 * Emitted when the user clicks the "View session transcript" navigation link
 * from a card's action row or from the detail panel.
 */
export function trackTranscriptLinkClicked(props: TranscriptLinkClickedProperties): void {
  emitTelemetry('planning_board', 'transcript_link_clicked', {
    source: props.source,
  });
}

// ── Event: context added ──────────────────────────────────────────────────────

export interface ContextAddedProperties {
  /**
   * The kind of context item added:
   *   'session' | 'phase' | 'task' | 'artifact' | 'transcript'
   */
  kind: 'session' | 'phase' | 'task' | 'artifact' | 'transcript';
  /**
   * How it was added:
   *   'manual'  — user typed/pasted an ID into the inline input
   *   'drag'    — session card dragged from the board
   */
  method: 'manual' | 'drag';
  /** Total number of items in the tray after adding. */
  trayCountAfter: number;
}

/**
 * Emitted when the user adds a context reference to the prompt tray.
 * Never includes the ID value itself.
 */
export function trackContextAdded(props: ContextAddedProperties): void {
  emitTelemetry('planning_board', 'context_added', {
    kind: props.kind,
    method: props.method,
    trayCountAfter: props.trayCountAfter,
  });
}

// ── Event: prompt copied ─────────────────────────────────────────────────────

export type CopyTarget = 'command' | 'prompt' | 'all';

export interface PromptCopiedProperties {
  /**
   * Which section was copied:
   *   'command' — the CLI command block
   *   'prompt'  — the prompt skeleton block
   *   'all'     — the combined "Copy All" action
   */
  copyTarget: CopyTarget;
  /** The feature ID the preview was generated for. */
  featureId: string;
  /** Phase number the preview was scoped to, if any. */
  phaseNumber: number | null;
  /** Number of context items in the tray at copy time. */
  contextRefCount: number;
}

/**
 * Emitted when the user copies from the PlanningNextRunPreview panel.
 * Never includes the actual prompt or command text.
 */
export function trackPromptCopied(props: PromptCopiedProperties): void {
  emitTelemetry('planning_board', 'prompt_copied', {
    copyTarget: props.copyTarget,
    featureId: props.featureId,
    phaseNumber: props.phaseNumber ?? -1,
    contextRefCount: props.contextRefCount,
  });
}

// ── Event: reduced-motion fallback used ──────────────────────────────────────

/**
 * Emitted once on mount of PlanningAgentSessionBoard when the user's OS
 * preference (`prefers-reduced-motion: reduce`) is active. Useful for
 * understanding what portion of users are on reduced-motion.
 */
export function trackReducedMotionFallback(): void {
  emitTelemetry('planning_board', 'reduced_motion_fallback', {
    mediaQuery: 'prefers-reduced-motion: reduce',
  });
}
