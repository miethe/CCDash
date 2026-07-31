/**
 * Provider identity derivation — additive, orthogonal to `modelProvider`
 * (backend/model_identity.py `_provider_label` → "Claude"/"OpenAI"/"Gemini",
 * consumed by session badges / `/api/sessions` / features / analytics
 * correlation). This module never touches that taxonomy.
 *
 * Mirrors backend `derive_provider_identity` in `backend/model_identity.py`
 * (T-001, analytics-provider-views quick feature) EXACTLY — this is the
 * single derivation path on the frontend; do not reimplement it elsewhere.
 * `lib/__tests__/providerIdentity.test.ts` carries a parity table intended
 * to match `backend/tests/test_provider_identity.py` case-for-case — drift
 * between the two implementations should fail CI.
 *
 * Grounding (see `.claude/progress/quick-features/analytics-provider-views.md`):
 * provider is modelled as three orthogonal axes, only two of which have live
 * data today:
 *  - providerVendor  — from the model slug (live)
 *  - providerSurface — from `platformType` (live)
 *  - providerChannel — from `launcher` / `modelVariant` (structurally wired;
 *    resolves to 'unknown' for ~100% of rows until launch-time capture is
 *    activated — never faked or inferred beyond the documented signals)
 */

import { CHART_SERIES_COLORS, getChartSeriesColor } from './chartTheme';

export type ProviderChannel = 'subscription' | 'ica' | 'api' | 'unknown';

export interface ProviderIdentity {
  /** 'Anthropic' | 'OpenAI' | 'Google' | 'Unknown' */
  providerVendor: string;
  /** 'Claude Code' | 'Codex' | the raw platformType string | 'Unknown' */
  providerSurface: string;
  providerChannel: ProviderChannel;
  /** Stable slug: `${vendor}:${surface}:${channel}`, each segment slugified. */
  providerId: string;
  /** Display string, e.g. "Anthropic · Claude Code"; a " · ICA" / " · API" suffix is appended only for those channels. */
  providerLabel: string;
}

export interface DeriveProviderIdentityInput {
  model?: string | null;
  platformType?: string | null;
  launcher?: string | null;
  modelVariant?: string | null;
}

const PROVIDER_VENDOR_TOKENS: Record<string, string> = {
  claude: 'Anthropic',
  gpt: 'OpenAI',
  openai: 'OpenAI',
  gemini: 'Google',
};

const PROVIDER_SURFACE_LABELS: Record<string, string> = {
  'claude code': 'Claude Code',
  codex: 'Codex',
};

const PROVIDER_CHANNEL_LABEL_SUFFIX: Partial<Record<ProviderChannel, string>> = {
  ica: 'ICA',
  api: 'API',
};

/** Matches a `1m` token delimited by start/end/`[`/`-`/`_`, e.g. "claude-sonnet-5[1m]" or "sonnet-1m". */
const ICA_MODEL_VARIANT_PATTERN = /(?:^|[[\-_])1m(?:$|[\]\-_])/;

/**
 * Derive the model vendor (Anthropic/OpenAI/Google/Unknown) from a raw model
 * slug. Deliberately independent of the existing "Claude"/"OpenAI"/"Gemini"
 * `modelProvider` display labels — only recognizes the vendors CCDash
 * currently observes; anything else is "Unknown", never a title-cased guess.
 */
function deriveProviderVendor(model: string | null | undefined): string {
  const raw = (model || '').trim().toLowerCase();
  if (!raw) return 'Unknown';
  const parts = raw.split(/[-_\s]+/).filter(Boolean);
  const token = parts[0] || '';
  return PROVIDER_VENDOR_TOKENS[token] ?? 'Unknown';
}

/** Normalizes a session's platformType into a provider surface label. Empty → "Unknown"; unrecognized non-empty values pass through unmodified. */
function deriveProviderSurface(platformType: string | null | undefined): string {
  const raw = (platformType || '').trim();
  if (!raw) return 'Unknown';
  return PROVIDER_SURFACE_LABELS[raw.toLowerCase()] ?? raw;
}

function deriveProviderChannel(
  launcher: string | null | undefined,
  modelVariant: string | null | undefined,
): ProviderChannel {
  const launcherNorm = (launcher || '').trim().toLowerCase();
  if (launcherNorm) {
    if (launcherNorm.includes('ica')) return 'ica';
    if (launcherNorm.includes('api')) return 'api';
    return 'subscription';
  }

  const variantNorm = (modelVariant || '').trim().toLowerCase();
  if (variantNorm && ICA_MODEL_VARIANT_PATTERN.test(variantNorm)) return 'ica';

  return 'unknown';
}

function providerSlug(value: string): string {
  const lowered = (value || '').trim().toLowerCase();
  const slug = lowered.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return slug || 'unknown';
}

export function deriveProviderIdentity(input: DeriveProviderIdentityInput): ProviderIdentity {
  const providerVendor = deriveProviderVendor(input.model);
  const providerSurface = deriveProviderSurface(input.platformType);
  const providerChannel = deriveProviderChannel(input.launcher, input.modelVariant);

  const providerId = [providerSlug(providerVendor), providerSlug(providerSurface), providerSlug(providerChannel)].join(':');

  let providerLabel = `${providerVendor} · ${providerSurface}`;
  const channelSuffix = PROVIDER_CHANNEL_LABEL_SUFFIX[providerChannel];
  if (channelSuffix) {
    providerLabel = `${providerLabel} · ${channelSuffix}`;
  }

  return { providerVendor, providerSurface, providerChannel, providerId, providerLabel };
}

// ── Chart tone mapping ──────────────────────────────────────────────────────

export type ProviderChartTone = keyof typeof CHART_SERIES_COLORS;

/** Fixed tone assignment for the vendor:surface combos observed/anticipated today. */
const PROVIDER_TONE_MAP: Record<string, ProviderChartTone> = {
  'anthropic:claude-code': 'primary',
  'openai:codex': 'secondary',
  'google:unknown': 'tertiary',
  'unknown:unknown': 'info',
};

const FALLBACK_TONES: ProviderChartTone[] = ['quaternary', 'quinary', 'success', 'warning', 'danger'];

/** Deterministic string hash (FNV-ish) so unmapped provider ids get a stable, repeatable tone. */
function hashKey(key: string): number {
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return hash;
}

/**
 * Maps a `ProviderIdentity.providerId` (or any `vendor:surface[:channel]`
 * slug) onto a stable `ChartSeriesTone` key from `lib/chartTheme.ts`. Never
 * invents new colors — callers resolve the actual color via
 * `getChartSeriesColor(getProviderTone(providerId))`.
 */
export function getProviderTone(providerId: string): ProviderChartTone {
  const [vendor = 'unknown', surface = 'unknown'] = (providerId || '').split(':');
  const key = `${vendor}:${surface}`;
  const mapped = PROVIDER_TONE_MAP[key];
  if (mapped) return mapped;
  const tone = FALLBACK_TONES[hashKey(key) % FALLBACK_TONES.length];
  return tone;
}

// Re-exported for convenience so callers don't need a second import for the
// common "give me a color" case.
export { getChartSeriesColor };
