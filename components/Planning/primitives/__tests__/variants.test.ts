import { describe, expect, it } from 'vitest';

import { statusVariant, readinessVariant } from '../variants';

describe('statusVariant', () => {
  it('returns ok for complete/done/active/in_progress values', () => {
    expect(statusVariant('complete')).toBe('ok');
    expect(statusVariant('completed')).toBe('ok');
    expect(statusVariant('done')).toBe('ok');
    expect(statusVariant('active')).toBe('ok');
    expect(statusVariant('in_progress')).toBe('ok');
    expect(statusVariant('IN_PROGRESS')).toBe('ok');
  });

  it('returns error for blocked/stale/reversed/mismatch values', () => {
    expect(statusVariant('blocked')).toBe('error');
    expect(statusVariant('stale')).toBe('error');
    expect(statusVariant('reversed')).toBe('error');
    expect(statusVariant('mismatch')).toBe('error');
    expect(statusVariant('BLOCKED')).toBe('error');
  });

  it('returns warn for pending/waiting/deferred values', () => {
    expect(statusVariant('pending')).toBe('warn');
    expect(statusVariant('waiting')).toBe('warn');
    expect(statusVariant('deferred')).toBe('warn');
  });

  it('returns neutral for unrecognised values', () => {
    expect(statusVariant('unknown')).toBe('neutral');
    expect(statusVariant('')).toBe('neutral');
    expect(statusVariant('some_custom_status')).toBe('neutral');
  });
});

describe('readinessVariant', () => {
  it('maps ready → ok', () => {
    expect(readinessVariant('ready')).toBe('ok');
  });

  it('maps blocked → error', () => {
    expect(readinessVariant('blocked')).toBe('error');
  });

  it('maps waiting → warn', () => {
    expect(readinessVariant('waiting')).toBe('warn');
  });

  it('maps unknown → neutral', () => {
    expect(readinessVariant('unknown')).toBe('neutral');
    expect(readinessVariant('')).toBe('neutral');
    expect(readinessVariant('other')).toBe('neutral');
  });
});
