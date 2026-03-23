import React from 'react';
import { ArrowRight, Layers3, ListOrdered, MapPinned, Sparkles } from 'lucide-react';

import { FeatureFamilyPosition, FeatureFamilySummary } from '../types';
import { cn } from '../lib/utils';
import { Button } from './ui/button';
import { Surface } from './ui/surface';

type FamilySummaryCardProps = {
  familySummary?: FeatureFamilySummary | null;
  familyPosition?: FeatureFamilyPosition | null;
  onOpenFeature?: (featureId: string) => void;
  className?: string;
};

const InfoBlock: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg border border-panel-border bg-surface-overlay/60 px-3 py-2">
    <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
    <p className="mt-1 text-sm font-medium text-panel-foreground">{value}</p>
  </div>
);

export const FamilySummaryCard: React.FC<FamilySummaryCardProps> = ({
  familySummary,
  familyPosition,
  onOpenFeature,
  className,
}) => {
  const nextItem = familySummary?.nextRecommendedFamilyItem
    || familySummary?.items.find(item => item.featureId === familySummary.nextRecommendedFeatureId)
    || null;

  const positionLabel = familyPosition?.display
    || (familySummary ? `${familySummary.currentPosition} of ${familySummary.totalItems}` : 'Unknown');

  return (
    <Surface tone="panel" padding="md" className={cn('space-y-4', className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Family summary</p>
          <h3 className="mt-1 flex items-center gap-2 text-base font-semibold text-panel-foreground">
            <Layers3 size={16} className="shrink-0 text-info" />
            <span className="truncate">{familySummary?.featureFamily || 'Unassigned family'}</span>
          </h3>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-panel-border bg-surface-overlay/80 px-2 py-0.5 text-[11px] text-muted-foreground">
          <MapPinned size={12} className="shrink-0" />
          {positionLabel}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <InfoBlock label="Total items" value={String(familySummary?.totalItems ?? 0)} />
        <InfoBlock label="Sequenced" value={String(familySummary?.sequencedItems ?? 0)} />
        <InfoBlock label="Unsequenced" value={String(familySummary?.unsequencedItems ?? 0)} />
      </div>

      {familySummary && (
        <div className="grid gap-3 rounded-xl border border-panel-border bg-surface-overlay/60 p-3 md:grid-cols-2">
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Current feature</p>
            <p className="text-sm font-medium text-panel-foreground">{familySummary.currentFeatureName}</p>
            <p className="text-xs text-muted-foreground">{familySummary.currentFeatureId}</p>
          </div>

          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Next recommended item</p>
            {nextItem ? (
              <>
                <p className="text-sm font-medium text-panel-foreground">{nextItem.featureName}</p>
                <p className="text-xs text-muted-foreground">{nextItem.primaryDocPath || nextItem.primaryDocId || nextItem.featureId}</p>
                {onOpenFeature && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onOpenFeature(nextItem.featureId)}
                    className="mt-2 h-8"
                  >
                    <ArrowRight size={14} />
                    Open next item
                  </Button>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No next item has been recommended yet.</p>
            )}
          </div>
        </div>
      )}

      {familyPosition?.display && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-panel-border bg-panel px-2 py-0.5 text-[11px]">
            <ListOrdered size={12} className="shrink-0" />
            {familyPosition.display}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-panel-border bg-panel px-2 py-0.5 text-[11px]">
            <Sparkles size={12} className="shrink-0" />
            {familyPosition.sequencedItems} sequenced, {familyPosition.unsequencedItems} unsequenced
          </span>
        </div>
      )}
    </Surface>
  );
};

