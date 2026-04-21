import type { ReactNode } from 'react';
import { Ban, ChevronRight, Clock, FileText, GitMerge, Layers } from 'lucide-react';

import type { FeatureSummaryItem, ProjectPlanningSummary } from '../../types';
import type { ArtifactDrillDownType } from './ArtifactDrillDownPage';
import {
  ArtifactChip,
  MetricTile,
  Panel,
  SectionHeader,
  StatusPill,
} from './primitives';

export interface PlanningSummaryPanelProps {
  summary: ProjectPlanningSummary;
  onSelectFeature?: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
  onDrillDown?: (type: ArtifactDrillDownType) => void;
}

interface FeatureRowProps {
  item: FeatureSummaryItem;
  onSelectFeature?: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
}

interface AttentionColumnProps {
  title: string;
  icon: ReactNode;
  items: FeatureSummaryItem[];
  onSelectFeature?: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
  accent: string;
}

const ROW_LIMIT = 8;

function artifactKindForType(type?: ArtifactDrillDownType): string {
  switch (type) {
    case 'design-specs':
      return 'spec';
    case 'prds':
      return 'prd';
    case 'implementation-plans':
      return 'implementation_plan';
    case 'contexts':
      return 'context';
    case 'reports':
      return 'report';
    default:
      return 'tracker';
  }
}

function FeatureRow({ item, onSelectFeature, onPrefetchFeature }: FeatureRowProps) {
  const statusMismatch = item.rawStatus !== item.effectiveStatus;

  return (
    <button
      type="button"
      aria-label={`View planning context for ${item.featureName}`}
      onClick={() => onSelectFeature?.(item.featureId)}
      onMouseEnter={() => onPrefetchFeature?.(item.featureId)}
      onFocus={() => onPrefetchFeature?.(item.featureId)}
      className="planning-row group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[color:var(--bg-3)] focus-visible:outline-none"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-[color:var(--ink-0)] group-hover:text-[color:var(--brand)]">
          {item.featureName}
        </p>
        <p className="truncate text-xs text-[color:var(--ink-2)]">
          {item.phaseCount} phase{item.phaseCount !== 1 ? 's' : ''}
          {item.blockedPhaseCount > 0 ? (
            <span className="ml-1" style={{ color: 'var(--err)' }}>
              • {item.blockedPhaseCount} blocked
            </span>
          ) : null}
        </p>
        {statusMismatch ? (
          <div className="mt-1 flex items-center gap-2 text-[10px]">
            <StatusPill status={item.rawStatus} />
            <ChevronRight size={10} className="text-[color:var(--ink-3)]" />
            <StatusPill status={item.effectiveStatus} />
          </div>
        ) : null}
      </div>
      <ChevronRight size={14} className="shrink-0 text-[color:var(--ink-3)] group-hover:text-[color:var(--brand)]" />
    </button>
  );
}

function AttentionColumn({
  title,
  icon,
  items,
  onSelectFeature,
  onPrefetchFeature,
  accent,
}: AttentionColumnProps) {
  const visible = items.slice(0, ROW_LIMIT);
  const overflow = items.length - ROW_LIMIT;

  return (
    <Panel className="flex flex-col gap-2 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: accent }}>
        {icon}
        {title}
        <span
          className="planning-tnum ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold text-[color:var(--ink-0)]"
          style={{ background: 'color-mix(in oklab, var(--ink-2) 16%, transparent)' }}
        >
          {items.length}
        </span>
      </div>
      <div className="mt-1 flex flex-col gap-0.5">
        {visible.length === 0 ? (
          <p className="py-4 text-center text-xs text-[color:var(--ink-3)]">All clear.</p>
        ) : (
          <>
            {visible.map((item) => (
              <FeatureRow
                key={item.featureId}
                item={item}
                onSelectFeature={onSelectFeature}
                onPrefetchFeature={onPrefetchFeature}
              />
            ))}
            {overflow > 0 ? (
              <p className="mt-1 text-center text-[11px] text-[color:var(--ink-3)]">
                +{overflow} more
              </p>
            ) : null}
          </>
        )}
      </div>
    </Panel>
  );
}

export function PlanningSummaryPanel({
  summary,
  onSelectFeature,
  onPrefetchFeature,
  onDrillDown,
}: PlanningSummaryPanelProps) {
  if (summary.featureSummaries.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <Panel className="flex max-w-sm flex-col items-center gap-3 border-dashed px-10 py-8 text-center">
          <FileText size={28} className="text-[color:var(--ink-3)]" />
          <p className="text-sm text-[color:var(--ink-2)]">No planning artifacts discovered yet.</p>
        </Panel>
      </div>
    );
  }

  const featureById = new Map<string, FeatureSummaryItem>(
    summary.featureSummaries.map((feature) => [feature.featureId, feature]),
  );

  const resolveIds = (ids: string[]): FeatureSummaryItem[] =>
    ids.flatMap((id) => {
      const item = featureById.get(id);
      return item ? [item] : [];
    });

  const staleItems = resolveIds(summary.staleFeatureIds);
  const blockedItems = resolveIds(summary.blockedFeatureIds);
  const mismatchedFromSummaries = summary.featureSummaries.filter((feature) => feature.isMismatch);
  const reversedItems = resolveIds(summary.reversalFeatureIds);
  const mismatchSet = new Map<string, FeatureSummaryItem>();

  for (const item of [...mismatchedFromSummaries, ...reversedItems]) {
    mismatchSet.set(item.featureId, item);
  }

  const mismatchItems = Array.from(mismatchSet.values());

  const artifactEntries: { label: string; count: number; drillDownType?: ArtifactDrillDownType }[] = [
    { label: 'PRDs', count: summary.nodeCountsByType.prd, drillDownType: 'prds' },
    { label: 'Design Specs', count: summary.nodeCountsByType.designSpec, drillDownType: 'design-specs' },
    { label: 'Implementation Plans', count: summary.nodeCountsByType.implementationPlan, drillDownType: 'implementation-plans' },
    { label: 'Context', count: summary.nodeCountsByType.context, drillDownType: 'contexts' },
    { label: 'Trackers', count: summary.nodeCountsByType.tracker },
    { label: 'Reports', count: summary.nodeCountsByType.report, drillDownType: 'reports' },
  ];

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <MetricTile label="Total Features" value={summary.totalFeatureCount} accent="var(--ink-0)" />
        <MetricTile
          label="Active"
          value={summary.activeFeatureCount}
          accent={summary.activeFeatureCount === 0 ? 'var(--ink-3)' : 'var(--ok)'}
        />
        <MetricTile
          label="Stale"
          value={summary.staleFeatureCount}
          accent={summary.staleFeatureCount === 0 ? 'var(--ink-3)' : 'var(--warn)'}
        />
        <MetricTile
          label="Blocked"
          value={summary.blockedFeatureCount}
          accent={summary.blockedFeatureCount === 0 ? 'var(--ink-3)' : 'var(--err)'}
        />
        <MetricTile
          label="Mismatches"
          value={summary.mismatchCount}
          accent={summary.mismatchCount === 0 ? 'var(--ink-3)' : 'var(--mag)'}
        />
      </div>

      <Panel className="p-4">
        <SectionHeader
          className="mb-3"
          eyebrow="Corpus View"
          heading="Artifact Composition"
          glyph={<Layers size={15} />}
        />
        <div className="flex flex-wrap gap-2">
          {artifactEntries.map(({ label, count, drillDownType }) => (
            <ArtifactChip
              key={label}
              kind={artifactKindForType(drillDownType)}
              label={label}
              count={count}
              onClick={drillDownType && onDrillDown && count > 0 ? () => onDrillDown(drillDownType) : undefined}
              aria-label={drillDownType && count > 0 ? `View ${count} ${label}` : undefined}
            />
          ))}
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <AttentionColumn
          title="Stale Features"
          icon={<Clock size={14} />}
          items={staleItems}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          accent="var(--warn)"
        />
        <AttentionColumn
          title="Blocked Features"
          icon={<Ban size={14} />}
          items={blockedItems}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          accent="var(--err)"
        />
        <AttentionColumn
          title="Mismatched / Reversed"
          icon={<GitMerge size={14} />}
          items={mismatchItems}
          onSelectFeature={onSelectFeature}
          onPrefetchFeature={onPrefetchFeature}
          accent="var(--mag)"
        />
      </div>
    </section>
  );
}
