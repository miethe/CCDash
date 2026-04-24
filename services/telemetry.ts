// services/telemetry.ts — P5-003: Structured frontend telemetry helper
//
// Emits structured debug-level events for cache hit/miss/stale and other
// frontend hot paths.  No runtime dependency is added — events are:
//
//   1. console.debug()-gated (only fires when the CDash debug flag is active)
//   2. Dispatched as a CustomEvent on `window` so external devtools / test
//      harnesses can subscribe with addEventListener('ccdash:telemetry', ...).
//
// The window hook is the same lightweight pattern used by testVisualizer.ts;
// no external SDK is needed.
//
// Usage:
//   import { emitCacheTelemetry } from '@/services/telemetry';
//   emitCacheTelemetry({ cache: 'featureSurface', event: 'hit', keyBucket: 'list' });

/** Cardinality-safe key bucket label for cache telemetry. */
export type CacheKeyBucket =
  | 'list'
  | 'rollup'
  | 'summary'
  | 'facets'
  | 'feature_context'
  | 'other';

/** Cache event type. */
export type CacheEventType = 'hit' | 'miss' | 'stale' | 'evict' | 'set';

export interface CacheTelemetryPayload {
  /** Short name identifying the cache (e.g. 'featureSurface', 'planning'). */
  cache: string;
  /** The event that occurred. */
  event: CacheEventType;
  /** Cardinality-safe bucket describing the key type. */
  keyBucket: CacheKeyBucket;
  /** Optional additional context (no raw IDs). */
  detail?: Record<string, string | number | boolean>;
}

/** Global window flag — set to true in devtools to enable debug events. */
declare global {
  interface Window {
    __ccdashDebug?: boolean;
  }
}

/**
 * Returns true when the CCDash debug mode is active.
 * Controlled by `window.__ccdashDebug = true` in the browser console.
 */
function isDebugEnabled(): boolean {
  return typeof window !== 'undefined' && window.__ccdashDebug === true;
}

/**
 * Emit a structured cache telemetry event.
 *
 * - Does nothing when debug mode is off (zero-cost in production).
 * - In debug mode: logs to console.debug AND dispatches a `ccdash:telemetry`
 *   CustomEvent on window so test harnesses can assert without global mocks.
 */
export function emitCacheTelemetry(payload: CacheTelemetryPayload): void {
  if (!isDebugEnabled()) return;
  try {
    const entry = { type: 'cache', ...payload, ts: Date.now() };
    console.debug('[ccdash:telemetry]', entry);
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('ccdash:telemetry', { detail: entry }));
    }
  } catch {
    // Telemetry must never throw — swallow all errors silently.
  }
}

/**
 * Convenience wrapper: emit a metric-style telemetry event (non-cache).
 * Follows the same debug-gate + window dispatch pattern.
 */
export function emitTelemetry(
  category: string,
  event: string,
  detail?: Record<string, string | number | boolean>,
): void {
  if (!isDebugEnabled()) return;
  try {
    const entry = { type: category, event, detail, ts: Date.now() };
    console.debug('[ccdash:telemetry]', entry);
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('ccdash:telemetry', { detail: entry }));
    }
  } catch {
    // swallow
  }
}
