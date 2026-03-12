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

export const contextSummaryLabel = (source: ContextSource | null | undefined): string => {
  if (!hasContextSnapshot(source)) return 'No current-context snapshot';
  return `${toNumber(source?.currentContextTokens).toLocaleString()} / ${toNumber(source?.contextWindowSize).toLocaleString()} (${toNumber(source?.contextUtilizationPct).toFixed(1)}%)`;
};
