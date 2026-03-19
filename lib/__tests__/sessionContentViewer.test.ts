import { describe, expect, it } from 'vitest';

import { getInlineContentViewerPayload } from '../sessionContentViewer';

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
});
