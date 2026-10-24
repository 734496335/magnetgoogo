import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {
  parseCatalog,
  parseCurrentPointer,
  parseDetail,
  parseManifest,
  parseResources,
} from '../src/core/mediaReleaseProtocol.ts';
import { resourceDisplayTitle } from '../src/core/mediaResourceTitle.ts';

const endpoints = (process.env.MEDIA_TEST_ENDPOINTS || 'https://media.magnetgoogo.com,https://cn.magnetgoogo.com/media')
  .split(',')
  .map((value) => value.trim().replace(/\/$/, ''))
  .filter(Boolean);
const concurrency = Math.max(1, Number(process.env.MEDIA_FULL_COMPAT_CONCURRENCY || 12));
const expectedRevision = process.env.MEDIA_EXPECTED_POINTER_REVISION
  ? Number(process.env.MEDIA_EXPECTED_POINTER_REVISION)
  : null;
const expectedMovieCount = process.env.MEDIA_EXPECTED_MOVIE_COUNT
  ? Number(process.env.MEDIA_EXPECTED_MOVIE_COUNT)
  : null;
const expectedSeriesCount = process.env.MEDIA_EXPECTED_SERIES_COUNT
  ? Number(process.env.MEDIA_EXPECTED_SERIES_COUNT)
  : null;
const expectedResourceCount = process.env.MEDIA_EXPECTED_RESOURCE_COUNT
  ? Number(process.env.MEDIA_EXPECTED_RESOURCE_COUNT)
  : null;

assert.ok(endpoints.length >= 2, 'at least two media endpoints are required');

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

async function fetchBytes(url) {
  let lastError = null;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: { 'user-agent': 'MagnetGoogo-App-Full-Compat/1' },
        signal: AbortSignal.timeout(20_000),
      });
      assert.equal(response.status, 200, `${url} status`);
      return Buffer.from(await response.arrayBuffer());
    } catch (error) {
      lastError = error;
      if (attempt === 2) throw error;
    }
  }
  throw lastError;
}

async function fetchMirrored(relativePath) {
  const values = await Promise.all(endpoints.map((base) => fetchBytes(`${base}${relativePath}`)));
  for (let index = 1; index < values.length; index += 1) {
    assert.deepEqual(values[index], values[0], `${relativePath} differs across endpoints`);
  }
  return values[0];
}

function assertRef(bytes, ref, label) {
  assert.equal(bytes.length, ref.size, `${label} size mismatch: ${ref.path}`);
  assert.equal(sha256(bytes), ref.hash, `${label} hash mismatch: ${ref.path}`);
}

async function parallelMap(values, worker) {
  const results = new Array(values.length);
  let cursor = 0;
  const runners = Array.from({ length: Math.min(concurrency, values.length) }, async () => {
    while (true) {
      const index = cursor;
      cursor += 1;
      if (index >= values.length) return;
      results[index] = await worker(values[index], index);
    }
  });
  await Promise.all(runners);
  return results;
}

const pointerBytes = await fetchMirrored('/v1/current.json');
const pointer = parseCurrentPointer(JSON.parse(pointerBytes.toString('utf8')));
if (expectedRevision !== null) assert.equal(pointer.pointer_revision, expectedRevision);

const manifestBytes = await fetchMirrored(pointer.manifest_path);
assert.equal(sha256(manifestBytes), pointer.manifest_sha256);
const manifest = parseManifest(JSON.parse(manifestBytes.toString('utf8')));
assert.equal(manifest.release_id, pointer.release_id);
if (expectedMovieCount !== null) assert.equal(manifest.counts.movie, expectedMovieCount);
if (expectedSeriesCount !== null) assert.equal(manifest.counts.series, expectedSeriesCount);
if (expectedResourceCount !== null) assert.equal(manifest.counts.resources, expectedResourceCount);

const catalogRefs = [];
for (const channel of Object.values(manifest.channels)) {
  if (channel.featured) catalogRefs.push(channel.featured);
  if (channel.updating) catalogRefs.push(channel.updating);
  catalogRefs.push(...channel.latest_pages);
}
const uniqueCatalogRefs = [...new Map(catalogRefs.map((ref) => [ref.hash, ref])).values()];
assert.equal(uniqueCatalogRefs.length, manifest.counts.catalog_objects);

const catalogs = await parallelMap(uniqueCatalogRefs, async (ref) => {
  const bytes = await fetchMirrored(ref.path);
  assertRef(bytes, ref, 'catalog');
  return parseCatalog(JSON.parse(bytes.toString('utf8')));
});

const cards = new Map();
for (const catalog of catalogs) {
  assert.equal(catalog.count, catalog.items.length);
  for (const card of catalog.items) {
    const previous = cards.get(card.media_id);
    if (previous) assert.deepEqual(card, previous, `catalog card mismatch: ${card.media_id}`);
    else cards.set(card.media_id, card);
  }
}
const cardValues = [...cards.values()];
assert.equal(cardValues.filter((card) => card.content_kind === 'movie').length, manifest.counts.movie);
assert.equal(cardValues.filter((card) => card.content_kind === 'series').length, manifest.counts.series);

const detailRows = await parallelMap(cardValues, async (card) => {
  const bytes = await fetchMirrored(card.detail_object.path);
  assertRef(bytes, card.detail_object, 'detail');
  const detail = parseDetail(JSON.parse(bytes.toString('utf8')));
  assert.equal(detail.media_id, card.media_id);
  assert.equal(detail.content_kind, card.content_kind);
  assert.equal(detail.resource_object.encrypted, false);
  return { card, detail };
});

const coverRefs = [...new Map(cardValues.map((card) => [card.cover.hash, card.cover])).values()];
await parallelMap(coverRefs, async (ref) => {
  const bytes = await fetchMirrored(ref.path);
  assertRef(bytes, ref, 'cover');
  assert.ok(bytes.length > 0, `empty cover: ${ref.path}`);
});

let resourceCount = 0;
let magnetCount = 0;
let seriesResourceCount = 0;
await parallelMap(detailRows, async ({ card, detail }) => {
  const ref = detail.resource_object;
  const bytes = await fetchMirrored(ref.path);
  assertRef(bytes, ref, 'resources');
  const resources = parseResources(JSON.parse(bytes.toString('utf8')));
  assert.equal(resources.media_id, card.media_id);
  assert.equal(resources.items.length, card.resource_count);
  for (const resource of resources.items) {
    resourceCount += 1;
    assert.equal(resource.resource_type, 'magnet', `${card.media_id} non-magnet resource`);
    assert.match(resource.url, /^magnet:\?/, `${card.media_id} magnet URL`);
    assert.match(resource.info_hash ?? '', /^[0-9a-f]{40}$/i, `${card.media_id} info_hash`);
    magnetCount += 1;
    if (card.content_kind === 'series') {
      seriesResourceCount += 1;
      assert.ok(resourceDisplayTitle(resource, card.season_number ?? undefined).trim(), `${card.media_id} empty display title`);
    }
  }
});

assert.equal(resourceCount, manifest.counts.resources);
assert.equal(magnetCount, resourceCount);

const audit = {
  status: 'PASS',
  app_version_contract: '0.2.7',
  pointer_revision: pointer.pointer_revision,
  release_id: pointer.release_id,
  pointer_sha256: sha256(pointerBytes),
  manifest_sha256: pointer.manifest_sha256,
  endpoints,
  catalog_objects: uniqueCatalogRefs.length,
  cards: cardValues.length,
  movie_count: manifest.counts.movie,
  series_count: manifest.counts.series,
  resource_count: resourceCount,
  magnet_count: magnetCount,
  series_resource_count: seriesResourceCount,
  cover_objects: coverRefs.length,
  mirrored_all_objects: true,
  all_catalogs_parsed: true,
  all_details_parsed: true,
  all_resources_parsed: true,
  series_resource_titles_renderable: true,
};

const auditPath = process.env.MEDIA_FULL_COMPAT_REPORT;
if (auditPath) {
  fs.writeFileSync(path.resolve(auditPath), `${JSON.stringify(audit, null, 2)}\n`, 'utf8');
}
console.log(JSON.stringify(audit));
