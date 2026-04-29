import { describe, expect, it } from 'vitest';

import { docsEntryBySlug, docsGroups, docsNavigation, docsPublicPath, docsSiteDescription, docsSiteTitle } from '../docsContent';

describe('docs content manifest', () => {
  it('exposes a public docs title and description', () => {
    expect(docsSiteTitle).toBe('CCDash Docs');
    expect(docsSiteDescription).toContain('setup');
  });

  it('keeps a curated nav structure with stable group ordering', () => {
    expect(docsGroups.map((group) => group.id)).toEqual(['start-here', 'guides', 'reference']);
    expect(docsNavigation[0].items[0].path).toBe('/docs/guides/setup.md');
    expect(docsNavigation[1].items).toHaveLength(8);
  });

  it('indexes entries by slug for route lookups', () => {
    expect(docsEntryBySlug.get('mcp-setup-guide')?.title).toBe('MCP Setup Guide');
    expect(docsPublicPath(docsEntryBySlug.get('document-frontmatter-readme')!.path)).toBe('/docs/schemas/document_frontmatter/README.md');
  });
});
