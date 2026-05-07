/**
 * OverviewTab — shared-shell composition layer for the 'overview' ModalTabId.
 *
 * Domain: shared-shell (metric tiles + execution gate) + planning (editorial sub-sections)
 *
 * Owns:
 *   - OverviewMetricStrip: four metric tiles from FeatureCardDTO / legacy feature data
 *   - ExecutionGateCard: execution domain sub-component (imported)
 *   - PlanningDeliverySection: Delivery Metadata + Quality Signals (legacy fullFeature path)
 *   - PlanningFamilySection: Family Position + Blocker Evidence (legacy fullFeature path)
 *
 * Design decisions (phase-4-tab-ownership.md § Decision 1):
 *   - Planning sub-sections continue to read from the legacy fullFeature path
 *     during P4; migration to FeatureModalSectionDTO items deferred to P5.
 *   - ExecutionGateCard is composed here; Begin Work CTA stays in the shell header.
 *   - All optional fields have explicit fallbacks (resilience-by-default).
 *
 * Constraints:
 *   - Does NOT call load() — that is the tab-activation effect's job.
 *   - Does NOT import ProjectBoard internals directly.
 */

import React from 'react';
import {
  BarChart3,
  Calendar,
  CheckCircle2,
  ClipboardList,
  ExternalLink,
  FileText,
  Filter,
  Layers,
  LayoutGrid,
  Link2,
  Tag,
} from 'lucide-react';

import { ExecutionGateCard } from './ExecutionGateCard';
import type {
  ExecutionGateState,
  FeatureDependencyEvidence,
  FeatureFamilyPosition,
  FeatureFamilySummary,
  LinkedDocument,
  LinkedFeatureRef,
} from '../../types';

// ── Local primitives (self-contained — mirrors ProjectBoard helpers without importing them) ──

interface MetricTileProps {
  label: string;
  value: React.ReactNode;
  detail?: string;
  icon: React.ComponentType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  accentClassName?: string;
}

const MetricTile: React.FC<MetricTileProps> = ({
  label,
  value,
  detail,
  icon: Icon,
  accentClassName,
}) => (
  <div className="rounded-lg border border-panel-border bg-panel p-3">
    <div className="mb-1.5 flex items-center gap-1.5">
      <Icon size={13} aria-hidden="true" />
      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
    </div>
    <div
      className={`text-2xl font-bold tabular-nums leading-none ${accentClassName ?? 'text-panel-foreground'}`}
    >
      {value}
    </div>
    {detail && <div className="mt-1.5 text-[11px] text-muted-foreground">{detail}</div>}
  </div>
);

interface SectionPanelProps {
  title: string;
  description?: string;
  icon?: React.ComponentType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  headerRight?: React.ReactNode;
  children?: React.ReactNode;
}

const SectionPanel: React.FC<SectionPanelProps> = ({
  title,
  description,
  icon: Icon,
  headerRight,
  children,
}) => (
  <div className="rounded-xl border border-panel-border bg-panel">
    <div className="flex items-start justify-between gap-3 border-b border-panel-border px-4 py-3">
      <div className="flex min-w-0 items-start gap-2">
        {Icon ? (
          <span className="mt-0.5 shrink-0 text-muted-foreground">
            <Icon size={14} aria-hidden="true" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-panel-foreground">{title}</h3>
          {description ? (
            <p className="mt-0.5 line-clamp-2 text-[11px] leading-5 text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
      </div>
      {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
    </div>
    <div className="p-4">{children}</div>
  </div>
);

interface FieldProps {
  label: string;
  value?: React.ReactNode;
  mono?: boolean;
}

const Field: React.FC<FieldProps> = ({ label, value, mono = false }) => (
  <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2">
    <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
      {label}
    </div>
    <div
      className={`mt-1 min-h-[18px] text-sm text-panel-foreground ${mono ? 'font-mono text-xs' : ''}`}
    >
      {value ?? '-'}
    </div>
  </div>
);

// ── Props ─────────────────────────────────────────────────────────────────────

export interface OverviewTabMetrics {
  totalTasks: number;
  completedTasks: number;
  deferredTasks: number;
  phasesCount: number;
  linkedDocsCount: number;
  pct: number;
  /** Count of document groups (summary text only). */
  docGroupCount?: number;
  /** Count of filtered phases (e.g. with current filter applied). */
  filteredPhasesCount?: number;
}

export interface OverviewTabDelivery {
  priority?: string | null;
  riskLevel?: string | null;
  complexity?: string | null;
  track?: string | null;
  featureFamily?: string | null;
  targetRelease?: string | null;
  milestone?: string | null;
  executionReadiness?: string | null;
  coverage?: string | null;

  qualitySignals?: {
    blockerCount?: number;
    atRiskTaskCount?: number;
    testImpact?: string | null;
    integritySignalRefs?: string[];
  } | null;

  blockedByCount?: number;
  relatedFeatureCount?: number;
}

export interface OverviewTabFamilyData {
  familyPosition?: FeatureFamilyPosition | null;
  familySummary?: FeatureFamilySummary | null;
  executionGate?: ExecutionGateState | null;
  blockingEvidence?: FeatureDependencyEvidence[];
  nextFamilyItemName?: string | null;
  nextFamilyItemId?: string | null;
  familyPositionLabel?: string;
  blockingReason?: string | null;
}

export interface OverviewTabDateSignals {
  plannedAt?: { value?: string | null; confidence?: string } | null;
  startedAt?: { value?: string | null; confidence?: string } | null;
  completedAt?: { value?: string | null; confidence?: string } | null;
  updatedAt?: { value?: string | null; confidence?: string } | null;
}

export interface OverviewTabProps {
  // ── Metric strip ────────────────────────────────────────────────────────────
  metrics: OverviewTabMetrics;

  // ── Delivery metadata + quality signals ─────────────────────────────────────
  delivery?: OverviewTabDelivery | null;

  // ── Family/execution data ────────────────────────────────────────────────────
  family?: OverviewTabFamilyData | null;

  // ── Date signals ─────────────────────────────────────────────────────────────
  dateSignals?: OverviewTabDateSignals | null;

  // ── Related/linked entities (for overview summary panels) ────────────────────
  blockedByRelations?: LinkedFeatureRef[];
  relatedFeatures?: string[];
  tags?: string[];
  linkedDocs?: LinkedDocument[];

  // ── Navigation callbacks ─────────────────────────────────────────────────────
  onFeatureNavigate?: (featureId: string) => void;
  onDocNavigate?: (doc: LinkedDocument) => void;
}

// ── OverviewTab ───────────────────────────────────────────────────────────────

export const OverviewTab: React.FC<OverviewTabProps> = ({
  metrics,
  delivery,
  family,
  dateSignals,
  blockedByRelations = [],
  relatedFeatures = [],
  tags = [],
  linkedDocs = [],
  onFeatureNavigate,
  onDocNavigate,
}) => {
  const featureValue = (val: string | null | undefined): string => val || '-';

  const qualitySignals = delivery?.qualitySignals ?? null;

  const resolvedFamilyPositionLabel =
    family?.familyPositionLabel ||
    '-';

  const executionGateDetail =
    family?.executionGate?.reason ||
    family?.blockingReason ||
    null;

  return (
    <div className="space-y-6">
      {/* ── Metric strip ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="Total Tasks"
          value={metrics.totalTasks}
          detail={`${metrics.pct}% overall progress`}
          icon={ClipboardList}
        />
        <MetricTile
          label="Completed"
          value={metrics.completedTasks}
          detail={
            metrics.deferredTasks > 0
              ? `${metrics.deferredTasks} deferred count as complete`
              : 'No deferred completion caveats'
          }
          icon={CheckCircle2}
          accentClassName="text-success"
        />
        <MetricTile
          label="Phases"
          value={metrics.phasesCount}
          detail={
            metrics.filteredPhasesCount !== undefined
              ? `${metrics.filteredPhasesCount} visible with current filters`
              : undefined
          }
          icon={Layers}
          accentClassName="text-info"
        />
        <MetricTile
          label="Documents"
          value={metrics.linkedDocsCount}
          detail={
            metrics.docGroupCount !== undefined
              ? `${metrics.docGroupCount} document groups`
              : undefined
          }
          icon={FileText}
          accentClassName="text-warning"
        />
      </div>

      {/* ── Delivery Metadata + Quality Signals ─────────────────────────────── */}
      {delivery ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
          <SectionPanel
            title="Delivery Metadata"
            description="Planning attributes that explain priority, ownership, release fit, and execution readiness."
            icon={LayoutGrid}
          >
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
              <Field label="Priority" value={featureValue(delivery.priority)} />
              <Field label="Risk" value={featureValue(delivery.riskLevel)} />
              <Field label="Complexity" value={featureValue(delivery.complexity)} />
              <Field label="Track" value={featureValue(delivery.track)} />
              <Field label="Family" value={featureValue(delivery.featureFamily)} mono />
              <Field label="Target" value={featureValue(delivery.targetRelease)} />
              <Field label="Milestone" value={featureValue(delivery.milestone)} />
              <Field label="Readiness" value={featureValue(delivery.executionReadiness)} />
              <Field label="Coverage" value={featureValue(delivery.coverage)} />
            </div>
          </SectionPanel>

          <SectionPanel
            title="Quality Signals"
            description="Risk and integrity signals that deserve attention before execution."
            icon={BarChart3}
          >
            <div className="grid grid-cols-2 gap-2">
              <Field label="Blockers" value={qualitySignals?.blockerCount ?? 0} />
              <Field label="At Risk" value={qualitySignals?.atRiskTaskCount ?? 0} />
              <Field label="Blocked By" value={delivery.blockedByCount ?? 0} />
              <Field
                label="Test Impact"
                value={featureValue(delivery.riskLevel ?? qualitySignals?.testImpact)}
              />
              <Field label="Relations" value={delivery.relatedFeatureCount ?? 0} />
            </div>
            {(qualitySignals?.integritySignalRefs || []).length > 0 && (
              <div className="mt-3 rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2 text-[11px] text-muted-foreground">
                <span className="font-semibold text-panel-foreground">Integrity refs:</span>{' '}
                {(qualitySignals?.integritySignalRefs || []).join(', ')}
              </div>
            )}
          </SectionPanel>
        </div>
      ) : null}

      {/* ── Execution Gate + Family Position + Blocker Evidence ─────────────── */}
      {family ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {/* ExecutionGateCard — execution domain (composed here per Decision 3) */}
          <ExecutionGateCard
            executionGate={family.executionGate}
            blockingReason={executionGateDetail}
            familyPosition={family.familyPosition}
            nextFamilyItemName={family.nextFamilyItemName}
          />

          <SectionPanel
            title="Family Position"
            description="Where this feature sits in its execution family."
            icon={Link2}
            headerRight={
              <span className="inline-flex max-w-[160px] items-center truncate rounded-md border border-info-border bg-info/10 px-2 py-0.5 font-mono text-[10px] uppercase text-info">
                {family.familySummary?.featureFamily || delivery?.featureFamily || '-'}
              </span>
            }
          >
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <Field label="Position" value={resolvedFamilyPositionLabel} />
              <Field
                label="Sequenced"
                value={
                  family.familySummary?.sequencedItems ??
                  family.familyPosition?.sequencedItems ??
                  0
                }
              />
              <Field
                label="Unsequenced"
                value={
                  family.familySummary?.unsequencedItems ??
                  family.familyPosition?.unsequencedItems ??
                  0
                }
              />
              <Field
                label="Next feature"
                value={
                  family.familySummary?.nextRecommendedFeatureId ||
                  family.nextFamilyItemId ||
                  '-'
                }
                mono
              />
            </div>
          </SectionPanel>

          <SectionPanel
            title="Blocker Evidence"
            description="Dependency evidence attached to this feature."
            icon={Filter}
            headerRight={
              <span
                className={`rounded-md border px-2 py-0.5 font-mono text-[10px] ${
                  (family.blockingEvidence || []).length > 0
                    ? 'border-danger-border bg-danger/10 text-danger'
                    : 'border-success-border bg-success/10 text-success'
                }`}
              >
                {(family.blockingEvidence || []).length}
              </span>
            }
          >
            {(family.blockingEvidence || []).length > 0 ? (
              <div className="space-y-2">
                {(family.blockingEvidence || []).slice(0, 3).map((evidence) => (
                  <div
                    key={evidence.dependencyFeatureId}
                    className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-[11px]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-foreground">
                        {evidence.dependencyFeatureName || evidence.dependencyFeatureId}
                      </span>
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                          evidence.state === 'complete'
                            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                            : evidence.state === 'blocked_unknown'
                              ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                              : 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                        }`}
                      >
                        {evidence.state}
                      </span>
                    </div>
                    {evidence.blockingReason ? (
                      <div className="mt-1 text-muted-foreground">{evidence.blockingReason}</div>
                    ) : null}
                  </div>
                ))}
                {(family.blockingEvidence || []).length > 3 && (
                  <div className="text-[11px] text-muted-foreground">
                    +{(family.blockingEvidence || []).length - 3} more blocker entries
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs italic text-muted-foreground">
                No blocker evidence is attached.
              </p>
            )}
          </SectionPanel>
        </div>
      ) : null}

      {/* ── Date Signals ────────────────────────────────────────────────────── */}
      {dateSignals ? (
        <SectionPanel title="Date Signals" icon={Calendar}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: 'Planned', signal: dateSignals.plannedAt },
              { label: 'Started', signal: dateSignals.startedAt },
              { label: 'Completed', signal: dateSignals.completedAt },
              { label: 'Updated', signal: dateSignals.updatedAt },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3 text-xs"
              >
                <div className="font-bold uppercase tracking-wider text-muted-foreground">
                  {item.label}
                </div>
                <div className="mt-1 text-sm text-panel-foreground">
                  {item.signal?.value
                    ? new Date(item.signal.value).toLocaleDateString()
                    : '-'}
                  {item.signal?.confidence ? ` (${item.signal.confidence})` : ''}
                </div>
              </div>
            ))}
          </div>
        </SectionPanel>
      ) : null}

      {/* ── Hard Dependencies + Linked Docs ─────────────────────────────────── */}
      {blockedByRelations.length > 0 && (
        <SectionPanel title="Hard Dependencies" icon={Link2}>
          <div className="flex flex-wrap gap-2">
            {blockedByRelations.map((relation, idx) => (
              <button
                key={`${relation.feature}-${idx}`}
                type="button"
                onClick={() => onFeatureNavigate?.(relation.feature)}
                className="rounded-full border border-danger-border bg-danger/10 px-2 py-1 text-[10px] font-semibold text-danger"
              >
                {relation.feature}
              </button>
            ))}
          </div>
        </SectionPanel>
      )}

      {linkedDocs.length > 0 && (
        <SectionPanel title="Linked Documents" icon={FileText}>
          <div className="space-y-2">
            {linkedDocs.map((doc) => (
              <button
                key={doc.id}
                type="button"
                onClick={() => onDocNavigate?.(doc)}
                className="group flex w-full items-center gap-3 rounded-lg border border-panel-border bg-surface-overlay/70 p-3 text-left transition-all hover:border-info-border hover:bg-surface-muted/70"
              >
                <FileText size={14} className="shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="flex-1 truncate text-sm text-foreground transition-colors group-hover:text-info">
                  {doc.title}
                </span>
                <span className="shrink-0 rounded border border-panel-border bg-surface-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                  {doc.docType || 'doc'}
                </span>
                <ExternalLink
                  size={12}
                  className="shrink-0 text-muted-foreground transition-colors group-hover:text-info"
                  aria-hidden="true"
                />
              </button>
            ))}
          </div>
        </SectionPanel>
      )}

      {/* ── Related Features ────────────────────────────────────────────────── */}
      {relatedFeatures.length > 0 && (
        <SectionPanel title="Related Features" icon={Link2}>
          <div className="flex flex-wrap gap-2">
            {relatedFeatures.map((rel) => (
              <span
                key={rel}
                className="rounded border border-panel-border bg-surface-muted px-2 py-1 text-xs text-info"
              >
                {rel}
              </span>
            ))}
          </div>
        </SectionPanel>
      )}

      {/* ── Tags ────────────────────────────────────────────────────────────── */}
      {tags.length > 0 && (
        <SectionPanel title="Tags" icon={Tag}>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <span
                key={tag}
                className="flex items-center gap-1 rounded-full border border-panel-border bg-surface-muted px-2 py-1 text-[10px] text-muted-foreground"
              >
                <Tag size={10} aria-hidden="true" />
                {tag}
              </span>
            ))}
          </div>
        </SectionPanel>
      )}
    </div>
  );
};

export default OverviewTab;
