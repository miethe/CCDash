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
import { Badge } from '../ui/badge';

interface TestStatusBadgeProps {
  status: TestStatus;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

interface StatusConfig {
  icon: LucideIcon;
  tone: 'neutral' | 'muted' | 'info' | 'success' | 'warning' | 'danger';
  label: string;
  spin?: boolean;
}

const STATUS_CONFIG: Record<TestStatus, StatusConfig> = {
  passed: {
    icon: CheckCircle2,
    tone: 'success',
    label: 'Passing',
  },
  failed: {
    icon: XCircle,
    tone: 'danger',
    label: 'Failing',
  },
  skipped: {
    icon: MinusCircle,
    tone: 'warning',
    label: 'Skipped',
  },
  error: {
    icon: AlertCircle,
    tone: 'danger',
    label: 'Error',
  },
  xfailed: {
    icon: AlertTriangle,
    tone: 'warning',
    label: 'XFail',
  },
  xpassed: {
    icon: AlertTriangle,
    tone: 'danger',
    label: 'XPass',
  },
  unknown: {
    icon: HelpCircle,
    tone: 'muted',
    label: 'Unknown',
  },
  running: {
    icon: Loader2,
    tone: 'info',
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
    <Badge
      role="status"
      aria-label={`Test status: ${config.label}`}
      aria-live={status === 'running' ? 'polite' : undefined}
      size={size === 'lg' ? 'md' : 'sm'}
      tone={config.tone}
      mono={false}
      className={`font-semibold ${sizeConfig.wrapper} ${sizeConfig.gap} ${className}`.trim()}
    >
      <Icon
        size={sizeConfig.icon}
        className={config.spin ? 'animate-spin motion-reduce:animate-none' : ''}
        aria-hidden="true"
      />
      {shouldShowLabel && <span>{config.label}</span>}
    </Badge>
  );
};

export type { TestStatusBadgeProps };
