import React from 'react';
import { Edit3, ChevronRight, AlertTriangle } from 'lucide-react';
import { ContentPane, type TruncationInfo } from '@miethe/ui/content-viewer';
import { FrontmatterDisplay } from '@miethe/ui/display';
import { detectFrontmatter, parseFrontmatter, stripFrontmatter } from '@miethe/ui/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Button } from '../ui/button';
import { AlertSurface, Surface } from '../ui/surface';
import {
  buildContentViewerTruncationInfo,
  getReadOnlyContentViewerMode,
  isContentViewerEditable,
  normalizeContentViewerPath,
} from '../../lib/contentViewer';

export interface UnifiedContentViewerProps {
  path: string | null;
  content: string | null;
  frontmatter?: Record<string, unknown> | null;
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
  frontmatter = null,
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
  const contentContainsFrontmatter = Boolean(content && detectFrontmatter(content));
  const hasExplicitFrontmatter = Boolean(
    frontmatter
    && typeof frontmatter === 'object'
    && !Array.isArray(frontmatter)
    && Object.keys(frontmatter).length > 0,
  );
  const shouldRenderExplicitFrontmatter = hasExplicitFrontmatter && !contentContainsFrontmatter;

  const parsedContent = React.useMemo(() => {
    if (shouldRenderExplicitFrontmatter) {
      return {
        frontmatter,
        displayContent: content || '',
      };
    }

    if (!content || !contentContainsFrontmatter) {
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
  }, [content, contentContainsFrontmatter, frontmatter, shouldRenderExplicitFrontmatter]);

  if (isEditing) {
    return (
      <Surface
        tone="overlay"
        padding="none"
        shadow="viewer"
        className={[
          'ccdash-content-viewer flex min-h-0 w-full flex-col overflow-hidden rounded-2xl',
          className || '',
        ].filter(Boolean).join(' ')}
      >
        {parsedContent.frontmatter && shouldRenderExplicitFrontmatter && (
          <FrontmatterDisplay
            frontmatter={parsedContent.frontmatter}
            defaultCollapsed
            className="m-4 mb-0 shrink-0"
          />
        )}
        <div className="min-h-0 flex-1 overflow-hidden">
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
      </Surface>
    );
  }

  const breadcrumbSegments = (normalizedPath || 'Untitled')
    .split('/')
    .filter(Boolean);

  return (
    <Surface
      tone="overlay"
      padding="none"
      shadow="viewer"
      className={[
        'ccdash-content-viewer flex min-h-0 w-full flex-col overflow-hidden rounded-2xl',
        className || '',
      ].filter(Boolean).join(' ')}
      data-content-viewer-mode={viewerMode}
      role="region"
      aria-label={ariaLabel || (normalizedPath ? `File content: ${normalizedPath}` : 'File content viewer')}
    >
      <div className="flex items-center justify-between gap-4 border-b border-panel-border bg-surface-overlay/80 px-4 py-3">
        <div className="min-w-0">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {viewerMode === 'markdown' ? 'Markdown Preview' : 'File Preview'}
          </div>
          <nav className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-muted-foreground" aria-label="File path">
            {breadcrumbSegments.map((segment, index) => (
              <React.Fragment key={`${segment}-${index}`}>
                {index > 0 && <ChevronRight size={12} className="shrink-0 text-disabled-foreground" />}
                <span className={index === breadcrumbSegments.length - 1 ? 'font-medium text-panel-foreground' : ''}>
                  {segment}
                </span>
              </React.Fragment>
            ))}
          </nav>
        </div>
        {canStartEdit && (
          <Button
            type="button"
            onClick={onEditStart}
            variant="panel"
            size="sm"
            className="shrink-0"
          >
            <Edit3 size={14} />
            Edit
          </Button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="flex h-full min-h-0 flex-col gap-4">
          {resolvedTruncationInfo?.truncated && (
            <AlertSurface intent="warning" className="flex items-start gap-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning-foreground" />
              <div>
                <div className="font-medium text-warning-foreground">Large file truncated</div>
                <div className="mt-1 text-xs text-warning-foreground/80">
                  Showing a partial preview
                  {typeof resolvedTruncationInfo.originalSize === 'number'
                    ? ` of ${formatBytes(resolvedTruncationInfo.originalSize)}.`
                    : '.'}
                </div>
              </div>
            </AlertSurface>
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
            <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-panel-border bg-surface-overlay/70">
              <div className="ccdash-markdown p-6 text-sm text-panel-foreground">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {parsedContent.displayContent || '*No content to preview*'}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-panel-border bg-surface-overlay/70">
              <pre className="min-w-max p-4 font-mono text-xs leading-6 text-panel-foreground">
                {parsedContent.displayContent || ''}
              </pre>
            </div>
          )}
        </div>
      </div>
    </Surface>
  );
};
