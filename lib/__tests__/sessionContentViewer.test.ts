import { describe, expect, it } from 'vitest';

import { getInlineContentViewerPayload, getTranscriptContentViewerPayload } from '../sessionContentViewer';

describe('sessionContentViewer helpers', () => {
  it('returns inline viewer payload for raw text output', () => {
    expect(getInlineContentViewerPayload('./docs/plan.md', '# Plan\n')).toEqual({
      path: 'docs/plan.md',
      content: '# Plan\n',
    });
  });

  it('extracts nested content fields from structured tool output', () => {
    expect(
      getInlineContentViewerPayload(
        'docs/plan.md',
        JSON.stringify({
          content: '# Loaded\n',
        }),
      ),
    ).toEqual({
      path: 'docs/plan.md',
      content: '# Loaded\n',
    });
  });

  it('returns null when path or content are missing', () => {
    expect(getInlineContentViewerPayload('', 'hello')).toBeNull();
    expect(getInlineContentViewerPayload('docs/plan.md', '')).toBeNull();
  });

  it('strips consistent read-tool line prefixes', () => {
    expect(getInlineContentViewerPayload('docs/plan.md', '1 | # Plan\n2 | - item\n3 | text')).toEqual({
      path: 'docs/plan.md',
      content: '# Plan\n- item\ntext',
    });
  });

  it('uses the shared viewer for long transcript content', () => {
    const payload = getTranscriptContentViewerPayload(
      'log-123',
      '# Heading\n\n' + 'Paragraph text.\n'.repeat(20),
    );

    expect(payload).toEqual({
      path: 'transcript/log-123.md',
      content: '# Heading\n\n' + 'Paragraph text.\n'.repeat(20),
    });
  });
});
