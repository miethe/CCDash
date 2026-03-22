export const THEME_STORAGE_KEY = 'ccdash:theme-mode:v1';

export const THEME_PREFERENCES = ['dark', 'light', 'system'] as const;

export type ThemePreference = (typeof THEME_PREFERENCES)[number];
export type ResolvedTheme = Exclude<ThemePreference, 'system'>;

type ThemeStorage = Pick<Storage, 'getItem' | 'setItem'>;

type ThemeClassList = Pick<DOMTokenList, 'add' | 'remove'>;

type ThemeDocument = {
  documentElement: {
    classList: ThemeClassList;
    dataset?: DOMStringMap | Record<string, string>;
    style?: Pick<CSSStyleDeclaration, 'colorScheme'> | Record<string, string>;
  };
};

type ThemeMediaQueryEvent = {
  matches: boolean;
};

type ThemeMediaQueryList = {
  matches: boolean;
  addEventListener?: (type: 'change', listener: (event: ThemeMediaQueryEvent) => void) => void;
  removeEventListener?: (type: 'change', listener: (event: ThemeMediaQueryEvent) => void) => void;
  addListener?: (listener: (event: ThemeMediaQueryEvent) => void) => void;
  removeListener?: (listener: (event: ThemeMediaQueryEvent) => void) => void;
};

type ThemeMatchMedia = (query: string) => ThemeMediaQueryList;

export interface ThemeSnapshot {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
}

export const isThemePreference = (value: unknown): value is ThemePreference =>
  typeof value === 'string' && THEME_PREFERENCES.includes(value as ThemePreference);

export const parseThemePreference = (value: unknown): ThemePreference =>
  isThemePreference(value) ? value : 'system';

export const readThemePreference = (storage?: ThemeStorage | null): ThemePreference => {
  if (!storage) return 'system';
  try {
    return parseThemePreference(storage.getItem(THEME_STORAGE_KEY));
  } catch {
    return 'system';
  }
};

export const persistThemePreference = (
  preference: ThemePreference,
  storage?: ThemeStorage | null,
): void => {
  if (!storage) return;
  try {
    storage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Ignore persistence failures and keep the runtime contract functional.
  }
};

export const getSystemTheme = (matchMedia?: ThemeMatchMedia | null): ResolvedTheme => {
  if (!matchMedia) return 'light';
  try {
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
};

export const resolveThemePreference = (
  preference: ThemePreference,
  systemTheme: ResolvedTheme,
): ResolvedTheme => (preference === 'system' ? systemTheme : preference);

export const getThemeSnapshot = (params?: {
  storage?: ThemeStorage | null;
  matchMedia?: ThemeMatchMedia | null;
}): ThemeSnapshot => {
  const preference = readThemePreference(params?.storage);
  return {
    preference,
    resolvedTheme: resolveThemePreference(preference, getSystemTheme(params?.matchMedia)),
  };
};

export const applyThemeSnapshot = (
  themeDocument: ThemeDocument | null | undefined,
  snapshot: ThemeSnapshot,
): void => {
  if (!themeDocument) return;

  const root = themeDocument.documentElement;
  if (snapshot.resolvedTheme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }

  if (root.dataset) {
    root.dataset.theme = snapshot.resolvedTheme;
    root.dataset.themePreference = snapshot.preference;
  }

  if (root.style) {
    root.style.colorScheme = snapshot.resolvedTheme;
  }
};

export const initializeThemeMode = (params?: {
  document?: ThemeDocument | null;
  storage?: ThemeStorage | null;
  matchMedia?: ThemeMatchMedia | null;
}): ThemeSnapshot => {
  const snapshot = getThemeSnapshot({
    storage: params?.storage,
    matchMedia: params?.matchMedia,
  });
  applyThemeSnapshot(params?.document, snapshot);
  return snapshot;
};

export const subscribeToSystemTheme = (
  matchMedia: ThemeMatchMedia | null | undefined,
  listener: (theme: ResolvedTheme) => void,
): (() => void) => {
  if (!matchMedia) return () => {};

  const mediaQuery = matchMedia('(prefers-color-scheme: dark)');
  const handleChange = (event: ThemeMediaQueryEvent): void => {
    listener(event.matches ? 'dark' : 'light');
  };

  if (typeof mediaQuery.addEventListener === 'function' && typeof mediaQuery.removeEventListener === 'function') {
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener?.('change', handleChange);
  }

  if (typeof mediaQuery.addListener === 'function' && typeof mediaQuery.removeListener === 'function') {
    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener?.(handleChange);
  }

  return () => {};
};
