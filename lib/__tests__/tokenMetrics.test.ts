import { describe, expect, it } from 'vitest';

import { resolveTokenMetrics } from '../tokenMetrics';

describe('resolveTokenMetrics', () => {
  it('prefers observed tokens when present', () => {
    const metrics = resolveTokenMetrics({
      tokensIn: 10,
      tokensOut: 20,
      cacheInputTokens: 40,
      observedTokens: 70,
      toolReportedTokens: 500,
    });

    expect(metrics.workloadTokens).toBe(70);
    expect(metrics.workloadSource).toBe('observed');
    expect(metrics.usedToolFallback).toBe(false);
  });

  it('uses tool-reported totals only as fallback when there are no linked subthreads', () => {
    const metrics = resolveTokenMetrics(
      {
        toolReportedTokens: 300,
      },
      { hasLinkedSubthreads: false },
    );

    expect(metrics.workloadTokens).toBe(300);
    expect(metrics.workloadSource).toBe('toolReported');
    expect(metrics.usedToolFallback).toBe(true);
  });

  it('does not use tool-reported totals when linked subthreads exist', () => {
    const metrics = resolveTokenMetrics(
      {
        modelIOTokens: 30,
        toolReportedTokens: 300,
      },
      { hasLinkedSubthreads: true },
    );

    expect(metrics.workloadTokens).toBe(30);
    expect(metrics.workloadSource).toBe('derived');
    expect(metrics.usedToolFallback).toBe(false);
  });
});
