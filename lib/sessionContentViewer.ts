import { looksLikeMarkdownContent, normalizeContentViewerPath } from './contentViewer';

export interface InlineContentViewerPayload {
  path: string;
  content: string;
}

const TRANSCRIPT_CONTENT_VIEWER_CHAR_THRESHOLD = 600;
const TRANSCRIPT_CONTENT_VIEWER_LINE_THRESHOLD = 14;

const extractStructuredOutputContent = (rawOutput: string): string | null => {
  const raw = String(rawOutput || '');
  const trimmed = raw.trim();
  if (!trimmed) return null;

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed === 'string' && parsed.trim()) {
      return parsed;
    }
    if (parsed && typeof parsed === 'object') {
      const record = parsed as Record<string, unknown>;
      if (typeof record.content === 'string' && record.content.trim()) {
        return record.content;
      }
      if (typeof record.stdout === 'string' && record.stdout.trim()) {
        return record.stdout;
      }
      if (typeof record.text === 'string' && record.text.trim()) {
        return record.text;
      }
    }
  } catch {
    // Fall back to treating the output as raw text.
  }

  return raw;
};

const stripLinePrefixes = (content: string): string => {
  const lines = content.split('\n');
  const nonEmptyLines = lines.filter(line => line.trim().length > 0);
  if (nonEmptyLines.length === 0) return content;

  const prefixedLinePattern = /^\s*\d+(?:\s*[|:]\s|\t)/;
  const prefixedCount = nonEmptyLines.filter(line => prefixedLinePattern.test(line)).length;
  if (prefixedCount / nonEmptyLines.length < 0.6) {
    return content;
  }

  return lines.map(line => line.replace(prefixedLinePattern, '')).join('\n');
};

const shouldUseTranscriptContentViewer = (content: string): boolean => {
  const trimmed = content.trim();
  if (!trimmed) return false;
  if (looksLikeMarkdownContent(trimmed)) return true;
  if (trimmed.length >= TRANSCRIPT_CONTENT_VIEWER_CHAR_THRESHOLD) return true;
  if (trimmed.split(/\r?\n/).length >= TRANSCRIPT_CONTENT_VIEWER_LINE_THRESHOLD) return true;
  return false;
};

const buildSyntheticTranscriptPath = (logId: string, content: string): string => {
  const safeId = String(logId || 'log')
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '') || 'log';

  return `transcript/${safeId}.${looksLikeMarkdownContent(content) ? 'md' : 'txt'}`;
};

export const getInlineContentViewerPayload = (
  filePath: string | null | undefined,
  rawOutput: string | null | undefined,
): InlineContentViewerPayload | null => {
  const path = normalizeContentViewerPath(filePath);
  const content = stripLinePrefixes(extractStructuredOutputContent(String(rawOutput || '')) || '');
  if (!path || !content) {
    return null;
  }

  return {
    path,
    content,
  };
};

export const getTranscriptContentViewerPayload = (
  logId: string,
  rawContent: string | null | undefined,
): InlineContentViewerPayload | null => {
  const content = extractStructuredOutputContent(String(rawContent || ''));
  if (!content || !shouldUseTranscriptContentViewer(content)) {
    return null;
  }

  return {
    path: buildSyntheticTranscriptPath(logId, content),
    content,
  };
};
