import type {
  AgentSession,
  FeaturePlanningContext,
  PlanningAgentSessionBoard,
  PlanningAgentSessionCard,
  PlanningArtifactRef,
  PlanningCommandCenterItem,
  SessionLog,
} from '@/types';

import { resolveDisplayCost } from './sessionSemantics';
import { resolveTokenMetrics, type ResolvedTokenMetrics, type WorkloadSourceKind } from './tokenMetrics';

export type AnalyticsDimensionKind =
  | 'model'
  | 'agent'
  | 'skill'
  | 'tool'
  | 'artifact'
  | 'file'
  | 'phase'
  | 'task';

export interface AnalyticsDimensionSummary {
  key: string;
  label: string;
  kind: AnalyticsDimensionKind;
  count: number;
  sessionCount: number;
  logCount: number;
  workloadTokens: number;
  costUsd: number;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface SessionAnalyticsTokenTotals {
  tokenInput: number;
  tokenOutput: number;
  modelIOTokens: number;
  cacheInputTokens: number;
  observedTokens: number;
  toolReportedTokens: number;
  workloadTokens: number;
  workloadBySource: Record<WorkloadSourceKind, number>;
  toolFallbackSessionCount: number;
}

export interface SessionAnalyticsTotals {
  sessionCount: number;
  activeSessionCount: number;
  completedSessionCount: number;
  logCount: number;
  durationSeconds: number;
  costUsd: number;
  toolUseCount: number;
  artifactCount: number;
  fileTouchCount: number;
  tokens: SessionAnalyticsTokenTotals;
}

export interface SessionAnalyticsSessionSummary {
  sessionId: string;
  title?: string;
  status: AgentSession['status'];
  startedAt: string;
  endedAt?: string;
  durationSeconds: number;
  model?: string;
  agents: string[];
  skills: string[];
  phaseHints: string[];
  taskHints: string[];
  logCount: number;
  toolUseCount: number;
  artifactCount: number;
  fileTouchCount: number;
  costUsd: number;
  tokens: ResolvedTokenMetrics;
}

export interface SessionAnalyticsSummary {
  totals: SessionAnalyticsTotals;
  sessions: SessionAnalyticsSessionSummary[];
  models: AnalyticsDimensionSummary[];
  agents: AnalyticsDimensionSummary[];
  skills: AnalyticsDimensionSummary[];
  tools: AnalyticsDimensionSummary[];
  artifacts: AnalyticsDimensionSummary[];
  files: AnalyticsDimensionSummary[];
  phases: AnalyticsDimensionSummary[];
  tasks: AnalyticsDimensionSummary[];
}

export type PlannedObservedKind = 'agent' | 'skill' | 'model' | 'task';

export interface PlannedObservedAnalyticsRow {
  key: string;
  label: string;
  kind: PlannedObservedKind;
  planned: boolean;
  observed: boolean;
  plannedCount: number;
  observedCount: number;
  plannedSources: string[];
  observedSources: string[];
}

export interface PlannedObservedAnalyticsGroup {
  kind: PlannedObservedKind;
  plannedCount: number;
  observedCount: number;
  matchedCount: number;
  plannedOnlyCount: number;
  observedOnlyCount: number;
  items: PlannedObservedAnalyticsRow[];
}

export interface FeatureAnalyticsSessionCardSummary {
  sessionId: string;
  state: PlanningAgentSessionCard['state'];
  agentName?: string;
  agentType?: string;
  model?: string;
  phaseNumber?: number;
  phaseTitle?: string;
  taskId?: string;
  taskTitle?: string;
  startedAt?: string;
  lastActivityAt?: string;
  durationSeconds: number;
  totalTokens: number;
  tokenInput: number;
  tokenOutput: number;
}

export interface FeatureAnalyticsTotals {
  sessionCount: number;
  activeSessionCount: number;
  completedSessionCount: number;
  failedSessionCount: number;
  durationSeconds: number;
  totalTokens: number;
  tokenInput: number;
  tokenOutput: number;
  phaseCount: number;
  taskCount: number;
}

export interface FeaturePlannedObservedSummary {
  agents: PlannedObservedAnalyticsGroup;
  skills: PlannedObservedAnalyticsGroup;
  models: PlannedObservedAnalyticsGroup;
  tasks: PlannedObservedAnalyticsGroup;
}

export interface FeatureAnalyticsSummary {
  featureId?: string;
  featureName?: string;
  totals: FeatureAnalyticsTotals;
  sessionCards: FeatureAnalyticsSessionCardSummary[];
  plannedVsObserved: FeaturePlannedObservedSummary;
  phases: AnalyticsDimensionSummary[];
  files: AnalyticsDimensionSummary[];
  artifacts: AnalyticsDimensionSummary[];
}

export interface FeatureAnalyticsSummaryInput {
  featureContext?: FeaturePlanningContext | null;
  sessionCards: PlanningAgentSessionCard[];
  commandCenterItem?: PlanningCommandCenterItem | null;
}

interface DimensionBucket {
  key: string;
  label: string;
  kind: AnalyticsDimensionKind;
  count: number;
  sessionIds: Set<string>;
  logCount: number;
  workloadTokens: number;
  costUsd: number;
  metadata: Record<string, string | number | boolean | null>;
}

interface Signal {
  key: string;
  label: string;
  count?: number;
  source?: string;
  metadata?: Record<string, string | number | boolean | null>;
}

interface PlannedObservedBucket {
  key: string;
  label: string;
  kind: PlannedObservedKind;
  plannedCount: number;
  observedCount: number;
  plannedSources: Set<string>;
  observedSources: Set<string>;
}

const emptyWorkloadBySource = (): Record<WorkloadSourceKind, number> => ({
  observed: 0,
  derived: 0,
  toolReported: 0,
  modelIo: 0,
  none: 0,
});

const toNumber = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

const normalizeLabel = (value: unknown): string | null => {
  const text = String(value ?? '').trim();
  return text ? text : null;
};

const keyFor = (value: string): string => value.trim().toLowerCase();

const signalFrom = (
  value: unknown,
  options: {
    label?: string | null;
    count?: number;
    source?: string;
    metadata?: Record<string, string | number | boolean | null>;
  } = {},
): Signal | null => {
  const keyLabel = normalizeLabel(value);
  if (!keyLabel) return null;
  return {
    key: keyFor(keyLabel),
    label: normalizeLabel(options.label) ?? keyLabel,
    count: options.count,
    source: options.source,
    metadata: options.metadata,
  };
};

const uniqueSignals = (signals: Array<Signal | null | undefined>): Signal[] => {
  const byKey = new Map<string, Signal>();
  signals.forEach(signal => {
    if (!signal) return;
    const existing = byKey.get(signal.key);
    if (!existing) {
      byKey.set(signal.key, { ...signal });
      return;
    }
    existing.count = toNumber(existing.count || 1) + toNumber(signal.count || 1);
    existing.metadata = { ...existing.metadata, ...signal.metadata };
  });
  return Array.from(byKey.values());
};

const flattenLogs = (logs: SessionLog[] | undefined): SessionLog[] => {
  const flattened: SessionLog[] = [];
  (logs || []).forEach(log => {
    flattened.push(log);
    if (log.subagentThread && log.subagentThread.length > 0) {
      flattened.push(...flattenLogs(log.subagentThread));
    }
  });
  return flattened;
};

const addDimension = (
  buckets: Map<string, DimensionBucket>,
  kind: AnalyticsDimensionKind,
  signal: Signal,
  contribution: {
    sessionId?: string;
    logCount?: number;
    workloadTokens?: number;
    costUsd?: number;
  } = {},
): void => {
  const bucket = buckets.get(signal.key) ?? {
    key: signal.key,
    label: signal.label,
    kind,
    count: 0,
    sessionIds: new Set<string>(),
    logCount: 0,
    workloadTokens: 0,
    costUsd: 0,
    metadata: {},
  };

  bucket.count += Math.max(1, toNumber(signal.count ?? 1));
  bucket.logCount += toNumber(contribution.logCount);
  bucket.workloadTokens += toNumber(contribution.workloadTokens);
  bucket.costUsd += toNumber(contribution.costUsd);
  if (contribution.sessionId) {
    bucket.sessionIds.add(contribution.sessionId);
  }
  if (signal.metadata) {
    Object.entries(signal.metadata).forEach(([key, value]) => {
      const existing = bucket.metadata[key];
      if (typeof existing === 'number' && typeof value === 'number') {
        bucket.metadata[key] = existing + value;
      } else if (existing === undefined || existing === null || existing === '') {
        bucket.metadata[key] = value;
      }
    });
  }

  buckets.set(signal.key, bucket);
};

const finalizeDimensions = (buckets: Map<string, DimensionBucket>): AnalyticsDimensionSummary[] => (
  Array.from(buckets.values())
    .map(bucket => ({
      key: bucket.key,
      label: bucket.label,
      kind: bucket.kind,
      count: bucket.count,
      sessionCount: bucket.sessionIds.size,
      logCount: bucket.logCount,
      workloadTokens: bucket.workloadTokens,
      costUsd: Number(bucket.costUsd.toFixed(6)),
      metadata: Object.keys(bucket.metadata).length > 0 ? bucket.metadata : undefined,
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
);

const sessionHasChildren = (sessionId: string, sessions: AgentSession[]): boolean => (
  sessions.some(candidate => (
    candidate.id !== sessionId
    && (
      candidate.parentSessionId === sessionId
      || candidate.subagentParentId === sessionId
      || candidate.forkParentSessionId === sessionId
    )
  ))
);

const sessionModelSignals = (session: AgentSession): Signal[] => {
  const fromModelsUsed = (session.modelsUsed || []).map(model => signalFrom(
    model.raw,
    {
      label: model.modelDisplayName || model.raw,
      metadata: {
        provider: model.modelProvider ?? null,
        family: model.modelFamily ?? null,
        version: model.modelVersion ?? null,
      },
    },
  ));
  const fallback = signalFrom(
    session.modelSlug || session.model,
    {
      label: session.modelDisplayName || session.modelSlug || session.model,
      metadata: {
        provider: session.modelProvider ?? null,
        family: session.modelFamily ?? null,
        version: session.modelVersion ?? null,
      },
    },
  );
  return uniqueSignals(fromModelsUsed.length > 0 ? fromModelsUsed : [fallback]);
};

const sessionAgentSignals = (session: AgentSession, logs: SessionLog[]): Signal[] => {
  const primaryAgents = [
    ...(session.agentsUsed || []),
    session.agentId,
    session.displayAgentType,
    session.subagentType,
  ];
  const logAgents = logs.map(log => log.agentName);
  return uniqueSignals([...primaryAgents, ...logAgents].map(value => signalFrom(value)));
};

const sessionSkillSignals = (session: AgentSession, logs: SessionLog[]): Signal[] => {
  const primarySkills = [
    ...(session.skillsUsed || []),
    session.skillName,
  ];
  const logSkills = logs.map(log => log.skillDetails?.name);
  return uniqueSignals([...primarySkills, ...logSkills].map(value => signalFrom(value)));
};

const sessionPhaseSignals = (session: AgentSession): Signal[] => uniqueSignals([
  ...(session.phaseHints || []).map(phase => signalFrom(phase)),
  ...(session.sessionMetadata?.relatedPhases || []).map(phase => signalFrom(phase)),
]);

const sessionTaskSignals = (session: AgentSession): Signal[] => uniqueSignals([
  signalFrom(session.taskId),
  ...(session.taskHints || []).map(task => signalFrom(task)),
]);

const toolSignals = (session: AgentSession, logs: SessionLog[]): Signal[] => {
  if (session.toolsUsed && session.toolsUsed.length > 0) {
    return uniqueSignals(session.toolsUsed.map(tool => signalFrom(
      tool.name,
      {
        count: tool.count,
        metadata: {
          category: tool.category ?? null,
          successRate: tool.successRate,
          totalMs: tool.totalMs ?? null,
        },
      },
    )));
  }
  return uniqueSignals(logs.map(log => signalFrom(log.toolCall?.name)));
};

const artifactSignals = (session: AgentSession): Signal[] => uniqueSignals(
  (session.linkedArtifacts || []).map(artifact => signalFrom(
    artifact.id || artifact.title,
    {
      label: artifact.title || artifact.id,
      metadata: {
        type: artifact.type,
        source: artifact.source,
      },
    },
  )),
);

const fileSignals = (session: AgentSession): Signal[] => {
  const updatedFiles = (session.updatedFiles || []).map(file => signalFrom(
    file.filePath,
    {
      metadata: {
        additions: toNumber(file.additions),
        deletions: toNumber(file.deletions),
        action: file.action,
        fileType: file.fileType,
      },
    },
  ));
  const relatedFile = signalFrom(session.sessionMetadata?.relatedFilePath);
  return uniqueSignals([...updatedFiles, relatedFile]);
};

export const buildSessionAnalyticsSummary = (sessions: AgentSession[]): SessionAnalyticsSummary => {
  const models = new Map<string, DimensionBucket>();
  const agents = new Map<string, DimensionBucket>();
  const skills = new Map<string, DimensionBucket>();
  const tools = new Map<string, DimensionBucket>();
  const artifacts = new Map<string, DimensionBucket>();
  const files = new Map<string, DimensionBucket>();
  const phases = new Map<string, DimensionBucket>();
  const tasks = new Map<string, DimensionBucket>();

  const totals: SessionAnalyticsTotals = {
    sessionCount: sessions.length,
    activeSessionCount: 0,
    completedSessionCount: 0,
    logCount: 0,
    durationSeconds: 0,
    costUsd: 0,
    toolUseCount: 0,
    artifactCount: 0,
    fileTouchCount: 0,
    tokens: {
      tokenInput: 0,
      tokenOutput: 0,
      modelIOTokens: 0,
      cacheInputTokens: 0,
      observedTokens: 0,
      toolReportedTokens: 0,
      workloadTokens: 0,
      workloadBySource: emptyWorkloadBySource(),
      toolFallbackSessionCount: 0,
    },
  };

  const sessionRows = sessions.map(session => {
    const logs = flattenLogs(session.logs);
    const tokens = resolveTokenMetrics(session, {
      hasLinkedSubthreads: sessionHasChildren(session.id, sessions),
    });
    const costUsd = resolveDisplayCost(session);
    const workloadTokens = tokens.workloadTokens;
    const toolUseCount = session.toolsUsed && session.toolsUsed.length > 0
      ? session.toolsUsed.reduce((sum, tool) => sum + Math.max(1, toNumber(tool.count)), 0)
      : logs.filter(log => Boolean(log.toolCall?.name)).length;
    const artifactCount = session.linkedArtifacts?.length ?? 0;
    const fileTouchCount = session.updatedFiles?.length ?? 0;

    totals.activeSessionCount += session.status === 'active' ? 1 : 0;
    totals.completedSessionCount += session.status === 'completed' ? 1 : 0;
    totals.logCount += logs.length;
    totals.durationSeconds += toNumber(session.durationSeconds);
    totals.costUsd += costUsd;
    totals.toolUseCount += toolUseCount;
    totals.artifactCount += artifactCount;
    totals.fileTouchCount += fileTouchCount;
    totals.tokens.tokenInput += tokens.tokenInput;
    totals.tokens.tokenOutput += tokens.tokenOutput;
    totals.tokens.modelIOTokens += tokens.modelIOTokens;
    totals.tokens.cacheInputTokens += tokens.cacheInputTokens;
    totals.tokens.observedTokens += tokens.observedTokens;
    totals.tokens.toolReportedTokens += tokens.toolReportedTokens;
    totals.tokens.workloadTokens += tokens.workloadTokens;
    totals.tokens.workloadBySource[tokens.workloadSource] += tokens.workloadTokens;
    totals.tokens.toolFallbackSessionCount += tokens.usedToolFallback ? 1 : 0;

    const contribution = {
      sessionId: session.id,
      logCount: logs.length,
      workloadTokens,
      costUsd,
    };

    sessionModelSignals(session).forEach(signal => addDimension(models, 'model', signal, contribution));
    sessionAgentSignals(session, logs).forEach(signal => addDimension(agents, 'agent', signal, contribution));
    sessionSkillSignals(session, logs).forEach(signal => addDimension(skills, 'skill', signal, contribution));
    toolSignals(session, logs).forEach(signal => addDimension(tools, 'tool', signal, contribution));
    artifactSignals(session).forEach(signal => addDimension(artifacts, 'artifact', signal, contribution));
    fileSignals(session).forEach(signal => addDimension(files, 'file', signal, contribution));
    sessionPhaseSignals(session).forEach(signal => addDimension(phases, 'phase', signal, contribution));
    sessionTaskSignals(session).forEach(signal => addDimension(tasks, 'task', signal, contribution));

    return {
      sessionId: session.id,
      title: session.title,
      status: session.status,
      startedAt: session.startedAt,
      endedAt: session.endedAt,
      durationSeconds: toNumber(session.durationSeconds),
      model: session.modelDisplayName || session.modelSlug || session.model,
      agents: sessionAgentSignals(session, logs).map(signal => signal.label),
      skills: sessionSkillSignals(session, logs).map(signal => signal.label),
      phaseHints: sessionPhaseSignals(session).map(signal => signal.label),
      taskHints: sessionTaskSignals(session).map(signal => signal.label),
      logCount: logs.length,
      toolUseCount,
      artifactCount,
      fileTouchCount,
      costUsd,
      tokens,
    };
  });

  totals.costUsd = Number(totals.costUsd.toFixed(6));

  return {
    totals,
    sessions: sessionRows,
    models: finalizeDimensions(models),
    agents: finalizeDimensions(agents),
    skills: finalizeDimensions(skills),
    tools: finalizeDimensions(tools),
    artifacts: finalizeDimensions(artifacts),
    files: finalizeDimensions(files),
    phases: finalizeDimensions(phases),
    tasks: finalizeDimensions(tasks),
  };
};

export const flattenPlanningSessionCards = (
  board?: PlanningAgentSessionBoard | null,
): PlanningAgentSessionCard[] => {
  if (!board?.groups) return [];
  const seen = new Set<string>();
  const cards: PlanningAgentSessionCard[] = [];
  board.groups.forEach(group => {
    (group.cards || []).forEach(card => {
      const key = normalizeLabel(card.sessionId);
      if (!key || seen.has(key)) return;
      seen.add(key);
      cards.push(card);
    });
  });
  return cards;
};

const addPlannedObserved = (
  buckets: Map<string, PlannedObservedBucket>,
  kind: PlannedObservedKind,
  side: 'planned' | 'observed',
  signal: Signal | null | undefined,
): void => {
  if (!signal) return;
  const bucket = buckets.get(signal.key) ?? {
    key: signal.key,
    label: signal.label,
    kind,
    plannedCount: 0,
    observedCount: 0,
    plannedSources: new Set<string>(),
    observedSources: new Set<string>(),
  };
  const count = Math.max(1, toNumber(signal.count ?? 1));
  if (side === 'planned') {
    bucket.plannedCount += count;
    if (signal.source) bucket.plannedSources.add(signal.source);
  } else {
    bucket.observedCount += count;
    if (signal.source) bucket.observedSources.add(signal.source);
  }
  buckets.set(signal.key, bucket);
};

const finalizePlannedObserved = (
  kind: PlannedObservedKind,
  buckets: Map<string, PlannedObservedBucket>,
): PlannedObservedAnalyticsGroup => {
  const items = Array.from(buckets.values())
    .map(bucket => ({
      key: bucket.key,
      label: bucket.label,
      kind: bucket.kind,
      planned: bucket.plannedCount > 0,
      observed: bucket.observedCount > 0,
      plannedCount: bucket.plannedCount,
      observedCount: bucket.observedCount,
      plannedSources: Array.from(bucket.plannedSources).sort(),
      observedSources: Array.from(bucket.observedSources).sort(),
    }))
    .sort((a, b) => {
      const aMatched = a.planned && a.observed ? 1 : 0;
      const bMatched = b.planned && b.observed ? 1 : 0;
      return bMatched - aMatched
        || (b.plannedCount + b.observedCount) - (a.plannedCount + a.observedCount)
        || a.label.localeCompare(b.label);
    });

  return {
    kind,
    plannedCount: items.filter(item => item.planned).length,
    observedCount: items.filter(item => item.observed).length,
    matchedCount: items.filter(item => item.planned && item.observed).length,
    plannedOnlyCount: items.filter(item => item.planned && !item.observed).length,
    observedOnlyCount: items.filter(item => !item.planned && item.observed).length,
    items,
  };
};

const phaseSignalFromCard = (card: PlanningAgentSessionCard): Signal | null => {
  const correlation = card.correlation;
  if (!correlation) return null;
  if (correlation.phaseNumber !== undefined && correlation.phaseNumber !== null) {
    const label = correlation.phaseTitle
      ? `Phase ${correlation.phaseNumber}: ${correlation.phaseTitle}`
      : `Phase ${correlation.phaseNumber}`;
    return signalFrom(`phase:${correlation.phaseNumber}`, { label, source: `session:${card.sessionId}` });
  }
  return signalFrom(correlation.phaseTitle, { source: `session:${card.sessionId}` });
};

const phaseSignalFromRow = (
  phaseNumber: number | null | undefined,
  name: string | null | undefined,
  source: string,
): Signal | null => {
  if (phaseNumber !== undefined && phaseNumber !== null) {
    const label = normalizeLabel(name)
      ? `Phase ${phaseNumber}: ${normalizeLabel(name)}`
      : `Phase ${phaseNumber}`;
    return signalFrom(`phase:${phaseNumber}`, { label, source });
  }
  return signalFrom(name, { source });
};

const artifactRefSignals = (refs: Array<PlanningArtifactRef[] | undefined>): Signal[] => uniqueSignals(
  refs.flatMap(group => (group || []).map(ref => signalFrom(
    ref.artifactId || ref.canonicalPath || ref.filePath,
    {
      label: ref.title || ref.filePath,
      metadata: {
        docType: ref.docType,
        status: ref.status,
      },
    },
  ))),
);

export const buildFeatureAnalyticsSummary = (
  input: FeatureAnalyticsSummaryInput,
): FeatureAnalyticsSummary => {
  const featureContext = input.featureContext ?? null;
  const commandCenterItem = input.commandCenterItem ?? null;
  const sessionCards = input.sessionCards || [];

  const plannedAgents = new Map<string, PlannedObservedBucket>();
  const plannedSkills = new Map<string, PlannedObservedBucket>();
  const plannedModels = new Map<string, PlannedObservedBucket>();
  const plannedTasks = new Map<string, PlannedObservedBucket>();
  const phaseBuckets = new Map<string, DimensionBucket>();
  const fileBuckets = new Map<string, DimensionBucket>();
  const artifactBuckets = new Map<string, DimensionBucket>();

  (featureContext?.graph?.phaseBatches || []).forEach(batch => {
    (batch.assignedAgents || []).forEach(agent => {
      addPlannedObserved(plannedAgents, 'agent', 'planned', signalFrom(agent, { source: `batch:${batch.batchId}` }));
    });
    (batch.taskIds || []).forEach(taskId => {
      addPlannedObserved(plannedTasks, 'task', 'planned', signalFrom(taskId, { source: `batch:${batch.batchId}` }));
    });
    (batch.fileScopeHints || []).forEach(filePath => {
      const signal = signalFrom(filePath, { source: `batch:${batch.batchId}` });
      if (signal) addDimension(fileBuckets, 'file', signal);
    });
    const phaseSignal = signalFrom(batch.phase, { source: `batch:${batch.batchId}` });
    if (phaseSignal) addDimension(phaseBuckets, 'phase', phaseSignal);
  });

  (featureContext?.phases || []).forEach(phase => {
    const phaseSignal = phaseSignalFromRow(phase.phaseNumber, phase.phaseTitle, `phase:${phase.phaseId}`);
    if (phaseSignal) {
      addDimension(phaseBuckets, 'phase', phaseSignal, { logCount: phase.totalTasks });
    }
    Object.entries(phase.linkedSessionsByPhase || {}).forEach(([phaseNumber, links]) => {
      const linkedPhase = phaseSignalFromRow(Number(phaseNumber), phase.phaseTitle, `phase:${phase.phaseId}`);
      if (linkedPhase) {
        addDimension(phaseBuckets, 'phase', linkedPhase, { logCount: links.length });
      }
      links.forEach(link => {
        addPlannedObserved(plannedAgents, 'agent', 'observed', signalFrom(link.agentName, {
          source: `linked-session:${link.sessionId}`,
        }));
      });
    });
  });

  (commandCenterItem?.phaseRows || []).forEach(row => {
    const phaseSignal = phaseSignalFromRow(row.phaseNumber, row.name, 'command-center:phase-row');
    if (phaseSignal) addDimension(phaseBuckets, 'phase', phaseSignal, { logCount: row.linkedSessions?.length ?? 0 });
    (row.agents || []).forEach(agent => {
      addPlannedObserved(plannedAgents, 'agent', 'planned', signalFrom(agent, { source: 'command-center:phase-row' }));
    });
    addPlannedObserved(plannedModels, 'model', 'planned', signalFrom(row.model, { source: 'command-center:phase-row' }));
    (row.phaseFiles || []).forEach(filePath => {
      const signal = signalFrom(filePath, { source: 'command-center:phase-row' });
      if (signal) addDimension(fileBuckets, 'file', signal);
    });
  });

  (commandCenterItem?.launchBatch?.agents || []).forEach(agent => {
    addPlannedObserved(plannedAgents, 'agent', 'planned', signalFrom(agent.label || agent.agentId, {
      source: 'command-center:launch-batch',
    }));
    (agent.skills || []).forEach(skill => {
      addPlannedObserved(plannedSkills, 'skill', 'planned', signalFrom(skill, {
        source: `launch-agent:${agent.agentId}`,
      }));
    });
  });

  (commandCenterItem?.relatedFiles || []).forEach(file => {
    const signal = signalFrom(file.path, {
      source: 'command-center:related-file',
      metadata: {
        docType: file.docType,
        sizeBytes: file.sizeBytes ?? null,
      },
    });
    if (signal) addDimension(fileBuckets, 'file', signal);
  });

  (commandCenterItem?.artifacts || []).forEach(artifact => {
    const signal = signalFrom(artifact.artifactId || artifact.path, {
      label: artifact.title || artifact.path,
      source: 'command-center:artifact',
      metadata: {
        docType: artifact.docType,
        status: artifact.status,
        exists: artifact.exists ?? null,
      },
    });
    if (signal) addDimension(artifactBuckets, 'artifact', signal);
  });

  const targetArtifactSignal = signalFrom(commandCenterItem?.targetArtifact?.path, {
    label: commandCenterItem?.targetArtifact?.title,
    source: 'command-center:target-artifact',
    metadata: {
      docType: commandCenterItem?.targetArtifact?.docType ?? null,
      exists: commandCenterItem?.targetArtifact?.exists ?? null,
    },
  });
  if (targetArtifactSignal) addDimension(artifactBuckets, 'artifact', targetArtifactSignal);

  artifactRefSignals([
    featureContext?.specs,
    featureContext?.prds,
    featureContext?.plans,
    featureContext?.ctxs,
    featureContext?.reports,
  ]).forEach(signal => addDimension(artifactBuckets, 'artifact', signal));

  const totals: FeatureAnalyticsTotals = {
    sessionCount: sessionCards.length,
    activeSessionCount: 0,
    completedSessionCount: 0,
    failedSessionCount: 0,
    durationSeconds: 0,
    totalTokens: 0,
    tokenInput: 0,
    tokenOutput: 0,
    phaseCount: 0,
    taskCount: 0,
  };

  const sessionRows = sessionCards.map(card => {
    const tokenInput = toNumber(card.tokenSummary?.tokensIn);
    const tokenOutput = toNumber(card.tokenSummary?.tokensOut);
    const totalTokens = toNumber(card.tokenSummary?.totalTokens) || (tokenInput + tokenOutput);
    const durationSeconds = toNumber(card.durationSeconds);
    const isActive = card.state === 'running' || card.state === 'thinking';

    totals.activeSessionCount += isActive ? 1 : 0;
    totals.completedSessionCount += card.state === 'completed' ? 1 : 0;
    totals.failedSessionCount += card.state === 'failed' ? 1 : 0;
    totals.durationSeconds += durationSeconds;
    totals.totalTokens += totalTokens;
    totals.tokenInput += tokenInput;
    totals.tokenOutput += tokenOutput;

    addPlannedObserved(plannedAgents, 'agent', 'observed', signalFrom(card.agentName || card.agentType, {
      source: `session:${card.sessionId}`,
    }));
    addPlannedObserved(plannedModels, 'model', 'observed', signalFrom(card.model || card.tokenSummary?.model, {
      source: `session:${card.sessionId}`,
    }));
    addPlannedObserved(plannedTasks, 'task', 'observed', signalFrom(card.correlation?.taskId, {
      label: card.correlation?.taskTitle || card.correlation?.taskId,
      source: `session:${card.sessionId}`,
    }));
    const phaseSignal = phaseSignalFromCard(card);
    if (phaseSignal) {
      addDimension(phaseBuckets, 'phase', phaseSignal, {
        sessionId: card.sessionId,
        workloadTokens: totalTokens,
      });
    }

    return {
      sessionId: card.sessionId,
      state: card.state,
      agentName: card.agentName,
      agentType: card.agentType,
      model: card.model || card.tokenSummary?.model,
      phaseNumber: card.correlation?.phaseNumber,
      phaseTitle: card.correlation?.phaseTitle,
      taskId: card.correlation?.taskId,
      taskTitle: card.correlation?.taskTitle,
      startedAt: card.startedAt,
      lastActivityAt: card.lastActivityAt,
      durationSeconds,
      totalTokens,
      tokenInput,
      tokenOutput,
    };
  });

  if (featureContext?.tokenUsageByModel) {
    Object.entries(featureContext.tokenUsageByModel).forEach(([model, total]) => {
      if (model === 'total' || toNumber(total) <= 0) return;
      addPlannedObserved(plannedModels, 'model', 'observed', signalFrom(model, {
        count: toNumber(total),
        source: 'feature-context:token-usage',
      }));
    });
  }

  totals.phaseCount = finalizeDimensions(phaseBuckets).length;
  totals.taskCount = finalizePlannedObserved('task', plannedTasks).items.length;

  return {
    featureId: featureContext?.featureId ?? commandCenterItem?.feature.featureId,
    featureName: featureContext?.featureName ?? commandCenterItem?.feature.name,
    totals,
    sessionCards: sessionRows,
    plannedVsObserved: {
      agents: finalizePlannedObserved('agent', plannedAgents),
      skills: finalizePlannedObserved('skill', plannedSkills),
      models: finalizePlannedObserved('model', plannedModels),
      tasks: finalizePlannedObserved('task', plannedTasks),
    },
    phases: finalizeDimensions(phaseBuckets),
    files: finalizeDimensions(fileBuckets),
    artifacts: finalizeDimensions(artifactBuckets),
  };
};
