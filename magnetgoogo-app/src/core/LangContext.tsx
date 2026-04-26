import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { NativeModules, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Lang, Translations, getTranslations } from './i18n';

const STORAGE_KEY = 'mg_lang';

/** Detect device language, default to 'zh'. */
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
    if (locale.toLowerCase().startsWith('en')) return 'en';
    return 'zh';
  } catch {
    return 'zh';
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
        if (saved === 'zh' || saved === 'en') {
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
