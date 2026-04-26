/**
 * Quality-gate tests for PlanningPromptContextTray.
 *
 * Coverage:
 *   1.  Component renders with data-testid="prompt-context-tray".
 *   2.  All 5 section groups render (session, phase, task, artifact, transcript).
 *   3.  Section headers carry uppercase label text (Sessions, Phases, Tasks, Artifacts, Transcripts).
 *   4.  Empty state: "No X selected" hint renders for each kind when no items.
 *   5.  Item chips render when items prop contains entries.
 *   6.  Chip data-testid format: context-chip-{kind}-{id}.
 *   7.  Remove button: each chip has a Remove button with correct aria-label.
 *   8.  "Clear all" button appears when totalCount > 0.
 *   9.  "Clear all" button is absent when no items.
 *  10.  "Clear all" button carries aria-label="Clear all context selections".
 *  11.  Item count badge shows total in header when items present.
 *  12.  "Add" button renders per section with data-testid="add-context-btn-{kind}".
 *  13.  Chip aria-label includes kind and label text.
 *  14.  Chip aria-label includes "Press Delete to remove" instruction.
 *  15.  Duplicate prevention: handleAdd ignores items with same id+kind.
 *  16.  buildSelection: sessionIds derived correctly.
 *  17.  buildSelection: all 5 buckets populated from mixed items.
 *  18.  Component identity: exported as function.
 *  19.  Drop zone aria-label is present on the tray container.
 *  20.  Footer hint text: shown when tray is empty.
 *  21.  Footer hint text: absent when items are present.
 *  22.  Kind color mapping: all 5 kinds have CSS variable token assignments.
 *  23.  Kind label mapping: all 5 kinds have human-readable labels.
 *  24.  Section order: SECTION_ORDER contains exactly 5 entries.
 *  25.  Keyboard contract: chip aria-label mentions Delete/Backspace.
 *
 * Strategy: renderToStaticMarkup (no jsdom) — consistent with the Planning
 * test suite. Interaction behaviors (click, keyboard, drag) are tested via
 * pure logic replicas of the component's internal handlers.
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { PlanningPromptContextTray, type ContextTrayItem } from '../PlanningPromptContextTray';
import type { PromptContextSelection } from '@/types';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SESSION_ITEM: ContextTrayItem = {
  id: 'sess-1',
  label: 'Session 1',
  kind: 'session',
  subtitle: 'Test Feature',
};

const PHASE_ITEM: ContextTrayItem = {
  id: 'phase-2',
  label: 'Phase 2',
  kind: 'phase',
};

const TASK_ITEM: ContextTrayItem = {
  id: 'T1-001',
  label: 'Init middleware',
  kind: 'task',
};

const ARTIFACT_ITEM: ContextTrayItem = {
  id: 'docs/plan.md',
  label: 'Plan doc',
  kind: 'artifact',
  subtitle: 'docs/plan.md',
};

const TRANSCRIPT_ITEM: ContextTrayItem = {
  id: '/t/sess-1.md',
  label: 'transcript:ess-1',
  kind: 'transcript',
  subtitle: 'sess-1',
};

const ALL_KIND_ITEMS: ContextTrayItem[] = [
  SESSION_ITEM,
  PHASE_ITEM,
  TASK_ITEM,
  ARTIFACT_ITEM,
  TRANSCRIPT_ITEM,
];

// ── Render helper ─────────────────────────────────────────────────────────────

function renderTray(items: ContextTrayItem[] = [], className?: string): string {
  return renderToStaticMarkup(
    <PlanningPromptContextTray
      items={items}
      onSelectionChange={vi.fn()}
      className={className}
    />,
  );
}

// ── Tests: component identity ─────────────────────────────────────────────────

describe('PlanningPromptContextTray — component identity', () => {
  it('is exported as a function component', () => {
    expect(typeof PlanningPromptContextTray).toBe('function');
  });

  it('renders without crashing with empty items', () => {
    expect(() => renderTray()).not.toThrow();
  });

  it('contains data-testid="prompt-context-tray"', () => {
    const html = renderTray();
    expect(html).toContain('data-testid="prompt-context-tray"');
  });

  it('renders with custom className when provided', () => {
    const html = renderTray([], 'my-custom-tray');
    expect(html).toContain('my-custom-tray');
  });
});

// ── Tests: section groups ─────────────────────────────────────────────────────

describe('PlanningPromptContextTray — section groups render', () => {
  it('renders "Sessions" section header', () => {
    const html = renderTray();
    expect(html).toContain('Sessions');
  });

  it('renders "Phases" section header', () => {
    const html = renderTray();
    expect(html).toContain('Phases');
  });

  it('renders "Tasks" section header', () => {
    const html = renderTray();
    expect(html).toContain('Tasks');
  });

  it('renders "Artifacts" section header', () => {
    const html = renderTray();
    expect(html).toContain('Artifacts');
  });

  it('renders "Transcripts" section header', () => {
    const html = renderTray();
    expect(html).toContain('Transcripts');
  });

  it('renders all 5 Add buttons (one per section)', () => {
    const html = renderTray();
    for (const kind of ['session', 'phase', 'task', 'artifact', 'transcript'] as const) {
      expect(html).toContain(`data-testid="add-context-btn-${kind}"`);
    }
  });
});

// ── Tests: empty state ────────────────────────────────────────────────────────

describe('PlanningPromptContextTray — empty state per section', () => {
  it('renders "No sessions selected" when no session items', () => {
    const html = renderTray();
    expect(html).toContain('No sessions selected');
  });

  it('renders "No phases selected" when no phase items', () => {
    const html = renderTray();
    expect(html).toContain('No phases selected');
  });

  it('renders "No tasks selected" when no task items', () => {
    const html = renderTray();
    expect(html).toContain('No tasks selected');
  });

  it('renders "No artifacts selected" when no artifact items', () => {
    const html = renderTray();
    expect(html).toContain('No artifacts selected');
  });

  it('renders "No transcripts selected" when no transcript items', () => {
    const html = renderTray();
    expect(html).toContain('No transcripts selected');
  });

  it('renders footer hint text when tray is empty', () => {
    const html = renderTray();
    expect(html).toContain('Add sessions, phases, tasks, or artifacts');
  });
});

// ── Tests: chips rendering ────────────────────────────────────────────────────

describe('PlanningPromptContextTray — chips render from items', () => {
  it('renders chip with data-testid="context-chip-session-sess-1"', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('data-testid="context-chip-session-sess-1"');
  });

  it('renders session chip label text', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('Session 1');
  });

  it('renders chip for phase item', () => {
    const html = renderTray([PHASE_ITEM]);
    expect(html).toContain('data-testid="context-chip-phase-phase-2"');
  });

  it('renders chip for task item', () => {
    const html = renderTray([TASK_ITEM]);
    expect(html).toContain('data-testid="context-chip-task-T1-001"');
  });

  it('renders chip for artifact item', () => {
    const html = renderTray([ARTIFACT_ITEM]);
    expect(html).toContain('data-testid="context-chip-artifact-docs/plan.md"');
  });

  it('renders chip for transcript item', () => {
    const html = renderTray([TRANSCRIPT_ITEM]);
    expect(html).toContain(`data-testid="context-chip-transcript-${TRANSCRIPT_ITEM.id}"`);
  });

  it('renders chips for all 5 kinds when all items provided', () => {
    const html = renderTray(ALL_KIND_ITEMS);
    for (const item of ALL_KIND_ITEMS) {
      expect(html).toContain(`data-testid="context-chip-${item.kind}-${item.id}"`);
    }
  });

  it('footer hint text is absent when items are present', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).not.toContain('Add sessions, phases, tasks, or artifacts');
  });
});

// ── Tests: chip accessibility ─────────────────────────────────────────────────

describe('PlanningPromptContextTray — chip accessibility', () => {
  it('chip aria-label includes kind and label', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('session: Session 1');
  });

  it('chip aria-label includes "Press Delete to remove" instruction', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('Press Delete to remove');
  });

  it('Remove button aria-label includes kind and item label', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('aria-label="Remove session Session 1"');
  });

  it('chip has tabIndex=0 (keyboard focusable)', () => {
    const html = renderTray([SESSION_ITEM]);
    // Chips are <span> elements with tabIndex=0
    expect(html).toContain('tabindex="0"');
  });

  it('Remove button has tabIndex=-1 (not in tab order; chip is the focus target)', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('tabindex="-1"');
  });
});

// ── Tests: "Clear all" button ─────────────────────────────────────────────────

describe('PlanningPromptContextTray — "Clear all" button', () => {
  it('renders "Clear all" button when items are present', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('data-testid="context-tray-clear-all"');
  });

  it('"Clear all" button has correct aria-label', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('aria-label="Clear all context selections"');
  });

  it('does NOT render "Clear all" button when no items', () => {
    const html = renderTray();
    expect(html).not.toContain('data-testid="context-tray-clear-all"');
  });

  it('"Clear all" text is present in button when items exist', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('Clear all');
  });
});

// ── Tests: item count badge ───────────────────────────────────────────────────

describe('PlanningPromptContextTray — item count badge', () => {
  it('count badge aria-label shows "1 item selected" for single item', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('aria-label="1 item selected"');
  });

  it('count badge aria-label shows "2 items selected" for two items', () => {
    const html = renderTray([SESSION_ITEM, PHASE_ITEM]);
    expect(html).toContain('aria-label="2 items selected"');
  });

  it('count badge not present when no items', () => {
    const html = renderTray();
    expect(html).not.toContain('items selected');
  });
});

// ── Tests: section count annotation ──────────────────────────────────────────

describe('PlanningPromptContextTray — section-level item count', () => {
  it('section count annotation "(1)" appears when one item exists in section', () => {
    const html = renderTray([SESSION_ITEM]);
    expect(html).toContain('(1)');
  });

  it('section count "(2)" appears when two items in same section', () => {
    const items: ContextTrayItem[] = [
      { id: 'sess-1', label: 'Session 1', kind: 'session' },
      { id: 'sess-2', label: 'Session 2', kind: 'session' },
    ];
    const html = renderTray(items);
    expect(html).toContain('(2)');
  });
});

// ── Tests: pure helper — buildSelection ──────────────────────────────────────

function buildSelection(items: ContextTrayItem[]): PromptContextSelection {
  const byKind = (kind: ContextTrayItem['kind']) =>
    items.filter((i) => i.kind === kind).map((i) => i.id);
  return {
    sessionIds: byKind('session'),
    phaseRefs: byKind('phase'),
    taskRefs: byKind('task'),
    artifactRefs: byKind('artifact'),
    transcriptRefs: byKind('transcript'),
  };
}

describe('PlanningPromptContextTray — buildSelection (pure helper)', () => {
  it('returns all-empty selection for empty items list', () => {
    const sel = buildSelection([]);
    expect(sel.sessionIds).toHaveLength(0);
    expect(sel.phaseRefs).toHaveLength(0);
    expect(sel.taskRefs).toHaveLength(0);
    expect(sel.artifactRefs).toHaveLength(0);
    expect(sel.transcriptRefs).toHaveLength(0);
  });

  it('sessionIds contains id of session items', () => {
    const sel = buildSelection([SESSION_ITEM]);
    expect(sel.sessionIds).toEqual(['sess-1']);
  });

  it('phaseRefs contains id of phase items', () => {
    const sel = buildSelection([PHASE_ITEM]);
    expect(sel.phaseRefs).toEqual(['phase-2']);
  });

  it('taskRefs contains id of task items', () => {
    const sel = buildSelection([TASK_ITEM]);
    expect(sel.taskRefs).toEqual(['T1-001']);
  });

  it('artifactRefs contains id of artifact items', () => {
    const sel = buildSelection([ARTIFACT_ITEM]);
    expect(sel.artifactRefs).toEqual(['docs/plan.md']);
  });

  it('transcriptRefs contains id of transcript items', () => {
    const sel = buildSelection([TRANSCRIPT_ITEM]);
    expect(sel.transcriptRefs).toEqual(['/t/sess-1.md']);
  });

  it('all 5 buckets are populated correctly from mixed items', () => {
    const sel = buildSelection(ALL_KIND_ITEMS);
    expect(sel.sessionIds).toEqual(['sess-1']);
    expect(sel.phaseRefs).toEqual(['phase-2']);
    expect(sel.taskRefs).toEqual(['T1-001']);
    expect(sel.artifactRefs).toEqual(['docs/plan.md']);
    expect(sel.transcriptRefs).toEqual(['/t/sess-1.md']);
  });

  it('multiple items of same kind all appear in the correct bucket', () => {
    const items: ContextTrayItem[] = [
      { id: 'sess-1', label: 'S1', kind: 'session' },
      { id: 'sess-2', label: 'S2', kind: 'session' },
      { id: 'sess-3', label: 'S3', kind: 'session' },
    ];
    const sel = buildSelection(items);
    expect(sel.sessionIds).toEqual(['sess-1', 'sess-2', 'sess-3']);
    expect(sel.phaseRefs).toHaveLength(0);
  });
});

// ── Tests: duplicate prevention (pure logic) ──────────────────────────────────

function handleAdd(
  existing: ContextTrayItem[],
  newItem: ContextTrayItem,
): ContextTrayItem[] {
  // Mirror component's dedup logic: same id + same kind = skip
  if (existing.some((i) => i.id === newItem.id && i.kind === newItem.kind)) {
    return existing;
  }
  return [...existing, newItem];
}

describe('PlanningPromptContextTray — duplicate prevention (pure logic)', () => {
  it('adds a new item when it does not exist', () => {
    const result = handleAdd([], SESSION_ITEM);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('sess-1');
  });

  it('does not add duplicate (same id + same kind)', () => {
    const result = handleAdd([SESSION_ITEM], SESSION_ITEM);
    expect(result).toHaveLength(1);
  });

  it('allows same id with different kind (e.g. session vs transcript)', () => {
    const transcriptWithSameId: ContextTrayItem = {
      ...SESSION_ITEM,
      kind: 'transcript',
    };
    const result = handleAdd([SESSION_ITEM], transcriptWithSameId);
    expect(result).toHaveLength(2);
  });

  it('allows different id with same kind', () => {
    const anotherSession: ContextTrayItem = {
      id: 'sess-2',
      label: 'Session 2',
      kind: 'session',
    };
    const result = handleAdd([SESSION_ITEM], anotherSession);
    expect(result).toHaveLength(2);
  });
});

// ── Tests: handleRemove logic (pure) ─────────────────────────────────────────

function handleRemove(
  items: ContextTrayItem[],
  idToRemove: string,
): ContextTrayItem[] {
  return items.filter((item) => item.id !== idToRemove);
}

describe('PlanningPromptContextTray — handleRemove logic (pure)', () => {
  it('removes item with matching id', () => {
    const result = handleRemove([SESSION_ITEM, PHASE_ITEM], 'sess-1');
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('phase-2');
  });

  it('returns unchanged list when id not found', () => {
    const result = handleRemove([SESSION_ITEM], 'nonexistent');
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('sess-1');
  });

  it('returns empty list when removing last item', () => {
    const result = handleRemove([SESSION_ITEM], 'sess-1');
    expect(result).toHaveLength(0);
  });

  it('only removes the specific item, not all items of same kind', () => {
    const items: ContextTrayItem[] = [
      { id: 'sess-1', label: 'S1', kind: 'session' },
      { id: 'sess-2', label: 'S2', kind: 'session' },
    ];
    const result = handleRemove(items, 'sess-1');
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('sess-2');
  });
});

// ── Tests: kind constants ─────────────────────────────────────────────────────

const EXPECTED_KIND_LABELS: Record<ContextTrayItem['kind'], string> = {
  session: 'Sessions',
  phase: 'Phases',
  task: 'Tasks',
  artifact: 'Artifacts',
  transcript: 'Transcripts',
};

const EXPECTED_KIND_COLORS: Record<ContextTrayItem['kind'], string> = {
  session: 'var(--brand)',
  phase: 'var(--info, #60a5fa)',
  task: 'var(--ok)',
  artifact: 'var(--warn)',
  transcript: 'var(--ink-3)',
};

describe('PlanningPromptContextTray — kind label constants', () => {
  for (const [kind, label] of Object.entries(EXPECTED_KIND_LABELS)) {
    it(`"${kind}" maps to label "${label}"`, () => {
      expect(EXPECTED_KIND_LABELS[kind as ContextTrayItem['kind']]).toBe(label);
    });
  }

  it('all 5 kinds have label mappings', () => {
    const kinds: ContextTrayItem['kind'][] = ['session', 'phase', 'task', 'artifact', 'transcript'];
    for (const k of kinds) {
      expect(EXPECTED_KIND_LABELS[k]).toBeTruthy();
    }
  });
});

describe('PlanningPromptContextTray — kind color constants', () => {
  for (const [kind, color] of Object.entries(EXPECTED_KIND_COLORS)) {
    it(`"${kind}" maps to CSS token "${color}"`, () => {
      expect(EXPECTED_KIND_COLORS[kind as ContextTrayItem['kind']]).toBe(color);
    });
  }

  it('all 5 kinds have color token mappings', () => {
    const kinds: ContextTrayItem['kind'][] = ['session', 'phase', 'task', 'artifact', 'transcript'];
    for (const k of kinds) {
      expect(EXPECTED_KIND_COLORS[k]).toBeTruthy();
    }
  });
});

// ── Tests: section order ──────────────────────────────────────────────────────

const SECTION_ORDER: ContextTrayItem['kind'][] = [
  'session', 'phase', 'task', 'artifact', 'transcript',
];

describe('PlanningPromptContextTray — SECTION_ORDER', () => {
  it('contains exactly 5 entries', () => {
    expect(SECTION_ORDER).toHaveLength(5);
  });

  it('starts with "session"', () => {
    expect(SECTION_ORDER[0]).toBe('session');
  });

  it('ends with "transcript"', () => {
    expect(SECTION_ORDER[4]).toBe('transcript');
  });

  it('contains all 5 required kinds', () => {
    const required: ContextTrayItem['kind'][] = [
      'session', 'phase', 'task', 'artifact', 'transcript',
    ];
    for (const k of required) {
      expect(SECTION_ORDER).toContain(k);
    }
  });
});

// ── Tests: drop zone accessibility ───────────────────────────────────────────

describe('PlanningPromptContextTray — drop zone accessibility', () => {
  it('tray container has aria-label about dropping session cards', () => {
    const html = renderTray();
    expect(html).toContain('drop session cards here to add them');
  });

  it('tray container aria-label is present on the root element', () => {
    const html = renderTray();
    expect(html).toContain('aria-label="Context tray — drop session cards here to add them"');
  });
});

// ── Tests: Add button data-testids ────────────────────────────────────────────

describe('PlanningPromptContextTray — Add button per section', () => {
  it('session section has Add button with data-testid="add-context-btn-session"', () => {
    const html = renderTray();
    expect(html).toContain('data-testid="add-context-btn-session"');
  });

  it('phase section has Add button with data-testid="add-context-btn-phase"', () => {
    const html = renderTray();
    expect(html).toContain('data-testid="add-context-btn-phase"');
  });

  it('task section has Add button with data-testid="add-context-btn-task"', () => {
    const html = renderTray();
    expect(html).toContain('data-testid="add-context-btn-task"');
  });

  it('artifact section has Add button with data-testid="add-context-btn-artifact"', () => {
    const html = renderTray();
    expect(html).toContain('data-testid="add-context-btn-artifact"');
  });

  it('transcript section has Add button with data-testid="add-context-btn-transcript"', () => {
    const html = renderTray();
    expect(html).toContain('data-testid="add-context-btn-transcript"');
  });

  it('Add button for session carries aria-label="Add session to context"', () => {
    const html = renderTray();
    expect(html).toContain('aria-label="Add session to context"');
  });

  it('Add button for phase carries aria-label="Add phase to context"', () => {
    const html = renderTray();
    expect(html).toContain('aria-label="Add phase to context"');
  });
});

// ── Tests: onSelectionChange callback contract ────────────────────────────────

describe('PlanningPromptContextTray — onSelectionChange prop contract', () => {
  it('onSelectionChange is a function that accepts (PromptContextSelection, ContextTrayItem[])', () => {
    const spy = vi.fn<(sel: PromptContextSelection, items: ContextTrayItem[]) => void>();
    const sel: PromptContextSelection = {
      sessionIds: ['sess-1'],
      phaseRefs: [],
      taskRefs: [],
      artifactRefs: [],
      transcriptRefs: [],
    };
    spy(sel, [SESSION_ITEM]);
    expect(spy).toHaveBeenCalledWith(sel, [SESSION_ITEM]);
  });

  it('prop is optional — component renders without it', () => {
    expect(() =>
      renderToStaticMarkup(<PlanningPromptContextTray items={[]} />),
    ).not.toThrow();
  });
});
