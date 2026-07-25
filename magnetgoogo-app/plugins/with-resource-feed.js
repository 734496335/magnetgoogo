const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const TARGET_RELATIVE = path.join(
  'android',
  'app',
  'src',
  'main',
  'assets',
  'resource-index',
  'sixv',
);
const LEGACY_ADULT_FEED_RELATIVE = path.join(
  'android',
  'app',
  'src',
  'main',
  'assets',
  'resource-index',
  'javbus_latest_100_feed.json',
);

const EMPTY_FEED = {
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

function resolveSource(projectRoot) {
  const configured = process.env.MOVIE_APP_BUNDLE_PATH || process.env.RESOURCE_FEED_PATH;
  if (configured) {
    return path.isAbsolute(configured) ? configured : path.resolve(projectRoot, configured);
  }
  return path.resolve(projectRoot, '..', 'data', 'resource_index', 'sixv_app_bundle');
}

function readAndValidateFeed(sourceDir) {
  const feedPath = path.join(sourceDir, 'feed.json');
  let payload;
  try {
    payload = JSON.parse(fs.readFileSync(feedPath, 'utf8'));
  } catch (error) {
    throw new Error(`[with-resource-feed] invalid movie feed at ${feedPath}: ${error.message}`);
  }
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

module.exports = function withResourceFeed(config) {
  return withDangerousMod(config, [
    'android',
    async (modConfig) => {
      const projectRoot = modConfig.modRequest.projectRoot;
      const sourceDir = resolveSource(projectRoot);
      const targetDir = path.resolve(projectRoot, TARGET_RELATIVE);
      const legacyAdultFeed = path.resolve(projectRoot, LEGACY_ADULT_FEED_RELATIVE);

      fs.rmSync(legacyAdultFeed, { force: true });
      fs.rmSync(targetDir, { recursive: true, force: true });
      fs.mkdirSync(targetDir, { recursive: true });

      if (fs.existsSync(path.join(sourceDir, 'feed.json'))) {
        const payload = readAndValidateFeed(sourceDir);
        fs.cpSync(sourceDir, targetDir, { recursive: true });
        console.log(
          `[with-resource-feed] bundled ${payload.items.length} SixV movies, ${payload.summary.recommended_count} recommended and ${payload.summary.cover_count} offline covers`,
        );
      } else {
        fs.writeFileSync(path.join(targetDir, 'feed.json'), JSON.stringify(EMPTY_FEED), 'utf8');
        console.warn(
          `[with-resource-feed] movie bundle not found; bundled empty feed. Expected ${sourceDir}`,
        );
      }

      return modConfig;
    },
  ]);
};
