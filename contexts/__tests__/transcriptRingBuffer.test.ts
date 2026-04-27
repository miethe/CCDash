/**
 * TEST-501: Transcript ring-buffer cap — FE-101 acceptance tests.
 *
 * Covers:
 * - Ring-buffer cap enforced at MAX_SESSION_LOG_ROWS (5000) rows
 * - Oldest rows dropped when cap exceeded (tail retention)
 * - Truncation marker emitted with correct shape when buffer is capped
 * - No unbounded memory growth on continued appends
 * - Memory-guard disabled → passthrough (no cap applied)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MAX_SESSION_LOG_ROWS } from '../../constants';
import type { AgentSession, SessionLog } from '../../types';

// ---------------------------------------------------------------------------
// Mock featureFlags BEFORE importing mergeSessionDetail so the module picks up
// the spy on `isMemoryGuardEnabled`.
// ---------------------------------------------------------------------------
vi.mock('../../lib/featureFlags', () => ({
  isMemoryGuardEnabled: vi.fn(() => true),
}));

import { mergeSessionDetail } from '../dataContextShared';
import { isMemoryGuardEnabled } from '../../lib/featureFlags';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeLog(idx: number): SessionLog {
  return {
    id: `log-${idx}`,
    timestamp: new Date(Date.UTC(2026, 0, 1, 0, idx % 60, Math.floor(idx / 60))).toISOString(),
    speaker: 'agent',
    type: 'message',
    content: `entry ${idx}`,
  };
}

function makeSession(id: string, logCount: number): AgentSession {
  return {
    id,
    taskId: 'T-501',
    status: 'completed',
    model: 'claude-test',
    durationSeconds: 10,
    tokensIn: 0,
    tokensOut: 0,
    totalCost: 0,
    startedAt: '2026-01-01T00:00:00Z',
    toolsUsed: [],
    logs: Array.from({ length: logCount }, (_, i) => makeLog(i)),
  };
}

function sessionSlot(id: string): AgentSession {
  return makeSession(id, 0);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TEST-501: transcript ring-buffer cap (FE-101)', () => {
  beforeEach(() => {
    vi.mocked(isMemoryGuardEnabled).mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // AC-1: Ring-buffer cap enforced at 5000 rows
  describe('AC-1 — cap enforced at 5000 rows', () => {
    it('does NOT truncate when log count is exactly at the cap', () => {
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].logs).toHaveLength(MAX_SESSION_LOG_ROWS);
    });

    it('truncates to exactly MAX_SESSION_LOG_ROWS when over limit', () => {
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS + 1000);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].logs).toHaveLength(MAX_SESSION_LOG_ROWS);
    });

    it('never produces more than MAX_SESSION_LOG_ROWS entries regardless of input size', () => {
      for (const extra of [1, 500, 5000, 100_000]) {
        const session = makeSession('s1', MAX_SESSION_LOG_ROWS + extra);
        const result = mergeSessionDetail([sessionSlot('s1')], session);
        expect(result[0].logs.length).toBeLessThanOrEqual(MAX_SESSION_LOG_ROWS);
      }
    });
  });

  // AC-2: Oldest rows dropped (newest retained)
  describe('AC-2 — oldest rows dropped, newest retained', () => {
    it('drops the leading (oldest) rows when over the cap', () => {
      const overLimit = MAX_SESSION_LOG_ROWS + 5;
      const session = makeSession('s1', overLimit);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      // First retained should be at index 5, not 0
      expect(result[0].logs[0].id).toBe('log-5');
    });

    it('retains the very last log entry (newest row)', () => {
      const overLimit = MAX_SESSION_LOG_ROWS + 200;
      const session = makeSession('s1', overLimit);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      const lastIdx = overLimit - 1;
      expect(result[0].logs[MAX_SESSION_LOG_ROWS - 1].id).toBe(`log-${lastIdx}`);
    });

    it('the retained slice is contiguous (no gaps in indices)', () => {
      const overLimit = MAX_SESSION_LOG_ROWS + 10;
      const session = makeSession('s1', overLimit);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      const retained = result[0].logs;
      for (let i = 1; i < retained.length; i++) {
        const prevIdx = parseInt(retained[i - 1].id.replace('log-', ''), 10);
        const currIdx = parseInt(retained[i].id.replace('log-', ''), 10);
        expect(currIdx).toBe(prevIdx + 1);
      }
    });
  });

  // AC-3: Truncation marker emitted when buffer is capped
  describe('AC-3 — truncation marker emitted on cap', () => {
    it('sets transcriptTruncated when over the cap', () => {
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS + 1);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].transcriptTruncated).toBeDefined();
    });

    it('does NOT set transcriptTruncated when at or below the cap', () => {
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].transcriptTruncated).toBeUndefined();
    });

    it('transcriptTruncated.droppedCount equals actual rows dropped', () => {
      const extra = 750;
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS + extra);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].transcriptTruncated!.droppedCount).toBe(extra);
    });

    it('transcriptTruncated.firstRetainedTimestamp matches first retained log', () => {
      const extra = 100;
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS + extra);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      const expectedTimestamp = session.logs[extra].timestamp;
      expect(result[0].transcriptTruncated!.firstRetainedTimestamp).toBe(expectedTimestamp);
    });

    it('truncation marker carries both required fields', () => {
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS + 50);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      const marker = result[0].transcriptTruncated!;
      expect(typeof marker.droppedCount).toBe('number');
      expect(typeof marker.firstRetainedTimestamp).toBe('string');
    });
  });

  // AC-4: No unbounded memory growth on continued appends
  describe('AC-4 — no unbounded growth on repeated appends', () => {
    it('output length stays bounded across 10 successive merges with growing inputs', () => {
      let sessions: AgentSession[] = [sessionSlot('s1')];
      for (let round = 1; round <= 10; round++) {
        // Each round, "fetch" a larger batch (simulates growing logs arriving)
        const fetched = makeSession('s1', MAX_SESSION_LOG_ROWS + round * 500);
        sessions = mergeSessionDetail(sessions, fetched);
        expect(sessions[0].logs.length).toBeLessThanOrEqual(MAX_SESSION_LOG_ROWS);
      }
    });

    it('log array length is strictly bounded even when input is 10× the cap', () => {
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS * 10);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].logs.length).toBe(MAX_SESSION_LOG_ROWS);
    });

    it('droppedCount accumulates correctly across the full over-limit scenario', () => {
      const factor = 3;
      const total = MAX_SESSION_LOG_ROWS * factor;
      const session = makeSession('s1', total);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].transcriptTruncated!.droppedCount).toBe(total - MAX_SESSION_LOG_ROWS);
    });
  });

  // Guard: memory guard disabled → passthrough, no cap
  describe('memory guard disabled — passthrough', () => {
    it('does not cap logs when isMemoryGuardEnabled returns false', () => {
      vi.mocked(isMemoryGuardEnabled).mockReturnValue(false);
      const overLimit = MAX_SESSION_LOG_ROWS + 200;
      const session = makeSession('s1', overLimit);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].logs).toHaveLength(overLimit);
      expect(result[0].transcriptTruncated).toBeUndefined();
    });

    it('does not emit truncation marker when guard is off', () => {
      vi.mocked(isMemoryGuardEnabled).mockReturnValue(false);
      const session = makeSession('s1', MAX_SESSION_LOG_ROWS + 1);
      const result = mergeSessionDetail([sessionSlot('s1')], session);
      expect(result[0].transcriptTruncated).toBeUndefined();
    });
  });
});
