import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart2,
  Bot,
  Box,
  Cpu,
  Database,
  FileText,
  GitCommit,
  Link as LinkIcon,
  ShieldAlert,
  Wrench,
  X,
} from 'lucide-react';
import type { AgentSession } from '../types';
import { formatModelDisplayName } from '../lib/modelIdentity';
import { buildSessionAnalyticsSummary } from '../lib/sessionAnalytics';
import { resolveDisplayCost } from '../lib/sessionSemantics';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../lib/tokenMetrics';

type AnalyticsModalTab = 'tokens' | 'agents-models' | 'skills-artifacts' | 'files-tools' | 'attribution-provenance';
type SummaryRecord = Record<string, unknown>;
type CountRow = { label: string; count: number; detail?: string };

interface SessionAnalyticsModalProps {
  isOpen: boolean;
  session: AgentSession | null;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
}

const ANALYTICS_TABS: Array<{
  id: AnalyticsModalTab;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}> = [
  { id: 'tokens', label: 'Tokens', icon: BarChart2 },
  { id: 'agents-models', label: 'Agents / Models', icon: Bot },
  { id: 'skills-artifacts', label: 'Skills / Artifacts', icon: Box },
  { id: 'files-tools', label: 'Files / Tools', icon: Wrench },
  { id: 'attribution-provenance', label: 'Attribution / Provenance', icon: ShieldAlert },
];

const asRecord = (value: unknown): SummaryRecord => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as SummaryRecord : {}
);

const readPath = (source: SummaryRecord, path: string): unknown => {
  let current: unknown = source;
  for (const part of path.split('.')) {
    if (!current || typeof current !== 'object' || Array.isArray(current)) return undefined;
    current = (current as SummaryRecord)[part];
  }
  return current;
};

const readNumber = (source: SummaryRecord, paths: string[], fallback = 0): number => {
  for (const path of paths) {
    const value = readPath(source, path);
    const parsed = typeof value === 'number' ? value : Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
};

const uniqueStrings = (values: Array<string | null | undefined>): string[] => (
  Array.from(new Set(values.map(value => String(value || '').trim()).filter(Boolean)))
);

const countRows = (values: string[], limit = 8): CountRow[] => {
  const counts = new Map<string, number>();
  values.forEach(value => {
    const label = String(value || '').trim();
    if (!label) return;
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }));
};

const dimensionRows = (value: unknown, fallback: CountRow[], limit = 8): CountRow[] => {
  if (!Array.isArray(value) || value.length === 0) return fallback;
  const rows = value
    .map((item): CountRow | null => {
      const row = asRecord(item);
      const label = String(row.label || row.key || '').trim();
      if (!label) return null;
      const count = Number(row.count ?? row.logCount ?? row.sessionCount ?? 0);
      const metadata = asRecord(row.metadata);
      const details = uniqueStrings([
        typeof metadata.provider === 'string' ? metadata.provider : '',
        typeof metadata.family === 'string' ? metadata.family : '',
        typeof metadata.type === 'string' ? metadata.type : '',
        typeof metadata.source === 'string' ? metadata.source : '',
      ]);
      const detail = details.join(' / ');
      return {
        label,
        count: Number.isFinite(count) ? count : 0,
        ...(detail ? { detail } : {}),
      };
    })
    .filter((row): row is CountRow => row !== null);
  return rows.length > 0 ? rows.slice(0, limit) : fallback;
};

const formatNumber = (value: number | null | undefined): string => (
  Number.isFinite(Number(value)) ? Number(value).toLocaleString() : '0'
);

const formatUsd = (value: number | null | undefined, digits = 4): string => {
  const parsed = Number(value || 0);
  return `$${(Number.isFinite(parsed) ? parsed : 0).toFixed(digits)}`;
};

const durationLabel = (seconds: number | null | undefined): string => {
  const parsed = Math.max(0, Number(seconds || 0));
  if (parsed < 60) return `${Math.round(parsed)}s`;
  const minutes = parsed / 60;
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
};

const sourceLabel = (value: string | null | undefined): string => {
  const normalized = String(value || '').trim();
  return normalized || 'Not captured';
};

const MetricTile: React.FC<{ label: string; value: string; detail?: string; tone?: string }> = ({ label, value, detail, tone }) => (
  <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2">
    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
    <div className={`mt-1 font-mono text-sm ${tone || 'text-panel-foreground'}`}>{value}</div>
    {detail ? <div className="mt-0.5 text-[11px] text-muted-foreground truncate">{detail}</div> : null}
  </div>
);

const MiniTable: React.FC<{
  rows: CountRow[];
  emptyLabel: string;
  countLabel?: string;
}> = ({ rows, emptyLabel, countLabel = 'Count' }) => (
  <div className="overflow-hidden rounded-lg border border-panel-border">
    {rows.length === 0 ? (
      <div className="px-3 py-4 text-xs text-muted-foreground">{emptyLabel}</div>
    ) : (
      <table className="w-full text-xs">
        <thead className="bg-surface-overlay/90 text-[10px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Name</th>
            <th className="px-3 py-2 text-right font-medium">{countLabel}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={`${row.label}-${row.count}`} className="border-t border-panel-border text-panel-foreground">
              <td className="max-w-[22rem] truncate px-3 py-2" title={row.label}>
                <div className="truncate">{row.label}</div>
                {row.detail ? <div className="truncate text-[10px] text-muted-foreground">{row.detail}</div> : null}
              </td>
              <td className="px-3 py-2 text-right font-mono">{formatNumber(row.count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);

const KeyValueGrid: React.FC<{ rows: Array<{ label: string; value: string; title?: string }> }> = ({ rows }) => (
  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
    {rows.map(row => (
      <div key={row.label} className="min-w-0 rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{row.label}</div>
        <div className="mt-1 truncate font-mono text-xs text-panel-foreground" title={row.title || row.value}>{row.value}</div>
      </div>
    ))}
  </div>
);

export const SessionAnalyticsModal: React.FC<SessionAnalyticsModalProps> = ({
  isOpen,
  session,
  loading = false,
  error = null,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<AnalyticsModalTab>('tokens');

  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    setActiveTab('tokens');
  }, [session?.id]);

  const summary = useMemo(() => {
    if (!session) return {};
    try {
      return asRecord(buildSessionAnalyticsSummary([session]));
    } catch {
      return {};
    }
  }, [session]);

  const analytics = useMemo(() => {
    if (!session) return null;

    const logs = session.logs || [];
    const toolLogs = logs.filter(log => log.type === 'tool');
    const failedToolLogs = toolLogs.filter(log => log.toolCall?.status === 'error' || log.toolCall?.isError);
    const resolvedTokens = resolveTokenMetrics(session);
    const cacheInputTokens = Number(session.cacheInputTokens ?? (
      Number(session.cacheCreationInputTokens || 0) + Number(session.cacheReadInputTokens || 0)
    ));
    const toolResultTokens = Number(session.toolResultInputTokens || 0)
      + Number(session.toolResultOutputTokens || 0)
      + Number(session.toolResultCacheCreationInputTokens || 0)
      + Number(session.toolResultCacheReadInputTokens || 0);
    const totalTokens = readNumber(
      summary,
      ['totals.tokens.workloadTokens', 'tokens.total', 'tokens.totalTokens', 'tokenSummary.totalTokens', 'totalTokens', 'workloadTokens'],
      Number(session.observedTokens || resolvedTokens.workloadTokens || 0),
    );
    const modelIOTokens = readNumber(
      summary,
      ['totals.tokens.modelIOTokens', 'tokens.modelIO', 'tokens.modelIOTokens', 'tokenSummary.modelIOTokens', 'modelIOTokens'],
      Number(session.modelIOTokens || resolvedTokens.modelIOTokens || 0),
    );
    const displayCost = readNumber(
      summary,
      ['totals.costUsd', 'cost.totalUsd', 'cost.displayCostUsd', 'displayCostUsd', 'totalCostUsd'],
      resolveDisplayCost(session),
    );

    const fallbackAgentRows = countRows([
      ...(session.agentsUsed || []),
      ...logs.filter(log => log.speaker === 'agent').map(log => log.agentName || 'Main Session'),
    ]);
    const fallbackModelRows = uniqueStrings([
      ...(session.modelsUsed || []).map(model => formatModelDisplayName(model.raw, model.modelDisplayName)),
      formatModelDisplayName(session.model, session.modelDisplayName),
    ]).map(label => ({
      label,
      count: logs.length || 1,
      detail: session.modelProvider || session.modelFamily || '',
    }));
    const fallbackSkillRows = countRows([
      ...(session.skillsUsed || []),
      ...logs.map(log => log.skillDetails?.name || '').filter(Boolean),
      ...logs.filter(log => log.type === 'skill').map(log => log.skillDetails?.name || log.content || 'skill'),
    ]);
    const fallbackArtifactRows = countRows((session.linkedArtifacts || []).map(artifact => artifact.type || artifact.source || 'artifact'));
    const fallbackToolRows = countRows([
      ...(session.toolsUsed || []).flatMap(tool => Array(Math.max(1, Number(tool.count || 1))).fill(tool.name)),
      ...toolLogs.map(log => log.toolCall?.name || 'tool'),
    ]);
    const fallbackFileRows = countRows((session.updatedFiles || []).map(file => String(file.filePath || file.fileType || 'file')));
    const fileActionRows = countRows((session.updatedFiles || []).map(file => String(file.action || 'updated')));
    const fileTypeRows = countRows((session.updatedFiles || []).map(file => String(file.fileType || 'file')));
    const attributionRows = (session.usageAttributionSummary?.rows || [])
      .slice(0, 8)
      .map(row => ({
        label: row.entityLabel || row.entityId,
        count: Number(row.exclusiveTokens || 0),
        detail: `${row.entityType} - ${formatPercent(Number(row.averageConfidence || 0), 0)} confidence`,
      }));
    const commits = uniqueStrings([
      session.gitCommitHash,
      ...(session.gitCommitHashes || []),
    ]);

    return {
      totalTokens,
      modelIOTokens,
      cacheInputTokens,
      toolResultTokens,
      inputTokens: readNumber(summary, ['totals.tokens.tokenInput', 'tokens.input', 'tokens.inputTokens', 'tokensIn'], session.tokensIn || 0),
      outputTokens: readNumber(summary, ['totals.tokens.tokenOutput', 'tokens.output', 'tokens.outputTokens', 'tokensOut'], session.tokensOut || 0),
      displayCost,
      costPerLog: logs.length > 0 ? displayCost / logs.length : 0,
      contextPct: Number(session.contextUtilizationPct || 0),
      contextTokens: Number(session.currentContextTokens || 0),
      contextWindow: Number(session.contextWindowSize || 0),
      logs,
      toolLogs,
      failedToolLogs,
      agentRows: dimensionRows(summary.agents, fallbackAgentRows),
      modelRows: dimensionRows(summary.models, fallbackModelRows),
      skillRows: dimensionRows(summary.skills, fallbackSkillRows),
      artifactRows: dimensionRows(summary.artifacts, fallbackArtifactRows),
      toolRows: dimensionRows(summary.tools, fallbackToolRows),
      fileRows: dimensionRows(summary.files, fallbackFileRows),
      fileActionRows,
      fileTypeRows,
      attributionRows,
      commits,
    };
  }, [session, summary]);

  if (!isOpen) return null;

  const title = session?.title?.trim() || session?.id || 'Session analytics';

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-surface-overlay/90 p-3 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Session analytics"
        className="flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-panel-border bg-panel shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-panel-border bg-surface-overlay px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-bold text-panel-foreground">
              <Activity size={16} className="text-indigo-400" />
              <span className="truncate">{title}</span>
            </div>
            <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{session?.id || 'Loading session detail'}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-surface-muted hover:text-panel-foreground"
            aria-label="Close session analytics"
          >
            <X size={18} />
          </button>
        </div>

        {error ? (
          <div className="border-b border-amber-500/25 bg-amber-500/10 px-4 py-2 text-xs text-amber-100">{error}</div>
        ) : null}

        <div className="flex flex-wrap gap-1 border-b border-panel-border bg-panel/90 px-3 py-2">
          {ANALYTICS_TABS.map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-semibold transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-muted-foreground hover:bg-surface-muted hover:text-panel-foreground'
                }`}
              >
                <Icon size={13} />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="min-h-[28rem] overflow-y-auto p-4">
          {loading && !analytics ? (
            <div className="flex h-72 flex-col items-center justify-center gap-3 text-muted-foreground">
              <Activity size={22} className="animate-spin text-indigo-400" />
              <div className="text-sm">Loading full session detail...</div>
            </div>
          ) : !session || !analytics ? (
            <div className="flex h-72 items-center justify-center text-sm text-muted-foreground">
              No session analytics available.
            </div>
          ) : (
            <div className="space-y-4">
              {loading ? (
                <div className="inline-flex items-center gap-2 rounded-lg border border-indigo-500/25 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-100">
                  <Activity size={13} className="animate-spin" />
                  Refreshing full detail...
                </div>
              ) : null}

              {activeTab === 'tokens' ? (
                <>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <MetricTile label="Total workload" value={formatTokenCount(analytics.totalTokens)} tone="text-indigo-200" />
                    <MetricTile label="Model IO" value={formatTokenCount(analytics.modelIOTokens)} detail={`${formatTokenCount(analytics.inputTokens)} in / ${formatTokenCount(analytics.outputTokens)} out`} />
                    <MetricTile label="Cache input" value={formatTokenCount(analytics.cacheInputTokens)} detail={`${formatPercent(analytics.totalTokens > 0 ? analytics.cacheInputTokens / analytics.totalTokens : 0, 0)} of workload`} />
                    <MetricTile label="Display cost" value={formatUsd(analytics.displayCost)} detail={`${formatUsd(analytics.costPerLog)} / log`} tone="text-emerald-300" />
                    <MetricTile label="Tool-result tokens" value={formatTokenCount(analytics.toolResultTokens)} />
                    <MetricTile label="Logs" value={formatNumber(analytics.logs.length)} detail={`${formatNumber(analytics.toolLogs.length)} tool calls`} />
                    <MetricTile label="Context" value={analytics.contextWindow ? `${analytics.contextPct.toFixed(1)}%` : 'Not captured'} detail={analytics.contextWindow ? `${formatTokenCount(analytics.contextTokens)} / ${formatTokenCount(analytics.contextWindow)}` : undefined} />
                    <MetricTile label="Duration" value={durationLabel(session.durationSeconds)} />
                  </div>
                </>
              ) : null}

              {activeTab === 'agents-models' ? (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <Bot size={14} /> Agents
                    </div>
                    <MiniTable rows={analytics.agentRows} emptyLabel="No agent attribution captured." />
                  </div>
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <Cpu size={14} /> Models
                    </div>
                    <MiniTable rows={analytics.modelRows} emptyLabel="No model allocation captured." countLabel="Steps" />
                  </div>
                </div>
              ) : null}

              {activeTab === 'skills-artifacts' ? (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <Database size={14} /> Skills
                    </div>
                    <MiniTable rows={analytics.skillRows} emptyLabel="No skill events captured." />
                  </div>
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <LinkIcon size={14} /> Artifacts
                    </div>
                    <MiniTable rows={analytics.artifactRows} emptyLabel="No linked artifacts captured." />
                  </div>
                  {(session.linkedArtifacts || []).length > 0 ? (
                    <div className="lg:col-span-2">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Latest Artifact Links</div>
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                        {(session.linkedArtifacts || []).slice(0, 6).map(artifact => (
                          <div key={artifact.id} className="min-w-0 rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2">
                            <div className="truncate text-xs font-medium text-panel-foreground" title={artifact.title}>{artifact.title}</div>
                            <div className="mt-0.5 flex flex-wrap gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                              <span>{artifact.type}</span>
                              <span>{artifact.source}</span>
                              {artifact.sourceLogId ? <span className="font-mono">{artifact.sourceLogId}</span> : null}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {activeTab === 'files-tools' ? (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <Wrench size={14} /> Tools
                    </div>
                    <MiniTable rows={analytics.toolRows} emptyLabel="No tool calls captured." />
                  </div>
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <FileText size={14} /> File Touches
                    </div>
                    <MiniTable rows={analytics.fileRows} emptyLabel="No file updates captured." />
                  </div>
                  <div className="lg:col-span-2 grid grid-cols-2 gap-3 md:grid-cols-4">
                    <MetricTile label="Updated files" value={formatNumber((session.updatedFiles || []).length)} />
                    <MetricTile label="Additions" value={formatNumber((session.updatedFiles || []).reduce((sum, file) => sum + Number(file.additions || 0), 0))} tone="text-emerald-300" />
                    <MetricTile label="Deletions" value={formatNumber((session.updatedFiles || []).reduce((sum, file) => sum + Number(file.deletions || 0), 0))} tone="text-rose-300" />
                    <MetricTile label="Failed tools" value={formatNumber(analytics.failedToolLogs.length)} tone={analytics.failedToolLogs.length > 0 ? 'text-amber-300' : undefined} />
                  </div>
                  <div className="lg:col-span-2">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">File Action Mix</div>
                    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                      <MiniTable rows={analytics.fileActionRows} emptyLabel="No file action breakdown captured." />
                      <MiniTable rows={analytics.fileTypeRows} emptyLabel="No file type breakdown captured." />
                    </div>
                  </div>
                </div>
              ) : null}

              {activeTab === 'attribution-provenance' ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <MetricTile label="Attribution entities" value={formatNumber(session.usageAttributionSummary?.summary.entityCount || 0)} />
                    <MetricTile label="Attributed events" value={formatNumber(session.usageAttributionCalibration?.attributedEventCount || 0)} />
                    <MetricTile label="Coverage" value={formatPercent(Number(session.usageAttributionCalibration?.primaryCoverage || 0), 0)} />
                    <MetricTile label="Avg confidence" value={Number(session.usageAttributionCalibration?.averageConfidence || 0).toFixed(2)} />
                  </div>
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Top Attribution</div>
                    <MiniTable rows={analytics.attributionRows} emptyLabel="No usage attribution rows captured." countLabel="Exclusive tokens" />
                  </div>
                  <KeyValueGrid
                    rows={[
                      { label: 'Source', value: sourceLabel(session.source || session.platformType), title: String(session.source || session.platformType || '') },
                      { label: 'Project', value: session.projectId === '' ? 'Unattributed' : sourceLabel(session.projectId), title: String(session.projectId || '') },
                      { label: 'Working directory', value: sourceLabel(session.cwd), title: String(session.cwd || '') },
                      { label: 'Cost provenance', value: sourceLabel(session.costProvenance), title: String(session.pricingModelSource || session.costProvenance || '') },
                      { label: 'Context source', value: sourceLabel(session.contextMeasurementSource), title: String(session.contextMeasurementSource || '') },
                      { label: 'Git branch', value: sourceLabel(session.gitBranch), title: String(session.gitBranch || '') },
                      { label: 'Commit evidence', value: analytics.commits.length > 0 ? analytics.commits.map(commit => commit.slice(0, 10)).join(', ') : 'Not captured', title: analytics.commits.join(', ') },
                    ]}
                  />
                  {session.aosCorrelation ? (
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2">
                      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        <GitCommit size={14} /> AOS Correlation
                      </div>
                      <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-[11px] text-panel-foreground">
                        {JSON.stringify(session.aosCorrelation, null, 2)}
                      </pre>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
