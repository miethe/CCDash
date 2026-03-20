import { describe, expect, it } from 'vitest';
import {
  buildContentViewerTruncationInfo,
  getContentViewerExtension,
  getContentViewerMode,
  getReadOnlyContentViewerMode,
  isContentViewerEditable,
  looksLikeMarkdownContent,
  normalizeContentViewerPath,
  resolveContentViewerFrontmatter,
  shouldUseContentViewer,
} from '../contentViewer';

describe('contentViewer utilities', () => {
  it('normalizes file paths for viewer usage', () => {
    expect(normalizeContentViewerPath('./docs\\plans//phase-1.md')).toBe('docs/plans/phase-1.md');
    expect(normalizeContentViewerPath('')).toBeNull();
  });

  it('derives extension, mode, and editability', () => {
    expect(getContentViewerExtension('notes/README.MD')).toBe('.md');
    expect(getContentViewerMode('notes/README.MD')).toBe('markdown');
    expect(isContentViewerEditable('notes/README.MD')).toBe(true);
    expect(getContentViewerMode('artifacts/output.json')).toBe('code');
    expect(isContentViewerEditable('artifacts/output.json')).toBe(true);
    expect(getContentViewerMode('logs/output.log')).toBe('text');
    expect(isContentViewerEditable('logs/output.log')).toBe(false);
  });

  it('builds truncation info only when needed', () => {
    expect(buildContentViewerTruncationInfo()).toBeUndefined();
    expect(
      buildContentViewerTruncationInfo({
        truncated: true,
        originalSize: 2048,
        fullFileUrl: 'https://example.com/file.md',
      })
    ).toEqual({
      truncated: true,
      originalSize: 2048,
      fullFileUrl: 'https://example.com/file.md',
    });
  });

  it('allows viewer mode only when a path is present', () => {
    expect(shouldUseContentViewer(null, 'content')).toBe(false);
    expect(shouldUseContentViewer('docs/file.md', null)).toBe(true);
  });

  it('detects markdown-like content for read-only rendering', () => {
    expect(looksLikeMarkdownContent('# Heading\n\n- one')).toBe(true);
    expect(looksLikeMarkdownContent('plain text output')).toBe(false);
    expect(getReadOnlyContentViewerMode('logs/output.txt', '# Heading\n\nParagraph')).toBe('markdown');
    expect(getReadOnlyContentViewerMode('logs/output.txt', 'plain text output')).toBe('code');
  });

  it('prefers raw frontmatter payloads for viewer rendering', () => {
    expect(resolveContentViewerFrontmatter({
      title: 'Normalized',
      raw: {
        title: 'Original',
        status: 'draft',
      },
    })).toEqual({
      title: 'Original',
      status: 'draft',
    });
  });

  it('filters empty frontmatter payloads', () => {
    expect(resolveContentViewerFrontmatter({
      tags: [],
      status: '',
      raw: {},
    })).toBeNull();
  });
});
