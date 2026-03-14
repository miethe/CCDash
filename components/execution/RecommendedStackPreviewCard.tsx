import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Layers, ShieldAlert, Sparkles, X } from 'lucide-react';

import {
  FeatureExecutionWarning,
  RecommendedStack,
  RecommendedStackComponent,
  StackRecommendationEvidence,
} from '../../types';
import { RecommendedStackCard } from './RecommendedStackCard';

interface RecommendedStackPreviewCardProps {
  recommendedStack?: RecommendedStack | null;
  stackAlternatives: RecommendedStack[];
  stackEvidence: StackRecommendationEvidence[];
  definitionResolutionWarnings: FeatureExecutionWarning[];
  onOpenSession: (sessionId: string) => void;
  onOpenFeature?: (featureId: string) => void;
}

const formatPercent = (value: number): string => `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;

const COMPONENT_TYPE_LABELS: Record<RecommendedStackComponent['componentType'], string> = {
  workflow: 'Workflow',
  agent: 'Agents',
  skill: 'Skills',
  context_module: 'Context',
  artifact: 'Artifacts',
  command: 'Commands',
  model_policy: 'Policies',
};

const getComponentLabel = (component: RecommendedStackComponent): string =>
  component.definition?.displayName || component.label || component.componentKey || 'Unnamed component';

export const RecommendedStackPreviewCard: React.FC<RecommendedStackPreviewCardProps> = ({
  recommendedStack,
  stackAlternatives = [],
  stackEvidence = [],
  definitionResolutionWarnings = [],
  onOpenSession,
  onOpenFeature,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen]);

  const previewComponents = useMemo(() => {
    if (!recommendedStack) return [];
    const seen = new Set<string>();
    return recommendedStack.components.filter(component => {
      const label = getComponentLabel(component).trim();
      if (!label || seen.has(label)) return false;
      seen.add(label);
      return true;
    }).slice(0, 4);
  }, [recommendedStack]);

  const groupedSummary = useMemo(() => {
    if (!recommendedStack) return [];
    const counts = new Map<string, number>();
    recommendedStack.components.forEach(component => {
      const label = COMPONENT_TYPE_LABELS[component.componentType] || component.componentType.replace(/_/g, ' ');
      counts.set(label, (counts.get(label) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }, [recommendedStack]);

  const signalTags = useMemo(() => {
    return stackEvidence
      .map(item => item.label?.trim() || item.sourceType.replace(/_/g, ' '))
      .filter(Boolean)
      .slice(0, 3);
  }, [stackEvidence]);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="group w-full overflow-hidden rounded-[24px] border border-slate-800/80 bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.12),_rgba(15,23,42,0.9)_42%,_rgba(2,6,23,0.96)_100%)] p-4 text-left shadow-[0_24px_70px_rgba(2,6,23,0.18)] transition-all hover:border-sky-500/30 hover:shadow-[0_30px_90px_rgba(2,6,23,0.26)]"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-100">
              <Sparkles size={12} />
              Recommended Stack
            </div>
            <h3 className="mt-3 text-lg font-semibold tracking-tight text-slate-100">
              {recommendedStack?.workflowRef || recommendedStack?.label || 'Historical stack guidance'}
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {recommendedStack
                ? (recommendedStack.commandAlignment || recommendedStack.explanation || 'Open the full stack composition and evidence.')
                : 'Historical stack guidance is not available for this feature yet. Open the modal for details and warnings.'}
            </p>
          </div>

          <div className="inline-flex shrink-0 items-center gap-1 rounded-full border border-slate-700 bg-slate-950/70 px-3 py-1 text-[11px] font-semibold text-slate-200 transition-colors group-hover:border-sky-500/30 group-hover:text-sky-100">
            Expand
            <ArrowUpRight size={12} />
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
            <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Match</div>
            <div className="mt-1 text-2xl font-semibold text-emerald-200">
              {recommendedStack ? formatPercent(recommendedStack.confidence) : 'n/a'}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
            <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Blueprint</div>
            <div className="mt-1 text-2xl font-semibold text-slate-100">
              {recommendedStack?.components.length || 0}
            </div>
            <div className="mt-1 text-xs text-slate-500">components</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
            <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Depth</div>
            <div className="mt-1 text-2xl font-semibold text-slate-100">
              {recommendedStack?.sampleSize || stackEvidence.length || 0}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {recommendedStack ? 'historical matches' : 'signals'}
            </div>
          </div>
        </div>

        {groupedSummary.length > 0 && (
          <div className="mt-4 rounded-2xl border border-slate-800/80 bg-slate-950/45 px-4 py-3">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
              <Layers size={12} />
              Blueprint Summary
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {groupedSummary.map(([label, count]) => (
                <span
                  key={label}
                  className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300"
                >
                  {label} {count}
                </span>
              ))}
            </div>
          </div>
        )}

        {previewComponents.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {previewComponents.map(component => (
              <span
                key={`${component.componentType}-${component.componentKey}-${component.label}`}
                className="rounded-full border border-slate-700 bg-slate-900/90 px-3 py-1 text-xs text-slate-300"
              >
                {getComponentLabel(component)}
              </span>
            ))}
          </div>
        )}

        {!recommendedStack && definitionResolutionWarnings.length > 0 && (
          <div className="mt-4 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            <div className="flex items-center gap-2">
              <ShieldAlert size={15} />
              {definitionResolutionWarnings.length} resolution warning{definitionResolutionWarnings.length === 1 ? '' : 's'}
            </div>
          </div>
        )}

        {signalTags.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {signalTags.map(tag => (
              <span
                key={tag}
                className="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-[11px] text-sky-100"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {stackAlternatives.length > 0 && (
          <div className="mt-4 text-xs text-slate-500">
            {stackAlternatives.length} alternate stack{stackAlternatives.length === 1 ? '' : 's'} available in the modal.
          </div>
        )}
      </button>

      {isOpen && (
        <div
          className="fixed inset-0 z-[82] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setIsOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Recommended stack details"
            className="max-h-[92vh] w-full max-w-7xl overflow-y-auto rounded-[32px] border border-slate-700 bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.12),_rgba(15,23,42,0.95)_42%,_rgba(2,6,23,0.99)_100%)] shadow-2xl"
            onClick={event => event.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-800 bg-slate-950/90 px-5 py-4 backdrop-blur-sm">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-100">
                  <Sparkles size={12} />
                  Recommendation Drilldown
                </div>
                <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-100">Recommended Stack</h3>
                <p className="mt-2 text-sm text-slate-400">
                  Full stack composition, alternatives, and historical evidence for this workflow.
                </p>
              </div>

              <button
                onClick={() => setIsOpen(false)}
                className="rounded-lg border border-slate-700 p-2 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                aria-label="Close recommended stack dialog"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-4 md:p-5">
              <RecommendedStackCard
                recommendedStack={recommendedStack}
                stackAlternatives={stackAlternatives}
                stackEvidence={stackEvidence}
                definitionResolutionWarnings={definitionResolutionWarnings}
                onOpenSession={onOpenSession}
                onOpenFeature={onOpenFeature}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
};
