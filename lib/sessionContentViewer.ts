import { normalizeContentViewerPath } from './contentViewer';

export interface InlineContentViewerPayload {
  path: string;
  content: string;
}

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

export const getInlineContentViewerPayload = (
  filePath: string | null | undefined,
  rawOutput: string | null | undefined,
): InlineContentViewerPayload | null => {
  const path = normalizeContentViewerPath(filePath);
  const content = extractStructuredOutputContent(String(rawOutput || ''));
  if (!path || !content) {
    return null;
  }

  return {
    path,
    content,
  };
};
