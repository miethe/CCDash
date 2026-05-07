/**
 * ExecutionGateCard — execution-owned sub-component (P4-005)
 *
 * Renders the execution gate state badge, reason text, waiting-on info, and
 * next actionable item. Composed into OverviewTab.tsx by the shared-shell
 * composition layer — it is NOT modal header chrome.
 *
 * Domain: execution
 * Placement: overview tab body (xl:col 1 of the 3-column grid below quality signals)
 *
 * Per Phase 4 Decision 3:
 *   - This card extracts from ProjectBoard.tsx L3184-3198.
 *   - The Begin Work CTA button stays in the shared-shell header (not here).
 *   - The card is imported into OverviewTab.tsx by reference.
 *
 * Constraints:
 * - Does NOT own execution orchestration or navigation state
 * - Does NOT import from ProjectBoard.tsx (helpers are self-contained below)
 * - Fallbacks required for every optional field (resilience-by-default)
 */

import React from 'react';
import { Play } from 'lucide-react';

import type {
  ExecutionGateState,
  ExecutionGateStateValue,
  FeatureFamilyPosition,
} from '../../types';

// ── Local style/label helpers (mirrors ProjectBoard.tsx constants) ─────────────
// Self-contained so this component has no dependency on ProjectBoard internals.

const EXECUTION_GATE_LABELS: Record<ExecutionGateStateValue, string> = {
  ready: 'Ready',
  blocked_dependency: 'Blocked by dependency',
  waiting_on_family_predecessor: 'Waiting on family predecessor',
  unknown_dependency_state: 'Dependency state unknown',
};

const EXECUTION_GATE_STYLES: Record<ExecutionGateStateValue, string> = {
  ready: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  blocked_dependency: 'bg-rose-500/10 text-rose-200 border-rose-500/30',
  waiting_on_family_predecessor: 'bg-amber-500/10 text-amber-200 border-amber-500/30',
  unknown_dependency_state: 'bg-slate-500/10 text-slate-200 border-slate-500/30',
};

const FALLBACK_STYLE = EXECUTION_GATE_STYLES.unknown_dependency_state;

function getGateLabel(gate?: ExecutionGateStateValue | string | null): string {
  if (!gate) return 'Unknown';
  return EXECUTION_GATE_LABELS[gate as ExecutionGateStateValue] ?? gate;
}

function getGateStyle(gate?: ExecutionGateStateValue | string | null): string {
  if (!gate) return FALLBACK_STYLE;
  return EXECUTION_GATE_STYLES[gate as ExecutionGateStateValue] ?? FALLBACK_STYLE;
}

// ── Local field primitive ─────────────────────────────────────────────────────
// Mirrors FeatureField in ProjectBoard.tsx without importing it.

interface GateFieldProps {
  label: string;
  value?: React.ReactNode;
  mono?: boolean;
}

const GateField: React.FC<GateFieldProps> = ({ label, value, mono = false }) => (
  <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2">
    <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
    <div
      className={`mt-1 min-h-[18px] text-sm text-panel-foreground ${mono ? 'font-mono text-xs' : ''}`}
    >
      {value ?? '-'}
    </div>
  </div>
);

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ExecutionGateCardProps {
  /**
   * Execution gate state from the feature's planning/execution metadata.
   * When null/undefined the card renders a neutral "unknown" state rather
   * than nothing — the card is always visible in the overview layout.
   */
  executionGate?: ExecutionGateState | null;
  /**
   * Dependency block reason override (from FeatureDependencyState).
   * Used as a fallback when executionGate.reason is absent.
   */
  blockingReason?: string | null;
  /**
   * Family position for resolving the next-item label.
   * Fallback: nextFamilyItemName, then '-'.
   */
  familyPosition?: FeatureFamilyPosition | null;
  /**
   * Display name of the next recommended family item (resolved by caller).
   * Used when familyPosition.nextItemLabel is absent.
   */
  nextFamilyItemName?: string | null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const ExecutionGateCard: React.FC<ExecutionGateCardProps> = ({
  executionGate,
  blockingReason,
  familyPosition,
  nextFamilyItemName,
}) => {
  const gateState = executionGate?.state ?? null;
  const reason =
    executionGate?.reason ||
    blockingReason ||
    'No gate reason available.';

  const nextItemLabel =
    familyPosition?.nextItemLabel ||
    nextFamilyItemName ||
    '-';

  return (
    <div className="rounded-xl border border-panel-border bg-panel">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-panel-border px-4 py-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-panel-border bg-surface-muted text-muted-foreground">
            <Play size={15} />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-panel-foreground">Execution Gate</h3>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{reason}</p>
          </div>
        </div>
        <div className="shrink-0">
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${getGateStyle(gateState)}`}
          >
            {getGateLabel(gateState)}
          </span>
        </div>
      </div>

      {/* Fields */}
      <div className="grid grid-cols-1 gap-2 p-3 sm:grid-cols-3 xl:grid-cols-1">
        <GateField
          label="Ready"
          value={executionGate?.isReady ? 'Yes' : 'No'}
        />
        <GateField
          label="Waiting on family"
          value={executionGate?.waitingOnFamilyPredecessor ? 'Yes' : 'No'}
        />
        <GateField
          label="Next item"
          value={nextItemLabel}
          mono
        />
      </div>
    </div>
  );
};
