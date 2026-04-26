/**
 * Remote config checker — fetches config.json from CDN to enforce:
 *   1. Forced app update (min_version gate)
 *   2. Optional update prompt (latest_version)
 *   3. Announcements
 *
 * Config is fetched on app start, result drives UI in _layout.tsx.
 */

import Constants from 'expo-constants';

// Primary: CF Worker gateway (handles version/membership logic)
// Fallback: jsDelivr CDN (static, no logic, but fast in China)
const GATEWAY_BASE = 'https://maggoogo-gateway.734496335lp.workers.dev';
const CDN_BASE = 'https://cdn.jsdelivr.net/gh/734496335/maggoogo-sources@main';

export interface RemoteConfig {
  latest_version: string;
  min_version: string;
  download: {
    primary: string;
    mirrors: string[];
  };
  announcement: string;
  source_expiry_hours: number;
  source_schema_version: number;
  updated_at: string;
}

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

/** Compare semver strings. Returns -1, 0, or 1. */
function compareSemver(a: string, b: string): number {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    const na = pa[i] || 0;
    const nb = pb[i] || 0;
    if (na < nb) return -1;
    if (na > nb) return 1;
  }
  return 0;
}

/** Fetch config.json and check version constraints. */
export async function checkConfig(): Promise<ConfigCheckResult> {
  const appVersion = getAppVersion();

  // Try gateway first (has logic), then static CDN fallback
  const urls = [`${GATEWAY_BASE}/config.json`, `${CDN_BASE}/config.json`];
  let config: RemoteConfig | null = null;
  let error: string | null = null;

  for (const url of urls) {
    try {
      const resp = await fetch(url, {
        headers: {
          'Cache-Control': 'no-cache',
          'X-App-Version': appVersion,
        },
      });
      if (resp.ok) {
        config = await resp.json();
        console.log(`[ConfigChecker] Loaded config from ${url}`);
        break;
      }
    } catch (e: any) {
      error = e.message || String(e);
      console.log(`[ConfigChecker] Failed ${url}: ${error}`);
    }
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
