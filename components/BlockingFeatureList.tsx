import React from 'react';
import { ArrowRight, ExternalLink, FileText, Link2 } from 'lucide-react';

import { FeatureDependencyState } from '../types';
import { cn } from '../lib/utils';
import { Button } from './ui/button';
import { Surface } from './ui/surface';
import { DependencyStateBadge } from './DependencyStateBadge';

type BlockingFeatureListProps = {
  dependencyState?: FeatureDependencyState | null;
  onOpenFeature?: (featureId: string) => void;
  onOpenDocument?: (documentId: string) => void;
  className?: string;
  title?: string;
};

const resolveBlockerDependencies = (dependencyState?: FeatureDependencyState | null) => (
  dependencyState?.dependencies?.filter(dependency => dependency.state !== 'complete') || []
);

const statusLabel = (state: string): string => {
  if (state === 'blocked_unknown') return 'Blocked, evidence incomplete';
  if (state === 'blocked') return 'Blocked';
  return 'Resolved';
};

const chipClassByState = (state: string): string => {
  if (state === 'blocked_unknown') return 'border-warning-border bg-warning/10 text-warning-foreground';
  if (state === 'blocked') return 'border-danger-border bg-danger/10 text-danger-foreground';
  return 'border-panel-border bg-surface-muted text-muted-foreground';
};

export const BlockingFeatureList: React.FC<BlockingFeatureListProps> = ({
  dependencyState,
  onOpenFeature,
  onOpenDocument,
  className,
  title = 'Blocking evidence',
}) => {
  const blockers = resolveBlockerDependencies(dependencyState);
  const hasBlockers = blockers.length > 0;

  return (
    <Surface tone="panel" padding="md" className={cn('space-y-3', className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
          <p className="mt-1 text-sm text-panel-foreground">
            {hasBlockers
              ? 'The selected feature cannot move forward until these dependencies clear.'
              : 'No unresolved blockers are recorded for this feature.'}
          </p>
        </div>
        <DependencyStateBadge dependencyState={dependencyState} compact />
      </div>

      {dependencyState?.blockingReason && (
        <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2 text-sm text-panel-foreground">
          {dependencyState.blockingReason}
        </div>
      )}

      {hasBlockers ? (
        <ul className="space-y-3" aria-label="Blocking feature evidence">
          {blockers.map((dependency, index) => {
            const hasFeatureAction = Boolean(onOpenFeature && dependency.dependencyFeatureId);
            const firstDocumentId = dependency.blockingDocumentIds[0];
            const hasDocumentAction = Boolean(onOpenDocument && firstDocumentId);

            return (
              <li
                key={`${dependency.dependencyFeatureId || 'dependency'}-${index}`}
                className="rounded-xl border border-panel-border bg-surface-overlay/60 p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-medium text-panel-foreground">
                        {dependency.dependencyFeatureName || dependency.dependencyFeatureId || 'Unknown dependency'}
                      </p>
                      <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide', chipClassByState(dependency.state))}>
                        {statusLabel(dependency.state)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {dependency.blockingReason}
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-wrap gap-2">
                    {hasFeatureAction && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => onOpenFeature(dependency.dependencyFeatureId)}
                        className="h-8"
                      >
                        <ArrowRight size={14} />
                        Open feature
                      </Button>
                    )}
                    {hasDocumentAction && (
                      <Button
                        type="button"
                        variant="chip"
                        size="sm"
                        onClick={() => onOpenDocument(firstDocumentId)}
                        className="h-8"
                      >
                        <FileText size={14} />
                        Open evidence
                      </Button>
                    )}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {dependency.dependencyCompletionEvidence.length > 0 && dependency.dependencyCompletionEvidence.map(evidence => (
                    <span
                      key={evidence}
                      className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-panel px-2 py-0.5 text-[11px] text-muted-foreground"
                    >
                      <Link2 size={12} className="shrink-0" />
                      {evidence}
                    </span>
                  ))}
                  {dependency.blockingDocumentIds.map(documentId => (
                    <span
                      key={documentId}
                      className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-panel px-2 py-0.5 text-[11px] text-muted-foreground"
                    >
                      <FileText size={12} className="shrink-0" />
                      {documentId}
                    </span>
                  ))}
                  {!dependency.dependencyCompletionEvidence.length && !dependency.blockingDocumentIds.length && (
                    <span className="text-xs text-muted-foreground">No evidence tokens recorded.</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="flex items-center gap-2 rounded-lg border border-panel-border bg-surface-overlay/60 px-3 py-2 text-sm text-muted-foreground">
          <ExternalLink size={14} className="shrink-0" />
          The feature has no unresolved blocker records.
        </div>
      )}
    </Surface>
  );
};

