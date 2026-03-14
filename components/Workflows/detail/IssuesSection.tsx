import React from 'react';
import { AlertTriangle } from 'lucide-react';

import { WorkflowRegistryIssue } from '../../../types';
import { issueToneClass } from '../workflowRegistryUtils';

interface IssuesSectionProps {
  issues: WorkflowRegistryIssue[];
}

export const IssuesSection: React.FC<IssuesSectionProps> = ({ issues }) => (
  <section className="rounded-[28px] border border-slate-800/80 bg-slate-950/55 px-5 py-5">
    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Issues</div>
    <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-100">Correlation gaps and tuning friction</h3>

    {issues.length === 0 ? (
      <div className="mt-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-4 text-sm text-emerald-100">
        No workflow-quality issues are currently attached to this entity.
      </div>
    ) : (
      <div className="mt-4 grid gap-3">
        {issues.map(issue => (
          <article
            key={`${issue.code}-${issue.title}`}
            className={`rounded-xl border px-4 py-4 ${issueToneClass(issue.severity)}`}
          >
            <div className="flex items-start gap-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-sm font-semibold [overflow-wrap:anywhere]">{issue.title}</div>
                  <span className="rounded-full border border-current/15 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em]">
                    {issue.severity}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 [overflow-wrap:anywhere]">{issue.message}</p>
                {Object.keys(issue.metadata || {}).length > 0 && (
                  <div className="mt-3 rounded-xl border border-current/10 bg-black/10 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.16em] opacity-70">Metadata</div>
                    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs opacity-90">
                      {JSON.stringify(issue.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    )}
  </section>
);
