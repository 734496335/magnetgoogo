import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseResourceFeed,
  resourceFeedItemKey,
  ResourceFeedValidationError,
} from '../src/core/resourceFeedProtocol.ts';
import {
  FEATURED_SCORE_THRESHOLD,
  HIGH_SCORE_THRESHOLD,
  getMovieScoreTier,
  getVisibleMovieRatings,
} from '../src/core/movieRatings.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const bundleDir = path.resolve(here, '..', '..', 'data', 'resource_index', 'sixv_app_bundle');
const localFeedPath = path.join(bundleDir, 'feed.json');

const EXPECTED_RECOMMENDED = [
  '寒战1994',
  '穿普拉达的女王2',
  '宇宙巨人：希曼崛起',
  '揭秘日',
  '惊声尖笑6',
  '星球大战：曼达洛人与古古',
  '末日逃生2：迁移',
  '10间敢死队',
  '后室',
];

function sampleResource(provider = 'magnet') {
  return {
    resource_type: provider === 'magnet' ? 'magnet' : 'cloud',
    provider,
    url: provider === 'magnet'
      ? 'magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
      : `https://example.com/${provider}`,
    info_hash: provider === 'magnet' ? 'a'.repeat(40) : null,
    display_title: '1080p.HD中字',
    extraction_code: provider === 'baidu' ? '1234' : null,
    quality_tags: ['1080p', 'HD'],
  };
}

function sampleItem(rank, title = `Movie ${rank}`, recommended = false) {
  return {
    rank,
    movie_id: `movie:${String(rank).padStart(64, '0')}`,
    source_id: 'sixv',
    source_item_key: `/dy/${rank}.html`,
    detail_url: `https://www.6v520.com/dy/${rank}.html`,
    listing_title: `2026动作《${title}》4K`,
    title,
    original_title: null,
    year: 2026,
    update_date: '2026-07-25',
    release_date: '2026-07-01',
    duration_minutes: 120,
    countries: ['中国'],
    genres: ['动作'],
    languages: ['国语'],
    directors: ['导演'],
    actors: ['演员'],
    imdb_id: 'tt1234567',
    imdb_rating: 7.4,
    imdb_rating_text: '7.4/10 from 1000 users',
    douban_rating: 8.1,
    douban_rating_text: '8.1/10',
    douban_url: null,
    cover_source_url: 'https://www.66tutup.com/test.jpg',
    cover_asset_path: `covers/${String(rank).padStart(64, '0')}.jpg`,
    cover_width: 720,
    cover_height: 1080,
    synopsis: '剧情简介',
    recommended,
    highlight_labels: recommended ? ['推荐'] : [],
    quality_tags: ['4K', 'HD'],
    resources: [sampleResource()],
  };
}

function sampleFeed(items) {
  return {
    schema_version: 'movie-app-feed/1',
    source_id: 'sixv',
    generated_at: '2026-07-25T15:00:00Z',
    snapshot_captured_at: '2026-07-25T14:00:00Z',
    items,
    summary: {
      record_count: items.length,
      target_count: items.length,
      recommended_count: items.filter((item) => item.recommended).length,
      resource_count: items.reduce((sum, item) => sum + item.resources.length, 0),
      missing_urls: [],
      snapshot_http_requests: 0,
      detail_http_requests: 0,
      database_movie_count: items.length,
      cover_count: items.length,
      offline_ready: true,
    },
  };
}

const parsed = parseResourceFeed(sampleFeed([sampleItem(1), sampleItem(2)]));
assert.equal(parsed.items.length, 2);
assert.equal(new Set(parsed.items.map(resourceFeedItemKey)).size, 2);
console.log('PASS  M1  movie IDs are stable unique card keys');

assert.throws(
  () => parseResourceFeed(sampleFeed([sampleItem(2)])),
  (error) => error instanceof ResourceFeedValidationError && error.code === 'RANK_NOT_CONTINUOUS',
);
console.log('PASS  M2  non-continuous movie ranking is rejected');

const mismatch = sampleFeed([sampleItem(1)]);
mismatch.summary.cover_count = 0;
assert.throws(
  () => parseResourceFeed(mismatch),
  (error) => error instanceof ResourceFeedValidationError && error.code === 'COUNT_MISMATCH',
);
console.log('PASS  M3  movie/cover count mismatch is rejected');

const legacyAdult = sampleFeed([sampleItem(1)]);
legacyAdult.items[0].content_code = 'ABC-001';
assert.throws(
  () => parseResourceFeed(legacyAdult),
  (error) => error instanceof ResourceFeedValidationError && error.code === 'LEGACY_ADULT_FIELD',
);
console.log('PASS  M4  legacy adult-feed fields are rejected');

assert.equal(FEATURED_SCORE_THRESHOLD, 6.0);
assert.equal(HIGH_SCORE_THRESHOLD, 8.0);
assert.deepEqual(
  getVisibleMovieRatings({ imdb_rating: 0, douban_rating: null }),
  [],
);
assert.deepEqual(
  getVisibleMovieRatings({ imdb_rating: 6.9, douban_rating: 6.0 }).map(({ source, value, tier }) => ({ source, value, tier })),
  [
    { source: 'IMDb', value: 6.9, tier: 'featured' },
    { source: '豆瓣', value: 6.0, tier: 'featured' },
  ],
);
assert.equal(getMovieScoreTier({ imdb_rating: 7.9, douban_rating: 5.9 }), 'featured');
assert.equal(getMovieScoreTier({ imdb_rating: 8.0, douban_rating: 7.9 }), 'high');
assert.equal(getMovieScoreTier({ imdb_rating: 5.9, douban_rating: null }), null);
console.log('PASS  M5  zero is hidden, 6.0+ is featured and 8.0+ is high score');

if (fs.existsSync(localFeedPath)) {
  const local = parseResourceFeed(JSON.parse(fs.readFileSync(localFeedPath, 'utf8')));
  assert.equal(local.items.length, 50);
  assert.equal(local.summary.record_count, 50);
  assert.equal(local.summary.cover_count, 50);
  assert.equal(local.summary.recommended_count, 9);
  assert.equal(local.summary.resource_count, 134);
  assert.equal(local.summary.offline_ready, true);
  assert.deepEqual(
    local.items.filter((item) => item.recommended).map((item) => item.title),
    EXPECTED_RECOMMENDED,
  );
  assert.equal(new Set(local.items.map(resourceFeedItemKey)).size, 50);
  for (const item of local.items) {
    assert.equal('content_code' in item, false);
    assert.equal('adult' in item, false);
    const visibleRatings = getVisibleMovieRatings(item);
    assert.ok(visibleRatings.every((rating) => rating.value > 0 && rating.value <= 10));
    const coverPath = path.resolve(bundleDir, item.cover_asset_path);
    assert.ok(coverPath.startsWith(bundleDir + path.sep));
    assert.ok(fs.existsSync(coverPath), `missing cover: ${item.cover_asset_path}`);
    assert.ok(fs.statSync(coverPath).size > 0, `empty cover: ${item.cover_asset_path}`);
  }
  const providers = new Set(local.items.flatMap((item) => item.resources.map((resource) => resource.provider)));
  assert.ok(providers.has('magnet'));
  assert.ok(providers.has('xunlei'));
  assert.ok(providers.has('quark'));
  assert.ok(providers.has('baidu'));
  console.log('PASS  M6  SixV bundle is 50 movies / 9 recommendations / 134 resources / 50 offline covers');
} else {
  console.log('SKIP  M6  local untracked SixV App bundle is not present');
}

console.log('=== Movie resource feed tests passed ===');
