import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  Layers,
} from 'lucide-react';

import { useData } from '../../contexts/DataContext';
import type { PlanDocument } from '../../types';
import { DocumentModal } from '../DocumentModal';

// ── Artifact type mapping ─────────────────────────────────────────────────────

export type ArtifactDrillDownType =
  | 'design-specs'
  | 'prds'
  | 'implementation-plans'
  | 'contexts'
  | 'reports';

interface ArtifactTypeConfig {
  label: string;
  singularLabel: string;
  docTypeTokens: string[];
  docSubtypeTokens?: string[];
  rootKindTokens?: string[];
}

const ARTIFACT_TYPE_CONFIGS: Record<ArtifactDrillDownType, ArtifactTypeConfig> = {
  'design-specs': {
    label: 'Design Specs',
    singularLabel: 'Design Spec',
    docTypeTokens: ['spec'],
    docSubtypeTokens: ['design_spec', 'design_doc'],
  },
  'prds': {
    label: 'PRDs',
    singularLabel: 'PRD',
    docTypeTokens: ['prd'],
  },
  'implementation-plans': {
    label: 'Implementation Plans',
    singularLabel: 'Implementation Plan',
    docTypeTokens: ['implementation_plan'],
  },
  'contexts': {
    label: 'Context Files',
    singularLabel: 'Context File',
    docSubtypeTokens: ['context', 'context_notes', 'worknotes'],
    docTypeTokens: ['context'],
  },
  'reports': {
    label: 'Reports',
    singularLabel: 'Report',
    docTypeTokens: ['report'],
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function normalizeToken(value: string): string {
  return (value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function matchesConfig(doc: PlanDocument, config: ArtifactTypeConfig): boolean {
  const docTypeNorm = normalizeToken(doc.docType || '');
  const docSubtypeNorm = normalizeToken(doc.docSubtype || '');
  const rootKindNorm = normalizeToken(doc.rootKind || '');

  if (config.docTypeTokens.some(t => docTypeNorm === t)) return true;
  if (config.docSubtypeTokens?.some(t => docSubtypeNorm === t)) return true;
  if (config.rootKindTokens?.some(t => rootKindNorm === t)) return true;

  return false;
}

function getPrimaryDate(doc: PlanDocument): string {
  return doc.updatedAt || doc.lastModified || doc.createdAt || '';
}

function formatDate(value: string): string {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

function getStatusStyle(status: string): string {
  const s = normalizeToken(status);
  if (s === 'completed' || s === 'done') return 'bg-emerald-600/20 text-emerald-400';
  if (s === 'in_progress' || s === 'active') return 'bg-sky-600/20 text-sky-400';
  if (s === 'blocked') return 'bg-rose-600/20 text-rose-400';
  if (s === 'deferred' || s === 'archived') return 'bg-slate-600/40 text-slate-500';
  return 'bg-slate-700/60 text-slate-300';
}

// ── Document row ──────────────────────────────────────────────────────────────

function ArtifactRow({
  doc,
  onClick,
}: {
  doc: PlanDocument;
  onClick: () => void;
}) {
  const status = doc.statusNormalized || doc.status || 'unknown';
  const date = getPrimaryDate(doc);
  const summary = (doc.description || doc.summary || '').trim();

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-start gap-3 rounded-lg border border-panel-border bg-surface-elevated px-4 py-3 text-left transition-all hover:border-info/40 hover:bg-slate-700/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info/50"
    >
      <span className="mt-0.5 shrink-0 text-muted-foreground/60 group-hover:text-info transition-colors">
        <FileText size={14} />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="truncate text-sm font-medium text-panel-foreground group-hover:text-info transition-colors">
            {doc.title}
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium leading-none ${getStatusStyle(status)}`}
            >
              {status}
            </span>
            {date && (
              <span className="text-[10px] text-muted-foreground/60">
                {formatDate(date)}
              </span>
            )}
          </div>
        </div>
        {summary && (
          <p className="line-clamp-1 text-xs text-muted-foreground/70">{summary}</p>
        )}
        <p className="truncate font-mono text-[10px] text-muted-foreground/40">{doc.filePath}</p>
      </div>
    </button>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex max-w-sm flex-col items-center gap-3 rounded-xl border border-dashed border-panel-border bg-surface-elevated/40 px-10 py-8 text-center">
        <Layers size={28} className="text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">No {label.toLowerCase()} found.</p>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ArtifactDrillDownPage() {
  const { type } = useParams<{ type: string }>();
  const navigate = useNavigate();
  const { documents } = useData();
  const [selectedDoc, setSelectedDoc] = useState<PlanDocument | null>(null);

  const artifactType = type as ArtifactDrillDownType | undefined;
  const config = artifactType ? ARTIFACT_TYPE_CONFIGS[artifactType] : null;

  if (!config) {
    return (
      <div className="max-w-screen-xl space-y-6">
        <button
          onClick={() => navigate('/planning')}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-panel-foreground transition-colors"
        >
          <ArrowLeft size={13} />
          Back to Planning
        </button>
        <div className="rounded-lg border border-danger/40 bg-danger/5 px-6 py-4">
          <p className="text-sm text-danger-foreground">Unknown artifact type: {type}</p>
        </div>
      </div>
    );
  }

  const filtered = documents.filter(doc => matchesConfig(doc, config));
  const sorted = [...filtered].sort((a, b) => {
    const da = getPrimaryDate(a);
    const db = getPrimaryDate(b);
    return (db ? new Date(db).getTime() : 0) - (da ? new Date(da).getTime() : 0);
  });

  return (
    <div className="max-w-screen-xl space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/planning')}
            className="flex items-center gap-2 rounded-lg border border-panel-border bg-surface-elevated px-3 py-1.5 text-xs text-muted-foreground hover:text-panel-foreground hover:bg-slate-700/30 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info"
          >
            <ArrowLeft size={13} />
            Back to Planning
          </button>
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-info" />
            <h1 className="text-lg font-semibold text-panel-foreground">{config.label}</h1>
            <span className="rounded-full bg-slate-700/60 px-2 py-0.5 text-[10px] font-bold tabular-nums text-panel-foreground">
              {sorted.length}
            </span>
          </div>
        </div>
      </div>

      {/* List */}
      {sorted.length === 0 ? (
        <EmptyState label={config.label} />
      ) : (
        <div className="space-y-1.5">
          {sorted.map(doc => (
            <ArtifactRow
              key={doc.id}
              doc={doc}
              onClick={() => setSelectedDoc(doc)}
            />
          ))}
        </div>
      )}

      {/* Document Modal */}
      {selectedDoc && (
        <DocumentModal
          doc={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onBack={() => setSelectedDoc(null)}
          backLabel={config.label}
        />
      )}
    </div>
  );
}
