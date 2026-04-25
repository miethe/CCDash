/**
 * PASB-403: PlanningNextRunPreview
 *
 * Displays a scaffolded CLI command + prompt skeleton for the next planning
 * run of a feature. Fetches from the backend next-run-preview endpoint and
 * presents two copyable code sections plus context reference chips and
 * advisory warnings.
 *
 * Props:
 *   featureId       — required; the feature to preview
 *   phaseNumber     — optional; scopes the preview to a specific phase
 *   selectedCards   — optional; when supplied, triggers the POST variant of the
 *                     endpoint so selected sessions inform the skeleton
 *   onClose         — optional; called when the user dismisses the panel
 *
 * Accessibility:
 *   - role="region" + aria-label, not role="dialog"
 *   - Copy buttons announce state via aria-label
 *   - Warning list uses role="list" + aria-label
 *   - Keyboard-navigable: all interactive elements reachable by Tab
 */

import { useEffect, useRef, useState, useCallback, type JSX } from 'react';
import {
  X,
  Terminal,
  FileText,
  Copy,
  Check,
  AlertTriangle,
  Tag,
  FileBox,
  GitCommit,
  Layers,
  RefreshCw,
  ClipboardList,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import type {
  PlanningAgentSessionCard,
  PlanningNextRunPreview as PlanningNextRunPreviewType,
  NextRunContextRef,
  PromptContextSelection,
} from '@/types';
import { getNextRunPreview, postNextRunPreview, PlanningApiError } from '@/services/planning';

// ── Helpers ────────────────────────────────────────────────────────────────────

function buildContextSelectionFromCards(
  cards: PlanningAgentSessionCard[],
): PromptContextSelection {
  return {
    sessionIds: cards.map((c) => c.sessionId),
    phaseRefs: [],
    taskRefs: [],
    artifactRefs: [],
    transcriptRefs: cards
      .filter((c) => Boolean(c.transcriptHref))
      .map((c) => c.transcriptHref as string),
  };
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="planning-mono mb-1.5 text-[9.5px] uppercase tracking-widest"
      style={{ color: 'var(--ink-4)' }}
    >
      {children}
    </p>
  );
}

function Divider() {
  return (
    <div
      className="w-full"
      style={{ height: 1, background: 'var(--line-1, #2d3347)' }}
      aria-hidden="true"
    />
  );
}

// ── Context ref chip ──────────────────────────────────────────────────────────

const REF_TYPE_ICON: Record<NextRunContextRef['refType'], JSX.Element> = {
  session: <GitCommit size={9} aria-hidden />,
  phase: <Layers size={9} aria-hidden />,
  task: <Tag size={9} aria-hidden />,
  artifact: <FileBox size={9} aria-hidden />,
  transcript: <FileText size={9} aria-hidden />,
};

const REF_TYPE_COLOR: Record<NextRunContextRef['refType'], string> = {
  session: 'var(--brand)',
  phase: 'var(--info, #60a5fa)',
  task: 'var(--ok)',
  artifact: 'var(--warn)',
  transcript: 'var(--ink-3)',
};

function ContextRefChip({ ref: r }: { ref: NextRunContextRef }) {
  const color = REF_TYPE_COLOR[r.refType];
  return (
    <span
      className="planning-mono inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9.5px] font-medium leading-none"
      style={{
        color,
        background: `color-mix(in oklab, ${color} 10%, transparent)`,
        border: `1px solid color-mix(in oklab, ${color} 25%, transparent)`,
      }}
      title={r.refPath ?? r.refId}
      aria-label={`${r.refType}: ${r.refLabel}`}
    >
      <span style={{ display: 'flex', color }}>
        {REF_TYPE_ICON[r.refType]}
      </span>
      <span className="max-w-[140px] truncate">{r.refLabel}</span>
    </span>
  );
}

// ── Copyable code block ───────────────────────────────────────────────────────

function CopyButton({
  text,
  label,
  className,
}: {
  text: string;
  label: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [text]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5',
        'planning-mono text-[9px] font-medium leading-none transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
        copied
          ? 'text-[color:var(--ok)]'
          : 'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
        className,
      )}
      aria-label={copied ? `${label} copied` : label}
      aria-pressed={copied}
    >
      {copied ? <Check size={9} aria-hidden /> : <Copy size={9} aria-hidden />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function CodeBlock({
  content,
  copyLabel,
  maxHeight = 160,
}: {
  content: string;
  copyLabel: string;
  maxHeight?: number;
}) {
  return (
    <div
      className="group relative rounded border"
      style={{ borderColor: 'var(--line-1)' }}
    >
      {/* Copy button — top-right corner */}
      <div className="absolute right-1.5 top-1.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <CopyButton text={content} label={copyLabel} />
      </div>
      <pre
        className="planning-mono overflow-x-auto overflow-y-auto p-3 text-[10px] leading-relaxed"
        style={{
          maxHeight,
          background: 'var(--bg-0, var(--bg-2))',
          color: 'var(--ink-2)',
          fontFamily: 'var(--font-mono, ui-monospace, monospace)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          borderRadius: 'inherit',
        }}
        tabIndex={0}
        aria-label={copyLabel}
      >
        {content}
      </pre>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-3 px-4 py-3">
      <div
        className="h-3 w-1/3 rounded"
        style={{ background: 'var(--bg-3)' }}
      />
      <div
        className="h-10 w-full rounded"
        style={{ background: 'var(--bg-3)' }}
      />
      <div
        className="h-3 w-1/3 rounded"
        style={{ background: 'var(--bg-3)' }}
      />
      <div
        className="h-24 w-full rounded"
        style={{ background: 'var(--bg-3)' }}
      />
    </div>
  );
}

// ── Error state ───────────────────────────────────────────────────────────────

function ErrorState({
  error,
  onRetry,
}: {
  error: Error;
  onRetry: () => void;
}) {
  const isNotFound = error instanceof PlanningApiError && error.status === 404;
  return (
    <div className="px-4 py-3 space-y-2">
      <div
        className="flex items-start gap-2 rounded border p-2.5"
        style={{
          borderColor: 'color-mix(in oklab, var(--err) 30%, transparent)',
          background: 'color-mix(in oklab, var(--err) 6%, transparent)',
        }}
      >
        <AlertTriangle
          size={11}
          style={{ color: 'var(--err)', flexShrink: 0, marginTop: 1 }}
          aria-hidden
        />
        <p className="planning-mono text-[10.5px]" style={{ color: 'var(--ink-2)' }}>
          {isNotFound
            ? 'Preview not available for this feature.'
            : 'Failed to load next-run preview.'}
        </p>
      </div>
      {!isNotFound && (
        <button
          type="button"
          onClick={onRetry}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2.5 py-1.5',
            'border border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
            'planning-mono text-[10px] text-[color:var(--ink-2)]',
            'transition-colors hover:border-[color:var(--line-2)] hover:text-[color:var(--ink-1)]',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
          )}
        >
          <RefreshCw size={10} aria-hidden />
          Retry
        </button>
      )}
    </div>
  );
}

// ── Props ──────────────────────────────────────────────────────────────────────

export interface PlanningNextRunPreviewProps {
  featureId: string;
  phaseNumber?: number;
  selectedCards?: PlanningAgentSessionCard[];
  onClose?: () => void;
  className?: string;
}

// ── Main component ────────────────────────────────────────────────────────────

export function PlanningNextRunPreview({
  featureId,
  phaseNumber,
  selectedCards,
  onClose,
  className,
}: PlanningNextRunPreviewProps): JSX.Element {
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [preview, setPreview] = useState<PlanningNextRunPreviewType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [fetchKey, setFetchKey] = useState(0);

  // Move initial focus to close button when panel mounts.
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, [featureId]);

  // Fetch preview — uses POST when selected cards are provided.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const doFetch =
      selectedCards && selectedCards.length > 0
        ? postNextRunPreview(
            featureId,
            buildContextSelectionFromCards(selectedCards),
            phaseNumber,
          )
        : getNextRunPreview(featureId, phaseNumber);

    doFetch
      .then((data) => {
        if (!cancelled) {
          setPreview(data);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [featureId, phaseNumber, selectedCards, fetchKey]);

  const handleRetry = useCallback(() => {
    setFetchKey((k) => k + 1);
  }, []);

  // "Copy All" merges command + prompt into a single clipboard payload.
  const handleCopyAll = useCallback(async () => {
    if (!preview) return;
    const combined = `# Command\n${preview.command}\n\n# Prompt\n${preview.promptSkeleton}`;
    await navigator.clipboard.writeText(combined);
  }, [preview]);

  const [allCopied, setAllCopied] = useState(false);
  const allCopyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopyAllClick = useCallback(async () => {
    await handleCopyAll();
    setAllCopied(true);
    if (allCopyTimerRef.current) clearTimeout(allCopyTimerRef.current);
    allCopyTimerRef.current = setTimeout(() => setAllCopied(false), 2000);
  }, [handleCopyAll]);

  useEffect(() => {
    return () => {
      if (allCopyTimerRef.current) clearTimeout(allCopyTimerRef.current);
    };
  }, []);

  const featureLabel = preview?.featureName ?? featureId;
  const phaseLabel =
    preview?.phaseNumber != null ? ` · Phase ${preview.phaseNumber}` : '';

  return (
    <aside
      className={cn(
        'planning-card-enter',
        'rounded-[var(--radius)] border',
        'bg-[color:var(--bg-1)]',
        'border-[color:var(--brand)]',
        'shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand)_20%,transparent),0_8px_24px_color-mix(in_oklab,var(--brand)_8%,transparent)]',
        'overflow-hidden',
        className,
      )}
      role="region"
      aria-label={`Next-run preview: ${featureLabel}${phaseLabel}`}
      data-testid="next-run-preview-panel"
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between gap-3 px-4 py-3"
        style={{
          borderBottom: '1px solid var(--line-1, #2d3347)',
          background: 'color-mix(in oklab, var(--brand) 5%, var(--bg-1))',
        }}
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <ClipboardList
            size={13}
            style={{ color: 'var(--brand)', flexShrink: 0 }}
            aria-hidden
          />
          <div className="min-w-0">
            <p
              className="truncate text-[12.5px] font-semibold leading-snug"
              style={{ color: 'var(--ink-0)' }}
            >
              Next-Run Preview
            </p>
            <p
              className="planning-mono mt-0.5 truncate text-[9.5px]"
              style={{ color: 'var(--ink-4)' }}
            >
              {featureLabel}{phaseLabel}
            </p>
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-1.5">
          {/* Copy All button */}
          {preview && (
            <button
              type="button"
              onClick={handleCopyAllClick}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1',
                'border planning-mono text-[9.5px] font-medium transition-all duration-150',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
                allCopied
                  ? 'border-[color:color-mix(in_oklab,var(--ok)_40%,var(--line-1))] text-[color:var(--ok)]'
                  : 'border-[color:var(--line-1)] text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
              )}
              aria-label={allCopied ? 'All copied' : 'Copy command and prompt'}
              aria-pressed={allCopied}
              data-testid="next-run-copy-all-btn"
            >
              {allCopied ? <Check size={10} aria-hidden /> : <Copy size={10} aria-hidden />}
              {allCopied ? 'Copied' : 'Copy All'}
            </button>
          )}

          {/* Close button */}
          {onClose && (
            <button
              ref={closeBtnRef}
              type="button"
              onClick={onClose}
              className={cn(
                'flex-shrink-0 rounded p-1 transition-colors',
                'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
                'border border-[color:var(--line-1)] hover:border-[color:var(--line-2)]',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
              )}
              aria-label="Close next-run preview"
              data-testid="next-run-preview-close-btn"
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────── */}
      <div className="overflow-y-auto" style={{ maxHeight: 560 }}>
        {loading && <LoadingSkeleton />}

        {!loading && error && (
          <ErrorState error={error} onRetry={handleRetry} />
        )}

        {!loading && !error && preview && (
          <div className="space-y-0">

            {/* 1. Command preview ──────────────────────────────────────── */}
            <section className="px-4 py-3">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <Terminal
                    size={10}
                    style={{ color: 'var(--ink-4)' }}
                    aria-hidden
                  />
                  <SectionLabel>Command</SectionLabel>
                </div>
                <CopyButton text={preview.command} label="Copy command" />
              </div>
              <CodeBlock
                content={preview.command}
                copyLabel="Copy command"
                maxHeight={80}
              />
            </section>

            <Divider />

            {/* 2. Prompt skeleton ──────────────────────────────────────── */}
            <section className="px-4 py-3">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <FileText
                    size={10}
                    style={{ color: 'var(--ink-4)' }}
                    aria-hidden
                  />
                  <SectionLabel>Prompt Skeleton</SectionLabel>
                </div>
                <CopyButton text={preview.promptSkeleton} label="Copy prompt" />
              </div>
              <CodeBlock
                content={preview.promptSkeleton}
                copyLabel="Copy prompt skeleton"
                maxHeight={200}
              />
            </section>

            {/* 3. Context references ───────────────────────────────────── */}
            {preview.contextRefs.length > 0 && (
              <>
                <Divider />
                <section className="px-4 py-3">
                  <SectionLabel>Context References</SectionLabel>
                  <div
                    className="flex flex-wrap gap-1.5"
                    role="list"
                    aria-label="Context references"
                  >
                    {preview.contextRefs.map((ref, i) => (
                      <span key={i} role="listitem">
                        <ContextRefChip ref={ref} />
                      </span>
                    ))}
                  </div>
                </section>
              </>
            )}

            {/* 4. Warnings ─────────────────────────────────────────────── */}
            {preview.warnings.length > 0 && (
              <>
                <Divider />
                <section className="px-4 py-3">
                  <SectionLabel>Warnings</SectionLabel>
                  <ul
                    className="space-y-1.5"
                    role="list"
                    aria-label="Preview warnings"
                    data-testid="next-run-warnings"
                  >
                    {preview.warnings.map((warn, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 rounded border p-2"
                        style={{
                          borderColor: 'color-mix(in oklab, var(--warn) 30%, transparent)',
                          background: 'color-mix(in oklab, var(--warn) 6%, transparent)',
                        }}
                        role="listitem"
                      >
                        <AlertTriangle
                          size={10}
                          style={{ color: 'var(--warn)', flexShrink: 0, marginTop: 1 }}
                          aria-hidden
                        />
                        <span
                          className="planning-mono text-[10px] leading-relaxed"
                          style={{ color: 'var(--ink-2)' }}
                        >
                          {warn}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Footer: freshness metadata ──────────────────────────────────── */}
      {preview?.dataFreshness && (
        <div
          className="flex items-center justify-between gap-3 px-4 py-2"
          style={{
            borderTop: '1px solid var(--line-1, #2d3347)',
            background: 'var(--bg-0, var(--bg-1))',
          }}
        >
          <span
            className="planning-mono text-[9px] tabular-nums"
            style={{ color: 'var(--ink-4)' }}
          >
            Data freshness: {preview.dataFreshness}
          </span>
          {preview.generatedAt && (
            <span
              className="planning-mono text-[9px] tabular-nums"
              style={{ color: 'var(--ink-4)' }}
            >
              Generated {new Date(preview.generatedAt).toLocaleTimeString()}
            </span>
          )}
        </div>
      )}
    </aside>
  );
}
