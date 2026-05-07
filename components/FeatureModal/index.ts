/**
 * FeatureModal subtree barrel export.
 *
 * Import from this file in all consumers outside the FeatureModal/ directory.
 * Domain-specific tab components (P4-003 through P4-005) are NOT re-exported
 * here — they are imported directly by their respective domain owners.
 */

export { FeatureDetailShell } from './FeatureDetailShell';

export { TabStateView } from './TabStateView';
export type { TabStateViewProps, TabStatus } from './TabStateView';

export {
  TAB_OWNERSHIP,
} from './types';
export type {
  ModalTabId,
  ModalTabDomain,
  TabOwnershipRecord,
  ShellTabConfig,
  ShellSectionState,
  ShellSectionStateMap,
  FeatureDetailShellProps,
} from './types';

// ── Shared-shell overview tab (P4-006) ────────────────────────────────────────

export { OverviewTab } from './OverviewTab';
export type {
  OverviewTabProps,
  OverviewTabMetrics,
  OverviewTabDelivery,
  OverviewTabFamilyData,
  OverviewTabDateSignals,
} from './OverviewTab';

// ── Execution-domain components (P4-005) ──────────────────────────────────────

export { TestStatusTab } from './TestStatusTab';
export type { TestStatusTabProps } from './TestStatusTab';

export { ExecutionGateCard } from './ExecutionGateCard';
export type { ExecutionGateCardProps } from './ExecutionGateCard';

// ── Forensics-domain components (P4-004) ──────────────────────────────────────

export { SessionsTab } from './SessionsTab';
export type { SessionsTabProps, FeatureSessionLink } from './SessionsTab';

export { HistoryTab } from './HistoryTab';
export type { HistoryTabProps } from './HistoryTab';
