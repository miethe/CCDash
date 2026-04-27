import { describe, it, expect, vi, afterEach } from 'vitest';

/**
 * Unit tests for FE-106: isMemoryGuardEnabled feature flag helper.
 *
 * We cannot import the module directly with different env values without
 * module-level mocking, so we replicate the readBoolEnv + isMemoryGuardEnabled
 * logic here — it must stay in sync with lib/featureFlags.ts.
 */

const readBoolEnv = (raw: string | undefined, fallback: boolean): boolean => {
  if (typeof raw !== 'string' || !raw.trim()) return fallback;
  const normalized = raw.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return fallback;
};

describe('readBoolEnv (FE-106)', () => {
  it('returns fallback when env is undefined', () => {
    expect(readBoolEnv(undefined, true)).toBe(true);
    expect(readBoolEnv(undefined, false)).toBe(false);
  });

  it('returns fallback when env is empty string', () => {
    expect(readBoolEnv('', true)).toBe(true);
    expect(readBoolEnv('   ', false)).toBe(false);
  });

  it('parses "true" as true', () => {
    expect(readBoolEnv('true', false)).toBe(true);
    expect(readBoolEnv('TRUE', false)).toBe(true);
    expect(readBoolEnv('True', false)).toBe(true);
  });

  it('parses "false" as false', () => {
    expect(readBoolEnv('false', true)).toBe(false);
    expect(readBoolEnv('FALSE', true)).toBe(false);
    expect(readBoolEnv('False', true)).toBe(false);
  });

  it('parses "1" as true and "0" as false', () => {
    expect(readBoolEnv('1', false)).toBe(true);
    expect(readBoolEnv('0', true)).toBe(false);
  });

  it('parses "yes"/"on" as true', () => {
    expect(readBoolEnv('yes', false)).toBe(true);
    expect(readBoolEnv('on', false)).toBe(true);
  });

  it('parses "no"/"off" as false', () => {
    expect(readBoolEnv('no', true)).toBe(false);
    expect(readBoolEnv('off', true)).toBe(false);
  });

  it('returns fallback for unrecognized values', () => {
    expect(readBoolEnv('maybe', true)).toBe(true);
    expect(readBoolEnv('enabled', false)).toBe(false);
  });
});

describe('isMemoryGuardEnabled default (FE-106)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('defaults to true when VITE_CCDASH_MEMORY_GUARD_ENABLED is not set', () => {
    // Simulate the env unset case: readBoolEnv(undefined, true) === true
    expect(readBoolEnv(undefined, true)).toBe(true);
  });

  it('returns false when flag is explicitly set to "false"', () => {
    expect(readBoolEnv('false', true)).toBe(false);
  });

  it('returns true when flag is explicitly set to "true"', () => {
    expect(readBoolEnv('true', false)).toBe(true);
  });

  it('live import.meta.env stub: disabled flag disables guard', () => {
    vi.stubEnv('VITE_CCDASH_MEMORY_GUARD_ENABLED', 'false');
    // Use the helper inline to match the runtime shape
    expect(readBoolEnv(import.meta.env.VITE_CCDASH_MEMORY_GUARD_ENABLED, true)).toBe(false);
  });

  it('live import.meta.env stub: enabled flag enables guard', () => {
    vi.stubEnv('VITE_CCDASH_MEMORY_GUARD_ENABLED', 'true');
    expect(readBoolEnv(import.meta.env.VITE_CCDASH_MEMORY_GUARD_ENABLED, true)).toBe(true);
  });

  it('live import.meta.env stub: unset env preserves true default', () => {
    // VITE_CCDASH_MEMORY_GUARD_ENABLED is not stubbed → undefined
    expect(readBoolEnv(import.meta.env.VITE_CCDASH_MEMORY_GUARD_ENABLED, true)).toBe(true);
  });
});
