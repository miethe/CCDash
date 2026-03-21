import React from 'react';
import { ExternalLink } from 'lucide-react';

import { FeatureTestHealth } from '../../types';
import { HealthGauge } from './HealthGauge';
import { HealthSummaryBar } from './HealthSummaryBar';

interface FeatureModalTestStatusProps {
  featureId: string;
  health: FeatureTestHealth;
  onNavigateToExecution: () => void;
}

export const FeatureModalTestStatus: React.FC<FeatureModalTestStatusProps> = ({
  featureId,
  health,
  onNavigateToExecution,
}) => (
  <div className="space-y-4">
    <div className="flex items-center gap-4">
      <HealthGauge passRate={health.passRate} integrityScore={health.integrityScore} size="md" />
      <div className="flex-1">
        <HealthSummaryBar
          passed={health.passed}
          failed={health.failed}
          skipped={health.skipped}
          total={health.totalTests}
        />
      </div>
    </div>

    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2 text-xs text-muted-foreground">
      <p className="font-mono text-muted-foreground">{featureId}</p>
      <p className="mt-1">
        Last run: {health.lastRunAt ? new Date(health.lastRunAt).toLocaleString() : 'No run yet'}
      </p>
    </div>

    {health.openSignals > 0 && (
      <p className="text-sm text-amber-300">
        {health.openSignals} integrity alert{health.openSignals > 1 ? 's' : ''} detected.
      </p>
    )}

    <button
      type="button"
      onClick={onNavigateToExecution}
      className="inline-flex items-center gap-1 text-sm text-indigo-300 hover:text-indigo-200"
    >
      View full test status <ExternalLink size={12} />
    </button>
  </div>
);

export type { FeatureModalTestStatusProps };
