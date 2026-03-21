import React, { useMemo } from 'react';
import { FileCode2 } from 'lucide-react';

import { SessionFileUpdate, SessionLog } from '../../types';
import { TestStatusView } from './TestStatusView';

interface SessionTestStatusViewProps {
  projectId: string;
  sessionId: string;
  sessionStatus: string;
  sessionFileUpdates: SessionFileUpdate[];
  sessionLogs: SessionLog[];
  onNavigateToTestingPage?: () => void;
}

const TEST_FILE_PATTERNS = [
  /test_.*\.py$/i,
  /.*_test\.py$/i,
  /.*\.test\.(ts|tsx|js|jsx)$/i,
  /.*\.spec\.(ts|tsx|js|jsx)$/i,
  /(^|\/)tests?\//i,
  /(^|\/)conftest\.py$/i,
];

const isTestFile = (path: string): boolean => TEST_FILE_PATTERNS.some(pattern => pattern.test(path || ''));

const formatNetDiff = (row: SessionFileUpdate): string => {
  const adds = Math.max(0, row.additions || 0);
  const dels = Math.max(0, row.deletions || 0);
  if (adds === 0 && dels === 0) return 'no diff';
  return `+${adds} / -${dels}`;
};

const asRecord = (value: unknown): Record<string, any> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, any>
    : {}
);

const asStringArray = (value: unknown): string[] => (
  Array.isArray(value)
    ? value
      .map(item => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
      .filter(Boolean)
    : []
);

const asNumber = (value: unknown, fallback = 0): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
};

const takeString = (...values: unknown[]): string => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return '';
};

const toEpoch = (timestamp?: string): number => {
  if (!timestamp) return 0;
  const parsed = Date.parse(timestamp);
  return Number.isFinite(parsed) ? parsed : 0;
};

interface SessionTestRunRow {
  logId: string;
  timestamp: string;
  framework: string;
  status: string;
  command: string;
  domain: string;
  domains: string[];
  targets: string[];
  flags: string[];
  total: number;
  durationSeconds: number;
  counts: Record<string, number>;
}

export const SessionTestStatusView: React.FC<SessionTestStatusViewProps> = ({
  projectId,
  sessionId,
  sessionStatus,
  sessionFileUpdates,
  sessionLogs,
  onNavigateToTestingPage,
}) => {
  const modifiedTestFiles = useMemo(() => (
    (sessionFileUpdates || [])
      .filter(file => isTestFile(file.filePath))
      .sort((a, b) => toEpoch(b.timestamp) - toEpoch(a.timestamp))
  ),
    [sessionFileUpdates],
  );

  const testRunsDuringSession = useMemo<SessionTestRunRow[]>(() => (
    (sessionLogs || [])
      .filter(log => log.type === 'tool')
      .map(log => {
        const metadata = asRecord(log.metadata);
        const testRun = asRecord(metadata.testRun);
        if (!Object.keys(testRun).length) return null;

        const result = asRecord(testRun.result);
        const countsRecord = asRecord(result.counts || metadata.testCounts);
        const counts: Record<string, number> = {};
        ['passed', 'failed', 'error', 'skipped', 'xfailed', 'xpassed', 'deselected', 'rerun'].forEach(key => {
          const count = asNumber(countsRecord[key], 0);
          if (count > 0) counts[key] = count;
        });
        let total = asNumber(result.total || metadata.testTotal, 0);
        if (total <= 0) {
          total = Object.values(counts).reduce((sum, value) => sum + value, 0);
        }

        return {
          logId: log.id,
          timestamp: String(log.timestamp || ''),
          framework: takeString(testRun.framework, metadata.testFramework, 'test'),
          status: takeString(result.status, metadata.testStatus, 'unknown'),
          command: takeString(
            testRun.commandSegment,
            testRun.command,
            metadata.bashCommand,
            metadata.command,
            log.toolCall?.args,
          ),
          domain: takeString(testRun.primaryDomain, metadata.testDomain),
          domains: asStringArray(testRun.domains || metadata.testDomains),
          targets: asStringArray(testRun.targets || metadata.testTargets),
          flags: asStringArray(testRun.flags || metadata.testFlags),
          total,
          durationSeconds: asNumber(result.durationSeconds || metadata.testDurationSeconds, 0),
          counts,
        } satisfies SessionTestRunRow;
      })
      .filter((row): row is SessionTestRunRow => Boolean(row))
      .sort((a, b) => toEpoch(b.timestamp) - toEpoch(a.timestamp))
  ), [sessionLogs]);

  const isLive = ['active', 'running'].includes(String(sessionStatus || '').toLowerCase());

  return (
    <div className="space-y-4">
      {modifiedTestFiles.length > 0 && (
        <section className="rounded-xl border border-panel-border bg-panel p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Modified Tests During This Session
          </h3>
          <div className="max-h-72 overflow-y-auto pr-1 space-y-2">
            {modifiedTestFiles.map((file, index) => (
              <div
                key={`${file.filePath}-${file.timestamp}-${index}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2 text-xs"
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-panel-foreground">{file.filePath}</p>
                  <p className="text-muted-foreground">{new Date(file.timestamp).toLocaleString()}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded border border-panel-border bg-surface-muted px-1.5 py-0.5">
                    <FileCode2 size={11} />
                    {file.action || 'update'}
                  </span>
                  <span className="font-mono">{formatNetDiff(file)}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-xl border border-panel-border bg-panel p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Tests Run During This Session
        </h3>
        {testRunsDuringSession.length === 0 ? (
          <p className="text-xs text-muted-foreground">No test runs detected from transcript tool calls.</p>
        ) : (
          <div className="max-h-80 overflow-y-auto pr-1 space-y-2">
            {testRunsDuringSession.map((run, index) => (
              <div
                key={`${run.logId}-${run.timestamp}-${index}`}
                className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-2 text-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-panel-foreground">{run.command || `${run.framework} run`}</p>
                    <p className="text-muted-foreground">{new Date(run.timestamp).toLocaleString()}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded border border-panel-border bg-surface-muted px-1.5 py-0.5 text-foreground">
                      {run.framework}
                    </span>
                    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 ${
                      run.status === 'passed'
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                        : run.status === 'failed'
                          ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                          : 'border-panel-border bg-surface-muted text-foreground'
                    }`}>
                      {run.status}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                  {run.total > 0 && <span>{run.total} tests</span>}
                  {run.durationSeconds > 0 && <span>{run.durationSeconds.toFixed(2)}s</span>}
                  {run.domain && <span>domain: {run.domain}</span>}
                  {Object.entries(run.counts).map(([key, value]) => (
                    <span key={`${run.logId}-${key}`} className="font-mono">{key}:{value}</span>
                  ))}
                </div>

                {(run.targets.length > 0 || run.domains.length > 0 || run.flags.length > 0) && (
                  <div className="space-y-1">
                    {run.targets.length > 0 && (
                      <p className="text-muted-foreground truncate">targets: {run.targets.join(', ')}</p>
                    )}
                    {run.domains.length > 0 && (
                      <p className="text-muted-foreground truncate">domains: {run.domains.join(', ')}</p>
                    )}
                    {run.flags.length > 0 && (
                      <p className="text-muted-foreground truncate">flags: {run.flags.join(' ')}</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <TestStatusView
        projectId={projectId}
        filter={{ sessionId }}
        mode="tab"
        isLive={isLive}
        onNavigateToTestingPage={onNavigateToTestingPage}
      />
    </div>
  );
};

export type { SessionTestStatusViewProps };
