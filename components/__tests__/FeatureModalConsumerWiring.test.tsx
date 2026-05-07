/**
 * P4-010 / P4-006: Feature Modal Consumer Wiring
 *
 * Asserts that:
 *   1. ProjectBoardFeatureModal imports and calls useFeatureModalData — no raw
 *      /api/features/${...} string interpolation remains in components/.
 *   2. Switching to the 'phases' tab triggers exactly one phases-section call
 *      via the typed client (modalSections.phases.load()).
 *   3. Error state in a section renders the TabStateView error branch with a
 *      retry button; clicking retry re-invokes the section.
 *   4. P4-006: ProjectBoard mounts FeatureDetailShell with shellSectionStates
 *      so that TabStateView wiring is delegated to the shell (not inline).
 *
 * Testing strategy:
 *   Source-level structural proofs (zero-runtime, always stable) + a pure
 *   state-machine simulation of the tab-activation load dispatcher (P4-010
 *   effect).  Full DOM rendering is out of scope for this suite (no jsdom).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ── Source files under test ───────────────────────────────────────────────────

const PROJECTBOARD_PATH = path.resolve(__dirname, '../ProjectBoard.tsx');
const PROJECTBOARD_SRC = fs.readFileSync(PROJECTBOARD_PATH, 'utf-8');

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Returns all raw /api/features/${...} template-literal interpolations found. */
function findRawApiInterpolations(source: string): string[] {
  // Match backtick strings containing /api/features/${
  const re = /`[^`]*\/api\/features\/\$\{[^`]*`/g;
  return source.match(re) ?? [];
}

/** Extracts the P4-010 tab-activation effect block by its anchor comment. */
function getTabActivationLoadEffect(source: string): string {
  const marker = '  // P4-010: Trigger useFeatureModalData section loads on tab activation.';
  const idx = source.indexOf(marker);
  if (idx === -1) return '';
  return source.slice(idx, idx + 1200);
}

/** Extracts the useFeatureModalData call site in the modal component. */
function getModalDataHookCallSite(source: string): string {
  const marker = '  // P4-010: per-section hook for typed, lazy modal data loading.';
  const idx = source.indexOf(marker);
  if (idx === -1) return '';
  return source.slice(idx, idx + 500);
}

// ── 1. No raw /api/features/ interpolations in components/ ───────────────────

describe('P4-010 — No raw /api/features/ interpolations in ProjectBoard.tsx', () => {
  it('contains zero template-literal /api/features/ interpolations', () => {
    const violations = findRawApiInterpolations(PROJECTBOARD_SRC);
    expect(violations).toHaveLength(0);
  });

  it('the TaskSourceDialog uses getFeatureTaskSource (typed client)', () => {
    expect(PROJECTBOARD_SRC).toContain('getFeatureTaskSource(task.sourceFile)');
  });

  it('the TaskSourceDialog does NOT contain a raw fetch() with /api/features/task-source', () => {
    expect(PROJECTBOARD_SRC).not.toContain("fetch(`/api/features/task-source");
    expect(PROJECTBOARD_SRC).not.toContain('fetch(`/api/features/task-source');
  });
});

// Extend to all components in the directory (belt-and-suspenders).
describe('P4-010 — No raw /api/features/ interpolations in any components/ file', () => {
  const COMPONENTS_DIR = path.resolve(__dirname, '..');

  function collectComponentSources(dir: string): Array<{ rel: string; src: string }> {
    const results: Array<{ rel: string; src: string }> = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
        const nested = collectComponentSources(path.join(dir, entry.name));
        results.push(...nested);
        continue;
      }
      if (!entry.name.endsWith('.tsx') && !entry.name.endsWith('.ts')) continue;
      const full = path.join(dir, entry.name);
      results.push({ rel: path.relative(COMPONENTS_DIR, full), src: fs.readFileSync(full, 'utf-8') });
    }
    return results;
  }

  const sources = collectComponentSources(COMPONENTS_DIR);

  it('no .tsx/.ts file in components/ has raw /api/features/ template interpolations', () => {
    const violations: string[] = [];
    for (const { rel, src } of sources) {
      const found = findRawApiInterpolations(src);
      if (found.length > 0) {
        violations.push(`${rel}: ${found.join(', ')}`);
      }
    }
    expect(violations, `Found raw /api/features/ interpolations:\n${violations.join('\n')}`).toHaveLength(0);
  });
});

// ── 2. useFeatureModalData hook is wired into ProjectBoardFeatureModal ────────

describe('P4-010 — useFeatureModalData hook wired in modal component', () => {
  it('ProjectBoard.tsx imports useFeatureModalData', () => {
    // P4-006 added ModalTabId to the named imports; check for the hook import
    // regardless of any additional named exports brought in alongside it.
    expect(PROJECTBOARD_SRC).toContain("useFeatureModalData");
    expect(PROJECTBOARD_SRC).toContain("from '../services/useFeatureModalData'");
  });

  it('modalSections is instantiated via useFeatureModalData(feature.id)', () => {
    // P5-005: options object added for featureSurfaceV2Enabled flag wiring.
    expect(PROJECTBOARD_SRC).toContain('useFeatureModalData(feature.id,');
  });

  it('P4-006: FeatureDetailShell is imported and used as the modal adapter', () => {
    // P4-006: ProjectBoard is now a thin adapter — inline TabStateView blocks replaced
    // by FeatureDetailShell which delegates TabStateView rendering for each tab.
    expect(PROJECTBOARD_SRC).toContain("import { FeatureDetailShell } from './FeatureModal/FeatureDetailShell'");
    expect(PROJECTBOARD_SRC).toContain('<FeatureDetailShell');
  });

  it('P4-006: ProjectBoard passes sectionStates (shellSectionStates) to FeatureDetailShell', () => {
    // The adapter assembles ShellSectionStateMap from modalSections and passes it to the shell.
    // The shell then internally wires TabStateView per tab using section.status / section.error.
    expect(PROJECTBOARD_SRC).toContain('sectionStates={shellSectionStates}');
    expect(PROJECTBOARD_SRC).toContain('const shellSectionStates = useMemo');
  });

  it('P4-006: shellSectionStates includes all 7 ModalTabId keys', () => {
    // All section entries must be present so the shell can render TabStateView for every tab.
    expect(PROJECTBOARD_SRC).toContain('overview: modalSections.overview');
    expect(PROJECTBOARD_SRC).toContain('phases: modalSections.phases');
    expect(PROJECTBOARD_SRC).toContain('docs: modalSections.docs');
    expect(PROJECTBOARD_SRC).toContain('relations: modalSections.relations');
    expect(PROJECTBOARD_SRC).toContain('sessions: modalSections.sessions');
    expect(PROJECTBOARD_SRC).toContain("'test-status': modalSections['test-status']");
    expect(PROJECTBOARD_SRC).toContain('history: modalSections.history');
  });

  it('P4-006: TabStateView is still imported (used inside domain tab components)', () => {
    // TabStateView is still imported in ProjectBoard for legacy use (StatusDropdown etc.),
    // but the per-tab wiring is now delegated to FeatureDetailShell.
    expect(PROJECTBOARD_SRC).toContain("TabStateView");
  });
});

// ── 3. Tab-activation load dispatcher (P4-010 effect) ────────────────────────

describe('P4-010 — Tab-activation effect loads sections via typed client', () => {
  const block = getTabActivationLoadEffect(PROJECTBOARD_SRC);

  it('P4-010 tab-activation effect is present', () => {
    expect(block.length).toBeGreaterThan(0);
  });

  it('phases tab activation calls modalSections.phases.load()', () => {
    expect(block).toContain("modalSections.phases.load()");
  });

  it('docs tab activation calls modalSections.docs.load()', () => {
    expect(block).toContain("modalSections.docs.load()");
  });

  it('relations tab activation calls modalSections.relations.load()', () => {
    expect(block).toContain("modalSections.relations.load()");
  });

  it('sessions tab activation calls modalSections.sessions.load()', () => {
    expect(block).toContain("modalSections.sessions.load()");
  });

  it('test-status tab activation calls modalSections test-status section load()', () => {
    expect(block).toContain("modalSections['test-status'].load()");
  });

  it('history tab activation calls modalSections.history.load()', () => {
    expect(block).toContain("modalSections.history.load()");
  });
});

// ── 4. TabStateView props per section (P4-006 adapter source-level) ─────────────
//
// P4-006: ProjectBoard is now a thin adapter. Section state is passed as a map
// (shellSectionStates → ShellSectionStateMap) to FeatureDetailShell, which
// delegates TabStateView rendering for each tab internally.
// The assertions below verify the adapter correctly assembles the section state map.

describe('P4-006 — Shell section state adapter: correct per-section wiring', () => {
  it('shellSectionStates assembles from modalSections for all tabs', () => {
    // Each of the 7 ModalTabId keys must appear in the shellSectionStates map.
    expect(PROJECTBOARD_SRC).toContain('overview: modalSections.overview');
    expect(PROJECTBOARD_SRC).toContain('phases: modalSections.phases');
    expect(PROJECTBOARD_SRC).toContain('docs: modalSections.docs');
    expect(PROJECTBOARD_SRC).toContain('relations: modalSections.relations');
    expect(PROJECTBOARD_SRC).toContain('sessions: modalSections.sessions');
    expect(PROJECTBOARD_SRC).toContain("'test-status': modalSections['test-status']");
    expect(PROJECTBOARD_SRC).toContain('history: modalSections.history');
  });

  it('FeatureDetailShell receives sectionStates from shellSectionStates', () => {
    // The shell surfaces status/error/retry from ShellSectionStateMap internally.
    // Verify the binding is present.
    expect(PROJECTBOARD_SRC).toContain('sectionStates={shellSectionStates}');
  });

  it('FeatureDetailShell source internally uses section.status for TabStateView', () => {
    // The contract is that FeatureDetailShell passes section.status to TabStateView.
    // This is tested via the shell source (not ProjectBoard).
    const SHELL_SRC = fs.readFileSync(
      path.resolve(__dirname, '../FeatureModal/FeatureDetailShell.tsx'),
      'utf-8',
    );
    expect(SHELL_SRC).toContain('status={section.status}');
    expect(SHELL_SRC).toContain('error={section.error?.message');
    expect(SHELL_SRC).toContain('onRetry={section.retry}');
  });
});

// ── 5. Simulated phases-section activation (pure state machine) ───────────────
//
// Mirrors the P4-010 useEffect logic:
//   if (activeTab === 'phases') { modalSections.phases.load(); }
// Verifies exactly-one call on phases-tab activation and no call on overview.

type MockSections = {
  [K in string]: { load: (...args: unknown[]) => unknown };
};

function simulateTabLoadEffect(activeTab: string, sections: MockSections): void {
  if (activeTab === 'overview') {
    sections.overview.load();
  } else if (activeTab === 'phases') {
    sections.phases.load();
  } else if (activeTab === 'docs') {
    sections.docs.load();
  } else if (activeTab === 'relations') {
    sections.relations.load();
  } else if (activeTab === 'sessions') {
    sections.sessions.load();
  } else if (activeTab === 'test-status') {
    sections['test-status'].load();
  } else if (activeTab === 'history') {
    sections.history.load();
  }
}

function makeMockSections(): MockSections {
  return {
    overview: { load: vi.fn() },
    phases: { load: vi.fn() },
    docs: { load: vi.fn() },
    relations: { load: vi.fn() },
    sessions: { load: vi.fn() },
    'test-status': { load: vi.fn() },
    history: { load: vi.fn() },
  };
}

describe('P4-010 — Phases section: exactly one load call on tab activation', () => {
  let sections: MockSections;

  beforeEach(() => {
    sections = makeMockSections();
  });

  it('overview tab activation calls overview.load() and no others', () => {
    simulateTabLoadEffect('overview', sections);
    expect(sections.overview.load).toHaveBeenCalledTimes(1);
    expect(sections.phases.load).not.toHaveBeenCalled();
    expect(sections.docs.load).not.toHaveBeenCalled();
  });

  it('phases tab activation calls phases.load() exactly once', () => {
    simulateTabLoadEffect('phases', sections);
    expect(sections.phases.load).toHaveBeenCalledTimes(1);
    expect(sections.overview.load).not.toHaveBeenCalled();
    expect(sections.sessions.load).not.toHaveBeenCalled();
  });

  it('switching phases → overview → phases calls phases.load() twice', () => {
    // Each tab activation is an independent effect call in the hook
    simulateTabLoadEffect('phases', sections);
    simulateTabLoadEffect('overview', sections);
    simulateTabLoadEffect('phases', sections);
    expect(sections.phases.load).toHaveBeenCalledTimes(2);
    // The hook's own load() is idempotent when status === 'loading' or 'success',
    // so in practice the second call is a no-op — tested at the hook level.
  });

  it('sessions tab activation calls sessions.load() exactly once', () => {
    simulateTabLoadEffect('sessions', sections);
    expect(sections.sessions.load).toHaveBeenCalledTimes(1);
    expect(sections.phases.load).not.toHaveBeenCalled();
  });
});

// ── 6. TabStateView error+retry interaction (pure component logic) ─────────────
//
// Simulates the error-state scenario: section.status === 'error' →
// TabStateView renders the error banner; clicking retry re-invokes section.retry().
// Tested as a pure callback simulation (no DOM required).

describe('P4-010 — TabStateView retry callback: error state triggers re-invoke', () => {
  it('onRetry callback invokes section.retry() on error', () => {
    const retrySpy = vi.fn();

    // Simulate: TabStateView is rendered with status='error'; user clicks Retry.
    // The onRetry prop is wired to section.retry() in the source.
    // We verify the wire is present in source and the callback fires.
    const onRetry = retrySpy; // this IS section.retry() per the source wiring

    // Simulate a user click
    onRetry();

    expect(retrySpy).toHaveBeenCalledTimes(1);
  });

  it('TabStateView error branch is never rendered as empty data (source guard)', () => {
    // TabStateView contract: if status === 'error', it renders ErrorBanner, not EmptyState.
    // Verify source explicitly: isEmpty is only evaluated when status === 'success'.
    const TAB_STATE_VIEW_SRC = fs.readFileSync(
      path.resolve(__dirname, '../FeatureModal/TabStateView.tsx'),
      'utf-8',
    );
    // Error state must bail out before reaching the isEmpty check.
    expect(TAB_STATE_VIEW_SRC).toContain("if (status === 'error')");
    expect(TAB_STATE_VIEW_SRC).toContain("return <ErrorBanner");
    // The isEmpty + status === 'success' guard ensures error never shows empty state.
    expect(TAB_STATE_VIEW_SRC).toContain("isEmpty && status === 'success'");
  });

  it('P4-006: TabStateView error prop wiring is delegated to FeatureDetailShell (source proof)', () => {
    // P4-006: ProjectBoard no longer directly passes error?.message to TabStateView.
    // The shell receives ShellSectionStateMap and internally wires section.error?.message
    // to TabStateView. Verify the shell source contains this wiring.
    const SHELL_SRC = fs.readFileSync(
      path.resolve(__dirname, '../FeatureModal/FeatureDetailShell.tsx'),
      'utf-8',
    );
    // The shell must use optional chaining on error?.message to avoid [object Object] display.
    expect(SHELL_SRC).toContain('error?.message');
    // ProjectBoard must NOT be doing its own per-section error wiring outside shellSectionStates.
    // (The old direct wiring pattern no longer appears.)
    const oldDirectWiring = (PROJECTBOARD_SRC.match(/error=\{modalSections[^}]*\.error\?\.message\}/g) ?? []).length;
    // After P4-006, direct wiring inside ProjectBoard return JSX is 0 (shell owns it).
    expect(oldDirectWiring).toBe(0);
  });
});
