import type { TruncationInfo } from '@miethe/ui/content-viewer';

const VIEWER_EDITABLE_EXTENSIONS = new Set([
  '.md',
  '.markdown',
  '.txt',
  '.json',
  '.ts',
  '.tsx',
  '.js',
  '.jsx',
  '.py',
  '.yml',
  '.yaml',
  '.toml',
]);

const VIEWER_MARKDOWN_EXTENSIONS = new Set(['.md', '.markdown']);
const MARKDOWN_SIGNAL_PATTERNS = [
  /^#{1,6}\s+/m,
  /^>\s+/m,
  /^[-*+]\s+/m,
  /^\d+\.\s+/m,
  /```[\s\S]*?```/m,
  /^\|.+\|\s*$/m,
  /^---\n[\s\S]+?\n---\n?/m,
];

export type ContentViewerMode = 'markdown' | 'text' | 'code' | 'binary';

export interface ContentViewerTruncationInput {
  truncated?: boolean;
  originalSize?: number;
  fullFileUrl?: string;
}

export const normalizeContentViewerPath = (path: string | null | undefined): string | null => {
  const normalized = String(path || '')
    .replace(/\\/g, '/')
    .replace(/^(?:\.\/|\/)+/, '')
    .replace(/\/+/g, '/')
    .trim();

  return normalized.length > 0 ? normalized : null;
};

export const getContentViewerExtension = (path: string | null | undefined): string => {
  const normalizedPath = normalizeContentViewerPath(path);
  if (!normalizedPath) return '';

  const filename = normalizedPath.split('/').pop() || '';
  const lastDot = filename.lastIndexOf('.');
  if (lastDot <= 0) return '';
  return filename.slice(lastDot).toLowerCase();
};

export const getContentViewerMode = (path: string | null | undefined): ContentViewerMode => {
  const extension = getContentViewerExtension(path);
  if (VIEWER_MARKDOWN_EXTENSIONS.has(extension)) return 'markdown';
  if (VIEWER_EDITABLE_EXTENSIONS.has(extension)) return 'code';
  if (!extension) return 'text';
  return 'text';
};

export const looksLikeMarkdownContent = (content: string | null | undefined): boolean => {
  const text = String(content || '').trim();
  if (!text) return false;

  return MARKDOWN_SIGNAL_PATTERNS.some(pattern => pattern.test(text));
};

export const getReadOnlyContentViewerMode = (
  path: string | null | undefined,
  content: string | null | undefined,
): ContentViewerMode => {
  const modeFromPath = getContentViewerMode(path);
  if (modeFromPath === 'markdown') {
    return 'markdown';
  }
  if (looksLikeMarkdownContent(content)) {
    return 'markdown';
  }
  return modeFromPath;
};

export const isContentViewerEditable = (path: string | null | undefined): boolean => {
  const extension = getContentViewerExtension(path);
  return extension ? VIEWER_EDITABLE_EXTENSIONS.has(extension) : false;
};

export const shouldUseContentViewer = (path: string | null | undefined, content: string | null | undefined): boolean => {
  if (!normalizeContentViewerPath(path)) return false;
  if (typeof content === 'string' && content.trim().length > 0) return true;
  return true;
};

export const buildContentViewerTruncationInfo = (
  input?: ContentViewerTruncationInput | TruncationInfo | null
): TruncationInfo | undefined => {
  if (!input?.truncated) return undefined;
  return {
    truncated: true,
    originalSize: typeof input.originalSize === 'number' ? input.originalSize : undefined,
    fullFileUrl: input.fullFileUrl,
  };
};
