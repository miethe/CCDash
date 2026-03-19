import React from 'react';
import { ContentPane, type TruncationInfo } from '@miethe/ui/content-viewer';
import { getContentViewerMode } from '@/lib/contentViewer';
import {
  buildContentViewerTruncationInfo,
  isContentViewerEditable,
  normalizeContentViewerPath,
} from '@/lib/contentViewer';

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
  const viewerMode = getContentViewerMode(normalizedPath);
  const resolvedReadOnly = readOnly || !isContentViewerEditable(normalizedPath);
  const resolvedTruncationInfo = buildContentViewerTruncationInfo(truncationInfo);

  return (
    <div
      className={[
        'overflow-hidden rounded-xl border border-slate-800 bg-slate-950/95 shadow-[0_0_0_1px_rgba(15,23,42,0.25),0_24px_80px_rgba(2,6,23,0.6)]',
        className || '',
      ]
        .filter(Boolean)
        .join(' ')}
      data-content-viewer-mode={viewerMode}
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
};
