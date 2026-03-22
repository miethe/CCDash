import React from 'react';
import { ExternalLink, Layers3, LibraryBig, Network, PackageOpen, ScrollText } from 'lucide-react';

import { WorkflowRegistryCompositionSummary } from '../../../types';
import { formatPercent, openExternalUrl } from '../workflowRegistryUtils';

interface CompositionSectionProps {
  composition: WorkflowRegistryCompositionSummary;
}

const StatCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string;
  caption?: string;
}> = ({ icon, label, value, caption }) => (
  <div className="rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
    <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
      {icon}
      {label}
    </div>
    <div className="mt-2 text-2xl font-semibold tracking-tight text-panel-foreground">{value}</div>
    {caption && <div className="mt-1 text-xs text-muted-foreground">{caption}</div>}
  </div>
);

export const CompositionSection: React.FC<CompositionSectionProps> = ({ composition }) => {
  const planSummaryEntries = Object.entries(composition.planSummary || {}).slice(0, 6);
  const hasCompositionData = Boolean(
    composition.artifactRefs.length ||
      composition.contextRefs.length ||
      composition.resolvedContextModules.length ||
      composition.stageOrder.length ||
      composition.bundleAlignment ||
      planSummaryEntries.length,
  );

  return (
    <section className="rounded-[28px] border border-panel-border bg-surface-overlay/70 px-5 py-5">
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Composition</div>
      <div className="mt-2 flex items-center justify-between gap-4">
        <h3 className="text-xl font-semibold tracking-tight text-panel-foreground">Workflow shape and dependency surface</h3>
        {composition.bundleAlignment?.bundleName && (
          <button
            type="button"
            onClick={() => openExternalUrl(composition.bundleAlignment?.sourceUrl || '')}
            className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-100 hover:bg-sky-500/20"
          >
            Open bundle
            <ExternalLink size={12} />
          </button>
        )}
      </div>

      {!hasCompositionData ? (
        <div className="mt-4 rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4 text-sm text-muted-foreground">
          This workflow has no extracted composition metadata yet. The registry is showing the gap explicitly instead of hiding it.
        </div>
      ) : (
        <>
          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <StatCard icon={<PackageOpen size={12} />} label="Artifact Refs" value={String(composition.artifactRefs.length)} />
            <StatCard icon={<LibraryBig size={12} />} label="Context Refs" value={String(composition.contextRefs.length)} />
            <StatCard
              icon={<Layers3 size={12} />}
              label="Stages"
              value={String(composition.stageOrder.length)}
              caption={`${composition.gateCount} gates • ${composition.fanOutCount} fan-out`}
            />
            <StatCard
              icon={<Network size={12} />}
              label="Resolved Modules"
              value={String(composition.resolvedContextModules.length)}
              caption={composition.bundleAlignment ? composition.bundleAlignment.bundleName : 'No bundle alignment'}
            />
          </div>

          {composition.stageOrder.length > 0 && (
            <div className="mt-5 rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Stage Order</div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {composition.stageOrder.map((stage, index) => (
                  <React.Fragment key={`${stage}-${index}`}>
                    <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1.5 text-sm font-semibold text-indigo-100">
                      {stage}
                    </span>
                    {index < composition.stageOrder.length - 1 && (
                      <span className="text-muted-foreground">/</span>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Artifact References</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {composition.artifactRefs.length > 0 ? (
                    composition.artifactRefs.map(ref => (
                      <span
                        key={ref}
                        className="rounded-full border border-panel-border bg-panel/80 px-2.5 py-1 text-xs text-panel-foreground"
                      >
                        {ref}
                      </span>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">No artifact references extracted.</span>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Resolved Context Modules</div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {composition.resolvedContextModules.length > 0 ? (
                    composition.resolvedContextModules.map(module => (
                      <button
                        key={`${module.moduleId}-${module.contextRef}`}
                        type="button"
                        onClick={() => openExternalUrl(module.sourceUrl)}
                        className="rounded-2xl border border-panel-border bg-surface-overlay/90 px-4 py-3 text-left transition-colors hover:border-hover"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold text-panel-foreground [overflow-wrap:anywhere]">
                            {module.moduleName || module.contextRef}
                          </div>
                          <ExternalLink size={12} className="text-muted-foreground" />
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {module.contextRef} • {module.status || 'unknown'}
                        </div>
                        <div className="mt-2 text-xs text-foreground">
                          Preview footprint {module.previewTokens.toLocaleString()} tok
                        </div>
                      </button>
                    ))
                  ) : (
                    <div className="text-sm text-muted-foreground">No resolved context modules attached.</div>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {composition.bundleAlignment && (
                <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-4">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/70">Bundle Alignment</div>
                  <div className="mt-2 text-lg font-semibold text-cyan-50">
                    {composition.bundleAlignment.bundleName || composition.bundleAlignment.bundleId}
                  </div>
                  <div className="mt-2 text-sm text-cyan-50/80">
                    Match score {formatPercent(composition.bundleAlignment.matchScore)}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {composition.bundleAlignment.matchedRefs.map(ref => (
                      <span
                        key={`${composition.bundleAlignment?.bundleId}-${ref}`}
                        className="rounded-full border border-cyan-500/20 bg-surface-overlay/70 px-2.5 py-1 text-xs text-cyan-50"
                      >
                        {ref}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  <ScrollText size={12} />
                  Plan Summary
                </div>
                {planSummaryEntries.length > 0 ? (
                  <dl className="mt-3 grid gap-3">
                    {planSummaryEntries.map(([key, value]) => (
                      <div key={key} className="rounded-xl border border-panel-border bg-surface-overlay/80 px-3 py-3">
                        <dt className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{key}</dt>
                        <dd className="mt-1 text-sm text-panel-foreground [overflow-wrap:anywhere]">
                          {typeof value === 'string' ? value : JSON.stringify(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <div className="mt-3 text-sm text-muted-foreground">No structured plan summary was cached.</div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
