/**
 * PlanningTabGroup — thin composition layer for planning-owned modal tabs.
 *
 * This component is OPTIONAL. Its purpose is to simplify the FeatureDetailShell's
 * renderTabContent render prop at the call site: instead of the caller writing
 * three separate conditional branches for 'phases' | 'docs' | 'relations',
 * it can pass a single <PlanningTabGroup> element.
 *
 * Usage in renderTabContent:
 *
 *   renderTabContent={(activeTab) => (
 *     <PlanningTabGroup
 *       activeTab={activeTab}
 *       featureId={featureId}
 *       planningStore={planningStore}
 *       // ... domain data props
 *     />
 *   )}
 *
 * The component returns null for any tab that is not planning-owned, so it is
 * safe to compose with other domain render-prop fragments.
 *
 * PlanningTabGroup does NOT call handle.load(). Tab activation loading is the
 * caller's responsibility (the tab-activation effect in the ProjectBoard
 * FeatureModal integration, P4-006).
 */

import React from 'react';

import { PhasesTab, type PhasesTabProps } from './PhasesTab';
import { DocsTab, type DocsTabProps } from './DocsTab';
import { RelationsTab, type RelationsTabProps } from './RelationsTab';
import type { ModalTabId } from '../../services/useFeatureModalCore';
import type { FeatureModalPlanningStore } from '../../services/useFeatureModalPlanning';

// ── Prop types ────────────────────────────────────────────────────────────────

/**
 * Props for PlanningTabGroup.
 *
 * The planning store is passed directly rather than calling useFeatureModalPlanning()
 * internally, so the parent retains full control over cache lifecycle, prefetch,
 * and markStale — and so this component can be tested without a real hook.
 *
 * Domain data props (phases, linkedDocs, etc.) are passed through unchanged
 * to their respective tab components.
 */
export interface PlanningTabGroupProps {
  /** Currently active tab from FeatureDetailShell. */
  activeTab: ModalTabId;

  /** Planning store from useFeatureModalPlanning(featureId). */
  planningStore: FeatureModalPlanningStore;

  // ── PhasesTab props (forwarded) ────────────────────────────────────────────
  phasesProps: Omit<PhasesTabProps, 'handle'>;

  // ── DocsTab props (forwarded) ──────────────────────────────────────────────
  docsProps: Omit<DocsTabProps, 'handle'>;

  // ── RelationsTab props (forwarded) ────────────────────────────────────────
  relationsProps: Omit<RelationsTabProps, 'handle'>;
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * PlanningTabGroup — composition layer that routes planning-owned tab IDs
 * to their respective domain components.
 *
 * Returns null for any non-planning tab ID so the component is safe to use
 * inside a catch-all renderTabContent render prop.
 */
export const PlanningTabGroup: React.FC<PlanningTabGroupProps> = ({
  activeTab,
  planningStore,
  phasesProps,
  docsProps,
  relationsProps,
}) => {
  switch (activeTab) {
    case 'phases':
      return <PhasesTab handle={planningStore.phases} {...phasesProps} />;

    case 'docs':
      return <DocsTab handle={planningStore.docs} {...docsProps} />;

    case 'relations':
      return <RelationsTab handle={planningStore.relations} {...relationsProps} />;

    default:
      // Not a planning-owned tab — return null so other domain fragments can render.
      return null;
  }
};

export default PlanningTabGroup;
