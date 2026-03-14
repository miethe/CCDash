import {
  ExecutionArtifactReference,
  WorkflowRegistryAction,
  WorkflowRegistryCorrelationState,
  WorkflowRegistryEffectivenessSummary,
  WorkflowRegistryIdentity,
  WorkflowRegistryIssueSeverity,
} from '../../types';

export const WORKFLOW_FILTER_OPTIONS: Array<{
  value: WorkflowRegistryCorrelationState | 'all';
  label: string;
}> = [
  { value: 'all', label: 'All' },
  { value: 'strong', label: 'Resolved' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'weak', label: 'Weak' },
  { value: 'unresolved', label: 'Unresolved' },
];

export const formatPercent = (value: number): string =>
  `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;

export const formatInteger = (value: number): string =>
  Math.max(0, Number(value || 0)).toLocaleString();

export const formatDateTime = (value: string): string => {
  if (!value) return 'Unknown';
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return value;
  return new Date(parsed).toLocaleString();
};

export const correlationStateLabel = (state: WorkflowRegistryCorrelationState): string => {
  if (state === 'strong') return 'Resolved';
  if (state === 'hybrid') return 'Hybrid';
  if (state === 'weak') return 'Weak';
  return 'Unresolved';
};

export const correlationBadgeClass = (state: WorkflowRegistryCorrelationState): string => {
  if (state === 'strong') return 'border-emerald-500/35 bg-emerald-500/10 text-emerald-100';
  if (state === 'hybrid') return 'border-cyan-500/20 bg-cyan-500/10 text-cyan-100';
  if (state === 'weak') return 'border-sky-500/25 bg-sky-500/10 text-sky-100';
  return 'border-amber-500/35 bg-amber-500/10 text-amber-100';
};

export const issueToneClass = (severity: WorkflowRegistryIssueSeverity): string => {
  if (severity === 'error') return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
  if (severity === 'warning') return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
  return 'border-slate-700 bg-slate-900/70 text-slate-300';
};

export const scoreBarClass = (
  kind: 'success' | 'efficiency' | 'quality' | 'risk',
): string => {
  if (kind === 'success') return 'from-emerald-400 to-emerald-500';
  if (kind === 'efficiency') return 'from-sky-400 to-blue-500';
  if (kind === 'quality') return 'from-cyan-400 to-indigo-500';
  return 'from-amber-300 via-orange-400 to-rose-500';
};

export const scoreValueClass = (
  kind: 'success' | 'efficiency' | 'quality' | 'risk',
): string => {
  if (kind === 'success') return 'text-emerald-200';
  if (kind === 'efficiency') return 'text-sky-200';
  if (kind === 'quality') return 'text-cyan-200';
  return 'text-amber-200';
};

export const hasEffectivenessSummary = (
  effectiveness?: WorkflowRegistryEffectivenessSummary | null,
): effectiveness is WorkflowRegistryEffectivenessSummary =>
  Boolean(effectiveness && Number(effectiveness.sampleSize || 0) > 0);

export const openExternalUrl = (url: string) => {
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
};

export const runWorkflowRegistryAction = (
  action: WorkflowRegistryAction,
  handlers: {
    navigate: (href: string) => void;
    openExternal?: (href: string) => void;
  },
) => {
  if (action.disabled || !action.href) return;
  if (action.target === 'internal') {
    handlers.navigate(action.href);
    return;
  }
  (handlers.openExternal || openExternalUrl)(action.href);
};

export const buildIdentityReference = (
  identity: WorkflowRegistryIdentity,
  kind: 'workflow' | 'command',
): ExecutionArtifactReference | null => {
  if (kind === 'workflow' && identity.resolvedWorkflowId) {
    return {
      key: identity.resolvedWorkflowId,
      label: identity.resolvedWorkflowLabel || identity.displayLabel || identity.resolvedWorkflowId,
      kind: 'workflow',
      status: identity.correlationState === 'strong' || identity.correlationState === 'hybrid' ? 'resolved' : 'cached',
      definitionType: 'workflow',
      externalId: identity.resolvedWorkflowId,
      sourceUrl: identity.resolvedWorkflowSourceUrl,
      sourceAttribution: 'SkillMeat workflow cache',
      description: identity.observedWorkflowFamilyRef || identity.displayLabel,
      metadata: {
        observedWorkflowFamilyRef: identity.observedWorkflowFamilyRef,
        observedAliases: identity.observedAliases,
      },
    };
  }

  if (kind === 'command' && identity.resolvedCommandArtifactId) {
    return {
      key: identity.resolvedCommandArtifactId,
      label: identity.resolvedCommandArtifactLabel || identity.resolvedCommandArtifactId,
      kind: 'command',
      status: identity.correlationState === 'unresolved' ? 'cached' : 'resolved',
      definitionType: 'artifact',
      externalId: identity.resolvedCommandArtifactId,
      sourceUrl: identity.resolvedCommandArtifactSourceUrl,
      sourceAttribution: 'SkillMeat command artifact cache',
      description: identity.observedWorkflowFamilyRef || identity.displayLabel,
      metadata: {
        observedWorkflowFamilyRef: identity.observedWorkflowFamilyRef,
        observedAliases: identity.observedAliases,
      },
    };
  }

  return null;
};
