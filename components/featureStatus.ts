export interface FeatureStatusStyle {
  label: string;
  color: string;
  dot: string;
  badge: string;
}

const FEATURE_STATUS_CONFIG: Record<string, FeatureStatusStyle> = {
  done: {
    label: 'Done',
    color: 'bg-emerald-500/10 text-emerald-500',
    dot: 'bg-emerald-500',
    badge: 'border-emerald-500/35 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20',
  },
  'in-progress': {
    label: 'In Progress',
    color: 'bg-indigo-500/10 text-indigo-500',
    dot: 'bg-indigo-500',
    badge: 'border-indigo-500/35 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20',
  },
  review: {
    label: 'Review',
    color: 'bg-amber-500/10 text-amber-500',
    dot: 'bg-amber-500',
    badge: 'border-amber-500/35 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20',
  },
  backlog: {
    label: 'Backlog',
    color: 'bg-slate-500/10 text-slate-500',
    dot: 'bg-slate-500',
    badge: 'border-slate-600/80 bg-slate-800/70 text-slate-300 hover:bg-slate-800',
  },
  deferred: {
    label: 'Deferred',
    color: 'bg-amber-500/10 text-amber-400',
    dot: 'bg-amber-400',
    badge: 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20',
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
