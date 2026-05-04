import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useData } from './DataContext';
import { SessionModelFacet } from '../types';
import {
  buildModelColorRegistry,
  emptyModelColorRegistry,
  ModelColorRegistry,
  ModelColorSettings,
  normalizeModelToken,
  resolveModelColor,
  sanitizeHexColor,
  toModelBadgeStyle,
} from '../lib/modelColors';
import { apiFetch } from '../services/apiClient';

const STORAGE_PREFIX = 'ccdash:model-colors:v1';

const defaultSettings: ModelColorSettings = {
  familyColors: {},
  modelColors: {},
};

interface ModelColorsContextValue {
  modelFacets: SessionModelFacet[];
  modelFacetsLoading: boolean;
  registry: ModelColorRegistry;
  familyColorOverrides: Record<string, string>;
  modelColorOverrides: Record<string, string>;
  getFamilyOverrideColor: (family: string) => string;
  getModelOverrideColor: (model: string) => string;
  setFamilyColorOverride: (family: string, color: string) => void;
  clearFamilyColorOverride: (family: string) => void;
  setModelColorOverride: (model: string, color: string) => void;
  clearModelColorOverride: (model: string) => void;
  getColorForModel: (params: { model?: string; family?: string }) => string;
  getBadgeStyleForModel: (params: { model?: string; family?: string }) => React.CSSProperties;
}

const ModelColorsContext = createContext<ModelColorsContextValue | null>(null);

const storageKeyForProject = (projectId: string): string => `${STORAGE_PREFIX}:${projectId || 'default'}`;

const loadSettings = (projectId: string): ModelColorSettings => {
  if (typeof window === 'undefined') return defaultSettings;
  try {
    const raw = window.localStorage.getItem(storageKeyForProject(projectId));
    if (!raw) return defaultSettings;
    const parsed = JSON.parse(raw) as Partial<ModelColorSettings> | null;
    return {
      familyColors: parsed?.familyColors && typeof parsed.familyColors === 'object' ? parsed.familyColors : {},
      modelColors: parsed?.modelColors && typeof parsed.modelColors === 'object' ? parsed.modelColors : {},
    };
  } catch {
    return defaultSettings;
  }
};

const persistSettings = (projectId: string, settings: ModelColorSettings): void => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(storageKeyForProject(projectId), JSON.stringify(settings));
  } catch {
    // Ignore persistence failures and keep runtime behavior functional.
  }
};

const normalizeFacet = (item: any): SessionModelFacet => ({
  raw: String(item?.raw || ''),
  modelDisplayName: String(item?.modelDisplayName || ''),
  modelProvider: String(item?.modelProvider || ''),
  modelFamily: String(item?.modelFamily || ''),
  modelVersion: String(item?.modelVersion || ''),
  count: Number(item?.count || 0),
});

export const ModelColorsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { activeProject } = useData();
  const projectId = String(activeProject?.id || '');
  const [settings, setSettings] = useState<ModelColorSettings>(() => loadSettings(projectId));
  const [modelFacets, setModelFacets] = useState<SessionModelFacet[]>([]);
  const [modelFacetsLoading, setModelFacetsLoading] = useState(false);

  useEffect(() => {
    setSettings(loadSettings(projectId));
  }, [projectId]);

  useEffect(() => {
    persistSettings(projectId, settings);
  }, [projectId, settings]);

  useEffect(() => {
    let cancelled = false;
    setModelFacetsLoading(true);
    apiFetch('/api/sessions/facets/models?include_subagents=true')
      .then(async (res) => {
        if (!res.ok) throw new Error(`Failed to load model facets (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        const rows = Array.isArray(data) ? data.map(normalizeFacet).filter(item => item.raw) : [];
        setModelFacets(rows);
        setModelFacetsLoading(false);
      })
      .catch((error) => {
        if (cancelled) return;
        console.warn('Failed to load model facets for color settings', error);
        setModelFacets([]);
        setModelFacetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const registry = useMemo(
    () => (modelFacets.length > 0 ? buildModelColorRegistry(modelFacets) : emptyModelColorRegistry),
    [modelFacets],
  );

  const getFamilyOverrideColor = useCallback(
    (family: string): string => settings.familyColors[normalizeModelToken(family)] || '',
    [settings.familyColors],
  );

  const getModelOverrideColor = useCallback(
    (model: string): string => settings.modelColors[normalizeModelToken(model)] || '',
    [settings.modelColors],
  );

  const setFamilyColorOverride = useCallback((family: string, color: string) => {
    const key = normalizeModelToken(family);
    const nextColor = sanitizeHexColor(color);
    if (!key || !nextColor) return;
    setSettings(prev => ({
      ...prev,
      familyColors: {
        ...prev.familyColors,
        [key]: nextColor,
      },
    }));
  }, []);

  const clearFamilyColorOverride = useCallback((family: string) => {
    const key = normalizeModelToken(family);
    if (!key) return;
    setSettings(prev => {
      const next = { ...prev.familyColors };
      delete next[key];
      return { ...prev, familyColors: next };
    });
  }, []);

  const setModelColorOverride = useCallback((model: string, color: string) => {
    const key = normalizeModelToken(model);
    const nextColor = sanitizeHexColor(color);
    if (!key || !nextColor) return;
    setSettings(prev => ({
      ...prev,
      modelColors: {
        ...prev.modelColors,
        [key]: nextColor,
      },
    }));
  }, []);

  const clearModelColorOverride = useCallback((model: string) => {
    const key = normalizeModelToken(model);
    if (!key) return;
    setSettings(prev => {
      const next = { ...prev.modelColors };
      delete next[key];
      return { ...prev, modelColors: next };
    });
  }, []);

  const getColorForModel = useCallback(
    (params: { model?: string; family?: string }): string => resolveModelColor(params, settings, registry),
    [settings, registry],
  );

  const getBadgeStyleForModel = useCallback(
    (params: { model?: string; family?: string }): React.CSSProperties => toModelBadgeStyle(getColorForModel(params)),
    [getColorForModel],
  );

  const value = useMemo<ModelColorsContextValue>(() => ({
    modelFacets,
    modelFacetsLoading,
    registry,
    familyColorOverrides: settings.familyColors,
    modelColorOverrides: settings.modelColors,
    getFamilyOverrideColor,
    getModelOverrideColor,
    setFamilyColorOverride,
    clearFamilyColorOverride,
    setModelColorOverride,
    clearModelColorOverride,
    getColorForModel,
    getBadgeStyleForModel,
  }), [
    modelFacets,
    modelFacetsLoading,
    registry,
    settings.familyColors,
    settings.modelColors,
    getFamilyOverrideColor,
    getModelOverrideColor,
    setFamilyColorOverride,
    clearFamilyColorOverride,
    setModelColorOverride,
    clearModelColorOverride,
    getColorForModel,
    getBadgeStyleForModel,
  ]);

  return (
    <ModelColorsContext.Provider value={value}>
      {children}
    </ModelColorsContext.Provider>
  );
};

export const useModelColors = (): ModelColorsContextValue => {
  const context = useContext(ModelColorsContext);
  if (!context) {
    throw new Error('useModelColors must be used within a ModelColorsProvider');
  }
  return context;
};
