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
import { resourceDisplayTitle } from '../src/core/mediaResourceTitle.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const dataRoot = process.env.RESOURCE_INDEX_DATA_ROOT
  ? path.resolve(process.env.RESOURCE_INDEX_DATA_ROOT)
  : path.resolve(here, '..', '..', 'data', 'resource_index');
const movieBundleDir = path.join(dataRoot, 'movie_app_bundle');
const seriesBundleDir = path.join(dataRoot, 'series_app_bundle');

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
    rotten_tomatoes_rating: null,
    rotten_tomatoes_rating_text: null,
    rotten_tomatoes_url: null,
    bangumi_rating: null,
    bangumi_rating_text: null,
    bangumi_subject_id: null,
    bangumi_url: null,
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

function sampleSeriesFeed() {
  const item = {
    ...sampleItem(1, '测试剧集'),
    source_id: 'sixv-series',
    content_kind: 'series',
    series_title: '测试剧集',
    season_number: 1,
    episode_number: 8,
    episode_label: '更新08',
    update_status: '更新08',
    cover_asset_path: 'covers/series-test.jpg',
    cover_width: 720,
    cover_height: 1080,
    recommended: false,
  };
  return {
    schema_version: 'media-app-feed/1',
    source_id: 'series-offline',
    content_kind: 'series',
    generated_at: '2026-07-26T12:00:00Z',
    snapshot_captured_at: '2026-07-26T11:00:00Z',
    items: [item],
    summary: {
      record_count: 1,
      target_count: 1,
      recommended_count: 0,
      resource_count: 1,
      missing_urls: [],
      snapshot_http_requests: 0,
      detail_http_requests: 0,
      database_movie_count: 1,
      cover_count: 1,
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
  getVisibleMovieRatings({
    imdb_rating: 0,
    douban_rating: null,
    rotten_tomatoes_rating: null,
    bangumi_rating: null,
  }),
  [],
);
assert.deepEqual(
  getVisibleMovieRatings({
    imdb_rating: 6.9,
    douban_rating: 6.0,
    rotten_tomatoes_rating: 85,
    bangumi_rating: 7.2,
  }).map(({ source, value, displayValue, tier }) => ({ source, value, displayValue, tier })),
  [
    { source: '豆瓣', value: 6.0, displayValue: '6.0', tier: 'featured' },
    { source: 'IMDb', value: 6.9, displayValue: '6.9', tier: 'featured' },
    { source: '烂番茄', value: 85, displayValue: '85%', tier: 'high' },
    { source: 'Bangumi', value: 7.2, displayValue: '7.2', tier: 'featured' },
  ],
);
assert.equal(getMovieScoreTier({
  imdb_rating: 7.9,
  douban_rating: 5.9,
  rotten_tomatoes_rating: null,
  bangumi_rating: null,
}), 'featured');
assert.equal(getMovieScoreTier({
  imdb_rating: 8.0,
  douban_rating: 7.9,
  rotten_tomatoes_rating: null,
  bangumi_rating: null,
}), 'high');
assert.equal(getMovieScoreTier({
  imdb_rating: 5.9,
  douban_rating: null,
  rotten_tomatoes_rating: null,
  bangumi_rating: null,
}), null);
console.log('PASS  M5  IMDb/Douban/Bangumi use 10-point tiers and Rotten Tomatoes uses percent tiers');

const series = parseResourceFeed(sampleSeriesFeed());
assert.equal(series.content_kind, 'series');
assert.equal(series.items[0].content_kind, 'series');
assert.equal(series.items[0].update_status, '更新08');
assert.equal(series.items[0].cover_asset_path, 'covers/series-test.jpg');
assert.equal(resourceFeedItemKey(series.items[0]).startsWith('series:'), true);
console.log('PASS  M6  bundled series feed requires a local offline cover');

const episodeResource = {
  ...sampleResource(),
  display_title: '1080P',
  url: 'magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb&dn=X-Men%2097%20S01E04%20Motendo%201080p',
};
assert.equal(resourceDisplayTitle(episodeResource), 'S01E04 · 1080P');
assert.equal(
  resourceDisplayTitle({
    ...sampleResource(),
    display_title: 'HD',
    url: 'magnet:?xt=urn:btih:cccccccccccccccccccccccccccccccccccccccc&dn=%E7%AC%AC1-2%E9%9B%86%20720p',
  }),
  '第1-2集 · HD',
);
assert.equal(
  resourceDisplayTitle({ ...sampleResource(), display_title: '完整文件名.mkv' }),
  '完整文件名.mkv',
);
console.log('PASS  M7  generic quality-only resource titles recover episode identity from magnet dn');

function verifyLocalBundle(bundleDir, expectedKind) {
  const feedPath = path.join(bundleDir, 'feed.json');
  if (!fs.existsSync(feedPath)) return false;
  const local = parseResourceFeed(JSON.parse(fs.readFileSync(feedPath, 'utf8')));
  assert.equal(local.content_kind, expectedKind);
  assert.equal(local.items.length, 100);
  assert.equal(local.summary.record_count, 100);
  assert.equal(local.summary.cover_count, 100);
  assert.equal(local.summary.offline_ready, true);
  assert.equal(new Set(local.items.map(resourceFeedItemKey)).size, 100);
  for (const item of local.items) {
    assert.equal('content_code' in item, false);
    assert.equal('adult' in item, false);
    const visibleRatings = getVisibleMovieRatings(item);
    assert.ok(visibleRatings.every((rating) => rating.value > 0 && rating.value <= 10));
    const coverPath = path.resolve(bundleDir, item.cover_asset_path);
    assert.ok(coverPath.startsWith(bundleDir + path.sep));
    assert.ok(fs.existsSync(coverPath), `missing cover: ${item.cover_asset_path}`);
    assert.ok(fs.statSync(coverPath).size > 0, `empty cover: ${item.cover_asset_path}`);
    if (expectedKind === 'series' && Number.isInteger(item.season_number)) {
      for (const resource of item.resources) {
        assert.equal(resource.season_number, item.season_number);
      }
    }
  }
  return true;
}

const movieReady = verifyLocalBundle(movieBundleDir, 'movie');
const seriesReady = verifyLocalBundle(seriesBundleDir, 'series');
if (movieReady && seriesReady) {
  console.log('PASS  M8  local movie100 and series100 bundles have 200 verified offline covers');
} else {
  console.log('SKIP  M8  complete local movie/series App bundles are not present');
}

console.log('=== Media resource feed tests passed ===');
