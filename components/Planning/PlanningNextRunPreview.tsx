/**
 * PASB-403: PlanningNextRunPreview
 * PASB-404: Launch Sheet Alignment
 *
 * Displays a scaffolded CLI command + prompt skeleton for the next planning
 * run of a feature. Fetches from the backend next-run-preview endpoint and
 * presents two copyable code sections plus context reference chips and
 * advisory warnings.
 *
 * This component is COPY/PREVIEW ONLY. It intentionally has no "Launch" or
 * "Execute" buttons. To launch a batch, use PlanningLaunchSheet via the
 * "Open Launch Sheet" affordance below the command section.
 *
 * Props:
 *   featureId           — required; the feature to preview
 *   phaseNumber         — optional; scopes the preview to a specific phase
 *   selectedCards       — optional; when supplied, triggers the POST variant of
 *                         the endpoint so selected sessions inform the skeleton
 *   onClose             — optional; called when the user dismisses the panel
 *   onOpenLaunchSheet   — optional; called when the user requests to open the
 *                         Launch Sheet for actual execution
 *   recommendedProvider — optional; provider label shown in the launch context
 *                         strip (use the display label, e.g. "Claude Code")
 *   recommendedModel    — optional; model name shown in the launch context strip
 *   recommendedWorktree — optional; worktree path shown in the launch context strip
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
  ExternalLink,
  Eye,
  Cpu,
  GitBranch,
  Server,
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

// ── Launch context strip ──────────────────────────────────────────────────────
//
// Mirrors the label/styling conventions used in PlanningLaunchSheet:
//   - Provider: display label (e.g. "Claude Code") not raw provider string
//   - Model: raw model string, same as the launch sheet model select option text
//   - Worktree: "branch · path" format matching the worktree select option text
//
// All three fields are optional — if none are provided the strip is omitted.

interface LaunchContextStripProps {
  provider?: string;
  model?: string;
  worktreeBranch?: string;
  worktreePath?: string;
  onOpenLaunchSheet?: () => void;
}

function LaunchContextStrip({
  provider,
  model,
  worktreeBranch,
  worktreePath,
  onOpenLaunchSheet,
}: LaunchContextStripProps) {
  const hasAnyMeta = provider || model || worktreeBranch || worktreePath;
  if (!hasAnyMeta && !onOpenLaunchSheet) return null;

  return (
    <div
      className="rounded border px-3 py-2.5 space-y-2"
      style={{
        borderColor: 'color-mix(in oklab, var(--brand) 18%, var(--line-1))',
        background: 'color-mix(in oklab, var(--brand) 4%, var(--bg-0, var(--bg-1)))',
      }}
    >
      {/* Meta row — only render when we have at least one value */}
      {hasAnyMeta && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {provider && (
            <div className="flex items-center gap-1.5 min-w-0">
              <Server
                size={9}
                style={{ color: 'var(--ink-4)', flexShrink: 0 }}
                aria-hidden
              />
              <span
                className="planning-mono text-[9.5px] uppercase tracking-wide"
                style={{ color: 'var(--ink-4)' }}
              >
                Provider
              </span>
              {/* Label formatting matches PlanningLaunchSheet: p.label || p.provider */}
              <span
                className="planning-mono text-[9.5px] font-medium truncate"
                style={{ color: 'var(--ink-2)' }}
              >
                {provider}
              </span>
            </div>
          )}
          {model && (
            <div className="flex items-center gap-1.5 min-w-0">
              <Cpu
                size={9}
                style={{ color: 'var(--ink-4)', flexShrink: 0 }}
                aria-hidden
              />
              <span
                className="planning-mono text-[9.5px] uppercase tracking-wide"
                style={{ color: 'var(--ink-4)' }}
              >
                Model
              </span>
              <span
                className="planning-mono text-[9.5px] font-medium truncate"
                style={{ color: 'var(--ink-2)' }}
              >
                {model}
              </span>
            </div>
          )}
          {(worktreeBranch || worktreePath) && (
            <div className="flex items-center gap-1.5 min-w-0">
              <GitBranch
                size={9}
                style={{ color: 'var(--ink-4)', flexShrink: 0 }}
                aria-hidden
              />
              <span
                className="planning-mono text-[9.5px] uppercase tracking-wide"
                style={{ color: 'var(--ink-4)' }}
              >
                Worktree
              </span>
              {/* Format mirrors PlanningLaunchSheet worktree select: "branch · path" */}
              <span
                className="planning-mono text-[9.5px] font-medium truncate"
                style={{ color: 'var(--ink-2)' }}
              >
                {[worktreeBranch, worktreePath].filter(Boolean).join(' · ')}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Open Launch Sheet affordance */}
      {onOpenLaunchSheet && (
        <div className="flex items-center justify-between gap-2">
          <span
            className="planning-mono text-[9px]"
            style={{ color: 'var(--ink-4)' }}
          >
            Configure provider, model, and worktree before launching.
          </span>
          <button
            type="button"
            onClick={onOpenLaunchSheet}
            className={cn(
              'inline-flex items-center gap-1 shrink-0',
              'rounded-[var(--radius-sm)] border px-2 py-1',
              'planning-mono text-[9px] font-medium transition-all duration-150',
              'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--brand)]',
            )}
            style={{
              borderColor: 'color-mix(in oklab, var(--brand) 35%, var(--line-1))',
              color: 'var(--brand)',
              background: 'color-mix(in oklab, var(--brand) 8%, transparent)',
            }}
            aria-label="Open Launch Sheet to configure and execute this batch"
            data-testid="next-run-open-launch-sheet-btn"
          >
            <ExternalLink size={8} aria-hidden />
            Open Launch Sheet
          </button>
        </div>
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
  /**
   * Called when the user clicks "Open Launch Sheet". Wire this up to open
   * PlanningLaunchSheet for actual execution. If omitted, the affordance
   * link is not rendered.
   */
  onOpenLaunchSheet?: () => void;
  /**
   * Recommended provider display label to show in the launch context strip.
   * Use the human-readable label (e.g. "Claude Code"), matching PlanningLaunchSheet's
   * `p.label || p.provider` convention.
   */
  recommendedProvider?: string;
  /**
   * Recommended model name to show in the launch context strip.
   * Raw model string — same text as the model select option in PlanningLaunchSheet.
   */
  recommendedModel?: string;
  /**
   * Recommended worktree branch for the launch context strip.
   * Combined with recommendedWorktreePath as "branch · path" — matching
   * PlanningLaunchSheet's worktree select option format.
   */
  recommendedWorktreeBranch?: string;
  /**
   * Recommended worktree path for the launch context strip.
   */
  recommendedWorktreePath?: string;
}

// ── Main component ────────────────────────────────────────────────────────────

export function PlanningNextRunPreview({
  featureId,
  phaseNumber,
  selectedCards,
  onClose,
  className,
  onOpenLaunchSheet,
  recommendedProvider,
  recommendedModel,
  recommendedWorktreeBranch,
  recommendedWorktreePath,
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

  // Determine whether to render the launch context strip.
  const hasLaunchContext =
    recommendedProvider ||
    recommendedModel ||
    recommendedWorktreeBranch ||
    recommendedWorktreePath ||
    onOpenLaunchSheet;

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
            <div className="flex items-center gap-2">
              <p
                className="truncate text-[12.5px] font-semibold leading-snug"
                style={{ color: 'var(--ink-0)' }}
              >
                Next-Run Preview
              </p>
              {/* Preview Only badge — always visible so users understand this is not an execution path */}
              <span
                className="planning-mono inline-flex items-center gap-1 shrink-0 rounded px-1.5 py-0.5 text-[8.5px] font-semibold uppercase tracking-wide leading-none"
                style={{
                  color: 'var(--ink-3)',
                  background: 'color-mix(in oklab, var(--ink-4) 12%, transparent)',
                  border: '1px solid color-mix(in oklab, var(--ink-4) 20%, transparent)',
                }}
                aria-label="Preview only — no execution"
                title="This panel generates commands for copy/paste only. Use the Launch Sheet to execute."
              >
                <Eye size={7} aria-hidden />
                Preview Only
              </span>
            </div>
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

              {/* Launch context strip — shown below the command block when context is available */}
              {hasLaunchContext && (
                <div className="mt-2.5">
                  <LaunchContextStrip
                    provider={recommendedProvider}
                    model={recommendedModel}
                    worktreeBranch={recommendedWorktreeBranch}
                    worktreePath={recommendedWorktreePath}
                    onOpenLaunchSheet={onOpenLaunchSheet}
                  />
                </div>
              )}
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

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <div
        className="px-4 py-2 space-y-0"
        style={{
          borderTop: '1px solid var(--line-1, #2d3347)',
          background: 'var(--bg-0, var(--bg-1))',
        }}
      >
        {/* Freshness metadata row — only when available */}
        {preview?.dataFreshness && (
          <div className="flex items-center justify-between gap-3 pb-1.5">
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

        {/* Disclaimer — always rendered so the copy-only contract is always visible */}
        <p
          className="planning-mono text-[9px] leading-relaxed"
          style={{ color: 'var(--ink-4)' }}
          data-testid="next-run-disclaimer"
        >
          This preview generates commands for copy/paste only. To execute, use the Launch Sheet.
        </p>
      </div>
    </aside>
  );
}
