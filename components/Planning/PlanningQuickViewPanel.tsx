/**
 * P14-001: PlanningQuickViewPanel
 * P14-003: QuickViewPromotionRow — promotion affordances (feature modal, doc modal, expanded page)
 *
 * Right-side slide-over panel opened when a tracker/intake row is clicked in
 * /planning. Accepts `children` as a content slot — feature vs. document
 * resolution is handled by P14-002.
 *
 * Anatomy:
 *   - Fixed overlay (inert when closed, visible when open)
 *   - Right-anchored panel with slide-in/out CSS transition
 *   - Trapped focus cycle (Tab / Shift-Tab stays inside the panel)
 *   - ESC + close-button dismiss
 *   - Focus restores to the invoking element on close
 *   - Optional `promotionFooter` slot rendered at the bottom of the panel
 *
 * Promotion (P14-003):
 *   Use <QuickViewPromotionRow> as the `promotionFooter` prop value.
 *   It provides keyboard-accessible buttons for:
 *     1. Open full feature modal  → planningRouteFeatureModalHref (in-route)
 *     2. Open full document modal → calls onOpenDocument callback
 *     3. Open expanded planning page → /planning/feature/:featureId
 *
 * Accessibility:
 *   - role="dialog", aria-modal="true"
 *   - aria-labelledby pointing to the panel heading
 *   - All interactive controls are keyboard-reachable
 */

import React, {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from 'react';
import { X, ExternalLink, Maximize2, FileText } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  planningRouteFeatureModalHref,
  planningFeatureDetailHref,
  type PlanningFeatureModalTab,
} from '@/services/planningRoutes';

// ── Focus trap helpers ────────────────────────────────────────────────────────

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  'details > summary',
].join(',');

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS)).filter(
    (el) => !el.closest('[inert]') && el.offsetParent !== null,
  );
}

// ── QuickViewPromotionRow (P14-003) ───────────────────────────────────────────

/**
 * Which surface type is shown in the quick-view panel.
 * Controls which promotion buttons are rendered.
 */
export type QuickViewContentKind = 'feature' | 'document' | 'none';

export interface QuickViewPromotionRowProps {
  /**
   * Discriminant — determines which promotion buttons appear.
   *   'feature'  → feature modal + expanded planning page
   *   'document' → document modal
   *   'none'     → nothing rendered (passthrough / unknown type)
   */
  kind: QuickViewContentKind;

  /** Feature ID — required when kind === 'feature' */
  featureId?: string;

  /**
   * Initial tab to open in the full feature modal.
   * Defaults to 'overview'.
   */
  featureModalTab?: PlanningFeatureModalTab;

  /**
   * Called when the "Open document modal" button is clicked.
   * The caller is responsible for opening `DocumentModal`.
   * Required when kind === 'document'.
   */
  onOpenDocument?: () => void;

  /**
   * Called just before any promotion navigation/action fires so the quick-view
   * panel can close itself. The panel consumer must wire this to `closePanel()`.
   */
  onClose?: () => void;
}

/**
 * Footer row of promotion actions inside the quick-view panel.
 *
 * Place this as the `promotionFooter` prop of `PlanningQuickViewPanel`.
 * P14-002 should supply `kind`, `featureId`, and `onOpenDocument` based on
 * which content type is currently shown.
 *
 * All buttons are standard `<button>` elements — keyboard accessible out of the
 * box and included in the panel's focus-trap cycle.
 */
export function QuickViewPromotionRow({
  kind,
  featureId,
  featureModalTab = 'overview',
  onOpenDocument,
  onClose,
}: QuickViewPromotionRowProps): JSX.Element | null {
  const navigate = useNavigate();

  const handleOpenFeatureModal = useCallback(() => {
    if (!featureId) return;
    onClose?.();
    navigate(planningRouteFeatureModalHref(featureId, featureModalTab));
  }, [featureId, featureModalTab, navigate, onClose]);

  const handleOpenExpandedPage = useCallback(() => {
    if (!featureId) return;
    onClose?.();
    navigate(planningFeatureDetailHref(featureId));
  }, [featureId, navigate, onClose]);

  const handleOpenDocument = useCallback(() => {
    onClose?.();
    onOpenDocument?.();
  }, [onClose, onOpenDocument]);

  if (kind === 'none') return null;

  return (
    <div
      className={cn(
        'flex shrink-0 flex-wrap items-center gap-2',
        'border-t px-5 py-3',
      )}
      style={{ borderColor: 'var(--line-1)' }}
      data-testid="quick-view-promotion-row"
    >
      {kind === 'feature' && featureId && (
        <>
          {/* Primary: open full feature modal in-route */}
          <button
            type="button"
            onClick={handleOpenFeatureModal}
            data-testid="promote-open-feature-modal"
            aria-label="Open full feature modal"
            className={cn(
              'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium',
              'border-[color:var(--brand)] bg-[color:var(--brand)]/10 text-[color:var(--brand)]',
              'transition-colors hover:bg-[color:var(--brand)]/20',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1',
              'focus-visible:ring-offset-[color:var(--bg-1)]',
            )}
          >
            <Maximize2 size={12} aria-hidden="true" />
            Open full view
          </button>

          {/* Secondary: navigate to expanded /planning/feature/:id page */}
          <button
            type="button"
            onClick={handleOpenExpandedPage}
            data-testid="promote-open-planning-page"
            aria-label="Open expanded planning page"
            className={cn(
              'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium',
              'border-[color:var(--line-2)] text-[color:var(--ink-2)]',
              'transition-colors hover:border-[color:var(--line-1)] hover:text-[color:var(--ink-0)]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1',
              'focus-visible:ring-offset-[color:var(--bg-1)]',
            )}
          >
            <ExternalLink size={12} aria-hidden="true" />
            Planning detail
          </button>
        </>
      )}

      {kind === 'document' && onOpenDocument && (
        <button
          type="button"
          onClick={handleOpenDocument}
          data-testid="promote-open-document-modal"
          aria-label="Open full document modal"
          className={cn(
            'flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium',
            'border-[color:var(--brand)] bg-[color:var(--brand)]/10 text-[color:var(--brand)]',
            'transition-colors hover:bg-[color:var(--brand)]/20',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1',
            'focus-visible:ring-offset-[color:var(--bg-1)]',
          )}
        >
          <FileText size={12} aria-hidden="true" />
          Open document
        </button>
      )}
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface PlanningQuickViewPanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children?: ReactNode;
  /**
   * Width class for the panel. Defaults to a responsive width suitable for
   * tracker/intake content.
   */
  widthClassName?: string;
  /**
   * P14-003: Optional promotion footer rendered below the content scroll area.
   * Pass a <QuickViewPromotionRow> element here. The panel positions it in a
   * sticky footer slot so it is always visible regardless of content length.
   */
  promotionFooter?: ReactNode;
}

// ── usePlanningQuickView ──────────────────────────────────────────────────────

export interface PlanningQuickViewState {
  open: boolean;
  title: string;
  /** Call this to open the panel, passing the title and the DOM element that
   *  triggered the action so focus can be restored on close. */
  openPanel: (title: string, triggerEl?: HTMLElement | null) => void;
  closePanel: () => void;
}

/**
 * Route-local hook for controlling PlanningQuickViewPanel state.
 *
 * The hook tracks the trigger element so the panel can restore focus when
 * it closes — matching the P14-001 requirement for focus restoration.
 *
 * Usage:
 *   const qv = usePlanningQuickView();
 *   // In JSX:
 *   <button onClick={(e) => qv.openPanel('My row title', e.currentTarget)}>…</button>
 *   <PlanningQuickViewPanel {...qv}>…children…</PlanningQuickViewPanel>
 */
export function usePlanningQuickView(): PlanningQuickViewState & {
  /** The element that last triggered the panel open — passed through to the
   *  panel via the `triggerRef` internal prop. Exposed so callers can wire it
   *  manually if needed. */
  triggerRef: React.MutableRefObject<HTMLElement | null>;
} {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const triggerRef = useRef<HTMLElement | null>(null);

  const openPanel = useCallback((nextTitle: string, triggerEl?: HTMLElement | null) => {
    triggerRef.current = triggerEl ?? null;
    setTitle(nextTitle);
    setOpen(true);
  }, []);

  const closePanel = useCallback(() => {
    setOpen(false);
  }, []);

  return { open, title, openPanel, closePanel, triggerRef };
}

// ── PlanningQuickViewPanel ────────────────────────────────────────────────────

/**
 * Right-side slide-over panel.
 *
 * Renders a backdrop + panel when `open` is true. The panel slides in from the
 * right using a CSS transition driven by the `data-open` attribute so the
 * transition plays both on entry and on exit (the node stays mounted until the
 * consumer unmounts it, which for quick-view is "never" since it is always in
 * the tree).
 *
 * P14-003: accepts an optional `promotionFooter` slot rendered in a sticky
 * footer below the scrollable content area.
 */
export function PlanningQuickViewPanel({
  open,
  onClose,
  title,
  children,
  widthClassName = 'w-full max-w-[480px] sm:max-w-[520px]',
  promotionFooter,
}: PlanningQuickViewPanelProps): JSX.Element {
  const headingId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // ── ESC to close ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [open, onClose]);

  // ── Focus management ─────────────────────────────────────────────────────────
  // Track the element that had focus when the panel opened so we can restore it.
  const priorFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open) {
      // Store the currently focused element before we steal focus.
      priorFocusRef.current = document.activeElement as HTMLElement | null;
      // Move focus into the panel — close button is always first focusable.
      requestAnimationFrame(() => {
        closeBtnRef.current?.focus();
      });
    } else {
      // Restore focus to the trigger element on close.
      requestAnimationFrame(() => {
        if (priorFocusRef.current && typeof priorFocusRef.current.focus === 'function') {
          priorFocusRef.current.focus();
          priorFocusRef.current = null;
        }
      });
    }
  }, [open]);

  // ── Focus trap ───────────────────────────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key !== 'Tab' || !panelRef.current) return;
      const focusable = getFocusableElements(panelRef.current);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [],
  );

  // ── Backdrop click ───────────────────────────────────────────────────────────
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  return (
    <>
      {/* ── Backdrop ────────────────────────────────────────────────────────── */}
      <div
        aria-hidden="true"
        onClick={handleBackdropClick}
        className={cn(
          'fixed inset-0 z-40 transition-opacity duration-200',
          open
            ? 'pointer-events-auto bg-black/50 opacity-100 backdrop-blur-[2px]'
            : 'pointer-events-none opacity-0',
        )}
      />

      {/* ── Slide-over panel ────────────────────────────────────────────────── */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        aria-hidden={!open}
        onKeyDown={handleKeyDown}
        className={cn(
          // Layout
          'fixed inset-y-0 right-0 z-50 flex flex-col',
          widthClassName,
          // Colours — use planning token surface
          'border-l border-[color:var(--line-1)] bg-[color:var(--bg-1)]',
          // Shadow for depth
          'shadow-[-8px_0_40px_rgba(0,0,0,0.5)]',
          // Slide transition
          'transition-transform duration-250 ease-[cubic-bezier(0.32,0.72,0,1)]',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
        // When closed, remove from the focus order entirely.
        // Cast through unknown to satisfy the React types for the experimental `inert` attribute.
        {...(!open ? ({ inert: true } as unknown as React.HTMLAttributes<HTMLDivElement>) : {})}
      >
        {/* ── Header ──────────────────────────────────────────────────────────── */}
        <div
          className="flex shrink-0 items-start justify-between gap-3 border-b px-5 py-4"
          style={{ borderColor: 'var(--line-1)' }}
        >
          <h2
            id={headingId}
            className="planning-serif min-w-0 flex-1 truncate text-base font-medium italic leading-snug"
            style={{ color: 'var(--ink-0)', fontSize: 'clamp(15px, 1.4vw, 17px)' }}
          >
            {title}
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Close quick view"
            className={cn(
              'shrink-0 rounded-md border p-1.5 transition-colors',
              'border-[color:var(--line-2)] text-[color:var(--ink-2)]',
              'hover:border-[color:var(--brand)] hover:text-[color:var(--ink-0)]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1',
              'focus-visible:ring-offset-[color:var(--bg-1)]',
            )}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        {/* ── Content slot ────────────────────────────────────────────────────── */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {children}
        </div>

        {/* ── Promotion footer (P14-003) ───────────────────────────────────────── */}
        {promotionFooter}
      </div>
    </>
  );
}
