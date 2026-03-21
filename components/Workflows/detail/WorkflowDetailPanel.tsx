import React, { useMemo, useState } from 'react';
import { ArrowLeft, Clock3, ExternalLink, RefreshCcw } from 'lucide-react';

import {
  ExecutionArtifactReference,
  WorkflowRegistryAction,
  WorkflowRegistryDetail,
} from '../../../types';
import { ArtifactReferenceModal } from '../../execution/ArtifactReferenceModal';
import {
  buildIdentityReference,
  formatDateTime,
  formatInteger,
  openExternalUrl,
} from '../workflowRegistryUtils';
import { ActionsRow } from './ActionsRow';
import { CompositionSection } from './CompositionSection';
import { DetailIdentityHeader } from './DetailIdentityHeader';
import { EffectivenessSection } from './EffectivenessSection';
import { IssuesSection } from './IssuesSection';

interface WorkflowDetailPanelProps {
  detail: WorkflowRegistryDetail | null;
  loading: boolean;
  error: string;
  showBackButton: boolean;
  onBack: () => void;
  onRetry: () => void;
  onOpenAction: (action: WorkflowRegistryAction) => void;
}

const LoadingState: React.FC = () => (
  <div className="space-y-4 animate-pulse">
    <div className="h-64 rounded-[28px] border border-panel-border bg-surface-overlay/70" />
    <div className="h-52 rounded-[28px] border border-panel-border bg-surface-overlay/70" />
    <div className="h-52 rounded-[28px] border border-panel-border bg-surface-overlay/70" />
  </div>
);

const EmptyState: React.FC = () => (
  <div className="flex min-h-[28rem] items-center justify-center rounded-[28px] border border-dashed border-panel-border bg-surface-overlay/60 px-6 py-10 text-center">
    <div className="max-w-md">
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Detail</div>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight text-panel-foreground">Select a workflow</h3>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        Choose a catalog entry to inspect identity, composition, effectiveness, and unresolved workflow-correlation gaps.
      </p>
    </div>
  </div>
);

const ReferenceMetrics = (reference: ExecutionArtifactReference): Array<{ label: string; value: string }> => [
  { label: 'Kind', value: reference.kind || 'artifact' },
  { label: 'Status', value: reference.status || 'unknown' },
  { label: 'External ID', value: reference.externalId || 'n/a' },
];

export const WorkflowDetailPanel: React.FC<WorkflowDetailPanelProps> = ({
  detail,
  loading,
  error,
  showBackButton,
  onBack,
  onRetry,
  onOpenAction,
}) => {
  const [activeReference, setActiveReference] = useState<ExecutionArtifactReference | null>(null);

  const workflowReference = useMemo(
    () => (detail ? buildIdentityReference(detail.identity, 'workflow') : null),
    [detail],
  );
  const commandReference = useMemo(
    () => (detail ? buildIdentityReference(detail.identity, 'command') : null),
    [detail],
  );

  if (loading) return <LoadingState />;

  if (error) {
    return (
      <div className="rounded-[28px] border border-rose-500/30 bg-rose-500/10 px-5 py-5 text-sm text-rose-100">
        <div className="font-semibold">Workflow detail unavailable</div>
        <p className="mt-2 text-rose-100/80">{error}</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-2 rounded-full border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-50"
        >
          <RefreshCcw size={12} />
          Retry
        </button>
      </div>
    );
  }

  if (!detail) return <EmptyState />;

  return (
    <div className="space-y-4">
      {showBackButton && (
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded-full border border-panel-border bg-surface-overlay/80 px-3 py-1.5 text-xs font-semibold text-panel-foreground transition-colors hover:border-hover"
        >
          <ArrowLeft size={12} />
          Back to catalog
        </button>
      )}

      <DetailIdentityHeader
        detail={detail}
        workflowReference={workflowReference}
        commandReference={commandReference}
        onOpenReference={setActiveReference}
      />

      <ActionsRow actions={detail.actions} onOpenAction={onOpenAction} />

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <CompositionSection composition={detail.composition} />
        <EffectivenessSection effectiveness={detail.effectiveness} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <IssuesSection issues={detail.issues} />

        <section className="rounded-[28px] border border-panel-border bg-surface-overlay/70 px-5 py-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Evidence</div>
          <h3 className="mt-2 text-xl font-semibold tracking-tight text-panel-foreground">Sessions and executions</h3>

          <div className="mt-4 space-y-4">
            <div className="rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Representative Sessions</div>
              <div className="mt-3 space-y-3">
                {detail.representativeSessions.length > 0 ? (
                  detail.representativeSessions.map(session => (
                    <button
                      key={session.sessionId}
                      type="button"
                      onClick={() =>
                        onOpenAction({
                          id: `open-session-${session.sessionId}`,
                          label: 'Open representative session',
                          target: 'internal',
                          href: session.href,
                          disabled: false,
                          reason: '',
                          metadata: { sessionId: session.sessionId },
                        })
                      }
                      className="w-full rounded-2xl border border-panel-border bg-surface-overlay/90 px-4 py-3 text-left transition-colors hover:border-hover"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-panel-foreground [overflow-wrap:anywhere]">
                          {session.title || session.sessionId}
                        </div>
                        <span className="rounded-full border border-panel-border bg-panel px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-foreground">
                          {session.status || 'unknown'}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {session.workflowRef || 'No workflow ref'} • {formatDateTime(session.startedAt)}
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="text-sm text-muted-foreground">No representative sessions were attached.</div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Recent SkillMeat Executions</div>
              <div className="mt-3 space-y-3">
                {detail.recentExecutions.length > 0 ? (
                  detail.recentExecutions.map(execution => (
                    <button
                      key={execution.executionId || execution.startedAt}
                      type="button"
                      onClick={() => openExternalUrl(execution.sourceUrl)}
                      className="w-full rounded-2xl border border-panel-border bg-surface-overlay/90 px-4 py-3 text-left transition-colors hover:border-hover"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-panel-foreground">
                          {execution.executionId || 'Execution'}
                        </div>
                        <ExternalLink size={12} className="text-muted-foreground" />
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock3 size={12} />
                        {formatDateTime(execution.startedAt)}
                      </div>
                      <div className="mt-2 text-xs text-foreground">
                        {execution.status || 'unknown'} • {formatInteger(Object.keys(execution.parameters || {}).length)} parameter field(s)
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="text-sm text-muted-foreground">No recent workflow executions were cached.</div>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      {activeReference && (
        <ArtifactReferenceModal
          reference={activeReference}
          title="Workflow Reference"
          metrics={ReferenceMetrics(activeReference)}
          onClose={() => setActiveReference(null)}
        />
      )}
    </div>
  );
};
