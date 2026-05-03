export interface TokenMetricSource {
  tokensIn?: number | null;
  tokensOut?: number | null;
  tokenInput?: number | null;
  tokenOutput?: number | null;
  modelIOTokens?: number | null;
  cacheInputTokens?: number | null;
  observedTokens?: number | null;
  toolReportedTokens?: number | null;
  cacheShare?: number | null;
  outputShare?: number | null;
}

export interface WorkloadResolutionOptions {
  allowToolFallback?: boolean;
  hasLinkedSubthreads?: boolean;
}

export type WorkloadSourceKind = 'observed' | 'derived' | 'toolReported' | 'modelIo' | 'none';

export interface ResolvedTokenMetrics {
  tokenInput: number;
  tokenOutput: number;
  modelIOTokens: number;
  cacheInputTokens: number;
  observedTokens: number;
  toolReportedTokens: number;
  workloadTokens: number;
  workloadSource: WorkloadSourceKind;
  cacheShare: number;
  outputShare: number;
  usedToolFallback: boolean;
}

const toNumber = (value: unknown): number => {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const resolveTokenMetrics = (
  source: TokenMetricSource | null | undefined,
  options: WorkloadResolutionOptions = {},
): ResolvedTokenMetrics => {
  const tokenInput = toNumber(source?.tokensIn ?? source?.tokenInput);
  const tokenOutput = toNumber(source?.tokensOut ?? source?.tokenOutput);
  const modelIOTokens = toNumber(source?.modelIOTokens) || (tokenInput + tokenOutput);
  const cacheInputTokens = toNumber(source?.cacheInputTokens);
  const observedTokens = toNumber(source?.observedTokens);
  const toolReportedTokens = toNumber(source?.toolReportedTokens);
  const derivedTokens = modelIOTokens + cacheInputTokens;
  const allowToolFallback = options.allowToolFallback !== false;
  const hasLinkedSubthreads = Boolean(options.hasLinkedSubthreads);

  let workloadTokens = 0;
  let workloadSource: WorkloadSourceKind = 'none';

  if (observedTokens > 0) {
    workloadTokens = observedTokens;
    workloadSource = 'observed';
  } else if (derivedTokens > 0) {
    workloadTokens = derivedTokens;
    workloadSource = 'derived';
  } else if (allowToolFallback && !hasLinkedSubthreads && toolReportedTokens > 0) {
    workloadTokens = toolReportedTokens;
    workloadSource = 'toolReported';
  } else if (modelIOTokens > 0) {
    workloadTokens = modelIOTokens;
    workloadSource = 'modelIo';
  }

  const explicitCacheShare = toNumber(source?.cacheShare);
  const explicitOutputShare = toNumber(source?.outputShare);

  return {
    tokenInput,
    tokenOutput,
    modelIOTokens,
    cacheInputTokens,
    observedTokens,
    toolReportedTokens,
    workloadTokens,
    workloadSource,
    cacheShare: explicitCacheShare > 0 ? explicitCacheShare : (workloadTokens > 0 ? cacheInputTokens / workloadTokens : 0),
    outputShare: explicitOutputShare > 0 ? explicitOutputShare : (modelIOTokens > 0 ? tokenOutput / modelIOTokens : 0),
    usedToolFallback: workloadSource === 'toolReported',
  };
};

export const formatTokenCount = (value: number | null | undefined): string =>
  toNumber(value).toLocaleString();

/**
 * Compact token count formatter for inline transcript captions.
 * - Values ≥ 1,000,000 → "1.2M"
 * - Values ≥ 1,000     → "1.2K"
 * - Values < 1,000     → raw integer string
 */
export const formatTokenCountCompact = (value: number | null | undefined): string => {
  const n = toNumber(value);
  if (n >= 1_000_000) {
    return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  }
  if (n >= 1_000) {
    return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  }
  return `${Math.floor(n)}`;
};

export const formatPercent = (value: number | null | undefined, digits = 1): string =>
  `${(toNumber(value) * 100).toFixed(digits)}%`;
