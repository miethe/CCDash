import { describe, expect, it } from 'vitest';

import {
  deriveProviderIdentity,
  getProviderTone,
  type DeriveProviderIdentityInput,
  type ProviderIdentity,
} from '../providerIdentity';
import { getChartSeriesColor } from '../chartTheme';

/**
 * Parity table with `backend/tests/test_provider_identity.py` — every case
 * here mirrors a backend test case for `derive_provider_identity`
 * (analytics-provider-views T-001/T-003). Case names reference the backend
 * test method they parallel; keep both files in sync when either changes.
 */
const PARITY_CASES: Array<{
  name: string;
  input: DeriveProviderIdentityInput;
  expected: Partial<ProviderIdentity>;
}> = [
  // ── TestProviderVendor ─────────────────────────────────────────────────
  { name: 'test_claude_vendor_is_anthropic', input: { model: 'claude-opus-4-5-20251101' }, expected: { providerVendor: 'Anthropic' } },
  { name: 'test_gpt_vendor_is_openai', input: { model: 'gpt-5.6-terra' }, expected: { providerVendor: 'OpenAI' } },
  { name: 'test_gemini_vendor_is_google', input: { model: 'gemini-3.5-flash' }, expected: { providerVendor: 'Google' } },
  { name: 'test_unrecognized_model_is_unknown_vendor', input: { model: 'mistral-large' }, expected: { providerVendor: 'Unknown' } },
  { name: 'test_synthetic_model_is_unknown_vendor', input: { model: '<synthetic>' }, expected: { providerVendor: 'Unknown' } },
  { name: 'test_empty_model_is_unknown_vendor', input: { model: '' }, expected: { providerVendor: 'Unknown' } },
  { name: 'test_none_model_is_unknown_vendor', input: { model: null }, expected: { providerVendor: 'Unknown' } },

  // ── TestProviderSurface ────────────────────────────────────────────────
  { name: 'test_claude_code_surface', input: { model: 'claude-sonnet-5', platformType: 'Claude Code' }, expected: { providerSurface: 'Claude Code' } },
  { name: 'test_codex_surface', input: { model: 'gpt-5.6-terra', platformType: 'Codex' }, expected: { providerSurface: 'Codex' } },
  { name: 'test_case_insensitive_surface_normalization', input: { model: 'gpt-5.6-terra', platformType: 'codex' }, expected: { providerSurface: 'Codex' } },
  { name: 'test_empty_platform_type_is_unknown_surface', input: { model: 'claude-sonnet-5', platformType: '' }, expected: { providerSurface: 'Unknown' } },
  { name: 'test_none_platform_type_is_unknown_surface', input: { model: 'claude-sonnet-5', platformType: null }, expected: { providerSurface: 'Unknown' } },

  // ── TestProviderChannel ─────────────────────────────────────────────────
  { name: 'test_launcher_containing_ica_wins', input: { model: 'claude-sonnet-5', launcher: 'ica-claude' }, expected: { providerChannel: 'ica' } },
  { name: 'test_launcher_containing_ica_case_insensitive', input: { model: 'claude-sonnet-5', launcher: 'ICA-Gateway' }, expected: { providerChannel: 'ica' } },
  { name: 'test_launcher_containing_api_wins', input: { model: 'claude-sonnet-5', launcher: 'direct-api-runner' }, expected: { providerChannel: 'api' } },
  { name: 'test_other_launcher_is_subscription', input: { model: 'claude-sonnet-5', launcher: 'claude-code-cli' }, expected: { providerChannel: 'subscription' } },
  {
    name: 'test_launcher_authoritative_over_model_variant',
    input: { model: 'claude-sonnet-5', launcher: 'claude-code-cli', modelVariant: '[1m]' },
    expected: { providerChannel: 'subscription' },
  },
  { name: 'test_model_variant_bracketed_1m_is_ica', input: { model: 'claude-sonnet-5', modelVariant: '[1m]' }, expected: { providerChannel: 'ica' } },
  { name: 'test_model_variant_bare_1m_is_ica', input: { model: 'claude-sonnet-5', modelVariant: '1m' }, expected: { providerChannel: 'ica' } },
  {
    name: 'test_model_variant_suffixed_1m_is_ica',
    input: { model: 'claude-sonnet-5', modelVariant: 'claude-sonnet-5[1m]' },
    expected: { providerChannel: 'ica' },
  },
  { name: 'test_model_variant_without_1m_is_unknown', input: { model: 'claude-sonnet-5', modelVariant: 'standard' }, expected: { providerChannel: 'unknown' } },
  { name: 'test_no_launcher_no_variant_is_unknown', input: { model: 'claude-sonnet-5' }, expected: { providerChannel: 'unknown' } },
  {
    name: 'test_todays_all_empty_capture_columns_yield_unknown_channel',
    input: { model: 'claude-opus-4-5', platformType: 'Claude Code', launcher: '', modelVariant: '' },
    expected: { providerChannel: 'unknown' },
  },

  // ── TestProviderIdAndLabel ──────────────────────────────────────────────
  {
    name: 'test_provider_id_is_slugified_triple',
    input: { model: 'claude-sonnet-5', platformType: 'Claude Code', launcher: 'claude-code-cli' },
    expected: { providerId: 'anthropic:claude-code:subscription' },
  },
  { name: 'test_provider_id_unknown_triple', input: { model: null }, expected: { providerId: 'unknown:unknown:unknown' } },
  {
    name: 'test_provider_label_no_suffix_for_subscription',
    input: { model: 'claude-sonnet-5', platformType: 'Claude Code', launcher: 'claude-code-cli' },
    expected: { providerLabel: 'Anthropic · Claude Code' },
  },
  {
    name: 'test_provider_label_no_suffix_for_unknown_channel',
    input: { model: 'claude-sonnet-5', platformType: 'Claude Code' },
    expected: { providerLabel: 'Anthropic · Claude Code' },
  },
  {
    name: 'test_provider_label_ica_suffix',
    input: { model: 'claude-sonnet-5', platformType: 'Claude Code', launcher: 'ica-claude' },
    expected: { providerLabel: 'Anthropic · Claude Code · ICA' },
  },
  {
    name: 'test_provider_label_api_suffix',
    input: { model: 'claude-sonnet-5', platformType: 'Claude Code', launcher: 'api-runner' },
    expected: { providerLabel: 'Anthropic · Claude Code · API' },
  },

  // ── TestCodexSlugs ──────────────────────────────────────────────────────
  {
    name: 'test_codex_gpt_terra_full_identity',
    input: { model: 'gpt-5.6-terra', platformType: 'Codex' },
    expected: {
      providerVendor: 'OpenAI',
      providerSurface: 'Codex',
      providerChannel: 'unknown',
      providerId: 'openai:codex:unknown',
      providerLabel: 'OpenAI · Codex',
    },
  },
];

describe('deriveProviderIdentity — parity table (mirrors backend/tests/test_provider_identity.py)', () => {
  it.each(PARITY_CASES)('$name', ({ input, expected }) => {
    expect(deriveProviderIdentity(input)).toMatchObject(expected);
  });
});

describe('deriveProviderIdentity — return shape', () => {
  it('returns exactly the five documented keys', () => {
    const result = deriveProviderIdentity({ model: 'claude-sonnet-5', platformType: 'Claude Code' });
    expect(Object.keys(result).sort()).toEqual(
      ['providerChannel', 'providerId', 'providerLabel', 'providerSurface', 'providerVendor'].sort(),
    );
  });

  it('all values are strings', () => {
    const result = deriveProviderIdentity({ model: 'claude-sonnet-5', platformType: 'Claude Code', launcher: 'ica' });
    Object.values(result).forEach((value) => expect(typeof value).toBe('string'));
  });

  it('unrecognized non-empty platformType passes through unmodified (not collapsed to Unknown)', () => {
    const result = deriveProviderIdentity({ model: 'gemini-3.5-flash', platformType: 'gemini-cli' });
    expect(result.providerSurface).toBe('gemini-cli');
  });
});

describe('getProviderTone', () => {
  it('maps the two live provider combos onto distinct, stable tones', () => {
    const claudeCodeTone = getProviderTone('anthropic:claude-code:unknown');
    const codexTone = getProviderTone('openai:codex:unknown');
    expect(claudeCodeTone).not.toBe(codexTone);
    // Stable across repeated calls (no randomness).
    expect(getProviderTone('anthropic:claude-code:unknown')).toBe(claudeCodeTone);
  });

  it('resolves a real chart color, never an invented one', () => {
    const tone = getProviderTone('anthropic:claude-code:unknown');
    expect(typeof getChartSeriesColor(tone)).toBe('string');
    expect(getChartSeriesColor(tone)).toBe(getChartSeriesColor(tone));
  });

  it('gives an unmapped provider id a deterministic fallback tone', () => {
    const first = getProviderTone('anthropic:desktop:unknown');
    const second = getProviderTone('anthropic:desktop:unknown');
    expect(first).toBe(second);
  });
});
