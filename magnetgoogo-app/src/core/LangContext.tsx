import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { NativeModules, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Lang, ALL_LANGS, Translations, getTranslations } from './i18n';

const STORAGE_KEY = 'mg_lang';

/** Detect device language, match to supported langs. */
function detectDeviceLang(): Lang {
  try {
    let locale = '';
    // Method 1: NativeModules (most reliable on older RN)
    try {
      locale = NativeModules.I18nManager?.localeIdentifier || '';
    } catch {}
    // Method 2: I18nManager constants
    if (!locale) {
      try {
        const RN = require('react-native');
        locale = RN.I18nManager?.localeIdentifier || '';
      } catch {}
    }
    // Method 3: Platform constants
    if (!locale && Platform.OS === 'android') {
      try {
        locale = NativeModules.PlatformConstants?.getConstants()?.localeIdentifier || '';
      } catch {}
    }

    if (!locale) return 'zh'; // Default to Chinese

    const prefix = locale.toLowerCase().replace(/_/g, '-').split('-')[0];
    const match = ALL_LANGS.find((l) => l === prefix);
    if (match) return match;
    if (prefix === 'zh') return 'zh';
    return 'en';
  } catch {
    return 'zh'; // Default to Chinese on error
  }
}

interface LangState {
  lang: Lang;
  t: Translations;
  setLang: (l: Lang) => void;
}

const LangCtx = createContext<LangState>({
  lang: 'zh',
  t: getTranslations('zh'),
  setLang: () => {},
});

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>('zh');

  useEffect(() => {
    (async () => {
      try {
        const saved = await AsyncStorage.getItem(STORAGE_KEY);
        if (ALL_LANGS.includes(saved as Lang)) {
          setLangState(saved as Lang);
        } else {
          setLangState(detectDeviceLang());
        }
      } catch {
        setLangState(detectDeviceLang());
      }
    })();
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    AsyncStorage.setItem(STORAGE_KEY, l).catch(() => {});
  }, []);

  const t = getTranslations(lang);
  const value = useMemo(() => ({ lang, t, setLang }), [lang, t, setLang]);

  return (
    <LangCtx.Provider value={value}>
      {children}
    </LangCtx.Provider>
  );
}

export const useLang = () => useContext(LangCtx);
