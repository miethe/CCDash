/**
 * automatic-session-naming (T1-004) — FE title-chain wiring + provenance
 * surfacing + escaping/null resilience across the five target surfaces
 * (PRD §11 AC-ESC-1, Resilience Acceptance table):
 *   - components/SessionCard.tsx (shared chain + provenance badge)
 *   - components/SessionInspector.tsx
 *   - components/SessionInspector/SessionInspectorPanels.tsx
 *   - components/Planning/PlanningAgentSessionBoard.tsx
 *   - components/Planning/CommandCenter/MultiProjectSessionBoard.tsx
 *
 * Two test styles are used, matching existing repo convention
 * (components/__tests__/transcriptIntelligence.test.tsx):
 *   1. Direct render tests (renderToStaticMarkup) for the small, pure
 *      SessionCard.tsx exports — genuine React rendering of the null case.
 *   2. Source-level assertions for the large surface files, verifying the
 *      wiring exists and that no raw-HTML sink is used near sessionName.
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import {
  deriveSessionCardTitle,
  deriveTranscriptIntelligenceTitle,
  describeSessionNameProvenance,
  SessionNameProvenanceBadge,
} from '../SessionCard';

const render = (el: React.ReactElement): string => renderToStaticMarkup(el);

const readSource = (relativePath: string): string =>
  fs.readFileSync(path.resolve(__dirname, relativePath), 'utf-8');

const SESSION_INSPECTOR_SOURCE = readSource('../SessionInspector.tsx');
const SESSION_INSPECTOR_PANELS_SOURCE = readSource('../SessionInspector/SessionInspectorPanels.tsx');
const PLANNING_AGENT_SESSION_BOARD_SOURCE = readSource('../Planning/PlanningAgentSessionBoard.tsx');
const MULTI_PROJECT_SESSION_BOARD_SOURCE = readSource('../Planning/CommandCenter/MultiProjectSessionBoard.tsx');
const SESSION_CARD_SOURCE = readSource('../SessionCard.tsx');

// ── describeSessionNameProvenance ──────────────────────────────────────────────

describe('describeSessionNameProvenance', () => {
  it('returns null for null/undefined/empty source', () => {
    expect(describeSessionNameProvenance(null)).toBeNull();
    expect(describeSessionNameProvenance(undefined)).toBeNull();
    expect(describeSessionNameProvenance('')).toBeNull();
    expect(describeSessionNameProvenance('   ')).toBeNull();
  });

  it('marks provider_persisted as the only provider-set token', () => {
    const info = describeSessionNameProvenance('provider_persisted');
    expect(info?.isProviderPersisted).toBe(true);
    expect(info?.label).toBe('Provider');
  });

  it.each([
    ['derived_deterministic', 'Derived'],
    ['derived_embedding_transfer', 'AI · Similar'],
    ['derived_generative', 'AI'],
    ['operator_set', 'Manual'],
  ])('labels %s as %s and flags it as not provider-set', (token, expectedLabel) => {
    const info = describeSessionNameProvenance(token);
    expect(info?.label).toBe(expectedLabel);
    expect(info?.isProviderPersisted).toBe(false);
  });

  it('treats an unrecognised token as unknown provenance rather than failing', () => {
    const info = describeSessionNameProvenance('some_future_token');
    expect(info).not.toBeNull();
    expect(info?.label).toBe('Unknown source');
    expect(info?.isProviderPersisted).toBe(false);
  });
});

// ── SessionNameProvenanceBadge ─────────────────────────────────────────────────

describe('SessionNameProvenanceBadge', () => {
  it('renders nothing when sessionName is null (contract state, not a bug)', () => {
    expect(render(<SessionNameProvenanceBadge sessionName={null} sessionNameSource="provider_persisted" />)).toBe('');
  });

  it('renders nothing when sessionName is undefined', () => {
    expect(render(<SessionNameProvenanceBadge sessionNameSource="provider_persisted" />)).toBe('');
  });

  it('renders nothing when sessionName is an empty/whitespace string', () => {
    expect(render(<SessionNameProvenanceBadge sessionName="   " sessionNameSource="provider_persisted" />)).toBe('');
  });

  it('renders nothing when sessionName exists but sessionNameSource is null (never fabricate provenance)', () => {
    expect(render(<SessionNameProvenanceBadge sessionName="Refactor auth middleware" sessionNameSource={null} />)).toBe('');
  });

  it('renders a "Provider" badge for provider_persisted, distinct styling from derived', () => {
    const html = render(
      <SessionNameProvenanceBadge sessionName="Refactor auth middleware" sessionNameSource="provider_persisted" />,
    );
    expect(html).toContain('Provider');
    expect(html).toMatch(/emerald/);
  });

  it('renders an "AI" badge for derived_generative with a distinct (non-emerald) tone, to avoid mistaking it for provider-set', () => {
    const html = render(
      <SessionNameProvenanceBadge sessionName="Debug session naming worker" sessionNameSource="derived_generative" />,
    );
    expect(html).toContain('AI');
    expect(html).toMatch(/amber/);
    expect(html).not.toMatch(/emerald/);
  });

  it('does not render the raw sessionName text (only the provenance label) — no injection surface here', () => {
    const html = render(
      <SessionNameProvenanceBadge sessionName="<img src=x onerror=alert(1)>" sessionNameSource="derived_generative" />,
    );
    expect(html).not.toContain('<img');
    expect(html).not.toContain('onerror');
  });
});

// ── deriveSessionCardTitle / deriveTranscriptIntelligenceTitle: sessionName priority ──

describe('deriveSessionCardTitle — sessionName feeds the existing explicitTitle slot', () => {
  it('uses sessionName when present', () => {
    expect(deriveSessionCardTitle('session-123', 'Refactor auth middleware', null)).toBe('Refactor auth middleware');
  });

  it('null sessionName falls through to the existing chain (sessionTypeLabel), never crashes', () => {
    expect(
      deriveSessionCardTitle('session-123', undefined, { sessionTypeLabel: 'Implementation' }),
    ).toBe('Implementation');
  });

  it('null sessionName and no metadata falls all the way through to the raw session id, never crashes', () => {
    expect(deriveSessionCardTitle('session-123', undefined, null)).toBe('session-123');
  });

  it('React text interpolation escapes an adversarial sessionName (AC-ESC-1) — no raw HTML sink', () => {
    const title = deriveSessionCardTitle('session-123', '<script>alert(1)</script>', null);
    const html = render(<div>{title}</div>);
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });
});

describe('deriveTranscriptIntelligenceTitle — sessionName priority preserved under the flag', () => {
  it('sessionName wins over the flagged transcript-intelligence title path being disabled', () => {
    expect(
      deriveTranscriptIntelligenceTitle('session-123', 'Refactor auth middleware', null, 'Some intelligence title', false),
    ).toBe('Refactor auth middleware');
  });

  it('null sessionName + disabled flag falls through to the raw session id, never crashes', () => {
    expect(deriveTranscriptIntelligenceTitle('session-123', undefined, null, null, false)).toBe('session-123');
  });
});

// ── AC-ESC-1: no raw-HTML sink anywhere in the touched surfaces ──────────────

describe('AC-ESC-1 — no surface renders session_name via an unsanitised raw-HTML/markdown sink', () => {
  it.each([
    ['SessionCard.tsx', SESSION_CARD_SOURCE],
    ['SessionInspector.tsx', SESSION_INSPECTOR_SOURCE],
    ['SessionInspector/SessionInspectorPanels.tsx', SESSION_INSPECTOR_PANELS_SOURCE],
    ['Planning/PlanningAgentSessionBoard.tsx', PLANNING_AGENT_SESSION_BOARD_SOURCE],
    ['Planning/CommandCenter/MultiProjectSessionBoard.tsx', MULTI_PROJECT_SESSION_BOARD_SOURCE],
  ])('%s never uses dangerouslySetInnerHTML', (_name, source) => {
    expect(source).not.toContain('dangerouslySetInnerHTML');
  });
});

// ── Source-level wiring checks (large-surface pattern; mirrors transcriptIntelligence.test.tsx) ──

describe('SessionInspector.tsx — sessionName wired into the existing title chain', () => {
  it('feeds session.sessionName ahead of session.title into deriveSessionCardTitle, not a new resolver', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain(
      'deriveSessionCardTitle(session.id, session.sessionName || session.title, session.sessionMetadata || null)',
    );
  });

  it('surfaces sessionNameSource via the shared provenance badge next to the header title', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('<SessionNameProvenanceBadge sessionName={session.sessionName} sessionNameSource={session.sessionNameSource} />');
  });
});

describe('SessionInspectorPanels.tsx (SessionSummaryCard) — sessionName wired into the existing title chain', () => {
  it('feeds session.sessionName ahead of session.title into deriveTranscriptIntelligenceTitle', () => {
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('session.sessionName || session.title');
  });

  it('surfaces sessionNameSource via the shared provenance badge in infoBadges', () => {
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('<SessionNameProvenanceBadge sessionName={session.sessionName} sessionNameSource={session.sessionNameSource} />');
  });
});

describe('PlanningAgentSessionBoard.tsx — sessionName wired into the existing title chain', () => {
  it('routes card.sessionName through deriveSessionCardTitle rather than rendering it directly', () => {
    expect(PLANNING_AGENT_SESSION_BOARD_SOURCE).toContain(
      "deriveSessionCardTitle(card.sessionId, card.sessionName ?? undefined, null)",
    );
  });

  it('only renders the session-name row when a name exists (null renders nothing, never a crash)', () => {
    expect(PLANNING_AGENT_SESSION_BOARD_SOURCE).toContain("Boolean((card.sessionName || '').trim())");
  });

  it('surfaces provenance via the shared badge', () => {
    expect(PLANNING_AGENT_SESSION_BOARD_SOURCE).toContain('<SessionNameProvenanceBadge sessionName={card.sessionName} sessionNameSource={card.sessionNameSource} />');
  });
});

describe('MultiProjectSessionBoard.tsx — sessionName wired into the existing title chain', () => {
  it('routes card.sessionName through deriveSessionCardTitle rather than rendering it directly', () => {
    expect(MULTI_PROJECT_SESSION_BOARD_SOURCE).toContain(
      "deriveSessionCardTitle(card.sessionId, card.sessionName ?? undefined, null)",
    );
  });

  it('only renders the session-name row when a name exists (null renders nothing, never a crash)', () => {
    expect(MULTI_PROJECT_SESSION_BOARD_SOURCE).toContain("Boolean((card.sessionName || '').trim())");
  });

  it('surfaces provenance via the shared badge', () => {
    expect(MULTI_PROJECT_SESSION_BOARD_SOURCE).toContain('<SessionNameProvenanceBadge sessionName={card.sessionName} sessionNameSource={card.sessionNameSource} />');
  });
});

// ── FR-9/OQ-1 propagation: PlanningAgentSessionCard type + wire adapters ──────

describe('PlanningAgentSessionCard FE type + wire adapters carry sessionName/sessionNameSource', () => {
  it('types.ts declares sessionName/sessionNameSource on PlanningAgentSessionCard', () => {
    const typesSource = readSource('../../types.ts');
    const interfaceStart = typesSource.indexOf('export interface PlanningAgentSessionCard {');
    const interfaceEnd = typesSource.indexOf('\n}', interfaceStart);
    const interfaceBody = typesSource.slice(interfaceStart, interfaceEnd);
    expect(interfaceBody).toContain('sessionName?: string | null');
    expect(interfaceBody).toContain('sessionNameSource?: string | null');
  });

  it('services/planning.ts adapts wire session_name/session_name_source to camelCase', () => {
    const servicesSource = readSource('../../services/planning.ts');
    expect(servicesSource).toContain('session_name?: string | null');
    expect(servicesSource).toContain('sessionName: wire.session_name ?? null');
    expect(servicesSource).toContain('sessionNameSource: wire.session_name_source ?? null');
  });

  it('services/multiProjectPlanningCommandCenter.ts adapts wire session_name/session_name_source', () => {
    const servicesSource = readSource('../../services/multiProjectPlanningCommandCenter.ts');
    expect(servicesSource).toContain("wire.session_name != null ? String(wire.session_name) : null");
    expect(servicesSource).toContain("wire.session_name_source != null ? String(wire.session_name_source) : null");
  });
});
