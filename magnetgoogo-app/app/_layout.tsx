import { Buffer } from 'buffer';
(globalThis as any).Buffer = (globalThis as any).Buffer || Buffer;

import { useEffect, useState } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SourceProvider } from '../src/core/SourceContext';
import { LangProvider } from '../src/core/LangContext';
import { ThemeProvider, useTheme } from '../src/core/ThemeContext';
import { checkConfig, type ConfigCheckResult } from '../src/core/configChecker';
import ForceUpdateModal from '../src/components/ForceUpdateModal';
import { installCrashReporter } from '../src/core/crashReporter';

// Install global crash handler as early as possible
installCrashReporter();

export default function RootLayout() {
  const [configResult, setConfigResult] = useState<ConfigCheckResult | null>(null);

  useEffect(() => {
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

function ThemedApp({ configResult }: { configResult: ConfigCheckResult | null }) {
  const { colors } = useTheme();
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
      {configResult?.forceUpdate && (
        <ForceUpdateModal result={configResult} visible={true} />
      )}
    </>
  );
}
