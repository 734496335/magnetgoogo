import { File, Paths } from 'expo-file-system';
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

export type ResourceFeedOrigin = 'bundled';

export interface LoadedResourceFeed {
  feed: MovieFeed;
  origin: ResourceFeedOrigin;
}

const memoryCache: Partial<Record<MediaKind, LoadedResourceFeed>> = {};

function safeAssetParts(relativePath: string): string[] {
  const parts = relativePath.split('/').filter(Boolean);
  if (!parts.length || parts.some((part) => part === '.' || part === '..' || part.includes('\\'))) {
    throw new Error('INVALID_MEDIA_ASSET_PATH');
  }
  return parts;
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

export async function loadResourceFeed(
  kind: MediaKind = 'movie',
  forceRefresh = false,
): Promise<LoadedResourceFeed> {
  if (!forceRefresh && memoryCache[kind]) return memoryCache[kind] as LoadedResourceFeed;
  try {
    const loaded = await loadBundled(kind);
    memoryCache[kind] = loaded;
    return loaded;
  } catch (error) {
    logResourceFeedFailure(kind, 'bundled_load', 'BUNDLED_MEDIA_FEED_FAILED', error);
    if (memoryCache[kind]) return memoryCache[kind] as LoadedResourceFeed;
    throw new Error(`${kind.toUpperCase()}_FEED_UNAVAILABLE`);
  }
}

export async function loadMediaById(
  kind: MediaKind,
  mediaId: string,
): Promise<MovieFeedItem | null> {
  const { feed } = await loadResourceFeed(kind, false);
  return findMovieById(feed, mediaId);
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
  if (!item.cover_asset_path) return null;
  return new File(
    Paths.bundle,
    ...BUNDLE_ROOTS[item.content_kind],
    ...safeAssetParts(item.cover_asset_path),
  ).uri;
}

export function clearResourceFeedMemoryCache(kind?: MediaKind) {
  if (kind) {
    delete memoryCache[kind];
    return;
  }
  delete memoryCache.movie;
  delete memoryCache.series;
}
