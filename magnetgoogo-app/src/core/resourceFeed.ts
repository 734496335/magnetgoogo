import Constants from 'expo-constants';
import { File, Paths } from 'expo-file-system';
import { parseResourceFeed, type ResourceFeed } from './resourceFeedProtocol';

const BUNDLED_FEED_PATH = ['resource-index', 'javbus_latest_100_feed.json'] as const;
const REMOTE_TIMEOUT_MS = 6000;

export type ResourceFeedOrigin = 'remote' | 'bundled';

export interface LoadedResourceFeed {
  feed: ResourceFeed;
  origin: ResourceFeedOrigin;
}

let memoryCache: LoadedResourceFeed | null = null;

function configuredRemoteUrls(): string[] {
  const raw = Constants.expoConfig?.extra?.resourceFeedUrl;
  const values = Array.isArray(raw) ? raw : typeof raw === 'string' ? raw.split(',') : [];
  return values
    .map((value) => String(value).trim())
    .filter((value) => /^https:\/\//i.test(value));
}

function logResourceFeedFailure(stage: string, errorCode: string, error: unknown, extra?: Record<string, unknown>) {
  console.warn('[ResourceFeed]', {
    stage,
    error_code: errorCode,
    error: error instanceof Error ? error.message : String(error),
    ...extra,
  });
}

async function parseTextPayload(text: string, stage: string): Promise<ResourceFeed> {
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch (error) {
    logResourceFeedFailure(stage, 'INVALID_JSON', error);
    throw error;
  }
  return parseResourceFeed(json);
}

async function loadRemote(url: string): Promise<LoadedResourceFeed> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REMOTE_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`HTTP_${response.status}`);
    }
    const feed = await parseTextPayload(await response.text(), 'remote_parse');
    return { feed, origin: 'remote' };
  } finally {
    clearTimeout(timer);
  }
}

async function loadBundled(): Promise<LoadedResourceFeed> {
  const file = new File(Paths.bundle, ...BUNDLED_FEED_PATH);
  if (!file.exists) {
    throw new Error(`BUNDLED_FEED_MISSING:${file.uri}`);
  }
  const feed = await parseTextPayload(await file.text(), 'bundled_parse');
  return { feed, origin: 'bundled' };
}

export async function loadResourceFeed(forceRefresh = false): Promise<LoadedResourceFeed> {
  if (!forceRefresh && memoryCache) return memoryCache;

  const urls = configuredRemoteUrls();
  for (const url of urls) {
    try {
      const loaded = await loadRemote(url);
      memoryCache = loaded;
      return loaded;
    } catch (error) {
      logResourceFeedFailure('remote_load', 'REMOTE_FEED_FAILED', error, { url });
    }
  }

  try {
    const loaded = await loadBundled();
    memoryCache = loaded;
    return loaded;
  } catch (error) {
    logResourceFeedFailure('bundled_load', 'BUNDLED_FEED_FAILED', error, {
      configured_remote_count: urls.length,
    });
    if (memoryCache) return memoryCache;
    throw new Error('RESOURCE_FEED_UNAVAILABLE');
  }
}

export function clearResourceFeedMemoryCache() {
  memoryCache = null;
}
