/**
 * ThemeContext — Light/Dark mode with AsyncStorage persistence.
 * Auto-detects system theme on first launch.
 */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'mg_theme';

export type ThemeMode = 'light' | 'dark' | 'system';

export interface Colors {
  bg: string;
  card: string;
  text: string;
  textSecondary: string;
  textTertiary: string;
  accent: string;
  border: string;
  inputBg: string;
  statusBar: 'light' | 'dark';
  shadow: string;
  chipBg: string;
  chipActiveBg: string;
  tagBg: string;
  tagText: string;
  toastBg: string;
  toastBorder: string;
  toastText: string;
}

const LIGHT: Colors = {
  bg: '#fffdfb',
  card: '#fff',
  text: '#262b35',
  textSecondary: '#5d6578',
  textTertiary: '#9aa3b4',
  accent: '#4285F4',
  border: '#f0ede8',
  inputBg: 'rgba(255,255,255,0.85)',
  statusBar: 'dark',
  shadow: '#e4dfd6',
  chipBg: '#f4f2ef',
  chipActiveBg: '#4285F4',
  tagBg: '#f0f4ff',
  tagText: '#4285F4',
  toastBg: '#fffbeb',
  toastBorder: '#fde68a',
  toastText: '#92400e',
};

const DARK: Colors = {
  bg: '#0f0f0f',
  card: '#1c1c1e',
  text: '#e8e8ec',
  textSecondary: '#a1a1aa',
  textTertiary: '#71717a',
  accent: '#60a5fa',
  border: '#333338',
  inputBg: '#2c2c2e',
  statusBar: 'light',
  shadow: '#000',
  chipBg: '#2c2c2e',
  chipActiveBg: '#3b82f6',
  tagBg: '#1e293b',
  tagText: '#60a5fa',
  toastBg: '#422006',
  toastBorder: '#854d0e',
  toastText: '#fde68a',
};

interface ThemeState {
  mode: ThemeMode;
  dark: boolean;
  colors: Colors;
  setMode: (m: ThemeMode) => void;
}

const ThemeCtx = createContext<ThemeState>({
  mode: 'system',
  dark: false,
  colors: LIGHT,
  setMode: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>('system');

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (saved === 'light' || saved === 'dark' || saved === 'system') {
        setModeState(saved);
      }
    }).catch(() => {});
  }, []);

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    AsyncStorage.setItem(STORAGE_KEY, m).catch(() => {});
  }, []);

  const dark = mode === 'dark' || (mode === 'system' && systemScheme === 'dark');
  const colors = dark ? DARK : LIGHT;

  return (
    <ThemeCtx.Provider value={{ mode, dark, colors, setMode }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export const useTheme = () => useContext(ThemeCtx);
