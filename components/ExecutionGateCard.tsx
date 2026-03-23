import React from 'react';
import { AlertTriangle, ArrowRight, CheckCircle2, CircleHelp, ShieldAlert, Sparkles, Target } from 'lucide-react';

import { ExecutionGateState } from '../types';
import { cn } from '../lib/utils';
import { BlockingFeatureList } from './BlockingFeatureList';
import { DependencyStateBadge } from './DependencyStateBadge';
import { FamilySummaryCard } from './FamilySummaryCard';
import { Button } from './ui/button';
import { Surface } from './ui/surface';

type ExecutionGateCardProps = {
  executionGate?: ExecutionGateState | null;
  onOpenFeature?: (featureId: string) => void;
  onOpenDocument?: (documentId: string) => void;
  className?: string;
};

type GateMeta = {
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
};

const GATE_META: Record<ExecutionGateState['state'], GateMeta> = {
  ready: {
    label: 'Ready to execute',
    description: 'Dependency and family ordering are clear.',
    icon: CheckCircle2,
    tone: 'success',
  },
  blocked_dependency: {
    label: 'Blocked by dependency',
    description: 'A dependency must clear before execution can proceed.',
    icon: AlertTriangle,
    tone: 'danger',
  },
  waiting_on_family_predecessor: {
    label: 'Waiting on family predecessor',
    description: 'The family sequence suggests another item should move first.',
    icon: Sparkles,
    tone: 'warning',
  },
  unknown_dependency_state: {
    label: 'Dependency state unknown',
    description: 'The execution surface needs clearer blocker evidence.',
    icon: ShieldAlert,
    tone: 'warning',
  },
};

const toneClassMap: Record<GateMeta['tone'], string> = {
  neutral: 'border-panel-border bg-surface-overlay/70 text-panel-foreground',
  success: 'border-success-border bg-success/10 text-success-foreground',
  warning: 'border-warning-border bg-warning/10 text-warning-foreground',
  danger: 'border-danger-border bg-danger/10 text-danger-foreground',
};

export const ExecutionGateCard: React.FC<ExecutionGateCardProps> = ({
  executionGate,
  onOpenFeature,
  onOpenDocument,
  className,
}) => {
  const state = executionGate?.state ?? 'unknown_dependency_state';
  const meta = GATE_META[state];
  const Icon = meta.icon;
  const dependencyState = executionGate?.dependencyState ?? null;
  const familySummary = executionGate?.familySummary ?? null;
  const familyPosition = executionGate?.familyPosition ?? null;
  const recommendedItem = familySummary?.items.find(item => item.featureId === executionGate?.recommendedFamilyItemId)
    || familySummary?.items.find(item => item.featureId === executionGate?.firstExecutableFamilyItemId)
    || familySummary?.nextRecommendedFamilyItem
    || null;
  const canOpenRecommended = Boolean(onOpenFeature && recommendedItem?.featureId);
  const blockingFeatureId = executionGate?.blockingDependencyId || dependencyState?.firstBlockingDependencyId || '';
  const blockingDocumentId = dependencyState?.blockingDocumentIds?.[0] || '';

  return (
    <Surface tone="panel" padding="md" className={cn('space-y-4', className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Execution gate</p>
          <h3 className="mt-1 flex items-center gap-2 text-base font-semibold text-panel-foreground">
            <Icon size={16} className="shrink-0" />
            <span>{meta.label}</span>
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{meta.description}</p>
        </div>
        <DependencyStateBadge dependencyState={dependencyState} />
      </div>

      <div className={cn('rounded-xl border px-3 py-2 text-sm', toneClassMap[meta.tone])}>
        {executionGate?.reason || meta.description}
      </div>

      <div className="flex flex-wrap gap-2">
        {canOpenRecommended && (
          <Button
            type="button"
            variant="default"
            size="sm"
            onClick={() => onOpenFeature(recommendedItem!.featureId)}
          >
            <Target size={14} />
            Open recommended item
          </Button>
        )}
        {blockingFeatureId && onOpenFeature && state !== 'ready' && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onOpenFeature(blockingFeatureId)}
            className="h-8"
          >
            <ArrowRight size={14} />
            Open blocker
          </Button>
        )}
        {blockingDocumentId && onOpenDocument && (
          <Button
            type="button"
            variant="chip"
            size="sm"
            onClick={() => onOpenDocument(blockingDocumentId)}
            className="h-8"
          >
            <CircleHelp size={14} />
            Open evidence
          </Button>
        )}
      </div>

      {familySummary && (
        <FamilySummaryCard
          familySummary={familySummary}
          familyPosition={familyPosition}
          onOpenFeature={onOpenFeature}
          className="shadow-none"
        />
      )}

      {(state === 'blocked_dependency' || state === 'unknown_dependency_state') && (
        <BlockingFeatureList
          dependencyState={dependencyState}
          onOpenFeature={onOpenFeature}
          onOpenDocument={onOpenDocument}
          className="shadow-none"
          title="Blocking dependencies"
        />
      )}
    </Surface>
  );
};

