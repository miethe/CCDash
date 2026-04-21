/**
 * EdgeLayer — SVG overlay rendering animated flow edges between lane cells
 * in the planning graph.
 *
 * Strategy:
 *   - Single absolutely-positioned SVG covering the entire scrollable body
 *     (same width × totalHeight as the rows container).
 *   - Edges connect the horizontal mid-points of adjacent *populated* lanes
 *     for each feature row.
 *   - Active features (status in_progress | ready): animated dashed stroke
 *     using var(--brand) and @keyframes edge-flow.
 *   - Inactive features: static muted stroke (var(--ink-4), opacity 0.5).
 *   - Completed features: edges hidden (opacity 0).
 *   - pointer-events: none everywhere — never interferes with clicks.
 *   - All animation is CSS-driven; zero per-frame JS.
 */

// Inject edge-flow keyframes once — runs at module evaluation time so it is
// available before the first render. Uses strokeDashoffset only (GPU composited
// via will-change: auto on SVG; no layout triggers).
if (typeof document !== 'undefined' && !document.getElementById('edge-layer-keyframes')) {
  const style = document.createElement('style');
  style.id = 'edge-layer-keyframes';
  style.textContent = `
    @keyframes edge-flow {
      from { stroke-dashoffset: 24; }
      to   { stroke-dashoffset: 0;  }
    }
    .edge-active {
      stroke: color-mix(in oklab, var(--brand) 80%, transparent);
      stroke-width: 1.5;
      stroke-dasharray: 6 6;
      stroke-linecap: round;
      animation: edge-flow 0.9s linear infinite;
      will-change: stroke-dashoffset;
    }
    .edge-inactive {
      stroke: var(--ink-4);
      stroke-width: 1;
      stroke-dasharray: none;
      opacity: 0.45;
    }
  `;
  document.head.appendChild(style);
}

export interface EdgeLayerFeature {
  /** Feature slug (used as React key) */
  slug: string;
  /**
   * Which lane keys have at least one populated node.
   * e.g. { design_spec: true, prd: true, progress: false, ... }
   */
  lanePresence: Record<string, boolean>;
  /** Derived effective status for this feature row */
  effectiveStatus: string;
}

export interface EdgeLayerProps {
  /**
   * Ordered list of lane keys, matching the column order in the grid
   * (does NOT include the feature column or the totals column).
   */
  laneKeys: string[];
  /** Width of the leftmost feature column (px) */
  featureColW: number;
  /** Width of each lane column (px) */
  laneW: number;
  /** Total SVG width = featureColW + laneKeys.length * laneW + totalsColW */
  totalWidth: number;
  /**
   * Row descriptors.  The order matches the rendered row order.
   * Each entry carries the feature's lane presence map + status.
   */
  features: EdgeLayerFeature[];
  /**
   * Height of each row (px).  Must be the same length as `features`.
   * If a single number is provided it applies uniformly to all rows.
   */
  rowHeights: number | number[];
}

/** Map a status string to an edge visual category */
function edgeCategory(status: string): 'active' | 'inactive' | 'completed' {
  const s = status.toLowerCase();
  if (s === 'completed' || s === 'superseded') return 'completed';
  if (
    s === 'in_progress' ||
    s === 'in-progress' ||
    s === 'ready' ||
    s === 'approved'
  ) return 'active';
  return 'inactive';
}

export function EdgeLayer({
  laneKeys,
  featureColW,
  laneW,
  totalWidth,
  features,
  rowHeights,
}: EdgeLayerProps) {
  if (features.length === 0) return null;

  // Compute per-lane horizontal center x values.
  // Lane i occupies [featureColW + i*laneW, featureColW + (i+1)*laneW].
  const laneCenterX = laneKeys.map(
    (_, i) => featureColW + i * laneW + laneW / 2,
  );

  // Build cumulative row top positions.
  const rowTopOf: number[] = [];
  let accum = 0;
  for (let i = 0; i < features.length; i++) {
    rowTopOf.push(accum);
    const h = Array.isArray(rowHeights) ? rowHeights[i] ?? 54 : rowHeights;
    accum += h;
  }
  const totalHeight = accum;

  const paths: React.ReactElement[] = [];

  for (let rowIdx = 0; rowIdx < features.length; rowIdx++) {
    const feat = features[rowIdx];
    const cat = edgeCategory(feat.effectiveStatus);

    if (cat === 'completed') continue; // hide edges for completed features

    const rowH = Array.isArray(rowHeights) ? rowHeights[rowIdx] ?? 54 : rowHeights;
    const cy = rowTopOf[rowIdx] + rowH / 2;

    // Collect populated lane indices in order
    const populatedIndices = laneKeys
      .map((key, i) => (feat.lanePresence[key] ? i : -1))
      .filter(i => i !== -1);

    if (populatedIndices.length < 2) continue; // need at least 2 nodes to draw an edge

    // Draw one edge segment between each pair of adjacent populated lanes
    for (let ei = 0; ei < populatedIndices.length - 1; ei++) {
      const iFrom = populatedIndices[ei];
      const iTo = populatedIndices[ei + 1];

      const x1 = laneCenterX[iFrom] + laneW * 0.3; // exit from right side of cell
      const x2 = laneCenterX[iTo] - laneW * 0.3;   // enter at left side of next cell

      if (x2 <= x1) continue; // safety: skip degenerate edges

      const mx = (x1 + x2) / 2;

      // Cubic bezier: straight horizontal with slight S-curve anchor
      const d = `M ${x1} ${cy} C ${mx} ${cy}, ${mx} ${cy}, ${x2} ${cy}`;

      paths.push(
        <path
          key={`${feat.slug}-e${ei}`}
          d={d}
          fill="none"
          className={cat === 'active' ? 'edge-active' : 'edge-inactive'}
          // Stagger animation per row so not all edges pulse in lockstep
          style={
            cat === 'active'
              ? { animationDelay: `${(rowIdx * 0.07).toFixed(2)}s` }
              : undefined
          }
        />,
      );
    }
  }

  if (paths.length === 0) return null;

  return (
    <svg
      aria-hidden="true"
      width={totalWidth}
      height={totalHeight}
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        overflow: 'visible',
        zIndex: 0, // behind lane cell content (cells are positioned in normal flow above z:0)
      }}
    >
      {paths}
    </svg>
  );
}
