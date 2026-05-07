/**
 * TestStatusTab — execution-owned tab component (P4-005)
 *
 * Renders test health summary for a feature and provides navigation to the
 * full execution workbench (`/execution?feature=...&tab=test-status`).
 *
 * Domain: execution
 * Tab: test-status
 *
 * Constraints:
 * - Does NOT own execution orchestration state
 * - Does NOT modify useFeatureModalExecution or FeatureModalTestStatus
 * - Conditionally hidden when totalTests <= 0 (caller must gate on this)
 * - Navigation links to /execution without owning the run lifecycle
 */

import React from 'react';

import type { FeatureTestHealth } from '../../types';
import type { SectionHandle } from '../../services/useFeatureModalData';
import { FeatureModalTestStatus } from '../TestVisualizer/FeatureModalTestStatus';
import { TabStateView } from './TabStateView';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface TestStatusTabProps {
  /** Stable feature ID used for navigation and display. */
  featureId: string;
  /**
   * Test health payload. When null / undefined or totalTests === 0 the tab
   * renders nothing (caller should have filtered the tab from the tab bar).
   */
  health: FeatureTestHealth | null | undefined;
  /** Section handle from useFeatureModalExecution()['test-status']. */
  section: SectionHandle;
  /**
   * Called after navigation is triggered — typically closes the modal so
   * the execution workbench has the full viewport.
   */
  onClose: () => void;
  /** react-router navigate function (or compatible). */
  navigate: (path: string) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const TestStatusTab: React.FC<TestStatusTabProps> = ({
  featureId,
  health,
  section,
  onClose,
  navigate,
}) => {
  // Guard: if there is no test health data (or all counts are zero) render
  // nothing. The caller is responsible for hiding the tab button, but we also
  // guard here so the component is safe to mount regardless.
  if (!health || health.totalTests <= 0) {
    return null;
  }

  const handleNavigateToExecution = () => {
    onClose();
    navigate(`/execution?feature=${encodeURIComponent(featureId)}&tab=test-status`);
  };

  return (
    <TabStateView
      status={section.status}
      error={section.error?.message}
      onRetry={section.retry}
      isEmpty={false}
      staleLabel="Refreshing test status…"
    >
      <FeatureModalTestStatus
        featureId={featureId}
        health={health}
        onNavigateToExecution={handleNavigateToExecution}
      />
    </TabStateView>
  );
};
