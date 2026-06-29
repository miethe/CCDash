/**
 * SessionSourceChip — Phase 6 session source attribution badge.
 * Phase 3 (Codex): codex variant, platformType fallback, SessionUnattributedBadge.
 *
 * Verifies:
 * - Correct label rendered per source value (all 5 values including codex).
 * - Correct tone class per source value.
 * - Returns nothing (renders empty) when source is undefined.
 * - Returns nothing when source is null and platformType is absent/non-Codex.
 * - Renders codex chip when source is null but platformType === 'Codex' (fallback).
 * - Renders codex chip when source is absent but platformType === 'Codex' (fallback).
 * - Compact prop passes through (size="sm" badge).
 * - Unknown source string falls back gracefully.
 * - SessionUnattributedBadge renders for projectId === '' with and without cwd.
 * - Filter-readiness: deriveEffectiveSource utility.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';

import { SessionSourceChip, SessionUnattributedBadge, deriveEffectiveSource } from '../SessionSourceChip';

// ── Helpers ───────────────────────────────────────────────────────────────────

const render = (el: React.ReactElement): string => renderToStaticMarkup(el);

// ── Tests: label per source value ─────────────────────────────────────────────

describe('SessionSourceChip — label per source value', () => {
  it('renders "Codex" for codex', () => {
    const html = render(<SessionSourceChip source="codex" />);
    expect(html).toContain('Codex');
  });

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

// ── Tests: tone classes ────────────────────────────────────────────────────────

describe('SessionSourceChip — tone classes per source value', () => {
  it('codex → warning tone class', () => {
    const html = render(<SessionSourceChip source="codex" />);
    expect(html).toMatch(/bg-warning/);
  });

  it('filesystem → neutral tone class', () => {
    const html = render(<SessionSourceChip source="filesystem" />);
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

// ── Tests: resilience (undefined/null source) ────────────────────────────────

describe('SessionSourceChip — resilience (undefined/null source)', () => {
  it('renders nothing when source is undefined', () => {
    const html = render(<SessionSourceChip source={undefined} />);
    expect(html).toBe('');
  });

  it('renders nothing when source prop is omitted', () => {
    const html = render(<SessionSourceChip />);
    expect(html).toBe('');
  });

  it('renders nothing when source is null and platformType is absent', () => {
    const html = render(<SessionSourceChip source={null} />);
    expect(html).toBe('');
  });

  it('renders nothing when source is null and platformType is "Claude Code"', () => {
    const html = render(<SessionSourceChip source={null} platformType="Claude Code" />);
    expect(html).toBe('');
  });
});

// ── Tests: platformType fallback (Phase-3 backward compat) ───────────────────

describe('SessionSourceChip — platformType fallback', () => {
  it('renders Codex chip when source is null and platformType is "Codex"', () => {
    const html = render(<SessionSourceChip source={null} platformType="Codex" />);
    expect(html).toContain('Codex');
  });

  it('renders Codex chip when source is undefined and platformType is "Codex"', () => {
    const html = render(<SessionSourceChip source={undefined} platformType="Codex" />);
    expect(html).toContain('Codex');
  });

  it('platformType "Codex" fallback renders warning tone', () => {
    const html = render(<SessionSourceChip source={null} platformType="Codex" />);
    expect(html).toMatch(/bg-warning/);
  });

  it('explicit source takes priority over platformType', () => {
    const html = render(<SessionSourceChip source="remote" platformType="Codex" />);
    expect(html).toContain('Remote ingest');
    expect(html).not.toContain('Codex');
  });
});

// ── Tests: compact variant ─────────────────────────────────────────────────────

describe('SessionSourceChip — compact variant', () => {
  it('renders without crashing in compact mode for codex', () => {
    expect(() => render(<SessionSourceChip source="codex" compact />)).not.toThrow();
  });

  it('renders without crashing in compact mode for filesystem', () => {
    expect(() => render(<SessionSourceChip source="filesystem" compact />)).not.toThrow();
  });

  it('compact still renders the label', () => {
    const html = render(<SessionSourceChip source="codex" compact />);
    expect(html).toContain('Codex');
  });
});

// ── Tests: deriveEffectiveSource utility ──────────────────────────────────────

describe('deriveEffectiveSource utility', () => {
  it('returns explicit source when present', () => {
    expect(deriveEffectiveSource('codex')).toBe('codex');
    expect(deriveEffectiveSource('filesystem')).toBe('filesystem');
    expect(deriveEffectiveSource('remote')).toBe('remote');
  });

  it('returns "codex" when source is null and platformType is "Codex"', () => {
    expect(deriveEffectiveSource(null, 'Codex')).toBe('codex');
  });

  it('returns "codex" when source is undefined and platformType is "Codex"', () => {
    expect(deriveEffectiveSource(undefined, 'Codex')).toBe('codex');
  });

  it('returns null when source is null and platformType is absent', () => {
    expect(deriveEffectiveSource(null)).toBe(null);
    expect(deriveEffectiveSource(null, undefined)).toBe(null);
  });

  it('returns null when source is null and platformType is "Claude Code"', () => {
    expect(deriveEffectiveSource(null, 'Claude Code')).toBe(null);
  });

  it('returns null when source is undefined and platformType is absent', () => {
    expect(deriveEffectiveSource(undefined)).toBe(null);
  });
});

// ── Tests: SessionUnattributedBadge ──────────────────────────────────────────

describe('SessionUnattributedBadge', () => {
  it('renders "Unattributed" label', () => {
    const html = render(<SessionUnattributedBadge />);
    expect(html).toContain('Unattributed');
  });

  it('renders warning tone styling', () => {
    const html = render(<SessionUnattributedBadge />);
    expect(html).toContain('amber');
  });

  it('includes cwd in tooltip when provided', () => {
    const html = render(<SessionUnattributedBadge cwd="/home/user/my-repo" />);
    expect(html).toContain('/home/user/my-repo');
  });

  it('renders without cwd (no crash, reasonable fallback tooltip)', () => {
    const html = render(<SessionUnattributedBadge />);
    expect(html).toContain('title=');
    expect(html).toContain('Unattributed');
  });

  it('compact variant renders without crashing', () => {
    expect(() => render(<SessionUnattributedBadge cwd="/repo" compact />)).not.toThrow();
  });
});

// ── Tests: tooltip ────────────────────────────────────────────────────────────

describe('SessionSourceChip — tooltip', () => {
  it('codex has a descriptive title attribute', () => {
    const html = render(<SessionSourceChip source="codex" />);
    expect(html).toContain('title=');
    expect(html).toContain('Codex');
  });

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
