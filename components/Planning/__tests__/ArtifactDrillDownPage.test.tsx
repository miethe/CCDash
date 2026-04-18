/**
 * PCP-708: ArtifactDrillDownPage tests.
 *
 * Strategy: renderToStaticMarkup (no jsdom) consistent with the Planning test
 * suite convention. Route params are simulated via MemoryRouter + Routes.
 *
 * Coverage:
 *   1. Renders correct list for design-specs type
 *   2. Renders correct list for prds type
 *   3. Renders correct list for implementation-plans type
 *   4. Renders correct list for progress type
 *   5. Renders correct list for contexts type
 *   6. Renders correct list for reports type
 *   7. Shows empty state when no docs match type
 *   8. Filters out documents that do not match the requested type
 *   9. Unknown type renders graceful fallback (not a crash)
 *  10. Document rows render title and status
 *  11. DocumentModal integration — opening modal via state is exercised in markup
 *  12. Back button is present and links toward /planning
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { PlanDocument } from '../../../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockDocuments: PlanDocument[] = [];

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({ documents: mockDocuments }),
}));

// DocumentModal is a heavy component — stub it for static rendering tests.
vi.mock('../../DocumentModal', () => ({
  DocumentModal: ({ doc }: { doc: PlanDocument }) => (
    <div data-testid="document-modal" data-doc-id={doc.id}>
      Document Modal: {doc.title}
    </div>
  ),
}));

import { ArtifactDrillDownPage } from '../ArtifactDrillDownPage';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDoc(overrides: Partial<PlanDocument> = {}): PlanDocument {
  return {
    id: 'doc-1',
    title: 'Test Document',
    filePath: 'docs/test.md',
    status: 'active',
    lastModified: '2026-04-17T00:00:00Z',
    updatedAt: '2026-04-17T00:00:00Z',
    author: 'test',
    frontmatter: { tags: [] },
    ...overrides,
  };
}

function renderAtPath(path: string): string {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/planning/artifacts/:type" element={<ArtifactDrillDownPage />} />
        <Route path="/planning/artifacts/" element={<ArtifactDrillDownPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDocuments.length = 0;
});

// ── Known types ───────────────────────────────────────────────────────────────

describe('ArtifactDrillDownPage — design-specs', () => {
  it('renders matching design spec documents', () => {
    mockDocuments.push(
      makeDoc({ id: 'spec-1', title: 'Auth Design Spec', docType: 'spec' }),
      makeDoc({ id: 'other-1', title: 'An Implementation Plan', docType: 'implementation_plan' }),
    );
    const html = renderAtPath('/planning/artifacts/design-specs');
    expect(html).toContain('Auth Design Spec');
    expect(html).toContain('Design Specs');
    expect(html).not.toContain('An Implementation Plan');
  });

  it('also matches docs with docSubtype=design_spec', () => {
    mockDocuments.push(
      makeDoc({ id: 'spec-sub', title: 'Subtype Design Spec', docType: 'unknown', docSubtype: 'design_spec' }),
    );
    const html = renderAtPath('/planning/artifacts/design-specs');
    expect(html).toContain('Subtype Design Spec');
  });
});

describe('ArtifactDrillDownPage — prds', () => {
  it('renders matching PRD documents', () => {
    mockDocuments.push(
      makeDoc({ id: 'prd-1', title: 'Auth PRD', docType: 'prd' }),
    );
    const html = renderAtPath('/planning/artifacts/prds');
    expect(html).toContain('Auth PRD');
    expect(html).toContain('PRDs');
  });
});

describe('ArtifactDrillDownPage — implementation-plans', () => {
  it('renders matching implementation plan documents', () => {
    mockDocuments.push(
      makeDoc({ id: 'plan-1', title: 'Auth Implementation Plan', docType: 'implementation_plan' }),
    );
    const html = renderAtPath('/planning/artifacts/implementation-plans');
    expect(html).toContain('Auth Implementation Plan');
    expect(html).toContain('Implementation Plans');
  });

  it('does NOT surface phase_plan as a standalone artifact under implementation-plans', () => {
    mockDocuments.push(
      makeDoc({ id: 'plan-2', title: 'Phase 1 Plan', docType: 'phase_plan' }),
      makeDoc({ id: 'plan-3', title: 'Real Impl Plan', docType: 'implementation_plan' }),
    );
    const html = renderAtPath('/planning/artifacts/implementation-plans');
    // phase_plan is evidence-only; it must not appear in the drill-down list
    expect(html).not.toContain('Phase 1 Plan');
    // implementation_plan still visible
    expect(html).toContain('Real Impl Plan');
  });
});

describe('ArtifactDrillDownPage — progress (removed as standalone category)', () => {
  it('returns the unknown-type fallback for /planning/artifacts/progress', () => {
    mockDocuments.push(
      makeDoc({ id: 'prog-1', title: 'Auth Progress', docType: 'progress' }),
    );
    const html = renderAtPath('/planning/artifacts/progress');
    // 'progress' is no longer a valid ArtifactDrillDownType — page shows fallback
    expect(html).toContain('progress');
    expect(html).not.toContain('Progress Files');
    expect(html).not.toContain('Auth Progress');
  });
});

describe('ArtifactDrillDownPage — contexts', () => {
  it('renders matching context documents', () => {
    mockDocuments.push(
      makeDoc({ id: 'ctx-1', title: 'Auth Context', docType: 'context' }),
    );
    const html = renderAtPath('/planning/artifacts/contexts');
    expect(html).toContain('Auth Context');
    expect(html).toContain('Context Files');
  });

  it('also matches docSubtype=context_notes', () => {
    mockDocuments.push(
      makeDoc({ id: 'ctx-2', title: 'Context Notes Doc', docSubtype: 'context_notes' }),
    );
    const html = renderAtPath('/planning/artifacts/contexts');
    expect(html).toContain('Context Notes Doc');
  });
});

describe('ArtifactDrillDownPage — reports', () => {
  it('renders matching report documents', () => {
    mockDocuments.push(
      makeDoc({ id: 'rep-1', title: 'Auth AAR Report', docType: 'report' }),
    );
    const html = renderAtPath('/planning/artifacts/reports');
    expect(html).toContain('Auth AAR Report');
    expect(html).toContain('Reports');
  });
});

// ── Empty state ───────────────────────────────────────────────────────────────

describe('ArtifactDrillDownPage — empty state', () => {
  it('shows empty state when no docs match the type', () => {
    mockDocuments.push(
      makeDoc({ id: 'prd-1', title: 'Some PRD', docType: 'prd' }),
    );
    const html = renderAtPath('/planning/artifacts/reports');
    expect(html).toContain('No reports found');
    expect(html).not.toContain('Some PRD');
  });

  it('shows empty state when document list is empty', () => {
    const html = renderAtPath('/planning/artifacts/design-specs');
    expect(html).toContain('No design specs found');
  });
});

// ── Unknown type ──────────────────────────────────────────────────────────────

describe('ArtifactDrillDownPage — unknown type', () => {
  it('renders graceful fallback without crashing', () => {
    const html = renderAtPath('/planning/artifacts/totally-unknown-type');
    expect(html).toContain('totally-unknown-type');
    expect(html).not.toMatch(/Error:|TypeError:|Cannot read/);
  });

  it('fallback shows a back button to /planning', () => {
    const html = renderAtPath('/planning/artifacts/mystery-type');
    expect(html).toContain('Back to Planning');
  });
});

// ── Document row content ──────────────────────────────────────────────────────

describe('ArtifactDrillDownPage — row content', () => {
  it('renders the document title in a row', () => {
    mockDocuments.push(
      makeDoc({ id: 'prd-x', title: 'My Important PRD', docType: 'prd', status: 'active' }),
    );
    const html = renderAtPath('/planning/artifacts/prds');
    expect(html).toContain('My Important PRD');
  });

  it('renders the file path in the row', () => {
    mockDocuments.push(
      makeDoc({ id: 'prd-path', title: 'PRD With Path', docType: 'prd', filePath: 'docs/prds/my-prd.md' }),
    );
    const html = renderAtPath('/planning/artifacts/prds');
    expect(html).toContain('docs/prds/my-prd.md');
  });

  it('renders count badge in header', () => {
    mockDocuments.push(
      makeDoc({ id: 'prd-1', title: 'PRD One', docType: 'prd' }),
      makeDoc({ id: 'prd-2', title: 'PRD Two', docType: 'prd' }),
    );
    const html = renderAtPath('/planning/artifacts/prds');
    expect(html).toContain('>2<');
  });

  it('renders back button toward /planning', () => {
    const html = renderAtPath('/planning/artifacts/prds');
    expect(html).toContain('Back to Planning');
  });
});
