import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { NativeModules, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Lang, ALL_LANGS, Translations, getTranslations } from './i18n';

const STORAGE_KEY = 'mg_lang';

/** Detect device language, match to supported langs. */
function detectDeviceLang(): Lang {
  try {
    let locale = '';
    if (Platform.OS === 'ios') {
      locale =
        NativeModules.SettingsManager?.settings?.AppleLocale ||
        NativeModules.SettingsManager?.settings?.AppleLanguages?.[0] ||
        '';
    } else {
      locale = NativeModules.I18nManager?.localeIdentifier || '';
    }
    const prefix = locale.toLowerCase().replace(/_/g, '-').split('-')[0];
    const match = ALL_LANGS.find((l) => l === prefix);
    if (match) return match;
    if (prefix === 'zh') return 'zh';
    return 'en';
  } catch {
    return 'en';
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
          setLangState(saved);
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

  return (
    <LangCtx.Provider value={{ lang, t, setLang }}>
      {children}
    </LangCtx.Provider>
  );
}

export const useLang = () => useContext(LangCtx);
