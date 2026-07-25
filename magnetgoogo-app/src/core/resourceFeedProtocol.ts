export type MovieResourceType = 'magnet' | 'cloud';
export type MovieResourceProvider = 'magnet' | 'xunlei' | 'quark' | 'baidu' | string;

export interface MovieResource {
  resource_type: MovieResourceType;
  provider: MovieResourceProvider;
  url: string;
  info_hash: string | null;
  display_title: string;
  extraction_code: string | null;
  quality_tags: string[];
}

export interface MovieFeedSummary {
  record_count: number;
  target_count: number;
  recommended_count: number;
  resource_count: number;
  missing_urls: string[];
  snapshot_http_requests: number;
  detail_http_requests: number;
  database_movie_count: number;
  cover_count: number;
  offline_ready: boolean;
}

export interface MovieFeedItem {
  rank: number;
  movie_id: string;
  source_id: 'sixv';
  source_item_key: string;
  detail_url: string;
  listing_title: string;
  title: string;
  original_title: string | null;
  year: number | null;
  update_date: string | null;
  release_date: string | null;
  duration_minutes: number | null;
  countries: string[];
  genres: string[];
  languages: string[];
  directors: string[];
  actors: string[];
  imdb_id: string | null;
  douban_rating: number | null;
  douban_rating_text: string | null;
  douban_url: string | null;
  cover_source_url: string;
  cover_asset_path: string;
  cover_width: number;
  cover_height: number;
  synopsis: string | null;
  recommended: boolean;
  highlight_labels: string[];
  quality_tags: string[];
  resources: MovieResource[];
}

export interface MovieFeed {
  schema_version: 'movie-app-feed/1';
  source_id: 'sixv';
  generated_at: string;
  snapshot_captured_at: string | null;
  items: MovieFeedItem[];
  summary: MovieFeedSummary;
}

export class ResourceFeedValidationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'ResourceFeedValidationError';
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key];
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new ResourceFeedValidationError('INVALID_STRING', `${context}.${key} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(record: Record<string, unknown>, key: string, context: string): string | null {
  const value = record[key];
  if (value === null || value === undefined || value === '') return null;
  if (typeof value !== 'string') {
    throw new ResourceFeedValidationError('INVALID_NULLABLE_STRING', `${context}.${key} must be string or null`);
  }
  return value.trim() || null;
}

function integer(record: Record<string, unknown>, key: string, context: string, minimum = 0): number {
  const value = record[key];
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new ResourceFeedValidationError('INVALID_INTEGER', `${context}.${key} must be an integer >= ${minimum}`);
  }
  return value as number;
}

function nullableInteger(record: Record<string, unknown>, key: string, context: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new ResourceFeedValidationError('INVALID_NULLABLE_INTEGER', `${context}.${key} must be an integer or null`);
  }
  return value as number;
}

function nullableNumber(record: Record<string, unknown>, key: string, context: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ResourceFeedValidationError('INVALID_NULLABLE_NUMBER', `${context}.${key} must be a number or null`);
  }
  return value;
}

function boolean(record: Record<string, unknown>, key: string, context: string): boolean {
  const value = record[key];
  if (typeof value !== 'boolean') {
    throw new ResourceFeedValidationError('INVALID_BOOLEAN', `${context}.${key} must be boolean`);
  }
  return value;
}

function stringArray(value: unknown, context: string): string[] {
  if (!Array.isArray(value)) {
    throw new ResourceFeedValidationError('INVALID_STRING_ARRAY', `${context} must be an array`);
  }
  return value.map((entry, index) => {
    if (typeof entry !== 'string' || entry.trim().length === 0) {
      throw new ResourceFeedValidationError('INVALID_STRING_ARRAY_ITEM', `${context}[${index}] must be non-empty string`);
    }
    return entry.trim();
  });
}

function parseResource(value: unknown, context: string): MovieResource {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_RESOURCE', `${context} must be an object`);
  }
  const resourceType = requiredString(value, 'resource_type', context);
  if (resourceType !== 'magnet' && resourceType !== 'cloud') {
    throw new ResourceFeedValidationError('INVALID_RESOURCE_TYPE', `${context}.resource_type is unsupported`);
  }
  return {
    resource_type: resourceType,
    provider: requiredString(value, 'provider', context),
    url: requiredString(value, 'url', context),
    info_hash: nullableString(value, 'info_hash', context),
    display_title: requiredString(value, 'display_title', context),
    extraction_code: nullableString(value, 'extraction_code', context),
    quality_tags: stringArray(value.quality_tags, `${context}.quality_tags`),
  };
}

function parseSummary(value: unknown): MovieFeedSummary {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_SUMMARY', 'summary must be an object');
  }
  return {
    record_count: integer(value, 'record_count', 'summary'),
    target_count: integer(value, 'target_count', 'summary'),
    recommended_count: integer(value, 'recommended_count', 'summary'),
    resource_count: integer(value, 'resource_count', 'summary'),
    missing_urls: stringArray(value.missing_urls, 'summary.missing_urls'),
    snapshot_http_requests: integer(value, 'snapshot_http_requests', 'summary'),
    detail_http_requests: integer(value, 'detail_http_requests', 'summary'),
    database_movie_count: integer(value, 'database_movie_count', 'summary'),
    cover_count: integer(value, 'cover_count', 'summary'),
    offline_ready: boolean(value, 'offline_ready', 'summary'),
  };
}

function parseItem(value: unknown, index: number): MovieFeedItem {
  const context = `items[${index}]`;
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_ITEM', `${context} must be an object`);
  }
  if ('content_code' in value || 'adult' in value || 'people' in value) {
    throw new ResourceFeedValidationError('LEGACY_ADULT_FIELD', `${context} contains a legacy adult-feed field`);
  }
  const sourceId = requiredString(value, 'source_id', context);
  if (sourceId !== 'sixv') {
    throw new ResourceFeedValidationError('INVALID_SOURCE', `${context}.source_id must be sixv`);
  }
  const resourcesValue = value.resources;
  if (!Array.isArray(resourcesValue)) {
    throw new ResourceFeedValidationError('INVALID_RESOURCES', `${context}.resources must be an array`);
  }
  return {
    rank: integer(value, 'rank', context, 1),
    movie_id: requiredString(value, 'movie_id', context),
    source_id: 'sixv',
    source_item_key: requiredString(value, 'source_item_key', context),
    detail_url: requiredString(value, 'detail_url', context),
    listing_title: requiredString(value, 'listing_title', context),
    title: requiredString(value, 'title', context),
    original_title: nullableString(value, 'original_title', context),
    year: nullableInteger(value, 'year', context),
    update_date: nullableString(value, 'update_date', context),
    release_date: nullableString(value, 'release_date', context),
    duration_minutes: nullableInteger(value, 'duration_minutes', context),
    countries: stringArray(value.countries, `${context}.countries`),
    genres: stringArray(value.genres, `${context}.genres`),
    languages: stringArray(value.languages, `${context}.languages`),
    directors: stringArray(value.directors, `${context}.directors`),
    actors: stringArray(value.actors, `${context}.actors`),
    imdb_id: nullableString(value, 'imdb_id', context),
    douban_rating: nullableNumber(value, 'douban_rating', context),
    douban_rating_text: nullableString(value, 'douban_rating_text', context),
    douban_url: nullableString(value, 'douban_url', context),
    cover_source_url: requiredString(value, 'cover_source_url', context),
    cover_asset_path: requiredString(value, 'cover_asset_path', context),
    cover_width: integer(value, 'cover_width', context, 1),
    cover_height: integer(value, 'cover_height', context, 1),
    synopsis: nullableString(value, 'synopsis', context),
    recommended: boolean(value, 'recommended', context),
    highlight_labels: stringArray(value.highlight_labels, `${context}.highlight_labels`),
    quality_tags: stringArray(value.quality_tags, `${context}.quality_tags`),
    resources: resourcesValue.map((resource, resourceIndex) => parseResource(resource, `${context}.resources[${resourceIndex}]`)),
  };
}

export function parseResourceFeed(value: unknown): MovieFeed {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_ROOT', 'movie feed must be an object');
  }
  if (value.schema_version !== 'movie-app-feed/1' || value.source_id !== 'sixv') {
    throw new ResourceFeedValidationError('INVALID_FEED_IDENTITY', 'movie feed identity mismatch');
  }
  if (!Array.isArray(value.items)) {
    throw new ResourceFeedValidationError('INVALID_ITEMS', 'items must be an array');
  }
  const summary = parseSummary(value.summary);
  const items = value.items.map(parseItem);
  if (summary.record_count !== items.length || summary.cover_count !== items.length) {
    throw new ResourceFeedValidationError('COUNT_MISMATCH', 'movie or cover count does not match items');
  }
  items.forEach((item, index) => {
    if (item.rank !== index + 1) {
      throw new ResourceFeedValidationError('RANK_NOT_CONTINUOUS', `items[${index}].rank is not continuous`);
    }
  });
  const recommendedCount = items.filter((item) => item.recommended).length;
  const resourceCount = items.reduce((sum, item) => sum + item.resources.length, 0);
  if (summary.recommended_count !== recommendedCount || summary.resource_count !== resourceCount) {
    throw new ResourceFeedValidationError('SUMMARY_MISMATCH', 'movie feed summary does not match item contents');
  }
  if (!summary.offline_ready) {
    throw new ResourceFeedValidationError('OFFLINE_ASSETS_REQUIRED', 'movie feed must include offline covers');
  }
  return {
    schema_version: 'movie-app-feed/1',
    source_id: 'sixv',
    generated_at: requiredString(value, 'generated_at', 'feed'),
    snapshot_captured_at: nullableString(value, 'snapshot_captured_at', 'feed'),
    items,
    summary,
  };
}

export function resourceFeedItemKey(item: MovieFeedItem): string {
  return item.movie_id;
}

export function findMovieById(feed: MovieFeed, movieId: string): MovieFeedItem | null {
  return feed.items.find((item) => item.movie_id === movieId) ?? null;
}
