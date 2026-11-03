import React, { useState } from 'react';
import type {
  SessionContextAttribution,
  SessionContextLayer,
  SessionContextStage,
} from '../../types';

export interface SessionContextAttributionPanelProps {
  attribution?: SessionContextAttribution | null;
}

const PHASE_LABELS: Record<string, string> = {
  first_observed_after_sessionstart: 'First input after SessionStart (not guaranteed cold start)',
  post_compact: 'After compaction',
  prompt: 'Prompt injection',
  startup: 'Recorded startup',
};

export function phaseLabel(phase: string | null | undefined): { label: string; raw: string | null } {
  const raw = typeof phase === 'string' ? phase.trim() : '';
  if (!raw || raw === 'unknown') return { label: 'Unrecorded phase', raw: null };
  if (Object.prototype.hasOwnProperty.call(PHASE_LABELS, raw)) return { label: PHASE_LABELS[raw], raw };
  return { label: raw, raw };
}

const isMeasured = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0;

const UNIT_WORDS: Record<string, [string, string]> = {
  characters: ['character', 'characters'],
  bytes: ['byte', 'bytes'],
  tokens: ['token', 'tokens'],
};

export function formatAmount(amount: unknown, unit: string): string {
  if (!isMeasured(amount)) return 'Unmeasured';
  const words = UNIT_WORDS[unit];
  const word = words ? (amount === 1 ? words[0] : words[1]) : String(unit);
  return `${amount.toLocaleString('en-US')} ${word}`;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return 'Time not recorded';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z').replace(/:00Z$/, 'Z');
}

const STATUS_COPY: Record<string, { label: string; blurb: string }> = {
  measured: { label: 'Measured', blurb: 'Every recorded stage carries a reading.' },
  partial: { label: 'Partially measured', blurb: 'Some stages or layers have readings; the rest are marked unmeasured.' },
  unmeasured: { label: 'Unmeasured', blurb: 'No usable reading was recorded for this session.' },
};

const JOIN_COPY: Record<string, string> = {
  matched: 'Matched to this session',
  unmatched: 'No matching session found',
  ambiguous: 'Ambiguous session match',
  source_unavailable: 'Source unavailable',
};

const ATTRIBUTION_COPY: Record<string, { label: string; hint: string }> = {
  measured: { label: 'Measured', hint: 'Named layer amount recorded by the source.' },
  attributed: { label: 'Attributed', hint: 'Source of this content is identified.' },
  unattributed: { label: 'Unattributed', hint: 'Amount is known; its origin is unresolved.' },
  missing: { label: 'Missing', hint: 'No reading for this layer.' },
};

const chip = 'inline-flex items-center rounded-full border border-panel-border bg-surface-overlay px-2 py-0.5 text-xs font-medium text-foreground';

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <section aria-labelledby="ctx-evidence-heading" className="rounded-xl border border-panel-border bg-panel p-4 text-panel-foreground">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="ctx-evidence-heading" className="text-base font-semibold text-foreground">Context evidence</h3>
        <span className={chip}>Unmeasured</span>
      </div>
      <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </section>
  );
}

function LayerRow({ layer, stage }: { layer: SessionContextLayer; stage: SessionContextStage }) {
  const known = isMeasured(layer.amount);
  const copy = ATTRIBUTION_COPY[layer.attribution] ?? { label: String(layer.attribution), hint: 'Recorded attribution state.' };
  // A bar is only drawn when the layer shares the stage's unit and is a part of that stage's own amount.
  const showBar = known && isMeasured(stage.amount) && stage.amount > 0 && layer.unit === stage.unit && layer.amount! <= stage.amount;
  const pct = showBar ? Math.min(100, (layer.amount! / stage.amount!) * 100) : 0;
  const unattributed = layer.attribution === 'unattributed';
  return (
    <li className="rounded-lg border border-panel-border bg-surface-overlay p-3">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <span className="min-w-0 break-words text-sm font-medium text-foreground">{layer.name}</span>
        <span className={`${chip} ${unattributed ? 'border-dashed' : ''}`} title={copy.hint}>{copy.label}</span>
      </div>
      <p className="mt-1 text-sm text-foreground">
        {known ? formatAmount(layer.amount, layer.unit) : 'Unmeasured'}
        {unattributed && known ? <span className="text-muted-foreground"> · origin unresolved</span> : null}
      </p>
      {showBar ? (
        <div className="mt-2" role="img" aria-label={`${Math.round(pct)}% of this stage's ${layer.unit}`}>
          <div className="h-1.5 w-full rounded-full border border-panel-border">
            <div className={`h-full rounded-full ${unattributed ? 'bg-muted-foreground/50' : 'bg-foreground/70'}`} style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{Math.round(pct)}% of this stage’s {layer.unit}</p>
        </div>
      ) : null}
      <p className="mt-1 break-words text-xs text-muted-foreground">
        {layer.source}
        {layer.sourceVersion ? ` · v${layer.sourceVersion}` : ' · version not recorded'}
        {layer.unit === 'unknown' ? ' · unit not recorded' : layer.unit !== stage.unit ? ` · counted in ${layer.unit}, separate from stage ${stage.unit}` : ''}
      </p>
    </li>
  );
}

export function SessionContextAttributionPanel({ attribution }: SessionContextAttributionPanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (!attribution) {
    return (
      <EmptyState
        title="No context evidence for this session"
        body="Nothing was recorded or the source was not available, so no amounts are shown. This is unmeasured, not zero."
      />
    );
  }

  const stages = Array.isArray(attribution.stages) ? attribution.stages : [];
  const unknowns = Array.isArray(attribution.unknowns) ? attribution.unknowns : [];
  const status = STATUS_COPY[attribution.status] ?? { label: 'Unmeasured', blurb: 'Status was not recognised, so nothing is assumed.' };
  const cov = attribution.coverage;
  const join = cov ? JOIN_COPY[cov.joinStatus] ?? String(cov.joinStatus) : 'Join status not recorded';
  const selected = stages.find((s) => s.id === selectedId) ?? stages[0];

  return (
    <section aria-labelledby="ctx-evidence-heading" className="rounded-xl border border-panel-border bg-panel p-4 text-panel-foreground">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id="ctx-evidence-heading" className="text-base font-semibold text-foreground">Context evidence</h3>
          <p className="mt-1 text-sm text-muted-foreground">{status.blurb}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={chip}>{status.label}</span>
          <span className={chip}>{join}</span>
        </div>
      </header>

      <p className="mt-3 break-words text-xs text-muted-foreground">
        Source: {cov?.source ?? 'not recorded'}
        {cov?.sourceVersion ? ` · v${cov.sourceVersion}` : ''}
        {' · '}{stages.length} {stages.length === 1 ? 'stage' : 'stages'} shown
        {cov && cov.stageCount !== stages.length ? ` of ${cov.stageCount} reported` : ''}
        {attribution.generatedAt ? ` · generated ${formatTime(attribution.generatedAt)}` : ''}
      </p>

      {stages.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-panel-border p-3 text-sm text-muted-foreground">
          No context stages were recorded. Amounts are unmeasured rather than zero.
        </p>
      ) : (
        <div className="mt-5 grid min-w-0 gap-4 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
          <div className="min-w-0">
          <h4 className="text-sm font-semibold text-foreground">Stages over time</h4>
          <ol className="mt-2 max-h-[28rem] space-y-2 overflow-y-auto">
            {stages.map((stage, i) => {
              const p = phaseLabel(stage.phase);
              const active = stage.id === selected?.id;
              return (
                <li key={`${stage.id}-${i}`}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSelectedId(stage.id)}
                    className={`w-full rounded-lg border p-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-foreground ${
                      active ? 'border-foreground bg-surface-overlay' : 'border-panel-border bg-panel'
                    }`}
                  >
                    <span className="block text-sm font-medium text-foreground">{i + 1}. {p.label}</span>
                    {p.raw && !PHASE_LABELS[p.raw] ? (
                      <span className="block text-xs text-muted-foreground">Recorded source label</span>
                    ) : null}
                    <span className="mt-0.5 block text-sm text-foreground">{formatAmount(stage.amount, stage.unit)}</span>
                    <span className="block text-xs text-muted-foreground">{formatTime(stage.observedAt)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          </div>
          <div className="min-w-0">{selected ? <StageDetail stage={selected} /> : null}</div>
        </div>
      )}

      <div className="mt-5">
        <h4 className="text-sm font-semibold text-foreground">What is not known</h4>
        {unknowns.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {unknowns.map((u, i) => (
              <li key={i} className="break-words">{String(u)}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">No gaps were reported by the source. Stages and layers not listed were not recorded.</p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          Characters, bytes and tokens are different units and are never added together. These readings describe context size only, not cost.
        </p>
      </div>
    </section>
  );
}

function StageDetail({ stage }: { stage: SessionContextStage }) {
  const p = phaseLabel(stage.phase);
  const layers = Array.isArray(stage.layers) ? stage.layers : [];
  return (
    <div className="rounded-xl border border-panel-border bg-surface-overlay p-3 sm:p-4" aria-live="polite">
      <h4 className="text-sm font-semibold text-foreground">Selected stage: {p.label}</h4>
      {p.raw && !PHASE_LABELS[p.raw] ? (
        <p className="text-xs text-muted-foreground">Phase shown exactly as recorded by the source.</p>
      ) : null}
      <p className="mt-2 text-2xl font-semibold text-foreground">{formatAmount(stage.amount, stage.unit)}</p>
      <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
        <div><dt className="text-xs text-muted-foreground">Observed</dt><dd className="break-words text-foreground">{formatTime(stage.observedAt)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Source</dt><dd className="break-words text-foreground">{stage.source}{stage.sourceVersion ? ` · v${stage.sourceVersion}` : ' · version not recorded'}</dd></div>
        <div className="sm:col-span-2"><dt className="text-xs text-muted-foreground">Method</dt><dd className="break-words text-foreground">{stage.method || 'Not recorded'}</dd></div>
      </dl>
      <details className="mt-3 rounded-lg border border-panel-border p-2">
        <summary className="cursor-pointer text-sm font-medium text-foreground">Provenance</summary>
        <p className="mt-2 whitespace-pre-wrap break-words text-sm text-muted-foreground">{stage.provenance || 'Not recorded'}</p>
      </details>

      <h5 className="mt-4 text-sm font-semibold text-foreground">Layers in this stage</h5>
      {layers.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">No layers were recorded for this stage. Layer amounts are unmeasured.</p>
      ) : (
        <>
          <ul className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
            {layers.map((l, i) => (
              <LayerRow key={`${l.name}-${i}`} layer={l} stage={stage} />
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Layers are not added up here; they may not cover the whole stage. Unattributed amounts are real readings whose origin is still unresolved.
          </p>
        </>
      )}
    </div>
  );
}
