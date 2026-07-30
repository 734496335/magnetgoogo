import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createAsyncSerialQueue } from '../src/core/asyncSerialQueue.ts';
import { parseResourceFeed } from '../src/core/resourceFeedProtocol.ts';

const remoteItem = {
  rank: 1,
  movie_id: `movie:${'a'.repeat(64)}`,
  source_id: 'media-release',
  source_item_key: `movie:${'a'.repeat(64)}`,
  detail_url: `https://media.magnetgoogo.com/v1/objects/detail/${'b'.repeat(64)}.json`,
  listing_title: 'Incremental Cache Test',
  content_kind: 'movie',
  series_title: null,
  season_number: null,
  episode_number: null,
  episode_label: null,
  update_status: null,
  title: 'Incremental Cache Test',
  original_title: null,
  year: 2026,
  update_date: null,
  release_date: null,
  duration_minutes: null,
  countries: ['CN'],
  genres: ['Test'],
  languages: [],
  directors: [],
  actors: [],
  imdb_id: null,
  imdb_rating: null,
  imdb_rating_text: null,
  douban_rating: null,
  douban_rating_text: null,
  douban_url: null,
  cover_source_url: null,
  cover_asset_path: null,
  cover_width: null,
  cover_height: null,
  synopsis: null,
  recommended: false,
  highlight_labels: [],
  quality_tags: ['HD'],
  resources: [],
  resource_count_hint: 4,
  remote_cover_url: `https://media.magnetgoogo.com/v1/covers/${'c'.repeat(64)}.jpg`,
  remote_endpoint: 'https://media.magnetgoogo.com',
  remote_release_id: '20260729T000000Z-cache-test',
  remote_detail_path: `/v1/objects/detail/${'b'.repeat(64)}.json`,
  remote_detail_hash: 'b'.repeat(64),
  remote_detail_size: 2048,
};

const remoteFeed = {
  schema_version: 'media-app-feed/1',
  source_id: 'media-release',
  content_kind: 'movie',
  generated_at: '2026-07-29T00:00:00Z',
  snapshot_captured_at: '2026-07-29T00:00:00Z',
  items: [remoteItem],
  summary: {
    record_count: 1,
    target_count: 1,
    recommended_count: 0,
    resource_count: 4,
    missing_urls: [],
    snapshot_http_requests: 0,
    detail_http_requests: 0,
    database_movie_count: 1,
    cover_count: 1,
    offline_ready: true,
  },
};

const parsed = parseResourceFeed(remoteFeed, {
  requireOfflineCover: false,
  allowResourceCountHints: true,
});
assert.equal(parsed.items[0].resource_count_hint, 4);
assert.equal(parsed.items[0].remote_release_id, remoteItem.remote_release_id);
assert.equal(parsed.items[0].remote_detail_path, remoteItem.remote_detail_path);
assert.equal(parsed.items[0].remote_detail_hash, remoteItem.remote_detail_hash);
assert.equal(parsed.items[0].remote_detail_size, remoteItem.remote_detail_size);
assert.equal(parsed.items[0].remote_endpoint, remoteItem.remote_endpoint);
assert.throws(() => parseResourceFeed(remoteFeed), (error) => error?.code === 'OFFLINE_COVER_REQUIRED');

const enqueue = createAsyncSerialQueue();
let activeTasks = 0;
let maximumActiveTasks = 0;
const queueOrder = [];
const queuedTask = (name, delayMs, shouldFail = false) => enqueue(async () => {
  activeTasks += 1;
  maximumActiveTasks = Math.max(maximumActiveTasks, activeTasks);
  queueOrder.push(`${name}:start`);
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  queueOrder.push(`${name}:end`);
  activeTasks -= 1;
  if (shouldFail) throw new Error(`${name}_failed`);
  return name;
});
const queueResults = await Promise.allSettled([
  queuedTask('movie', 20),
  queuedTask('series', 1),
  queuedTask('failed', 1, true),
  queuedTask('after_failure', 1),
]);
assert.equal(maximumActiveTasks, 1);
assert.deepEqual(queueOrder, [
  'movie:start', 'movie:end',
  'series:start', 'series:end',
  'failed:start', 'failed:end',
  'after_failure:start', 'after_failure:end',
]);
assert.deepEqual(queueResults.map((result) => result.status), ['fulfilled', 'fulfilled', 'rejected', 'fulfilled']);

const root = process.cwd();
const cacheSource = fs.readFileSync(path.join(root, 'src/core/mediaReleaseCache.ts'), 'utf8');
const legacySource = fs.readFileSync(path.join(root, 'src/core/mediaReleaseLegacyMigration.ts'), 'utf8');
const clientSource = fs.readFileSync(path.join(root, 'src/core/mediaReleaseClient.ts'), 'utf8');
const detailScreen = fs.readFileSync(path.join(root, 'app/movie/[movieId].tsx'), 'utf8');
const sourceStore = fs.readFileSync(path.join(root, 'src/core/secureSourceStore.ts'), 'utf8');
const sourceCrypto = fs.readFileSync(path.join(root, 'src/core/crypto.ts'), 'utf8');

assert.match(cacheSource, /media-release-cache-v2/);
assert.match(cacheSource, /new Directory\(CACHE_ROOT, 'feeds'\)/);
assert.match(cacheSource, /new Directory\(CACHE_ROOT, 'catalogs'\)/);
assert.match(cacheSource, /new Directory\(CACHE_ROOT, 'details'\)/);
assert.match(cacheSource, /media-app-catalog-cache\/2/);
assert.match(cacheSource, /cachedMediaCatalog/);
assert.match(cacheSource, /saveMediaCatalog/);
assert.match(cacheSource, /payload_base64/);
assert.match(cacheSource, /media-app-detail-cache\/2/);
assert.match(cacheSource, /envelope\.detail_hash !== currentItem\.remote_detail_hash/);
assert.match(cacheSource, /writeDetailEnvelope/);
assert.match(cacheSource, /const enqueueMediaFeedSave = createAsyncSerialQueue\(\)/);
assert.match(cacheSource, /return enqueueMediaFeedSave\(\(\) => saveMediaFeedsUnlocked/);
assert.match(cacheSource, /const targetFile = \(\) => new File\(directory, name\)/);
assert.match(cacheSource, /targetFile\(\)\.move\(backupFile\(\)\)/);
assert.match(cacheSource, /temporaryFile\(\)\.move\(targetFile\(\)\)/);
assert.match(cacheSource, /backupFile\(\)\.move\(targetFile\(\)\)/);
assert.doesNotMatch(cacheSource, /const target = new File\(directory, name\)[\s\S]*target\.move\(backup\)[\s\S]*temporary\.move\(target\)/);
assert.doesNotMatch(cacheSource, /CryptoJS|SecureStore|CACHE_EXPIRY|72 \* 60 \* 60/);
assert.match(legacySource, /CryptoJS\.AES/);
assert.match(legacySource, /deleteLegacyMediaCache/);
assert.match(clientSource, /manifest_refresh_skipped: true/);
assert.match(clientSource, /feed_unchanged/);
assert.match(clientSource, /feed_offline_cache/);
assert.match(clientSource, /incremental_network_bytes/);
assert.match(clientSource, /catalog_cache_hits/);
assert.match(clientSource, /catalog_downloads/);
assert.match(clientSource, /fetchCatalogObject/);
assert.match(clientSource, /detailSyncs/);
assert.match(clientSource, /cachedMediaDetail\(item\)/);
assert.match(detailScreen, /loadMediaCardById/);
assert.match(detailScreen, /setMovie\(card\)/);
assert.match(detailScreen, /hydrateMediaItem\(card\)/);
assert.match(sourceStore, /encPayload/);
assert.match(sourceStore, /decryptSources/);
assert.match(sourceCrypto, /CryptoJS\.AES/);
assert.match(sourceCrypto, /HmacSHA256/);

console.log(JSON.stringify({
  status: 'PASS',
  media_cache_encrypted: false,
  search_source_encryption_retained: true,
  feed_shards: true,
  catalog_hash_shards: true,
  per_media_detail_shards: true,
  long_term_hash_reuse: true,
  remote_references_preserved: true,
  detail_manifest_refresh_skipped: true,
  unchanged_feed_uses_pointer_only: true,
  offline_feed_is_retained: true,
  immediate_card_render: true,
  feed_index_commit_serialized: maximumActiveTasks === 1,
}));
