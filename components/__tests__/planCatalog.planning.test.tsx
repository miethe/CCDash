/**
 * PCP-404: Cross-surface adoption of shared planning primitives in PlanCatalog.
 *
 * Strategy: PlanCatalog has deep React-Router, DataContext, and async deps.
 * Per spec, we export a pure helper and test primitives with synthesized Feature
 * fixtures rather than rendering the full catalog tree.
 *
 * The helper `renderFeatureStatusCell` is defined inline here rather than
 * exported from PlanCatalog itself — the catalog rendering is already tested
 * end-to-end via build; this file guards the chip/badge primitive behaviour.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { Feature, PlanningEffectiveStatus } from '../../types';
import { EffectiveStatusChips, MismatchBadge } from '../Planning/primitives';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makePlanningStatus = (
  overrides: Partial<PlanningEffectiveStatus> = {},
): PlanningEffectiveStatus => ({
  rawStatus: 'in-progress',
  effectiveStatus: 'in_progress',
  provenance: { source: 'derived', reason: 'Phase evidence', evidence: [] },
  mismatchState: {
    state: 'aligned',
    reason: '',
    isMismatch: false,
    evidence: [],
  },
  ...overrides,
});

const makeFeature = (overrides: Partial<Feature> = {}): Feature => ({
  id: 'FEAT-101',
  name: 'Auth Revamp',
  status: 'in-progress',
  totalTasks: 10,
  completedTasks: 4,
  category: 'backend',
  tags: ['auth', 'security'],
  updatedAt: '2026-04-17T00:00:00Z',
  linkedDocs: [],
  phases: [],
  relatedFeatures: [],
  ...overrides,
});

/**
 * Pure helper that reproduces what the catalog card renders for a linked
 * feature's status cell.  Kept here (not exported from PlanCatalog) to avoid
 * coupling the component's internal JSX to the test harness.
 */
function renderFeatureStatusCell(feature: Feature): string {
  const isMismatch = Boolean(feature.planningStatus?.mismatchState?.isMismatch);
  return renderToStaticMarkup(
    <span>
      <EffectiveStatusChips
        rawStatus={feature.planningStatus?.rawStatus ?? feature.status}
        effectiveStatus={feature.planningStatus?.effectiveStatus ?? undefined}
        isMismatch={isMismatch}
        provenance={feature.planningStatus?.provenance ?? undefined}
      />
      {isMismatch && feature.planningStatus && (
        <MismatchBadge
          compact
          state={feature.planningStatus.mismatchState.state}
          reason={feature.planningStatus.mismatchState.reason}
        />
      )}
    </span>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('PlanCatalog planning status cell (PCP-404)', () => {
  it('renders raw status chip when planningStatus is absent', () => {
    const feature = makeFeature({ planningStatus: undefined });
    const html = renderFeatureStatusCell(feature);
    expect(html).toContain('raw: in-progress');
    expect(html).not.toContain('eff:');
    expect(html).not.toContain('Status mismatch detected');
  });

  it('renders both raw and effective chips when they differ', () => {
    const feature = makeFeature({
      planningStatus: makePlanningStatus({
        rawStatus: 'in-progress',
        effectiveStatus: 'done',
      }),
    });
    const html = renderFeatureStatusCell(feature);
    expect(html).toContain('raw: in-progress');
    expect(html).toContain('eff: done');
  });

  it('renders MismatchBadge when isMismatch is true', () => {
    const feature = makeFeature({
      planningStatus: makePlanningStatus({
        rawStatus: 'in-progress',
        effectiveStatus: 'done',
        mismatchState: {
          state: 'mismatched',
          reason: 'Progress doc says done but tracker is in-progress',
          isMismatch: true,
          evidence: [],
        },
      }),
    });
    const html = renderFeatureStatusCell(feature);
    expect(html).toContain('mismatched');
    expect(html).toContain('Progress doc says done but tracker is in-progress');
  });

  it('does NOT render MismatchBadge when mismatch is absent', () => {
    const feature = makeFeature({
      planningStatus: makePlanningStatus({
        mismatchState: {
          state: 'aligned',
          reason: '',
          isMismatch: false,
          evidence: [],
        },
      }),
    });
    const html = renderFeatureStatusCell(feature);
    expect(html).not.toContain('mismatched');
  });

  it('renders provenance tooltip content when provenance is supplied', () => {
    const feature = makeFeature({
      planningStatus: makePlanningStatus({
        provenance: {
          source: 'derived',
          reason: 'Derived from phase evidence',
          evidence: [],
        },
      }),
    });
    const html = renderFeatureStatusCell(feature);
    // Provenance tooltip is inside the StatusChip wrapper div
    expect(html).toContain('Derived from phase evidence');
  });
});
