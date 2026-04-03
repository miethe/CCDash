import type {
  SessionIntelligenceCapability,
  SessionIntelligenceConcernSummary,
  SessionIntelligenceSessionRollup,
} from '../types';
import type { RuntimeStatus } from '../services/runtimeProfile';

export type IntelligenceAvailabilityKind = 'available' | 'unsupported' | 'degraded';

export interface IntelligenceAvailability {
  kind: IntelligenceAvailabilityKind;
  title: string;
  message: string;
}

export interface AggregatedConcernSummary {
  label: string;
  averageScore: number;
  averageConfidence: number;
  flaggedSessions: number;
  factCount: number;
}

export interface AggregatedSessionIntelligence {
  sessionCount: number;
  featureIds: string[];
  representativeSessionIds: string[];
  sentiment: AggregatedConcernSummary;
  churn: AggregatedConcernSummary;
  scopeDrift: AggregatedConcernSummary;
}

const DEFAULT_CONCERN: AggregatedConcernSummary = {
  label: 'No data',
  averageScore: 0,
  averageConfidence: 0,
  flaggedSessions: 0,
  factCount: 0,
};

const STORAGE_PROFILE_LABELS: Record<string, string> = {
  local: 'local',
  enterprise: 'enterprise',
  unknown: 'current',
};

const concernSeverity = (concern: SessionIntelligenceConcernSummary): number =>
  Math.abs(Number(concern.score || 0)) + (Number(concern.flaggedCount || 0) * 0.25);

const summarizeConcern = (
  items: SessionIntelligenceSessionRollup[],
  selector: (item: SessionIntelligenceSessionRollup) => SessionIntelligenceConcernSummary,
): AggregatedConcernSummary => {
  if (items.length === 0) return DEFAULT_CONCERN;

  const totals = items.reduce(
    (acc, item) => {
      const concern = selector(item);
      acc.score += Number(concern.score || 0);
      acc.confidence += Number(concern.confidence || 0);
      acc.flaggedSessions += Number(concern.flaggedCount || 0) > 0 ? 1 : 0;
      acc.factCount += Number(concern.factCount || 0);
      return acc;
    },
    { score: 0, confidence: 0, flaggedSessions: 0, factCount: 0 },
  );

  const lead = [...items]
    .map(selector)
    .sort((a, b) => concernSeverity(b) - concernSeverity(a))[0];

  return {
    label: lead?.label || 'No data',
    averageScore: totals.score / items.length,
    averageConfidence: totals.confidence / items.length,
    flaggedSessions: totals.flaggedSessions,
    factCount: totals.factCount,
  };
};

export const formatConcernLabel = (value: string | null | undefined): string => {
  const normalized = String(value || '').trim().replace(/_/g, ' ');
  if (!normalized) return 'Unknown';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

export const formatConcernScore = (value: number): string => {
  const numeric = Number(value || 0);
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}`;
};

export const aggregateSessionIntelligence = (
  items: SessionIntelligenceSessionRollup[],
): AggregatedSessionIntelligence => ({
  sessionCount: items.length,
  featureIds: Array.from(new Set(items.map(item => item.featureId).filter(Boolean))).slice(0, 8),
  representativeSessionIds: [...items]
    .sort((a, b) => {
      const severityA = concernSeverity(a.sentiment) + concernSeverity(a.churn) + concernSeverity(a.scopeDrift);
      const severityB = concernSeverity(b.sentiment) + concernSeverity(b.churn) + concernSeverity(b.scopeDrift);
      return severityB - severityA;
    })
    .map(item => item.sessionId)
    .slice(0, 5),
  sentiment: summarizeConcern(items, item => item.sentiment),
  churn: summarizeConcern(items, item => item.churn),
  scopeDrift: summarizeConcern(items, item => item.scopeDrift),
});

export const describeIntelligenceAvailability = (
  runtimeStatus: RuntimeStatus | null | undefined,
  capability?: SessionIntelligenceCapability | null,
): IntelligenceAvailability => {
  if (capability && capability.supported) {
    if (capability.authoritative) {
      return {
        kind: 'available',
        title: 'Enterprise intelligence available',
        message: capability.detail || 'Canonical transcript intelligence is available for this workspace.',
      };
    }
    return {
      kind: 'degraded',
      title: 'Fallback intelligence mode',
      message: capability.detail || 'CCDash is serving a non-authoritative transcript intelligence fallback.',
    };
  }

  const storageProfile = String(runtimeStatus?.storageProfile || 'unknown').trim().toLowerCase() || 'unknown';
  const storageLabel = STORAGE_PROFILE_LABELS[storageProfile] || storageProfile;

  if (storageProfile === 'local') {
    return {
      kind: 'unsupported',
      title: 'Enterprise-only capability',
      message: 'Transcript intelligence search and derived evidence are unavailable in local storage mode.',
    };
  }

  return {
    kind: 'degraded',
    title: 'Intelligence unavailable',
    message: `CCDash could not load transcript intelligence from the ${storageLabel} storage profile.`,
  };
};
