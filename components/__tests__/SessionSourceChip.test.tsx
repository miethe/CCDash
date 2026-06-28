/**
 * SessionSourceChip — Phase 6 session source attribution badge.
 *
 * Verifies:
 * - Correct label rendered per source value.
 * - Correct tone class per source value.
 * - Returns nothing (renders empty) when source is undefined.
 * - Compact prop passes through (size="sm" badge).
 * - Unknown source string falls back gracefully.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';

import { SessionSourceChip } from '../SessionSourceChip';

// ── Helpers ───────────────────────────────────────────────────────────────────

const render = (el: React.ReactElement): string => renderToStaticMarkup(el);

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SessionSourceChip — label per source value', () => {
  it('renders "Local file" for filesystem', () => {
    const html = render(<SessionSourceChip source="filesystem" />);
    expect(html).toContain('Local file');
  });

  it('renders "Remote ingest" for remote', () => {
    const html = render(<SessionSourceChip source="remote" />);
    expect(html).toContain('Remote ingest');
  });

  it('renders "Entire checkpoint" for entire', () => {
    const html = render(<SessionSourceChip source="entire" />);
    expect(html).toContain('Entire checkpoint');
  });

  it('renders "Unknown" for unknown', () => {
    const html = render(<SessionSourceChip source="unknown" />);
    expect(html).toContain('Unknown');
  });
});

describe('SessionSourceChip — tone classes per source value', () => {
  it('filesystem → neutral tone class', () => {
    const html = render(<SessionSourceChip source="filesystem" />);
    // neutral tone: bg-surface-overlay or border-panel-border
    expect(html).toMatch(/border-panel-border/);
  });

  it('remote → info tone class', () => {
    const html = render(<SessionSourceChip source="remote" />);
    expect(html).toMatch(/bg-info/);
  });

  it('entire → info tone class', () => {
    const html = render(<SessionSourceChip source="entire" />);
    expect(html).toMatch(/bg-info/);
  });

  it('unknown → neutral tone class', () => {
    const html = render(<SessionSourceChip source="unknown" />);
    expect(html).toMatch(/border-panel-border/);
  });
});

describe('SessionSourceChip — resilience (undefined source)', () => {
  it('renders nothing when source is undefined', () => {
    const html = render(<SessionSourceChip source={undefined} />);
    expect(html).toBe('');
  });

  it('renders nothing when source prop is omitted', () => {
    const html = render(<SessionSourceChip />);
    expect(html).toBe('');
  });
});

describe('SessionSourceChip — compact variant', () => {
  it('renders without crashing in compact mode', () => {
    expect(() => render(<SessionSourceChip source="filesystem" compact />)).not.toThrow();
    expect(() => render(<SessionSourceChip source="remote" compact />)).not.toThrow();
  });

  it('compact still renders the label', () => {
    const html = render(<SessionSourceChip source="remote" compact />);
    expect(html).toContain('Remote ingest');
  });
});

describe('SessionSourceChip — tooltip', () => {
  it('filesystem has a descriptive title attribute', () => {
    const html = render(<SessionSourceChip source="filesystem" />);
    expect(html).toContain('title=');
    expect(html).toContain('filesystem');
  });

  it('remote has a descriptive title attribute', () => {
    const html = render(<SessionSourceChip source="remote" />);
    expect(html).toContain('title=');
    expect(html).toContain('remote');
  });
});
