import * as Application from 'expo-application';
import { File, Paths } from 'expo-file-system';
import { cachedMediaFeed, clearMediaCacheMemory } from './mediaReleaseCache';
import {
  clearActiveMediaRelease,
  loadRemoteMediaDetail,
  syncMediaFeed,
} from './mediaReleaseClient';
import {
  findMovieById,
  parseResourceFeed,
  type MediaKind,
  type MovieFeed,
  type MovieFeedItem,
} from './resourceFeedProtocol';

const BUNDLE_ROOTS: Record<MediaKind, readonly string[]> = {
  movie: ['resource-index', 'sixv'],
  series: ['resource-index', 'series'],
};

export type ResourceFeedOrigin = 'bundled' | 'disk-cache' | 'network';

export interface LoadedResourceFeed {
  feed: MovieFeed;
  origin: ResourceFeedOrigin;
}

export interface ResourceFeedLoadResult extends LoadedResourceFeed {
  /** True only when this loadResourceFeed call completed a live network refresh. */
  refreshSucceeded: boolean;
  refreshErrorCode?: string;
}

const memoryCache: Partial<Record<MediaKind, LoadedResourceFeed>> = {};
const networkSyncs: Partial<Record<MediaKind, Promise<LoadedResourceFeed>>> = {};

function safeAssetParts(relativePath: string): string[] {
  const parts = relativePath.split('/').filter(Boolean);
  if (!parts.length || parts.some((part) => part === '.' || part === '..' || part.includes('\\'))) {
    throw new Error('INVALID_MEDIA_ASSET_PATH');
  }
  return parts;
}

function logResourceFeedSuccess(
  kind: MediaKind,
  stage: string,
  origin: ResourceFeedOrigin,
  recordCount: number,
) {
  if (!Application.applicationId?.endsWith('.debug')) return;
  console.log('[MediaReleaseEvidence]', {
    stage,
    error_code: 'OK',
    content_kind: kind,
    origin,
    record_count: recordCount,
  });
}

function logResourceFeedFailure(
  kind: MediaKind,
  stage: string,
  errorCode: string,
  error: unknown,
) {
  console.warn('[ResourceFeed]', {
    stage,
    error_code: errorCode,
    content_kind: kind,
    error: error instanceof Error ? error.message : String(error),
  });
}

async function loadBundled(kind: MediaKind): Promise<LoadedResourceFeed> {
  const root = BUNDLE_ROOTS[kind];
  const file = new File(Paths.bundle, ...root, 'feed.json');
  if (!file.exists) {
    throw new Error(`BUNDLED_MEDIA_FEED_MISSING:${kind}:${file.uri}`);
  }
  let json: unknown;
  try {
    json = JSON.parse(await file.text());
  } catch (error) {
    logResourceFeedFailure(kind, 'bundled_parse', 'INVALID_MEDIA_FEED_JSON', error);
    throw error;
  }
  const feed = parseResourceFeed(json);
  if (feed.content_kind !== kind) {
    throw new Error(`BUNDLED_MEDIA_KIND_MISMATCH:${kind}:${feed.content_kind}`);
  }
  return { feed, origin: 'bundled' };
}

async function loadCached(kind: MediaKind): Promise<LoadedResourceFeed | null> {
  try {
    const feed = await cachedMediaFeed(kind);
    if (!feed || feed.content_kind !== kind) return null;
    return { feed, origin: 'disk-cache' };
  } catch (error) {
    logResourceFeedFailure(kind, 'disk_cache_load', 'MEDIA_DISK_CACHE_FAILED', error);
    return null;
  }
}

export async function syncResourceFeed(kind: MediaKind): Promise<LoadedResourceFeed> {
  if (networkSyncs[kind]) return networkSyncs[kind] as Promise<LoadedResourceFeed>;
  const task = syncMediaFeed(kind)
    .then((feed): LoadedResourceFeed => {
      const loaded: LoadedResourceFeed = { feed, origin: 'network' };
      memoryCache[kind] = loaded;
      logResourceFeedSuccess(kind, 'network_feed_ready', loaded.origin, feed.items.length);
      return loaded;
    })
    .catch((error) => {
      logResourceFeedFailure(kind, 'network_sync', 'MEDIA_NETWORK_SYNC_FAILED', error);
      throw error;
    })
    .finally(() => {
      if (networkSyncs[kind] === task) delete networkSyncs[kind];
    });
  networkSyncs[kind] = task;
  return task;
}

export async function loadResourceFeed(
  kind: MediaKind = 'movie',
  forceRefresh = false,
): Promise<ResourceFeedLoadResult> {
  if (forceRefresh) {
    try {
      const loaded = await syncResourceFeed(kind);
      return { ...loaded, refreshSucceeded: true };
    } catch (error) {
      logResourceFeedFailure(kind, 'force_refresh', 'MEDIA_FORCE_REFRESH_FAILED', error);
      if (memoryCache[kind]) {
        return {
          ...(memoryCache[kind] as LoadedResourceFeed),
          refreshSucceeded: false,
          refreshErrorCode: 'MEDIA_FORCE_REFRESH_FAILED',
        };
      }
      const cached = await loadCached(kind);
      if (cached) {
        memoryCache[kind] = cached;
        return { ...cached, refreshSucceeded: false, refreshErrorCode: 'MEDIA_FORCE_REFRESH_FAILED' };
      }
      const bundled = await loadBundled(kind);
      return { ...bundled, refreshSucceeded: false, refreshErrorCode: 'MEDIA_FORCE_REFRESH_FAILED' };
    }
  }
  if (memoryCache[kind]) {
    const loaded = memoryCache[kind] as LoadedResourceFeed;
    logResourceFeedSuccess(kind, 'memory_feed_ready', loaded.origin, loaded.feed.items.length);
    return { ...loaded, refreshSucceeded: false };
  }
  const cached = await loadCached(kind);
  if (cached) {
    memoryCache[kind] = cached;
    logResourceFeedSuccess(kind, 'disk_feed_ready', cached.origin, cached.feed.items.length);
    return { ...cached, refreshSucceeded: false };
  }
  try {
    const loaded = await loadBundled(kind);
    memoryCache[kind] = loaded;
    logResourceFeedSuccess(kind, 'bundled_feed_ready', loaded.origin, loaded.feed.items.length);
    return { ...loaded, refreshSucceeded: false };
  } catch (error) {
    logResourceFeedFailure(kind, 'bundled_load', 'BUNDLED_MEDIA_FEED_FAILED', error);
    if (memoryCache[kind]) {
      return { ...(memoryCache[kind] as LoadedResourceFeed), refreshSucceeded: false };
    }
    throw new Error(`${kind.toUpperCase()}_FEED_UNAVAILABLE`);
  }
}

export async function loadMediaCardById(
  kind: MediaKind,
  mediaId: string,
): Promise<MovieFeedItem | null> {
  const { feed } = await loadResourceFeed(kind, false);
  return findMovieById(feed, mediaId);
}

export async function loadMediaCardByIdAcrossFeeds(mediaId: string): Promise<MovieFeedItem | null> {
  const movie = await loadMediaCardById('movie', mediaId);
  if (movie) return movie;
  return loadMediaCardById('series', mediaId);
}

export async function hydrateMediaItem(item: MovieFeedItem): Promise<MovieFeedItem> {
  if (!item.remote_release_id || !item.remote_detail_path) return item;
  return loadRemoteMediaDetail(item);
}

export async function loadMediaById(
  kind: MediaKind,
  mediaId: string,
): Promise<MovieFeedItem | null> {
  const item = await loadMediaCardById(kind, mediaId);
  if (!item) return null;
  try {
    return await hydrateMediaItem(item);
  } catch (error) {
    logResourceFeedFailure(kind, 'network_detail', 'MEDIA_NETWORK_DETAIL_FAILED', error);
    return item;
  }
}

export async function loadMovieById(movieId: string): Promise<MovieFeedItem | null> {
  return loadMediaById('movie', movieId);
}

export async function loadMediaByIdAcrossFeeds(mediaId: string): Promise<MovieFeedItem | null> {
  const movie = await loadMediaById('movie', mediaId);
  if (movie) return movie;
  return loadMediaById('series', mediaId);
}

export function movieCoverUri(item: MovieFeedItem): string | null {
  if (item.remote_cover_url) return item.remote_cover_url;
  if (item.cover_asset_path) {
    return new File(
      Paths.bundle,
      ...BUNDLE_ROOTS[item.content_kind],
      ...safeAssetParts(item.cover_asset_path),
    ).uri;
  }
  return item.cover_source_url;
}

export function clearResourceFeedMemoryCache(kind?: MediaKind) {
  if (kind) {
    delete memoryCache[kind];
    return;
  }
  delete memoryCache.movie;
  delete memoryCache.series;
  clearMediaCacheMemory();
  clearActiveMediaRelease();
}
