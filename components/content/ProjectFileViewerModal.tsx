import React from 'react';
import { ExternalLink, X } from 'lucide-react';

import { UnifiedContentViewer } from './UnifiedContentViewer';
import { getCodebaseFileContent, type CodebaseFileContentResponse } from '../../services/codebase';

interface ProjectFileViewerModalProps {
  filePath: string;
  localPath?: string | null;
  onClose: () => void;
}

export const ProjectFileViewerModal: React.FC<ProjectFileViewerModalProps> = ({
  filePath,
  localPath,
  onClose,
}) => {
  const [payload, setPayload] = React.useState<CodebaseFileContentResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const next = await getCodebaseFileContent(filePath);
        if (!cancelled) {
          setPayload(next);
        }
      } catch (loadError: any) {
        if (!cancelled) {
          setPayload(null);
          setError(loadError?.message || 'Failed to load file content');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [filePath]);

  const handleOpenLocalFile = React.useCallback(() => {
    if (!localPath) return;
    window.location.href = `vscode://file/${encodeURI(localPath)}`;
  }, [localPath]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="w-full max-w-6xl max-h-[92vh] overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl flex flex-col"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 bg-slate-950 px-5 py-4">
            <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-indigo-300">Shared Viewer</div>
            <h3 className="mt-1 truncate font-mono text-sm text-slate-100">{filePath}</h3>
            <div className="mt-1 text-xs text-slate-500">
              {typeof payload?.sizeBytes === 'number' ? `${payload.sizeBytes.toLocaleString()} bytes` : 'Loading file content'}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {localPath && (
              <button
                type="button"
                onClick={handleOpenLocalFile}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-300 hover:border-indigo-500/40 hover:text-indigo-200"
              >
                <ExternalLink size={14} />
                Open Locally
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-800 hover:text-slate-200"
              aria-label="Close file viewer"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden p-5">
          <UnifiedContentViewer
            path={payload?.filePath || filePath}
            content={payload?.content || null}
            isLoading={isLoading}
            error={error}
            readOnly
            truncationInfo={payload?.truncated ? { truncated: true, originalSize: payload.originalSize ?? payload.sizeBytes } : undefined}
            ariaLabel={`Project file content: ${filePath}`}
            className="h-full"
          />
        </div>
      </div>
    </div>
  );
};
