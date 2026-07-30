const { withDangerousMod } = require('@expo/config-plugins');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ASSET_ROOT = path.join('android', 'app', 'src', 'main', 'assets', 'resource-index');
const MOVIE_TARGET_RELATIVE = path.join(ASSET_ROOT, 'sixv');
const SERIES_TARGET_RELATIVE = path.join(ASSET_ROOT, 'series');
const LEGACY_ADULT_FEED_RELATIVE = path.join(ASSET_ROOT, 'javbus_latest_100_feed.json');

function emptyFeed(kind) {
  return {
    schema_version: 'media-app-feed/1',
    source_id: `${kind}-offline`,
    content_kind: kind,
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
}

function resolveBundleSource(projectRoot, kind) {
  const configured = kind === 'movie'
    ? process.env.MOVIE_APP_BUNDLE_PATH || process.env.RESOURCE_FEED_PATH
    : process.env.SERIES_APP_BUNDLE_PATH || process.env.SERIES_APP_FEED_PATH;
  if (configured) {
    return path.isAbsolute(configured) ? configured : path.resolve(projectRoot, configured);
  }
  return path.resolve(projectRoot, '..', 'data', 'resource_index', `${kind}_app_bundle`);
}

function readJson(filePath, label) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    throw new Error(`[with-resource-feed] invalid ${label} at ${filePath}: ${error.message}`);
  }
}

function safeAssetPath(sourceDir, relativePath, context) {
  if (typeof relativePath !== 'string' || !relativePath.trim()) {
    throw new Error(`[with-resource-feed] ${context}.cover_asset_path is required`);
  }
  const resolved = path.resolve(sourceDir, relativePath);
  const relative = path.relative(sourceDir, resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative) || !fs.existsSync(resolved)) {
    throw new Error(`[with-resource-feed] missing or unsafe cover for ${context}`);
  }
  return resolved;
}

function hasDirtyLabel(value) {
  return (
    typeof value !== 'string'
    || !value.trim()
    || /^\s*[:：]/.test(value)
    || /<[^>]*>|\\?["']?\s*>/.test(value)
    || /\S\s+片(?:$|\s)/.test(value)
  );
}

function isGenericResourceTitle(value) {
  return /^\s*(?:2160p|1080p|720p|4k|uhd|fhd|hd|bd|蓝光|磁力资源|下载|资源)\s*$/i.test(
    String(value || ''),
  );
}

function readAndValidateMediaBundle(sourceDir, kind) {
  const feedPath = path.join(sourceDir, 'feed.json');
  const payload = readJson(feedPath, `${kind} feed`);
  if (
    payload?.schema_version !== 'media-app-feed/1'
    || payload?.source_id !== `${kind}-offline`
    || payload?.content_kind !== kind
    || !Array.isArray(payload.items)
    || !payload.summary
  ) {
    throw new Error(`[with-resource-feed] ${kind} feed identity mismatch at ${feedPath}`);
  }
  if (
    payload.summary.record_count !== payload.items.length
    || payload.summary.cover_count !== payload.items.length
    || payload.summary.offline_ready !== true
  ) {
    throw new Error(`[with-resource-feed] ${kind} feed is not fully offline-ready`);
  }

  const movieIds = new Set();
  let recommended = 0;
  let resources = 0;
  payload.items.forEach((item, index) => {
    const context = `${kind}[${index}]`;
    if (
      !item
      || item.rank !== index + 1
      || typeof item.movie_id !== 'string'
      || !item.movie_id
      || movieIds.has(item.movie_id)
      || item.content_kind !== kind
      || typeof item.title !== 'string'
      || !item.title.trim()
      || !Array.isArray(item.resources)
      || item.resources.length === 0
    ) {
      throw new Error(`[with-resource-feed] invalid ${context}`);
    }
    movieIds.add(item.movie_id);
    if ('content_code' in item || 'adult' in item || 'people' in item) {
      throw new Error(`[with-resource-feed] legacy adult field in ${context}`);
    }
    for (const field of ['genres', 'countries']) {
      if (!Array.isArray(item[field]) || item[field].some(hasDirtyLabel)) {
        throw new Error(`[with-resource-feed] dirty ${field} in ${context}`);
      }
    }

    const coverPath = safeAssetPath(sourceDir, item.cover_asset_path, context);
    const cover = fs.readFileSync(coverPath);
    const digest = crypto.createHash('sha256').update(cover).digest('hex');
    if (
      typeof item.cover_content_hash !== 'string'
      || digest !== item.cover_content_hash
      || item.cover_byte_size !== cover.length
      || !Number.isInteger(item.cover_width)
      || item.cover_width <= 0
      || !Number.isInteger(item.cover_height)
      || item.cover_height <= 0
    ) {
      throw new Error(`[with-resource-feed] cover metadata mismatch in ${context}`);
    }

    item.resources.forEach((resource, resourceIndex) => {
      if (
        !resource
        || !['magnet', 'cloud'].includes(resource.resource_type)
        || typeof resource.url !== 'string'
        || typeof resource.display_title !== 'string'
        || !resource.display_title.trim()
      ) {
        throw new Error(`[with-resource-feed] invalid ${context}.resources[${resourceIndex}]`);
      }
      if (
        kind === 'series'
        && Number.isInteger(item.season_number)
        && resource.season_number !== item.season_number
      ) {
        throw new Error(`[with-resource-feed] cross-season resource in ${context}`);
      }
      if (resource.episode_label && isGenericResourceTitle(resource.display_title)) {
        throw new Error(`[with-resource-feed] episode identity lost in ${context}`);
      }
    });
    if (item.recommended) recommended += 1;
    resources += item.resources.length;
  });

  if (
    payload.summary.recommended_count !== recommended
    || payload.summary.resource_count !== resources
  ) {
    throw new Error(`[with-resource-feed] summary does not match ${kind} items`);
  }
  return payload;
}

function bundleOrEmpty({ sourceDir, targetDir, kind }) {
  fs.rmSync(targetDir, { recursive: true, force: true });
  fs.mkdirSync(targetDir, { recursive: true });
  if (!fs.existsSync(path.join(sourceDir, 'feed.json'))) {
    if (process.env.ALLOW_EMPTY_RESOURCE_FEED === '1') {
      fs.writeFileSync(path.join(targetDir, 'feed.json'), JSON.stringify(emptyFeed(kind)), 'utf8');
      console.warn(`[with-resource-feed] ${kind} bundle not found; explicit empty-feed override is active. Expected ${sourceDir}`);
      return;
    }
    throw new Error(
      `[with-resource-feed] required ${kind} offline bundle is missing at ${sourceDir}. Run deploy\\resource-index\\run-media-offline.bat first.`,
    );
  }
  const payload = readAndValidateMediaBundle(sourceDir, kind);
  fs.cpSync(sourceDir, targetDir, { recursive: true });
  console.log(
    `[with-resource-feed] bundled ${payload.items.length} ${kind} entries, ${payload.summary.resource_count} resources and ${payload.summary.cover_count} verified offline covers`,
  );
}

module.exports = function withResourceFeed(config) {
  return withDangerousMod(config, [
    'android',
    async (modConfig) => {
      const projectRoot = modConfig.modRequest.projectRoot;
      const movieSourceDir = resolveBundleSource(projectRoot, 'movie');
      const seriesSourceDir = resolveBundleSource(projectRoot, 'series');
      const movieTargetDir = path.resolve(projectRoot, MOVIE_TARGET_RELATIVE);
      const seriesTargetDir = path.resolve(projectRoot, SERIES_TARGET_RELATIVE);
      const legacyAdultFeed = path.resolve(projectRoot, LEGACY_ADULT_FEED_RELATIVE);

      fs.rmSync(legacyAdultFeed, { force: true });
      bundleOrEmpty({ sourceDir: movieSourceDir, targetDir: movieTargetDir, kind: 'movie' });
      bundleOrEmpty({ sourceDir: seriesSourceDir, targetDir: seriesTargetDir, kind: 'series' });
      return modConfig;
    },
  ]);
};
