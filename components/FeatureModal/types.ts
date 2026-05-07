/**
 * Shared types for the FeatureModal subtree.
 *
 * All types here are CCDash-local — they reference CCDash-specific identifiers
 * (ModalTabId, SectionHandle) and are not candidates for promotion to
 * @miethe/ui/primitives at this time.
 *
 * Promotion decision (P4-001):
 *   Audited BaseArtifactModal, TabNavigation, VerticalTabNavigation, and Tabs
 *   in the @miethe/ui package. @miethe/ui's BaseArtifactModal is a generic
 *   artifact-modal primitive decoupled from any domain tab-state management.
 *   FeatureDetailShell couples to CCDash's ModalSectionStore
 *   (SectionHandle.status / load / retry / invalidate) and to the
 *   ModalTabDomain ownership model — both purely CCDash concerns.
 *   No concrete second consumer was found. Shell remains CCDash-local.
 */

import type React from 'react';
import type { ModalTabId, SectionHandle } from '../../services/useFeatureModalData';

// Re-export ModalTabId so that types.ts consumers don't need to reach into
// useFeatureModalData directly. The canonical definition stays in useFeatureModalData.
export type { ModalTabId } from '../../services/useFeatureModalData';

// ── Domain ownership ──────────────────────────────────────────────────────────

/**
 * Domain that owns the content of a feature modal tab.
 *
 *   'shared-shell'  — chrome owned by the shell itself (metric tiles, CTA header)
 *   'planning'      — planning-domain tabs (phases, docs, relations, overview editorial)
 *   'forensics'     — forensics-domain tabs (sessions, history)
 *   'execution'     — execution-domain tabs (test-status, execution gate)
 */
export type ModalTabDomain = 'shared-shell' | 'planning' | 'forensics' | 'execution';

/**
 * Single source of truth mapping each ModalTabId to its owning domain.
 * Derived from the Phase 4 ownership manifest at
 * .claude/worknotes/planning-forensics-boundary-extraction-v1/phase-4-tab-ownership.md
 */
export type TabOwnershipRecord = Record<ModalTabId, ModalTabDomain>;

export const TAB_OWNERSHIP: TabOwnershipRecord = {
  // overview: shared-shell for metric tiles + planning for editorial sub-sections.
  // We classify the whole tab as 'shared-shell' here because the shell
  // owns the data-loading entry point (FeatureModalOverviewDTO). The planning
  // sub-sections are composed into OverviewTab.tsx by import.
  overview: 'shared-shell',
  phases: 'planning',
  docs: 'planning',
  relations: 'planning',
  sessions: 'forensics',
  'test-status': 'execution',
  history: 'forensics',
} as const;

// ── Tab configuration ─────────────────────────────────────────────────────────

/**
 * Configuration record for a single tab in FeatureDetailShell.
 *
 * The shell renders the tab button and delegates content rendering to
 * the `renderContent` render prop. The shell owns no product-specific
 * tab content.
 */
export interface ShellTabConfig {
  /** Matches ModalTabId; used as the tab button key and aria controls. */
  id: ModalTabId;
  /** Human-readable label displayed in the tab bar. */
  label: string;
  /** Optional icon component rendered before the label. */
  icon?: React.ComponentType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  /** Whether this tab is visible in the tab bar. Defaults to true. */
  enabled?: boolean;
  /** Domain that owns the content of this tab. Used for documentation/debugging. */
  domain: ModalTabDomain;
}

// ── Section state shape expected by FeatureDetailShell ────────────────────────

/**
 * Minimal per-tab section state consumed by FeatureDetailShell.
 * This is a structural alias over SectionHandle; the shell does not depend
 * on the full SectionHandle implementation — it only needs status/error/retry.
 */
export type ShellSectionState = Pick<SectionHandle, 'status' | 'error' | 'retry'>;

/**
 * Map from ModalTabId to per-section state, as consumed by FeatureDetailShell.
 */
export type ShellSectionStateMap = Record<ModalTabId, ShellSectionState>;

// ── FeatureDetailShell props ──────────────────────────────────────────────────

/**
 * Props for the FeatureDetailShell component.
 *
 * The shell manages the tab frame, active tab state, close behavior, and
 * per-tab state rendering (idle / loading / error / stale / success via
 * TabStateView). It does NOT own product-specific tab content.
 *
 * Product-specific content is provided via the `renderTabContent` render prop,
 * which is called with the currently active tab's ID. Domain owners (P4-003,
 * P4-004, P4-005) implement the content for their tabs and compose them in
 * the render prop.
 */
export interface FeatureDetailShellProps {
  // ── Identity ────────────────────────────────────────────────────────────────

  /** Unique, stable feature ID. Used for aria-labelledby and modal title IDs. */
  featureId: string;
  /** Feature display name. Rendered in the modal header. */
  featureName: string;

  // ── Status display ──────────────────────────────────────────────────────────

  /**
   * Slot for the feature status badge (e.g. StatusDropdown).
   * Shell renders this in the header below the feature ID badge.
   */
  statusBadge?: React.ReactNode;

  /**
   * Slot for additional header badges (e.g. done-with-deferrals badge).
   * Rendered inline with the feature ID and status badge.
   */
  headerBadges?: React.ReactNode;

  /**
   * Slot for the progress bar row rendered below the feature name in the header.
   */
  progressRow?: React.ReactNode;

  // ── Tab configuration ───────────────────────────────────────────────────────

  /**
   * Ordered list of tab configurations. The shell renders tab buttons in this
   * order, filtering out disabled tabs (enabled === false).
   */
  tabs: ShellTabConfig[];

  /**
   * The initially-active tab. Defaults to 'overview'.
   * The shell manages active tab state internally after mount.
   */
  initialTab?: ModalTabId;

  /**
   * Called when the active tab changes. Allows callers to sync URL state.
   * The shell does not read from URL — that is the caller's responsibility.
   */
  onTabChange?: (tab: ModalTabId) => void;

  // ── Section state ───────────────────────────────────────────────────────────

  /**
   * Per-tab section states from useFeatureModalData (or compatible shape).
   * The shell uses these to drive TabStateView for each tab's loading state.
   *
   * The shell does NOT call load() — that is the caller's responsibility
   * (the tab-activation effect in ProjectBoardFeatureModal / P4-006).
   */
  sectionStates: ShellSectionStateMap;

  // ── Content render prop ─────────────────────────────────────────────────────

  /**
   * Render prop for tab content. Called with the currently active tab ID.
   * The shell wraps the result in TabStateView with the section's status.
   *
   * Return null or undefined to render only the TabStateView state layer
   * (useful for tabs still being extracted, where content remains inline).
   */
  renderTabContent: (activeTab: ModalTabId) => React.ReactNode;

  // ── Header action slots ─────────────────────────────────────────────────────

  /**
   * Slot for the Begin Work CTA button in the header.
   * Per Decision 3 in the ownership manifest: Begin Work stays in shared-shell
   * header chrome. The caller provides the button with its handler attached.
   */
  beginWorkAction?: React.ReactNode;

  /**
   * Slot for additional header actions rendered alongside Begin Work and Expand.
   * Inserted before the expand and close buttons.
   */
  extraHeaderActions?: React.ReactNode;

  /**
   * Handler for the Expand button (navigate to full planning detail page).
   * If not provided, the Expand button is not rendered.
   */
  onExpand?: () => void;

  // ── Close ───────────────────────────────────────────────────────────────────

  /**
   * Called when the modal is dismissed (close button, backdrop click, Escape).
   */
  onClose: () => void;
}
