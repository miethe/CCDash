import React, { useEffect } from 'react';
import { ExternalLink, X } from 'lucide-react';

import { ExecutionArtifactReference } from '../../types';

interface ArtifactMetric {
  label: string;
  value: string;
}

interface ArtifactReferenceModalProps {
  reference: ExecutionArtifactReference;
  title?: string;
  subtitle?: string;
  metrics?: ArtifactMetric[];
  relatedRefs?: ExecutionArtifactReference[];
  onOpenReference?: (reference: ExecutionArtifactReference) => void;
  onClose: () => void;
}

const statusToneClass = (status: string): string => {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'resolved') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100';
  if (normalized === 'cached') return 'border-sky-500/30 bg-sky-500/10 text-sky-100';
  return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
};

const openExternalUrl = (url: string) => {
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
};

export const ArtifactReferenceModal: React.FC<ArtifactReferenceModalProps> = ({
  reference,
  title,
  subtitle,
  metrics = [],
  relatedRefs = [],
  onOpenReference,
  onClose,
}) => {
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

  const metadataEntries = Object.entries(reference.metadata || {}).slice(0, 12);

  return (
    <div className="fixed inset-0 z-[90] bg-slate-950/80 backdrop-blur-sm px-4 py-8" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title || reference.label || 'Artifact details'}
        className="mx-auto max-h-full w-full max-w-3xl overflow-y-auto rounded-[28px] border border-slate-700 bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.14),_rgba(15,23,42,0.96)_40%,_rgba(2,6,23,0.99)_100%)] shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-5 py-4">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{title || 'Artifact Details'}</div>
            <div className="mt-2 text-2xl font-semibold text-slate-100 [overflow-wrap:anywhere]">{reference.label || reference.key || 'Unnamed reference'}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-400">
              <span className={`rounded-full border px-2.5 py-1 text-xs ${statusToneClass(reference.status)}`}>{reference.status || 'unresolved'}</span>
              <span>{reference.kind || 'artifact'}</span>
              {reference.externalId && <span className="font-mono text-slate-500">{reference.externalId}</span>}
            </div>
            {subtitle && <p className="mt-3 text-sm text-slate-400">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700 p-2 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
            aria-label="Close artifact modal"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-5 px-5 py-5">
          {(reference.description || reference.sourceAttribution) && (
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              {reference.description && <p className="text-sm leading-6 text-slate-300">{reference.description}</p>}
              {reference.sourceAttribution && (
                <div className="mt-3 text-xs uppercase tracking-[0.16em] text-slate-500">
                  Source attribution: <span className="text-slate-300">{reference.sourceAttribution}</span>
                </div>
              )}
            </div>
          )}

          {metrics.length > 0 && (
            <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
              {metrics.map(metric => (
                <div key={`${reference.key}-${metric.label}`} className="rounded-2xl border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">{metric.label}</div>
                  <div className="mt-1 text-lg font-semibold text-slate-100 [overflow-wrap:anywhere]">{metric.value}</div>
                </div>
              ))}
            </div>
          )}

          {reference.sourceUrl && (
            <button
              onClick={() => openExternalUrl(reference.sourceUrl)}
              className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-100 hover:bg-sky-500/20"
            >
              Open in SkillMeat
              <ExternalLink size={12} />
            </button>
          )}

          {relatedRefs.length > 0 && (
            <div className="space-y-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Related References</div>
              <div className="grid gap-2 md:grid-cols-2">
                {relatedRefs.map(relatedRef => (
                  <button
                    key={`${relatedRef.kind}-${relatedRef.key}-${relatedRef.label}`}
                    onClick={() => onOpenReference?.(relatedRef)}
                    className="rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-3 text-left transition-colors hover:border-slate-600"
                  >
                    <div className="text-sm font-semibold text-slate-100 [overflow-wrap:anywhere]">{relatedRef.label || relatedRef.key}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {relatedRef.kind} {relatedRef.externalId ? `• ${relatedRef.externalId}` : ''}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {metadataEntries.length > 0 && (
            <div className="space-y-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Reference Metadata</div>
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                <dl className="grid gap-3 md:grid-cols-2">
                  {metadataEntries.map(([key, value]) => (
                    <div key={`${reference.key}-${key}`} className="min-w-0">
                      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{key}</dt>
                      <dd className="mt-1 text-sm text-slate-200 [overflow-wrap:anywhere]">
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
