import { File, Paths } from 'expo-file-system';
import {
  findMovieById,
  parseResourceFeed,
  type MovieFeed,
  type MovieFeedItem,
} from './resourceFeedProtocol';

const BUNDLE_ROOT = ['resource-index', 'sixv'] as const;
const BUNDLED_FEED_PATH = [...BUNDLE_ROOT, 'feed.json'] as const;

export type ResourceFeedOrigin = 'bundled';

export interface LoadedResourceFeed {
  feed: MovieFeed;
  origin: ResourceFeedOrigin;
}

let memoryCache: LoadedResourceFeed | null = null;

function safeAssetParts(relativePath: string): string[] {
  const parts = relativePath.split('/').filter(Boolean);
  if (!parts.length || parts.some((part) => part === '.' || part === '..' || part.includes('\\'))) {
    throw new Error('INVALID_MOVIE_ASSET_PATH');
  }
  return parts;
}

function logResourceFeedFailure(stage: string, errorCode: string, error: unknown) {
  console.warn('[ResourceFeed]', {
    stage,
    error_code: errorCode,
    error: error instanceof Error ? error.message : String(error),
  });
}

async function loadBundled(): Promise<LoadedResourceFeed> {
  const file = new File(Paths.bundle, ...BUNDLED_FEED_PATH);
  if (!file.exists) {
    throw new Error(`BUNDLED_MOVIE_FEED_MISSING:${file.uri}`);
  }
  let json: unknown;
  try {
    json = JSON.parse(await file.text());
  } catch (error) {
    logResourceFeedFailure('bundled_parse', 'INVALID_MOVIE_FEED_JSON', error);
    throw error;
  }
  return { feed: parseResourceFeed(json), origin: 'bundled' };
}

export async function loadResourceFeed(forceRefresh = false): Promise<LoadedResourceFeed> {
  if (!forceRefresh && memoryCache) return memoryCache;
  try {
    memoryCache = await loadBundled();
    return memoryCache;
  } catch (error) {
    logResourceFeedFailure('bundled_load', 'BUNDLED_MOVIE_FEED_FAILED', error);
    if (memoryCache) return memoryCache;
    throw new Error('MOVIE_FEED_UNAVAILABLE');
  }
}

export async function loadMovieById(movieId: string): Promise<MovieFeedItem | null> {
  const { feed } = await loadResourceFeed(false);
  return findMovieById(feed, movieId);
}

export function movieCoverUri(item: MovieFeedItem): string {
  return new File(Paths.bundle, ...BUNDLE_ROOT, ...safeAssetParts(item.cover_asset_path)).uri;
}

export function clearResourceFeedMemoryCache() {
  memoryCache = null;
}
