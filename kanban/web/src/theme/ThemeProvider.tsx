import React, { createContext, useContext, useEffect, useState, useMemo } from 'react';

export type Theme = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

export interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
}

export const THEME_STORAGE_KEY = 'kb.theme';
const VALID_THEMES = new Set<Theme>(['light', 'dark', 'system']);

/**
 * Validates and sanitizes stored theme value, falling back to 'system' on hostile inputs.
 */
export function sanitizeTheme(stored: string | null): Theme {
  if (stored && VALID_THEMES.has(stored as Theme)) {
    return stored as Theme;
  }
  return 'system';
}

/**
 * Returns current system color scheme preference ('light' | 'dark').
 */
export function getSystemResolvedTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'light';
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/**
 * Provides theme state, system preference resolution, and DOM dataset synchronization.
 * Uses pure dataset attribute mutation without inline style injection to comply with CSP.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      const sanitized = sanitizeTheme(stored);
      if (stored !== null && stored !== sanitized) {
        localStorage.setItem(THEME_STORAGE_KEY, 'system');
      }
      return sanitized;
    } catch {
      return 'system';
    }
  });

  const [systemDark, setSystemDark] = useState<boolean>(() => {
    if (typeof window.matchMedia !== 'function') {
      return false;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return;
    }
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const update = (e: MediaQueryListEvent): void => {
      setSystemDark(e.matches);
    };
    mql.addEventListener('change', update);
    return () => {
      mql.removeEventListener('change', update);
    };
  }, []);

  const resolvedTheme: ResolvedTheme = useMemo(() => {
    if (theme === 'system') {
      return systemDark ? 'dark' : 'light';
    }
    return theme;
  }, [theme, systemDark]);

  useEffect(() => {
    if (theme === 'system') {
      delete document.documentElement.dataset.theme;
    } else {
      document.documentElement.dataset.theme = theme;
    }
  }, [theme]);

  const setTheme = (newTheme: Theme): void => {
    const sanitized = sanitizeTheme(newTheme);
    setThemeState(sanitized);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, sanitized);
    } catch {
      // Ignore storage errors in restricted contexts
    }
  };

  const contextValue = useMemo<ThemeContextValue>(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
    }),
    [theme, resolvedTheme],
  );

  return <ThemeContext.Provider value={contextValue}>{children}</ThemeContext.Provider>;
}

/**
 * Accesses active theme context and controls.
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
