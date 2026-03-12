import { describe, expect, it } from 'vitest';

import type { AgentSession } from '@/types';

import { buildSessionBlockInsights } from '../sessionBlockInsights';

const baseSession = (): AgentSession => ({
  id: 'session-1',
  taskId: 'TASK-1',
  status: 'completed',
  model: 'claude-sonnet',
  durationSeconds: 7 * 60 * 60,
  tokensIn: 0,
  tokensOut: 0,
  totalCost: 7,
  startedAt: '2026-03-12T10:00:00.000Z',
  endedAt: '2026-03-12T17:00:00.000Z',
  toolsUsed: [],
  logs: [],
  usageEvents: [
    {
      id: 'evt-1',
      projectId: 'proj',
      sessionId: 'session-1',
      rootSessionId: 'session-1',
      linkedSessionId: '',
      sourceLogId: 'log-1',
      capturedAt: '2026-03-12T10:15:00.000Z',
      eventKind: 'message',
      model: 'claude-sonnet',
      toolName: '',
      agentName: '',
      tokenFamily: 'model_input',
      deltaTokens: 1000,
      costUsdModelIO: 0.1,
      metadata: {},
    },
    {
      id: 'evt-2',
      projectId: 'proj',
      sessionId: 'session-1',
      rootSessionId: 'session-1',
      linkedSessionId: '',
      sourceLogId: 'log-2',
      capturedAt: '2026-03-12T14:30:00.000Z',
      eventKind: 'message',
      model: 'claude-sonnet',
      toolName: '',
      agentName: '',
      tokenFamily: 'model_output',
      deltaTokens: 500,
      costUsdModelIO: 0.1,
      metadata: {},
    },
    {
      id: 'evt-3',
      projectId: 'proj',
      sessionId: 'session-1',
      rootSessionId: 'session-1',
      linkedSessionId: '',
      sourceLogId: 'log-3',
      capturedAt: '2026-03-12T16:45:00.000Z',
      eventKind: 'message',
      model: 'claude-sonnet',
      toolName: '',
      agentName: '',
      tokenFamily: 'cache_read_input',
      deltaTokens: 500,
      costUsdModelIO: 0.1,
      metadata: {},
    },
  ],
}) as AgentSession;

describe('buildSessionBlockInsights', () => {
  it('splits long sessions into configurable blocks and preserves totals', () => {
    const insights = buildSessionBlockInsights(baseSession(), { blockDurationHours: 5 });

    expect(insights.isLongSession).toBe(true);
    expect(insights.blocks).toHaveLength(2);
    expect(insights.totalWorkloadTokens).toBe(2000);
    expect(insights.blocks[0].workloadTokens).toBe(1500);
    expect(insights.blocks[1].workloadTokens).toBe(500);
    expect(insights.blocks[0].status).toBe('completed');
    expect(insights.blocks[1].status).toBe('partial');
    expect(insights.blocks[1].projectedWorkloadTokens).toBe(1250);
    expect(insights.blocks[0].costUsd + insights.blocks[1].costUsd).toBeCloseTo(7, 5);
  });

  it('falls back to message logs when usage events are unavailable', () => {
    const session = baseSession();
    session.usageEvents = [];
    session.logs = [
      {
        id: 'log-1',
        timestamp: '2026-03-12T10:15:00.000Z',
        speaker: 'agent',
        type: 'message',
        content: '',
        metadata: {
          inputTokens: 300,
          outputTokens: 200,
          cache_creation_input_tokens: 100,
          cache_read_input_tokens: 0,
        },
      },
    ];

    const insights = buildSessionBlockInsights(session, { blockDurationHours: 5 });

    expect(insights.dataSource).toBe('logs');
    expect(insights.totalWorkloadTokens).toBe(600);
    expect(insights.blocks[0].modelInputTokens).toBe(300);
    expect(insights.blocks[0].modelOutputTokens).toBe(200);
    expect(insights.blocks[0].cacheCreationInputTokens).toBe(100);
  });
});
