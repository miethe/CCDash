import React, { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  ExternalLink,
  Info,
  Link2,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';

import {
  ExecutionArtifactReference,
  FeatureExecutionWarning,
  RecommendedStack,
  RecommendedStackComponent,
  SimilarWorkExample,
  StackRecommendationEvidence,
} from '../../types';
import { ArtifactReferenceModal } from './ArtifactReferenceModal';

interface RecommendedStackCardProps {
  recommendedStack?: RecommendedStack | null;
  stackAlternatives: RecommendedStack[];
  stackEvidence: StackRecommendationEvidence[];
  definitionResolutionWarnings: FeatureExecutionWarning[];
  onOpenSession: (sessionId: string) => void;
  onOpenFeature?: (featureId: string) => void;
}

interface ReferenceChipData {
  key: string;
  label: string;
  status: 'resolved' | 'cached' | 'unresolved';
  definitionType: string;
  externalId: string;
  version: string;
  sourceUrl: string;
  reference: ExecutionArtifactReference;
}

interface InsightMetric {
  label: string;
  value: string;
  tone?: 'default' | 'success' | 'warning' | 'info';
}

interface InsightAction {
  label: string;
  url: string;
}

interface InsightTag {
  label: string;
  url?: string;
}

interface InsightSection {
  key: string;
  title: string;
  summary: string;
  metrics: InsightMetric[];
  actions: InsightAction[];
  tags: InsightTag[];
  footnote?: string;
}

const COMPONENT_GROUPS: Array<{ key: RecommendedStackComponent['componentType']; label: string; multiple: boolean }> = [
  { key: 'workflow', label: 'Workflow', multiple: false },
  { key: 'agent', label: 'Agent', multiple: true },
  { key: 'skill', label: 'Skills', multiple: true },
  { key: 'context_module', label: 'Context Modules', multiple: true },
  { key: 'artifact', label: 'Artifacts', multiple: true },
  { key: 'command', label: 'Commands', multiple: true },
  { key: 'model_policy', label: 'Model Policies', multiple: true },
];

const formatPercent = (value: number): string => `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;
const formatCurrency = (value: number): string => `$${Number(value || 0).toFixed(2)}`;
const asNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};
const asString = (value: unknown): string => (typeof value === 'string' ? value : '');
const asArray = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const formatDuration = (seconds: number): string => {
  const total = Math.max(0, Number(seconds || 0));
  if (total >= 3600) return `${(total / 3600).toFixed(1)}h`;
  if (total >= 60) return `${Math.round(total / 60)}m`;
  return `${Math.round(total)}s`;
};

const formatDateTime = (value: string): string => {
  if (!value) return 'Unknown';
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
};

const statusChipClass = (status: 'resolved' | 'cached' | 'unresolved'): string => {
  if (status === 'resolved') return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-100';
  if (status === 'cached') return 'border-sky-500/35 bg-sky-500/10 text-sky-100';
  return 'border-amber-500/35 bg-amber-500/10 text-amber-100';
};

const outcomeTone = (item: SimilarWorkExample): { label: string; className: string } => {
  if (item.successScore >= 0.75 && item.riskScore <= 0.35) {
    return { label: 'Success', className: 'text-emerald-300' };
  }
  if (item.successScore >= 0.5 && item.riskScore <= 0.6) {
    return { label: 'Partial', className: 'text-amber-300' };
  }
  return { label: 'Failed', className: 'text-rose-300' };
};

const getReferenceLabel = (component: RecommendedStackComponent): string => {
  if (component.definition?.displayName) return component.definition.displayName;
  return component.label || component.componentKey || 'local-only';
};

const compactUnique = (values: string[]): string[] => {
  const seen = new Set<string>();
  return values.filter(value => {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
};

const getReferenceData = (component: RecommendedStackComponent): ReferenceChipData => {
  const fallbackReference: ExecutionArtifactReference = component.artifactRef || {
    key: `${component.componentType}:${component.componentKey}`,
    label: component.label || component.componentKey || 'local-only',
    kind: component.componentType,
    status: component.status === 'resolved' ? 'resolved' : 'unresolved',
    definitionType: component.definition?.definitionType || '',
    externalId: component.definition?.externalId || component.componentKey,
    sourceUrl: component.definition?.sourceUrl || '',
    sourceAttribution: component.sourceAttribution || '',
    description: '',
    metadata: component.payload || {},
  };
  if (component.definition) {
    return {
      key: `${component.componentType}:${component.definition.externalId || component.componentKey}`,
      label: component.definition.displayName || component.label || component.componentKey,
      status: component.definition.status,
      definitionType: component.definition.definitionType,
      externalId: component.definition.externalId,
      version: component.definition.version,
      sourceUrl: component.definition.sourceUrl,
      reference: {
        ...fallbackReference,
        key: component.definition.externalId || fallbackReference.key,
        label: component.definition.displayName || fallbackReference.label,
        status: component.definition.status,
        definitionType: component.definition.definitionType,
        externalId: component.definition.externalId,
        sourceUrl: component.definition.sourceUrl,
      },
    };
  }

  return {
    key: `${component.componentType}:${component.componentKey}`,
    label: component.label || component.componentKey || 'local-only',
    status: component.status === 'resolved' ? 'resolved' : 'unresolved',
    definitionType: component.componentType,
    externalId: component.componentKey,
    version: '',
    sourceUrl: '',
    reference: fallbackReference,
  };
};

const openExternalUrl = (url: string) => {
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
};

const insightMetricToneClass = (tone: InsightMetric['tone']): string => {
  if (tone === 'success') return 'text-emerald-200';
  if (tone === 'warning') return 'text-amber-200';
  if (tone === 'info') return 'text-sky-200';
  return 'text-slate-100';
};

const buildInsightSections = (stackEvidence: StackRecommendationEvidence[]): InsightSection[] => {
  const sections: InsightSection[] = [];

  stackEvidence.forEach(evidence => {
    const metrics = evidence.metrics || {};

    if (evidence.sourceType === 'context_preview') {
      const resolvedContexts = asArray<Record<string, unknown>>(metrics.resolvedContexts);
      const tags = resolvedContexts
        .filter(item => asString(item.moduleName) || asString(item.contextRef))
        .slice(0, 4)
        .map(item => ({
          label: asString(item.moduleName) || asString(item.contextRef) || 'Context',
          url: asString(item.sourceUrl) || undefined,
        }));
      const actions = compactUnique(resolvedContexts.map(item => asString(item.sourceUrl))).map(url => ({
        label: 'Open memory',
        url,
      }));
      sections.push({
        key: evidence.id || evidence.sourceType,
        title: 'Context Coverage',
        summary: evidence.summary,
        metrics: [
          { label: 'Resolved', value: `${asNumber(metrics.resolved)}/${Math.max(1, asNumber(metrics.referenced))}`, tone: 'success' },
          { label: 'Previewed', value: String(asNumber(metrics.previewed)), tone: 'info' },
          { label: 'Token Footprint', value: `${asNumber(metrics.previewTokenFootprint)} tok`, tone: 'warning' },
        ],
        actions,
        tags,
      });
      return;
    }

    if (evidence.sourceType === 'bundle_alignment') {
      const bundleName = asString(metrics.bundleName) || asString(metrics.bundleId) || 'Curated bundle';
      const matchedRefs = asArray<string>(metrics.matchedRefs).slice(0, 4).map(ref => ({ label: ref }));
      const sourceUrl = asString(metrics.sourceUrl);
      sections.push({
        key: evidence.id || evidence.sourceType,
        title: bundleName,
        summary: evidence.summary,
        metrics: [
          { label: 'Bundle Fit', value: formatPercent(asNumber(metrics.matchScore)), tone: 'success' },
          { label: 'Matched Refs', value: String(asArray<string>(metrics.matchedRefs).length), tone: 'info' },
        ],
        actions: sourceUrl ? [{ label: 'Open curated bundle', url: sourceUrl }] : [],
        tags: matchedRefs,
      });
      return;
    }

    if (evidence.sourceType === 'workflow_execution') {
      const active = asNumber(metrics.active);
      const hint = asString(metrics.liveUpdateHint);
      const sourceUrl = asString(metrics.sourceUrl);
      sections.push({
        key: evidence.id || evidence.sourceType,
        title: 'Execution Awareness',
        summary: evidence.summary,
        metrics: [
          { label: 'Recent Runs', value: String(asNumber(metrics.count)), tone: 'info' },
          { label: 'Completed', value: String(asNumber(metrics.completed)), tone: 'success' },
          { label: 'Active', value: String(active), tone: active > 0 ? 'warning' : 'default' },
        ],
        actions: sourceUrl ? [{ label: 'Open executions', url: sourceUrl }] : [],
        tags: active > 0 ? [{ label: `${active} active execution${active === 1 ? '' : 's'}` }] : [],
        footnote: hint === 'view_scoped_polling' ? 'Live refresh is available while this workflow is in view.' : undefined,
      });
    }
  });

  return sections;
};

const buildHeadlineTags = (stackEvidence: StackRecommendationEvidence[]): InsightTag[] => {
  const tags: InsightTag[] = [];

  stackEvidence.forEach(evidence => {
    const metrics = evidence.metrics || {};
    if (evidence.sourceType === 'effective_workflow') {
      tags.push({
        label: 'Effective workflow',
        url: asString(metrics.sourceUrl) || undefined,
      });
      return;
    }
    if (evidence.sourceType === 'bundle_alignment') {
      const bundleName = asString(metrics.bundleName) || asString(metrics.bundleId);
      if (bundleName) {
        tags.push({
          label: `Bundle: ${bundleName}`,
          url: asString(metrics.sourceUrl) || undefined,
        });
      }
      return;
    }
    if (evidence.sourceType === 'workflow_execution') {
      const active = asNumber(metrics.active);
      const count = asNumber(metrics.count);
      if (active > 0) {
        tags.push({ label: `${active} active execution${active === 1 ? '' : 's'}` });
      } else if (count > 0) {
        tags.push({ label: `${count} recent execution${count === 1 ? '' : 's'}` });
      }
      return;
    }
    if (evidence.sourceType === 'context_preview') {
      const previewed = asNumber(metrics.previewed);
      if (previewed > 0) {
        tags.push({ label: `${previewed} context preview${previewed === 1 ? '' : 's'}` });
      }
    }
  });

  return tags.slice(0, 4);
};

const DefinitionChip: React.FC<{ reference: ReferenceChipData; fullWidth?: boolean; onOpenReference: (reference: ExecutionArtifactReference) => void }> = ({
  reference,
  fullWidth = false,
  onOpenReference,
}) => {
  const content = (
    <span className={`inline-flex min-w-0 max-w-full items-start gap-2 overflow-hidden rounded-xl border px-3 py-2 text-xs leading-4 ${fullWidth ? 'w-full justify-between' : ''} ${statusChipClass(reference.status)}`}>
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${reference.status === 'resolved' ? 'bg-emerald-300' : reference.status === 'cached' ? 'bg-sky-300' : 'bg-amber-300'}`} />
      <span className="min-w-0 flex-1 break-words text-left [overflow-wrap:anywhere]">{reference.label}</span>
      {reference.sourceUrl ? <ExternalLink size={12} className="shrink-0" /> : <Info size={12} className="shrink-0" />}
    </span>
  );
  return (
    <button
      onClick={() => onOpenReference(reference.reference)}
      className={fullWidth ? 'w-full text-left' : 'text-left'}
    >
      {content}
    </button>
  );
};

const StackStatCard: React.FC<{
  label: string;
  value: string;
  tone?: 'default' | 'success' | 'info' | 'warning';
}> = ({ label, value, tone = 'default' }) => (
  <div className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
    <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">{label}</div>
    <div
      className={`mt-1 text-lg font-semibold [overflow-wrap:anywhere] ${
        tone === 'success'
          ? 'text-emerald-200'
          : tone === 'info'
            ? 'text-sky-200'
            : tone === 'warning'
              ? 'text-amber-200'
              : 'text-slate-100'
      }`}
    >
      {value}
    </div>
  </div>
);

const InsightCard: React.FC<{ section: InsightSection }> = ({ section }) => (
  <div className="min-w-0 overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/50 p-4">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="text-base font-semibold text-slate-100 [overflow-wrap:anywhere]">{section.title}</div>
        <div className="mt-1 text-sm leading-6 text-slate-400 [overflow-wrap:anywhere]">{section.summary}</div>
      </div>
      <div className="w-fit shrink-0 rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-slate-400">
        Insight
      </div>
    </div>

    <div className="mt-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
      {section.metrics.map(metric => (
        <div key={`${section.key}-${metric.label}`} className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-500">{metric.label}</div>
          <div className={`mt-1 text-lg font-semibold [overflow-wrap:anywhere] ${insightMetricToneClass(metric.tone)}`}>{metric.value}</div>
        </div>
      ))}
    </div>

    {section.tags.length > 0 && (
      <div className="mt-4 flex flex-wrap gap-2">
        {section.tags.map(tag => (
          tag.url ? (
            <button
              key={`${section.key}-${tag.label}`}
              onClick={() => openExternalUrl(tag.url || '')}
              className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-sky-200 hover:border-slate-500 hover:text-sky-100"
            >
              {tag.label}
              <ExternalLink size={12} />
            </button>
          ) : (
            <span key={`${section.key}-${tag.label}`} className="inline-flex items-center rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300">
              {tag.label}
            </span>
          )
        ))}
      </div>
    )}

    {(section.actions.length > 0 || section.footnote) && (
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {section.actions.map(action => (
          <button
            key={`${section.key}-${action.label}`}
            onClick={() => openExternalUrl(action.url)}
            className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-100 hover:bg-sky-500/20"
          >
            {action.label}
            <ExternalLink size={12} />
          </button>
        ))}
        {section.footnote && (
          <span className="text-xs text-slate-500">{section.footnote}</span>
        )}
      </div>
    )}
  </div>
);

const SimilarWorkModal: React.FC<{
  evidence: StackRecommendationEvidence;
  onClose: () => void;
  onOpenSession: (sessionId: string) => void;
  onOpenFeature?: (featureId: string) => void;
}> = ({ evidence, onClose, onOpenSession, onOpenFeature }) => {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[85] bg-slate-950/80 backdrop-blur-sm px-4 py-8" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Similar past work"
        className="mx-auto max-h-full w-full max-w-3xl overflow-y-auto rounded-[28px] border border-slate-700 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.16),_rgba(15,23,42,0.96)_45%,_rgba(2,6,23,0.99)_100%)] shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <div className="font-mono text-2xl text-slate-100">Similar Past Work</div>
            <p className="mt-2 text-sm text-slate-400">{evidence.summary}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700 p-2 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
            aria-label="Close similar work modal"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-5">
          {evidence.similarWork.map(item => {
            const outcome = outcomeTone(item);
            return (
              <div key={item.sessionId} className="rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-lg text-slate-100">{item.title || item.sessionId}</div>
                    <div className="mt-1 text-sm text-slate-500">{formatDateTime(item.startedAt)}</div>
                  </div>
                  <div className={`inline-flex items-center gap-2 text-sm ${outcome.className}`}>
                    <span className="h-2.5 w-2.5 rounded-full bg-current" />
                    {outcome.label}
                  </div>
                </div>

                <div className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
                  <div>
                    Feature:{' '}
                    {item.featureId ? (
                      <button
                        onClick={() => onOpenFeature?.(item.featureId)}
                        className="font-mono text-sky-200 underline decoration-slate-600 underline-offset-4"
                      >
                        {item.featureId}
                      </button>
                    ) : (
                      <span className="font-mono text-slate-400">n/a</span>
                    )}
                  </div>
                  <div>Workflow: <span className="font-mono text-slate-200">{item.workflowRef || 'unknown'}</span></div>
                  <div>Similarity: <span className="rounded-full bg-slate-800 px-2 py-0.5 font-mono text-slate-100">{formatPercent(item.similarityScore)} similar</span></div>
                  <div>Cost: <span className="font-mono text-slate-200">{formatCurrency(item.totalCost)}</span></div>
                </div>

                {item.matchedComponents.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.matchedComponents.map(component => (
                      <span key={`${item.sessionId}-${component}`} className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-300">
                        {component}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-400 md:grid-cols-4">
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-slate-500">Duration</div>
                    <div className="mt-1 font-mono text-slate-200">{formatDuration(item.durationSeconds)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-slate-500">Success</div>
                    <div className="mt-1 font-mono text-slate-200">{formatPercent(item.successScore)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-slate-500">Quality</div>
                    <div className="mt-1 font-mono text-slate-200">{formatPercent(item.qualityScore)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-slate-500">Risk</div>
                    <div className="mt-1 font-mono text-slate-200">{formatPercent(item.riskScore)}</div>
                  </div>
                </div>

                {item.reasons.length > 0 && (
                  <div className="mt-4 text-sm text-slate-400">
                    {item.reasons.join(' • ')}
                  </div>
                )}

                <button
                  onClick={() => onOpenSession(item.sessionId)}
                  className="mt-4 text-sm text-sky-200 underline decoration-slate-600 underline-offset-4 hover:text-sky-100"
                >
                  View Session
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export const RecommendedStackCard: React.FC<RecommendedStackCardProps> = ({
  recommendedStack,
  stackAlternatives = [],
  stackEvidence = [],
  definitionResolutionWarnings = [],
  onOpenSession,
  onOpenFeature,
}) => {
  const [activeEvidence, setActiveEvidence] = useState<StackRecommendationEvidence | null>(null);
  const [activeReference, setActiveReference] = useState<ExecutionArtifactReference | null>(null);

  const groupedComponents = useMemo(() => {
    const groups = new Map<string, RecommendedStackComponent[]>();
    (recommendedStack?.components || []).forEach(component => {
      const key = component.componentType;
      const existing = groups.get(key) || [];
      groups.set(key, [...existing, component]);
    });
    return groups;
  }, [recommendedStack?.components]);

  const referenceChips = useMemo(() => {
    const unique = new Map<string, ReferenceChipData>();
    (recommendedStack?.components || []).forEach(component => {
      const reference = getReferenceData(component);
      if (!unique.has(reference.key)) unique.set(reference.key, reference);
    });
    return Array.from(unique.values());
  }, [recommendedStack?.components]);

  const insightSections = useMemo(
    () => buildInsightSections(stackEvidence),
    [stackEvidence],
  );

  const headlineTags = useMemo(
    () => buildHeadlineTags(stackEvidence),
    [stackEvidence],
  );
  const workflowReference = useMemo(
    () => recommendedStack?.components.find(component => component.componentType === 'workflow')?.artifactRef || null,
    [recommendedStack?.components],
  );

  if (!recommendedStack) {
    return (
      <section className="rounded-[28px] border border-slate-800/80 bg-slate-900/80 p-5 shadow-[0_24px_70px_rgba(2,6,23,0.18)]">
        <div className="flex items-start gap-3">
          <ShieldAlert size={18} className="mt-0.5 text-amber-300" />
          <div>
            <h3 className="text-xl font-semibold tracking-tight text-slate-100">Recommended Stack</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Historical stack guidance is not available for this feature yet. Command recommendations remain active.
            </p>
            {definitionResolutionWarnings.length > 0 && (
              <div className="mt-4 space-y-2">
                {definitionResolutionWarnings.map((warning, index) => (
                  <div key={`${warning.section}-${index}`} className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    {warning.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="rounded-[28px] border border-slate-800/80 bg-slate-900/80 p-5 shadow-[0_24px_70px_rgba(2,6,23,0.2)]">
        <div className="flex items-start gap-4">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-100">
              <Sparkles size={12} />
              Historical Match
            </div>
            <h3 className="mt-3 text-xl font-semibold tracking-tight text-slate-100 md:text-2xl">Recommended Stack</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {recommendedStack.explanation || recommendedStack.commandAlignment || 'Historical execution signals were matched against related work to suggest the best-fit stack.'}
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.18fr)_minmax(20rem,0.82fr)]">
          <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/50 p-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Workflow</div>
                {workflowReference ? (
                  <button
                    onClick={() => setActiveReference(workflowReference)}
                    className="mt-2 text-left text-lg font-semibold text-sky-200 underline decoration-slate-600 underline-offset-4 [overflow-wrap:anywhere]"
                  >
                    {recommendedStack.workflowRef || recommendedStack.label}
                  </button>
                ) : (
                  <div className="mt-2 text-lg font-semibold text-slate-100 [overflow-wrap:anywhere]">
                    {recommendedStack.workflowRef || recommendedStack.label}
                  </div>
                )}
                <p className="mt-2 text-sm leading-6 text-slate-400 [overflow-wrap:anywhere]">
                  {recommendedStack.explanation || 'Historical execution signals were matched against similar work to recommend the most reliable workflow composition.'}
                </p>
              </div>
              <div className="inline-flex w-fit shrink-0 items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-100">
                <CheckCircle2 size={14} />
                Historical fit
              </div>
            </div>

            <div className="mt-4 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(16rem,1fr))]">
              <div className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Execution Alignment</div>
                <div className="mt-1 text-sm leading-6 text-slate-300 [overflow-wrap:anywhere]">
                  {recommendedStack.commandAlignment || 'Aligned to the current execution pattern.'}
                </div>
              </div>
              <div className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Primary Evidence</div>
                <div className="mt-1 text-sm leading-6 text-slate-300 [overflow-wrap:anywhere]">
                  {recommendedStack.label || 'Historical stack recommendation'}
                </div>
              </div>
            </div>

            {headlineTags.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {headlineTags.map(tag => (
                  tag.url ? (
                    <button
                      key={tag.label}
                      onClick={() => openExternalUrl(tag.url || '')}
                      className="inline-flex max-w-full items-center gap-1 rounded-full border border-sky-500/25 bg-sky-500/10 px-3 py-1 text-xs text-sky-100 hover:bg-sky-500/20"
                    >
                      <span className="[overflow-wrap:anywhere]">{tag.label}</span>
                      <ExternalLink size={12} className="shrink-0" />
                    </button>
                  ) : (
                    <span key={tag.label} className="inline-flex max-w-full items-center rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300 [overflow-wrap:anywhere]">
                      {tag.label}
                    </span>
                  )
                ))}
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/50 p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Outcome Snapshot</div>
              <div className="mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
                <StackStatCard label="Success" value={formatPercent(recommendedStack.successScore)} tone="success" />
                <StackStatCard label="Efficiency" value={formatPercent(recommendedStack.efficiencyScore)} tone="info" />
                <StackStatCard label="Quality" value={formatPercent(recommendedStack.qualityScore)} tone="info" />
                <StackStatCard label="Risk" value={formatPercent(recommendedStack.riskScore)} tone="warning" />
              </div>
            </div>

            <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/50 p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Recommendation Stats</div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-emerald-200/80">Match</div>
                  <div className="mt-1 text-3xl font-semibold text-emerald-100">{formatPercent(recommendedStack.confidence)}</div>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Sample Size</div>
                  <div className="mt-1 text-3xl font-semibold text-slate-100">{recommendedStack.sampleSize}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className={`mt-4 grid gap-4 ${referenceChips.length > 0 || insightSections.length > 0 ? 'xl:grid-cols-[minmax(0,1.12fr)_minmax(20rem,0.88fr)]' : ''}`}>
          <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/45 p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Execution Blueprint</div>
                <div className="mt-1 text-lg font-semibold text-slate-100">Grouped stack components</div>
              </div>
              <div className="text-sm text-slate-500">
                {recommendedStack.components.length} component{recommendedStack.components.length === 1 ? '' : 's'}
              </div>
            </div>
            <div className="mt-4 grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
              {COMPONENT_GROUPS.map(group => {
                const items = groupedComponents.get(group.key) || [];
                if (items.length === 0) return null;
                return (
                  <div key={group.key} className="min-w-0 overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/50 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 text-sm font-semibold text-slate-100">{group.label}</div>
                      <div className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-400">
                        {items.length}
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2">
                      {items.map(component => (
                        <DefinitionChip
                          key={`${group.key}-${component.componentKey}-${component.label}`}
                          reference={getReferenceData(component)}
                          fullWidth
                          onOpenReference={setActiveReference}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {(referenceChips.length > 0 || insightSections.length > 0) && (
            <div className="space-y-4">
              {referenceChips.length > 0 && (
                <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/45 p-4">
                  <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    <Link2 size={12} />
                    Resolved References
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {referenceChips.map(reference => (
                      <DefinitionChip key={reference.key} reference={reference} onOpenReference={setActiveReference} />
                    ))}
                  </div>
                </div>
              )}

              {insightSections.length > 0 && (
                <div className="space-y-4">
                  {insightSections.map(section => (
                    <InsightCard key={section.key} section={section} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {definitionResolutionWarnings.length > 0 && (
          <div className="mt-4 space-y-2">
            {definitionResolutionWarnings.map((warning, index) => (
              <div key={`${warning.section}-${index}`} className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                {warning.message}
              </div>
            ))}
          </div>
        )}

        <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(18rem,0.85fr)_minmax(0,1.15fr)]">
          <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-lg font-semibold text-slate-100">Alternatives</div>
              <div className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-400">
                {stackAlternatives.length}
              </div>
            </div>
            <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-1">
              {stackAlternatives.length === 0 && (
                <div className="rounded-2xl border border-slate-800 bg-slate-950/40 px-4 py-4 text-sm text-slate-500">
                  No alternate historical stacks were strong enough to rank.
                </div>
              )}
              {stackAlternatives.map((alternative, index) => {
                const alternativeWorkflowRef = alternative.components.find(component => component.componentType === 'workflow')?.artifactRef || null;
                return (
                  <div key={alternative.id} className="min-w-0 overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/45 px-4 py-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0 flex-1">
                        {alternativeWorkflowRef ? (
                          <button
                            onClick={() => setActiveReference(alternativeWorkflowRef)}
                            className="text-left text-base font-semibold text-sky-200 underline decoration-slate-600 underline-offset-4 [overflow-wrap:anywhere]"
                          >
                            {index + 1}. {alternative.label || alternative.workflowRef}
                          </button>
                        ) : (
                          <div className="text-base font-semibold text-slate-100 [overflow-wrap:anywhere]">{index + 1}. {alternative.label || alternative.workflowRef}</div>
                        )}
                        <div className="mt-1 text-sm text-slate-500 [overflow-wrap:anywhere]">{alternative.commandAlignment || 'Aligned to current execution pattern'}</div>
                      </div>
                      <div className="shrink-0 self-start rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-sm font-semibold text-slate-200">
                        {formatPercent(alternative.confidence)}
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {alternative.components.slice(0, 5).map(component => (
                        <button
                          key={`${alternative.id}-${component.componentKey}`}
                          onClick={() => component.artifactRef && setActiveReference(component.artifactRef)}
                          className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-300 [overflow-wrap:anywhere]"
                        >
                          {getReferenceLabel(component)}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="min-w-0 overflow-hidden rounded-[24px] border border-slate-800/80 bg-slate-950/40 p-4">
            <div className="text-lg font-semibold text-slate-100">Evidence</div>
            <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-1">
              {stackEvidence.length === 0 && (
                <div className="text-sm text-slate-500">No historical evidence items were attached to this recommendation.</div>
              )}
              {stackEvidence.map(evidence => (
                <div key={evidence.id} className="min-w-0 overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="text-base font-semibold text-slate-100 [overflow-wrap:anywhere]">{evidence.label}</div>
                      <div className="mt-1 text-sm leading-6 text-slate-400 [overflow-wrap:anywhere]">{evidence.summary}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300">
                        {evidence.sourceType.replace(/_/g, ' ')}
                      </div>
                      <div className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300">
                        {formatPercent(evidence.confidence)} confidence
                      </div>
                    </div>
                  </div>

                  {evidence.similarWork.length > 0 && (
                    <div className="mt-4">
                      <button
                        onClick={() => setActiveEvidence(evidence)}
                        className="text-sm text-sky-200 underline decoration-slate-600 underline-offset-4 hover:text-sky-100"
                      >
                        View {evidence.similarWork.length} similar session{evidence.similarWork.length === 1 ? '' : 's'}
                      </button>
                      <div className="mt-3 space-y-2">
                        {evidence.similarWork.slice(0, 3).map(item => (
                          <div key={item.sessionId} className="flex flex-col gap-2 text-sm text-slate-400 sm:flex-row sm:flex-wrap sm:items-center">
                            <button
                              onClick={() => onOpenSession(item.sessionId)}
                              className="font-mono text-sky-200 underline decoration-slate-600 underline-offset-4 [overflow-wrap:anywhere]"
                            >
                              {item.title || item.sessionId}
                            </button>
                            <span>{formatDateTime(item.startedAt)}</span>
                            <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs text-slate-300">{formatPercent(item.similarityScore)} similar</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {activeEvidence && (
        <SimilarWorkModal
          evidence={activeEvidence}
          onClose={() => setActiveEvidence(null)}
          onOpenSession={onOpenSession}
          onOpenFeature={onOpenFeature}
        />
      )}
      {activeReference && (
        <ArtifactReferenceModal
          reference={activeReference}
          title="Artifact Reference"
          subtitle="Resolved from the historical stack recommendation payload for this feature."
          metrics={[
            { label: 'Kind', value: activeReference.kind || 'artifact' },
            { label: 'Status', value: activeReference.status || 'unresolved' },
            { label: 'External ID', value: activeReference.externalId || 'n/a' },
          ]}
          relatedRefs={(recommendedStack?.components || [])
            .map(component => component.artifactRef)
            .filter((reference): reference is ExecutionArtifactReference => Boolean(reference))
            .filter(reference => reference.key !== activeReference.key)
            .slice(0, 8)}
          onOpenReference={setActiveReference}
          onClose={() => setActiveReference(null)}
        />
      )}
    </>
  );
};
