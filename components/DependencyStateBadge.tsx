import React from 'react';
import { AlertTriangle, CircleHelp, CheckCircle2, ShieldAlert } from 'lucide-react';

import { FeatureDependencyState } from '../types';
import { cn } from '../lib/utils';
import { Badge } from './ui/badge';

type DependencyStateBadgeProps = {
  dependencyState?: FeatureDependencyState | null;
  className?: string;
  compact?: boolean;
};

type DependencyStateMeta = {
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
};

const STATE_META: Record<FeatureDependencyState['state'], DependencyStateMeta> = {
  unblocked: {
    label: 'Unblocked',
    description: 'No blocking dependencies remain.',
    icon: CheckCircle2,
    tone: 'success',
  },
  ready_after_dependencies: {
    label: 'Ready after dependencies',
    description: 'Dependencies are known and the work becomes executable when they clear.',
    icon: CheckCircle2,
    tone: 'success',
  },
  blocked: {
    label: 'Blocked',
    description: 'A dependency is still blocking execution.',
    icon: AlertTriangle,
    tone: 'danger',
  },
  blocked_unknown: {
    label: 'Blocked, evidence incomplete',
    description: 'The dependency state is blocked but the evidence is incomplete.',
    icon: ShieldAlert,
    tone: 'warning',
  },
};

const DEFAULT_META: DependencyStateMeta = {
  label: 'Dependency state unknown',
  description: 'No dependency state is available for this feature.',
  icon: CircleHelp,
  tone: 'neutral',
};

export const DependencyStateBadge: React.FC<DependencyStateBadgeProps> = ({
  dependencyState,
  className,
  compact = false,
}) => {
  const state = dependencyState?.state;
  const meta = state ? STATE_META[state] : DEFAULT_META;
  const Icon = meta.icon;
  const dependencyCount = dependencyState?.dependencyCount ?? 0;
  const unresolvedCount = (dependencyState?.blockedDependencyCount ?? 0) + (dependencyState?.unknownDependencyCount ?? 0);
  const summary = dependencyCount > 0
    ? `${dependencyCount} ${dependencyCount === 1 ? 'dependency' : 'dependencies'}${unresolvedCount > 0 ? `, ${unresolvedCount} unresolved` : ''}`
    : 'No dependencies recorded';

  return (
    <Badge
      tone={meta.tone}
      className={cn(
        'max-w-full whitespace-normal text-left',
        compact ? 'gap-1.5 px-2 py-1 text-[10px]' : 'gap-2 px-2.5 py-1.5 text-xs',
        className,
      )}
      title={`${meta.label}. ${meta.description}`}
    >
      <Icon size={12} className="shrink-0" aria-hidden="true" />
      <span className="font-medium">{meta.label}</span>
      {!compact && (
        <span className="text-[11px] font-normal text-current/80">
          {summary}
        </span>
      )}
    </Badge>
  );
};
