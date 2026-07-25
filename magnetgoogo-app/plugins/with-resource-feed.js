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
  'javbus_latest_100_feed.json',
);

const EMPTY_FEED = {
  summary: {
    generated_at: '1970-01-01T00:00:00.000Z',
    source_id: 'unconfigured',
    record_count: 0,
    canonical_content_count: 0,
    content_observation_count: 0,
    resource_count: 0,
    resource_observation_count: 0,
    people_count: 0,
    tag_count: 0,
    records_without_resources: 0,
    missing_urls: [],
    running_runs: 0,
    partial_runs: 0,
  },
  items: [],
};

function resolveSource(projectRoot) {
  const configured = process.env.RESOURCE_FEED_PATH;
  if (configured) {
    return path.isAbsolute(configured) ? configured : path.resolve(projectRoot, configured);
  }
  return path.resolve(projectRoot, '..', 'data', 'resource_index', 'javbus_latest_100_feed.json');
}

function validateFeed(raw, sourcePath) {
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new Error(`[with-resource-feed] invalid JSON at ${sourcePath}: ${error.message}`);
  }

  if (!payload || typeof payload !== 'object' || !payload.summary || !Array.isArray(payload.items)) {
    throw new Error(`[with-resource-feed] invalid feed shape at ${sourcePath}`);
  }
  if (payload.summary.record_count !== payload.items.length) {
    throw new Error(
      `[with-resource-feed] record_count=${payload.summary.record_count} but items=${payload.items.length}`,
    );
  }
  payload.items.forEach((item, index) => {
    if (!item || item.rank !== index + 1 || typeof item.content_code !== 'string') {
      throw new Error(`[with-resource-feed] invalid item/rank at index ${index}`);
    }
  });
  return payload;
}

module.exports = function withResourceFeed(config) {
  return withDangerousMod(config, [
    'android',
    async (modConfig) => {
      const projectRoot = modConfig.modRequest.projectRoot;
      const sourcePath = resolveSource(projectRoot);
      const targetPath = path.resolve(projectRoot, TARGET_RELATIVE);
      fs.mkdirSync(path.dirname(targetPath), { recursive: true });

      if (fs.existsSync(sourcePath)) {
        const raw = fs.readFileSync(sourcePath, 'utf8');
        const payload = validateFeed(raw, sourcePath);
        fs.writeFileSync(targetPath, JSON.stringify(payload), 'utf8');
        console.log(
          `[with-resource-feed] bundled ${payload.items.length} items from ${sourcePath}`,
        );
      } else {
        fs.writeFileSync(targetPath, JSON.stringify(EMPTY_FEED), 'utf8');
        console.warn(
          `[with-resource-feed] source not found; bundled empty feed. Expected ${sourcePath}`,
        );
      }

      return modConfig;
    },
  ]);
};
