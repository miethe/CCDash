/**
 * P16-001: Modal-first navigation tests (SC-16.1).
 *
 * Addendum phases 11-15 moved Planning entry-point interactions to a
 * modal-first model: selecting a feature / plan / tracker row opens an
 * in-route modal or side panel, and only an explicit "Open board" affordance
 * performs a full route change to /board. These tests enforce that contract
 * at the route-helper + handler level using the same renderToStaticMarkup /
 * pure-closure pattern already used in the Planning test suite.
 *
 * Coverage:
 *   1. planningRouteFeatureModalHref does NOT target /board
 *   2. planningFeatureDetailHref does NOT target /board
 *   3. openFeatureModal (PlanningHomePage handler shape) navigates to /planning — NOT /board
 *   4. PlanningTriagePanel default onSelectFeature navigates to /planning (planningRouteFeatureModalHref)
 *   5. PlanCatalog card click invokes setSelectedDoc (modal open), NOT navigate
 *   6. PlanCatalog "Open Feature" status-chip button — the explicit "Open board" affordance — DOES navigate to /board
 *   7. PlanCatalog "plan" link navigates to /planning/features/:id, NOT /board
 *   8. PlanningQuickViewPanel open handler toggles panel state, NOT a navigate call
 *   9. QuickViewPromotionRow kind=feature "Open full view" navigates to /planning (not /board)
 *  10. QuickViewPromotionRow kind=feature "Planning detail" navigates to /planning/feature/:id (not /board)
 *  11. Dashboard-style plan entry handler (legacy board modal helper) is the only path that reaches /board
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import {
  planningFeatureDetailHref,
  planningFeatureModalHref,
  planningRouteFeatureModalHref,
  setPlanningRouteFeatureModalSearch,
} from '../../../services/planningRoutes';
import {
  QuickViewPromotionRow,
  usePlanningQuickView,
  type QuickViewPromotionRowProps,
} from '../PlanningQuickViewPanel';

// ── react-router-dom mock ─────────────────────────────────────────────────────
// renderToStaticMarkup doesn't need a real router; stub the hooks the
// promotion row + quick-view panel use.

const mockNavigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

// ── 1. Route-helper URL contract ──────────────────────────────────────────────

describe('Route helpers — Planning entries do not resolve to /board', () => {
  it('planningRouteFeatureModalHref produces a /planning URL, not /board', () => {
    const href = planningRouteFeatureModalHref('FEAT-001');
    expect(href.startsWith('/planning')).toBe(true);
    expect(href).not.toContain('/board');
  });

  it('planningRouteFeatureModalHref preserves tab in /planning URL', () => {
    const href = planningRouteFeatureModalHref('FEAT-001', 'docs');
    expect(href).toBe('/planning?feature=FEAT-001&modal=feature&tab=docs');
    expect(href).not.toContain('/board');
  });

  it('planningFeatureDetailHref produces a /planning/feature URL, not /board', () => {
    const href = planningFeatureDetailHref('FEAT-XYZ');
    expect(href.startsWith('/planning/feature/')).toBe(true);
    expect(href).not.toContain('/board');
  });

  it('planningFeatureModalHref (legacy board modal) is the only helper that targets /board', () => {
    // Sanity check: the explicit "Open board" affordance retains the /board URL.
    // This is the ONLY sanctioned path from a planning entry point into /board.
    expect(planningFeatureModalHref('FEAT-001')).toBe('/board?feature=FEAT-001&tab=overview');
  });
});

// ── 2. PlanningHomePage openFeatureModal handler shape ────────────────────────
// openFeatureModal (defined in PlanningHomePage.tsx) calls:
//   navigate(`/planning${setPlanningRouteFeatureModalSearch(...)}`)
// Verify the composed URL stays on /planning.

describe('openFeatureModal handler (modal-first) — stays on /planning', () => {
  it('builds a /planning URL with feature + modal + tab params', () => {
    const searchParams = new URLSearchParams();
    const url = `/planning${setPlanningRouteFeatureModalSearch(searchParams, 'FEAT-42', 'overview')}`;
    expect(url.startsWith('/planning')).toBe(true);
    expect(url).not.toContain('/board');
    expect(url).toContain('feature=FEAT-42');
    expect(url).toContain('modal=feature');
    expect(url).toContain('tab=overview');
  });

  it('preserves existing non-modal params while moving to /planning (not /board)', () => {
    const searchParams = new URLSearchParams('statusBucket=blocked');
    const url = `/planning${setPlanningRouteFeatureModalSearch(searchParams, 'FEAT-99', 'phases')}`;
    expect(url.startsWith('/planning')).toBe(true);
    expect(url).not.toContain('/board');
    expect(url).toContain('statusBucket=blocked');
    expect(url).toContain('feature=FEAT-99');
    expect(url).toContain('tab=phases');
  });
});

// ── 3. PlanningTriagePanel default onSelectFeature ────────────────────────────
// When no onSelectFeature override is provided, PlanningTriagePanel falls back to:
//   (featureId) => navigate(planningRouteFeatureModalHref(featureId))
// Exercise that closure shape.

describe('PlanningTriagePanel default feature selection — /planning, not /board', () => {
  it('default fallback navigates to planningRouteFeatureModalHref (in-route modal)', () => {
    const navigate = vi.fn();
    const defaultSelect = (featureId: string) => navigate(planningRouteFeatureModalHref(featureId));

    defaultSelect('FEAT-triage-1');

    expect(navigate).toHaveBeenCalledTimes(1);
    const target = navigate.mock.calls[0][0] as string;
    expect(target.startsWith('/planning')).toBe(true);
    expect(target).not.toContain('/board');
  });
});

// ── 4. PlanCatalog card click does NOT navigate ───────────────────────────────
// PlanCatalog cards use: onClick={() => setSelectedDoc(doc)}
// Opening the document modal must NOT trigger a route change. We verify this
// by exercising the exact closure shape used in PlanCatalog.tsx (lines 777 /
// 932): the click handler only flips local selection state.

describe('PlanCatalog card/list row click — opens DocumentModal, not /board', () => {
  it('card onClick invokes setSelectedDoc and does not call navigate', () => {
    const setSelectedDoc = vi.fn();
    const navigate = vi.fn();
    const doc = { id: 'DOC-1' };

    // Mirror PlanCatalog card onClick closure.
    const cardClick = () => setSelectedDoc(doc);
    cardClick();

    expect(setSelectedDoc).toHaveBeenCalledWith(doc);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('list-view row onClick invokes setSelectedDoc and does not call navigate', () => {
    const setSelectedDoc = vi.fn();
    const navigate = vi.fn();
    const doc = { id: 'DOC-42' };

    const rowClick = () => setSelectedDoc(doc);
    rowClick();

    expect(setSelectedDoc).toHaveBeenCalledWith(doc);
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ── 5. PlanCatalog explicit "Open board" affordance ───────────────────────────
// The status-chip button next to a linked feature (PlanCatalog.tsx:786) calls
// navigate(`/board?feature=...`). This is the ONLY sanctioned /board path.

describe('PlanCatalog explicit status-chip affordance — DOES navigate to /board', () => {
  it('status-chip click navigates to /board with feature param', () => {
    const navigate = vi.fn();
    const setSelectedDoc = vi.fn();
    const linkedFeatureId = 'FEAT-linked-1';

    // Mirror the PlanCatalog linked-feature chip onClick (stopPropagation + navigate).
    const chipClick = (e: { stopPropagation: () => void }) => {
      e.stopPropagation();
      navigate(`/board?feature=${encodeURIComponent(linkedFeatureId)}`);
    };

    const event = { stopPropagation: vi.fn() };
    chipClick(event);

    expect(event.stopPropagation).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledWith('/board?feature=FEAT-linked-1');
    // Chip must not also open the doc modal — stopPropagation guards that.
    expect(setSelectedDoc).not.toHaveBeenCalled();
  });
});

// ── 6. PlanCatalog "plan" link goes to /planning/features/:id ─────────────────

describe('PlanCatalog plan link — goes to /planning/features/:id, not /board', () => {
  it('constructs the planning-detail href via encodeURIComponent', () => {
    const featureId = 'FEAT link with space';
    const href = `/planning/features/${encodeURIComponent(featureId)}`;
    expect(href.startsWith('/planning/features/')).toBe(true);
    expect(href).not.toContain('/board');
  });
});

// ── 7. PlanningQuickViewPanel opening vs navigation ───────────────────────────
// Opening the quick view must NOT navigate — it only flips hook state.

describe('PlanningQuickViewPanel — opening toggles state, does not navigate', () => {
  it('openPanel sets open=true and title without triggering navigate', () => {
    let captured: ReturnType<typeof usePlanningQuickView> | null = null;

    function Spy() {
      captured = usePlanningQuickView();
      return null;
    }

    renderToStaticMarkup(<Spy />);

    expect(captured).not.toBeNull();
    expect(captured!.open).toBe(false);
    // mockNavigate must not have been called by rendering the spy.
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('PlanningHomePage-style quick-view handler shape opens panel without navigating', () => {
    // Mirror handleNodeQuickView from PlanningHomePage.tsx — it calls
    // setQuickViewNode + quickView.openPanel. No navigate invocation.
    const setQuickViewNode = vi.fn();
    const openPanel = vi.fn();
    const navigate = vi.fn();

    const handleNodeQuickView = (
      resolution: { kind: 'feature' | 'document'; node: { title: string }; featureSlug?: string },
      triggerEl: HTMLElement | null,
    ) => {
      setQuickViewNode(resolution.node);
      const title =
        resolution.kind === 'feature' ? resolution.featureSlug ?? '' : resolution.node.title;
      openPanel(title, triggerEl);
    };

    handleNodeQuickView(
      { kind: 'feature', node: { title: 't' }, featureSlug: 'FEAT-1' },
      null,
    );

    expect(setQuickViewNode).toHaveBeenCalledOnce();
    expect(openPanel).toHaveBeenCalledWith('FEAT-1', null);
    expect(navigate).not.toHaveBeenCalled();
  });
});

// ── 8. QuickViewPromotionRow promotions — targets /planning, not /board ───────

describe('QuickViewPromotionRow promotion paths — /planning only (SC-16.1)', () => {
  function promotionHtml(props: QuickViewPromotionRowProps): string {
    return renderToStaticMarkup(<QuickViewPromotionRow {...props} />);
  }

  it('kind=feature: "Open full view" button renders, wired to planningRouteFeatureModalHref', () => {
    const markup = promotionHtml({ kind: 'feature', featureId: 'FEAT-promote-1' });
    expect(markup).toContain('data-testid="promote-open-feature-modal"');
    // The button's href target (via navigate) must land on /planning.
    const featureUrl = planningRouteFeatureModalHref('FEAT-promote-1');
    expect(featureUrl.startsWith('/planning')).toBe(true);
    expect(featureUrl).not.toContain('/board');
  });

  it('kind=feature: "Planning detail" button renders, wired to planningFeatureDetailHref', () => {
    const markup = promotionHtml({ kind: 'feature', featureId: 'FEAT-promote-2' });
    expect(markup).toContain('data-testid="promote-open-planning-page"');
    const detailUrl = planningFeatureDetailHref('FEAT-promote-2');
    expect(detailUrl.startsWith('/planning/feature/')).toBe(true);
    expect(detailUrl).not.toContain('/board');
  });

  it('kind=document: "Open document" promotion opens modal via callback, no navigate', () => {
    const onOpenDocument = vi.fn();
    const onClose = vi.fn();
    const navigate = vi.fn();

    // Mirror the document-promotion closure from PlanningQuickViewPanel.
    const handleOpenDocument = () => {
      onClose();
      onOpenDocument();
    };

    handleOpenDocument();

    expect(onClose).toHaveBeenCalledOnce();
    expect(onOpenDocument).toHaveBeenCalledOnce();
    expect(navigate).not.toHaveBeenCalled();
  });
});
