/**
 * PCP-708: Unit tests for planning route helpers.
 *
 * Tests all three helpers exported from services/planningRoutes.ts:
 *   - planningFeatureModalHref
 *   - planningRouteFeatureModalHref
 *   - planningFeatureDetailHref
 *   - planningArtifactsHref
 *
 * Coverage:
 *   1. planningFeatureModalHref — default tab (overview)
 *   2. planningFeatureModalHref — explicit valid tab
 *   3. planningFeatureModalHref — every supported tab variant
 *   4. planningFeatureDetailHref — basic slug
 *   5. planningArtifactsHref — known artifact type slug
 *   6. URL-encoding — ids with spaces
 *   7. URL-encoding — ids with slash
 *   8. URL-encoding — ids with special chars (#, &, ?)
 *   9. Empty featureId is passed through (callers own validation)
 */
import { describe, expect, it } from 'vitest';

import {
  planningArtifactsHref,
  planningFeatureDetailHref,
  planningFeatureModalHref,
  planningRouteFeatureModalHref,
  removePlanningRouteFeatureModalSearch,
  resolvePlanningRouteFeatureModalState,
  setPlanningRouteFeatureModalSearch,
  type PlanningFeatureModalTab,
} from '../planningRoutes';

describe('planningFeatureModalHref', () => {
  it('defaults to overview tab', () => {
    expect(planningFeatureModalHref('feat-1')).toBe(
      '/board?feature=feat-1&tab=overview',
    );
  });

  it('accepts an explicit tab', () => {
    expect(planningFeatureModalHref('feat-1', 'docs')).toBe(
      '/board?feature=feat-1&tab=docs',
    );
  });

  it('produces correct paths for every supported tab', () => {
    const tabs: PlanningFeatureModalTab[] = [
      'overview',
      'phases',
      'docs',
      'relations',
      'sessions',
      'history',
      'test-status',
    ];
    for (const tab of tabs) {
      const href = planningFeatureModalHref('feat-1', tab);
      expect(href).toBe(`/board?feature=feat-1&tab=${tab}`);
    }
  });

  it('URL-encodes featureId with spaces', () => {
    expect(planningFeatureModalHref('my feature')).toBe(
      '/board?feature=my%20feature&tab=overview',
    );
  });

  it('URL-encodes featureId with slash', () => {
    expect(planningFeatureModalHref('ns/feat-1')).toBe(
      '/board?feature=ns%2Ffeat-1&tab=overview',
    );
  });

  it('URL-encodes featureId with special chars', () => {
    expect(planningFeatureModalHref('feat#1&x=2?y=3')).toBe(
      '/board?feature=feat%231%26x%3D2%3Fy%3D3&tab=overview',
    );
  });

  it('passes empty featureId through without crashing', () => {
    const href = planningFeatureModalHref('');
    expect(href).toBe('/board?feature=&tab=overview');
  });
});

describe('planningRouteFeatureModalHref', () => {
  it('keeps feature modal links under /planning', () => {
    expect(planningRouteFeatureModalHref('feat-1')).toBe(
      '/planning?feature=feat-1&modal=feature&tab=overview',
    );
  });

  it('accepts an explicit tab', () => {
    expect(planningRouteFeatureModalHref('feat-1', 'docs')).toBe(
      '/planning?feature=feat-1&modal=feature&tab=docs',
    );
  });

  it('URL-encodes featureId', () => {
    expect(planningRouteFeatureModalHref('ns/feat 1')).toBe(
      '/planning?feature=ns%2Ffeat%201&modal=feature&tab=overview',
    );
  });
});

describe('resolvePlanningRouteFeatureModalState', () => {
  it('parses a planning feature modal deep link', () => {
    expect(
      resolvePlanningRouteFeatureModalState(
        new URLSearchParams('feature=feat-1&modal=feature&tab=docs'),
      ),
    ).toEqual({ featureId: 'feat-1', tab: 'docs' });
  });

  it('defaults invalid or missing tabs to overview', () => {
    expect(
      resolvePlanningRouteFeatureModalState(
        new URLSearchParams('feature=feat-1&modal=feature&tab=bogus'),
      ),
    ).toEqual({ featureId: 'feat-1', tab: 'overview' });
  });

  it('does not resolve without modal=feature and feature', () => {
    expect(resolvePlanningRouteFeatureModalState(new URLSearchParams('feature=feat-1'))).toBeNull();
    expect(resolvePlanningRouteFeatureModalState(new URLSearchParams('modal=feature'))).toBeNull();
  });
});

describe('removePlanningRouteFeatureModalSearch', () => {
  it('removes modal params while preserving unrelated planning search params', () => {
    expect(
      removePlanningRouteFeatureModalSearch(
        new URLSearchParams('feature=feat-1&modal=feature&tab=docs&density=compact'),
      ),
    ).toBe('?density=compact');
  });

  it('returns an empty search string when only modal params were present', () => {
    expect(
      removePlanningRouteFeatureModalSearch(
        new URLSearchParams('feature=feat-1&modal=feature&tab=docs'),
      ),
    ).toBe('');
  });
});

describe('setPlanningRouteFeatureModalSearch', () => {
  it('sets modal params while preserving unrelated planning search params', () => {
    expect(
      setPlanningRouteFeatureModalSearch(
        new URLSearchParams('density=compact'),
        'feat-1',
        'docs',
      ),
    ).toBe('?density=compact&feature=feat-1&modal=feature&tab=docs');
  });
});

describe('planningFeatureDetailHref', () => {
  it('produces /planning/feature/<id>', () => {
    expect(planningFeatureDetailHref('feat-1')).toBe('/planning/feature/feat-1');
  });

  it('URL-encodes featureId with spaces', () => {
    expect(planningFeatureDetailHref('my feature')).toBe(
      '/planning/feature/my%20feature',
    );
  });

  it('URL-encodes featureId with slash', () => {
    expect(planningFeatureDetailHref('ns/feat-1')).toBe(
      '/planning/feature/ns%2Ffeat-1',
    );
  });

  it('URL-encodes featureId with special chars', () => {
    expect(planningFeatureDetailHref('feat#1&x=2')).toBe(
      '/planning/feature/feat%231%26x%3D2',
    );
  });
});

describe('planningArtifactsHref', () => {
  it('produces /planning/artifacts/<type>', () => {
    expect(planningArtifactsHref('design-specs')).toBe(
      '/planning/artifacts/design-specs',
    );
  });

  it('handles all known artifact type slugs', () => {
    const types = [
      'design-specs',
      'prds',
      'implementation-plans',
      'progress',
      'contexts',
      'reports',
    ] as const;
    for (const type of types) {
      expect(planningArtifactsHref(type)).toBe(`/planning/artifacts/${type}`);
    }
  });

  it('URL-encodes type with special chars', () => {
    expect(planningArtifactsHref('my type/x')).toBe(
      '/planning/artifacts/my%20type%2Fx',
    );
  });
});
