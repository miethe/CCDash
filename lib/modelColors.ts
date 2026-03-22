import { CSSProperties } from 'react';
import { SessionModelFacet } from '../types';

export interface ModelColorSettings {
  familyColors: Record<string, string>;
  modelColors: Record<string, string>;
}

export interface ModelRegistryFamily {
  label: string;
  count: number;
}

export interface ModelRegistryModel {
  raw: string;
  label: string;
  family: string;
  provider: string;
  version: string;
  count: number;
}

export interface ModelColorRegistry {
  families: ModelRegistryFamily[];
  models: ModelRegistryModel[];
  familyLabelByKey: Record<string, string>;
  modelByKey: Record<string, ModelRegistryModel>;
}

const DEFAULT_COLOR = '#94a3b8';
const DEFAULT_PALETTE = [
  '#f97316',
  '#22c55e',
  '#38bdf8',
  '#f43f5e',
  '#a78bfa',
  '#14b8a6',
  '#f59e0b',
  '#84cc16',
  '#0ea5e9',
  '#ec4899',
  '#8b5cf6',
  '#10b981',
  '#3b82f6',
  '#ef4444',
  '#06b6d4',
  '#eab308',
];

const stableHash = (value: string): number => {
  let hash = 0;
  const input = String(value || '');
  for (let idx = 0; idx < input.length; idx += 1) {
    hash = (hash * 31 + input.charCodeAt(idx)) >>> 0;
  }
  return hash;
};

const normalizeLabel = (value: string): string => String(value || '').trim();

export const normalizeModelToken = (value: string): string => normalizeLabel(value).toLowerCase();

export const sanitizeHexColor = (value: string): string => {
  const raw = normalizeLabel(value);
  if (!raw) return '';
  const normalized = raw.startsWith('#') ? raw : `#${raw}`;
  if (/^#[0-9a-fA-F]{6}$/.test(normalized)) return normalized.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(normalized)) {
    const r = normalized[1];
    const g = normalized[2];
    const b = normalized[3];
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
  }
  return '';
};

const pickPaletteColor = (key: string): string => {
  if (!key) return DEFAULT_COLOR;
  return DEFAULT_PALETTE[stableHash(key) % DEFAULT_PALETTE.length];
};

const hexToRgb = (color: string): { r: number; g: number; b: number } | null => {
  const normalized = sanitizeHexColor(color);
  if (!normalized) return null;
  const value = normalized.slice(1);
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return { r, g, b };
};

const withAlpha = (rgb: { r: number; g: number; b: number }, alpha: number): string =>
  `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;

const brighten = (channel: number, amount: number): number =>
  Math.max(0, Math.min(255, Math.round(channel + (255 - channel) * amount)));

// Model colors are domain accents. They intentionally remain data-driven and must
// not replace the app's semantic theme tokens for shared surfaces or shell chrome.
export const toColorBadgeStyle = (color: string): CSSProperties => {
  const rgb = hexToRgb(color) || hexToRgb(DEFAULT_COLOR)!;
  return {
    color: `rgb(${brighten(rgb.r, 0.35)}, ${brighten(rgb.g, 0.35)}, ${brighten(rgb.b, 0.35)})`,
    borderColor: withAlpha(rgb, 0.45),
    backgroundColor: withAlpha(rgb, 0.17),
  };
};

export const toModelBadgeStyle = (color: string): CSSProperties => toColorBadgeStyle(color);

export const resolveStablePaletteColor = (value: string, namespace = 'badge'): string => {
  const key = normalizeModelToken(value);
  if (!key) return DEFAULT_COLOR;
  return pickPaletteColor(`${namespace}:${key}`);
};

export const emptyModelColorRegistry: ModelColorRegistry = {
  families: [],
  models: [],
  familyLabelByKey: {},
  modelByKey: {},
};

export const buildModelColorRegistry = (facets: SessionModelFacet[]): ModelColorRegistry => {
  if (!Array.isArray(facets) || facets.length === 0) {
    return emptyModelColorRegistry;
  }

  const familyMap = new Map<string, ModelRegistryFamily>();
  const modelMap = new Map<string, ModelRegistryModel>();

  facets.forEach(facet => {
    const raw = normalizeLabel(facet.raw);
    if (!raw) return;

    const family = normalizeLabel(facet.modelFamily) || 'Unknown';
    const provider = normalizeLabel(facet.modelProvider);
    const version = normalizeLabel(facet.modelVersion);
    const label = normalizeLabel(facet.modelDisplayName) || raw;
    const count = Math.max(0, Number(facet.count || 0));

    const familyKey = normalizeModelToken(family);
    const existingFamily = familyMap.get(familyKey);
    if (existingFamily) {
      existingFamily.count += count;
    } else {
      familyMap.set(familyKey, { label: family, count });
    }

    const modelKey = normalizeModelToken(raw);
    const existingModel = modelMap.get(modelKey);
    if (existingModel) {
      existingModel.count += count;
      if (!existingModel.label && label) existingModel.label = label;
      if (!existingModel.family && family) existingModel.family = family;
      if (!existingModel.provider && provider) existingModel.provider = provider;
      if (!existingModel.version && version) existingModel.version = version;
    } else {
      modelMap.set(modelKey, {
        raw,
        label,
        family,
        provider,
        version,
        count,
      });
    }
  });

  const families = Array.from(familyMap.values()).sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.label.localeCompare(b.label);
  });

  const models = Array.from(modelMap.values()).sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.label.localeCompare(b.label);
  });

  return {
    families,
    models,
    familyLabelByKey: Object.fromEntries(
      families.map(entry => [normalizeModelToken(entry.label), entry.label]),
    ),
    modelByKey: Object.fromEntries(
      models.map(entry => [normalizeModelToken(entry.raw), entry]),
    ),
  };
};

export const resolveModelColor = (
  params: {
    model?: string;
    family?: string;
  },
  settings: ModelColorSettings,
  registry: ModelColorRegistry,
): string => {
  const modelKey = normalizeModelToken(params.model || '');
  if (modelKey) {
    const modelOverride = sanitizeHexColor(settings.modelColors[modelKey] || '');
    if (modelOverride) return modelOverride;
  }

  let familyKey = normalizeModelToken(params.family || '');
  if (!familyKey && modelKey) {
    familyKey = normalizeModelToken(registry.modelByKey[modelKey]?.family || '');
  }
  if (familyKey) {
    const familyOverride = sanitizeHexColor(settings.familyColors[familyKey] || '');
    if (familyOverride) return familyOverride;
  }

  if (modelKey) return pickPaletteColor(modelKey);
  if (familyKey) return pickPaletteColor(`family:${familyKey}`);
  return DEFAULT_COLOR;
};
