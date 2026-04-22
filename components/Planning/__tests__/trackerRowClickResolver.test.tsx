/**
 * P14-002: Tracker/intake row-click resolver tests.
 *
 * Tests the `resolveNodeClick` branching logic:
 *   - Nodes with `featureSlug` → kind='feature'
 *   - Nodes without `featureSlug` → kind='document'
 *
 * These tests exercise the pure resolver function directly — no DOM, no
 * rendering required. Consistent with the renderToStaticMarkup-based approach
 * used by the rest of the Planning test suite.
 *
 * Acceptance criteria (SC-14.2):
 *   - Feature rows → resolution.kind === 'feature' with featureSlug
 *   - Doc-only rows → resolution.kind === 'document'
 *   - Decision is observable from the resolver output
 */

import { describe, expect, it } from 'vitest';
import { resolveNodeClick, type NodeClickResolution } from '../TrackerIntakePanel';
import type { PlanningNode } from '../../../types';

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeNode(overrides: Partial<PlanningNode> = {}): PlanningNode {
  return {
    id: 'node-1',
    type: 'tracker',
    path: 'docs/tracker.md',
    title: 'Test Node',
    featureSlug: '',
    rawStatus: 'open',
    effectiveStatus: 'open',
    mismatchState: { state: 'aligned', reason: '', isMismatch: false, evidence: [] },
    updatedAt: '',
    ...overrides,
  };
}

// ── resolveNodeClick ──────────────────────────────────────────────────────────

describe('resolveNodeClick — feature-first branching', () => {
  it('node with featureSlug → kind=feature', () => {
    const node = makeNode({ featureSlug: 'FEAT-101' });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('feature');
  });

  it('node with featureSlug → featureSlug is forwarded', () => {
    const node = makeNode({ featureSlug: 'FEAT-202' });
    const result = resolveNodeClick(node) as Extract<NodeClickResolution, { kind: 'feature' }>;
    expect(result.featureSlug).toBe('FEAT-202');
  });

  it('node with featureSlug → node reference is preserved', () => {
    const node = makeNode({ featureSlug: 'FEAT-303', title: 'Feature node' });
    const result = resolveNodeClick(node);
    expect(result.node).toBe(node);
  });

  it('node without featureSlug → kind=document', () => {
    const node = makeNode({ featureSlug: "" });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('document');
  });

  it('node with empty string featureSlug → kind=document (falsy)', () => {
    // An empty string is falsy — treated as no slug.
    const node = makeNode({ featureSlug: '' });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('document');
  });

  it('doc-only node → node reference is preserved', () => {
    const node = makeNode({ featureSlug: "", title: 'Doc-only node' });
    const result = resolveNodeClick(node);
    expect(result.node).toBe(node);
  });

  it('tracker type node with featureSlug → feature', () => {
    const node = makeNode({ type: 'tracker', featureSlug: 'FEAT-500' });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('feature');
  });

  it('design_spec node without featureSlug → document', () => {
    const node = makeNode({ type: 'design_spec', featureSlug: "" });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('document');
  });

  it('prd node with featureSlug → feature (synthetic stale node case)', () => {
    // Mirrors the synthetic PlanningNode created for stale feature summaries
    const syntheticNode: PlanningNode = {
      id: 'feature-stale-FEAT-999',
      type: 'prd',
      path: '',
      title: 'Stale Feature',
      featureSlug: 'FEAT-999',
      rawStatus: 'stale',
      effectiveStatus: 'stale',
      mismatchState: {
        state: 'stale',
        reason: 'Feature marked stale at project level',
        isMismatch: true,
        evidence: [],
      },
      updatedAt: '',
    };
    const result = resolveNodeClick(syntheticNode);
    expect(result.kind).toBe('feature');
    if (result.kind === 'feature') {
      expect(result.featureSlug).toBe('FEAT-999');
    }
  });

  it('context node without featureSlug → document', () => {
    const node = makeNode({ type: 'context', featureSlug: "", path: 'docs/ctx.md' });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('document');
  });
});

// ── Discriminated union type narrowing ────────────────────────────────────────

describe('resolveNodeClick — TypeScript discriminated union', () => {
  it('feature result has featureSlug property', () => {
    const node = makeNode({ featureSlug: 'FEAT-001' });
    const result = resolveNodeClick(node);
    // TypeScript narrowing: accessing .featureSlug only valid on kind='feature'
    if (result.kind === 'feature') {
      expect(typeof result.featureSlug).toBe('string');
    } else {
      // If we somehow got document, fail explicitly
      expect(result.kind).toBe('feature');
    }
  });

  it('document result does NOT expose featureSlug (kind is document)', () => {
    const node = makeNode({ featureSlug: "" });
    const result = resolveNodeClick(node);
    expect(result.kind).toBe('document');
    // Confirm no .featureSlug on the document variant
    expect('featureSlug' in result).toBe(false);
  });
});
