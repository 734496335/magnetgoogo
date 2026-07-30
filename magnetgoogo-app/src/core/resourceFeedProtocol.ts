export type MediaKind = 'movie' | 'series';
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
  season_number: number | null;
  episode_start: number | null;
  episode_end: number | null;
  episode_label: string | null;
  title_source: string | null;
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
  source_id: string;
  source_item_key: string;
  detail_url: string;
  listing_title: string;
  content_kind: MediaKind;
  series_title: string | null;
  season_number: number | null;
  episode_number: number | null;
  episode_label: string | null;
  update_status: string | null;
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
  imdb_rating: number | null;
  imdb_rating_text: string | null;
  douban_rating: number | null;
  douban_rating_text: string | null;
  douban_url: string | null;
  rotten_tomatoes_rating: number | null;
  rotten_tomatoes_rating_text: string | null;
  rotten_tomatoes_url: string | null;
  bangumi_rating: number | null;
  bangumi_rating_text: string | null;
  bangumi_subject_id: string | null;
  bangumi_url: string | null;
  cover_source_url: string | null;
  cover_asset_path: string | null;
  cover_width: number | null;
  cover_height: number | null;
  synopsis: string | null;
  recommended: boolean;
  highlight_labels: string[];
  quality_tags: string[];
  resources: MovieResource[];
  resource_count_hint?: number;
  remote_cover_url?: string | null;
  remote_endpoint?: string;
  remote_release_id?: string;
  remote_detail_path?: string;
  remote_detail_hash?: string;
  remote_detail_size?: number;
}

export interface MovieFeed {
  schema_version: 'movie-app-feed/1' | 'media-app-feed/1';
  source_id: string;
  content_kind: MediaKind;
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

function nullableInteger(
  record: Record<string, unknown>,
  key: string,
  context: string,
  minimum = 0,
): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new ResourceFeedValidationError(
      'INVALID_NULLABLE_INTEGER',
      `${context}.${key} must be an integer >= ${minimum} or null`,
    );
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
    season_number: nullableInteger(value, 'season_number', context, 1),
    episode_start: nullableInteger(value, 'episode_start', context, 1),
    episode_end: nullableInteger(value, 'episode_end', context, 1),
    episode_label: nullableString(value, 'episode_label', context),
    title_source: nullableString(value, 'title_source', context),
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

function parseItem(
  value: unknown,
  index: number,
  expectedKind: MediaKind,
  requireOfflineCover: boolean,
): MovieFeedItem {
  const context = `items[${index}]`;
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_ITEM', `${context} must be an object`);
  }
  if ('content_code' in value || 'adult' in value || 'people' in value) {
    throw new ResourceFeedValidationError('LEGACY_ADULT_FIELD', `${context} contains a legacy adult-feed field`);
  }
  const itemKind = nullableString(value, 'content_kind', context) ?? expectedKind;
  if (itemKind !== expectedKind) {
    throw new ResourceFeedValidationError('CONTENT_KIND_MISMATCH', `${context}.content_kind must be ${expectedKind}`);
  }
  const resourcesValue = value.resources;
  if (!Array.isArray(resourcesValue)) {
    throw new ResourceFeedValidationError('INVALID_RESOURCES', `${context}.resources must be an array`);
  }
  const coverAssetPath = nullableString(value, 'cover_asset_path', context);
  if (requireOfflineCover && !coverAssetPath) {
    throw new ResourceFeedValidationError('OFFLINE_COVER_REQUIRED', `${context}.cover_asset_path is required`);
  }
  return {
    rank: integer(value, 'rank', context, 1),
    movie_id: requiredString(value, 'movie_id', context),
    source_id: requiredString(value, 'source_id', context),
    source_item_key: requiredString(value, 'source_item_key', context),
    detail_url: requiredString(value, 'detail_url', context),
    listing_title: requiredString(value, 'listing_title', context),
    content_kind: expectedKind,
    series_title: nullableString(value, 'series_title', context),
    season_number: nullableInteger(value, 'season_number', context, 1),
    episode_number: nullableInteger(value, 'episode_number', context, 0),
    episode_label: nullableString(value, 'episode_label', context),
    update_status: nullableString(value, 'update_status', context),
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
    imdb_rating: nullableNumber(value, 'imdb_rating', context),
    imdb_rating_text: nullableString(value, 'imdb_rating_text', context),
    douban_rating: nullableNumber(value, 'douban_rating', context),
    douban_rating_text: nullableString(value, 'douban_rating_text', context),
    douban_url: nullableString(value, 'douban_url', context),
    rotten_tomatoes_rating: nullableNumber(value, 'rotten_tomatoes_rating', context),
    rotten_tomatoes_rating_text: nullableString(value, 'rotten_tomatoes_rating_text', context),
    rotten_tomatoes_url: nullableString(value, 'rotten_tomatoes_url', context),
    bangumi_rating: nullableNumber(value, 'bangumi_rating', context),
    bangumi_rating_text: nullableString(value, 'bangumi_rating_text', context),
    bangumi_subject_id: nullableString(value, 'bangumi_subject_id', context),
    bangumi_url: nullableString(value, 'bangumi_url', context),
    cover_source_url: nullableString(value, 'cover_source_url', context),
    cover_asset_path: coverAssetPath,
    cover_width: nullableInteger(value, 'cover_width', context, 1),
    cover_height: nullableInteger(value, 'cover_height', context, 1),
    synopsis: nullableString(value, 'synopsis', context),
    recommended: boolean(value, 'recommended', context),
    highlight_labels: stringArray(value.highlight_labels, `${context}.highlight_labels`),
    quality_tags: stringArray(value.quality_tags, `${context}.quality_tags`),
    resources: resourcesValue.map((resource, resourceIndex) => parseResource(resource, `${context}.resources[${resourceIndex}]`)),
  };
}

export function parseResourceFeed(value: unknown): MovieFeed {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_ROOT', 'media feed must be an object');
  }
  const schemaVersion = value.schema_version;
  const isMovieFeed = schemaVersion === 'movie-app-feed/1';
  const isMediaFeed = schemaVersion === 'media-app-feed/1';
  if (!isMovieFeed && !isMediaFeed) {
    throw new ResourceFeedValidationError('INVALID_FEED_IDENTITY', 'media feed schema mismatch');
  }
  const contentKindValue = isMovieFeed ? 'movie' : requiredString(value, 'content_kind', 'feed');
  if (contentKindValue !== 'movie' && contentKindValue !== 'series') {
    throw new ResourceFeedValidationError('INVALID_CONTENT_KIND', 'feed.content_kind is unsupported');
  }
  const contentKind: MediaKind = contentKindValue;
  const sourceId = requiredString(value, 'source_id', 'feed');
  if (isMovieFeed && sourceId !== 'sixv') {
    throw new ResourceFeedValidationError('INVALID_FEED_IDENTITY', 'legacy movie feed source mismatch');
  }
  if (!Array.isArray(value.items)) {
    throw new ResourceFeedValidationError('INVALID_ITEMS', 'items must be an array');
  }
  const summary = parseSummary(value.summary);
  const requireOfflineCover = summary.offline_ready && value.items.length > 0;
  const items = value.items.map((item, index) => parseItem(item, index, contentKind, requireOfflineCover));
  if (summary.record_count !== items.length) {
    throw new ResourceFeedValidationError('COUNT_MISMATCH', 'feed record count does not match items');
  }
  if (requireOfflineCover && summary.cover_count !== items.length) {
    throw new ResourceFeedValidationError('COUNT_MISMATCH', 'offline cover count does not match items');
  }
  if (!requireOfflineCover && summary.cover_count > items.length) {
    throw new ResourceFeedValidationError('COUNT_MISMATCH', 'cover count exceeds items');
  }
  items.forEach((item, index) => {
    if (item.rank !== index + 1) {
      throw new ResourceFeedValidationError('RANK_NOT_CONTINUOUS', `items[${index}].rank is not continuous`);
    }
  });
  const recommendedCount = items.filter((item) => item.recommended).length;
  const resourceCount = items.reduce((sum, item) => sum + item.resources.length, 0);
  if (summary.recommended_count !== recommendedCount || summary.resource_count !== resourceCount) {
    throw new ResourceFeedValidationError('SUMMARY_MISMATCH', 'media feed summary does not match item contents');
  }
  if (!summary.offline_ready) {
    throw new ResourceFeedValidationError('OFFLINE_ASSETS_REQUIRED', 'media feed must be bundled for offline use');
  }
  return {
    schema_version: isMovieFeed ? 'movie-app-feed/1' : 'media-app-feed/1',
    source_id: sourceId,
    content_kind: contentKind,
    generated_at: requiredString(value, 'generated_at', 'feed'),
    snapshot_captured_at: nullableString(value, 'snapshot_captured_at', 'feed'),
    items,
    summary,
  };
}

export function resourceFeedItemKey(item: MovieFeedItem): string {
  return `${item.content_kind}:${item.movie_id}`;
}

export function findMovieById(feed: MovieFeed, movieId: string): MovieFeedItem | null {
  return feed.items.find((item) => item.movie_id === movieId) ?? null;
}
