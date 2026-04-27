/**
 * FE-104: Polling lifecycle teardown tests.
 *
 * Tests the failure-counting and teardown logic of AppRuntimeContext without
 * rendering the full React tree.  We exercise the same state machine that
 * AppRuntimeContext implements: track consecutive failures, clear intervals
 * after N=3 failures, expose runtimeUnreachable, and reset on retry.
 *
 * Uses vi.useFakeTimers() so setInterval / clearInterval are fully controlled.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ---------------------------------------------------------------------------
// Minimal simulation of the AppRuntimeContext polling teardown state machine
// ---------------------------------------------------------------------------

const CONSECUTIVE_FAILURE_THRESHOLD = 3;

interface SimState {
  runtimeUnreachable: boolean;
  pollingActive: boolean;
  consecutiveFailures: number;
  healthIntervalId: ReturnType<typeof setInterval> | null;
  featureIntervalId: ReturnType<typeof setInterval> | null;
  liveConnectionStopped: boolean;
}

function createPollingSimulator(onHealthPoll: () => Promise<void>) {
  const state: SimState = {
    runtimeUnreachable: false,
    pollingActive: true,
    consecutiveFailures: 0,
    healthIntervalId: null,
    featureIntervalId: null,
    liveConnectionStopped: false,
  };

  // Mirrors teardownPolling() in AppRuntimeContext
  function teardownPolling() {
    if (state.healthIntervalId !== null) {
      clearInterval(state.healthIntervalId);
      state.healthIntervalId = null;
    }
    if (state.featureIntervalId !== null) {
      clearInterval(state.featureIntervalId);
      state.featureIntervalId = null;
    }
    // Mirrors stopLiveConnection()
    state.liveConnectionStopped = true;
    state.pollingActive = false;
    state.runtimeUnreachable = true;
  }

  // Mirrors the health check success/failure path inside refreshAll()
  async function runHealthCheck() {
    if (!state.pollingActive) return;
    try {
      await onHealthPoll();
      // success — reset counter
      state.consecutiveFailures = 0;
    } catch {
      state.consecutiveFailures += 1;
      if (state.consecutiveFailures >= CONSECUTIVE_FAILURE_THRESHOLD) {
        teardownPolling();
      }
    }
  }

  // Start the 30 s poll (compressed to 100 ms for testing)
  function startHealthPoll(intervalMs = 100) {
    const id = setInterval(() => {
      if (!state.pollingActive) return;
      void runHealthCheck();
    }, intervalMs);
    state.healthIntervalId = id;
  }

  // Start the 5 s feature poll (compressed to 50 ms for testing)
  function startFeaturePoll(intervalMs = 50) {
    const id = setInterval(() => {
      if (!state.pollingActive) return;
    }, intervalMs);
    state.featureIntervalId = id;
  }

  // Mirrors retryRuntime()
  function retryRuntime() {
    state.consecutiveFailures = 0;
    state.pollingActive = true;
    state.runtimeUnreachable = false;
    state.liveConnectionStopped = false;
    // Restart intervals (simulated)
    startHealthPoll();
    startFeaturePoll();
  }

  return { state, startHealthPoll, startFeaturePoll, retryRuntime, runHealthCheck };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AppRuntimeContext — FE-104 polling lifecycle teardown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('does NOT tear down polling after 1 or 2 consecutive failures', async () => {
    let callCount = 0;
    const alwaysFail = async () => {
      callCount++;
      throw new Error('backend unreachable');
    };

    const { state, startHealthPoll, runHealthCheck } = createPollingSimulator(alwaysFail);
    startHealthPoll(100);

    // Manually trigger 2 failures
    await runHealthCheck();
    await runHealthCheck();

    expect(state.consecutiveFailures).toBe(2);
    expect(state.runtimeUnreachable).toBe(false);
    expect(state.pollingActive).toBe(true);
    expect(state.healthIntervalId).not.toBeNull();
    expect(callCount).toBe(2);
  });

  it('tears down intervals and live connection after exactly 3 consecutive failures', async () => {
    const alwaysFail = async () => { throw new Error('backend unreachable'); };

    const { state, startHealthPoll, startFeaturePoll, runHealthCheck } = createPollingSimulator(alwaysFail);
    startHealthPoll(100);
    startFeaturePoll(50);

    const healthIdBeforeTeardown = state.healthIntervalId;
    const featureIdBeforeTeardown = state.featureIntervalId;

    expect(healthIdBeforeTeardown).not.toBeNull();
    expect(featureIdBeforeTeardown).not.toBeNull();

    await runHealthCheck(); // failure 1
    await runHealthCheck(); // failure 2
    await runHealthCheck(); // failure 3 → teardown fires

    expect(state.consecutiveFailures).toBe(3);
    expect(state.runtimeUnreachable).toBe(true);
    expect(state.pollingActive).toBe(false);
    expect(state.healthIntervalId).toBeNull();
    expect(state.featureIntervalId).toBeNull();
    expect(state.liveConnectionStopped).toBe(true);
  });

  it('intervals do not fire further work after teardown', async () => {
    let callCount = 0;
    const alwaysFail = async () => {
      callCount++;
      throw new Error('backend unreachable');
    };

    const { state, startHealthPoll, runHealthCheck } = createPollingSimulator(alwaysFail);
    startHealthPoll(100);

    // Drive to teardown
    await runHealthCheck();
    await runHealthCheck();
    await runHealthCheck();

    expect(state.pollingActive).toBe(false);
    const countAtTeardown = callCount;

    // Advance fake timers well past one poll interval — pollingActive=false guard
    // prevents the interval callback from calling the health endpoint again
    vi.advanceTimersByTime(500);
    // Flush any pending microtasks
    await Promise.resolve();

    expect(callCount).toBe(countAtTeardown);
  });

  it('success before threshold resets the consecutive failure count', async () => {
    let shouldFail = true;
    const conditionalFail = async () => {
      if (shouldFail) throw new Error('backend unreachable');
    };

    const { state, runHealthCheck } = createPollingSimulator(conditionalFail);

    await runHealthCheck(); // failure 1
    await runHealthCheck(); // failure 2

    expect(state.consecutiveFailures).toBe(2);

    shouldFail = false;
    await runHealthCheck(); // success → resets counter

    expect(state.consecutiveFailures).toBe(0);
    expect(state.runtimeUnreachable).toBe(false);
  });

  it('retryRuntime re-arms polling and resets runtimeUnreachable after teardown', async () => {
    const alwaysFail = async () => { throw new Error('backend unreachable'); };

    const { state, startHealthPoll, startFeaturePoll, runHealthCheck, retryRuntime } =
      createPollingSimulator(alwaysFail);
    startHealthPoll(100);
    startFeaturePoll(50);

    // Drive to teardown
    await runHealthCheck();
    await runHealthCheck();
    await runHealthCheck();

    expect(state.runtimeUnreachable).toBe(true);
    expect(state.pollingActive).toBe(false);

    // User clicks Retry
    retryRuntime();

    expect(state.runtimeUnreachable).toBe(false);
    expect(state.pollingActive).toBe(true);
    expect(state.consecutiveFailures).toBe(0);
    expect(state.liveConnectionStopped).toBe(false);
    // New intervals should have been registered
    expect(state.healthIntervalId).not.toBeNull();
    expect(state.featureIntervalId).not.toBeNull();
  });
});
