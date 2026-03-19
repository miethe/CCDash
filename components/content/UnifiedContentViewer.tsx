import React from 'react';
import { Edit3, ChevronRight, AlertTriangle } from 'lucide-react';
import { ContentPane, type TruncationInfo } from '@miethe/ui/content-viewer';
import { FrontmatterDisplay } from '@miethe/ui/display';
import { detectFrontmatter, parseFrontmatter, stripFrontmatter } from '@miethe/ui/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  buildContentViewerTruncationInfo,
  getReadOnlyContentViewerMode,
  isContentViewerEditable,
  normalizeContentViewerPath,
} from '../../lib/contentViewer';

export interface UnifiedContentViewerProps {
  path: string | null;
  content: string | null;
  isLoading?: boolean;
  error?: string | null;
  readOnly?: boolean;
  truncationInfo?: TruncationInfo | null;
  isEditing?: boolean;
  editedContent?: string;
  onEditStart?: () => void;
  onEditChange?: (content: string) => void;
  onSave?: (content: string) => void | Promise<void>;
  onCancel?: () => void;
  ariaLabel?: string;
  className?: string;
}

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const power = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / 1024 ** power;
  return power === 0 ? `${bytes} B` : `${value.toFixed(1)} ${units[power]}`;
};

export const UnifiedContentViewer = ({
  path,
  content,
  isLoading = false,
  error = null,
  readOnly = false,
  truncationInfo,
  isEditing = false,
  editedContent = '',
  onEditStart,
  onEditChange,
  onSave,
  onCancel,
  ariaLabel,
  className,
}: UnifiedContentViewerProps) => {
  const normalizedPath = normalizeContentViewerPath(path);
  const resolvedReadOnly = readOnly || !isContentViewerEditable(normalizedPath);
  const resolvedTruncationInfo = buildContentViewerTruncationInfo(truncationInfo);
  const viewerMode = getReadOnlyContentViewerMode(normalizedPath, content);
  const canStartEdit = !resolvedReadOnly && !isEditing && typeof onEditStart === 'function';

  const parsedContent = React.useMemo(() => {
    if (!content || !detectFrontmatter(content)) {
      return {
        frontmatter: null as Record<string, unknown> | null,
        displayContent: content || '',
      };
    }

    const parsed = parseFrontmatter(content);
    return {
      frontmatter: parsed.frontmatter,
      displayContent: stripFrontmatter(content),
    };
  }, [content]);

  if (isEditing) {
    return (
      <div
        className={[
          'ccdash-content-viewer min-h-0 w-full overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/95 shadow-[0_0_0_1px_rgba(15,23,42,0.25),0_24px_80px_rgba(2,6,23,0.6)]',
          className || '',
        ].filter(Boolean).join(' ')}
      >
        <ContentPane
          path={normalizedPath}
          content={content}
          isLoading={isLoading}
          error={error}
          readOnly={resolvedReadOnly}
          truncationInfo={resolvedTruncationInfo}
          isEditing={isEditing}
          editedContent={editedContent}
          onEditStart={onEditStart}
          onEditChange={onEditChange}
          onSave={onSave}
          onCancel={onCancel}
          ariaLabel={ariaLabel || (normalizedPath ? `File content: ${normalizedPath}` : 'File content viewer')}
        />
      </div>
    );
  }

  const breadcrumbSegments = (normalizedPath || 'Untitled')
    .split('/')
    .filter(Boolean);

  return (
    <div
      className={[
        'ccdash-content-viewer flex min-h-0 w-full flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/95 shadow-[0_0_0_1px_rgba(15,23,42,0.25),0_24px_80px_rgba(2,6,23,0.6)]',
        className || '',
      ].filter(Boolean).join(' ')}
      data-content-viewer-mode={viewerMode}
      role="region"
      aria-label={ariaLabel || (normalizedPath ? `File content: ${normalizedPath}` : 'File content viewer')}
    >
      <div className="flex items-center justify-between gap-4 border-b border-slate-800 bg-slate-950/80 px-4 py-3">
        <div className="min-w-0">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            {viewerMode === 'markdown' ? 'Markdown Preview' : 'File Preview'}
          </div>
          <nav className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-slate-400" aria-label="File path">
            {breadcrumbSegments.map((segment, index) => (
              <React.Fragment key={`${segment}-${index}`}>
                {index > 0 && <ChevronRight size={12} className="shrink-0 text-slate-600" />}
                <span className={index === breadcrumbSegments.length - 1 ? 'font-medium text-slate-100' : ''}>
                  {segment}
                </span>
              </React.Fragment>
            ))}
          </nav>
        </div>
        {canStartEdit && (
          <button
            type="button"
            onClick={onEditStart}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:border-indigo-500/40 hover:bg-indigo-500/10 hover:text-indigo-100"
          >
            <Edit3 size={14} />
            Edit
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="flex h-full min-h-0 flex-col gap-4">
          {resolvedTruncationInfo?.truncated && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-300" />
              <div>
                <div className="font-medium text-amber-200">Large file truncated</div>
                <div className="mt-1 text-xs text-amber-100/80">
                  Showing a partial preview
                  {typeof resolvedTruncationInfo.originalSize === 'number'
                    ? ` of ${formatBytes(resolvedTruncationInfo.originalSize)}.`
                    : '.'}
                </div>
              </div>
            </div>
          )}

          {parsedContent.frontmatter && (
            <FrontmatterDisplay
              frontmatter={parsedContent.frontmatter}
              defaultCollapsed
              className="shrink-0"
            />
          )}

          {isLoading || error || !normalizedPath || content === null ? (
            <div className="min-h-0 flex-1 overflow-hidden rounded-xl">
              <ContentPane
                path={normalizedPath}
                content={content}
                isLoading={isLoading}
                error={error}
                readOnly={resolvedReadOnly}
                truncationInfo={resolvedTruncationInfo}
                isEditing={false}
                editedContent={editedContent}
                onEditStart={onEditStart}
                onEditChange={onEditChange}
                onSave={onSave}
                onCancel={onCancel}
                ariaLabel={ariaLabel || (normalizedPath ? `File content: ${normalizedPath}` : 'File content viewer')}
              />
            </div>
          ) : viewerMode === 'markdown' ? (
            <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-800/80 bg-slate-950/70">
              <div className="ccdash-markdown p-6 text-sm text-slate-200">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {parsedContent.displayContent || '*No content to preview*'}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-800/80 bg-slate-950/70">
              <pre className="min-w-max p-4 font-mono text-xs leading-6 text-slate-200">
                {parsedContent.displayContent || ''}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
