import { Buffer } from 'buffer';
(globalThis as any).Buffer = (globalThis as any).Buffer || Buffer;

import { useEffect, useState, useRef } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View, Text, Animated, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { SourceProvider, useSources } from '../src/core/SourceContext';
import { LangProvider } from '../src/core/LangContext';
import { ThemeProvider, useTheme } from '../src/core/ThemeContext';
import { checkConfig, type ConfigCheckResult } from '../src/core/configChecker';
import ForceUpdateModal from '../src/components/ForceUpdateModal';
import OptionalUpdateModal from '../src/components/OptionalUpdateModal';
import { installCrashReporter } from '../src/core/crashReporter';
import { loadPersistedCookies } from '../src/core/httpClient';
import { initAnalytics } from '../src/core/analytics';
import { loadReports } from '../src/core/searchDebugLogger';

// Install global crash handler as early as possible
installCrashReporter();

export default function RootLayout() {
  const [configResult, setConfigResult] = useState<ConfigCheckResult | null>(null);

  useEffect(() => {
    loadPersistedCookies();
    initAnalytics();
    loadReports();
    checkConfig().then((result) => {
      // Safety: if config says force update but appVersion >= min_version, ignore
      // (protects against stale CDN cache returning old min_version)
      if (result.forceUpdate && result.config) {
        const appVer = require('../src/core/configChecker').getAppVersion();
        console.log(`[Layout] forceUpdate=${result.forceUpdate}, appVer=${appVer}, min=${result.config.min_version}`);
      }
      setConfigResult(result);
    }).catch(() => {});
  }, []);

  return (
    <ThemeProvider>
      <LangProvider>
        <SourceProvider>
          <ThemedApp configResult={configResult} />
        </SourceProvider>
      </LangProvider>
    </ThemeProvider>
  );
}

/** Global toast that shows source sync status on any screen. */
function SyncToast() {
  const { syncToast } = useSources();
  const insets = useSafeAreaInsets();
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(-40)).current;
  const [display, setDisplay] = useState(false);

  useEffect(() => {
    if (syncToast) {
      setDisplay(true);
      Animated.parallel([
        Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
        Animated.spring(translateY, { toValue: 0, useNativeDriver: true, tension: 80, friction: 10 }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(opacity, { toValue: 0, duration: 250, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: -40, duration: 250, useNativeDriver: true }),
      ]).start(() => setDisplay(false));
    }
  }, [syncToast, opacity, translateY]);

  if (!display) return null;
  const isError = syncToast?.includes('失败') || syncToast?.includes('fail');
  return (
    <Animated.View
      style={[
        toastStyles.wrap,
        { top: insets.top + 8, opacity, transform: [{ translateY }] },
      ]}
      pointerEvents="none"
    >
      <View style={[toastStyles.pill, isError && toastStyles.pillError]}>
        <Text style={[toastStyles.text, isError && toastStyles.textError]}>{syncToast}</Text>
      </View>
    </Animated.View>
  );
}

const toastStyles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 24,
    right: 24,
    zIndex: 9999,
    alignItems: 'center',
  },
  pill: {
    backgroundColor: 'rgba(30,30,30,0.88)',
    borderRadius: 14,
    paddingVertical: 10,
    paddingHorizontal: 18,
  },
  pillError: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
  },
  text: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  textError: {
    color: '#DC2626',
  },
});

function ThemedApp({ configResult }: { configResult: ConfigCheckResult | null }) {
  const { colors } = useTheme();
  const [showOptionalUpdate, setShowOptionalUpdate] = useState(
    () => !!(configResult?.updateAvailable && !configResult?.forceUpdate),
  );

  useEffect(() => {
    if (configResult?.updateAvailable && !configResult?.forceUpdate) {
      setShowOptionalUpdate(true);
    }
  }, [configResult]);

  return (
    <>
      <StatusBar style={colors.statusBar} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.bg },
          animation: 'slide_from_right',
        }}
      />
      <SyncToast />
      {configResult?.forceUpdate && (
        <ForceUpdateModal result={configResult} visible={true} />
      )}
      {configResult && !configResult.forceUpdate && configResult.updateAvailable && (
        <OptionalUpdateModal
          result={configResult}
          visible={showOptionalUpdate}
          onDismiss={() => setShowOptionalUpdate(false)}
        />
      )}
    </>
  );
}
