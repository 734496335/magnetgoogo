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

let resourceItems = 0;
for (const card of cards.values()) {
  const detailBytes = bytes(card.detail_object.path);
  assert.equal(detailBytes.length, card.detail_object.size);
  assert.equal(crypto.createHash('sha256').update(detailBytes).digest('hex'), card.detail_object.hash);
  const detail = JSON.parse(detailBytes);
  assert.equal(detail.schema_version, 'media-detail/1');
  assert.equal(detail.media_id, card.media_id);
  assert.equal(detail.resource_object.encrypted, false);
  const resourceBytes = bytes(detail.resource_object.path);
  assert.equal(resourceBytes.length, detail.resource_object.size);
  assert.equal(crypto.createHash('sha256').update(resourceBytes).digest('hex'), detail.resource_object.hash);
  const resources = JSON.parse(resourceBytes);
  assert.equal(resources.schema_version, 'media-resources/1');
  assert.equal(resources.media_id, card.media_id);
  resourceItems += resources.items.length;
}
assert.equal(resourceItems, 1682);

const protocolSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseProtocol.ts'), 'utf8');
const clientSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseClient.ts'), 'utf8');
const cacheSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseCache.ts'), 'utf8');
assert.match(protocolSource, /tweetnacl/);
assert.match(protocolSource, /94eLTKi0Gz1RIQEssMSHrk1ND5WRjdIWzQqjAhrsCb4=/);
assert.match(clientSource, /https:\/\/media\.magnetgoogo\.com/);
assert.match(clientSource, /https:\/\/cn\.magnetgoogo\.com\/media/);
assert.match(clientSource, /pointer_revision/);
assert.match(cacheSource, /72 \* 60 \* 60 \* 1000/);
assert.match(cacheSource, /CryptoJS\.AES/);
assert.match(cacheSource, /HmacSHA256/);

const endpointChecks = [];
const pointerHash = crypto.createHash('sha256').update(fs.readFileSync(pointerPath)).digest('hex');
const sampleCatalogRef = uniqueCatalogRefs[0];
const sampleCatalog = JSON.parse(bytes(sampleCatalogRef.path));
const sampleCard = sampleCatalog.items[0];
for (const base of ['https://media.magnetgoogo.com', 'https://cn.magnetgoogo.com/media']) {
  const currentResponse = await fetch(`${base}/v1/current.json`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  assert.equal(currentResponse.status, 200, `${base} current status`);
  const currentBytes = Buffer.from(await currentResponse.arrayBuffer());
  assert.equal(crypto.createHash('sha256').update(currentBytes).digest('hex'), pointerHash);
  const remotePointer = JSON.parse(currentBytes);
  assert.equal(verifySigned(remotePointer), true);
  assert.equal(remotePointer.pointer_revision, 4);

  const manifestResponse = await fetch(`${base}${remotePointer.manifest_path}`, {
    headers: { 'user-agent': 'MagnetGoogo-App-Protocol-Test/1' },
    signal: AbortSignal.timeout(20_000),
  });
  assert.equal(manifestResponse.status, 200, `${base} manifest status`);
  const remoteManifestBytes = Buffer.from(await manifestResponse.arrayBuffer());
  assert.equal(crypto.createHash('sha256').update(remoteManifestBytes).digest('hex'), remotePointer.manifest_sha256);
  assert.equal(verifySigned(JSON.parse(remoteManifestBytes)), true);

  const sampleRefs = [sampleCatalogRef, sampleCard.cover, sampleCard.detail_object];
  for (const ref of sampleRefs) {
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
  endpointChecks.push({ base, pointer_revision: remotePointer.pointer_revision, live_chain: true });
}

console.log(JSON.stringify({
  status: 'PASS',
  pointer_revision: pointer.pointer_revision,
  release_id: releaseId,
  catalog_objects: uniqueCatalogRefs.length,
  media_cards: cards.size,
  resource_items: resourceItems,
  signature_tamper_rejected: true,
  endpoints: endpointChecks,
}));
