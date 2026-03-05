import React from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Loader2,
  LucideIcon,
  MinusCircle,
  XCircle,
} from 'lucide-react';

import { TestStatus } from '../../types';

interface TestStatusBadgeProps {
  status: TestStatus;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

interface StatusConfig {
  icon: LucideIcon;
  colorClass: string;
  label: string;
  spin?: boolean;
}

const STATUS_CONFIG: Record<TestStatus, StatusConfig> = {
  passed: {
    icon: CheckCircle2,
    colorClass: 'border-emerald-500/45 bg-emerald-500/12 text-emerald-200',
    label: 'Passing',
  },
  failed: {
    icon: XCircle,
    colorClass: 'border-rose-500/45 bg-rose-500/12 text-rose-200',
    label: 'Failing',
  },
  skipped: {
    icon: MinusCircle,
    colorClass: 'border-amber-500/45 bg-amber-500/12 text-amber-200',
    label: 'Skipped',
  },
  error: {
    icon: AlertCircle,
    colorClass: 'border-rose-600/45 bg-rose-600/12 text-rose-300',
    label: 'Error',
  },
  xfailed: {
    icon: AlertTriangle,
    colorClass: 'border-amber-400/45 bg-amber-400/12 text-amber-200',
    label: 'XFail',
  },
  xpassed: {
    icon: AlertTriangle,
    colorClass: 'border-rose-400/45 bg-rose-400/12 text-rose-200',
    label: 'XPass',
  },
  unknown: {
    icon: HelpCircle,
    colorClass: 'border-slate-500/45 bg-slate-500/12 text-slate-300',
    label: 'Unknown',
  },
  running: {
    icon: Loader2,
    colorClass: 'border-indigo-400/45 bg-indigo-400/12 text-indigo-200',
    label: 'Running',
    spin: true,
  },
};

const SIZE_CONFIG = {
  sm: {
    wrapper: 'px-1 py-0.5 text-[10px]',
    icon: 12,
    gap: 'gap-0',
  },
  md: {
    wrapper: 'px-1.5 py-0.5 text-[10px]',
    icon: 16,
    gap: 'gap-1.5',
  },
  lg: {
    wrapper: 'px-2 py-1 text-xs',
    icon: 20,
    gap: 'gap-1.5',
  },
} as const;

export const TestStatusBadge: React.FC<TestStatusBadgeProps> = ({
  status,
  size = 'md',
  showLabel,
  className = '',
}) => {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.unknown;
  const sizeConfig = SIZE_CONFIG[size];
  const shouldShowLabel = size === 'sm' ? false : showLabel ?? true;
  const Icon = config.icon;

  return (
    <span
      role="status"
      aria-label={`Test status: ${config.label}`}
      aria-live={status === 'running' ? 'polite' : undefined}
      className={`inline-flex items-center rounded border font-semibold ${sizeConfig.wrapper} ${sizeConfig.gap} ${config.colorClass} ${className}`.trim()}
    >
      <Icon
        size={sizeConfig.icon}
        className={config.spin ? 'animate-spin motion-reduce:animate-none' : ''}
        aria-hidden="true"
      />
      {shouldShowLabel && <span>{config.label}</span>}
    </span>
  );
};

export type { TestStatusBadgeProps };
