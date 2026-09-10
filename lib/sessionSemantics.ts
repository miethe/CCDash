type CostSource = {
  totalCost?: number | null;
  reportedCostUsd?: number | null;
  recalculatedCostUsd?: number | null;
  displayCostUsd?: number | null;
  costProvenance?: string | null;
  costConfidence?: number | null;
  costMismatchPct?: number | null;
  pricingModelSource?: string | null;
};

type ContextSource = {
  currentContextTokens?: number | null;
  contextWindowSize?: number | null;
  contextUtilizationPct?: number | null;
  contextMeasurementSource?: string | null;
  contextMeasuredAt?: string | null;
};

const toNumber = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const resolveDisplayCost = (source: CostSource | null | undefined): number => {
  const displayCost = Number(source?.displayCostUsd);
  if (Number.isFinite(displayCost)) return displayCost;
  return toNumber(source?.totalCost);
};

export const costProvenanceLabel = (value: string | null | undefined): string => {
  switch ((value || '').trim().toLowerCase()) {
    case 'reported':
      return 'Reported';
    case 'recalculated':
      return 'Recalculated';
    case 'estimated':
      return 'Estimated';
    default:
      return 'Unknown';
  }
};

export const costConfidenceLabel = (value: number | null | undefined): string => {
  const confidence = toNumber(value);
  return `${Math.round(confidence * 100)}% confidence`;
};

export const costSummaryLabel = (source: CostSource | null | undefined): string => {
  const parts = [costProvenanceLabel(source?.costProvenance)];
  const confidence = toNumber(source?.costConfidence);
  if (confidence > 0) parts.push(costConfidenceLabel(confidence));
  if (toNumber(source?.costMismatchPct) > 0) {
    parts.push(`${(toNumber(source?.costMismatchPct) * 100).toFixed(1)}% mismatch`);
  }
  return parts.join(' · ');
};

export const formatContextMeasurementSource = (value: string | null | undefined): string => {
  const normalized = (value || '').trim().toLowerCase();
  if (normalized === 'hook_context_window') return 'Hook snapshot';
  if (normalized === 'transcript_latest_assistant_usage') return 'Transcript fallback';
  return normalized ? normalized.replace(/_/g, ' ') : 'Unavailable';
};

export const hasContextSnapshot = (source: ContextSource | null | undefined): boolean => (
  toNumber(source?.currentContextTokens) > 0 && toNumber(source?.contextWindowSize) > 0
);

/**
 * G1 "first+last pair": display rule for a session's effort tier.
 *
 * `effortTier` is the SessionStart-captured value (the "start"); `effortTierLast`
 * is the freshest value observed at any later UserPromptSubmit (null when none
 * differed from start — see update_effort_tier_last in
 * scripts/hooks/ccdash_capture_session_start.py). Renders "start→last" only when
 * both are present and differ; otherwise renders the single known value, or
 * `null` when there is nothing captured at all (caller renders its own
 * "Not captured" fallback for that case, matching every other launch-capture
 * field's contract).
 */
export const formatEffortTierDisplay = (
  effortTier: string | null | undefined,
  effortTierLast: string | null | undefined,
): string | null => {
  if (!effortTier) return null;
  if (effortTierLast && effortTierLast !== effortTier) {
    return `${effortTier}→${effortTierLast}`;
  }
  return effortTier;
};

/**
 * G1 aggregation rule (read-side counterpart to the API's `_EFFORT_EXPR`):
 * the effective per-session effort tier is `effortTierLast` when present,
 * else `effortTier`. Used wherever a single value (not the start→last display
 * string) is needed, e.g. grouping/filtering by tier.
 */
export const effectiveEffortTier = (
  effortTier: string | null | undefined,
  effortTierLast: string | null | undefined,
): string | null => effortTierLast || effortTier || null;

export const contextSummaryLabel = (source: ContextSource | null | undefined): string => {
  if (!hasContextSnapshot(source)) return 'No current-context snapshot';
  return `${toNumber(source?.currentContextTokens).toLocaleString()} / ${toNumber(source?.contextWindowSize).toLocaleString()} (${toNumber(source?.contextUtilizationPct).toFixed(1)}%)`;
};
