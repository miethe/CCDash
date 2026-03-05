import React, { useMemo } from 'react';
import { FileCode2 } from 'lucide-react';

import { SessionFileUpdate } from '../../types';
import { TestStatusView } from './TestStatusView';

interface SessionTestStatusViewProps {
  projectId: string;
  sessionId: string;
  sessionStatus: string;
  sessionFileUpdates: SessionFileUpdate[];
  onNavigateToTestingPage?: () => void;
}

const TEST_FILE_PATTERNS = [
  /test_.*\.py$/i,
  /.*_test\.py$/i,
  /.*\.test\.(ts|tsx|js|jsx)$/i,
  /.*\.spec\.(ts|tsx|js|jsx)$/i,
  /(^|\/)tests?\//i,
];

const isTestFile = (path: string): boolean => TEST_FILE_PATTERNS.some(pattern => pattern.test(path || ''));

const formatNetDiff = (row: SessionFileUpdate): string => {
  const adds = Math.max(0, row.additions || 0);
  const dels = Math.max(0, row.deletions || 0);
  if (adds === 0 && dels === 0) return 'no diff';
  return `+${adds} / -${dels}`;
};

export const SessionTestStatusView: React.FC<SessionTestStatusViewProps> = ({
  projectId,
  sessionId,
  sessionStatus,
  sessionFileUpdates,
  onNavigateToTestingPage,
}) => {
  const modifiedTestFiles = useMemo(
    () => (sessionFileUpdates || []).filter(file => isTestFile(file.filePath)),
    [sessionFileUpdates],
  );

  const isLive = ['active', 'running'].includes(String(sessionStatus || '').toLowerCase());

  return (
    <div className="space-y-4">
      {modifiedTestFiles.length > 0 && (
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Modified Tests During This Session
          </h3>
          <div className="space-y-2">
            {modifiedTestFiles.map((file, index) => (
              <div
                key={`${file.filePath}-${file.timestamp}-${index}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-xs"
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-slate-200">{file.filePath}</p>
                  <p className="text-slate-500">{new Date(file.timestamp).toLocaleString()}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-slate-400">
                  <span className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5">
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
