/**
 * Lightweight crash reporter — captures JS errors and unhandled promise rejections.
 * Stores crash logs locally in AsyncStorage, exposes them for user-triggered reporting.
 * No third-party SDK required.
 */
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'mg_crash_logs';
const MAX_LOGS = 20;

export interface CrashLog {
  id: string;
  timestamp: string;
  message: string;
  stack?: string;
  platform: string;
  appVersion: string;
  isFatal: boolean;
}

const APP_VERSION = '1.0.0';

async function saveCrash(log: CrashLog): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    const logs: CrashLog[] = raw ? JSON.parse(raw) : [];
    logs.unshift(log);
    if (logs.length > MAX_LOGS) logs.length = MAX_LOGS;
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(logs));
  } catch {
    // Can't even save — nothing we can do
  }
}

function buildLog(error: Error | string, isFatal: boolean): CrashLog {
  const err = typeof error === 'string' ? new Error(error) : error;
  return {
    id: `crash_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    message: err.message || String(error),
    stack: err.stack?.slice(0, 2000),
    platform: `${Platform.OS} ${Platform.Version}`,
    appVersion: APP_VERSION,
    isFatal,
  };
}

/** Install global error handlers. Call once at app startup. */
export function installCrashReporter(): void {
  // JS errors
  const prevHandler = ErrorUtils.getGlobalHandler();
  ErrorUtils.setGlobalHandler((error: Error, isFatal?: boolean) => {
    const log = buildLog(error, !!isFatal);
    saveCrash(log);
    console.error('[CrashReporter]', log.message);
    // Call previous handler so RN still shows red screen in dev
    if (prevHandler) prevHandler(error, isFatal);
  });

  // Unhandled promise rejections
  const tracking = require('promise/setimmediate/rejection-tracking');
  tracking.enable({
    allRejections: true,
    onUnhandled: (_id: number, error: Error) => {
      const log = buildLog(error, false);
      saveCrash(log);
      console.warn('[CrashReporter] Unhandled promise rejection:', log.message);
    },
    onHandled: () => {},
  });
}

/** Get stored crash logs. */
export async function getCrashLogs(): Promise<CrashLog[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Clear stored crash logs. */
export async function clearCrashLogs(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}

/** Format crash logs into a text report for GitHub Issues. */
export function formatCrashReport(logs: CrashLog[]): string {
  if (logs.length === 0) return 'No crash logs recorded.';
  return logs
    .map(
      (l) =>
        `### ${l.isFatal ? '💥 FATAL' : '⚠️ Error'} — ${l.timestamp}\n` +
        `- **Message:** ${l.message}\n` +
        `- **Platform:** ${l.platform}\n` +
        `- **App:** v${l.appVersion}\n` +
        (l.stack ? `\`\`\`\n${l.stack}\n\`\`\`\n` : ''),
    )
    .join('\n---\n\n');
}
