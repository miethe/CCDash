// P5-009: ⌘K command palette for the planning shell.
//
// Search endpoints used:
//   Features : GET /api/v1/features?view=cards&q=<query>  (listFeatureCards)
//   Documents: GET /api/documents?q=<query>&offset=0&limit=10
//
// Sessions search (GET /api/v1/sessions/search) is intentionally omitted for
// now — the two above cover the primary navigation surface.

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  KeyboardEvent,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { listFeatureCards } from '@/services/featureSurface';
import { apiRequestJson } from '@/services/apiClient';
import { planningFeatureDetailHref } from '@/services/planningRoutes';
import type { PlanDocument } from '@/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface FeatureResult {
  kind: 'feature';
  id: string;
  name: string;
  status: string;
  summary: string;
}

interface DocResult {
  kind: 'doc';
  id: string;
  title: string;
  docType: string;
  filePath: string;
}

type PaletteResult = FeatureResult | DocResult;

// ── Document search helper ────────────────────────────────────────────────────

async function searchDocuments(q: string): Promise<DocResult[]> {
  try {
    const url = `/api/documents?q=${encodeURIComponent(q)}&offset=0&limit=10`;
    const data = await apiRequestJson<{ items?: PlanDocument[] } | PlanDocument[]>(url);
    const items: PlanDocument[] = Array.isArray(data) ? data : ((data as { items?: PlanDocument[] }).items ?? []);
    return items.slice(0, 8).map((d) => ({
      kind: 'doc' as const,
      id: d.id ?? '',
      title: d.title ?? d.id ?? '',
      docType: d.docType ?? '',
      filePath: d.filePath ?? '',
    }));
  } catch {
    return [];
  }
}

// ── Feature search helper ─────────────────────────────────────────────────────

async function searchFeatures(q: string): Promise<FeatureResult[]> {
  try {
    const page = await listFeatureCards({ q, pageSize: 8 });
    return page.items.slice(0, 8).map((f) => ({
      kind: 'feature' as const,
      id: f.id,
      name: f.name,
      status: f.status,
      summary: f.summary ?? f.descriptionPreview ?? '',
    }));
  } catch {
    return [];
  }
}

// ── Status colour helper ──────────────────────────────────────────────────────

function statusDot(status: string): string {
  switch (status) {
    case 'active':
    case 'in_progress':
    case 'in-progress':
      return 'var(--ok)';
    case 'blocked':
      return 'var(--err)';
    case 'completed':
      return 'var(--brand)';
    default:
      return 'var(--ink-4)';
  }
}

// ── Group label ───────────────────────────────────────────────────────────────

function GroupLabel({ label }: { label: string }) {
  return (
    <div
      className="planning-mono px-3 pt-2 pb-1 text-[10px] font-medium uppercase tracking-widest"
      style={{ color: 'var(--ink-4)' }}
    >
      {label}
    </div>
  );
}

// ── Result row ────────────────────────────────────────────────────────────────

interface ResultRowProps {
  result: PaletteResult;
  active: boolean;
  onSelect: (r: PaletteResult) => void;
  onHover: () => void;
}

function ResultRow({ result, active, onSelect, onHover }: ResultRowProps) {
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (active) {
      ref.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [active]);

  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onSelect(result)}
      onMouseMove={onHover}
      className={cn(
        'flex w-full items-start gap-3 px-3 py-2 text-left transition-colors',
        active
          ? 'bg-[color:var(--bg-3)]'
          : 'hover:bg-[color:var(--bg-2)]',
      )}
    >
      {result.kind === 'feature' ? (
        <>
          <span
            aria-hidden="true"
            className="mt-[3px] flex-shrink-0 rounded-full"
            style={{
              width: 7,
              height: 7,
              background: statusDot(result.status),
              boxShadow: result.status === 'active' || result.status === 'in_progress'
                ? `0 0 6px ${statusDot(result.status)}`
                : undefined,
            }}
          />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span
              className="planning-mono truncate text-[12px] font-medium"
              style={{ color: 'var(--ink-0)' }}
            >
              {result.name}
            </span>
            {result.summary && (
              <span
                className="planning-mono truncate text-[11px]"
                style={{ color: 'var(--ink-3)' }}
              >
                {result.summary}
              </span>
            )}
          </span>
          <span
            className="planning-mono ml-auto flex-shrink-0 text-[10px] capitalize"
            style={{ color: 'var(--ink-4)' }}
          >
            {result.status.replace(/_/g, ' ')}
          </span>
        </>
      ) : (
        <>
          <span
            aria-hidden="true"
            className="planning-mono mt-[2px] flex-shrink-0 text-[10px]"
            style={{ color: 'var(--ink-4)' }}
          >
            ¶
          </span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span
              className="planning-mono truncate text-[12px] font-medium"
              style={{ color: 'var(--ink-0)' }}
            >
              {result.title}
            </span>
            {result.filePath && (
              <span
                className="planning-mono truncate text-[11px]"
                style={{ color: 'var(--ink-4)' }}
              >
                {result.filePath}
              </span>
            )}
          </span>
          <span
            className="planning-mono ml-auto flex-shrink-0 text-[10px]"
            style={{ color: 'var(--ink-4)' }}
          >
            {result.docType}
          </span>
        </>
      )}
    </button>
  );
}

// ── Empty / error states ──────────────────────────────────────────────────────

function EmptyState({ query }: { query: string }) {
  return (
    <div
      className="planning-mono px-4 py-8 text-center text-[12px]"
      style={{ color: 'var(--ink-4)' }}
    >
      {query.length < 2
        ? 'Type at least 2 characters to search…'
        : `No results for "${query}"`}
    </div>
  );
}

function ErrorState() {
  return (
    <div
      className="planning-mono px-4 py-8 text-center text-[12px]"
      style={{ color: 'var(--err)' }}
    >
      Search failed — please try again.
    </div>
  );
}

// ── CommandPalette ────────────────────────────────────────────────────────────

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

type SearchState = 'idle' | 'loading' | 'done' | 'error';

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState('');
  const [features, setFeatures] = useState<FeatureResult[]>([]);
  const [docs, setDocs] = useState<DocResult[]>([]);
  const [searchState, setSearchState] = useState<SearchState>('idle');
  const [activeIndex, setActiveIndex] = useState(0);

  const debounceRef = useRef<number | null>(null);

  // All results in display order — features first, then docs
  const allResults: PaletteResult[] = [...features, ...docs];

  // Reset when closed
  useEffect(() => {
    if (!open) {
      setQuery('');
      setFeatures([]);
      setDocs([]);
      setSearchState('idle');
      setActiveIndex(0);
    }
  }, [open]);

  // Focus input on open
  useEffect(() => {
    if (open) {
      // Wait one tick for the overlay to render
      const t = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  // Debounced search
  const runSearch = useCallback((q: string) => {
    if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);

    if (q.trim().length < 2) {
      setFeatures([]);
      setDocs([]);
      setSearchState('idle');
      return;
    }

    debounceRef.current = window.setTimeout(async () => {
      setSearchState('loading');
      try {
        const [featureResults, docResults] = await Promise.all([
          searchFeatures(q),
          searchDocuments(q),
        ]);
        setFeatures(featureResults);
        setDocs(docResults);
        setSearchState('done');
        setActiveIndex(0);
      } catch {
        setSearchState('error');
      }
    }, 220);
  }, []);

  const handleQueryChange = useCallback(
    (value: string) => {
      setQuery(value);
      runSearch(value);
    },
    [runSearch],
  );

  // Select a result
  const handleSelect = useCallback(
    (result: PaletteResult) => {
      onClose();
      if (result.kind === 'feature') {
        navigate(planningFeatureDetailHref(result.id));
      } else {
        // Navigate to document — best-effort via the document id in the hash
        navigate(`/docs?doc=${encodeURIComponent(result.id)}`);
      }
    },
    [navigate, onClose],
  );

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (allResults.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % allResults.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + allResults.length) % allResults.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const selected = allResults[activeIndex];
        if (selected) handleSelect(selected);
      }
    },
    [allResults, activeIndex, handleSelect, onClose],
  );

  // Backdrop click
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (!open) return null;

  const showEmpty =
    searchState === 'done' && features.length === 0 && docs.length === 0;

  return (
    /* Backdrop */
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(3px)' }}
    >
      {/* Panel */}
      <div
        className="flex w-full max-w-xl flex-col overflow-hidden rounded-[var(--radius)] border"
        style={{
          background: 'var(--bg-1)',
          borderColor: 'var(--line-2)',
          boxShadow: '0 32px 80px rgba(0,0,0,0.6)',
          maxHeight: '60vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input row */}
        <div
          className="flex items-center gap-2 border-b px-3 py-2.5"
          style={{ borderColor: 'var(--line-1)' }}
        >
          {/* Search icon or spinner */}
          {searchState === 'loading' ? (
            <svg
              className="h-4 w-4 flex-shrink-0 animate-spin"
              viewBox="0 0 16 16"
              fill="none"
              style={{ color: 'var(--brand)' }}
            >
              <circle
                cx="8"
                cy="8"
                r="6"
                stroke="currentColor"
                strokeWidth="2"
                strokeDasharray="28"
                strokeDashoffset="10"
              />
            </svg>
          ) : (
            <svg
              className="h-4 w-4 flex-shrink-0"
              viewBox="0 0 16 16"
              fill="none"
              style={{ color: 'var(--ink-3)' }}
            >
              <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10.5 10.5L13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          )}
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded={allResults.length > 0}
            aria-autocomplete="list"
            aria-controls="cmd-palette-results"
            autoComplete="off"
            spellCheck={false}
            placeholder="Search features, docs…"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onKeyDown={handleKeyDown}
            className="planning-mono min-w-0 flex-1 bg-transparent text-[13px] outline-none"
            style={{ color: 'var(--ink-0)' }}
          />
          <kbd
            className="planning-mono hidden rounded px-1.5 py-0.5 text-[10px] sm:block"
            style={{
              background: 'var(--bg-3)',
              color: 'var(--ink-3)',
              border: '1px solid var(--line-2)',
            }}
          >
            Esc
          </kbd>
        </div>

        {/* Results list */}
        <div
          id="cmd-palette-results"
          role="listbox"
          aria-label="Search results"
          className="overflow-y-auto"
          style={{ maxHeight: 'calc(60vh - 52px)' }}
        >
          {searchState === 'error' && <ErrorState />}

          {(searchState === 'idle' || (searchState === 'done' && showEmpty)) && (
            <EmptyState query={query} />
          )}

          {features.length > 0 && (
            <>
              <GroupLabel label="Features" />
              {features.map((f, i) => (
                <ResultRow
                  key={f.id}
                  result={f}
                  active={activeIndex === i}
                  onSelect={handleSelect}
                  onHover={() => setActiveIndex(i)}
                />
              ))}
            </>
          )}

          {docs.length > 0 && (
            <>
              <GroupLabel label="Documents" />
              {docs.map((d, i) => (
                <ResultRow
                  key={d.id}
                  result={d}
                  active={activeIndex === features.length + i}
                  onSelect={handleSelect}
                  onHover={() => setActiveIndex(features.length + i)}
                />
              ))}
            </>
          )}

          {/* Bottom breathing room */}
          {allResults.length > 0 && <div className="h-2" />}
        </div>

        {/* Footer hint */}
        {allResults.length > 0 && (
          <div
            className="planning-mono flex items-center gap-3 border-t px-3 py-2 text-[10.5px]"
            style={{ borderColor: 'var(--line-1)', color: 'var(--ink-4)' }}
          >
            <span>↑↓ navigate</span>
            <span style={{ color: 'var(--line-2)' }}>·</span>
            <span>↵ open</span>
            <span style={{ color: 'var(--line-2)' }}>·</span>
            <span>Esc close</span>
          </div>
        )}
      </div>
    </div>
  );
}
