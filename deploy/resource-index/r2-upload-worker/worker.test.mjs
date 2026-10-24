import assert from 'node:assert/strict';
import test from 'node:test';

import worker, { maxObjectBytesFor, validateCurrentCandidate } from './worker.mjs';
import { createHash } from 'node:crypto';

const TOKEN = 't'.repeat(48);
const MANIFEST_KEY = 'v1/releases/20261024T000000Z-1234abcd/manifest.json';

function environment() {
  const objects = new Map();
  return {
    objects,
    UPLOAD_TOKEN: TOKEN,
    PUBLISH_MODE: 'production-auto',
    MEDIA_BUCKET: {
      async list() { return { objects: [] }; },
      async head(key) { return objects.get(key) || null; },
      async get(key) { return objects.get(key) || null; },
      async put(key, payload, options) {
        assert.equal(options.onlyIf.etagDoesNotMatch, '*');
        assert.equal(options.sha256, createHash('sha256').update(Buffer.from(payload)).digest('hex'));
        const item = {
          size: payload.byteLength, customMetadata: options.customMetadata, etag: 'test',
          body: Buffer.from(payload), httpEtag: '"test"',
          writeHttpMetadata(headers) { headers.set('content-type', options.httpMetadata.contentType); },
        };
        objects.set(key, item);
        return item;
      },
    },
  };
}

function uploadRequest(body, overrides = {}) {
  return new Request('https://bridge.example/object?key=' + encodeURIComponent(overrides.key || MANIFEST_KEY), {
    method: 'PUT',
    headers: {
      authorization: 'Bearer ' + TOKEN,
      'content-type': 'application/json; charset=utf-8',
      'x-media-object-kind': 'manifest',
      'x-media-size': String(body.length),
      'x-media-sha256': createHash('sha256').update(body).digest('hex'),
      ...overrides.headers,
    },
    body,
  });
}

const ONE_MIB = 1024 * 1024;
const EIGHT_MIB = 8 * 1024 * 1024;

test('allows a release manifest up to eight MiB', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/releases/20260729T000000Z-b07630f3/manifest.json',
      'manifest',
      'application/json; charset=utf-8',
    ),
    EIGHT_MIB,
  );
});

test('keeps normal objects at one MiB', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/objects/detail/example.json',
      'detail',
      'application/json; charset=utf-8',
    ),
    ONE_MIB,
  );
});

test('does not grant the manifest limit to a disguised object kind', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/releases/20260729T000000Z-b07630f3/manifest.json',
      'detail',
      'application/json; charset=utf-8',
    ),
    ONE_MIB,
  );
});

test('does not grant the manifest limit to a disguised path', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/objects/detail/manifest.json',
      'manifest',
      'application/json; charset=utf-8',
    ),
    ONE_MIB,
  );
});

test('accepts a monotonic signed pointer shape for promotion', () => {
  const candidate = {
    schema_version: 'media-current/1',
    release_id: '20260730T000000Z-1234abcd',
    pointer_revision: 7,
    manifest_path: '/v1/releases/20260730T000000Z-1234abcd/manifest.json',
    manifest_sha256: 'a'.repeat(64),
    min_app_version: '0.2.1',
  };
  const existing = {
    ...candidate,
    release_id: '20260729T000000Z-8765dcba',
    pointer_revision: 6,
    manifest_path: '/v1/releases/20260729T000000Z-8765dcba/manifest.json',
    manifest_sha256: 'b'.repeat(64),
  };
  assert.equal(validateCurrentCandidate(candidate, existing), null);
});

test('rejects rollback and same-revision conflicts', () => {
  const existing = {
    schema_version: 'media-current/1',
    release_id: '20260730T000000Z-1234abcd',
    pointer_revision: 7,
    manifest_path: '/v1/releases/20260730T000000Z-1234abcd/manifest.json',
    manifest_sha256: 'a'.repeat(64),
    min_app_version: '0.2.1',
  };
  assert.match(validateCurrentCandidate({ ...existing, pointer_revision: 6 }, existing), /rollback/);
  assert.match(
    validateCurrentCandidate({ ...existing, release_id: '20260730T010000Z-deadbeef', manifest_path: '/v1/releases/20260730T010000Z-deadbeef/manifest.json' }, existing),
    /same revision/,
  );
});

test('does not grant the manifest limit to a non-JSON payload', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/releases/20260729T000000Z-b07630f3/manifest.json',
      'manifest',
      'application/octet-stream',
    ),
    ONE_MIB,
  );
});

test('health advertises the deployed upload limits', async () => {
  const response = await worker.fetch(new Request('https://bridge.example/health', {
    headers: { authorization: 'Bearer ' + TOKEN },
  }), environment());
  const health = await response.json();
  assert.equal(health.maxObjectBytes, ONE_MIB);
  assert.equal(health.maxManifestBytes, EIGHT_MIB);
  assert.equal(health.currentPromotion, true);
});

for (const size of [2 * ONE_MIB + 1, EIGHT_MIB]) {
  test('PUT verifies and idempotently reuses a manifest of ' + size + ' bytes', async () => {
    const env = environment();
    const body = Buffer.alloc(size, 0x20);
    body[0] = 0x7b;
    body[size - 1] = 0x7d;
    const response = await worker.fetch(uploadRequest(body), env);
    assert.equal(response.status, 201);
    const stored = env.objects.get(MANIFEST_KEY);
    assert.equal(stored.size, size);
    assert.deepEqual(stored.body, body);
    const second = await worker.fetch(uploadRequest(body), env);
    assert.equal(second.status, 200);
    assert.equal((await second.json()).reused, true);
    assert.equal(env.objects.size, 1);
  });
}

test('PUT rejects a manifest above eight MiB before writing', async () => {
  const env = environment();
  const response = await worker.fetch(uploadRequest(Buffer.alloc(0), {
    headers: { 'x-media-size': String(EIGHT_MIB + 1) },
  }), env);
  assert.equal(response.status, 400);
  assert.equal(env.objects.size, 0);
});

test('PUT rejects actual bytes that differ from the declared size or checksum', async () => {
  for (const headers of [{ 'x-media-size': '2' }, { 'x-media-sha256': '0'.repeat(64) }]) {
    const env = environment();
    const response = await worker.fetch(uploadRequest(Buffer.alloc(2 * ONE_MIB + 1), { headers }), env);
    assert.equal(response.status, 400);
    assert.equal(env.objects.size, 0);
  }
});

test('PUT keeps ordinary and disguised objects at one MiB', async () => {
  for (const overrides of [
    { key: 'v1/objects/detail/example.json' },
    { headers: { 'x-media-object-kind': 'detail' } },
    { headers: { 'content-type': 'application/octet-stream' } },
  ]) {
    const env = environment();
    const response = await worker.fetch(uploadRequest(Buffer.alloc(ONE_MIB + 1), overrides), env);
    assert.equal(response.status, 400);
    assert.equal(env.objects.size, 0);
  }
});

test('PUT preserves authentication and immutable conflict checks', async () => {
  const env = environment();
  const denied = await worker.fetch(uploadRequest(Buffer.from('{}'), {
    headers: { authorization: 'Bearer wrong' },
  }), env);
  assert.equal(denied.status, 401);
  assert.equal(env.objects.size, 0);
  assert.equal((await worker.fetch(uploadRequest(Buffer.from('{}')), env)).status, 201);
  const conflict = await worker.fetch(uploadRequest(Buffer.from('{"changed":true}')), env);
  assert.equal(conflict.status, 409);
  assert.equal(env.objects.get(MANIFEST_KEY).body.toString(), '{}');
});
