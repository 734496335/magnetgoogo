import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseResourceFeed,
  resourceFeedItemKey,
  ResourceFeedValidationError,
} from '../src/core/resourceFeedProtocol.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const localFeedPath = path.resolve(here, '..', '..', 'data', 'resource_index', 'javbus_latest_100_feed.json');

function sampleItem(rank, code) {
  return {
    rank,
    content_id: `adult_video:${code}`,
    content_code: code,
    title: `Title ${rank}`,
    listing_title: `Listing ${rank}`,
    release_date: '2026-07-01',
    duration_minutes: 90,
    maker_name: 'Maker',
    publisher_name: 'Publisher',
    series_name: null,
    cover_source_url: 'https://example.com/cover.jpg',
    detail_url: `https://example.com/${code}/${rank}`,
    people: [],
    tags: ['tag'],
    resource_count: 2,
    source_first_seen_at: '2026-07-25T00:00:00Z',
    source_last_seen_at: '2026-07-25T00:00:00Z',
  };
}

function sampleFeed(items) {
  return {
    summary: {
      generated_at: '2026-07-25T00:00:00Z',
      source_id: 'fixture',
      record_count: items.length,
      canonical_content_count: items.length,
      content_observation_count: items.length,
      resource_count: items.reduce((sum, item) => sum + item.resource_count, 0),
      resource_observation_count: items.reduce((sum, item) => sum + item.resource_count, 0),
      people_count: 0,
      tag_count: 1,
      records_without_resources: 0,
      missing_urls: [],
      running_runs: 0,
      partial_runs: 0,
    },
    items,
  };
}

const parsed = parseResourceFeed(sampleFeed([sampleItem(1, 'A-001'), sampleItem(2, 'A-001')]));
assert.equal(parsed.items.length, 2);
assert.notEqual(resourceFeedItemKey(parsed.items[0]), resourceFeedItemKey(parsed.items[1]));
console.log('PASS  R1  duplicate content codes retain unique source-observation card keys');

assert.throws(
  () => parseResourceFeed(sampleFeed([sampleItem(2, 'A-001')])),
  (error) => error instanceof ResourceFeedValidationError && error.code === 'RANK_NOT_CONTINUOUS',
);
console.log('PASS  R2  non-continuous ranking is rejected');

const mismatch = sampleFeed([sampleItem(1, 'A-001')]);
mismatch.summary.record_count = 2;
assert.throws(
  () => parseResourceFeed(mismatch),
  (error) => error instanceof ResourceFeedValidationError && error.code === 'COUNT_MISMATCH',
);
console.log('PASS  R3  summary/item count mismatch is rejected');

if (fs.existsSync(localFeedPath)) {
  const local = parseResourceFeed(JSON.parse(fs.readFileSync(localFeedPath, 'utf8')));
  assert.equal(local.items.length, 100);
  assert.equal(local.summary.record_count, 100);
  assert.equal(local.summary.canonical_content_count, 97);
  assert.equal(local.summary.resource_count, 299);
  assert.equal(local.summary.resource_observation_count, 309);
  assert.equal(local.summary.records_without_resources, 0);

  const codeCounts = new Map();
  for (const item of local.items) {
    codeCounts.set(item.content_code, (codeCounts.get(item.content_code) ?? 0) + 1);
  }
  const duplicateObservationCount = [...codeCounts.values()]
    .filter((count) => count > 1)
    .reduce((sum, count) => sum + count - 1, 0);
  assert.equal(duplicateObservationCount, 3);
  assert.equal(new Set(local.items.map(resourceFeedItemKey)).size, 100);
  console.log('PASS  R4  local JavBus feed is 100/97 with 3 duplicate observations and 299 resources');
} else {
  console.log('SKIP  R4  local untracked resource feed is not present');
}

console.log('=== Resource feed tests passed ===');
