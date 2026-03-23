import React from 'react';
import { ArrowRight, CheckCircle2, CircleDashed, CircleHelp, Clock3, Layers3, ListOrdered } from 'lucide-react';

import { FeatureFamilyItem, FeatureFamilyPosition, FeatureFamilySummary } from '../types';
import { cn } from '../lib/utils';
import { DependencyStateBadge } from './DependencyStateBadge';
import { Surface } from './ui/surface';

type FamilySequenceLaneProps = {
  familySummary?: FeatureFamilySummary | null;
  familyPosition?: FeatureFamilyPosition | null;
  onOpenFeature?: (featureId: string) => void;
  className?: string;
  ariaLabel?: string;
};

type FamilyItemDisplayState = {
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
};

const FINAL_STATUSES = new Set(['done', 'deferred', 'completed']);

const getFamilyItemState = (item: FeatureFamilyItem, nextRecommendedFeatureId: string | undefined): FamilyItemDisplayState => {
  if (item.isCurrent) {
      return {
        label: 'Current',
        description: 'This is the selected feature.',
        icon: Layers3,
        tone: 'info',
      };
  }
  if (item.featureId && nextRecommendedFeatureId && item.featureId === nextRecommendedFeatureId) {
      return {
        label: 'Next',
        description: 'This is the next recommended item in the family.',
        icon: ArrowRight,
        tone: 'info',
    };
  }
  if (item.isBlockedUnknown) {
    return {
      label: 'Blocked, evidence incomplete',
      description: 'This item is blocked but the evidence is incomplete.',
      icon: CircleHelp,
      tone: 'warning',
    };
  }
  if (item.isBlocked) {
    return {
      label: 'Blocked',
      description: 'A dependency is still blocking this item.',
      icon: Clock3,
      tone: 'danger',
    };
  }
  if (!item.isSequenced) {
    return {
      label: 'Unsequenced',
      description: 'This item is part of the family but has no explicit sequence order.',
      icon: CircleDashed,
      tone: 'neutral',
    };
  }
  if (FINAL_STATUSES.has((item.featureStatus || '').trim().toLowerCase())) {
    return {
      label: 'Done',
      description: 'This family item is complete.',
      icon: CheckCircle2,
      tone: 'success',
    };
  }
  return {
    label: item.isExecutable ? 'Ready' : 'Queued',
    description: item.isExecutable
      ? 'This item is executable.'
      : 'This item is sequenced but not yet the active target.',
    icon: item.isExecutable ? ArrowRight : ListOrdered,
    tone: item.isExecutable ? 'info' : 'neutral',
  };
};

export const FamilySequenceLane: React.FC<FamilySequenceLaneProps> = ({
  familySummary,
  familyPosition,
  onOpenFeature,
  className,
  ariaLabel = 'Family sequence lane',
}) => {
  const items = familySummary?.items || [];
  const nextRecommendedFeatureId = familySummary?.nextRecommendedFeatureId || '';

  return (
    <Surface tone="panel" padding="md" className={cn('space-y-3', className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{ariaLabel}</p>
          <p className="mt-1 text-sm text-panel-foreground">
            Ordered family items with current, next, blocked, and unsequenced states.
          </p>
        </div>
        {familySummary && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full border border-panel-border bg-surface-overlay/80 px-2 py-0.5 text-[11px] text-muted-foreground">
              {familySummary.totalItems} total
            </span>
            <span className="inline-flex items-center rounded-full border border-panel-border bg-surface-overlay/80 px-2 py-0.5 text-[11px] text-muted-foreground">
              {familySummary.sequencedItems} sequenced
            </span>
            <span className="inline-flex items-center rounded-full border border-panel-border bg-surface-overlay/80 px-2 py-0.5 text-[11px] text-muted-foreground">
              {familySummary.unsequencedItems} unsequenced
            </span>
          </div>
        )}
      </div>

      {familyPosition?.display && (
        <p className="text-xs text-muted-foreground">
          Current position: {familyPosition.display}
        </p>
      )}

      {items.length > 0 ? (
        <ol
          className="grid gap-3 overflow-x-auto pb-1 [grid-auto-flow:column] [grid-auto-columns:minmax(14rem,1fr)]"
          aria-label={ariaLabel}
        >
          {items.map(item => {
            const displayState = getFamilyItemState(item, nextRecommendedFeatureId);
            const Icon = displayState.icon;
            const handleClick = () => {
              if (onOpenFeature && item.featureId) {
                onOpenFeature(item.featureId);
              }
            };

            return (
              <li key={item.featureId} className="min-h-full">
                <button
                  type="button"
                  onClick={handleClick}
                  className={cn(
                    'flex h-full w-full flex-col rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/40',
                    item.isCurrent
                      ? 'border-info-border bg-info/10 shadow-sm'
                      : item.isBlockedUnknown
                        ? 'border-warning-border bg-warning/10'
                        : item.isBlocked
                          ? 'border-danger-border bg-danger/10'
                          : item.isBlockedUnknown || !item.isSequenced
                            ? 'border-panel-border bg-surface-overlay/70'
                            : 'border-panel-border bg-surface-overlay/60 hover:border-hover hover:bg-hover/40',
                  )}
                  aria-current={item.isCurrent ? 'step' : undefined}
                  aria-label={`${item.featureName || item.featureId}: ${displayState.label}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-panel-foreground">
                        {item.featureName || item.featureId}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {item.primaryDocPath || item.primaryDocId || 'No primary document attached'}
                      </p>
                    </div>
                    <span className="rounded-full border border-panel-border bg-panel px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {item.isSequenced && item.sequenceOrder !== null && item.sequenceOrder !== undefined
                        ? `#${item.sequenceOrder}`
                        : 'Unsequenced'}
                    </span>
                  </div>

                  <div className="mt-3 flex items-center gap-2">
                    <span className={cn(
                      'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                      displayState.tone === 'success' && 'border-success-border bg-success/10 text-success-foreground',
                      displayState.tone === 'warning' && 'border-warning-border bg-warning/10 text-warning-foreground',
                      displayState.tone === 'danger' && 'border-danger-border bg-danger/10 text-danger-foreground',
                      displayState.tone === 'info' && 'border-info-border bg-info/10 text-info-foreground',
                      displayState.tone === 'neutral' && 'border-panel-border bg-surface-overlay/80 text-muted-foreground',
                    )}>
                      <Icon size={12} className="shrink-0" />
                      {displayState.label}
                    </span>
                    {item.dependencyState && (
                      <DependencyStateBadge dependencyState={item.dependencyState} compact className="max-w-full" />
                    )}
                  </div>

                  <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">
                    {displayState.description}
                  </p>

                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                    <span className="rounded-full border border-panel-border bg-panel px-2 py-0.5">
                      {item.featureStatus || 'unknown'}
                    </span>
                    {item.isCurrent && (
                      <span className="rounded-full border border-info-border bg-info/10 px-2 py-0.5 text-info-foreground">
                        Current item
                      </span>
                    )}
                    {item.isExecutable && !item.isCurrent && (
                      <span className="rounded-full border border-success-border bg-success/10 px-2 py-0.5 text-success-foreground">
                        Executable
                      </span>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="rounded-lg border border-panel-border bg-surface-overlay/60 px-3 py-2 text-sm text-muted-foreground">
          No family items are available.
        </div>
      )}
    </Surface>
  );
};
