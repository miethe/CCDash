import React from 'react';
import { Link2, Radar, Sparkles, Terminal } from 'lucide-react';

import {
  ExecutionArtifactReference,
  WorkflowRegistryDetail,
} from '../../../types';
import {
  correlationBadgeClass,
  correlationStateLabel,
  formatDateTime,
  formatInteger,
} from '../workflowRegistryUtils';

interface DetailIdentityHeaderProps {
  detail: WorkflowRegistryDetail;
  workflowReference: ExecutionArtifactReference | null;
  commandReference: ExecutionArtifactReference | null;
  onOpenReference: (reference: ExecutionArtifactReference) => void;
}

const ReferenceButton: React.FC<{
  icon: React.ReactNode;
  label: string;
  subtitle: string;
  onClick: () => void;
}> = ({ icon, label, subtitle, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-3 text-left transition-colors hover:border-slate-600"
  >
    <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
      {icon}
      {subtitle}
    </div>
    <div className="mt-2 text-sm font-semibold text-slate-100 [overflow-wrap:anywhere]">{label}</div>
  </button>
);

export const DetailIdentityHeader: React.FC<DetailIdentityHeaderProps> = ({
  detail,
  workflowReference,
  commandReference,
  onOpenReference,
}) => (
  <section className="rounded-[28px] border border-slate-800/80 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.14),_rgba(15,23,42,0.97)_38%,_rgba(2,6,23,1)_100%)] px-5 py-5">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Identity</div>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-100 [overflow-wrap:anywhere]">
          {detail.identity.displayLabel || detail.identity.observedWorkflowFamilyRef || detail.id}
        </h2>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-400">
          <span
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[11px] font-semibold ${correlationBadgeClass(detail.correlationState)}`}
          >
            <Radar size={12} />
            {correlationStateLabel(detail.correlationState)}
          </span>
          <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2.5 py-1 text-xs text-slate-300">
            Sample size {formatInteger(detail.sampleSize)}
          </span>
          <span className="rounded-full border border-slate-800 bg-slate-950/70 px-2.5 py-1 text-xs text-slate-300">
            Last seen {formatDateTime(detail.lastObservedAt)}
          </span>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300">
          Observed family <span className="font-mono text-slate-200">{detail.identity.observedWorkflowFamilyRef || 'n/a'}</span>
          {' '}is being correlated against SkillMeat workflow definitions, command artifacts, and CCDash effectiveness evidence.
        </p>
      </div>
      <div className="grid min-w-[18rem] gap-3 md:grid-cols-2">
        {workflowReference && (
          <ReferenceButton
            icon={<Sparkles size={12} />}
            label={workflowReference.label}
            subtitle="Workflow Definition"
            onClick={() => onOpenReference(workflowReference)}
          />
        )}
        {commandReference && (
          <ReferenceButton
            icon={<Terminal size={12} />}
            label={commandReference.label}
            subtitle="Command Artifact"
            onClick={() => onOpenReference(commandReference)}
          />
        )}
      </div>
    </div>

    <div className="mt-5 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/55 px-4 py-4">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Observed Aliases</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {detail.identity.observedAliases.length > 0 ? (
            detail.identity.observedAliases.map(alias => (
              <span
                key={`${detail.id}-${alias}`}
                className="rounded-full border border-slate-800 bg-slate-900/80 px-2.5 py-1 text-xs text-slate-200"
              >
                {alias}
              </span>
            ))
          ) : (
            <span className="text-sm text-slate-500">No additional aliases cached.</span>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/55 px-4 py-4">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Representative Commands</div>
        <div className="mt-3 space-y-2">
          {detail.representativeCommands.length > 0 ? (
            detail.representativeCommands.map(command => (
              <div
                key={`${detail.id}-${command}`}
                className="rounded-xl border border-slate-800 bg-slate-950/80 px-3 py-2 font-mono text-xs text-slate-200 [overflow-wrap:anywhere]"
              >
                {command}
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-500">No command evidence attached.</div>
          )}
        </div>
      </div>
    </div>

    <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
      <Link2 size={12} />
      {detail.issueCount > 0
        ? `${formatInteger(detail.issueCount)} issue(s) are shaping current workflow confidence.`
        : 'No active workflow-quality issues were detected for this entity.'}
    </div>
  </section>
);
