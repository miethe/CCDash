import React from 'react';
import { BookOpen, ChevronRight, FileText, Layers3 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';

import { Surface } from '../ui/surface';
import { Button } from '../ui/button';
import { cn } from '../../lib/utils';
import {
  type DocsEntry,
  type DocsPath,
  docsGroups,
  docsPublicPath,
  docsSiteDescription,
  docsSiteTitle,
} from '../../src/docs/docsContent';

const sectionIcons = {
  'start-here': BookOpen,
  guides: FileText,
  reference: Layers3,
} as const;

const docsModules = import.meta.glob('/docs/**/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const readDoc = (path: DocsPath): string => docsModules[docsPublicPath(path)] || '';

export const DocsPage: React.FC = () => {
  const firstEntry = docsGroups[0]?.entries[0];
  const [selectedSlug, setSelectedSlug] = React.useState(firstEntry?.slug ?? '');
  const selectedGroup =
    docsGroups.find((group) => group.entries.some((entry) => entry.slug === selectedSlug)) ?? docsGroups[0];
  const selectedEntry: DocsEntry | undefined = selectedGroup?.entries.find((entry) => entry.slug === selectedSlug) ?? firstEntry;
  const content = selectedEntry ? readDoc(selectedEntry.path) : '';
  const pageCount = docsGroups.reduce((count, group) => count + group.entries.length, 0);

  return (
    <div className="flex min-h-screen flex-col gap-4 bg-app-background p-4 text-app-foreground">
      <Surface tone="panel" padding="none" shadow="sm" className="shrink-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-panel-border px-4 py-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Docs</div>
            <h1 className="text-lg font-semibold text-panel-foreground">{docsSiteTitle}</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{docsSiteDescription}</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Link to="/" className="rounded-md border border-panel-border bg-surface-muted px-2 py-1 transition hover:border-focus hover:text-panel-foreground">
              Landing
            </Link>
            <Link to="/dashboard" className="rounded-md border border-panel-border bg-surface-muted px-2 py-1 transition hover:border-focus hover:text-panel-foreground">
              App
            </Link>
            <span className="rounded-md border border-panel-border bg-surface-muted px-2 py-1">{pageCount} pages</span>
            <span className="rounded-md border border-panel-border bg-surface-muted px-2 py-1">Markdown rendered locally</span>
          </div>
        </div>
        <div className="grid min-h-0 gap-0 lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="min-h-0 border-b border-panel-border lg:border-b-0 lg:border-r">
            <div className="max-h-[34rem] overflow-auto p-3">
              {docsGroups.map((group) => {
                const Icon = sectionIcons[group.id] || BookOpen;
                return (
                  <div key={group.id} className="mb-4 last:mb-0">
                    <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      <Icon size={12} />
                      {group.title}
                    </div>
                    <p className="mb-2 text-xs leading-5 text-muted-foreground">{group.description}</p>
                    <div className="space-y-1">
                      {group.entries.map((entry) => {
                        const active = entry.slug === selectedEntry?.slug;
                        return (
                          <Button
                            key={entry.slug}
                            type="button"
                            variant={active ? 'panel' : 'ghost'}
                            size="sm"
                            onClick={() => setSelectedSlug(entry.slug)}
                            className={cn(
                              'h-auto w-full justify-start whitespace-normal px-3 py-2 text-left',
                              active && 'border-focus/40 bg-hover/60',
                            )}
                          >
                            <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
                              <span className="flex w-full items-center gap-2">
                                <span className="min-w-0 flex-1 truncate text-sm">{entry.title}</span>
                                <ChevronRight size={14} className={cn('shrink-0 transition-opacity', active ? 'opacity-100' : 'opacity-0')} />
                              </span>
                              <span className="text-xs font-normal text-muted-foreground">{entry.description}</span>
                            </span>
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </aside>
          <main className="min-h-0 p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded-md border border-panel-border bg-surface-muted px-2 py-1">{selectedGroup?.title ?? 'Overview'}</span>
              <span className="rounded-md border border-panel-border bg-surface-muted px-2 py-1">{selectedEntry?.path ?? 'README.md'}</span>
            </div>
            {selectedEntry?.description && (
              <div className="mb-4 rounded-lg border border-info-border bg-info/10 px-4 py-3 text-sm text-info-foreground">
                {selectedEntry.description}
              </div>
            )}
            <Surface tone="overlay" padding="none" shadow="viewer" className="min-h-[28rem] overflow-hidden">
              <div className="max-h-[calc(100vh-14rem)] overflow-auto p-5">
                <div className="ccdash-markdown text-sm text-panel-foreground">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {content || '# Documentation\n\nNo markdown content was found for this entry.'}
                  </ReactMarkdown>
                </div>
              </div>
            </Surface>
          </main>
        </div>
      </Surface>
    </div>
  );
};
