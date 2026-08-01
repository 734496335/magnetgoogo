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
  FEATURED_PERCENT_THRESHOLD,
  FEATURED_SCORE_THRESHOLD,
  HIGH_PERCENT_THRESHOLD,
  HIGH_SCORE_THRESHOLD,
  MEDIA_LIST_SORT_POLICY,
  MEDIA_RECOMMENDATION_POLICY,
  MOVIE_PRIMARY_SCORE_PRIORITY,
  compareMediaFeedRank,
  getMovieScoreTier,
  getPrimaryMovieRating,
  getVisibleMovieRatings,
  isServerRecommendedMovie,
} from '../src/core/movieRatings.ts';
import {
  inferSeriesSeason,
  magnetBatchText,
  resourceDisplayTitle,
  resourceEpisodeIdentity,
  seriesStatusForDisplay,
  sortMediaResources,
} from '../src/core/mediaResourceTitle.ts';

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
    rotten_tomatoes_rating: 92,
    rotten_tomatoes_rating_text: '92%',
    rotten_tomatoes_url: 'https://www.rottentomatoes.com/m/test',
    bangumi_rating: 8.4,
    bangumi_rating_text: '8.4/10',
    bangumi_subject_id: '12345',
    bangumi_url: 'https://bgm.tv/subject/12345',
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
    cover_asset_path: null,
    cover_width: null,
    cover_height: null,
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
      cover_count: 0,
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
assert.equal(FEATURED_PERCENT_THRESHOLD, 60);
assert.equal(HIGH_PERCENT_THRESHOLD, 80);
assert.equal(MEDIA_LIST_SORT_POLICY, 'release-rank');
assert.equal(MEDIA_RECOMMENDATION_POLICY, 'server-recommended');
assert.deepEqual(MOVIE_PRIMARY_SCORE_PRIORITY, ['douban', 'imdb', 'bangumi', 'rotten_tomatoes']);
assert.deepEqual(
  getVisibleMovieRatings({
    imdb_rating: 0,
    douban_rating: null,
    rotten_tomatoes_rating: 0,
    bangumi_rating: null,
  }),
  [],
);
assert.deepEqual(
  getVisibleMovieRatings({
    imdb_rating: 10.1,
    douban_rating: -1,
    rotten_tomatoes_rating: 101,
    bangumi_rating: 10.1,
  }),
  [],
);
assert.deepEqual(
  getVisibleMovieRatings({
    imdb_rating: 7.2,
    douban_rating: 8.1,
    rotten_tomatoes_rating: 92,
    bangumi_rating: 8.4,
  }).map(({ key, source, displayValue, tier, isPrimary }) => ({ key, source, displayValue, tier, isPrimary })),
  [
    { key: 'douban', source: '豆瓣', displayValue: '8.1', tier: 'high', isPrimary: true },
    { key: 'imdb', source: 'IMDb', displayValue: '7.2', tier: null, isPrimary: false },
    { key: 'rotten_tomatoes', source: '烂番茄', displayValue: '92%', tier: null, isPrimary: false },
    { key: 'bangumi', source: 'Bangumi', displayValue: '8.4', tier: null, isPrimary: false },
  ],
);
assert.equal(getPrimaryMovieRating({ imdb_rating: 9.0, douban_rating: 5.9 })?.source, '豆瓣');
assert.equal(getMovieScoreTier({ imdb_rating: 9.0, douban_rating: 5.9 }), null);
assert.equal(getPrimaryMovieRating({ imdb_rating: 7.9, bangumi_rating: 9.2, rotten_tomatoes_rating: 95 })?.source, 'IMDb');
assert.equal(getMovieScoreTier({ imdb_rating: 7.9, bangumi_rating: 9.2, rotten_tomatoes_rating: 95 }), 'featured');
assert.equal(getPrimaryMovieRating({ bangumi_rating: 8.2, rotten_tomatoes_rating: 95 })?.source, 'Bangumi');
assert.equal(getMovieScoreTier({ bangumi_rating: 8.2, rotten_tomatoes_rating: 95 }), 'high');
assert.equal(getPrimaryMovieRating({ rotten_tomatoes_rating: 85 })?.source, '烂番茄');
assert.equal(getMovieScoreTier({ rotten_tomatoes_rating: 85 }), 'high');
assert.deepEqual(
  [sampleItem(2), sampleItem(1)].sort(compareMediaFeedRank).map((item) => item.rank),
  [1, 2],
);
assert.equal(isServerRecommendedMovie(sampleItem(1, 'Recommended', true)), true);
assert.equal(isServerRecommendedMovie(sampleItem(1, 'Not recommended', false)), false);
console.log('PASS  M5  four ratings display while rank, recommendation and primary-score policies stay explicit');

const legacyRatingItem = sampleItem(1, 'Legacy revision');
delete legacyRatingItem.rotten_tomatoes_rating;
delete legacyRatingItem.rotten_tomatoes_rating_text;
delete legacyRatingItem.rotten_tomatoes_url;
delete legacyRatingItem.bangumi_rating;
delete legacyRatingItem.bangumi_rating_text;
delete legacyRatingItem.bangumi_subject_id;
delete legacyRatingItem.bangumi_url;
const legacyRatingFeed = parseResourceFeed(sampleFeed([legacyRatingItem]));
assert.equal(legacyRatingFeed.items[0].rotten_tomatoes_rating, null);
assert.equal(legacyRatingFeed.items[0].bangumi_rating, null);
assert.equal(legacyRatingFeed.items[0].bangumi_subject_id, null);
console.log('PASS  M5B  old revisions without new rating fields remain compatible');

const series = parseResourceFeed(sampleSeriesFeed());
assert.equal(series.content_kind, 'series');
assert.equal(series.items[0].content_kind, 'series');
assert.equal(series.items[0].update_status, '更新08');
assert.equal(series.items[0].cover_asset_path, null);
assert.equal(resourceFeedItemKey(series.items[0]).startsWith('series:'), true);
console.log('PASS  M6  bundled series feed supports cached cover fallback and offline text/resources');

const episodeResource = {
  ...sampleResource(),
  display_title: '1080P',
  url: 'magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb&dn=X-Men%2097%20S01E04%20Motendo%201080p',
};
assert.equal(resourceDisplayTitle(episodeResource, 1), 'S01E04 · 1080p · HD');
assert.equal(
  resourceDisplayTitle({
    ...sampleResource(),
    display_title: 'HD',
    quality_tags: ['HD'],
    url: 'magnet:?xt=urn:btih:cccccccccccccccccccccccccccccccccccccccc&dn=%E7%AC%AC1-2%E9%9B%86%20720p',
  }, 1),
  'S01E01-E02 · HD',
);
assert.equal(
  resourceDisplayTitle({ ...sampleResource(), display_title: '完整文件名.mkv' }),
  '完整文件名.mkv',
);
assert.equal(inferSeriesSeason('X战警97 第一季', 2), 1);
assert.equal(inferSeriesSeason('犯罪心理：演变 第十八季', 19), 18);
assert.equal(inferSeriesSeason('Show Season 4', null), 4);
assert.equal(seriesStatusForDisplay('X战警97 第一季', 2, '第二季 第6集'), null);
assert.equal(seriesStatusForDisplay('X战警97 第一季', 2, '更新10'), '更新10');
assert.equal(seriesStatusForDisplay('Show', 3, 'S02E06'), null);

const unorderedResources = [
  {
    ...sampleResource(),
    info_hash: '2'.repeat(40),
    display_title: '1080P',
    url: `magnet:?xt=urn:btih:${'2'.repeat(40)}&dn=Show.S02E01.1080p`,
  },
  {
    ...sampleResource(),
    info_hash: '1'.repeat(40),
    display_title: '1080P',
    url: `magnet:?xt=urn:btih:${'1'.repeat(40)}&dn=Show.S01E02.1080p`,
  },
  {
    ...sampleResource(),
    info_hash: '0'.repeat(40),
    display_title: '1080P',
    url: `magnet:?xt=urn:btih:${'0'.repeat(40)}&dn=Show.S01E01.1080p`,
  },
  {
    ...sampleResource(),
    info_hash: '3'.repeat(40),
    display_title: '第一季.全集打包.1080p',
    url: `magnet:?xt=urn:btih:${'3'.repeat(40)}&dn=Show.S01.COMPLETE.1080p`,
  },
];
const sortedResources = sortMediaResources(unorderedResources, 1);
assert.deepEqual(
  sortedResources.map((resource) => resourceEpisodeIdentity(resource, 1)?.label),
  ['S01E01', 'S01E02', 'S01 全季', 'S02E01'],
);
assert.equal(
  magnetBatchText([...sortedResources, sortedResources[0]]),
  sortedResources.map((resource) => resource.url).join('\r\n'),
);
console.log('PASS  M7  series titles recover episode identity, sort naturally and batch-copy one magnet per line');

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
    assert.ok(visibleRatings.every((rating) => (
      rating.value > 0 && rating.value <= (rating.key === 'rotten_tomatoes' ? 100 : 10)
    )));
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
  console.log('PASS  M8  SixV bundle is 50 movies / 9 recommendations / 134 resources / 50 offline covers');
} else {
  console.log('SKIP  M8  local untracked SixV App bundle is not present');
}

console.log('=== Movie resource feed tests passed ===');
