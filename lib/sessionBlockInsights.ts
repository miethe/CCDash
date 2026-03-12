import type { AgentSession, SessionLog, SessionUsageEvent } from '@/types';

import { resolveDisplayCost } from './sessionSemantics';

const DEFAULT_BLOCK_DURATION_HOURS = 5;
const HOUR_MS = 60 * 60 * 1000;

type WorkloadFamily = 'model_input' | 'model_output' | 'cache_creation_input' | 'cache_read_input';

export interface SessionBlockPoint {
  timestamp: string;
  timestampMs: number;
  family: WorkloadFamily;
  deltaTokens: number;
}

export interface SessionBlockSummary {
  index: number;
  label: string;
  status: 'completed' | 'active' | 'partial' | 'upcoming';
  startAt: string;
  endAt: string;
  actualEndAt: string;
  progressPct: number;
  elapsedHours: number;
  durationHours: number;
  modelInputTokens: number;
  modelOutputTokens: number;
  cacheCreationInputTokens: number;
  cacheReadInputTokens: number;
  workloadTokens: number;
  costUsd: number;
  tokenBurnRatePerHour: number;
  costBurnRatePerHour: number;
  projectedWorkloadTokens: number;
  projectedCostUsd: number;
}

export interface SessionBlockInsights {
  blockDurationHours: number;
  blockDurationMs: number;
  sessionStartAt: string;
  sessionEndAt: string;
  sessionDurationHours: number;
  totalWorkloadTokens: number;
  totalCostUsd: number;
  dataSource: 'usageEvents' | 'logs' | 'none';
  blocks: SessionBlockSummary[];
  latestBlock: SessionBlockSummary | null;
  activeBlock: SessionBlockSummary | null;
  isLongSession: boolean;
}

const toNumber = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

const toTimestampMs = (value: string | null | undefined): number => {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const clampHours = (value: number | null | undefined): number => {
  const parsed = Math.round(toNumber(value));
  if (parsed <= 0) return DEFAULT_BLOCK_DURATION_HOURS;
  return Math.min(24, parsed);
};

const blockStatus = (
  index: number,
  totalBlocks: number,
  isSessionActive: boolean,
  blockProgressPct: number,
): SessionBlockSummary['status'] => {
  if (blockProgressPct <= 0) return 'upcoming';
  if (blockProgressPct >= 100) return 'completed';
  if (isSessionActive && index === totalBlocks - 1) return 'active';
  return 'partial';
};

const blockLabel = (index: number): string => `Block ${index + 1}`;

const buildPoint = (timestamp: string, family: WorkloadFamily, deltaTokens: number): SessionBlockPoint | null => {
  const timestampMs = toTimestampMs(timestamp);
  if (timestampMs <= 0 || deltaTokens <= 0) return null;
  return {
    timestamp,
    timestampMs,
    family,
    deltaTokens,
  };
};

const pointsFromUsageEvents = (usageEvents: SessionUsageEvent[] | undefined): SessionBlockPoint[] => {
  const points: SessionBlockPoint[] = [];
  (usageEvents || []).forEach(event => {
    const family = String(event.tokenFamily || '').trim() as WorkloadFamily;
    if (
      family !== 'model_input'
      && family !== 'model_output'
      && family !== 'cache_creation_input'
      && family !== 'cache_read_input'
    ) {
      return;
    }
    const point = buildPoint(event.capturedAt, family, toNumber(event.deltaTokens));
    if (point) points.push(point);
  });
  return points.sort((a, b) => a.timestampMs - b.timestampMs);
};

const pointsFromLogs = (logs: SessionLog[] | undefined): SessionBlockPoint[] => {
  const points: SessionBlockPoint[] = [];
  (logs || []).forEach(log => {
    const metadata = log.metadata || {};
    const timestamp = String(log.timestamp || '').trim();
    const families: Array<[WorkloadFamily, number]> = [
      ['model_input', toNumber(metadata.inputTokens)],
      ['model_output', toNumber(metadata.outputTokens)],
      ['cache_creation_input', toNumber(metadata.cache_creation_input_tokens)],
      ['cache_read_input', toNumber(metadata.cache_read_input_tokens)],
    ];
    families.forEach(([family, deltaTokens]) => {
      const point = buildPoint(timestamp, family, deltaTokens);
      if (point) points.push(point);
    });
  });
  return points.sort((a, b) => a.timestampMs - b.timestampMs);
};

const summarizeWorkloadTokens = (points: SessionBlockPoint[]): number => (
  points.reduce((sum, point) => sum + point.deltaTokens, 0)
);

export const buildSessionBlockInsights = (
  session: AgentSession,
  options: { blockDurationHours?: number; now?: Date } = {},
): SessionBlockInsights => {
  const blockDurationHours = clampHours(options.blockDurationHours);
  const blockDurationMs = blockDurationHours * HOUR_MS;
  const usageEventPoints = pointsFromUsageEvents(session.usageEvents);
  const logPoints = usageEventPoints.length > 0 ? [] : pointsFromLogs(session.logs);
  const points = usageEventPoints.length > 0 ? usageEventPoints : logPoints;
  const dataSource: SessionBlockInsights['dataSource'] = usageEventPoints.length > 0
    ? 'usageEvents'
    : logPoints.length > 0
      ? 'logs'
      : 'none';

  const fallbackNowMs = options.now instanceof Date ? options.now.getTime() : Date.now();
  const startedAtMs = toTimestampMs(session.startedAt) || (points[0]?.timestampMs ?? fallbackNowMs);
  const inferredEndMs = Math.max(
    toTimestampMs(session.endedAt),
    toTimestampMs(session.updatedAt),
    points[points.length - 1]?.timestampMs ?? 0,
    startedAtMs + (toNumber(session.durationSeconds) * 1000),
  );
  const sessionEndMs = Math.max(startedAtMs, inferredEndMs || fallbackNowMs);
  const sessionDurationMs = Math.max(0, sessionEndMs - startedAtMs);
  const totalBlocks = Math.max(1, Math.ceil(Math.max(sessionDurationMs, 1) / blockDurationMs));
  const totalWorkloadTokens = summarizeWorkloadTokens(points);
  const totalCostUsd = resolveDisplayCost(session);
  const costPerToken = totalWorkloadTokens > 0 ? totalCostUsd / totalWorkloadTokens : 0;
  const isSessionActive = String(session.status || '').toLowerCase() === 'active';

  const blocks: SessionBlockSummary[] = Array.from({ length: totalBlocks }, (_, index) => {
    const blockStartMs = startedAtMs + (index * blockDurationMs);
    const blockEndMs = blockStartMs + blockDurationMs;
    const actualEndMs = Math.min(sessionEndMs, blockEndMs);
    const elapsedMs = Math.max(0, actualEndMs - blockStartMs);
    const progressPct = Math.max(0, Math.min(100, (elapsedMs / blockDurationMs) * 100));
    const blockPoints = points.filter(point => (
      point.timestampMs >= blockStartMs
      && (
        point.timestampMs < blockEndMs
        || (index === totalBlocks - 1 && point.timestampMs === blockEndMs)
      )
    ));

    const summary = {
      model_input: 0,
      model_output: 0,
      cache_creation_input: 0,
      cache_read_input: 0,
    };
    blockPoints.forEach(point => {
      summary[point.family] += point.deltaTokens;
    });

    const workloadTokens = (
      summary.model_input
      + summary.model_output
      + summary.cache_creation_input
      + summary.cache_read_input
    );
    const costUsd = Number((workloadTokens * costPerToken).toFixed(6));
    const tokenBurnRatePerHour = elapsedMs > 0 ? Number(((workloadTokens / elapsedMs) * HOUR_MS).toFixed(2)) : 0;
    const costBurnRatePerHour = elapsedMs > 0 ? Number(((costUsd / elapsedMs) * HOUR_MS).toFixed(4)) : 0;
    const projectedWorkloadTokens = elapsedMs > 0
      ? Math.round((workloadTokens / elapsedMs) * blockDurationMs)
      : 0;
    const projectedCostUsd = elapsedMs > 0
      ? Number(((costUsd / elapsedMs) * blockDurationMs).toFixed(6))
      : 0;

    return {
      index,
      label: blockLabel(index),
      status: blockStatus(index, totalBlocks, isSessionActive, progressPct),
      startAt: new Date(blockStartMs).toISOString(),
      endAt: new Date(blockEndMs).toISOString(),
      actualEndAt: new Date(actualEndMs).toISOString(),
      progressPct: Number(progressPct.toFixed(1)),
      elapsedHours: Number((elapsedMs / HOUR_MS).toFixed(2)),
      durationHours: blockDurationHours,
      modelInputTokens: summary.model_input,
      modelOutputTokens: summary.model_output,
      cacheCreationInputTokens: summary.cache_creation_input,
      cacheReadInputTokens: summary.cache_read_input,
      workloadTokens,
      costUsd,
      tokenBurnRatePerHour,
      costBurnRatePerHour,
      projectedWorkloadTokens,
      projectedCostUsd,
    };
  });

  const activeBlock = blocks.find(block => block.status === 'active') || null;
  const latestBlock = blocks[blocks.length - 1] || null;

  return {
    blockDurationHours,
    blockDurationMs,
    sessionStartAt: new Date(startedAtMs).toISOString(),
    sessionEndAt: new Date(sessionEndMs).toISOString(),
    sessionDurationHours: Number((sessionDurationMs / HOUR_MS).toFixed(2)),
    totalWorkloadTokens,
    totalCostUsd,
    dataSource,
    blocks,
    latestBlock,
    activeBlock,
    isLongSession: sessionDurationMs >= blockDurationMs,
  };
};
