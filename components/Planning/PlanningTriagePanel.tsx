/**
 * T3-001: Triage Inbox Panel
 * T3-002: Triage action buttons — kind-mapped CTAs with toast + refresh
 *
 * Filterable triage surface for mismatches, blockers, stale features,
 * and ready-to-promote features. Derived client-side from ProjectPlanningSummary
 * featureSummaries — no separate endpoint required.
 *
 * Filter tabs: All / Blocked / Mismatches / Stale / Ready-to-promote
 * Row anatomy: 3px severity bar · kind badge · feature slug · title · action button + chevron
 * Title click → navigate to planningFeatureModalHref (existing modal route)
 * Empty state: green check + "Nothing to triage"
 *
 * Action button behaviour (T3-002):
 * - kind → label: blocked→"Remediate" | mismatch→"Reconcile" | stale→"Resume shaping" | ready→"Promote"
 * - Click: button disabled+spinner for ~800ms, fires toast, calls onRefresh
 * - Actual remediation logic is a stub ("Coming in v2")
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Loader2 } from 'lucide-react';

import type { ProjectPlanningSummary } from '../../types';
import { planningFeatureModalHref } from '../../services/planningRoutes';
import { Panel, Btn, BtnGhost, Dot } from './primitives';

// ── Toast (scoped to this panel) ──────────────────────────────────────────────

interface ToastEntry {
  id: string;
  message: string;
}

function useTriageToast() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timersRef = useRef<number[]>([]);

  const push = useCallback((message: string) => {
    const id = `triage-toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev, { id, message }].slice(-3));
    const timer = window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 2800);
    timersRef.current.push(timer);
  }, []);

  useEffect(() => {
    return () => {
      timersRef.current.forEach((id) => window.clearTimeout(id));
      timersRef.current = [];
    };
  }, []);

  return { toasts, push };
}

// ── Triage item derivation ────────────────────────────────────────────────────

type TriageKind = 'blocked' | 'mismatch' | 'stale' | 'ready';
type TriageSeverity = 'high' | 'medium' | 'low' | 'info';

export interface TriageItem {
  id: string;
  featureId: string;
  slug: string;
  title: string;
  kind: TriageKind;
  severity: TriageSeverity;
  reason: string;
}

const KIND_LABEL: Record<TriageKind, string> = {
  blocked: 'BLOCKED',
  mismatch: 'MISMATCH',
  stale: 'STALE',
  ready: 'READY',
};

/** Primary action label per triage kind (T3-002). */
const KIND_ACTION_LABEL: Record<TriageKind, string> = {
  blocked: 'Remediate',
  mismatch: 'Reconcile',
  stale: 'Resume shaping',
  ready: 'Promote',
};

/** Toast message template per triage kind. */
function actionToastMessage(kind: TriageKind, slug: string): string {
  switch (kind) {
    case 'blocked':
      return `Remediate started for ${slug} — coming in v2.`;
    case 'mismatch':
      return `Reconcile started for ${slug} — coming in v2.`;
    case 'stale':
      return `Resume shaping queued for ${slug} — coming in v2.`;
    case 'ready':
      return `Promote initiated for ${slug} — coming in v2.`;
  }
}

const SEVERITY_COLOR: Record<TriageSeverity, string> = {
  high: 'var(--err)',
  medium: 'var(--warn)',
  low: 'var(--info)',
  info: 'var(--spec)',
};

/**
 * Derive triage items from the planning summary's featureSummaries.
 * A feature can appear multiple times (once per applicable condition).
 * Priority ordering: blocked > mismatch > stale > ready.
 */
function deriveTriageItems(summary: ProjectPlanningSummary): TriageItem[] {
  const items: TriageItem[] = [];
  const staleSet = new Set(summary.staleFeatureIds ?? []);

  for (const f of summary.featureSummaries) {
    const status = f.effectiveStatus ?? f.rawStatus ?? '';

    // Blocked
    if (
      f.hasBlockedPhases ||
      status === 'blocked' ||
      summary.blockedFeatureIds?.includes(f.featureId)
    ) {
      items.push({
        id: `${f.featureId}:blocked`,
        featureId: f.featureId,
        slug: f.featureId,
        title: f.featureName,
        kind: 'blocked',
        severity: 'high',
        reason: f.hasBlockedPhases
          ? `${f.blockedPhaseCount} phase${f.blockedPhaseCount !== 1 ? 's' : ''} blocked`
          : 'Feature is blocked',
      });
    }

    // Mismatch
    if (f.isMismatch) {
      items.push({
        id: `${f.featureId}:mismatch`,
        featureId: f.featureId,
        slug: f.featureId,
        title: f.featureName,
        kind: 'mismatch',
        severity: 'medium',
        reason: f.mismatchState
          ? `Status mismatch: ${f.mismatchState}`
          : 'Raw / effective status diverge',
      });
    }

    // Stale
    if (staleSet.has(f.featureId)) {
      items.push({
        id: `${f.featureId}:stale`,
        featureId: f.featureId,
        slug: f.featureId,
        title: f.featureName,
        kind: 'stale',
        severity: 'low',
        reason: 'No recent activity detected',
      });
    }

    // Ready to promote
    if (status === 'ready' || status === 'approved') {
      items.push({
        id: `${f.featureId}:ready`,
        featureId: f.featureId,
        slug: f.featureId,
        title: f.featureName,
        kind: 'ready',
        severity: 'info',
        reason: status === 'approved' ? 'Approved — promote to in-progress' : 'Ready to promote',
      });
    }
  }

  return items;
}

// ── Filter tab strip ──────────────────────────────────────────────────────────

type FilterKey = 'all' | TriageKind;

interface TabDef {
  key: FilterKey;
  label: string;
  count: number;
}

function TabStrip({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: FilterKey;
  onChange: (k: FilterKey) => void;
}) {
  return (
    <div
      className="flex gap-0.5"
      style={{ padding: '10px 14px 0', borderBottom: '1px solid var(--line-1)' }}
      role="tablist"
      aria-label="Triage filter tabs"
    >
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={isActive}
            type="button"
            onClick={() => onChange(t.key)}
            style={{
              padding: '8px 12px',
              fontSize: 12,
              fontWeight: 500,
              background: 'transparent',
              border: 'none',
              color: isActive ? 'var(--ink-0)' : 'var(--ink-2)',
              borderBottom: isActive ? '2px solid var(--brand)' : '2px solid transparent',
              marginBottom: -1,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontFamily: 'inherit',
              transition: 'color 120ms ease',
            }}
          >
            {t.label}
            <span
              className="planning-tnum planning-mono"
              style={{
                padding: '1px 6px',
                borderRadius: 8,
                fontSize: 10,
                background: isActive
                  ? 'color-mix(in oklab, var(--brand) 20%, transparent)'
                  : 'var(--bg-3)',
                color: isActive ? 'var(--brand)' : 'var(--ink-2)',
                transition: 'background 120ms ease, color 120ms ease',
              }}
            >
              {t.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ── Triage action button ──────────────────────────────────────────────────────

/**
 * T3-002: Action button with 800ms disabled-spinner state.
 * Fires toast + calls onRefresh; actual logic is stubbed for v2.
 */
function TriageActionBtn({
  item,
  onToast,
  onRefresh,
}: {
  item: TriageItem;
  onToast: (message: string) => void;
  onRefresh?: () => void;
}) {
  const [pending, setPending] = useState(false);
  const timerRef = useRef<number | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  const handleClick = useCallback(() => {
    if (pending) return;
    setPending(true);

    // Fire toast immediately
    onToast(actionToastMessage(item.kind, item.slug));

    // Trigger refresh if wired
    onRefresh?.();

    // Reset button after ~800ms
    timerRef.current = window.setTimeout(() => {
      setPending(false);
      timerRef.current = null;
    }, 800);
  }, [pending, item.kind, item.slug, onToast, onRefresh]);

  const label = KIND_ACTION_LABEL[item.kind];

  return (
    <Btn
      size="xs"
      type="button"
      disabled={pending}
      onClick={handleClick}
      aria-label={`${label} ${item.title}`}
      aria-busy={pending}
      style={{
        minWidth: 76,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        transition: 'opacity 120ms ease',
        opacity: pending ? 0.65 : 1,
      }}
    >
      {pending ? (
        <>
          <Loader2
            size={10}
            aria-hidden="true"
            style={{ animation: 'spin 600ms linear infinite', flexShrink: 0 }}
          />
          <span>{label}</span>
        </>
      ) : (
        label
      )}
    </Btn>
  );
}

// ── Triage row ────────────────────────────────────────────────────────────────

function TriageRow({
  item,
  onSelectFeature,
  onToast,
  onRefresh,
}: {
  item: TriageItem;
  onSelectFeature: (featureId: string) => void;
  onToast: (message: string) => void;
  onRefresh?: () => void;
}) {
  const severityColor = SEVERITY_COLOR[item.severity];
  const kindLabel = KIND_LABEL[item.kind];

  return (
    <div
      data-testid={`triage-row-${item.id}`}
      style={{
        display: 'grid',
        gridTemplateColumns: '6px 110px 1fr auto',
        alignItems: 'center',
        gap: 14,
        padding: '12px 14px',
        borderBottom: '1px solid var(--line-1)',
      }}
    >
      {/* 3px severity bar */}
      <div
        aria-hidden="true"
        style={{
          width: 3,
          height: 24,
          background: severityColor,
          borderRadius: 2,
          flexShrink: 0,
        }}
      />

      {/* Kind badge + slug */}
      <div style={{ minWidth: 0 }}>
        <div
          className="planning-mono planning-caps"
          style={{ fontSize: 10, color: severityColor, letterSpacing: '0.12em' }}
        >
          {kindLabel}
        </div>
        <div
          className="planning-mono"
          style={{
            fontSize: 10.5,
            color: 'var(--ink-3)',
            marginTop: 2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={item.slug}
        >
          {item.slug}
        </div>
      </div>

      {/* Title + reason */}
      <div style={{ minWidth: 0 }}>
        <button
          type="button"
          onClick={() => onSelectFeature(item.featureId)}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            color: 'var(--ink-0)',
            fontSize: 13,
            fontWeight: 500,
            textAlign: 'left',
            cursor: 'pointer',
            fontFamily: 'inherit',
            maxWidth: '100%',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            display: 'block',
          }}
        >
          {item.title}
        </button>
        <div
          style={{
            fontSize: 11.5,
            color: 'var(--ink-3)',
            marginTop: 2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {item.reason}
        </div>
      </div>

      {/* Action button + chevron */}
      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
        <TriageActionBtn item={item} onToast={onToast} onRefresh={onRefresh} />
        <BtnGhost
          size="xs"
          aria-label={`Open ${item.title}`}
          onClick={() => onSelectFeature(item.featureId)}
        >
          <ChevronRight size={12} />
        </BtnGhost>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function TriageEmptyState() {
  return (
    <div
      style={{
        padding: '40px 16px',
        textAlign: 'center',
        color: 'var(--ink-3)',
        fontSize: 13,
      }}
      data-testid="triage-empty-state"
    >
      <div
        style={{
          fontSize: 24,
          marginBottom: 8,
          color: 'var(--ok)',
          lineHeight: 1,
        }}
        aria-hidden="true"
      >
        ✓
      </div>
      Nothing to triage.
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface PlanningTriagePanelProps {
  summary: ProjectPlanningSummary;
  onSelectFeature?: (featureId: string) => void;
  /** Called after a triage action button is clicked to trigger a planning summary refresh. */
  onRefresh?: () => void;
}

export function PlanningTriagePanel({
  summary,
  onSelectFeature,
  onRefresh,
}: PlanningTriagePanelProps) {
  const navigate = useNavigate();
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all');
  const { toasts, push: pushToast } = useTriageToast();

  const items = useMemo(() => deriveTriageItems(summary), [summary]);

  const handleSelectFeature = useMemo(
    () =>
      onSelectFeature ??
      ((featureId: string) => navigate(planningFeatureModalHref(featureId))),
    [onSelectFeature, navigate],
  );

  const tabs: TabDef[] = useMemo(
    () => [
      { key: 'all', label: 'All', count: items.length },
      { key: 'blocked', label: 'Blocked', count: items.filter((i) => i.kind === 'blocked').length },
      { key: 'mismatch', label: 'Mismatches', count: items.filter((i) => i.kind === 'mismatch').length },
      { key: 'stale', label: 'Stale', count: items.filter((i) => i.kind === 'stale').length },
      { key: 'ready', label: 'Ready to promote', count: items.filter((i) => i.kind === 'ready').length },
    ],
    [items],
  );

  const filtered = useMemo(
    () => (activeFilter === 'all' ? items : items.filter((i) => i.kind === activeFilter)),
    [items, activeFilter],
  );

  return (
    <>
      <Panel
        data-testid="planning-triage-panel"
        style={{ overflow: 'hidden', padding: 0 }}
      >
        {/* Panel heading */}
        <div
          className="flex items-center justify-between"
          style={{ padding: '14px 14px 0' }}
        >
          <h2
            className="planning-serif"
            style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--ink-0)' }}
          >
            Triage Inbox
          </h2>
          <span
            className="planning-tnum planning-mono"
            style={{
              fontSize: 10.5,
              color: items.length > 0 ? 'var(--warn)' : 'var(--ok)',
              background: items.length > 0
                ? 'color-mix(in oklab, var(--warn) 14%, transparent)'
                : 'color-mix(in oklab, var(--ok) 14%, transparent)',
              border: `1px solid color-mix(in oklab, ${items.length > 0 ? 'var(--warn)' : 'var(--ok)'} 28%, transparent)`,
              borderRadius: 10,
              padding: '2px 7px',
            }}
          >
            {items.length} {items.length === 1 ? 'item' : 'items'}
          </span>
        </div>

        {/* Filter tabs */}
        <TabStrip tabs={tabs} active={activeFilter} onChange={setActiveFilter} />

        {/* Row list */}
        <div style={{ maxHeight: 380, overflow: 'auto' }}>
          {filtered.length === 0 ? (
            <TriageEmptyState />
          ) : (
            filtered.map((item) => (
              <TriageRow
                key={item.id}
                item={item}
                onSelectFeature={handleSelectFeature}
                onToast={pushToast}
                onRefresh={onRefresh}
              />
            ))
          )}
        </div>
      </Panel>

      {/* Panel-scoped toasts */}
      {toasts.length > 0 && (
        <div
          aria-live="polite"
          aria-atomic="false"
          className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2"
        >
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className="planning-mono pointer-events-auto flex items-center gap-2.5 rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--brand)_40%,var(--line-2))] bg-[color:var(--bg-1)] px-4 py-2.5 text-[11.5px] text-[color:var(--ink-0)] shadow-[0_14px_40px_rgba(0,0,0,0.45)]"
              style={{ backdropFilter: 'blur(8px)' }}
            >
              <Dot tone="var(--brand)" />
              {toast.message}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
