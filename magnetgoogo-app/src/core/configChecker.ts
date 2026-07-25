/**
 * Remote config checker — fetches config.json from CDN to enforce:
 *   1. Forced app update (min_version gate)
 *   2. Optional update prompt (latest_version)
 *   3. Announcements
 *
 * Config is fetched on app start, result drives UI in _layout.tsx.
 */

import Constants from 'expo-constants';
import { compareSemver, isRemoteConfig, type ValidRemoteConfig } from './configValidation';

// Endpoints raced in parallel — first valid response wins.
const CN_ALI = 'https://cn.magnetgoogo.com';
const CF_PAGES = 'https://magnetgoogo.com';
const CDN_BASE = 'https://cdn.jsdelivr.net/gh/734496335/mg-data@main';
const RAW_BASE = 'https://raw.githubusercontent.com/734496335/mg-data/main';
const GATEWAY_BASE = 'https://api.naoshiquan.com';
const GATEWAY_OLD = 'https://maggoogo-gateway.734496335lp.workers.dev';

/** Fetch with timeout (default 6s — short because we race). */
function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 6000): Promise<Response> {
  return new Promise((resolve, reject) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => { ctrl.abort(); reject(new Error('timeout')); }, timeoutMs);
    fetch(url, { ...options, signal: ctrl.signal })
      .then(r => { clearTimeout(timer); resolve(r); })
      .catch(e => { clearTimeout(timer); reject(e); });
  });
}

export interface RemoteConfig extends ValidRemoteConfig {}

export interface ConfigCheckResult {
  config: RemoteConfig | null;
  forceUpdate: boolean;
  updateAvailable: boolean;
  announcement: string;
  downloadUrl: string;
  mirrors: string[];
  error: string | null;
}

/** Get the current app version from app.json / Constants. */
export function getAppVersion(): string {
  return Constants.expoConfig?.version || '0.1.0';
}

/** Fetch config.json and check version constraints. Race all endpoints. */
export async function checkConfig(): Promise<ConfigCheckResult> {
  const appVersion = getAppVersion();

  // Race all endpoints in parallel
  const urls = [
    `${CN_ALI}/config.json`,
    `${CF_PAGES}/config.json`,
    `${CDN_BASE}/config.json`,
    `${RAW_BASE}/config.json`,
    `${GATEWAY_BASE}/config.json`,
    `${GATEWAY_OLD}/config.json`,
  ];

  const headers = {
    'Cache-Control': 'no-cache',
    'X-App-Version': appVersion,
  };

  let config: RemoteConfig | null = null;
  let error: string | null = null;

  try {
    const result = await Promise.any(
      urls.map(async (url) => {
        const resp = await fetchWithTimeout(url, { headers });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (!isRemoteConfig(data)) throw new Error('invalid_config');
        console.log(`[ConfigChecker] ✓ Loaded config from ${url}`);
        return data;
      }),
    );
    config = result;
  } catch (e: any) {
    error = e.message || String(e);
    console.log(`[ConfigChecker] All endpoints failed: ${error}`);
  }

  if (!config) {
    return {
      config: null,
      forceUpdate: false,
      updateAvailable: false,
      announcement: '',
      downloadUrl: '',
      mirrors: [],
      error: error || 'Config not found',
    };
  }

  const forceUpdate = compareSemver(appVersion, config.min_version) < 0;
  const updateAvailable = compareSemver(appVersion, config.latest_version) < 0;

  return {
    config,
    forceUpdate,
    updateAvailable,
    announcement: config.announcement || '',
    downloadUrl: config.download?.primary || '',
    mirrors: config.download?.mirrors || [],
    error: null,
  };
}
