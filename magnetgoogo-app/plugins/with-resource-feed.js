const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const ASSET_ROOT = path.join('android', 'app', 'src', 'main', 'assets', 'resource-index');
const MOVIE_TARGET_RELATIVE = path.join(ASSET_ROOT, 'sixv');
const SERIES_TARGET_RELATIVE = path.join(ASSET_ROOT, 'series');
const LEGACY_ADULT_FEED_RELATIVE = path.join(ASSET_ROOT, 'javbus_latest_100_feed.json');

const EMPTY_MOVIE_FEED = {
  schema_version: 'movie-app-feed/1',
  source_id: 'sixv',
  generated_at: '1970-01-01T00:00:00.000Z',
  snapshot_captured_at: null,
  items: [],
  summary: {
    record_count: 0,
    target_count: 0,
    recommended_count: 0,
    resource_count: 0,
    missing_urls: [],
    snapshot_http_requests: 0,
    detail_http_requests: 0,
    database_movie_count: 0,
    cover_count: 0,
    offline_ready: true,
  },
};

const EMPTY_SERIES_FEED = {
  schema_version: 'media-app-feed/1',
  source_id: 'series-offline',
  content_kind: 'series',
  generated_at: '1970-01-01T00:00:00.000Z',
  snapshot_captured_at: null,
  items: [],
  summary: {
    record_count: 0,
    target_count: 0,
    recommended_count: 0,
    resource_count: 0,
    missing_urls: [],
    snapshot_http_requests: 0,
    detail_http_requests: 0,
    database_movie_count: 0,
    cover_count: 0,
    offline_ready: true,
  },
};

function resolveMovieSource(projectRoot) {
  const configured = process.env.MOVIE_APP_BUNDLE_PATH || process.env.RESOURCE_FEED_PATH;
  if (configured) {
    return path.isAbsolute(configured) ? configured : path.resolve(projectRoot, configured);
  }
  return path.resolve(projectRoot, '..', 'data', 'resource_index', 'sixv_app_bundle');
}

function resolveSeriesSource(projectRoot) {
  const configured = process.env.SERIES_APP_FEED_PATH;
  if (configured) {
    return path.isAbsolute(configured) ? configured : path.resolve(projectRoot, configured);
  }
  return path.resolve(projectRoot, '..', 'data', 'resource_index', 'series_latest_100_feed.json');
}

function readJson(filePath, label) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    throw new Error(`[with-resource-feed] invalid ${label} at ${filePath}: ${error.message}`);
  }
}

function readAndValidateMovieFeed(sourceDir) {
  const feedPath = path.join(sourceDir, 'feed.json');
  const payload = readJson(feedPath, 'movie feed');
  if (
    payload?.schema_version !== 'movie-app-feed/1'
    || payload?.source_id !== 'sixv'
    || !Array.isArray(payload.items)
    || !payload.summary
  ) {
    throw new Error(`[with-resource-feed] SixV movie feed identity mismatch at ${feedPath}`);
  }
  if (
    payload.summary.record_count !== payload.items.length
    || payload.summary.cover_count !== payload.items.length
    || payload.summary.offline_ready !== true
  ) {
    throw new Error('[with-resource-feed] movie/cover counts are not offline-ready');
  }
  let recommended = 0;
  let resources = 0;
  payload.items.forEach((item, index) => {
    if (
      !item
      || item.rank !== index + 1
      || typeof item.movie_id !== 'string'
      || typeof item.title !== 'string'
      || typeof item.cover_asset_path !== 'string'
      || !Array.isArray(item.resources)
    ) {
      throw new Error(`[with-resource-feed] invalid movie at index ${index}`);
    }
    if ('content_code' in item || 'adult' in item || 'people' in item) {
      throw new Error(`[with-resource-feed] legacy adult field at index ${index}`);
    }
    const coverPath = path.resolve(sourceDir, item.cover_asset_path);
    const relative = path.relative(sourceDir, coverPath);
    if (relative.startsWith('..') || path.isAbsolute(relative) || !fs.existsSync(coverPath)) {
      throw new Error(`[with-resource-feed] missing or unsafe cover at index ${index}`);
    }
    if (item.recommended) recommended += 1;
    resources += item.resources.length;
  });
  if (
    payload.summary.recommended_count !== recommended
    || payload.summary.resource_count !== resources
  ) {
    throw new Error('[with-resource-feed] summary does not match movie items');
  }
  return payload;
}

function cleanString(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function cleanStringArray(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((entry) => typeof entry === 'string' && entry.trim()).map((entry) => entry.trim());
}

function cleanInteger(value, minimum = 0) {
  return Number.isInteger(value) && value >= minimum ? value : null;
}

function cleanRating(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= 10
    ? value
    : null;
}

function cleanPercentRating(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= 100
    ? value
    : null;
}

function normalizeMagnetResource(resource) {
  if (
    !resource
    || resource.resource_type !== 'magnet'
    || typeof resource.url !== 'string'
    || !resource.url.startsWith('magnet:?')
  ) {
    return null;
  }
  return {
    resource_type: 'magnet',
    provider: 'magnet',
    url: resource.url,
    info_hash: cleanString(resource.info_hash),
    display_title: cleanString(resource.display_title) || '磁力资源',
    extraction_code: null,
    quality_tags: cleanStringArray(resource.quality_tags),
  };
}

function normalizeSeriesFeed(sourcePath) {
  const payload = readJson(sourcePath, 'series feed');
  if (
    payload?.schema_version !== 'media-feed/1'
    || payload?.content_kind_filter !== 'series'
    || !Array.isArray(payload.items)
    || payload?.summary?.record_count !== payload.items.length
  ) {
    throw new Error(`[with-resource-feed] series feed identity mismatch at ${sourcePath}`);
  }

  const items = payload.items.map((item, index) => {
    if (
      !item
      || item.content_kind !== 'series'
      || typeof item.movie_id !== 'string'
      || typeof item.source_id !== 'string'
      || typeof item.source_item_key !== 'string'
      || typeof item.detail_url !== 'string'
      || typeof item.listing_title !== 'string'
      || typeof item.title !== 'string'
      || !Array.isArray(item.resources)
    ) {
      throw new Error(`[with-resource-feed] invalid series at index ${index}`);
    }
    if ('content_code' in item || 'adult' in item || 'people' in item) {
      throw new Error(`[with-resource-feed] legacy adult field in series at index ${index}`);
    }
    const resources = item.resources.map(normalizeMagnetResource).filter(Boolean);
    return {
      rank: index + 1,
      movie_id: item.movie_id,
      source_id: item.source_id,
      source_item_key: item.source_item_key,
      detail_url: item.detail_url,
      listing_title: item.listing_title,
      content_kind: 'series',
      series_title: cleanString(item.series_title) || item.title,
      season_number: cleanInteger(item.season_number, 1),
      episode_number: cleanInteger(item.episode_number, 0),
      episode_label: cleanString(item.episode_label),
      update_status: cleanString(item.update_status),
      title: item.title.trim(),
      original_title: cleanString(item.original_title),
      year: cleanInteger(item.year),
      update_date: cleanString(item.update_date),
      release_date: cleanString(item.release_date),
      duration_minutes: cleanInteger(item.duration_minutes),
      countries: cleanStringArray(item.countries),
      genres: cleanStringArray(item.genres),
      languages: cleanStringArray(item.languages),
      directors: cleanStringArray(item.directors),
      actors: cleanStringArray(item.actors),
      imdb_id: cleanString(item.imdb_id),
      imdb_rating: cleanRating(item.imdb_rating),
      imdb_rating_text: cleanString(item.imdb_rating_text),
      douban_rating: cleanRating(item.douban_rating),
      douban_rating_text: cleanString(item.douban_rating_text),
      douban_url: cleanString(item.douban_url),
      rotten_tomatoes_rating: cleanPercentRating(item.rotten_tomatoes_rating),
      rotten_tomatoes_rating_text: cleanString(item.rotten_tomatoes_rating_text),
      rotten_tomatoes_url: cleanString(item.rotten_tomatoes_url),
      bangumi_rating: cleanRating(item.bangumi_rating),
      bangumi_rating_text: cleanString(item.bangumi_rating_text),
      bangumi_subject_id: cleanString(item.bangumi_subject_id),
      bangumi_url: cleanString(item.bangumi_url),
      cover_source_url: cleanString(item.cover_source_url),
      cover_asset_path: null,
      cover_width: null,
      cover_height: null,
      synopsis: cleanString(item.synopsis),
      recommended: Boolean(item.recommended),
      highlight_labels: cleanStringArray(item.highlight_labels),
      quality_tags: cleanStringArray(item.quality_tags),
      resources,
    };
  });

  const recommendedCount = items.filter((item) => item.recommended).length;
  const resourceCount = items.reduce((sum, item) => sum + item.resources.length, 0);
  const snapshotCapturedAt = Array.isArray(payload.sources)
    ? payload.sources.map((source) => cleanString(source?.snapshot_captured_at)).find(Boolean) || null
    : null;

  return {
    schema_version: 'media-app-feed/1',
    source_id: 'series-offline',
    content_kind: 'series',
    generated_at: cleanString(payload.generated_at) || new Date(0).toISOString(),
    snapshot_captured_at: snapshotCapturedAt,
    items,
    summary: {
      record_count: items.length,
      target_count: items.length,
      recommended_count: recommendedCount,
      resource_count: resourceCount,
      missing_urls: [],
      snapshot_http_requests: 0,
      detail_http_requests: 0,
      database_movie_count: items.length,
      cover_count: 0,
      offline_ready: true,
    },
  };
}

module.exports = function withResourceFeed(config) {
  return withDangerousMod(config, [
    'android',
    async (modConfig) => {
      const projectRoot = modConfig.modRequest.projectRoot;
      const movieSourceDir = resolveMovieSource(projectRoot);
      const seriesSourcePath = resolveSeriesSource(projectRoot);
      const movieTargetDir = path.resolve(projectRoot, MOVIE_TARGET_RELATIVE);
      const seriesTargetDir = path.resolve(projectRoot, SERIES_TARGET_RELATIVE);
      const legacyAdultFeed = path.resolve(projectRoot, LEGACY_ADULT_FEED_RELATIVE);

      fs.rmSync(legacyAdultFeed, { force: true });
      fs.rmSync(movieTargetDir, { recursive: true, force: true });
      fs.rmSync(seriesTargetDir, { recursive: true, force: true });
      fs.mkdirSync(movieTargetDir, { recursive: true });
      fs.mkdirSync(seriesTargetDir, { recursive: true });

      if (fs.existsSync(path.join(movieSourceDir, 'feed.json'))) {
        const moviePayload = readAndValidateMovieFeed(movieSourceDir);
        fs.cpSync(movieSourceDir, movieTargetDir, { recursive: true });
        console.log(
          `[with-resource-feed] bundled ${moviePayload.items.length} movies, ${moviePayload.summary.recommended_count} recommended and ${moviePayload.summary.cover_count} offline covers`,
        );
      } else {
        fs.writeFileSync(path.join(movieTargetDir, 'feed.json'), JSON.stringify(EMPTY_MOVIE_FEED), 'utf8');
        console.warn(`[with-resource-feed] movie bundle not found; bundled empty feed. Expected ${movieSourceDir}`);
      }

      if (fs.existsSync(seriesSourcePath)) {
        const seriesPayload = normalizeSeriesFeed(seriesSourcePath);
        fs.writeFileSync(path.join(seriesTargetDir, 'feed.json'), JSON.stringify(seriesPayload), 'utf8');
        console.log(
          `[with-resource-feed] bundled ${seriesPayload.items.length} series entries and ${seriesPayload.summary.resource_count} magnet resources; remote covers use App cache until local cover assets are supplied`,
        );
      } else {
        fs.writeFileSync(path.join(seriesTargetDir, 'feed.json'), JSON.stringify(EMPTY_SERIES_FEED), 'utf8');
        console.warn(`[with-resource-feed] series feed not found; bundled empty feed. Expected ${seriesSourcePath}`);
      }

      return modConfig;
    },
  ]);
};
