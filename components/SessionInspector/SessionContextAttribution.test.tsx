import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { SessionContextAttribution, SessionContextStage } from '../../types';
import { SessionContextAttributionPanel } from './SessionContextAttribution';

const stage = (o: Partial<SessionContextStage> = {}): SessionContextStage => ({
  id: 's1', phase: 'startup', observedAt: '2026-01-01T00:00:00Z', source: 'synthetic-src', sourceVersion: '1.0',
  unit: 'tokens', amount: 100, method: 'synthetic method', provenance: 'synthetic provenance', layers: [], ...o,
});
const attr = (stages: SessionContextStage[], o: Partial<SessionContextAttribution> = {}): SessionContextAttribution => ({
  schemaVersion: 1, status: 'partial', generatedAt: null,
  coverage: { joinStatus: 'matched', stageCount: stages.length, source: 'synthetic-src', sourceVersion: null },
  stages, unknowns: [], ...o,
});
const html = (a?: SessionContextAttribution | null) => renderToStaticMarkup(<SessionContextAttributionPanel attribution={a} />);

describe('SessionContextAttributionPanel', () => {
  it('shows unmeasured state for missing attribution, not zero', () => {
    for (const a of [undefined, null]) {
      const h = html(a);
      expect(h).toContain('Context evidence');
      expect(h).toContain('Unmeasured');
      expect(h).not.toMatch(/\b0 tokens\b/);
    }
  });

  it('explains empty stages and visible unknowns', () => {
    const h = html(attr([], { status: 'unmeasured', unknowns: ['no hook output'], coverage: { joinStatus: 'source_unavailable', stageCount: 0, source: 's', sourceVersion: null } }));
    expect(h).toContain('No context stages were recorded');
    expect(h).toContain('no hook output');
    expect(h).toContain('Source unavailable');
  });

  it('preserves zero and marks null/negative/NaN unmeasured', () => {
    expect(html(attr([stage({ amount: 0 })]))).toContain('0 tokens');
    for (const amount of [null, -5, NaN]) {
      const h = html(attr([stage({ amount })]));
      expect(h).toContain('Unmeasured');
      expect(h).not.toMatch(/\b0 tokens\b/);
    }
  });

  it('keeps mixed units separate with no combined total', () => {
    const h = html(attr([stage({ unit: 'bytes', amount: 2048, layers: [
      { name: 'L1', amount: 50, unit: 'tokens', source: 's', sourceVersion: null, attribution: 'attributed' },
      { name: 'L2', amount: 10, unit: 'characters', source: 's', sourceVersion: null, attribution: 'attributed' },
    ] })]));
    expect(h).toContain('2,048 bytes');
    expect(h).toContain('50 tokens');
    expect(h).toContain('10 characters');
    expect(h).not.toContain('2,108');
    expect(h).toContain('never added together');
  });

  it('keeps unattributed amounts known and missing layers unmeasured', () => {
    const h = html(attr([stage({ layers: [
      { name: 'U', amount: 40, unit: 'tokens', source: 's', sourceVersion: '2', attribution: 'unattributed' },
      { name: 'M', amount: null, unit: 'tokens', source: 's', sourceVersion: null, attribution: 'missing' },
    ] })]));
    expect(h).toContain('40 tokens');
    expect(h).toContain('origin unresolved');
    expect(h).toContain('Unattributed');
    expect(h).toContain('Missing');
    expect(h).toContain('Unmeasured');
  });

  it('uses required phase wording and keeps unknown phases as recorded', () => {
    const phases = ['first_observed_after_sessionstart', 'post_compact', 'prompt', 'startup', 'unknown', 'custom_phase_x'];
    const h = html(attr(phases.map((phase, i) => stage({ id: `p${i}`, phase }))));
    expect(h).toContain('First input after SessionStart (not guaranteed cold start)');
    expect(h).toContain('After compaction');
    expect(h).toContain('Prompt injection');
    expect(h).toContain('Recorded startup');
    expect(h).toContain('Unrecorded phase');
    expect(h).toContain('custom_phase_x');
  });

  it('retains a producer-shaped named unknown layer without inventing a zero', () => {
    const h = html(attr([stage({ layers: [
      { name: 'identity', amount: null, unit: 'unknown', source: 'unrecorded', sourceVersion: null, attribution: 'missing' },
      { name: 'memory', amount: null, unit: 'unknown', source: 'unrecorded', sourceVersion: null, attribution: 'missing' },
      { name: 'measured block', amount: 12, unit: 'characters', source: 'receipt', sourceVersion: '1', attribution: 'measured' },
    ] })]));
    expect(h).toContain('identity');
    expect(h).toContain('memory');
    expect(h).toContain('unit not recorded');
    expect(h).toContain('12 characters');
    expect(h).not.toContain('0 unknown');
  });

  it('escapes strings and renders no links', () => {
    const evil = '<img src=x onerror=alert(1)>';
    const h = html(attr([stage({ phase: evil, provenance: evil, method: evil, source: evil,
      layers: [{ name: evil, amount: 1, unit: 'tokens', source: evil, sourceVersion: null, attribution: 'attributed' }] })],
      { unknowns: [evil] }));
    expect(h).not.toContain('<img');
    expect(h).toContain('&lt;img');
    expect(h).not.toContain('<a ');
  });
});
