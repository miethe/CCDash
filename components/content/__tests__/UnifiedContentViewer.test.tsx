import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { UnifiedContentViewer } from '../UnifiedContentViewer';

describe('UnifiedContentViewer', () => {
  it('renders normalized file paths and file content in read-only mode', () => {
    const html = renderToStaticMarkup(
      <UnifiedContentViewer
        path="./docs/example.toml"
        content={'title = "Demo"\n'}
        readOnly
      />,
    );

    expect(html).toContain('data-content-viewer-mode="code"');
    expect(html).toContain('docs/example.toml');
    expect(html).toContain('title = &quot;Demo&quot;');
  });

  it('renders markdown-like content as formatted markdown in read-only mode', () => {
    const html = renderToStaticMarkup(
      <UnifiedContentViewer
        path="./logs/output.txt"
        content={'# Heading\n\n- first\n- second'}
        readOnly
      />,
    );

    expect(html).toContain('data-content-viewer-mode="markdown"');
    expect(html).toContain('<h1>Heading</h1>');
    expect(html).toContain('<li>first</li>');
  });
});
