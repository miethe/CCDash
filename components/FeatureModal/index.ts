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
