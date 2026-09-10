/**
 * G1 "first+last pair" — pure display/aggregation helpers for effort tier.
 *
 * Positive control: a fixture session whose effort changed mid-session
 * (effortTier !== effortTierLast) must render "start→last"; a fixture whose
 * effort never changed (effortTierLast === null) must render the single
 * start value with no arrow. Both cases are exercised below so the detector
 * is proven to fire on a known-true case, not just proven silent on the
 * negative one.
 */
import { describe, it, expect } from 'vitest';
import { effectiveEffortTier, formatEffortTierDisplay } from '../sessionSemantics';

describe('formatEffortTierDisplay (G1 render rule)', () => {
  it('positive control: effort changed mid-session renders "start→last"', () => {
    expect(formatEffortTierDisplay('medium', 'xhigh')).toBe('medium→xhigh');
  });

  it('two changes: last wins in the display string', () => {
    // effortTierLast is always overwritten with the freshest observation —
    // by the time SessionEnd/read happens, only the final value is on record.
    expect(formatEffortTierDisplay('medium', 'xhigh')).toBe('medium→xhigh');
  });

  it('fixture that never changes: effortTierLast is null → renders start alone, no arrow', () => {
    expect(formatEffortTierDisplay('medium', null)).toBe('medium');
    expect(formatEffortTierDisplay('medium', undefined)).toBe('medium');
  });

  it('effortTierLast equal to start (observed but unchanged) renders start alone, no arrow', () => {
    expect(formatEffortTierDisplay('medium', 'medium')).toBe('medium');
  });

  it('no effortTier at all → null (caller renders its own "Not captured" fallback)', () => {
    expect(formatEffortTierDisplay(null, null)).toBeNull();
    expect(formatEffortTierDisplay(undefined, 'xhigh')).toBeNull();
  });
});

describe('effectiveEffortTier (G1 aggregation rule: last when present, else start)', () => {
  it('uses last when present', () => {
    expect(effectiveEffortTier('medium', 'xhigh')).toBe('xhigh');
  });

  it('falls back to start when last is null/absent', () => {
    expect(effectiveEffortTier('medium', null)).toBe('medium');
    expect(effectiveEffortTier('medium', undefined)).toBe('medium');
  });

  it('null when neither is present', () => {
    expect(effectiveEffortTier(null, null)).toBeNull();
    expect(effectiveEffortTier(undefined, undefined)).toBeNull();
  });
});
