'use client';

import {
  createContext, useContext, useEffect, useMemo, useState, useCallback, ReactNode,
} from 'react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { buildTheme } from '../lib/theme';

type ThemeMode = 'light' | 'dark';

interface AppShellContextValue {
  isDark:       boolean;
  primaryColor: string;
  themeMode:    ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
  toggleTheme:  () => void;
}

const AppShellContext = createContext<AppShellContextValue>({
  isDark:       true,
  primaryColor: '#f92aad',
  themeMode:    'dark',
  setThemeMode: () => {},
  toggleTheme:  () => {},
});

const THEME_KEY = 'theme';

/**
 * AppShellProvider — single source of theme truth for all (app) pages.
 * Reads the initial mode from localStorage ("theme") and wraps children in
 * the MUI ThemeProvider so individual pages no longer manage their own theme.
 */
export function AppShellProvider({ children }: { children: ReactNode }) {
  // SSR-safe: start with the existing default ('dark') and hydrate from
  // localStorage in an effect to avoid a hydration mismatch.
  const [themeMode, setThemeModeState] = useState<ThemeMode>('dark');

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(THEME_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration of persisted pref
      if (stored === 'light' || stored === 'dark') setThemeModeState(stored);
    } catch { /* localStorage unavailable — keep default */ }
  }, []);

  const setThemeMode = useCallback((mode: ThemeMode) => {
    setThemeModeState(mode);
    try { window.localStorage.setItem(THEME_KEY, mode); } catch { /* non-fatal */ }
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeModeState(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      try { window.localStorage.setItem(THEME_KEY, next); } catch { /* non-fatal */ }
      return next;
    });
  }, []);

  const theme        = useMemo(() => buildTheme(themeMode), [themeMode]);
  const isDark       = themeMode === 'dark';
  const primaryColor = isDark ? '#f92aad' : '#1e3a8a';

  const value = useMemo<AppShellContextValue>(
    () => ({ isDark, primaryColor, themeMode, setThemeMode, toggleTheme }),
    [isDark, primaryColor, themeMode, setThemeMode, toggleTheme],
  );

  return (
    <AppShellContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </AppShellContext.Provider>
  );
}

export const useAppShell = () => useContext(AppShellContext);
