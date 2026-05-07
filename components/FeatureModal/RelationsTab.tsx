/**
 * RelationsTab — planning-owned tab component for the relations section.
 *
 * Domain: planning
 * Tab ID: 'relations'
 * Data: useFeatureModalPlanning().relations (SectionHandle)
 *
 * Renders:
 *   - Dependency evidence cards (blocking dependencies with state badges)
 *   - Family order summary (family name, position, next item)
 *   - Typed feature relations list
 *   - Related features chip cloud
 *   - Lineage signals (doc-level lineage metadata)
 *
 * Navigation:
 * - When `launchedFromPlanning` is true (caller is on /planning route),
 *   feature navigation uses planningRouteFeatureModalHref() so the URL
 *   stays within the planning route context.
 * - When false (launched from /board), navigation uses planningFeatureModalHref()
 *   which routes to the board's modal.
 * - Caller can also pass a fully custom `onFeatureNavigate` callback to override
 *   routing entirely (used in tests and from non-standard launch contexts).
 */

import React from 'react';

import { TabStateView } from './TabStateView';
import type { SectionHandle } from '../../services/useFeatureModalCore';
import type {
  FeatureDependencyEvidence,
  FeatureFamilyPosition,
  FeatureFamilySummary,
  LinkedDocument,
  LinkedFeatureRef,
} from '../../types';
import {
  planningFeatureModalHref,
  planningRouteFeatureModalHref,
} from '../../services/planningRoutes';

// ── Helper: resolve feature navigation href ───────────────────────────────────

function resolveFeatureHref(
  featureId: string,
  launchedFromPlanning: boolean,
): string {
  return launchedFromPlanning
    ? planningRouteFeatureModalHref(featureId)
    : planningFeatureModalHref(featureId);
}

// ── Prop types ────────────────────────────────────────────────────────────────

export interface RelationsTabProps {
  /** Planning-domain section handle from useFeatureModalPlanning(). */
  handle: SectionHandle;

  // ── Dependency evidence ────────────────────────────────────────────────────

  /**
   * Blocking dependency evidence array from the legacy fullFeature path.
   * Migrates to FeatureModalSectionDTO items in P5.
   */
  blockingEvidence?: FeatureDependencyEvidence[];

  // ── Family data ────────────────────────────────────────────────────────────

  familyPosition?: FeatureFamilyPosition | null;
  familySummary?: FeatureFamilySummary | null;
  nextFamilyItemLabel?: string;
  nextFamilyItemId?: string;
  /** Human-readable family position label (e.g. "1 of 4"). */
  familyPositionLabel?: string;
  /** Feature family name string. */
  featureFamily?: string;

  // ── Typed relations ────────────────────────────────────────────────────────

  linkedFeatures?: LinkedFeatureRef[];
  relatedFeatures?: string[];

  // ── Lineage ────────────────────────────────────────────────────────────────

  /**
   * Subset of linked docs that carry lineage metadata.
   * Used to render the Lineage Signals section.
   */
  linkedDocs?: LinkedDocument[];

  // ── Navigation ────────────────────────────────────────────────────────────

  /**
   * When true the tab uses planningRouteFeatureModalHref() for feature navigation
   * (stays within /planning). When false uses planningFeatureModalHref() (/board).
   * Defaults to false.
   */
  launchedFromPlanning?: boolean;

  /**
   * Override navigation handler for feature links.
   * When provided, this is called instead of the default href resolution.
   * The caller is responsible for closing any current modal if needed.
   */
  onFeatureNavigate?: (featureId: string) => void;

  /** Called to close the current modal before feature navigation. */
  onClose?: () => void;
}

// ── Sub-components ────────────────────────────────────────────────────────────

type DependencyState = 'complete' | 'blocked_unknown' | string;

function dependencyStateTone(state: DependencyState): string {
  if (state === 'complete') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  if (state === 'blocked_unknown') return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  return 'border-rose-500/30 bg-rose-500/10 text-rose-200';
}

interface SectionCardProps {
  title: string;
  children: React.ReactNode;
}

const SectionCard: React.FC<SectionCardProps> = ({ title, children }) => (
  <div className="rounded-lg border border-panel-border bg-panel p-4">
    <h3 className="mb-3 text-xs font-bold uppercase text-muted-foreground">{title}</h3>
    {children}
  </div>
);

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * RelationsTab — planning-owned tab content for the 'relations' ModalTabId.
 *
 * Accepts the SectionHandle from useFeatureModalPlanning().relations and
 * domain data derived from the legacy fullFeature path (P4 bridge).
 */
export const RelationsTab: React.FC<RelationsTabProps> = ({
  handle,
  blockingEvidence = [],
  familyPosition,
  familySummary,
  nextFamilyItemLabel,
  nextFamilyItemId,
  familyPositionLabel = '-',
  featureFamily,
  linkedFeatures = [],
  relatedFeatures = [],
  linkedDocs = [],
  launchedFromPlanning = false,
  onFeatureNavigate,
  onClose,
}) => {
  // Navigation handler: prefer explicit callback, else derive from route context.
  const navigateToFeature = (featureId: string) => {
    if (onFeatureNavigate) {
      onFeatureNavigate(featureId);
      return;
    }
    onClose?.();
    const href = resolveFeatureHref(featureId, launchedFromPlanning);
    window.location.href = href;
  };

  const hasRelations =
    linkedFeatures.length > 0 ||
    relatedFeatures.length > 0 ||
    blockingEvidence.length > 0;

  const isEmpty = !hasRelations && handle.status === 'success';

  // Docs with lineage metadata.
  const lineageDocs = linkedDocs.filter(
    (doc) =>
      doc.lineageFamily || doc.lineageParent || (doc.lineageChildren || []).length > 0,
  );

  const resolvedFamilyName =
    familySummary?.featureFamily || featureFamily || '-';
  const resolvedNextItem =
    nextFamilyItemLabel ||
    familyPosition?.nextItemLabel ||
    familySummary?.nextRecommendedFamilyItem?.featureName ||
    '-';
  const resolvedNextItemId =
    nextFamilyItemId ||
    familyPosition?.nextItemId ||
    familySummary?.nextRecommendedFeatureId ||
    '-';

  return (
    <TabStateView
      status={handle.status}
      error={handle.error?.message ?? null}
      onRetry={handle.retry}
      isEmpty={isEmpty}
      emptyLabel="No relations found for this feature."
      staleLabel="Refreshing relations…"
    >
      <div className="space-y-4">
        {/* Top row: Dependency Evidence + Family Order */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Dependency Evidence */}
          <SectionCard title="Dependency Evidence">
            {blockingEvidence.length > 0 ? (
              <div className="space-y-2">
                {blockingEvidence.map((evidence) => (
                  <div
                    key={`dependency-${evidence.dependencyFeatureId}`}
                    className="rounded border border-panel-border bg-surface-overlay px-3 py-2 text-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          if (!evidence.dependencyFeatureId) return;
                          navigateToFeature(evidence.dependencyFeatureId);
                        }}
                        className="truncate text-left font-mono text-indigo-300 transition-colors hover:text-indigo-200"
                      >
                        {evidence.dependencyFeatureName || evidence.dependencyFeatureId}
                      </button>
                      <span
                        className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${dependencyStateTone(evidence.state)}`}
                      >
                        {evidence.state}
                      </span>
                    </div>
                    {evidence.blockingReason && (
                      <div className="mt-1 text-muted-foreground">
                        {evidence.blockingReason}
                      </div>
                    )}
                    {evidence.dependencyCompletionEvidence.length > 0 && (
                      <div className="mt-1 text-muted-foreground">
                        Evidence:{' '}
                        <span className="font-mono text-foreground">
                          {evidence.dependencyCompletionEvidence.join(', ')}
                        </span>
                      </div>
                    )}
                    {(evidence.blockingDocumentIds || []).length > 0 && (
                      <div className="mt-1 text-muted-foreground">
                        Documents:{' '}
                        <span className="font-mono text-foreground">
                          {evidence.blockingDocumentIds.join(', ')}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs italic text-muted-foreground">
                No dependency evidence is attached.
              </p>
            )}
          </SectionCard>

          {/* Family Order */}
          <SectionCard title="Family Order">
            <dl className="space-y-2 text-xs">
              <div className="flex items-baseline gap-2">
                <dt className="text-muted-foreground">Family</dt>
                <dd className="ml-1 font-mono text-panel-foreground">{resolvedFamilyName}</dd>
              </div>
              <div className="flex items-baseline gap-2">
                <dt className="text-muted-foreground">Position</dt>
                <dd className="ml-1 text-panel-foreground">{familyPositionLabel}</dd>
              </div>
              <div className="flex items-baseline gap-2">
                <dt className="text-muted-foreground">Next item</dt>
                <dd className="ml-1 font-mono text-panel-foreground">{resolvedNextItem}</dd>
              </div>
              <div className="flex items-baseline gap-2">
                <dt className="text-muted-foreground">Recommended feature</dt>
                <dd className="ml-1 font-mono text-panel-foreground">{resolvedNextItemId}</dd>
              </div>
            </dl>
          </SectionCard>
        </div>

        {/* Typed Feature Relations */}
        <SectionCard title="Typed Feature Relations">
          {linkedFeatures.length > 0 ? (
            <div className="space-y-2">
              {linkedFeatures.map((relation, index) => (
                <div
                  key={`${relation.feature}-${relation.type ?? ''}-${relation.source ?? ''}-${index}`}
                  className="flex flex-wrap items-center gap-2 rounded border border-panel-border bg-surface-overlay px-3 py-2 text-xs"
                >
                  <button
                    type="button"
                    onClick={() => navigateToFeature(relation.feature)}
                    className="font-mono text-indigo-300 transition-colors hover:text-indigo-200"
                  >
                    {relation.feature}
                  </button>
                  <span className="rounded border border-panel-border bg-surface-muted px-1.5 py-0.5 uppercase text-foreground">
                    {relation.type || 'related'}
                  </span>
                  <span className="rounded border border-panel-border bg-surface-muted px-1.5 py-0.5 uppercase text-muted-foreground">
                    {relation.source || 'unknown'}
                  </span>
                  {typeof relation.confidence === 'number' && (
                    <span className="text-muted-foreground">
                      {Math.round(relation.confidence * 100)}%
                    </span>
                  )}
                  {relation.notes && (
                    <span className="text-muted-foreground">{relation.notes}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs italic text-muted-foreground">
              No typed feature relations available.
            </p>
          )}
        </SectionCard>

        {/* Related Features chip cloud */}
        <SectionCard title="Related Features">
          {relatedFeatures.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {relatedFeatures.map((rel) => (
                <button
                  key={rel}
                  type="button"
                  onClick={() => navigateToFeature(rel)}
                  className="rounded border border-panel-border bg-surface-muted px-2 py-1 text-xs text-indigo-400 transition-colors hover:bg-indigo-500/10"
                >
                  {rel}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs italic text-muted-foreground">No related features.</p>
          )}
        </SectionCard>

        {/* Lineage Signals */}
        <SectionCard title="Lineage Signals">
          {lineageDocs.length > 0 ? (
            <div className="space-y-2">
              {lineageDocs.map((doc) => (
                <div
                  key={`lineage-${doc.id}`}
                  className="rounded border border-panel-border bg-surface-overlay p-2 text-xs"
                >
                  <div className="font-medium text-foreground">{doc.title}</div>
                  <dl className="mt-1 space-y-0.5">
                    <div className="flex gap-2">
                      <dt className="text-muted-foreground">Family</dt>
                      <dd className="font-mono text-panel-foreground">
                        {doc.lineageFamily || '-'}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-muted-foreground">Parent</dt>
                      <dd className="font-mono text-panel-foreground">
                        {doc.lineageParent || '-'}
                      </dd>
                    </div>
                    {(doc.lineageChildren || []).length > 0 && (
                      <div className="flex gap-2">
                        <dt className="text-muted-foreground">Children</dt>
                        <dd className="font-mono text-panel-foreground">
                          {(doc.lineageChildren || []).join(', ')}
                        </dd>
                      </div>
                    )}
                  </dl>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs italic text-muted-foreground">
              No lineage metadata detected.
            </p>
          )}
        </SectionCard>
      </div>
    </TabStateView>
  );
};

export default RelationsTab;
