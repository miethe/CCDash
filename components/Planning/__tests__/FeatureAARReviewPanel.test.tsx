/**
 * T4-001: FeatureAARReviewPanel — quality-gate tests.
 *
 * Coverage:
 *   1. All 3 `triage_verdict` states render with distinct visual treatment
 *      (data-verdict attribute + verdict label text).
 *   2. Resilience: null correlation.confidence + empty session_ids + empty
 *      flags never crash — renders defined fallback text instead.
 *   3. Resilience: null flag.severity + empty evidence_refs never crash.
 *   4. Resilience: null correlation.featureId renders "no linked feature",
 *      never a broken link.
 *   5. Empty rollup (no entries) renders the empty state, not a crash.
 *   6. Loading state renders the loading affordance.
 *   7. Error state renders the error affordance (never throws).
 *   8. No active project renders the "no active project" fallback.
 *   9. featureId scoping: with a featureId, only entries whose
 *      correlation.featureId matches render; without one, all project
 *      entries render (existing project-wide behavior, unchanged).
 *
 * Strategy: mock `useAarReviewRollupQuery` directly and render via
 * `renderToStaticMarkup` — same approach as the rest of the Planning test
 * suite (see PlanningAgentSessionBoard.test.tsx) — no jsdom/QueryClientProvider
 * required since the hook itself is mocked out.
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { AarReviewEntry } from '@/types';

// ── Module-level mock ─────────────────────────────────────────────────────────

const mocks = vi.hoisted(() => ({
  queryResult: {
    data: [] as AarReviewEntry[] | undefined,
    isLoading: false,
    isError: false,
    error: null as Error | null,
  },
}));

vi.mock('../../../services/queries/aarReview', () => ({
  useAarReviewRollupQuery: () => mocks.queryResult,
}));

import { FeatureAARReviewPanel } from '../FeatureAARReviewPanel';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeEntry(overrides: Partial<AarReviewEntry> = {}): AarReviewEntry {
  return {
    schemaVersion: 2,
    status: 'ok',
    documentId: 'docs/aar/example.md',
    correlation: {
      strategy: 'explicit_session_ref',
      confidence: 1.0,
      sessionIds: ['sess-1'],
      featureId: 'FEAT-1',
    },
    flags: [],
    triageVerdict: 'surface_only',
    reasons: ['no flags triggered'],
    generatedAt: '2026-07-22T00:00:00Z',
    sourceRefs: ['docs/aar/example.md'],
    ...overrides,
  };
}

function render(
  entries: AarReviewEntry[] | undefined,
  opts: Partial<typeof mocks.queryResult> = {},
  featureId?: string | null,
): string {
  mocks.queryResult = {
    data: entries,
    isLoading: false,
    isError: false,
    error: null,
    ...opts,
  };
  return renderToStaticMarkup(<FeatureAARReviewPanel projectId="proj-1" featureId={featureId} />);
}

// ── Verdict states (all 3 must render distinctly) ────────────────────────────

describe('FeatureAARReviewPanel — triage verdict states', () => {
  it('renders surface_only with its distinct badge + label', () => {
    const html = render([makeEntry({ triageVerdict: 'surface_only' })]);
    expect(html).toContain('data-verdict="surface_only"');
    expect(html).toContain('Surface only');
  });

  it('renders deep_review_recommended with its distinct badge + label', () => {
    const html = render([
      makeEntry({
        documentId: 'docs/aar/deep.md',
        triageVerdict: 'deep_review_recommended',
      }),
    ]);
    expect(html).toContain('data-verdict="deep_review_recommended"');
    expect(html).toContain('Deep review recommended');
  });

  it('renders human_triage_required with its distinct badge + label', () => {
    const html = render([
      makeEntry({
        documentId: 'docs/aar/human.md',
        triageVerdict: 'human_triage_required',
        correlation: {
          strategy: null,
          confidence: null,
          sessionIds: [],
          featureId: null,
        },
        reasons: ['correlation confidence is missing/null; routing to human triage per the OQ-2 hard rule'],
      }),
    ]);
    expect(html).toContain('data-verdict="human_triage_required"');
    expect(html).toContain('Human triage required');
  });

  it('renders all 3 verdicts simultaneously with 3 distinct data-verdict values', () => {
    const html = render([
      makeEntry({ documentId: 'a.md', triageVerdict: 'surface_only' }),
      makeEntry({ documentId: 'b.md', triageVerdict: 'deep_review_recommended' }),
      makeEntry({ documentId: 'c.md', triageVerdict: 'human_triage_required' }),
    ]);
    expect(html).toContain('data-verdict="surface_only"');
    expect(html).toContain('data-verdict="deep_review_recommended"');
    expect(html).toContain('data-verdict="human_triage_required"');
  });

  it('renders a fallback badge for a null/unknown triage_verdict, never a crash', () => {
    expect(() => render([makeEntry({ triageVerdict: null })])).not.toThrow();
    const html = render([makeEntry({ triageVerdict: null })]);
    expect(html).toContain('data-verdict="unknown"');
    expect(html).toContain('Verdict pending');
  });
});

// ── Resilience: every optional §7.2 field absent/null ────────────────────────

describe('FeatureAARReviewPanel — resilience to null/absent optional fields', () => {
  it('null correlation.confidence renders "correlation pending", never a crash', () => {
    const entry = makeEntry({
      correlation: { strategy: 'two_hop_doc_feature_session', confidence: null, sessionIds: ['sess-1'], featureId: 'FEAT-2' },
    });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('correlation pending');
  });

  it('empty correlation.sessionIds renders "no linked sessions", never a crash', () => {
    const entry = makeEntry({
      correlation: { strategy: 'explicit_session_ref', confidence: 1.0, sessionIds: [], featureId: null },
    });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('no linked sessions');
  });

  it('null correlation.featureId renders "no linked feature", never a broken link', () => {
    const entry = makeEntry({
      correlation: { strategy: 'explicit_session_ref', confidence: 1.0, sessionIds: ['sess-1'], featureId: null },
    });
    const html = render([entry]);
    expect(html).toContain('no linked feature');
  });

  it('empty flags[] renders "no flags evaluated", never a crash', () => {
    const entry = makeEntry({ flags: [] });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('no flags evaluated');
  });

  it('a non-triggered flag with null severity + empty evidence_refs renders "not triggered" / "no evidence recorded", never a crash', () => {
    const entry = makeEntry({
      triageVerdict: 'deep_review_recommended',
      flags: [
        {
          flagId: 'context_ballooning',
          triggered: false,
          severity: null,
          evidenceRefs: [],
          rationale: null,
        },
      ],
    });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('not triggered');
    expect(html).toContain('no evidence recorded');
    expect(html).toContain('no rationale recorded');
  });

  it('a triggered flag with null severity renders "not evaluated" as its severity label, never a crash', () => {
    const entry = makeEntry({
      triageVerdict: 'deep_review_recommended',
      flags: [
        {
          flagId: 'weird_flag',
          triggered: true,
          severity: null,
          evidenceRefs: [],
          rationale: 'triggered without a resolved severity',
        },
      ],
    });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('not evaluated');
  });

  it('a triggered flag with evidence renders the evidence lines', () => {
    const entry = makeEntry({
      triageVerdict: 'deep_review_recommended',
      flags: [
        {
          flagId: 'missing_artifacts',
          triggered: true,
          severity: 'medium',
          evidenceRefs: ['components/Foo.tsx'],
          rationale: '1 of 2 claimed file(s) were not found among session-produced files.',
        },
      ],
    });
    const html = render([entry]);
    expect(html).toContain('components/Foo.tsx');
    expect(html).toContain('missing_artifacts');
  });

  it('empty reasons[] and sourceRefs[] never crash and render defined fallbacks', () => {
    const entry = makeEntry({ reasons: [], sourceRefs: [] });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('no source refs');
  });

  it('null generatedAt renders "generated at unknown", never a crash', () => {
    const entry = makeEntry({ generatedAt: null });
    const html = render([entry]);
    expect(html).toContain('generated at unknown');
  });

  it('empty documentId never crashes and falls back to a placeholder', () => {
    const entry = makeEntry({ documentId: '' });
    expect(() => render([entry])).not.toThrow();
    const html = render([entry]);
    expect(html).toContain('unknown document');
  });
});

// ── featureId scoping ─────────────────────────────────────────────────────────

describe('FeatureAARReviewPanel — featureId scoping', () => {
  it('with a featureId, only entries whose correlation.featureId matches render', () => {
    const html = render(
      [
        makeEntry({ documentId: 'a.md', correlation: { strategy: 'x', confidence: 1, sessionIds: ['s1'], featureId: 'FEAT-1' } }),
        makeEntry({ documentId: 'b.md', correlation: { strategy: 'x', confidence: 1, sessionIds: ['s2'], featureId: 'FEAT-2' } }),
        makeEntry({ documentId: 'c.md', correlation: { strategy: 'x', confidence: 1, sessionIds: ['s3'], featureId: 'FEAT-1' } }),
      ],
      {},
      'FEAT-1',
    );
    expect(html).toContain('a.md');
    expect(html).toContain('c.md');
    expect(html).not.toContain('b.md');
  });

  it('without a featureId, all project entries render (existing project-wide behavior)', () => {
    const html = render([
      makeEntry({ documentId: 'a.md', correlation: { strategy: 'x', confidence: 1, sessionIds: ['s1'], featureId: 'FEAT-1' } }),
      makeEntry({ documentId: 'b.md', correlation: { strategy: 'x', confidence: 1, sessionIds: ['s2'], featureId: 'FEAT-2' } }),
    ]);
    expect(html).toContain('a.md');
    expect(html).toContain('b.md');
  });

  it('a featureId that matches nothing renders the same empty state, never an error', () => {
    const html = render(
      [makeEntry({ documentId: 'a.md', correlation: { strategy: 'x', confidence: 1, sessionIds: ['s1'], featureId: 'FEAT-1' } })],
      {},
      'FEAT-999',
    );
    expect(html).toContain('data-testid="aar-review-empty-state"');
    expect(html).not.toContain('a.md');
  });
});

// ── Non-verdict states ────────────────────────────────────────────────────────

describe('FeatureAARReviewPanel — loading / error / empty / no-project states', () => {
  it('renders the loading affordance when isLoading', () => {
    mocks.queryResult = { data: undefined, isLoading: true, isError: false, error: null };
    const html = renderToStaticMarkup(<FeatureAARReviewPanel projectId="proj-1" />);
    expect(html).toContain('Loading AAR reviews');
  });

  it('renders the error affordance when isError, never throws', () => {
    mocks.queryResult = { data: undefined, isLoading: false, isError: true, error: new Error('boom') };
    expect(() =>
      renderToStaticMarkup(<FeatureAARReviewPanel projectId="proj-1" />),
    ).not.toThrow();
    mocks.queryResult = { data: undefined, isLoading: false, isError: true, error: new Error('boom') };
    const html = renderToStaticMarkup(<FeatureAARReviewPanel projectId="proj-1" />);
    expect(html).toContain('boom');
  });

  it('renders the empty state when the rollup has zero entries', () => {
    const html = render([]);
    expect(html).toContain('data-testid="aar-review-empty-state"');
    expect(html).toContain('No AAR reviews recorded for this project yet.');
  });

  it('renders "no active project" when projectId is null, never a crash', () => {
    expect(() => renderToStaticMarkup(<FeatureAARReviewPanel projectId={null} />)).not.toThrow();
    const html = renderToStaticMarkup(<FeatureAARReviewPanel projectId={null} />);
    expect(html).toContain('No active project selected.');
  });

  it('undefined data (query has not resolved) degrades to an empty rollup, never a crash', () => {
    mocks.queryResult = { data: undefined, isLoading: false, isError: false, error: null };
    expect(() => renderToStaticMarkup(<FeatureAARReviewPanel projectId="proj-1" />)).not.toThrow();
    const html = renderToStaticMarkup(<FeatureAARReviewPanel projectId="proj-1" />);
    expect(html).toContain('data-testid="aar-review-empty-state"');
  });
});
