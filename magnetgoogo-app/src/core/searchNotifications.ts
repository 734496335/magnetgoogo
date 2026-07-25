import { AppState, Platform, type AppStateStatus } from 'react-native';
import * as Notifications from 'expo-notifications';

const SEARCH_CHANNEL_ID = 'search-complete';

let _initialized = false;
let _appState: AppStateStatus = AppState.currentState;

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export function isAppForeground(): boolean {
  return _appState === 'active';
}

export async function initSearchNotifications(): Promise<void> {
  if (_initialized) return;
  _initialized = true;

  _appState = AppState.currentState;
  AppState.addEventListener('change', (next) => {
    _appState = next;
  });

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync(SEARCH_CHANNEL_ID, {
      name: 'Search completion',
      description: 'MagGoogo search completion notifications',
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 180, 120, 180],
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
    });
  }

  // Request permissions in foreground during initialization
  await ensureSearchNotificationPermission().catch(() => {});
}

export async function ensureSearchNotificationPermission(): Promise<boolean> {
  if (Platform.OS !== 'android' && Platform.OS !== 'ios') return false;
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  const requested = await Notifications.requestPermissionsAsync();
  return requested.granted;
}

export async function notifySearchCompleted(params: {
  query: string;
  resultCount: number;
  sourceCount: number;
  elapsedMs: number;
}): Promise<void> {
  if (isAppForeground()) return;

  const granted = await ensureSearchNotificationPermission().catch(() => false);
  if (!granted) return;

  const seconds = Math.max(1, Math.round(params.elapsedMs / 1000));
  await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Search complete',
      body: `"${params.query}" found ${params.resultCount} results in ${seconds}s`,
      data: {
        type: 'search_complete',
        query: params.query,
        resultCount: params.resultCount,
        sourceCount: params.sourceCount,
      },
      sound: true,
      priority: Notifications.AndroidNotificationPriority.DEFAULT,
    },
    trigger: null,
    ...(Platform.OS === 'android' ? { identifier: undefined } : {}),
  });
}
