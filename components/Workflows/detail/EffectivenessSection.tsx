import React from 'react';
import { BarChart3, Gauge, ShieldCheck, TriangleAlert } from 'lucide-react';

import { WorkflowRegistryEffectivenessSummary } from '../../../types';
import {
  formatInteger,
  formatPercent,
  hasEffectivenessSummary,
  scoreBarClass,
  scoreValueClass,
} from '../workflowRegistryUtils';

interface EffectivenessSectionProps {
  effectiveness?: WorkflowRegistryEffectivenessSummary | null;
}

const ScoreBar: React.FC<{
  label: string;
  value: number;
  kind: 'success' | 'efficiency' | 'quality' | 'risk';
}> = ({ label, value, kind }) => (
  <div className="space-y-2">
    <div className="flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.16em] text-slate-500">
      <span>{label}</span>
      <span className={`font-mono text-sm ${scoreValueClass(kind)}`}>{formatPercent(value)}</span>
    </div>
    <div className="h-2 overflow-hidden rounded-full bg-slate-900">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${scoreBarClass(kind)}`}
        style={{ width: `${Math.max(8, Math.round(Math.max(0, Math.min(1, value)) * 100))}%` }}
      />
    </div>
  </div>
);

const EvidenceMetric: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string;
}> = ({ icon, label, value }) => (
  <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4">
    <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
      {icon}
      {label}
    </div>
    <div className="mt-2 text-xl font-semibold tracking-tight text-slate-100">{value}</div>
  </div>
);

export const EffectivenessSection: React.FC<EffectivenessSectionProps> = ({ effectiveness }) => {
  const evidenceEntries = Object.entries(effectiveness?.evidenceSummary || {}).slice(0, 4);

  return (
    <section className="rounded-[28px] border border-slate-800/80 bg-slate-950/55 px-5 py-5">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Effectiveness</div>
      <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-100">Outcome signals and quality evidence</h3>

      {!hasEffectivenessSummary(effectiveness) ? (
        <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 text-sm text-slate-400">
          No effectiveness rollup has been cached yet for this workflow entity.
        </div>
      ) : (
        <>
          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <EvidenceMetric icon={<BarChart3 size={12} />} label="Scope" value={effectiveness.scopeLabel || effectiveness.scopeId} />
            <EvidenceMetric icon={<Gauge size={12} />} label="Sample Size" value={formatInteger(effectiveness.sampleSize)} />
            <EvidenceMetric icon={<ShieldCheck size={12} />} label="Coverage" value={formatPercent(effectiveness.attributionCoverage)} />
            <EvidenceMetric icon={<TriangleAlert size={12} />} label="Avg Confidence" value={formatPercent(effectiveness.averageAttributionConfidence)} />
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4">
              <ScoreBar label="Success" value={effectiveness.successScore} kind="success" />
              <ScoreBar label="Efficiency" value={effectiveness.efficiencyScore} kind="efficiency" />
              <ScoreBar label="Quality" value={effectiveness.qualityScore} kind="quality" />
              <ScoreBar label="Risk" value={effectiveness.riskScore} kind="risk" />
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Evidence Summary</div>
              {evidenceEntries.length > 0 ? (
                <dl className="mt-3 grid gap-3">
                  {evidenceEntries.map(([key, value]) => (
                    <div key={key} className="rounded-xl border border-slate-800 bg-slate-950/80 px-3 py-3">
                      <dt className="text-[11px] uppercase tracking-[0.16em] text-slate-500">{key}</dt>
                      <dd className="mt-1 text-sm text-slate-100 [overflow-wrap:anywhere]">
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <div className="mt-3 text-sm text-slate-500">No structured evidence summary was attached.</div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
