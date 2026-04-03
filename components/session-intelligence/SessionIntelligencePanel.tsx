import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowUpRight, BrainCircuit, MessageSquareText, Search, Sparkles } from 'lucide-react';

import { AnalyticsApiError, analyticsService } from '../../services/analytics';
import type { RuntimeStatus } from '../../services/runtimeProfile';
import type {
  SessionCodeChurnFact,
  SessionIntelligenceDetailResponse,
  SessionIntelligenceSessionRollup,
  SessionScopeDriftFact,
  SessionSemanticSearchResponse,
  SessionSentimentFact,
} from '../../types';
import {
  aggregateSessionIntelligence,
  describeIntelligenceAvailability,
  formatConcernLabel,
  formatConcernScore,
} from '../../lib/sessionIntelligence';

interface SessionIntelligencePanelProps {
  title?: string;
  description?: string;
  sessionId?: string;
  featureId?: string;
  rootSessionId?: string;
  runtimeStatus?: RuntimeStatus | null;
  onOpenSession?: (sessionId: string) => void;
  onJumpToTranscript?: () => void;
  className?: string;
}

const panelTone = (kind: 'available' | 'unsupported' | 'degraded'): string => {
  if (kind === 'available') return 'border-emerald-500/20 bg-emerald-500/5 text-emerald-100';
  if (kind === 'unsupported') return 'border-amber-500/20 bg-amber-500/10 text-amber-100';
  return 'border-rose-500/20 bg-rose-500/10 text-rose-100';
};

const formatPercent = (value: number): string => `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;

const buildErrorMessage = (error: unknown): string => {
  if (error instanceof AnalyticsApiError) {
    if (error.status === 404) return error.message;
    return `${error.message}${error.hint ? ` ${error.hint}` : ''}`.trim();
  }
  return error instanceof Error ? error.message : 'Failed to load transcript intelligence';
};

const summarizeEvidence = (evidence: Record<string, unknown> | null | undefined): Array<{ label: string; value: string }> =>
  Object.entries(evidence || {})
    .slice(0, 3)
    .map(([key, value]) => ({
      label: key.replace(/_/g, ' '),
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }));

const summaryCardClass = 'rounded-2xl border border-panel-border bg-surface-overlay/80 px-4 py-4';

const ConcernCard: React.FC<{
  label: string;
  valueLabel: string;
  score: number;
  confidence: number;
  factCount: number;
  flaggedSessions: number;
}> = ({ label, valueLabel, score, confidence, factCount, flaggedSessions }) => (
  <div className={summaryCardClass}>
    <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
    <div className="mt-2 flex items-end justify-between gap-3">
      <div>
        <div className="text-xl font-semibold text-panel-foreground">{formatConcernLabel(valueLabel)}</div>
        <div className="mt-1 text-xs text-muted-foreground">score {formatConcernScore(score)}</div>
      </div>
      <div className="text-right text-xs text-muted-foreground">
        <div>{formatPercent(confidence)} confidence</div>
        <div>{factCount} fact(s)</div>
        <div>{flaggedSessions} flagged</div>
      </div>
    </div>
  </div>
);

const SearchResults: React.FC<{
  payload: SessionSemanticSearchResponse | null;
  loading: boolean;
  error: string;
  onOpenSession?: (sessionId: string) => void;
}> = ({ payload, loading, error, onOpenSession }) => {
  if (loading) {
    return <div className="rounded-xl border border-panel-border bg-surface-overlay/70 px-4 py-4 text-sm text-muted-foreground">Searching transcript intelligence…</div>;
  }
  if (error) {
    return <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-4 text-sm text-rose-100">{error}</div>;
  }
  if (!payload) return null;
  if (payload.items.length === 0) {
    return <div className="rounded-xl border border-panel-border bg-surface-overlay/70 px-4 py-4 text-sm text-muted-foreground">No transcript hits matched the current query.</div>;
  }
  return (
    <div className="space-y-3">
      {payload.items.map(item => (
        <div key={`${item.sessionId}-${item.blockKind}-${item.blockIndex}`} className="rounded-xl border border-panel-border bg-surface-overlay/75 px-4 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-panel-foreground">{item.snippet || item.content}</div>
              <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                {item.blockKind} block • score {item.score.toFixed(2)}
              </div>
            </div>
            {onOpenSession && (
              <button
                type="button"
                onClick={() => onOpenSession(item.sessionId)}
                className="inline-flex items-center gap-1 rounded-full border border-panel-border bg-panel px-3 py-1 text-[11px] font-semibold text-panel-foreground transition-colors hover:border-hover"
              >
                Open session
                <ArrowUpRight size={12} />
              </button>
            )}
          </div>
          {item.matchedTerms.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {item.matchedTerms.map(term => (
                <span key={`${item.sessionId}-${item.blockIndex}-${term}`} className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[11px] text-cyan-100">
                  {term}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const SentimentFacts: React.FC<{ items: SessionSentimentFact[]; onJumpToTranscript?: () => void }> = ({ items, onJumpToTranscript }) => {
  if (items.length === 0) {
    return <div className="rounded-xl border border-panel-border bg-surface-overlay/70 px-4 py-4 text-sm text-muted-foreground">No sentiment facts were materialized for this session yet.</div>;
  }
  return (
    <div className="space-y-3">
      {items.slice(0, 3).map(item => (
        <div key={`${item.sourceMessageId}-${item.messageIndex}`} className="rounded-xl border border-panel-border bg-surface-overlay/75 px-4 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-panel-foreground">{formatConcernLabel(item.sentimentLabel)}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                message #{item.messageIndex} • score {formatConcernScore(item.sentimentScore)} • {formatPercent(item.confidence)} confidence
              </div>
            </div>
            {onJumpToTranscript && (
              <button type="button" onClick={onJumpToTranscript} className="text-xs font-semibold text-indigo-200 hover:text-indigo-100">
                View transcript
              </button>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {summarizeEvidence(item.evidence).map(entry => (
              <span key={`${item.sourceMessageId}-${entry.label}`} className="rounded-full border border-panel-border bg-panel px-2.5 py-1 text-[11px] text-muted-foreground">
                {entry.label}: {entry.value}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

const ChurnFacts: React.FC<{ items: SessionCodeChurnFact[]; onJumpToTranscript?: () => void }> = ({ items, onJumpToTranscript }) => {
  if (items.length === 0) {
    return <div className="rounded-xl border border-panel-border bg-surface-overlay/70 px-4 py-4 text-sm text-muted-foreground">No churn loops were flagged for this session.</div>;
  }
  return (
    <div className="space-y-3">
      {items.slice(0, 3).map(item => (
        <div key={`${item.filePath}-${item.firstSourceLogId}`} className="rounded-xl border border-panel-border bg-surface-overlay/75 px-4 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-panel-foreground">{item.filePath}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                churn {formatConcernScore(item.churnScore)} • progress {formatConcernScore(item.progressScore)} • {item.touchCount} touches
              </div>
            </div>
            {onJumpToTranscript && (
              <button type="button" onClick={onJumpToTranscript} className="text-xs font-semibold text-indigo-200 hover:text-indigo-100">
                Review evidence
              </button>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <span className="rounded-full border border-panel-border bg-panel px-2.5 py-1">{item.additionsTotal} additions</span>
            <span className="rounded-full border border-panel-border bg-panel px-2.5 py-1">{item.deletionsTotal} deletions</span>
            <span className="rounded-full border border-panel-border bg-panel px-2.5 py-1">{item.rewritePassCount} rewrite pass(es)</span>
            {item.lowProgressLoop && <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-amber-100">Low progress loop</span>}
          </div>
        </div>
      ))}
    </div>
  );
};

const ScopeFacts: React.FC<{ items: SessionScopeDriftFact[]; onJumpToTranscript?: () => void }> = ({ items, onJumpToTranscript }) => {
  if (items.length === 0) {
    return <div className="rounded-xl border border-panel-border bg-surface-overlay/70 px-4 py-4 text-sm text-muted-foreground">No scope drift evidence was recorded for this session.</div>;
  }
  return (
    <div className="space-y-3">
      {items.slice(0, 3).map(item => (
        <div key={`${item.threadSessionId}-${item.outOfScopePathCount}-${item.actualPathCount}`} className="rounded-xl border border-panel-border bg-surface-overlay/75 px-4 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-panel-foreground">{item.outOfScopePathCount} out-of-scope path(s)</div>
              <div className="mt-1 text-xs text-muted-foreground">
                drift ratio {formatConcernScore(item.driftRatio)} • adherence {formatConcernScore(item.adherenceScore)}
              </div>
            </div>
            {onJumpToTranscript && (
              <button type="button" onClick={onJumpToTranscript} className="text-xs font-semibold text-indigo-200 hover:text-indigo-100">
                Inspect transcript
              </button>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <span className="rounded-full border border-panel-border bg-panel px-2.5 py-1">{item.matchedPathCount}/{item.plannedPathCount} planned paths matched</span>
            <span className="rounded-full border border-panel-border bg-panel px-2.5 py-1">{item.actualPathCount} actual paths</span>
            <span className="rounded-full border border-panel-border bg-panel px-2.5 py-1">{formatPercent(item.confidence)} confidence</span>
          </div>
        </div>
      ))}
    </div>
  );
};

export const SessionIntelligencePanel: React.FC<SessionIntelligencePanelProps> = ({
  title = 'Transcript Intelligence',
  description = 'Surface canonical transcript search, sentiment, churn, and scope-drift evidence in context.',
  sessionId,
  featureId,
  rootSessionId,
  runtimeStatus = null,
  onOpenSession,
  onJumpToTranscript,
  className = '',
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [rollups, setRollups] = useState<SessionIntelligenceSessionRollup[]>([]);
  const [detail, setDetail] = useState<SessionIntelligenceDetailResponse | null>(null);
  const [queryInput, setQueryInput] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [searchPayload, setSearchPayload] = useState<SessionSemanticSearchResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const rollupPromise = analyticsService.getSessionIntelligence({
          sessionId,
          featureId,
          rootSessionId,
          limit: sessionId ? 10 : 25,
        });
        const detailPromise = sessionId
          ? analyticsService.getSessionIntelligenceDetail(sessionId).catch(err => {
              if (err instanceof AnalyticsApiError && err.status === 404) return null;
              throw err;
            })
          : Promise.resolve(null);
        const [rollupPayload, detailPayload] = await Promise.all([rollupPromise, detailPromise]);
        if (cancelled) return;
        setRollups(rollupPayload.items || []);
        setDetail(detailPayload);
      } catch (err) {
        if (cancelled) return;
        setRollups([]);
        setDetail(null);
        setError(buildErrorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [featureId, rootSessionId, sessionId]);

  const aggregate = useMemo(() => aggregateSessionIntelligence(rollups), [rollups]);
  const resolvedCapability = useMemo(() => {
    if (searchPayload?.capability) return searchPayload.capability;
    if (!hasData) return null;
    const storageProfile = String(runtimeStatus?.storageProfile || 'unknown').trim().toLowerCase() || 'unknown';
    return {
      supported: true,
      authoritative: storageProfile === 'enterprise',
      storageProfile,
      searchMode: 'lexical',
      detail: storageProfile === 'enterprise'
        ? 'Canonical transcript intelligence is available for this workspace.'
        : 'Transcript intelligence is available in a non-authoritative fallback mode.',
    };
  }, [hasData, runtimeStatus?.storageProfile, searchPayload?.capability]);
  const availability = useMemo(
    () => describeIntelligenceAvailability(runtimeStatus, resolvedCapability),
    [runtimeStatus, resolvedCapability],
  );

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = queryInput.trim();
    if (!normalized) {
      setActiveQuery('');
      setSearchPayload(null);
      setSearchError('');
      return;
    }
    setSearchLoading(true);
    setSearchError('');
    setActiveQuery(normalized);
    try {
      const payload = await analyticsService.searchSessionIntelligence({
        query: normalized,
        sessionId,
        featureId,
        rootSessionId,
        limit: 6,
      });
      setSearchPayload(payload);
    } catch (err) {
      setSearchPayload(null);
      setSearchError(buildErrorMessage(err));
    } finally {
      setSearchLoading(false);
    }
  };

  const hasData = rollups.length > 0 || Boolean(detail);

  return (
    <section className={`rounded-[24px] border border-panel-border bg-panel/70 px-5 py-5 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <BrainCircuit size={14} />
            Intelligence
          </div>
          <h3 className="mt-2 text-xl font-semibold tracking-tight text-panel-foreground">{title}</h3>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{description}</p>
        </div>
        <div className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${panelTone(availability.kind)}`}>
          {availability.title}
        </div>
      </div>

      {(availability.kind !== 'available' || (!hasData && !loading)) && (
        <div className={`mt-4 rounded-2xl border px-4 py-4 text-sm ${panelTone(availability.kind)}`}>
          {availability.message}
        </div>
      )}

      {loading ? (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="h-28 animate-pulse rounded-2xl border border-panel-border bg-surface-overlay/60" />
          <div className="h-28 animate-pulse rounded-2xl border border-panel-border bg-surface-overlay/60" />
          <div className="h-28 animate-pulse rounded-2xl border border-panel-border bg-surface-overlay/60" />
        </div>
      ) : error && !hasData ? (
        <div className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-4 text-sm text-rose-100">
          {error}
        </div>
      ) : hasData ? (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <ConcernCard
              label="Sentiment"
              valueLabel={detail?.summary?.sentiment.label || aggregate.sentiment.label}
              score={detail?.summary?.sentiment.score ?? aggregate.sentiment.averageScore}
              confidence={detail?.summary?.sentiment.confidence ?? aggregate.sentiment.averageConfidence}
              factCount={detail?.summary?.sentiment.factCount ?? aggregate.sentiment.factCount}
              flaggedSessions={detail?.summary?.sentiment.flaggedCount ?? aggregate.sentiment.flaggedSessions}
            />
            <ConcernCard
              label="Code Churn"
              valueLabel={detail?.summary?.churn.label || aggregate.churn.label}
              score={detail?.summary?.churn.score ?? aggregate.churn.averageScore}
              confidence={detail?.summary?.churn.confidence ?? aggregate.churn.averageConfidence}
              factCount={detail?.summary?.churn.factCount ?? aggregate.churn.factCount}
              flaggedSessions={detail?.summary?.churn.flaggedCount ?? aggregate.churn.flaggedSessions}
            />
            <ConcernCard
              label="Scope Drift"
              valueLabel={detail?.summary?.scopeDrift.label || aggregate.scopeDrift.label}
              score={detail?.summary?.scopeDrift.score ?? aggregate.scopeDrift.averageScore}
              confidence={detail?.summary?.scopeDrift.confidence ?? aggregate.scopeDrift.averageConfidence}
              factCount={detail?.summary?.scopeDrift.factCount ?? aggregate.scopeDrift.factCount}
              flaggedSessions={detail?.summary?.scopeDrift.flaggedCount ?? aggregate.scopeDrift.flaggedSessions}
            />
          </div>

          {!sessionId && aggregate.representativeSessionIds.length > 0 && (
            <div className="mt-4 rounded-2xl border border-panel-border bg-surface-overlay/75 px-4 py-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-panel-foreground">
                <Sparkles size={14} />
                Representative sessions
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {aggregate.representativeSessionIds.map(id => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => onOpenSession?.(id)}
                    disabled={!onOpenSession}
                    className="rounded-full border border-panel-border bg-panel px-3 py-1 text-[11px] font-mono text-panel-foreground transition-colors hover:border-hover disabled:cursor-default disabled:text-muted-foreground"
                  >
                    {id}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}

      {sessionId && (
        <>
          <form onSubmit={handleSearch} className="mt-5 rounded-2xl border border-panel-border bg-surface-overlay/75 px-4 py-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-panel-foreground">
              <MessageSquareText size={14} />
              Transcript search
            </div>
            <div className="mt-3 flex flex-col gap-3 md:flex-row">
              <input
                type="search"
                value={queryInput}
                onChange={event => setQueryInput(event.target.value)}
                placeholder="Search canonical transcript evidence"
                className="flex-1 rounded-xl border border-panel-border bg-panel/80 px-3 py-2 text-sm text-panel-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-focus/50"
              />
              <button
                type="submit"
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-panel-border bg-panel px-4 py-2 text-sm font-semibold text-panel-foreground transition-colors hover:border-hover"
              >
                <Search size={14} />
                Search
              </button>
            </div>
            {activeQuery && <div className="mt-2 text-xs text-muted-foreground">Query: “{activeQuery}”</div>}
          </form>

          <div className="mt-4">
            <SearchResults payload={searchPayload} loading={searchLoading} error={searchError} onOpenSession={onOpenSession} />
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-panel-foreground">
                <AlertTriangle size={14} className="text-amber-300" />
                Sentiment evidence
              </div>
              <SentimentFacts items={detail?.sentimentFacts || []} onJumpToTranscript={onJumpToTranscript} />
            </div>
            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-panel-foreground">
                <AlertTriangle size={14} className="text-rose-300" />
                Churn evidence
              </div>
              <ChurnFacts items={detail?.churnFacts || []} onJumpToTranscript={onJumpToTranscript} />
            </div>
            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-panel-foreground">
                <AlertTriangle size={14} className="text-cyan-300" />
                Scope evidence
              </div>
              <ScopeFacts items={detail?.scopeDriftFacts || []} onJumpToTranscript={onJumpToTranscript} />
            </div>
          </div>
        </>
      )}
    </section>
  );
};
