import { describe, expect, it, vi } from 'vitest';

import {
  THEME_STORAGE_KEY,
  applyThemeSnapshot,
  getThemeSnapshot,
  parseThemePreference,
  readThemePreference,
  resolveThemePreference,
  subscribeToSystemTheme,
} from '../themeMode';

describe('themeMode', () => {
  it('parses stored preferences with a system fallback', () => {
    expect(parseThemePreference('dark')).toBe('dark');
    expect(parseThemePreference('light')).toBe('light');
    expect(parseThemePreference('system')).toBe('system');
    expect(parseThemePreference('invalid')).toBe('system');
  });

  it('reads and resolves the stored preference against system theme', () => {
    const storage = {
      getItem: vi.fn(() => 'system'),
      setItem: vi.fn(),
    };
    const matchMedia = vi.fn(() => ({ matches: true }));

    expect(readThemePreference(storage)).toBe('system');
    expect(resolveThemePreference('system', 'dark')).toBe('dark');
    expect(getThemeSnapshot({ storage, matchMedia })).toEqual({
      preference: 'system',
      resolvedTheme: 'dark',
    });
    expect(storage.getItem).toHaveBeenCalledWith(THEME_STORAGE_KEY);
  });

  it('applies the theme snapshot to the document root contract', () => {
    const add = vi.fn();
    const remove = vi.fn();
    const dataset: Record<string, string> = {};
    const style: Record<string, string> = {};
    const themeDocument = {
      documentElement: {
        classList: { add, remove },
        dataset,
        style,
      },
    };

    applyThemeSnapshot(themeDocument, {
      preference: 'system',
      resolvedTheme: 'dark',
    });

    expect(add).toHaveBeenCalledWith('dark');
    expect(remove).not.toHaveBeenCalled();
    expect(dataset.theme).toBe('dark');
    expect(dataset.themePreference).toBe('system');
    expect(style.colorScheme).toBe('dark');
  });

  it('subscribes to system-theme changes through modern media query listeners', () => {
    const addEventListener = vi.fn();
    const removeEventListener = vi.fn();
    const listener = vi.fn();
    let registeredListener: ((event: { matches: boolean }) => void) | undefined;

    addEventListener.mockImplementation((_type, nextListener) => {
      registeredListener = nextListener;
    });

    const unsubscribe = subscribeToSystemTheme(
      () => ({
        matches: false,
        addEventListener,
        removeEventListener,
      }),
      listener,
    );

    registeredListener?.({ matches: true });
    expect(listener).toHaveBeenCalledWith('dark');

    unsubscribe();
    expect(removeEventListener).toHaveBeenCalled();
  });
});
