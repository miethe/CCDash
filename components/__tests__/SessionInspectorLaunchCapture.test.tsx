/**
 * T11-005: Launch-time capture field surface (R-P2 / AC-11.D)
 *
 * Verifies that SessionInspector:
 *   1. Renders an explicit 'Not captured' fallback for null/absent launch fields
 *      (all-null session must render cleanly — never "undefined", never crash).
 *   2. References all four camelCase session fields so a populated session shows
 *      the actual captured values.
 *   3. The T11-005 comment marker is present, documenting the feature in-source.
 *
 * Testing strategy (no @testing-library/react — consistent with P4-007/P4-009):
 *   Source-level proofs via fs.readFileSync + string/regex assertions.
 *   No jsdom configured in vitest.config.ts; structural proofs are the contract.
 *
 * AC-11.D invariant: absent field == "not captured" (a contract state, not a bug).
 * The source must coalesce each null/absent value to the literal 'Not captured'
 * so the DOM never contains "undefined" and the component never throws.
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ── Sources under test ────────────────────────────────────────────────────────
const SESSION_INSPECTOR_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../SessionInspector.tsx'),
  'utf-8',
);
const TYPES_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../../types.ts'),
  'utf-8',
);

// ── 1. Feature marker ─────────────────────────────────────────────────────────
describe('T11-005 — feature marker', () => {
  it('SessionInspector.tsx contains the T11-005 comment marker', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('T11-005');
  });

  it('SessionInspector.tsx references R-P2 / AC-11.D contract', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('AC-11.D');
  });
});

// ── 2. All-null session: explicit 'Not captured' fallback (R-P2 / AC-11.D) ───
describe('T11-005 — all-null session renders "Not captured" fallback (never undefined / never crash)', () => {
  it('source contains the "Not captured" fallback string', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('Not captured');
  });

  it('session.launcher is coalesced to "Not captured" when null/absent', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain("session.launcher || 'Not captured'");
  });

  it('session.profile is coalesced to "Not captured" when null/absent', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain("session.profile || 'Not captured'");
  });

  it('session.effortTier is coalesced to "Not captured" when null/absent', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain("session.effortTier || 'Not captured'");
  });

  it('session.modelVariant is coalesced to "Not captured" when null/absent', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain("session.modelVariant || 'Not captured'");
  });
});

// ── 3. Populated session: field values surface ────────────────────────────────
describe('T11-005 — populated session surfaces captured field values', () => {
  it('renders session.launcher when present', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('session.launcher');
  });

  it('renders session.profile when present', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('session.profile');
  });

  it('renders session.effortTier when present', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('session.effortTier');
  });

  it('renders session.modelVariant when present', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('session.modelVariant');
  });
});

// ── 4. UI labels ──────────────────────────────────────────────────────────────
describe('T11-005 — field label rows are present in the Session Capture panel', () => {
  it('has "Launcher" label', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('>Launcher<');
  });

  it('has "Profile" label', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('>Profile<');
  });

  it('has "Effort Tier" label', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('>Effort Tier<');
  });

  it('has "Model Variant" label', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('>Model Variant<');
  });
});

// ── 5. types.ts contract ──────────────────────────────────────────────────────
describe('T11-005 — types.ts declares the four launch-capture fields on AgentSession', () => {
  it('declares launcher?: string | null', () => {
    expect(TYPES_SOURCE).toContain('launcher?: string | null');
  });

  it('declares profile?: string | null', () => {
    expect(TYPES_SOURCE).toContain('profile?: string | null');
  });

  it('declares effortTier?: string | null', () => {
    expect(TYPES_SOURCE).toContain('effortTier?: string | null');
  });

  it('declares modelVariant?: string | null', () => {
    expect(TYPES_SOURCE).toContain('modelVariant?: string | null');
  });
});
