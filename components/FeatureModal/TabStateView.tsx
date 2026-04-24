/**
 * TabStateView — reusable per-tab state rendering primitive for feature modal tabs.
 *
 * Renders visible loading, error-with-retry, stale indicator, empty state, and
 * children (content). The contract mirrors ModalSectionStore status values.
 *
 * Status semantics:
 *   'idle'    — not yet triggered; renders nothing (caller decides when to trigger).
 *   'loading' — first-time fetch in-flight; no cached data. Renders spinner/skeleton.
 *   'success' — data loaded. Renders children; isEmpty check applies here only.
 *   'error'   — fetch failed. Renders red-tinted banner with retry button. Never
 *               renders empty-state (transient failure is NOT valid empty data).
 *   'stale'   — previously loaded data; background refresh in flight. Renders
 *               children plus a muted "refreshing…" indicator.
 *
 * Accessibility:
 *   - Loading/stale region: role="status" (non-assertive live region)
 *   - Error region: role="alert" (assertive live region)
 *   - Retry button: autoFocus so keyboard focus lands on it when error renders
 *
 * Wiring note: P4-010 owns consumer wiring. This component is purely additive.
 */

import React from 'react';
import { AlertTriangle, RefreshCw, Inbox } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

/** Status values align with ModalSectionStore (P4-002). */
export type TabStatus = 'idle' | 'loading' | 'success' | 'error' | 'stale';

export interface TabStateViewProps {
  /** Current section load status. */
  status: TabStatus;
  /** Error message. Only relevant when status === 'error'. */
  error?: string | null;
  /** Called when the user presses the retry button in the error banner. */
  onRetry?: () => void;
  /**
   * Whether the successfully-loaded data set is empty.
   * Only evaluated when status === 'success'. Ignored otherwise — a transient
   * error or in-flight load must never be rendered as empty data.
   */
  isEmpty?: boolean;
  /**
   * Label shown in the empty-state block when isEmpty && status === 'success'.
   * Defaults to "No data available."
   */
  emptyLabel?: string;
  /**
   * Whether a background refresh is in progress (relevant when status === 'stale').
   * Included in the prop surface for forward-compatibility; TabStateView derives
   * the refreshing indicator from status === 'stale' directly.
   */
  isStale?: boolean;
  /** Override text for the stale "refreshing…" marker. */
  staleLabel?: string;
  /** Tab content — rendered when status is 'success' or 'stale'. */
  children?: React.ReactNode;
}

// ── Sub-components ────────────────────────────────────────────────────────────

const LoadingSkeleton: React.FC = () => (
  <div
    role="status"
    aria-label="Loading"
    className="flex flex-col gap-3 py-2"
  >
    <div className="h-3 w-3/4 animate-pulse rounded-md bg-surface-muted" />
    <div className="h-3 w-1/2 animate-pulse rounded-md bg-surface-muted" />
    <div className="h-3 w-5/6 animate-pulse rounded-md bg-surface-muted" />
    <span className="sr-only">Loading…</span>
  </div>
);

const ErrorBanner: React.FC<{ message?: string | null; onRetry?: () => void }> = ({
  message,
  onRetry,
}) => (
  <div
    role="alert"
    className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
  >
    <AlertTriangle size={15} className="mt-0.5 shrink-0" aria-hidden="true" />
    <div className="flex-1 min-w-0">
      <p className="font-medium leading-5">Failed to load</p>
      {message ? (
        <p className="mt-0.5 text-xs leading-4 text-red-400/80">{message}</p>
      ) : null}
    </div>
    {onRetry ? (
      <button
        type="button"
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus
        onClick={onRetry}
        className="shrink-0 rounded-md border border-red-500/30 bg-red-500/15 px-2.5 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/25 hover:text-red-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
        aria-label="Retry loading"
      >
        Retry
      </button>
    ) : null}
  </div>
);

const StaleIndicator: React.FC<{ label?: string }> = ({ label }) => (
  <div
    role="status"
    aria-label={label ?? 'Refreshing'}
    className="flex items-center gap-1.5 py-1 text-[11px] text-muted-foreground/70"
  >
    <RefreshCw size={10} className="animate-spin" aria-hidden="true" />
    <span>{label ?? 'Refreshing…'}</span>
  </div>
);

const EmptyState: React.FC<{ label?: string }> = ({ label }) => (
  <div className="flex flex-col items-center gap-2 py-8 text-center">
    <Inbox size={28} className="text-muted-foreground/40" aria-hidden="true" />
    <p className="text-sm text-muted-foreground">
      {label ?? 'No data available.'}
    </p>
  </div>
);

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * TabStateView wraps a modal tab's content with appropriate loading, error,
 * stale, and empty-state rendering based on the section's load status.
 *
 * @example
 * ```tsx
 * <TabStateView
 *   status={sectionState.status}
 *   error={sectionState.error}
 *   onRetry={() => reload('phases')}
 *   isEmpty={phases.length === 0}
 *   emptyLabel="No phases defined for this feature."
 *   staleLabel="Refreshing phases…"
 * >
 *   <PhaseList phases={phases} />
 * </TabStateView>
 * ```
 */
export const TabStateView: React.FC<TabStateViewProps> = ({
  status,
  error,
  onRetry,
  isEmpty = false,
  emptyLabel,
  isStale: _isStale,
  staleLabel,
  children,
}) => {
  // 'idle' — nothing rendered; caller decides when to trigger the load.
  if (status === 'idle') {
    return null;
  }

  // 'loading' — first-time fetch; no content to show yet.
  if (status === 'loading') {
    return <LoadingSkeleton />;
  }

  // 'error' — show banner with retry; never fall through to empty state.
  if (status === 'error') {
    return <ErrorBanner message={error} onRetry={onRetry} />;
  }

  // 'success' or 'stale' — data is present (or was present).
  return (
    <>
      {status === 'stale' ? <StaleIndicator label={staleLabel} /> : null}
      {/* Empty state only after a confirmed successful load with zero items. */}
      {isEmpty && status === 'success' ? (
        <EmptyState label={emptyLabel} />
      ) : (
        children
      )}
    </>
  );
};

export default TabStateView;
