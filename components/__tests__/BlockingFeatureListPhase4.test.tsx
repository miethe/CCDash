/**
 * P4-009: BlockingFeatureList Phase-4 Migration
 *
 * Verifies that BlockingFeatureList renders correctly from a FeatureCardDTO
 * (the unified feature surface payload) when the full FeatureDependencyState
 * is absent — no per-feature /api/features/{id}/... fetch required.
 *
 * Scenarios:
 *  1. Card with blocking signals → renders blocker chip and summary text.
 *  2. Card with no blocking signals → renders "no unresolved blockers" message.
 *  3. Card with blocking reason → blocking reason text rendered.
 *  4. Backward compat: dependencyState still works unchanged (regression guard).
 *  5. onOpenFeature callback rendered when card is blocked + handler provided.
 *
 * Uses renderToStaticMarkup (same pattern as ProjectBoardCardMetrics).
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import type { FeatureCardDTO } from '../../services/featureSurface';
import type { FeatureDependencyState } from '../../types';
import { BlockingFeatureList } from '../BlockingFeatureList';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BLOCKED_CARD: FeatureCardDTO = {
  id: 'feat-blocked-1',
  name: 'Blocked Feature',
  status: 'in-progress',
  effectiveStatus: 'in-progress',
  category: 'backend',
  tags: [],
  summary: '',
  descriptionPreview: '',
  priority: 'high',
  riskLevel: 'high',
  complexity: 'high',
  totalTasks: 10,
  completedTasks: 2,
  deferredTasks: 0,
  phaseCount: 3,
  plannedAt: '2026-01-01T00:00:00Z',
  startedAt: '2026-02-01T00:00:00Z',
  completedAt: '',
  updatedAt: '2026-04-20T00:00:00Z',
  documentCoverage: { present: [], missing: [], countsByType: {} },
  qualitySignals: {
    blockerCount: 2,
    atRiskTaskCount: 1,
    hasBlockingSignals: true,
    testImpact: '',
    integritySignalRefs: [],
  },
  dependencyState: {
    state: 'blocked',
    blockingReason: 'Depends on upstream API changes.',
    blockedByCount: 2,
    readyDependencyCount: 0,
  },
  primaryDocuments: [],
  familyPosition: null,
  relatedFeatureCount: 0,
  precision: 'exact',
  freshness: null,
};

const UNBLOCKED_CARD: FeatureCardDTO = {
  ...BLOCKED_CARD,
  id: 'feat-clear-1',
  name: 'Clear Feature',
  qualitySignals: {
    blockerCount: 0,
    atRiskTaskCount: 0,
    hasBlockingSignals: false,
    testImpact: '',
    integritySignalRefs: [],
  },
  dependencyState: {
    state: 'unblocked',
    blockingReason: '',
    blockedByCount: 0,
    readyDependencyCount: 2,
  },
};

const LEGACY_DEPENDENCY_STATE: FeatureDependencyState = {
  state: 'blocked',
  dependencyCount: 1,
  resolvedDependencyCount: 0,
  blockedDependencyCount: 1,
  unknownDependencyCount: 0,
  blockingFeatureIds: ['feat-upstream-1'],
  blockingDocumentIds: ['doc-1'],
  firstBlockingDependencyId: 'feat-upstream-1',
  blockingReason: 'Legacy blocking reason',
  completionEvidence: [],
  dependencies: [
    {
      dependencyFeatureId: 'feat-upstream-1',
      dependencyFeatureName: 'Upstream Feature',
      dependencyStatus: 'in-progress',
      dependencyCompletionEvidence: [],
      blockingDocumentIds: ['doc-1'],
      blockingReason: 'Still in progress',
      resolved: false,
      state: 'blocked',
    },
  ],
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('P4-009 — BlockingFeatureList: card summary path (blocked card)', () => {
  it('renders blocking chip with blocker count from FeatureCardDTO.qualitySignals', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={BLOCKED_CARD} />,
    );
    expect(html).toContain('2 blockers');
  });

  it('renders summary text indicating blocking signals exist', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={BLOCKED_CARD} />,
    );
    expect(html).toContain('blocking signals');
  });

  it('renders the blocking reason from FeatureCardDTO.dependencyState', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={BLOCKED_CARD} />,
    );
    expect(html).toContain('Depends on upstream API changes.');
  });

  it('does not render the "no unresolved blockers" fallback when blocked', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={BLOCKED_CARD} />,
    );
    expect(html).not.toContain('no unresolved blocker records');
  });
});

describe('P4-009 — BlockingFeatureList: card summary path (unblocked card)', () => {
  it('renders "no unresolved blockers" message for clear card', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={UNBLOCKED_CARD} />,
    );
    expect(html).toContain('No unresolved blockers');
  });

  it('does not render blocker count chip for unblocked card', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={UNBLOCKED_CARD} />,
    );
    // No "N blockers" chip — the only "blocker" text is in the "no unresolved
    // blocker records" fallback message, not in a blocker-count badge.
    expect(html).not.toMatch(/\d+\s+blocker/);
    expect(html).not.toContain('ShieldAlert');
  });
});

describe('P4-009 — BlockingFeatureList: onOpenFeature rendered when blocked', () => {
  it('renders Open feature button when handler provided and card is blocked', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={BLOCKED_CARD} onOpenFeature={vi.fn()} />,
    );
    expect(html).toContain('Open feature');
  });

  it('does not render Open feature button when no handler provided', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList featureCard={BLOCKED_CARD} />,
    );
    expect(html).not.toContain('Open feature');
  });
});

describe('P4-009 — BlockingFeatureList: backward compat (legacy dependencyState)', () => {
  it('renders per-blocker list when dependencyState is present (legacy path)', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList dependencyState={LEGACY_DEPENDENCY_STATE} />,
    );
    expect(html).toContain('Upstream Feature');
  });

  it('legacy path renders blocking reason from dependency entry', () => {
    const html = renderToStaticMarkup(
      <BlockingFeatureList dependencyState={LEGACY_DEPENDENCY_STATE} />,
    );
    expect(html).toContain('Still in progress');
  });

  it('dependencyState takes priority over featureCard when both are provided', () => {
    // If both props are passed, the legacy dependencyState path should run
    // (featureCard card-summary path only activates when dependencyState is absent)
    const html = renderToStaticMarkup(
      <BlockingFeatureList
        dependencyState={LEGACY_DEPENDENCY_STATE}
        featureCard={BLOCKED_CARD}
      />,
    );
    // Legacy per-blocker item name should appear
    expect(html).toContain('Upstream Feature');
    // Card-path-only copy should NOT appear
    expect(html).not.toContain('Open the feature detail to inspect');
  });
});

describe('P4-009 — BlockingFeatureList: null/undefined guards', () => {
  it('renders without crashing when neither prop provided', () => {
    const html = renderToStaticMarkup(<BlockingFeatureList />);
    expect(html).toContain('no unresolved blocker records');
  });

  it('renders without crashing when featureCard is null', () => {
    const html = renderToStaticMarkup(<BlockingFeatureList featureCard={null} />);
    expect(html).toContain('no unresolved blocker records');
  });
});

// ── Source-level proof ────────────────────────────────────────────────────────

import * as fs from 'node:fs';
import * as path from 'node:path';

describe('P4-009 — BlockingFeatureList source-level proof', () => {
  const sourceFile = path.resolve(__dirname, '../BlockingFeatureList.tsx');
  const source = fs.readFileSync(sourceFile, 'utf8');

  it('accepts featureCard prop of type FeatureCardDTO', () => {
    expect(source).toContain('featureCard');
    expect(source).toContain('FeatureCardDTO');
  });

  it('no per-feature fetch calls in the component', () => {
    expect(source).not.toMatch(/fetch\(['"]/);
  });

  it('card summary path activates only when dependencyState is absent', () => {
    expect(source).toContain('!dependencyState && featureCard != null');
  });
});
