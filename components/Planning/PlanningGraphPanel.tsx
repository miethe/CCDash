import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Clock,
  FolderSearch,
  Plus,
  RefreshCw,
} from 'lucide-react';

// Inject pulse-ring keyframe once into document head.
// Uses transform + opacity — GPU composited, no layout triggers.
if (typeof document !== 'undefined' && !document.getElementById('phase-dot-keyframes')) {
  const style = document.createElement('style');
  style.id = 'phase-dot-keyframes';
  style.textContent = `
    @keyframes phase-pulse-ring {
      0%   { transform: scale(0.82); opacity: 0.75; }
      55%  { transform: scale(1.2);  opacity: 0.2;  }
      100% { transform: scale(0.82); opacity: 0.75; }
    }
  `;
  document.head.appendChild(style);
}

// Inject graph-panel-specific styles once.
if (typeof document !== 'undefined' && !document.getElementById('graph-panel-styles')) {
  const style = document.createElement('style');
  style.id = 'graph-panel-styles';
  style.textContent = `
    /* Category filter dropdown */
    .graph-filter-select {
      appearance: none;
      -webkit-appearance: none;
      background-color: var(--bg-2);
      border: 1px solid var(--line-2);
      border-radius: var(--radius-sm, 5px);
      color: var(--ink-1);
      cursor: pointer;
      font-family: var(--mono, monospace);
      font-size: 11px;
      padding: 5px 28px 5px 10px;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236b7280'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 8px center;
      transition: border-color 120ms ease, background-color 120ms ease;
    }
    .graph-filter-select:hover {
      border-color: color-mix(in oklab, var(--brand) 50%, var(--line-2));
      background-color: var(--bg-3);
    }
    .graph-filter-select:focus {
      outline: none;
      border-color: var(--brand);
      box-shadow: 0 0 0 2px color-mix(in oklab, var(--brand) 20%, transparent);
    }

    /* New feature button */
    .graph-new-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 5px 10px;
      border-radius: var(--radius-sm, 5px);
      border: 1px solid color-mix(in oklab, var(--brand) 45%, var(--line-2));
      background: color-mix(in oklab, var(--brand) 10%, var(--bg-2));
      color: var(--brand);
      font-family: var(--mono, monospace);
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: background 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
      white-space: nowrap;
    }
    .graph-new-btn:hover {
      background: color-mix(in oklab, var(--brand) 18%, var(--bg-2));
      border-color: color-mix(in oklab, var(--brand) 65%, var(--line-2));
      box-shadow: 0 0 10px color-mix(in oklab, var(--brand) 20%, transparent);
    }
    .graph-new-btn:active {
      transform: scale(0.97);
    }

    /* Toast for graph panel */
    @keyframes graph-toast-in {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .graph-toast-enter {
      animation: graph-toast-in 220ms ease forwards;
    }

    /* Legend strip */
    .graph-legend-strip {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px 14px;
      padding: 10px 14px;
      border-radius: var(--radius-sm, 5px);
      border: 1px solid var(--line-1);
      background: color-mix(in oklab, var(--bg-1) 85%, transparent);
    }

    /* Legend animated edge sample */
    .legend-edge-sample {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .legend-edge-path {
      stroke: color-mix(in oklab, var(--brand) 80%, transparent);
      stroke-width: 1.5;
      stroke-dasharray: 6 6;
      stroke-linecap: round;
      animation: edge-flow 0.9s linear infinite;
      will-change: stroke-dashoffset;
      fill: none;
    }
  `;
  document.head.appendChild(style);
}

import type {
  FeatureSummaryItem,
  FeatureTokenRollup,
  PlanDocument,
  PlanningNode,
  PlanningNodeType,
  ProjectPlanningGraph,
} from '../../types';
import {
  featureMatchesBucket,
  featureMatchesSignal,
  getProjectPlanningGraph,
  PlanningApiError,
} from '../../services/planning';
import type { PlanningSignal, PlanningStatusBucket } from '../../services/planningRoutes';
import { useData } from '../../contexts/DataContext';
import { DocumentModal } from '../DocumentModal';
import { BtnGhost, Chip, DocChip, StatusPill } from './primitives';
import { EdgeLayer } from './primitives/EdgeLayer';
import type { EdgeLayerFeature } from './primitives/EdgeLayer';

// ── Constants ─────────────────────────────────────────────────────────────────

const FEATURE_COL_W = 240;
const LANE_W = 200;
const TOTALS_COL_W = 180;

// Lane definitions following the design handoff order
// Each maps to a PlanningNodeType (or union of types for combined lanes)
interface LaneDef {
  key: string;
  label: string;
  color: string;
  glyph: string;
  nodeTypes: PlanningNodeType[];
}

const LANES: LaneDef[] = [
  {
    key: 'design_spec',
    label: 'Design Spec',
    color: 'var(--spec)',
    glyph: '◇',
    nodeTypes: ['design_spec'],
  },
  {
    key: 'prd',
    label: 'PRD',
    color: 'var(--prd)',
    glyph: '▣',
    nodeTypes: ['prd'],
  },
  {
    key: 'implementation_plan',
    label: 'Impl Plan',
    color: 'var(--plan)',
    glyph: '▤',
    nodeTypes: ['implementation_plan'],
  },
  {
    key: 'progress',
    label: 'Progress',
    color: 'var(--prog)',
    glyph: '◫',
    nodeTypes: ['progress'],
  },
  {
    key: 'context',
    label: 'Context / Report',
    color: 'var(--ctx)',
    glyph: '◌',
    nodeTypes: ['context', 'report', 'tracker'],
  },
];

// Category identity colors (matching design handoff FeatureCell logic)
const CATEGORY_COLORS: Record<string, string> = {
  features: 'var(--brand)',
  feature: 'var(--brand)',
  enhancements: 'var(--plan)',
  enhancement: 'var(--plan)',
  refactors: 'var(--info)',
  refactor: 'var(--info)',
  spikes: 'var(--spk)',
  spike: 'var(--spk)',
  bugfix: 'var(--err)',
};

// Filter category options — "all" means no filtering
type CategoryFilter = 'all' | 'features' | 'enhancements' | 'refactors' | 'spikes';

const CATEGORY_FILTER_OPTIONS: { value: CategoryFilter; label: string }[] = [
  { value: 'all', label: 'All categories' },
  { value: 'features', label: 'Features' },
  { value: 'enhancements', label: 'Enhancements' },
  { value: 'refactors', label: 'Refactors' },
  { value: 'spikes', label: 'Spikes' },
];

// Artifact legend entries — 8 artifact types + animated edge example
interface ArtifactLegendEntry {
  token: string;
  label: string;
  color: string;
}

const ARTIFACT_LEGEND: ArtifactLegendEntry[] = [
  { token: 'SPEC',  label: 'Design Spec',  color: 'var(--spec)'   },
  { token: 'SPIKE', label: 'Spike',        color: 'var(--spk)'    },
  { token: 'PRD',   label: 'PRD',          color: 'var(--prd)'    },
  { token: 'PLAN',  label: 'Impl Plan',    color: 'var(--plan)'   },
  { token: 'PHASE', label: 'Phase',        color: 'var(--prog)'   },
  { token: 'CTX',   label: 'Context',      color: 'var(--ctx)'    },
  { token: 'TRK',   label: 'Tracker',      color: 'var(--trk, var(--ctx))' },
  { token: 'REP',   label: 'Report',       color: 'var(--rep, var(--mag))' },
];

// ── Toast (scoped to graph panel) ─────────────────────────────────────────────

interface GraphToastEntry {
  id: string;
  message: string;
}

function useGraphToast() {
  const [toasts, setToasts] = useState<GraphToastEntry[]>([]);
  const timersRef = useRef<number[]>([]);

  const push = useCallback((message: string) => {
    const id = `graph-toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
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

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatGeneratedAt(value?: string): string {
  if (!value) return 'n/a';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

function groupByFeatureSlug(nodes: PlanningNode[]): Map<string, PlanningNode[]> {
  const map = new Map<string, PlanningNode[]>();
  for (const node of nodes) {
    const slug = node.featureSlug || '(unknown)';
    const existing = map.get(slug);
    if (existing) {
      existing.push(node);
    } else {
      map.set(slug, [node]);
    }
  }
  return map;
}

/** Get nodes for a lane from a feature's node list */
function getLaneNodes(nodes: PlanningNode[], lane: LaneDef): PlanningNode[] {
  return nodes.filter(n => lane.nodeTypes.includes(n.type));
}

/** Derive a display category from feature slug or node data */
function deriveCategory(slug: string, nodes: PlanningNode[]): string {
  // Try to infer from the slug prefix (e.g., "enhancements/feat-slug" → "enhancement")
  const parts = slug.split('/');
  if (parts.length > 1) {
    const prefix = parts[0].toLowerCase();
    if (prefix in CATEGORY_COLORS) return prefix;
  }
  // Default based on whether it has a spike
  const hasSpike = nodes.some(n => n.type === 'design_spec');
  if (hasSpike) return 'feature';
  return 'feature';
}

/**
 * Map a derived category token to a canonical CategoryFilter bucket.
 * Handles both plural ("enhancements") and singular ("enhancement") forms.
 */
function categoryToBucket(category: string): CategoryFilter {
  const c = category.toLowerCase();
  if (c === 'features' || c === 'feature') return 'features';
  if (c === 'enhancements' || c === 'enhancement') return 'enhancements';
  if (c === 'refactors' || c === 'refactor') return 'refactors';
  if (c === 'spikes' || c === 'spike') return 'spikes';
  return 'features'; // default unmapped → features bucket
}

/** Derive complexity from node count or title hints */
function deriveComplexity(nodes: PlanningNode[]): string {
  if (nodes.length >= 5) return 'L';
  if (nodes.length >= 3) return 'M';
  return 'S';
}

/** Check if a feature has a mismatch */
function hasMismatch(nodes: PlanningNode[]): boolean {
  return nodes.some(n => n.mismatchState?.isMismatch);
}

/** Check if a feature is stale */
function isStale(nodes: PlanningNode[]): boolean {
  return nodes.some(n =>
    n.mismatchState?.state === 'stale' ||
    n.mismatchState?.state === 'reversed' ||
    n.mismatchState?.state === 'unresolved',
  );
}

/** Derive effective status from nodes */
function deriveEffectiveStatus(nodes: PlanningNode[]): string {
  // Use the most "advanced" effective status across all nodes
  const priority = ['blocked', 'in-progress', 'in_progress', 'approved', 'draft', 'completed', 'superseded', 'future'];
  for (const p of priority) {
    if (nodes.some(n => n.effectiveStatus === p || n.rawStatus === p)) return p;
  }
  return nodes[0]?.rawStatus ?? 'unknown';
}

function graphNodesToFeatureSummary(slug: string, nodes: PlanningNode[]): FeatureSummaryItem {
  const effectiveStatus = deriveEffectiveStatus(nodes);
  const rawStatus = nodes.find((node) => node.rawStatus)?.rawStatus ?? effectiveStatus;
  const blockedCount = nodes.filter((node) => {
    const raw = (node.rawStatus ?? '').toLowerCase();
    const effective = (node.effectiveStatus ?? '').toLowerCase();
    return raw.includes('blocked') || effective.includes('blocked');
  }).length;

  return {
    featureId: slug,
    featureName: nodes.find((node) => node.title)?.title ?? slug,
    rawStatus,
    effectiveStatus,
    isMismatch: hasMismatch(nodes),
    mismatchState: isStale(nodes) ? 'stale' : hasMismatch(nodes) ? 'mismatch' : 'aligned',
    hasBlockedPhases: blockedCount > 0,
    phaseCount: nodes.length,
    blockedPhaseCount: blockedCount,
    nodeCount: nodes.length,
  };
}

function getFeatureBaseSlug(featureId: string): string {
  const segments = featureId.split('/');
  return segments[segments.length - 1] || featureId;
}

export function findGraphFeatureSummary(
  slug: string,
  featureSummaries: FeatureSummaryItem[] | undefined,
): FeatureSummaryItem | null {
  if (!featureSummaries?.length) return null;
  const baseSlug = getFeatureBaseSlug(slug);
  return (
    featureSummaries.find((feature) => feature.featureId === slug) ||
    featureSummaries.find((feature) => getFeatureBaseSlug(feature.featureId) === baseSlug) ||
    null
  );
}

export function graphFeatureMatchesFilter(
  slug: string,
  nodes: PlanningNode[],
  featureSummaries: FeatureSummaryItem[] | undefined,
  activeStatusBucket: PlanningStatusBucket | null,
  activeSignal: PlanningSignal | null,
): boolean {
  if (!activeStatusBucket && !activeSignal) return true;
  const summary = findGraphFeatureSummary(slug, featureSummaries) ?? graphNodesToFeatureSummary(slug, nodes);
  if (activeStatusBucket && !featureMatchesBucket(summary, activeStatusBucket)) return false;
  if (activeSignal && !featureMatchesSignal(summary, activeSignal)) return false;
  return true;
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** Sticky lane header row */
function GraphHeaderRow() {
  return (
    <div
      role="row"
      style={{
        display: 'grid',
        gridTemplateColumns: `${FEATURE_COL_W}px repeat(${LANES.length}, ${LANE_W}px) ${TOTALS_COL_W}px`,
        borderBottom: '1px solid var(--line-1)',
        background: 'var(--bg-1)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      {/* Feature column header */}
      <div
        role="columnheader"
        aria-colindex={1}
        style={{
          padding: '14px 16px',
          borderRight: '1px solid var(--line-1)',
        }}
      >
        <span
          className="planning-caps planning-mono"
          style={{ fontSize: 10, color: 'var(--ink-3)' }}
        >
          Feature
        </span>
      </div>

      {/* Lane headers */}
      {LANES.map(lane => (
        <div
          key={lane.key}
          role="columnheader"
          aria-colindex={LANES.indexOf(lane) + 2}
          style={{
            padding: '14px 14px',
            borderRight: '1px solid var(--line-1)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {/* Colored square glyph — glyph color = artifact-identity color */}
          <span
            aria-hidden="true"
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background: lane.color,
              display: 'inline-block',
              flexShrink: 0,
              boxShadow: `0 0 8px color-mix(in oklab, ${lane.color} 50%, transparent)`,
            }}
          />
          <span
            className="planning-caps planning-mono"
            style={{ fontSize: 10, color: 'var(--ink-2)' }}
          >
            {lane.label}
          </span>
        </div>
      ))}

      {/* Totals column header — neutral, no colored glyph */}
      <div
        role="columnheader"
        aria-colindex={LANES.length + 2}
        style={{
          padding: '14px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            fontSize: 11,
            color: 'var(--ink-3)',
            fontFamily: 'var(--mono)',
            lineHeight: 1,
          }}
        >
          ∑
        </span>
        <span
          className="planning-caps planning-mono"
          style={{ fontSize: 10, color: 'var(--ink-2)' }}
        >
          Totals
        </span>
      </div>
    </div>
  );
}

interface FeatureCellProps {
  slug: string;
  nodes: PlanningNode[];
  selected: boolean;
  onSelectFeature?: (slug: string) => void;
  onPrefetchFeature?: (slug: string) => void;
}

/** Feature identity cell — leftmost column */
function FeatureCell({ slug, nodes, selected, onSelectFeature, onPrefetchFeature }: FeatureCellProps) {
  const category = deriveCategory(slug, nodes);
  const complexity = deriveComplexity(nodes);
  const mismatch = hasMismatch(nodes);
  const stale = isStale(nodes);
  const effectiveStatus = deriveEffectiveStatus(nodes);
  const catColor = CATEGORY_COLORS[category] ?? 'var(--ink-3)';

  // Display title: use last path segment of slug or full slug
  const title = slug.includes('/')
    ? slug.split('/').pop() ?? slug
    : slug;

  return (
    <div
      onClick={() => onSelectFeature?.(slug)}
      onMouseEnter={() => onPrefetchFeature?.(slug)}
      onFocus={() => onPrefetchFeature?.(slug)}
      role="rowheader"
      aria-label={`${title}, ${category}, ${complexity} complexity, ${effectiveStatus}${mismatch ? ', frontmatter mismatch' : ''}${stale ? ', stale status' : ''}`}
      tabIndex={0}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelectFeature?.(slug);
        }
      }}
      style={{
        padding: '12px 14px',
        paddingLeft: selected ? 11 : 14,
        borderRight: '1px solid var(--line-1)',
        borderLeft: selected
          ? '3px solid var(--brand)'
          : '3px solid transparent',
        background: 'var(--bg-1)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        minWidth: 0,
        cursor: 'pointer',
        transition: 'border-left-color 120ms ease',
      }}
    >
      {/* Top row: category badge + complexity chip + mismatch/stale indicators */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'nowrap', minWidth: 0 }}>
        {/* Category badge */}
        <span
          className="planning-caps planning-mono"
          style={{
            fontSize: 9,
            color: catColor,
            letterSpacing: '0.1em',
            flexShrink: 0,
          }}
        >
          {category}
        </span>

        <span style={{ fontSize: 10, color: 'var(--ink-4)', flexShrink: 0 }}>·</span>

        {/* Complexity chip */}
        <span
          className="planning-mono"
          style={{
            fontSize: 9,
            color: 'var(--ink-3)',
            flexShrink: 0,
          }}
        >
          {complexity}
        </span>

        {/* Mismatch indicator: ⚑ in --mag color */}
        {mismatch && (
          <span
            title="Frontmatter mismatch detected"
            aria-label="Frontmatter mismatch detected"
            style={{
              marginLeft: 'auto',
              color: 'var(--mag)',
              fontSize: 10,
              flexShrink: 0,
              cursor: 'help',
            }}
          >
            ⚑
          </span>
        )}

        {/* Stale indicator: ◷ in --warn color */}
        {stale && !mismatch && (
          <span
            title="Stale or reversed status"
            aria-label="Stale or reversed status"
            style={{
              marginLeft: 'auto',
              color: 'var(--warn)',
              fontSize: 10,
              flexShrink: 0,
              cursor: 'help',
            }}
          >
            ◷
          </span>
        )}

        {/* Both mismatch + stale: show stale adjacent */}
        {stale && mismatch && (
          <span
            title="Stale or reversed status"
            aria-label="Stale or reversed status"
            style={{
              color: 'var(--warn)',
              fontSize: 10,
              flexShrink: 0,
              cursor: 'help',
            }}
          >
            ◷
          </span>
        )}
      </div>

      {/* Title — 2-line clamp */}
      <div
        style={{
          fontSize: 13.5,
          fontWeight: 500,
          color: 'var(--ink-0)',
          lineHeight: 1.25,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}
        title={slug}
      >
        {title}
      </div>

      {/* Bottom row: status pill + slug */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <StatusPill status={effectiveStatus} />
        {/* Slug chip — insertion point for T4-002's DocChips */}
        <span
          className="planning-mono"
          style={{
            fontSize: 10,
            color: 'var(--ink-3)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
            minWidth: 0,
          }}
          title={slug}
        >
          {slug}
        </span>
      </div>
    </div>
  );
}

// ── PhaseDot & PhaseStackInline ────────────────────────────────────────────────

type PhaseDotState = 'completed' | 'in_progress' | 'blocked' | 'pending';

interface PhaseDotProps {
  state: PhaseDotState;
  /** Phase number or label shown inside the dot (e.g. "3") */
  label?: string;
  /** Tooltip content */
  title?: string;
}

/**
 * 14×14 rounded-square dot representing one phase's status.
 *
 * completed  → filled var(--ok), white checkmark
 * in_progress → transparent fill, info-colored border + pulsing outer ring
 * blocked    → transparent fill, err-colored border + "!" glyph
 * pending    → muted transparent fill, ink-3 border + phase number
 */
function PhaseDot({ state, label, title }: PhaseDotProps) {
  const colorMap: Record<PhaseDotState, string> = {
    completed:   'var(--ok)',
    in_progress: 'var(--info)',
    blocked:     'var(--err)',
    pending:     'var(--ink-3)',
  };
  const color = colorMap[state];
  const filled = state === 'completed';
  const pulsing = state === 'in_progress';
  const blocked = state === 'blocked';

  return (
    <div
      title={title}
      style={{
        position: 'relative',
        width: 14,
        height: 14,
        borderRadius: 3,
        background: filled
          ? color
          : `color-mix(in oklab, ${color} 8%, transparent)`,
        border: `1.5px solid ${color}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontSize: 7.5,
        fontFamily: 'var(--mono, monospace)',
        fontWeight: 600,
        color: filled ? 'var(--bg-0)' : color,
      }}
    >
      {/* Inner glyph */}
      {filled ? '✓' : blocked ? '!' : (label ?? '')}

      {/* Pulsing ring for in-progress — absolutely positioned outer ring */}
      {pulsing && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: -4,
            borderRadius: 6,
            border: `1.5px solid color-mix(in oklab, ${color} 55%, transparent)`,
            willChange: 'transform, opacity',
            animation: 'phase-pulse-ring 1.8s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />
      )}
    </div>
  );
}

/** Map a PlanningNode effectiveStatus / rawStatus to a PhaseDotState */
function nodeToPhaseState(node: PlanningNode): PhaseDotState {
  const s = node.effectiveStatus || node.rawStatus || '';
  if (s === 'completed') return 'completed';
  if (s === 'in-progress' || s === 'in_progress') return 'in_progress';
  if (s === 'blocked') return 'blocked';
  return 'pending';
}

interface PhaseStackInlineProps {
  nodes: PlanningNode[];
  onOpen?: (e: React.MouseEvent<HTMLButtonElement>) => void;
}

/**
 * Horizontal row of PhaseDots (one per progress node) plus a "X/Y" count label.
 * Renders as an interactive button so clicking surfaces node detail.
 */
function PhaseStackInline({ nodes, onOpen }: PhaseStackInlineProps) {
  const completedCount = nodes.filter(n => nodeToPhaseState(n) === 'completed').length;
  const total = nodes.length;

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Open progress lane with ${completedCount} of ${total} phases complete`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '5px 8px',
        background: 'var(--bg-2)',
        border: '1px solid color-mix(in oklab, var(--prog) 35%, var(--line-1))',
        borderRadius: 5,
        cursor: 'pointer',
        fontFamily: 'inherit',
        transition: 'border-color 120ms ease, background 120ms ease',
        flexWrap: 'nowrap',
        maxWidth: '100%',
        overflow: 'hidden',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-3)';
        (e.currentTarget as HTMLButtonElement).style.borderColor =
          'color-mix(in oklab, var(--prog) 55%, var(--line-1))';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-2)';
        (e.currentTarget as HTMLButtonElement).style.borderColor =
          'color-mix(in oklab, var(--prog) 35%, var(--line-1))';
      }}
    >
      {nodes.map((node, i) => {
        const state = nodeToPhaseState(node);
        // Derive a short phase label: phaseNumber from node metadata or fallback to index+1
        // PlanningNode doesn't carry phaseNumber; fall back to 1-based index
        const phaseNum = i + 1;
        const tooltip = `Phase ${phaseNum}: ${node.title} (${node.effectiveStatus || node.rawStatus})`;
        return (
          <PhaseDot
            key={node.id}
            state={state}
            label={String(phaseNum)}
            title={tooltip}
          />
        );
      })}

      {/* X/Y count label */}
      <span
        className="planning-mono"
        style={{
          fontSize: 9.5,
          color: 'var(--ink-3)',
          marginLeft: 4,
          flexShrink: 0,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {completedCount}/{total}
      </span>
    </button>
  );
}

interface LaneCellProps {
  lane: LaneDef;
  nodes: PlanningNode[];
  onNodeClick?: (node: PlanningNode) => void;
}

/** Lane cell — progress lane renders PhaseStackInline; all other lanes render DocChips */
function LaneCell({ lane, nodes, onNodeClick }: LaneCellProps) {
  const laneNodes = getLaneNodes(nodes, lane);

  return (
    <div
      role="gridcell"
      aria-label={`${lane.label}: ${laneNodes.length === 0 ? 'no artifacts' : `${laneNodes.length} artifact${laneNodes.length === 1 ? '' : 's'}`}`}
      style={{
        padding: '10px 10px',
        borderRight: '1px solid var(--line-1)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        justifyContent: 'center',
        minWidth: 0,
      }}
    >
      {laneNodes.length === 0 ? (
        <EmptyDash />
      ) : lane.key === 'progress' ? (
        /* T4-003: Progress lane renders phase dots instead of DocChips */
        <PhaseStackInline
          nodes={laneNodes}
          onOpen={e => {
            e.stopPropagation();
            // Open the first progress node on click (closest to a "phase overview")
            if (laneNodes[0]) onNodeClick?.(laneNodes[0]);
          }}
        />
      ) : (
        laneNodes.map(node => (
          <DocChip
            key={node.id}
            node={node}
            onClick={e => {
              e.stopPropagation();
              onNodeClick?.(node);
            }}
          />
        ))
      )}
    </div>
  );
}

/** Empty lane dash */
function EmptyDash() {
  return (
    <span
      aria-label="No artifact"
      style={{
        fontSize: 14,
        color: 'var(--ink-4)',
        textAlign: 'center',
        letterSpacing: 4,
        userSelect: 'none',
      }}
    >
      —
    </span>
  );
}

// ── TotalsCell ─────────────────────────────────────────────────────────────────

/** Model identity keys shown in stacked bar order. */
const MODEL_KEYS = ['opus', 'sonnet', 'haiku'] as const;
type ModelKey = (typeof MODEL_KEYS)[number];

const MODEL_COLORS: Record<ModelKey, string> = {
  opus:   'var(--m-opus)',
  sonnet: 'var(--m-sonnet)',
  haiku:  'var(--m-haiku)',
};

/** Format a token count to a compact string: 1234 → "1.2k", 123456 → "123k". */
function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000)    return `${Math.round(n / 1_000)}k`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

interface TotalsCellProps {
  /** Server-provided rollup for this feature slug. Undefined when backend hasn't delivered T7-004 data. */
  rollup: FeatureTokenRollup | undefined;
}

/**
 * Rightmost grid column showing story-points, total tokens,
 * stacked model-identity bar, and per-model token chips.
 *
 * Renders a graceful placeholder when rollup is absent or has no linked sessions
 * (totalTokens === 0). Never estimates tokens client-side.
 */
function TotalsCell({ rollup }: TotalsCellProps) {
  // Empty state: no rollup delivered by backend or feature has no linked sessions.
  const hasTokens = rollup && rollup.totalTokens > 0;

  if (!rollup) {
    return (
      <div
        role="gridcell"
        aria-label="Token data not yet available"
        style={{
          padding: '10px 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 54,
        }}
        title="Token data not yet available"
      >
        <span
          className="planning-mono"
          style={{ fontSize: 11, color: 'var(--ink-4)', letterSpacing: 2 }}
        >
          —
        </span>
      </div>
    );
  }

  // Build per-model breakdown from the server-provided byModel array.
  const modelMap: Partial<Record<ModelKey, number>> = {};
  for (const entry of rollup.byModel) {
    const key = entry.model.toLowerCase() as ModelKey;
    if (MODEL_KEYS.includes(key)) {
      modelMap[key] = (modelMap[key] ?? 0) + entry.totalTokens;
    }
  }

  const total = rollup.totalTokens;

  return (
    <div
      role="gridcell"
      aria-label={`${rollup.storyPoints || 0} story points, ${hasTokens ? `${total.toLocaleString()} tokens` : 'no linked session tokens'}`}
      style={{
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        minWidth: 0,
        minHeight: 54,
        justifyContent: 'center',
      }}
    >
      {/* Top row: story points (left) + total tokens (right) */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, minWidth: 0 }}>
        {rollup.storyPoints > 0 ? (
          <>
            <span
              className="planning-mono planning-tnum"
              style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink-0)', lineHeight: 1 }}
            >
              {rollup.storyPoints}
            </span>
            <span
              className="planning-caps"
              style={{ fontSize: 8, color: 'var(--ink-3)', letterSpacing: '0.1em' }}
            >
              pts
            </span>
          </>
        ) : (
          <span
            className="planning-mono"
            style={{ fontSize: 13, color: 'var(--ink-4)' }}
          >
            —
          </span>
        )}
        {hasTokens && (
          <span
            className="planning-mono planning-tnum"
            title={`${total.toLocaleString()} tokens`}
            style={{
              marginLeft: 'auto',
              fontSize: 11,
              color: 'var(--ink-1)',
              whiteSpace: 'nowrap',
            }}
          >
            {fmtTokens(total)}
          </span>
        )}
      </div>

      {/* Stacked model-identity bar */}
      {hasTokens && (
        <div
          role="img"
          aria-label={`Token distribution: ${MODEL_KEYS.map(m => modelMap[m] ? `${m} ${fmtTokens(modelMap[m]!)}` : '').filter(Boolean).join(', ')}`}
          style={{
            display: 'flex',
            height: 5,
            borderRadius: 2,
            overflow: 'hidden',
            background: 'var(--bg-3)',
          }}
        >
          {MODEL_KEYS.map(m => {
            const count = modelMap[m] ?? 0;
            if (count === 0) return null;
            const pct = (count / total) * 100;
            return (
              <div
                key={m}
                title={`${m}: ${count.toLocaleString()} (${pct.toFixed(0)}%)`}
                style={{
                  width: `${pct}%`,
                  background: MODEL_COLORS[m],
                  flexShrink: 0,
                }}
              />
            );
          })}
        </div>
      )}

      {/* Per-model count row */}
      {hasTokens && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', minWidth: 0 }}>
          {MODEL_KEYS.map(m => {
            const count = modelMap[m] ?? 0;
            if (count === 0) return null;
            return (
              <span
                key={m}
                className="planning-mono planning-tnum"
                style={{ fontSize: 9, color: MODEL_COLORS[m], display: 'inline-flex', alignItems: 'center', gap: 3 }}
                aria-label={`${m} ${count.toLocaleString()} tokens`}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    background: MODEL_COLORS[m],
                    display: 'inline-block',
                    flexShrink: 0,
                  }}
                />
                {fmtTokens(count)}
              </span>
            );
          })}
        </div>
      )}

      {/* No-sessions empty state (rollup present but zero tokens) */}
      {!hasTokens && (
        <span
          className="planning-mono"
          style={{ fontSize: 10, color: 'var(--ink-4)' }}
          title="No session tokens linked to this feature"
        >
          no sessions
        </span>
      )}
    </div>
  );
}

interface GraphRowProps {
  slug: string;
  nodes: PlanningNode[];
  rollup: FeatureTokenRollup | undefined;
  selected: boolean;
  onSelectFeature?: (slug: string) => void;
  onPrefetchFeature?: (slug: string) => void;
  onNodeClick?: (node: PlanningNode) => void;
}

/** Single feature row in the graph grid */
function GraphRow({ slug, nodes, rollup, selected, onSelectFeature, onPrefetchFeature, onNodeClick }: GraphRowProps) {
  return (
    <div
      role="row"
      aria-selected={selected}
      style={{
        display: 'grid',
        gridTemplateColumns: `${FEATURE_COL_W}px repeat(${LANES.length}, ${LANE_W}px) ${TOTALS_COL_W}px`,
        borderBottom: '1px solid var(--line-1)',
        background: selected
          ? 'color-mix(in oklab, var(--brand) 6%, transparent)'
          : 'transparent',
        position: 'relative',
        minHeight: 54,
        transition: 'background 120ms ease',
        /* INSERTION POINT T4-005: SVG edge layer positioned absolute behind this row */
      }}
    >
      <FeatureCell
        slug={slug}
        nodes={nodes}
        selected={selected}
        onSelectFeature={onSelectFeature}
        onPrefetchFeature={onPrefetchFeature}
      />

      {LANES.map(lane => (
        <LaneCell
          key={lane.key}
          lane={lane}
          nodes={nodes}
          onNodeClick={onNodeClick}
        />
      ))}

      {/* Totals column — rightmost, no border-right */}
      <TotalsCell rollup={rollup} />
    </div>
  );
}

// ── Filter Controls ────────────────────────────────────────────────────────────

interface GraphFilterControlsProps {
  activeFilter: CategoryFilter;
  onFilterChange: (filter: CategoryFilter) => void;
  onNewFeature: () => void;
  visibleCount: number;
  totalCount: number;
}

/**
 * Filter bar rendered above the graph grid.
 * Left: "All categories" dropdown with category options.
 * Right: "New feature" stub button.
 */
function GraphFilterControls({
  activeFilter,
  onFilterChange,
  onNewFeature,
  visibleCount,
  totalCount,
}: GraphFilterControlsProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        flexWrap: 'wrap',
      }}
    >
      {/* Category dropdown */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <label
          htmlFor="graph-category-filter"
          className="planning-caps planning-mono"
          style={{ fontSize: 9, color: 'var(--ink-3)', letterSpacing: '0.08em', userSelect: 'none' }}
        >
          Category
        </label>
        <select
          id="graph-category-filter"
          className="graph-filter-select"
          value={activeFilter}
          onChange={e => onFilterChange(e.target.value as CategoryFilter)}
          aria-label="Filter features by category"
        >
          {CATEGORY_FILTER_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Filtered count hint — only shown when a filter is active */}
      {activeFilter !== 'all' && (
        <span
          className="planning-mono"
          style={{ fontSize: 10, color: 'var(--ink-3)' }}
          aria-live="polite"
        >
          {visibleCount} / {totalCount}
        </span>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* New feature button */}
      <button
        type="button"
        className="graph-new-btn"
        onClick={onNewFeature}
        aria-label="New feature (coming in v2)"
      >
        <Plus size={11} aria-hidden="true" />
        New feature
      </button>
    </div>
  );
}

// ── Artifact Legend ────────────────────────────────────────────────────────────

/**
 * Legend strip below the graph.
 * 8 artifact-type swatches + labels, followed by an animated edge sample.
 */
function ArtifactLegend() {
  return (
    <div
      className="graph-legend-strip"
      role="legend"
      aria-label="Artifact type legend"
    >
      {/* Artifact type swatches */}
      {ARTIFACT_LEGEND.map(entry => (
        <div
          key={entry.token}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            flexShrink: 0,
          }}
        >
          {/* Color swatch */}
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              width: 8,
              height: 8,
              borderRadius: 2,
              background: entry.color,
              flexShrink: 0,
              boxShadow: `0 0 6px color-mix(in oklab, ${entry.color} 40%, transparent)`,
            }}
          />
          {/* Token label */}
          <span
            className="planning-caps planning-mono"
            style={{
              fontSize: 9,
              color: entry.color,
              letterSpacing: '0.08em',
            }}
          >
            {entry.token}
          </span>
          {/* Full label */}
          <span
            className="planning-mono"
            style={{
              fontSize: 9,
              color: 'var(--ink-3)',
            }}
          >
            {entry.label}
          </span>
        </div>
      ))}

      {/* Divider */}
      <span
        aria-hidden="true"
        style={{ width: 1, height: 14, background: 'var(--line-2)', flexShrink: 0, alignSelf: 'center' }}
      />

      {/* Animated edge example */}
      <div
        className="legend-edge-sample"
        aria-label="Active edge — animated flow indicator"
      >
        {/* Inline SVG showing the animated dashed edge */}
        <svg
          aria-hidden="true"
          width={40}
          height={10}
          style={{ overflow: 'visible', flexShrink: 0 }}
        >
          <path
            d="M 2 5 C 20 5, 20 5, 38 5"
            className="legend-edge-path"
          />
          {/* Arrowhead stub */}
          <circle cx={38} cy={5} r={2} fill="color-mix(in oklab, var(--brand) 80%, transparent)" />
        </svg>
        <span
          className="planning-caps planning-mono"
          style={{ fontSize: 9, color: 'var(--ink-2)', letterSpacing: '0.08em' }}
        >
          active edge
        </span>
      </div>
    </div>
  );
}

// ── Empty / Loading / Error states ────────────────────────────────────────────

function EmptyGraphState() {
  return (
    <div
      className="planning-panel flex items-center justify-center border-dashed p-10 text-center"
      style={{ background: 'color-mix(in oklab, var(--bg-1) 70%, transparent)' }}
    >
      <div>
        <FolderSearch size={28} style={{ margin: '0 auto 12px', color: 'var(--ink-3)' }} />
        <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--ink-2)' }}>No lineage yet.</p>
        <p style={{ marginTop: 4, fontSize: 12, color: 'var(--ink-3)' }}>
          Add a PRD or design spec to seed the planning graph.
        </p>
      </div>
    </div>
  );
}

function FilterEmptyState({ filter }: { filter: CategoryFilter }) {
  const label = CATEGORY_FILTER_OPTIONS.find(o => o.value === filter)?.label ?? filter;
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 16px',
        gap: 8,
        color: 'var(--ink-3)',
      }}
    >
      <FolderSearch size={24} style={{ color: 'var(--ink-4)' }} />
      <p className="planning-mono" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
        No {label.toLowerCase()} found.
      </p>
      <p style={{ fontSize: 11, color: 'var(--ink-3)' }}>
        Try a different category or clear the filter.
      </p>
    </div>
  );
}

function GraphSkeleton() {
  return (
    <div className="animate-pulse" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ height: 44, borderRadius: 6, background: 'color-mix(in oklab, var(--bg-3) 60%, transparent)' }} />
      {[1, 2, 3].map(i => (
        <div key={i} style={{ height: 54, borderRadius: 6, background: 'color-mix(in oklab, var(--bg-3) 40%, transparent)' }} />
      ))}
    </div>
  );
}

function GraphError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        borderRadius: 8,
        border: '1px solid color-mix(in oklab, var(--err) 40%, transparent)',
        background: 'color-mix(in oklab, var(--err) 5%, transparent)',
        padding: '12px 16px',
      }}
    >
      <AlertCircle size={15} style={{ marginTop: 2, flexShrink: 0, color: 'var(--err)' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 12, color: 'var(--err)' }}>{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          flexShrink: 0,
          borderRadius: 4,
          border: '1px solid color-mix(in oklab, var(--err) 40%, transparent)',
          background: 'color-mix(in oklab, var(--err) 10%, transparent)',
          padding: '4px 8px',
          fontSize: 10,
          fontWeight: 500,
          color: 'var(--err)',
          cursor: 'pointer',
        }}
      >
        <RefreshCw size={10} />
        Retry
      </button>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface PlanningGraphPanelProps {
  projectId: string | null;
  featureSummaries?: FeatureSummaryItem[];
  onSelectFeature?: (featureId: string) => void;
  onPrefetchFeature?: (featureId: string) => void;
  activeStatusBucket?: import('../../services/planningRoutes').PlanningStatusBucket | null;
  activeSignal?: import('../../services/planningRoutes').PlanningSignal | null;
}

type GraphFetchState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; graph: ProjectPlanningGraph };

export function PlanningGraphPanel({
  projectId,
  featureSummaries,
  onSelectFeature,
  onPrefetchFeature,
  activeStatusBucket = null,
  activeSignal = null,
}: PlanningGraphPanelProps) {
  const { documents } = useData();
  const [state, setState] = useState<GraphFetchState>({ phase: 'idle' });
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<PlanDocument | null>(null);
  const [activeFilter, setActiveFilter] = useState<CategoryFilter>('all');
  const { toasts, push: pushToast } = useGraphToast();
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleNodeClick = useCallback((node: PlanningNode) => {
    if (!node.path) return;
    const doc =
      documents.find(d => d.filePath === node.path) ||
      documents.find(d => d.canonicalPath === node.path) ||
      documents.find(d => node.path!.endsWith(d.filePath)) ||
      documents.find(d => d.filePath.endsWith(node.path!)) ||
      null;
    if (doc) setSelectedDoc(doc);
  }, [documents]);

  const handleSelectFeature = useCallback((slug: string) => {
    setSelectedSlug(prev => prev === slug ? null : slug);
    // Propagate to parent (e.g., open detail drawer in later phases)
    onSelectFeature?.(slug);
  }, [onSelectFeature]);

  const handleNewFeature = useCallback(() => {
    pushToast('New feature — coming in v2.');
  }, [pushToast]);

  const loadGraph = useCallback(async () => {
    if (!projectId) {
      setState({ phase: 'idle' });
      return;
    }
    setState({ phase: 'loading' });
    try {
      const graph = await getProjectPlanningGraph({ projectId });
      setState({ phase: 'ready', graph });
    } catch (err) {
      const message =
        err instanceof PlanningApiError
          ? `Planning graph error (${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Failed to load planning graph.';
      setState({ phase: 'error', message });
    }
  }, [projectId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  if (state.phase === 'idle' || state.phase === 'loading') {
    return <GraphSkeleton />;
  }

  if (state.phase === 'error') {
    return <GraphError message={state.message} onRetry={() => void loadGraph()} />;
  }

  const { graph } = state;

  if (graph.nodeCount === 0) {
    return <EmptyGraphState />;
  }

  // Group nodes by feature slug to build rows
  const bySlug = groupByFeatureSlug(graph.nodes);
  const allSlugs = Array.from(bySlug.keys());

  // Apply category filter — map each slug to its derived category, then filter
  const filteredSlugs = activeFilter === 'all'
    ? allSlugs
    : allSlugs.filter(slug => {
        const nodes = bySlug.get(slug) ?? [];
        const cat = deriveCategory(slug, nodes);
        return categoryToBucket(cat) === activeFilter;
      });
  const visibleSlugs = filteredSlugs.filter((slug) =>
    graphFeatureMatchesFilter(
      slug,
      bySlug.get(slug) ?? [],
      featureSummaries,
      activeStatusBucket,
      activeSignal,
    ),
  );

  const totalWidth = FEATURE_COL_W + LANES.length * LANE_W + TOTALS_COL_W;

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Toolbar row */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 12,
            fontSize: 12,
            color: 'var(--ink-2)',
          }}
        >
          <span
            className="planning-mono"
            style={{ fontWeight: 500, color: 'var(--ink-0)' }}
          >
            {graph.nodeCount} nodes
            <span style={{ margin: '0 4px', color: 'var(--line-2)' }}>·</span>
            {graph.edgeCount} edges
            <span style={{ margin: '0 4px', color: 'var(--line-2)' }}>·</span>
            {allSlugs.length} features
          </span>

          {graph.generatedAt && (
            <Chip style={{ color: 'var(--ink-2)' }}>
              <Clock size={11} />
              Generated {formatGeneratedAt(graph.generatedAt)}
            </Chip>
          )}

          <BtnGhost
            onClick={() => void loadGraph()}
            style={{ marginLeft: 'auto' }}
            className="planning-mono px-2 py-1 text-[10px]"
          >
            <RefreshCw size={10} />
            Refresh
          </BtnGhost>
        </div>

        {/* T4-006: Filter controls row — above the graph grid */}
        <GraphFilterControls
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
          onNewFeature={handleNewFeature}
          visibleCount={visibleSlugs.length}
          totalCount={allSlugs.length}
        />

        {/* Graph grid — horizontally scrollable with sticky header */}
        <div
          className="planning-panel"
          role="table"
          aria-label="Planning feature artifact graph"
          aria-colcount={LANES.length + 2}
          aria-rowcount={visibleSlugs.length + 1}
          style={{ overflow: 'hidden', padding: 0 }}
        >
          {/* Sticky header */}
          <GraphHeaderRow />

          {/* Scrollable body */}
          <div
            ref={scrollRef}
            style={{ overflow: 'auto', maxHeight: '72vh' }}
          >
            {visibleSlugs.length === 0 ? (
              <FilterEmptyState filter={activeFilter} />
            ) : (
              <div style={{ position: 'relative', width: totalWidth, minWidth: '100%' }}>
                {/* T4-005: SVG edge layer — absolute, full width/height, pointer-events none */}
                <EdgeLayer
                  laneKeys={LANES.map(l => l.key)}
                  featureColW={FEATURE_COL_W}
                  laneW={LANE_W}
                  totalWidth={totalWidth}
                  rowHeights={54}
                  features={visibleSlugs.map((slug): EdgeLayerFeature => {
                    const nodes = bySlug.get(slug) ?? [];
                    const presence: Record<string, boolean> = {};
                    for (const lane of LANES) {
                      presence[lane.key] = getLaneNodes(nodes, lane).length > 0;
                    }
                    return {
                      slug,
                      lanePresence: presence,
                      effectiveStatus: deriveEffectiveStatus(nodes),
                    };
                  })}
                />

                {/* Feature rows — filtered */}
                {visibleSlugs.map(slug => (
                  <GraphRow
                    key={slug}
                    slug={slug}
                    nodes={bySlug.get(slug) ?? []}
                    rollup={graph.featureTokenRollups?.[slug]}
                    selected={selectedSlug === slug}
                    onSelectFeature={handleSelectFeature}
                    onPrefetchFeature={onPrefetchFeature}
                    onNodeClick={handleNodeClick}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* T4-006: Artifact legend — below the graph grid */}
        <ArtifactLegend />
      </div>

      {/* Document modal (unchanged) */}
      {selectedDoc && (
        <DocumentModal
          doc={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onBack={() => setSelectedDoc(null)}
          onOpenFeature={(featureId) => {
            setSelectedDoc(null);
            onSelectFeature?.(featureId);
          }}
          backLabel="Planning Graph"
        />
      )}

      {/* Graph-scoped toasts */}
      {toasts.length > 0 && (
        <div
          aria-live="polite"
          aria-atomic="false"
          className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2"
        >
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className="planning-mono graph-toast-enter pointer-events-auto flex items-center gap-2.5 rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--brand)_40%,var(--line-2))] bg-[color:var(--bg-1)] px-4 py-2.5 text-[11.5px] text-[color:var(--ink-0)] shadow-[0_14px_40px_rgba(0,0,0,0.45)]"
              style={{ backdropFilter: 'blur(8px)' }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: 'var(--brand)',
                  display: 'inline-block',
                  flexShrink: 0,
                }}
              />
              {toast.message}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
