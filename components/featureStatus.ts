export interface FeatureStatusStyle {
  label: string;
  color: string;
  dot: string;
  badge: string;
}

const FEATURE_STATUS_CONFIG: Record<string, FeatureStatusStyle> = {
  done: {
    label: 'Done',
    color: 'bg-success/10 text-success-foreground',
    dot: 'bg-success',
    badge: 'border-success-border bg-success/10 text-success-foreground hover:bg-success/20',
  },
  'in-progress': {
    label: 'In Progress',
    color: 'bg-info/10 text-info-foreground',
    dot: 'bg-info',
    badge: 'border-info-border bg-info/10 text-info-foreground hover:bg-info/20',
  },
  review: {
    label: 'Review',
    color: 'bg-warning/10 text-warning-foreground',
    dot: 'bg-warning',
    badge: 'border-warning-border bg-warning/10 text-warning-foreground hover:bg-warning/20',
  },
  backlog: {
    label: 'Backlog',
    color: 'bg-surface-muted text-muted-foreground',
    dot: 'bg-disabled-foreground',
    badge: 'border-panel-border bg-surface-overlay/80 text-muted-foreground hover:bg-hover/60 hover:text-panel-foreground',
  },
  deferred: {
    label: 'Deferred',
    color: 'bg-warning/10 text-warning-foreground',
    dot: 'bg-warning',
    badge: 'border-warning-border bg-warning/10 text-warning-foreground hover:bg-warning/20',
  },
};

export const FEATURE_STATUS_OPTIONS = ['backlog', 'in-progress', 'review', 'done', 'deferred'] as const;
export const COMPLETION_EQUIVALENT_STATUSES = new Set<string>(['done', 'deferred']);

export const getFeatureStatusStyle = (status: string): FeatureStatusStyle => {
  const normalized = (status || '').trim().toLowerCase();
  return FEATURE_STATUS_CONFIG[normalized] || FEATURE_STATUS_CONFIG.backlog;
};

export const isCompletionEquivalentStatus = (status: string): boolean =>
  COMPLETION_EQUIVALENT_STATUSES.has((status || '').trim().toLowerCase());
