/**
 * FE-106: Memory guard feature flag helper.
 *
 * Mirrors the readBooleanEnv style from services/live/config.ts.
 * Accepts '1'/'true'/'yes'/'on' and '0'/'false'/'no'/'off';
 * falls back to `defaultValue` for anything else (including undefined).
 */
const readBoolEnv = (raw: string | undefined, fallback: boolean): boolean => {
  if (typeof raw !== 'string' || !raw.trim()) return fallback;
  const normalized = raw.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return fallback;
};

/**
 * FE-106: Master gate for all FE-101..FE-105 memory-hardening changes.
 *
 * Default: true (env unset → hardening active).
 * Set VITE_CCDASH_MEMORY_GUARD_ENABLED=false to restore original behavior.
 */
export const isMemoryGuardEnabled = (): boolean =>
  readBoolEnv(import.meta.env.VITE_CCDASH_MEMORY_GUARD_ENABLED, true);
