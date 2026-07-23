/**
 * T4-001: FeatureAARReviewPanel — read-only AAR-review triage surface.
 *
 * Lists the persisted `aar_reviews` rollup for a project: one row per
 * deterministic AAR-document-to-session triage verdict, with its
 * correlation summary and flag evidence (PRD §7.2,
 * `ccdash-automated-aar-review-v1`).
 *
 * DATA SOURCE: `useAarReviewRollupQuery` (services/queries/aarReview.ts),
 * which fetches `GET /api/v1/project/aar-review?project_id=<projectId>` — see that
 * hook's module docstring for the full data-source rationale (no internal
 * `/api/agent/...` route lists the project-wide rollup today; the existing
 * internal route resolves exactly one AAR document).
 *
 * Read-only: no mutations, no write actions. Every optional §7.2 field is
 * rendered with a defined fallback (never a crash, never an omitted row) —
 * see the Known Gotchas in `.claude/progress/ccdash-automated-aar-review/phase-4-progress.md`:
 *   - `flags[].evidenceRefs` empty / `severity` null → "not triggered / not evaluated"
 *   - `correlation.featureId` null → session-only context, never a broken link
 *   - `correlation.confidence` null → "correlation pending"
 *   - `correlation.sessionIds` empty → "no linked sessions"
 */

import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, ShieldAlert, UserCheck } from 'lucide-react';

import type { AarReviewEntry, AarReviewFlag, AarReviewTriageVerdict } from '../../types';
import { useAarReviewRollupQuery } from '../../services/queries/aarReview';
import { Chip, Dot, MetricTile, Panel, SectionHeader } from './primitives';

// ── Verdict presentation (3 distinct visual treatments, tokens only) ────────

interface VerdictMeta {
  label: string;
  color: string;
  icon: ReactNode;
  description: string;
}

const VERDICT_META: Record<AarReviewTriageVerdict, VerdictMeta> = {
  surface_only: {
    label: 'Surface only',
    color: 'var(--ok)',
    icon: <CheckCircle2 size={13} aria-hidden="true" />,
    description: 'No flags triggered — no further action needed.',
  },
  deep_review_recommended: {
    label: 'Deep review recommended',
    color: 'var(--warn)',
    icon: <AlertTriangle size={13} aria-hidden="true" />,
    description: 'One or more flags triggered — worth a closer look.',
  },
  human_triage_required: {
    label: 'Human triage required',
    color: 'var(--err)',
    icon: <UserCheck size={13} aria-hidden="true" />,
    description: 'Correlation confidence missing/low, or an ambiguous match — needs a human.',
  },
};

const UNKNOWN_VERDICT_META: VerdictMeta = {
  label: 'Verdict pending',
  color: 'var(--ink-3)',
  icon: <ShieldAlert size={13} aria-hidden="true" />,
  description: 'No triage verdict has been computed for this row yet.',
};

function verdictMeta(verdict: AarReviewTriageVerdict | null): VerdictMeta {
  if (verdict == null) return UNKNOWN_VERDICT_META;
  return VERDICT_META[verdict] ?? UNKNOWN_VERDICT_META;
}

function VerdictBadge({ verdict }: { verdict: AarReviewTriageVerdict | null }) {
  const meta = verdictMeta(verdict);
  return (
    <span
      data-testid="aar-verdict-badge"
      data-verdict={verdict ?? 'unknown'}
      className="planning-mono planning-caps inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] border"
      style={{
        fontSize: 10.5,
        letterSpacing: '0.06em',
        padding: '3px 8px',
        color: meta.color,
        background: `color-mix(in oklab, ${meta.color} 14%, transparent)`,
        borderColor: `color-mix(in oklab, ${meta.color} 30%, transparent)`,
      }}
      title={meta.description}
    >
      {meta.icon}
      {meta.label}
    </span>
  );
}

// ── Correlation summary ──────────────────────────────────────────────────────

function formatConfidence(confidence: number | null): string {
  if (confidence == null) return 'correlation pending';
  return `${(confidence * 100).toFixed(0)}% confidence`;
}

function CorrelationSummary({ entry }: { entry: AarReviewEntry }) {
  const { correlation } = entry;
  const sessionCount = correlation.sessionIds.length;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px]" style={{ color: 'var(--ink-2)' }}>
      <span className="planning-mono" title={correlation.strategy ?? undefined}>
        {correlation.strategy ?? 'strategy unresolved'}
      </span>
      <span aria-hidden="true">·</span>
      <span
        className="planning-tnum"
        style={{ color: correlation.confidence == null ? 'var(--warn)' : 'var(--ink-2)' }}
      >
        {formatConfidence(correlation.confidence)}
      </span>
      <span aria-hidden="true">·</span>
      <span data-testid="aar-session-count">
        {sessionCount === 0
          ? 'no linked sessions'
          : `${sessionCount} linked session${sessionCount === 1 ? '' : 's'}`}
      </span>
      <span aria-hidden="true">·</span>
      <span>{correlation.featureId ? `feature ${correlation.featureId}` : 'no linked feature'}</span>
    </div>
  );
}

// ── Flag row ──────────────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<'low' | 'medium' | 'high', string> = {
  low: 'var(--ink-3)',
  medium: 'var(--warn)',
  high: 'var(--err)',
};

function FlagRow({ flag }: { flag: AarReviewFlag }) {
  const severityColor = flag.severity != null ? SEVERITY_COLOR[flag.severity] : 'var(--ink-4)';
  const severityLabel = flag.severity ?? 'not evaluated';

  return (
    <div
      data-testid={`aar-flag-${flag.flagId || 'unknown'}`}
      data-triggered={flag.triggered}
      className="flex flex-col gap-1 rounded-[var(--radius-sm)] px-2.5 py-2"
      style={{
        background: flag.triggered ? 'color-mix(in oklab, var(--warn) 8%, transparent)' : 'var(--bg-2)',
        border: `1px solid ${flag.triggered ? 'color-mix(in oklab, var(--warn) 30%, transparent)' : 'var(--line-1)'}`,
      }}
    >
      <div className="flex items-center gap-2">
        <Dot tone={flag.triggered ? severityColor : 'var(--ink-4)'} />
        <span className="planning-mono text-[11px]" style={{ color: 'var(--ink-0)' }}>
          {flag.flagId || 'unknown_flag'}
        </span>
        <span
          className="planning-caps planning-mono ml-auto text-[9.5px]"
          style={{ color: severityColor, letterSpacing: '0.08em' }}
        >
          {flag.triggered ? severityLabel : 'not triggered'}
        </span>
      </div>
      <p className="text-[11px]" style={{ color: 'var(--ink-2)' }}>
        {flag.rationale || 'no rationale recorded'}
      </p>
      {flag.evidenceRefs.length > 0 ? (
        <ul className="flex flex-col gap-0.5 pl-0.5" role="list" aria-label={`${flag.flagId} evidence`}>
          {flag.evidenceRefs.map((ref, index) => (
            <li
              key={`${flag.flagId}-evidence-${index}`}
              className="planning-mono truncate text-[10.5px]"
              style={{ color: 'var(--ink-3)' }}
              title={ref}
            >
              {ref}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[10.5px] italic" style={{ color: 'var(--ink-3)' }}>
          no evidence recorded
        </p>
      )}
    </div>
  );
}

// ── AAR review row (one persisted rollup entry) ──────────────────────────────

function AarReviewRow({ entry }: { entry: AarReviewEntry }) {
  const meta = verdictMeta(entry.triageVerdict);
  const triggeredFlags = entry.flags.filter((flag) => flag.triggered);
  const otherFlags = entry.flags.filter((flag) => !flag.triggered);

  return (
    <div
      data-testid={`aar-review-row-${entry.documentId || 'unknown'}`}
      className="flex flex-col gap-2.5 border-b px-4 py-3.5"
      style={{ borderColor: 'var(--line-1)', borderLeft: `3px solid ${meta.color}` }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="planning-mono truncate text-[12px] font-medium"
            style={{ color: 'var(--ink-0)' }}
            title={entry.documentId}
          >
            {entry.documentId || 'unknown document'}
          </span>
        </div>
        <VerdictBadge verdict={entry.triageVerdict} />
      </div>

      <CorrelationSummary entry={entry} />

      {entry.reasons.length > 0 ? (
        <ul className="flex flex-col gap-0.5" role="list" aria-label="Triage reasons">
          {entry.reasons.map((reason, index) => (
            <li key={`reason-${index}`} className="text-[11px]" style={{ color: 'var(--ink-2)' }}>
              — {reason}
            </li>
          ))}
        </ul>
      ) : null}

      {entry.flags.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {[...triggeredFlags, ...otherFlags].map((flag, index) => (
            <FlagRow key={`${entry.documentId}-${flag.flagId || 'flag'}-${index}`} flag={flag} />
          ))}
        </div>
      ) : (
        <p className="text-[11px] italic" style={{ color: 'var(--ink-3)' }}>
          no flags evaluated
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px]" style={{ color: 'var(--ink-3)' }}>
        <span>{entry.generatedAt ? `generated ${entry.generatedAt}` : 'generated at unknown'}</span>
        {entry.sourceRefs.length > 0 ? (
          <span className="flex flex-wrap items-center gap-1">
            {entry.sourceRefs.map((ref, index) => (
              <Chip key={`${entry.documentId}-src-${index}`} className="planning-mono px-1.5 py-0.5 text-[9.5px]">
                {ref}
              </Chip>
            ))}
          </span>
        ) : (
          <span>no source refs</span>
        )}
      </div>
    </div>
  );
}

// ── Summary strip (verdict counts) ──────────────────────────────────────────

function VerdictSummaryStrip({ entries }: { entries: AarReviewEntry[] }) {
  const counts: Record<AarReviewTriageVerdict, number> = {
    surface_only: 0,
    deep_review_recommended: 0,
    human_triage_required: 0,
  };
  for (const entry of entries) {
    if (entry.triageVerdict != null && entry.triageVerdict in counts) {
      counts[entry.triageVerdict] += 1;
    }
  }

  return (
    <div className="grid grid-cols-3 gap-3">
      <MetricTile
        label={VERDICT_META.surface_only.label}
        value={counts.surface_only}
        accent={counts.surface_only === 0 ? 'var(--ink-3)' : 'var(--ok)'}
      />
      <MetricTile
        label={VERDICT_META.deep_review_recommended.label}
        value={counts.deep_review_recommended}
        accent={counts.deep_review_recommended === 0 ? 'var(--ink-3)' : 'var(--warn)'}
      />
      <MetricTile
        label={VERDICT_META.human_triage_required.label}
        value={counts.human_triage_required}
        accent={counts.human_triage_required === 0 ? 'var(--ink-3)' : 'var(--err)'}
      />
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export interface FeatureAARReviewPanelProps {
  projectId: string | null | undefined;
  /**
   * Optional feature scope. When present, only rollup entries whose
   * `correlation.featureId` matches are rendered (see
   * `useAarReviewRollupQuery`'s `select` filter); absent/null keeps the
   * original project-wide behavior. An empty filtered list falls through
   * to the same empty state as "no reviews yet" — never an error.
   */
  featureId?: string | null;
}

export function FeatureAARReviewPanel({ projectId, featureId }: FeatureAARReviewPanelProps) {
  const query = useAarReviewRollupQuery({ projectId, featureId, enabled: !!projectId });
  const allEntries = query.data ?? [];
  // Belt-and-suspenders: the hook already narrows via its `select` filter,
  // but this component-level filter is idempotent and keeps the panel
  // correct even when the hook is mocked out directly (see test suite).
  const entries = featureId
    ? allEntries.filter((entry) => entry.correlation.featureId === featureId)
    : allEntries;

  if (!projectId) {
    return (
      <Panel className="flex flex-col items-center gap-2 border-dashed px-10 py-10 text-center">
        <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
          No active project selected.
        </p>
      </Panel>
    );
  }

  if (query.isLoading) {
    return (
      <Panel className="flex items-center justify-center gap-2 py-16" role="status" aria-busy="true">
        <Loader2 size={16} className="animate-spin" aria-hidden="true" style={{ color: 'var(--brand)' }} />
        <span className="text-xs" style={{ color: 'var(--ink-2)' }}>
          Loading AAR reviews...
        </span>
      </Panel>
    );
  }

  if (query.isError) {
    return (
      <Panel className="flex flex-col items-center gap-2 py-16 text-center">
        <AlertTriangle size={22} aria-hidden="true" style={{ color: 'var(--err)' }} />
        <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
          {query.error instanceof Error ? query.error.message : 'Failed to load AAR reviews.'}
        </p>
      </Panel>
    );
  }

  return (
    <section className="flex flex-col gap-3" data-testid="feature-aar-review-panel">
      <SectionHeader eyebrow="Automated AAR Review" heading="Triage Verdicts" />
      <VerdictSummaryStrip entries={entries} />
      <Panel className="flex min-h-0 flex-col" style={{ padding: 0, overflow: 'hidden' }}>
        {entries.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm" style={{ color: 'var(--ink-3)' }} data-testid="aar-review-empty-state">
            No AAR reviews recorded for this project yet.
          </div>
        ) : (
          <div role="list" aria-label="AAR review rows">
            {entries.map((entry, index) => (
              <AarReviewRow key={`${entry.documentId}-${index}`} entry={entry} />
            ))}
          </div>
        )}
      </Panel>
    </section>
  );
}

export default FeatureAARReviewPanel;
