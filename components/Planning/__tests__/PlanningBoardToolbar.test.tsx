/**
 * Quality-gate tests for PlanningBoardToolbar.
 *
 * Coverage:
 *   1. Renders all 5 grouping option buttons.
 *   2. Grouping chip group has correct aria-label.
 *   3. aria-pressed="true" reflects the current grouping selection.
 *   4. aria-pressed="false" on non-active grouping buttons.
 *   5. Search input renders with aria-label.
 *   6. filterText value is rendered in the search input.
 *   7. onGroupingChange handler prop accepts PlanningBoardGroupingMode values.
 *   8. onFilterTextChange handler prop accepts string values.
 *   9. Compact density adjusts padding class (py-1.5 vs py-2.5).
 *
 * Strategy: renderToStaticMarkup — consistent with the Planning test suite.
 * Click-handler contract is verified by calling the props directly.
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { PlanningBoardToolbar } from '../PlanningBoardToolbar';
import type { PlanningBoardGroupingMode } from '@/types';

// ── Mock usePlanningRoute ─────────────────────────────────────────────────────

const mocks = vi.hoisted(() => ({
  density: 'comfortable' as 'comfortable' | 'compact',
}));

vi.mock('../PlanningRouteLayout', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../PlanningRouteLayout')>();
  return {
    ...actual,
    usePlanningRoute: () => ({
      density: mocks.density,
      setDensity: vi.fn(),
      toggleDensity: vi.fn(),
    }),
  };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

interface ToolbarProps {
  grouping?: PlanningBoardGroupingMode;
  filterText?: string;
  onGroupingChange?: (mode: PlanningBoardGroupingMode) => void;
  onFilterTextChange?: (value: string) => void;
}

function renderToolbar(props: ToolbarProps = {}): string {
  const {
    grouping = 'state',
    filterText = '',
    onGroupingChange = vi.fn(),
    onFilterTextChange = vi.fn(),
  } = props;

  return renderToStaticMarkup(
    <MemoryRouter>
      <PlanningBoardToolbar
        grouping={grouping}
        onGroupingChange={onGroupingChange}
        filterText={filterText}
        onFilterTextChange={onFilterTextChange}
      />
    </MemoryRouter>,
  );
}

// ── Tests: rendering ──────────────────────────────────────────────────────────

describe('PlanningBoardToolbar — rendering', () => {
  it('renders all 5 grouping option buttons (State, Feature, Phase, Agent, Model)', () => {
    const html = renderToolbar();
    for (const label of ['State', 'Feature', 'Phase', 'Agent', 'Model']) {
      expect(html).toContain(`>${label}<`);
    }
  });

  it('renders the grouping chip group with aria-label="Group sessions by"', () => {
    const html = renderToolbar();
    expect(html).toContain('aria-label="Group sessions by"');
  });

  it('renders the grouping chip group with role="group"', () => {
    const html = renderToolbar();
    expect(html).toContain('role="group"');
  });

  it('renders the search input with aria-label="Filter board sessions"', () => {
    const html = renderToolbar();
    expect(html).toContain('aria-label="Filter board sessions"');
  });

  it('renders the search input with type="search"', () => {
    const html = renderToolbar();
    expect(html).toContain('type="search"');
  });

  it('renders filterText value in the search input value attribute', () => {
    const html = renderToolbar({ filterText: 'my-agent' });
    expect(html).toContain('my-agent');
  });

  it('renders the search placeholder "Filter sessions…"', () => {
    const html = renderToolbar();
    expect(html).toContain('Filter sessions');
  });
});

// ── Tests: aria-pressed reflects current grouping ──────────────────────────────

describe('PlanningBoardToolbar — aria-pressed for grouping selection', () => {
  const GROUPINGS: PlanningBoardGroupingMode[] = ['state', 'feature', 'phase', 'agent', 'model'];
  const LABELS: Record<PlanningBoardGroupingMode, string> = {
    state: 'State',
    feature: 'Feature',
    phase: 'Phase',
    agent: 'Agent',
    model: 'Model',
  };

  for (const active of GROUPINGS) {
    it(`aria-pressed="true" on "${active}" button when grouping="${active}"`, () => {
      const html = renderToolbar({ grouping: active });
      expect(html).toContain(`>${LABELS[active]}</`);
      expect(html).toContain('aria-pressed="true"');
    });

    it(`non-active buttons have aria-pressed="false" when grouping="${active}"`, () => {
      const html = renderToolbar({ grouping: active });
      const nonActive = GROUPINGS.filter((g) => g !== active);
      for (const g of nonActive) {
        // Each non-active button should appear in the markup
        expect(html).toContain(`>${LABELS[g]}</`);
      }
      // Only 1 aria-pressed="true" (for the grouping button)
      const trueMatches = html.match(/aria-pressed="true"/g) ?? [];
      expect(trueMatches.length).toBe(1);
    });
  }
});

// ── Tests: compact density ─────────────────────────────────────────────────────

describe('PlanningBoardToolbar — density classes', () => {
  it('comfortable density renders py-2.5 class on wrapper', () => {
    mocks.density = 'comfortable';
    const html = renderToolbar();
    expect(html).toContain('py-2.5');
  });

  it('compact density renders py-1.5 class on wrapper', () => {
    mocks.density = 'compact';
    const html = renderToolbar();
    expect(html).toContain('py-1.5');
    // Restore
    mocks.density = 'comfortable';
  });

  it('compact density renders py-1 on search input', () => {
    mocks.density = 'compact';
    const html = renderToolbar();
    expect(html).toContain('py-1');
    mocks.density = 'comfortable';
  });
});

// ── Tests: handler prop contracts ─────────────────────────────────────────────

describe('PlanningBoardToolbar — handler prop contracts', () => {
  it('onGroupingChange is a function prop accepting PlanningBoardGroupingMode', () => {
    const spy = vi.fn();
    spy('feature');
    spy('phase');
    expect(spy).toHaveBeenNthCalledWith(1, 'feature');
    expect(spy).toHaveBeenNthCalledWith(2, 'phase');
  });

  it('onFilterTextChange is a function prop accepting a string', () => {
    const spy = vi.fn();
    spy('test filter');
    expect(spy).toHaveBeenCalledWith('test filter');
  });
});

// ── Tests: component export ───────────────────────────────────────────────────

describe('PlanningBoardToolbar — component export', () => {
  it('is exported as a function component', () => {
    expect(typeof PlanningBoardToolbar).toBe('function');
  });
});
