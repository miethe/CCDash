import React, { createContext, useContext, useEffect, useEffectEvent, useMemo, useState } from 'react';

import {
  ThemePreference,
  ThemeSnapshot,
  applyThemeSnapshot,
  getThemeSnapshot,
  persistThemePreference,
  resolveThemePreference,
  subscribeToSystemTheme,
} from '../lib/themeMode';

interface ThemeContextValue extends ThemeSnapshot {
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const getBrowserSnapshot = (): ThemeSnapshot =>
  getThemeSnapshot({
    storage: typeof window === 'undefined' ? null : window.localStorage,
    matchMedia: typeof window === 'undefined' ? null : window.matchMedia.bind(window),
  });

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [preference, setPreference] = useState<ThemePreference>(() => getBrowserSnapshot().preference);
  const [resolvedTheme, setResolvedTheme] = useState<ThemeSnapshot['resolvedTheme']>(
    () => getBrowserSnapshot().resolvedTheme,
  );

  const syncTheme = useEffectEvent((nextPreference: ThemePreference) => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;

    const nextResolvedTheme = resolveThemePreference(
      nextPreference,
      window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
    );

    setResolvedTheme((currentTheme) => (currentTheme === nextResolvedTheme ? currentTheme : nextResolvedTheme));
    applyThemeSnapshot(document, {
      preference: nextPreference,
      resolvedTheme: nextResolvedTheme,
    });
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    persistThemePreference(preference, window.localStorage);
    syncTheme(preference);
  }, [preference, syncTheme]);

  useEffect(() => {
    if (preference !== 'system' || typeof window === 'undefined' || typeof document === 'undefined') {
      return;
    }

    return subscribeToSystemTheme(window.matchMedia.bind(window), (systemTheme) => {
      setResolvedTheme((currentTheme) => (currentTheme === systemTheme ? currentTheme : systemTheme));
      applyThemeSnapshot(document, {
        preference: 'system',
        resolvedTheme: systemTheme,
      });
    });
  }, [preference]);

  const value = useMemo<ThemeContextValue>(() => ({
    preference,
    resolvedTheme,
    setPreference,
  }), [preference, resolvedTheme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextValue => {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return value;
};
