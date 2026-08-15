import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import nacl from 'tweetnacl';

const repoRoot = path.resolve(process.cwd(), '..');
const releaseId = '20260726T000000Z-b8c702d5';
const releaseRoot = path.join(
  repoRoot,
  'data/resource_index/media_releases_m1_final/staging/releases',
  releaseId,
);
const pointerPath = path.join(
  repoRoot,
  'data/resource_index/media_releases_m1_final/staging/pointers',
  `00000000000000000004-${releaseId}.json`,
);
const publicKey = Buffer.from('94eLTKi0Gz1RIQEssMSHrk1ND5WRjdIWzQqjAhrsCb4=', 'base64');

function canonical(value) {
  if (value === null || ['boolean', 'number', 'string'].includes(typeof value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
}

function verifySigned(document) {
  const unsigned = { ...document };
  delete unsigned.signature;
  return nacl.sign.detached.verify(
    Buffer.from(canonical(unsigned), 'utf8'),
    Buffer.from(document.signature, 'base64'),
    publicKey,
  );
}

function bytes(relativePath) {
  return fs.readFileSync(path.join(releaseRoot, relativePath.replace(/^\//, '')));
}

const pointer = JSON.parse(fs.readFileSync(pointerPath, 'utf8'));
assert.equal(pointer.schema_version, 'media-current/1');
assert.equal(pointer.pointer_revision, 4);
assert.equal(pointer.release_id, releaseId);
assert.equal(verifySigned(pointer), true);

const tampered = { ...pointer, pointer_revision: 5 };
assert.equal(verifySigned(tampered), false);

const manifestBytes = bytes(pointer.manifest_path);
assert.equal(crypto.createHash('sha256').update(manifestBytes).digest('hex'), pointer.manifest_sha256);
const manifest = JSON.parse(manifestBytes);
assert.equal(verifySigned(manifest), true);
assert.equal(manifest.release_id, releaseId);
assert.equal(manifest.counts.movie, 100);
assert.equal(manifest.counts.series, 100);

const catalogRefs = [];
for (const channel of Object.values(manifest.channels)) {
  if (channel.featured) catalogRefs.push(channel.featured);
  if (channel.updating) catalogRefs.push(channel.updating);
  catalogRefs.push(...channel.latest_pages);
}
const uniqueCatalogRefs = [...new Map(catalogRefs.map((ref) => [ref.hash, ref])).values()];
assert.equal(uniqueCatalogRefs.length, 14);
const cards = new Map();
for (const ref of uniqueCatalogRefs) {
  const payload = bytes(ref.path);
  assert.equal(payload.length, ref.size);
  assert.equal(crypto.createHash('sha256').update(payload).digest('hex'), ref.hash);
  const catalog = JSON.parse(payload);
  assert.equal(catalog.schema_version, 'media-catalog/1');
  assert.equal(catalog.count, catalog.items.length);
  for (const item of catalog.items) cards.set(item.media_id, item);
}
assert.equal(cards.size, 200);
const catalogRatingCounts = {
  imdb: [...cards.values()].filter((item) => item.imdb_rating != null).length,
  douban: [...cards.values()].filter((item) => item.douban_rating != null).length,
  rotten_tomatoes: [...cards.values()].filter((item) => item.rotten_tomatoes_rating != null).length,
  bangumi: [...cards.values()].filter((item) => item.bangumi_rating != null).length,
};
assert.ok(catalogRatingCounts.imdb > 0);
assert.ok(catalogRatingCounts.douban > 0);
assert.ok(catalogRatingCounts.rotten_tomatoes > 0);
assert.ok(catalogRatingCounts.bangumi > 0);

let resourceItems = 0;
const detailRatingCounts = { rotten_tomatoes: 0, bangumi: 0 };
for (const card of cards.values()) {
  const detailBytes = bytes(card.detail_object.path);
  assert.equal(detailBytes.length, card.detail_object.size);
  assert.equal(crypto.createHash('sha256').update(detailBytes).digest('hex'), card.detail_object.hash);
  const detail = JSON.parse(detailBytes);
  assert.equal(detail.schema_version, 'media-detail/1');
  assert.equal(detail.media_id, card.media_id);
  assert.equal(detail.resource_object.encrypted, false);
  if (detail.rotten_tomatoes_rating != null) detailRatingCounts.rotten_tomatoes += 1;
  if (detail.bangumi_rating != null) detailRatingCounts.bangumi += 1;
  const resourceBytes = bytes(detail.resource_object.path);
  assert.equal(resourceBytes.length, detail.resource_object.size);
  assert.equal(crypto.createHash('sha256').update(resourceBytes).digest('hex'), detail.resource_object.hash);
  const resources = JSON.parse(resourceBytes);
  assert.equal(resources.schema_version, 'media-resources/1');
  assert.equal(resources.media_id, card.media_id);
  resourceItems += resources.items.length;
}
assert.equal(resourceItems, 1682);
assert.ok(detailRatingCounts.rotten_tomatoes > 0);
assert.ok(detailRatingCounts.bangumi > 0);

const protocolSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseProtocol.ts'), 'utf8');
const clientSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseClient.ts'), 'utf8');
const cacheSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseCache.ts'), 'utf8');
const legacyMigrationSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseLegacyMigration.ts'), 'utf8');
assert.match(protocolSource, /tweetnacl/);
assert.match(protocolSource, /94eLTKi0Gz1RIQEssMSHrk1ND5WRjdIWzQqjAhrsCb4=/);
assert.match(clientSource, /https:\/\/media\.magnetgoogo\.com/);
assert.match(clientSource, /https:\/\/api\.naoshiquan\.com\/media/);
assert.doesNotMatch(clientSource, /https:\/\/cn\.magnetgoogo\.com\/media/);
assert.match(clientSource, /CURRENT_TIMEOUT_MS = 10_000/);
assert.match(clientSource, /CURRENT_MAX_ATTEMPTS = 2/);
assert.match(clientSource, /MEDIA_CURRENT_TRANSIENT_RETRY/);
assert.match(clientSource, /message\.startsWith\('HTTP_5'\)/);
assert.match(clientSource, /pointer_revision/);
assert.match(clientSource, /manifest_refresh_skipped: true/);
assert.match(clientSource, /detailSyncs/);
assert.match(cacheSource, /media-release-cache-v2/);
assert.match(cacheSource, /media-app-detail-cache\/2/);
assert.match(cacheSource, /detail_hash/);
assert.match(cacheSource, /writeDetailEnvelope/);
assert.doesNotMatch(cacheSource, /CryptoJS|SecureStore|CACHE_EXPIRY/);
assert.match(legacyMigrationSource, /CryptoJS\.AES/);
assert.match(legacyMigrationSource, /HmacSHA256/);

const endpointChecks = [];
const expectedLivePointerHash = process.env.MEDIA_EXPECTED_POINTER_SHA256 || null;
const expectedLiveRevision = process.env.MEDIA_EXPECTED_POINTER_REVISION
  ? Number(process.env.MEDIA_EXPECTED_POINTER_REVISION)
  : null;
const minimumLiveRevision = Number(process.env.MEDIA_MIN_POINTER_REVISION || 4);
const expectedMovieCount = process.env.MEDIA_EXPECTED_MOVIE_COUNT
  ? Number(process.env.MEDIA_EXPECTED_MOVIE_COUNT)
  : null;
const expectedSeriesCount = process.env.MEDIA_EXPECTED_SERIES_COUNT
  ? Number(process.env.MEDIA_EXPECTED_SERIES_COUNT)
  : null;
const expectedResourceCount = process.env.MEDIA_EXPECTED_RESOURCE_COUNT
  ? Number(process.env.MEDIA_EXPECTED_RESOURCE_COUNT)
  : null;
let acceptedPointerHash = null;
let acceptedPointerBytes = null;

const liveEndpoints = (process.env.MEDIA_TEST_ENDPOINTS || 'https://media.magnetgoogo.com,https://api.naoshiquan.com/media')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);

for (const base of liveEndpoints) {
  const currentResponse = await fetch(`${base}/v1/current.json`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  assert.equal(currentResponse.status, 200, `${base} current status`);
  const currentBytes = Buffer.from(await currentResponse.arrayBuffer());
  const currentHash = crypto.createHash('sha256').update(currentBytes).digest('hex');
  if (acceptedPointerBytes === null) {
    acceptedPointerBytes = currentBytes;
    acceptedPointerHash = currentHash;
  } else {
    assert.deepEqual(currentBytes, acceptedPointerBytes, `${base} current bytes differ from peer endpoint`);
  }
  if (expectedLivePointerHash) assert.equal(currentHash, expectedLivePointerHash);

  const remotePointer = JSON.parse(currentBytes);
  assert.equal(verifySigned(remotePointer), true);
  assert.equal(remotePointer.schema_version, 'media-current/1');
  assert.ok(remotePointer.pointer_revision >= minimumLiveRevision);
  if (expectedLiveRevision !== null) assert.equal(remotePointer.pointer_revision, expectedLiveRevision);

  const manifestResponse = await fetch(`${base}${remotePointer.manifest_path}`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  assert.equal(manifestResponse.status, 200, `${base} manifest status`);
  const remoteManifestBytes = Buffer.from(await manifestResponse.arrayBuffer());
  assert.equal(crypto.createHash('sha256').update(remoteManifestBytes).digest('hex'), remotePointer.manifest_sha256);
  const remoteManifest = JSON.parse(remoteManifestBytes);
  assert.equal(verifySigned(remoteManifest), true);
  assert.equal(remoteManifest.release_id, remotePointer.release_id);
  assert.ok(remoteManifest.counts.movie > 0);
  assert.ok(remoteManifest.counts.series > 0);
  if (expectedMovieCount !== null) assert.equal(remoteManifest.counts.movie, expectedMovieCount);
  if (expectedSeriesCount !== null) assert.equal(remoteManifest.counts.series, expectedSeriesCount);
  if (expectedResourceCount !== null) assert.equal(remoteManifest.counts.resources, expectedResourceCount);

  const remoteCatalogRefs = [];
  for (const channel of Object.values(remoteManifest.channels)) {
    if (channel.featured) remoteCatalogRefs.push(channel.featured);
    if (channel.updating) remoteCatalogRefs.push(channel.updating);
    remoteCatalogRefs.push(...channel.latest_pages);
  }
  const remoteUniqueCatalogRefs = [
    ...new Map(remoteCatalogRefs.map((ref) => [ref.hash, ref])).values(),
  ];
  assert.equal(remoteUniqueCatalogRefs.length, remoteManifest.counts.catalog_objects);
  const sampleCatalogRef = remoteUniqueCatalogRefs[0];
  const catalogResponse = await fetch(`${base}${sampleCatalogRef.path}`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  assert.equal(catalogResponse.status, 200, `${base}${sampleCatalogRef.path}`);
  const catalogPayload = Buffer.from(await catalogResponse.arrayBuffer());
  assert.equal(catalogPayload.length, sampleCatalogRef.size);
  assert.equal(crypto.createHash('sha256').update(catalogPayload).digest('hex'), sampleCatalogRef.hash);
  const remoteCatalog = JSON.parse(catalogPayload);
  assert.ok(remoteCatalog.items.length > 0);
  const sampleCard = remoteCatalog.items[0];

  for (const ref of [sampleCard.cover, sampleCard.detail_object]) {
    const response = await fetch(`${base}${ref.path}`, {
      headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
      signal: AbortSignal.timeout(20_000),
    });
    assert.equal(response.status, 200, `${base}${ref.path}`);
    const payload = Buffer.from(await response.arrayBuffer());
    assert.equal(payload.length, ref.size);
    assert.equal(crypto.createHash('sha256').update(payload).digest('hex'), ref.hash);
  }
  const detailResponse = await fetch(`${base}${sampleCard.detail_object.path}`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  const remoteDetail = JSON.parse(Buffer.from(await detailResponse.arrayBuffer()));
  const resourceResponse = await fetch(`${base}${remoteDetail.resource_object.path}`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  const resourcePayload = Buffer.from(await resourceResponse.arrayBuffer());
  assert.equal(resourcePayload.length, remoteDetail.resource_object.size);
  assert.equal(crypto.createHash('sha256').update(resourcePayload).digest('hex'), remoteDetail.resource_object.hash);
  endpointChecks.push({
    base,
    pointer_revision: remotePointer.pointer_revision,
    release_id: remotePointer.release_id,
    pointer_sha256: currentHash,
    movie_count: remoteManifest.counts.movie,
    series_count: remoteManifest.counts.series,
    resource_count: remoteManifest.counts.resources,
    live_chain: true,
  });
}

console.log(JSON.stringify({
  status: 'PASS',
  local_fixture_pointer_revision: pointer.pointer_revision,
  local_fixture_release_id: releaseId,
  local_fixture_catalog_objects: uniqueCatalogRefs.length,
  local_fixture_media_cards: cards.size,
  local_fixture_resource_items: resourceItems,
  local_fixture_catalog_ratings: catalogRatingCounts,
  local_fixture_detail_ratings: detailRatingCounts,
  live_pointer_sha256: acceptedPointerHash,
  signature_tamper_rejected: true,
  endpoints: endpointChecks,
}));
