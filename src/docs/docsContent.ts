export type DocsGroupId = 'start-here' | 'guides' | 'reference';

export type DocsEntry = {
  slug: string;
  title: string;
  description: string;
  path: DocsPath;
};

export type DocsGroup = {
  id: DocsGroupId;
  title: string;
  description: string;
  entries: DocsEntry[];
};

export type DocsPath =
  | 'README.md'
  | 'guides/setup.md'
  | 'guides/runtime-storage-and-performance-quickstart.md'
  | 'guides/storage-profiles-guide.md'
  | 'guides/shared-content-viewer.md'
  | 'guides/cli-user-guide.md'
  | 'guides/standalone-cli-guide.md'
  | 'guides/mcp-setup-guide.md'
  | 'guides/operations-panel.md'
  | 'guides/telemetry-exporter-guide.md'
  | 'guides/agentic-sdlc-intelligence.md'
  | 'guides/session-usage-attribution.md'
  | 'guides/document-entity-and-linking.md'
  | 'schemas/document_frontmatter/README.md'
  | 'schemas/document_frontmatter/document-and-feature-mapping.md';

export const docsPublicPath = (path: DocsPath): string => `/docs/${path}`;

export const docsSiteTitle = 'CCDash Docs';

export const docsSiteDescription =
  'Curated public documentation for setup, operations, CLI usage, MCP access, planning, and document contracts.';

export const docsGroups: DocsGroup[] = [
  {
    id: 'start-here',
    title: 'Start Here',
    description: 'Primary entry points for setup, runtime choice, and the shared docs viewer.',
    entries: [
      {
        slug: 'setup',
        title: 'Setup',
        description: 'Install, configure, and troubleshoot a local CCDash environment.',
        path: 'guides/setup.md',
      },
      {
        slug: 'runtime-storage-and-performance-quickstart',
        title: 'Runtime, Storage, and Performance Quickstart',
        description: 'Pick the right runtime posture for local and hosted deployments.',
        path: 'guides/runtime-storage-and-performance-quickstart.md',
      },
      {
        slug: 'storage-profiles-guide',
        title: 'Storage Profiles Guide',
        description: 'Understand the local, hybrid, and hosted storage profiles.',
        path: 'guides/storage-profiles-guide.md',
      },
      {
        slug: 'shared-content-viewer',
        title: 'Shared Content Viewer',
        description: 'Review the unified viewer that renders docs, plans, and other content types.',
        path: 'guides/shared-content-viewer.md',
      },
    ],
  },
  {
    id: 'guides',
    title: 'Operational Guides',
    description: 'Guides for CLI, MCP, telemetry, planning, and session intelligence.',
    entries: [
      {
        slug: 'cli-user-guide',
        title: 'CLI User Guide',
        description: 'Use the CLI for common CCDash workflows.',
        path: 'guides/cli-user-guide.md',
      },
      {
        slug: 'standalone-cli-guide',
        title: 'Standalone CLI Guide',
        description: 'Run CCDash as a standalone command-line tool.',
        path: 'guides/standalone-cli-guide.md',
      },
      {
        slug: 'mcp-setup-guide',
        title: 'MCP Setup Guide',
        description: 'Connect CCDash to MCP-enabled tooling and workflows.',
        path: 'guides/mcp-setup-guide.md',
      },
      {
        slug: 'operations-panel',
        title: 'Operations Panel',
        description: 'Operate sync, telemetry, and runtime surfaces from the dashboard.',
        path: 'guides/operations-panel.md',
      },
      {
        slug: 'telemetry-exporter-guide',
        title: 'Telemetry Exporter Guide',
        description: 'Configure export pipelines and delivery checks.',
        path: 'guides/telemetry-exporter-guide.md',
      },
      {
        slug: 'agentic-sdlc-intelligence',
        title: 'Agentic SDLC Intelligence',
        description: 'Interpret delivery intelligence derived from agent sessions.',
        path: 'guides/agentic-sdlc-intelligence.md',
      },
      {
        slug: 'session-usage-attribution',
        title: 'Session Usage Attribution',
        description: 'Track where usage attribution is available and how it degrades.',
        path: 'guides/session-usage-attribution.md',
      },
      {
        slug: 'document-entity-and-linking',
        title: 'Document Entity and Linking',
        description: 'Understand how documents are indexed and linked across the app.',
        path: 'guides/document-entity-and-linking.md',
      },
    ],
  },
  {
    id: 'reference',
    title: 'Reference',
    description: 'Schemas and supporting references for the docs surface.',
    entries: [
      {
        slug: 'document-frontmatter-readme',
        title: 'Document Frontmatter Schema',
        description: 'Read the canonical frontmatter contracts used across markdown docs.',
        path: 'schemas/document_frontmatter/README.md',
      },
      {
        slug: 'document-frontmatter-mapping',
        title: 'Document and Feature Mapping',
        description: 'See how document metadata maps to feature and artifact surfaces.',
        path: 'schemas/document_frontmatter/document-and-feature-mapping.md',
      },
      {
        slug: 'docs-readme',
        title: 'Docs README',
        description: 'Review the current docs organization and editorial guidance.',
        path: 'README.md',
      },
    ],
  },
];

export const docsNavigation = docsGroups.map(({ id, title, description, entries }) => ({
  id,
  title,
  description,
  items: entries.map(({ slug, title: itemTitle, path, description: itemDescription }) => ({
    slug,
    title: itemTitle,
    path: docsPublicPath(path),
    description: itemDescription,
  })),
}));

export const docsEntryBySlug = new Map(
  docsGroups.flatMap((group) => group.entries.map((entry) => [entry.slug, entry] as const)),
);
