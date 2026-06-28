/**
 * IngestHealthBadge — Phase 6 ingest/daemon health rollup badge.
 *
 * Verifies:
 * - Empty / undefined ingestSources → neutral "Local only".
 * - Worst-state-wins: disconnected dominates all others → danger tone.
 * - backed_up with no disconnected → warning tone.
 * - connected with no worse → success tone.
 * - All idle → neutral "Idle" label.
 * - Tooltip lists per-source source_id + state.
 * - Multi-source count suffix rendered when sources.length > 1.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';

import { IngestHealthBadge } from '../IngestHealthBadge';
import type { IngestSourceHealth } from '../../services/apiClient';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeSource = (
  source_id: string,
  state: IngestSourceHealth['state'],
  lag_seconds: number | null = null,
): IngestSourceHealth => ({
  source_id,
  project_id: 'proj-1',
  workspace_id: 'ws-1',
  last_cursor: null,
  last_ingest_at: null,
  lag_seconds,
  state,
});

// ── Helpers ───────────────────────────────────────────────────────────────────

const render = (el: React.ReactElement): string => renderToStaticMarkup(el);

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('IngestHealthBadge — empty / absent sources', () => {
  it('renders "Local only" when ingestSources is undefined', () => {
    const html = render(<IngestHealthBadge />);
    expect(html).toContain('Local only');
  });

  it('renders "Local only" when ingestSources is an empty array', () => {
    const html = render(<IngestHealthBadge ingestSources={[]} />);
    expect(html).toContain('Local only');
  });

  it('neutral tone when empty', () => {
    const html = render(<IngestHealthBadge ingestSources={[]} />);
    // neutral tone includes border-panel-border
    expect(html).toMatch(/border-panel-border/);
  });

  it('never throws on undefined', () => {
    expect(() => render(<IngestHealthBadge />)).not.toThrow();
  });
});

describe('IngestHealthBadge — worst-state-wins: disconnected', () => {
  it('danger tone when any source is disconnected', () => {
    const sources = [
      makeSource('src-a', 'connected'),
      makeSource('src-b', 'disconnected'),
      makeSource('src-c', 'idle'),
    ];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toMatch(/bg-danger/);
    expect(html).toContain('Disconnected');
  });

  it('disconnected beats backed_up', () => {
    const sources = [
      makeSource('src-a', 'backed_up'),
      makeSource('src-b', 'disconnected'),
    ];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toContain('Disconnected');
    expect(html).not.toContain('Backed up');
  });
});

describe('IngestHealthBadge — worst-state-wins: backed_up', () => {
  it('warning tone when worst state is backed_up', () => {
    const sources = [
      makeSource('src-a', 'connected'),
      makeSource('src-b', 'backed_up'),
      makeSource('src-c', 'idle'),
    ];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toMatch(/bg-warning/);
    expect(html).toContain('Backed up');
  });
});

describe('IngestHealthBadge — worst-state-wins: connected', () => {
  it('success tone when worst state is connected (no worse states)', () => {
    const sources = [
      makeSource('src-a', 'connected'),
      makeSource('src-b', 'idle'),
    ];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toMatch(/bg-success/);
    expect(html).toContain('Connected');
  });
});

describe('IngestHealthBadge — all idle', () => {
  it('neutral tone when all sources are idle', () => {
    const sources = [makeSource('src-a', 'idle'), makeSource('src-b', 'idle')];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toMatch(/border-panel-border/);
    expect(html).toContain('Idle');
  });
});

describe('IngestHealthBadge — single source', () => {
  it('no count suffix for a single source', () => {
    const sources = [makeSource('src-1', 'connected')];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).not.toContain('(1)');
  });
});

describe('IngestHealthBadge — multi-source count suffix', () => {
  it('renders count suffix when sources.length > 1', () => {
    const sources = [
      makeSource('src-a', 'connected'),
      makeSource('src-b', 'connected'),
    ];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toContain('(2)');
  });
});

describe('IngestHealthBadge — tooltip', () => {
  it('tooltip includes source_id and state for each source', () => {
    const sources = [
      makeSource('src-alpha', 'connected', 5),
      makeSource('src-beta', 'idle'),
    ];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toContain('src-alpha');
    expect(html).toContain('src-beta');
    expect(html).toContain('connected');
    expect(html).toContain('idle');
  });

  it('tooltip includes lag_seconds when present', () => {
    const sources = [makeSource('src-a', 'backed_up', 120)];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    expect(html).toContain('120');
  });

  it('tooltip omits lag when lag_seconds is null', () => {
    const sources = [makeSource('src-a', 'connected', null)];
    const html = render(<IngestHealthBadge ingestSources={sources} />);
    // Should not contain "null" as text
    expect(html).not.toContain('>null<');
  });
});
