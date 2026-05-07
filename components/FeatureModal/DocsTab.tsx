/**
 * DocsTab — planning-owned tab component for the documents section.
 *
 * Domain: planning
 * Tab ID: 'docs'
 * Data: useFeatureModalPlanning().docs (SectionHandle)
 *
 * Renders document groups with their doc cards, summary metrics (doc count,
 * family position, execution gate summary), and doc-type breakdown chips.
 *
 * Design decisions:
 * - Document group expand/collapse state is local.
 * - Caller provides the derived data (linkedDocs, groupedDocs, etc.) from the
 *   legacy fullFeature path (P4 bridge). This component does not decode
 *   FeatureModalSectionDTO items — that is a P5 migration concern.
 * - Render callbacks (renderDocGrid) allow the caller to inject existing
 *   doc-card rendering without duplicating that logic here.
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Link2,
  Play,
  Terminal,
} from 'lucide-react';

import { TabStateView } from './TabStateView';
import { Surface } from '../ui/surface';
import type { SectionHandle } from '../../services/useFeatureModalCore';
import type { LinkedDocument } from '../../types';

// ── Doc group definitions (mirrors ProjectBoard constants) ────────────────────

export type DocGroupId = 'plans' | 'prds' | 'design' | 'specs' | 'reports' | 'progress' | 'other';

export interface DocGroupDefinition {
  id: DocGroupId;
  label: string;
  description?: string;
}

export const DOC_GROUPS: DocGroupDefinition[] = [
  { id: 'plans', label: 'Plans', description: 'Implementation & phase plans' },
  { id: 'prds', label: 'PRDs', description: 'Product requirement documents' },
  { id: 'design', label: 'Design', description: 'Design documents & specs' },
  { id: 'specs', label: 'Specs', description: 'Technical specifications' },
  { id: 'reports', label: 'Reports', description: 'After-action reports & findings' },
  { id: 'progress', label: 'Progress Files', description: 'Phase progress tracking files' },
  { id: 'other', label: 'Other', description: 'Uncategorised documents' },
];

// ── Doc type helpers ──────────────────────────────────────────────────────────

const DOC_TYPE_LABELS: Record<string, string> = {
  prd: 'PRD',
  implementation_plan: 'Plan',
  phase_plan: 'Phase Plan',
  progress: 'Progress',
  report: 'Report',
  design_doc: 'Design',
  spec: 'Spec',
};

export const getDocTypeLabel = (docType: string): string =>
  DOC_TYPE_LABELS[docType] || docType;

export const getDocTypeTone = (docType: string): string => {
  const tones: Record<string, string> = {
    prd: 'border-violet-500/30 bg-violet-500/10 text-violet-300',
    implementation_plan: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
    phase_plan: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300',
    progress: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    report: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    design_doc: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
    spec: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
  };
  return tones[docType] || 'border-panel-border bg-surface-muted text-muted-foreground';
};

export const getDocGroupIcon = (
  groupId: DocGroupId,
): React.ComponentType<{ size?: number; className?: string }> => {
  const icons: Partial<Record<DocGroupId, React.ComponentType<{ size?: number; className?: string }>>> = {
    plans: FileText,
    prds: FileText,
    progress: Terminal,
    reports: FileText,
  };
  return icons[groupId] ?? FileText;
};

// ── Metric tile (local, matches ProjectBoard's FeatureMetricTile) ─────────────

interface MetricTileProps {
  label: string;
  value: string | number;
  detail?: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accentClassName?: string;
}

const MetricTile: React.FC<MetricTileProps> = ({
  label,
  value,
  detail,
  icon: Icon,
  accentClassName = 'text-panel-foreground',
}) => (
  <div className="rounded-lg border border-panel-border bg-panel/80 p-3">
    <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
      <Icon size={12} aria-hidden="true" />
      {label}
    </div>
    <div className={`text-lg font-semibold ${accentClassName}`}>{value}</div>
    {detail && <div className="mt-0.5 truncate text-[10px] text-muted-foreground">{detail}</div>}
  </div>
);

// ── Progress bucket type ──────────────────────────────────────────────────────

export interface ProgressDocPhaseBucket {
  label: string;
  docs: LinkedDocument[];
}

// ── Prop types ────────────────────────────────────────────────────────────────

export interface DocsTabProps {
  /** Planning-domain section handle from useFeatureModalPlanning(). */
  handle: SectionHandle;

  /** All linked documents for this feature. */
  linkedDocs: LinkedDocument[];

  /**
   * Documents grouped by DocGroupId. Use a Map for predictable ordering.
   * Key: DocGroupId, Value: LinkedDocument[].
   */
  docsByGroup: Map<string, LinkedDocument[]>;

  /** Progress docs grouped by phase label. */
  progressDocPhaseBuckets?: ProgressDocPhaseBucket[];

  /**
   * Family position label string (e.g. "1 of 4").
   * Derived from the legacy fullFeature path.
   */
  familyPositionLabel?: string;
  /** Feature family name. */
  featureFamily?: string;
  /** Execution gate label (e.g. "Ready", "Blocked"). */
  executionGateLabel?: string;
  /** Execution gate detail text. */
  executionGateDetail?: string;

  /**
   * Render a grid of document cards.
   * The caller provides this because the doc card rendering is currently owned
   * by ProjectBoard. In P5 this will be replaced by an owned DocCard component.
   *
   * `isProgress` flag optionally toggles compact rendering.
   */
  renderDocGrid: (docs: LinkedDocument[], isProgress?: boolean) => React.ReactNode;
}

// ── Doc type count strip ──────────────────────────────────────────────────────

interface DocTypeCounts {
  docType: string;
  count: number;
}

function buildDocTypeCounts(docs: LinkedDocument[]): DocTypeCounts[] {
  const counts = new Map<string, number>();
  docs.forEach((doc) => {
    const dt = doc.docType || 'other';
    counts.set(dt, (counts.get(dt) ?? 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([docType, count]) => ({ docType, count }))
    .sort((a, b) => getDocTypeLabel(a.docType).localeCompare(getDocTypeLabel(b.docType)));
}

// ── Section header component ──────────────────────────────────────────────────

interface DocSectionProps {
  title: string;
  description?: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  docCount: number;
  isExpanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

const DocSection: React.FC<DocSectionProps> = ({
  title,
  description,
  icon: Icon,
  docCount,
  isExpanded,
  onToggle,
  children,
}) => (
  <section className="rounded-lg border border-panel-border bg-panel/80">
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon size={14} className="shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-panel-foreground">{title}</div>
        {description && (
          <div className="text-[10px] text-muted-foreground">{description}</div>
        )}
      </div>
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground transition-colors hover:text-panel-foreground"
        aria-expanded={isExpanded}
      >
        {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {docCount}
      </button>
    </div>
    {isExpanded && <div className="border-t border-panel-border px-4 pb-4 pt-3">{children}</div>}
  </section>
);

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * DocsTab — planning-owned tab content for the 'docs' ModalTabId.
 *
 * Accepts the SectionHandle from useFeatureModalPlanning().docs and derived
 * document data from the legacy fullFeature path (P4 bridge).
 */
export const DocsTab: React.FC<DocsTabProps> = ({
  handle,
  linkedDocs,
  docsByGroup,
  progressDocPhaseBuckets = [],
  familyPositionLabel = '-',
  featureFamily = '-',
  executionGateLabel = '-',
  executionGateDetail,
  renderDocGrid,
}) => {
  // Initial expand state: expand all groups that have docs.
  const initialExpanded = useMemo(() => {
    const expanded: Record<string, boolean> = {};
    DOC_GROUPS.forEach((g) => {
      expanded[g.id] = (docsByGroup.get(g.id) || []).length > 0;
    });
    return expanded;
  }, [docsByGroup]);

  const [docGroupExpanded, setDocGroupExpanded] = useState<Record<string, boolean>>(
    initialExpanded,
  );

  const toggleGroup = useCallback((groupId: string) => {
    setDocGroupExpanded((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  }, []);

  const docTypeCounts = useMemo(() => buildDocTypeCounts(linkedDocs), [linkedDocs]);
  const isEmpty = linkedDocs.length === 0 && handle.status === 'success';

  return (
    <TabStateView
      status={handle.status}
      error={handle.error?.message ?? null}
      onRetry={handle.retry}
      isEmpty={isEmpty}
      emptyLabel="No documents linked to this feature."
      staleLabel="Refreshing documents…"
    >
      <div className="space-y-4">
        {/* Summary metric tiles */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <MetricTile
            label="Document Groups"
            value={DOC_GROUPS.filter((g) => (docsByGroup.get(g.id) || []).length > 0).length}
            detail={`${linkedDocs.length} linked document${linkedDocs.length !== 1 ? 's' : ''}`}
            icon={FileText}
          />
          <MetricTile
            label="Family Position"
            value={familyPositionLabel}
            detail={featureFamily}
            icon={Link2}
            accentClassName="text-info"
          />
          <MetricTile
            label="Execution Gate"
            value={executionGateLabel}
            detail={executionGateDetail ?? 'No gate reason available'}
            icon={Play}
            accentClassName="text-warning"
          />
        </div>

        {/* Doc type breakdown */}
        {docTypeCounts.length > 0 && (
          <Surface tone="panel" padding="sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Types
              </span>
              {docTypeCounts.map((row) => (
                <span
                  key={`doc-type-count-${row.docType}`}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-bold uppercase ${getDocTypeTone(row.docType)}`}
                >
                  {getDocTypeLabel(row.docType)}
                  <span className="font-mono">{row.count}</span>
                </span>
              ))}
            </div>
          </Surface>
        )}

        {/* Empty state when no docs after confirmed load */}
        {linkedDocs.length === 0 && handle.status !== 'success' && (
          <div className="rounded-xl border border-dashed border-panel-border py-12 text-center text-muted-foreground">
            <FileText size={32} className="mx-auto mb-3 opacity-50" aria-hidden="true" />
            <p>No documents linked to this feature.</p>
          </div>
        )}

        {/* Doc group sections — exclude progress (handled separately below) */}
        {DOC_GROUPS.filter((g) => g.id !== 'progress').map((group) => {
          const docs = docsByGroup.get(group.id) || [];
          if (docs.length === 0) return null;

          const Icon = getDocGroupIcon(group.id);
          const implementationPlans =
            group.id === 'plans'
              ? docs.filter((d) => (d.docType || '').toLowerCase() === 'implementation_plan')
              : [];
          const phasePlans =
            group.id === 'plans'
              ? docs.filter((d) => (d.docType || '').toLowerCase() === 'phase_plan')
              : [];
          const isExpanded = docGroupExpanded[group.id] ?? false;

          return (
            <DocSection
              key={group.id}
              title={group.label}
              description={group.description}
              icon={Icon}
              docCount={docs.length}
              isExpanded={isExpanded}
              onToggle={() => toggleGroup(group.id)}
            >
              {group.id === 'plans' ? (
                <div className="space-y-4">
                  {implementationPlans.length > 0 && (
                    <div>
                      <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        Implementation Plans
                      </div>
                      {renderDocGrid(implementationPlans)}
                    </div>
                  )}
                  {phasePlans.length > 0 && (
                    <div>
                      <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        Phase Plans
                      </div>
                      {renderDocGrid(phasePlans)}
                    </div>
                  )}
                  {implementationPlans.length === 0 &&
                    phasePlans.length === 0 &&
                    renderDocGrid(docs)}
                </div>
              ) : (
                renderDocGrid(docs)
              )}
            </DocSection>
          );
        })}

        {/* Progress files section */}
        {(docsByGroup.get('progress') || []).length > 0 && (
          <DocSection
            title="Progress Files"
            description="Execution and phase progress files, grouped under their detected phase when available."
            icon={Terminal}
            docCount={(docsByGroup.get('progress') || []).length}
            isExpanded={docGroupExpanded['progress'] ?? false}
            onToggle={() => toggleGroup('progress')}
          >
            <div className="space-y-4">
              {progressDocPhaseBuckets.map((bucket) => (
                <div
                  key={`progress-${bucket.label}`}
                  className="rounded-lg border border-panel-border bg-surface-muted/55 p-3"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-panel-foreground">
                      {bucket.label}
                    </div>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {bucket.docs.length}
                    </span>
                  </div>
                  {renderDocGrid(bucket.docs, true)}
                </div>
              ))}
            </div>
          </DocSection>
        )}
      </div>
    </TabStateView>
  );
};

export default DocsTab;
