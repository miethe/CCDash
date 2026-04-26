// featureCacheBus — P4-011: Cross-cache invalidation bus
//
// A tiny synchronous pub/sub module that lets feature-write call sites publish
// a single event and have BOTH the planning browser cache and the feature
// surface cache invalidated in one shot.
//
// Design rationale: see docs/project_plans/design-specs/
//   feature-surface-planning-cache-coordination.md  (§ Decision)
//
// Usage (write-site):
//   import { publishFeatureWriteEvent } from './featureCacheBus';
//   await updateFeatureStatus(featureId, newStatus);
//   publishFeatureWriteEvent({ projectId, featureIds: [featureId], kind: 'status' });
//
// Subscribers are registered at module init time by the two cache modules;
// callers never need to import those modules directly.

// ── Event shape ───────────────────────────────────────────────────────────────

/** The class of mutation that triggered the invalidation. */
export type FeatureWriteKind = 'status' | 'phase' | 'rename' | 'task' | 'generic';

export interface FeatureWriteEvent {
  /** Affected project. Required for scoped invalidation. */
  projectId: string | undefined;
  /**
   * Affected feature IDs. Provide when known for the narrowest possible eviction.
   * Omit (or pass empty array) to perform a project-wide sweep.
   */
  featureIds?: string[];
  /** Mutation class — carried for tracing; not used for routing today. */
  kind: FeatureWriteKind;
}

// ── Subscriber type ───────────────────────────────────────────────────────────

export type FeatureWriteSubscriber = (event: FeatureWriteEvent) => void;

// ── Internal subscriber registry ─────────────────────────────────────────────

const _subscribers: Set<FeatureWriteSubscriber> = new Set();

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Register a subscriber.  Returns an unsubscribe function.
 *
 * Both `services/featureSurfaceCache.ts` and `services/planning.ts` call this
 * at module init time, so the registry is populated before any write can fire.
 */
export function subscribeToFeatureWrites(subscriber: FeatureWriteSubscriber): () => void {
  _subscribers.add(subscriber);
  return () => _subscribers.delete(subscriber);
}

/**
 * Publish a feature-write event.  Synchronously calls all registered
 * subscribers.  Call this immediately after a successful feature mutation
 * (status change, phase progression, rename, task update).
 *
 * Errors thrown by subscribers are caught and logged so one bad subscriber
 * cannot prevent the others from running.
 */
export function publishFeatureWriteEvent(event: FeatureWriteEvent): void {
  for (const sub of _subscribers) {
    try {
      sub(event);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[featureCacheBus] subscriber threw:', err);
    }
  }
}

/**
 * Visible for testing only.  Returns the current subscriber count.
 */
export function _getSubscriberCount(): number {
  return _subscribers.size;
}

/**
 * Visible for testing only.  Removes all subscribers without calling their
 * unsubscribe functions.  Use in afterEach to prevent cross-test bleed.
 */
export function _clearSubscribers(): void {
  _subscribers.clear();
}
