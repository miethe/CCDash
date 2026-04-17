import {
  Ban,
  ChevronRight,
  Clock,
  FileText,
  GitMerge,
  Layers,
} from 'lucide-react';

import type { FeatureSummaryItem, ProjectPlanningSummary } from '../../types';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface PlanningSummaryPanelProps {
  summary: ProjectPlanningSummary;
  onSelectFeature?: (featureId: string) => void;
}

// ── Health metric tile ────────────────────────────────────────────────────────

interface MetricTileProps {
  label: string;
  value: number;
  accent?: string;
  dimWhenZero?: boolean;
}

function MetricTile({ label, value, accent = 'text-panel-foreground', dimWhenZero = false }: MetricTileProps) {
  const effectiveAccent = dimWhenZero && value === 0 ? 'text-muted-foreground/50' : accent;
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-panel-border bg-surface-elevated px-4 py-3 shadow-sm">
      <span className={`text-2xl font-bold tabular-nums leading-none ${effectiveAccent}`}>
        {value}
      </span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

// ── Artifact chip ─────────────────────────────────────────────────────────────

interface ArtifactChipProps {
  label: string;
  count: number;
}

function ArtifactChip({ label, count }: ArtifactChipProps) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-panel-border bg-surface-elevated/70 px-3 py-1 text-xs text-muted-foreground">
      {label}
      <span className="rounded-full bg-slate-600/60 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-panel-foreground">
        {count}
      </span>
    </span>
  );
}

// ── Feature row ───────────────────────────────────────────────────────────────

interface FeatureRowProps {
  item: FeatureSummaryItem;
  onSelectFeature?: (featureId: string) => void;
}

function FeatureRow({ item, onSelectFeature }: FeatureRowProps) {
  const statusMismatch = item.rawStatus !== item.effectiveStatus;
  return (
    <button
      type="button"
      aria-label={`View planning context for ${item.featureName}`}
      onClick={() => onSelectFeature?.(item.featureId)}
      className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-slate-700/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info/50"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-panel-foreground group-hover:text-info">
          {item.featureName}
        </p>
        <p className="truncate text-xs text-muted-foreground/70">
          {item.phaseCount} phase{item.phaseCount !== 1 ? 's' : ''}
          {item.blockedPhaseCount > 0 && (
            <span className="ml-1 text-rose-400">
              • {item.blockedPhaseCount} blocked
            </span>
          )}
        </p>
        {statusMismatch && (
          <p className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground/60">
            <span className="font-medium text-slate-400">{item.rawStatus}</span>
            <ChevronRight size={10} />
            <span className="font-medium text-fuchsia-400">{item.effectiveStatus}</span>
          </p>
        )}
      </div>
      <ChevronRight size={14} className="shrink-0 text-muted-foreground/40 group-hover:text-info" />
    </button>
  );
}

// ── Attention column ──────────────────────────────────────────────────────────

const ROW_LIMIT = 8;

interface AttentionColumnProps {
  title: string;
  icon: React.ReactNode;
  items: FeatureSummaryItem[];
  onSelectFeature?: (featureId: string) => void;
  accentClass?: string;
}

function AttentionColumn({
  title,
  icon,
  items,
  onSelectFeature,
  accentClass = 'text-muted-foreground',
}: AttentionColumnProps) {
  const visible = items.slice(0, ROW_LIMIT);
  const overflow = items.length - ROW_LIMIT;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-panel-border bg-surface-elevated p-4 shadow-sm">
      <div className={`flex items-center gap-2 text-sm font-semibold ${accentClass}`}>
        {icon}
        {title}
        <span className="ml-auto rounded-full bg-slate-700/60 px-2 py-0.5 text-[10px] font-bold tabular-nums text-panel-foreground">
          {items.length}
        </span>
      </div>
      <div className="mt-1 flex flex-col gap-0.5">
        {visible.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground/50">All clear.</p>
        ) : (
          <>
            {visible.map((item) => (
              <FeatureRow key={item.featureId} item={item} onSelectFeature={onSelectFeature} />
            ))}
            {overflow > 0 && (
              <p className="mt-1 text-center text-[11px] text-muted-foreground/60">
                +{overflow} more
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PlanningSummaryPanel({ summary, onSelectFeature }: PlanningSummaryPanelProps) {
  // Graceful empty state
  if (summary.featureSummaries.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="flex max-w-sm flex-col items-center gap-3 rounded-xl border border-dashed border-panel-border bg-surface-elevated/40 px-10 py-8 text-center">
          <FileText size={28} className="text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">No planning artifacts discovered yet.</p>
        </div>
      </div>
    );
  }

  // Build lookup map for quick feature resolution
  const featureById = new Map<string, FeatureSummaryItem>(
    summary.featureSummaries.map((f) => [f.featureId, f])
  );

  const resolveIds = (ids: string[]): FeatureSummaryItem[] =>
    ids.flatMap((id) => {
      const item = featureById.get(id);
      return item ? [item] : [];
    });

  // Stale
  const staleItems = resolveIds(summary.staleFeatureIds);

  // Blocked
  const blockedItems = resolveIds(summary.blockedFeatureIds);

  // Mismatched + reversed (union, deduplicated by featureId)
  const mismatchedFromSummaries = summary.featureSummaries.filter((f) => f.isMismatch);
  const reversedItems = resolveIds(summary.reversalFeatureIds);
  const mismatchSet = new Map<string, FeatureSummaryItem>();
  for (const item of [...mismatchedFromSummaries, ...reversedItems]) {
    mismatchSet.set(item.featureId, item);
  }
  const mismatchItems = Array.from(mismatchSet.values());

  // Artifact composition entries
  const artifactEntries: { label: string; count: number }[] = [
    { label: 'PRDs', count: summary.nodeCountsByType.prd },
    { label: 'Design Specs', count: summary.nodeCountsByType.designSpec },
    { label: 'Implementation Plans', count: summary.nodeCountsByType.implementationPlan },
    { label: 'Progress', count: summary.nodeCountsByType.progress },
    { label: 'Context', count: summary.nodeCountsByType.context },
    { label: 'Trackers', count: summary.nodeCountsByType.tracker },
    { label: 'Reports', count: summary.nodeCountsByType.report },
  ];

  return (
    <section className="space-y-4">
      {/* ── Planning Health header row ─────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <MetricTile
          label="Total Features"
          value={summary.totalFeatureCount}
          accent="text-panel-foreground"
        />
        <MetricTile
          label="Active"
          value={summary.activeFeatureCount}
          accent="text-emerald-400"
          dimWhenZero
        />
        <MetricTile
          label="Stale"
          value={summary.staleFeatureCount}
          accent="text-amber-400"
          dimWhenZero
        />
        <MetricTile
          label="Blocked"
          value={summary.blockedFeatureCount}
          accent="text-rose-400"
          dimWhenZero
        />
        <MetricTile
          label="Mismatches"
          value={summary.mismatchCount}
          accent="text-fuchsia-400"
          dimWhenZero
        />
      </div>

      {/* ── Artifact Composition card ──────────────────────────────────── */}
      <div className="rounded-xl border border-panel-border bg-surface-elevated p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-panel-foreground">
          <Layers size={15} className="text-info" />
          Artifact Composition
        </div>
        <div className="flex flex-wrap gap-2">
          {artifactEntries.map(({ label, count }) => (
            <ArtifactChip key={label} label={label} count={count} />
          ))}
        </div>
      </div>

      {/* ── Attention lists ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <AttentionColumn
          title="Stale Features"
          icon={<Clock size={14} />}
          items={staleItems}
          onSelectFeature={onSelectFeature}
          accentClass="text-amber-400"
        />
        <AttentionColumn
          title="Blocked Features"
          icon={<Ban size={14} />}
          items={blockedItems}
          onSelectFeature={onSelectFeature}
          accentClass="text-rose-400"
        />
        <AttentionColumn
          title="Mismatched / Reversed"
          icon={<GitMerge size={14} />}
          items={mismatchItems}
          onSelectFeature={onSelectFeature}
          accentClass="text-fuchsia-400"
        />
      </div>
    </section>
  );
}
