import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
assert.match(source, /ANALYTICS_PAGE_SIZE_MAX = 100/);
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const { default: worker } = await import(moduleUrl);

class MemoryR2 {
  constructor() {
    this.objects = new Map();
    this.putCalls = 0;
    this.getCalls = 0;
    this.listCalls = 0;
    this.failGetOnce = new Set();
  }

  async put(key, body, options = {}) {
    this.putCalls += 1;
    this.objects.set(key, { key, body: String(body), options });
  }

  async get(key) {
    this.getCalls += 1;
    if (this.failGetOnce.delete(key)) throw new Error('synthetic_r2_get_failure');
    const item = this.objects.get(key);
    if (!item) return null;
    return {
      body: item.body,
      size: new TextEncoder().encode(item.body).byteLength,
      httpMetadata: item.options?.httpMetadata || {},
      httpEtag: `\"${key}\"`,
      async json() { return JSON.parse(item.body); },
    };
  }

  async list({ prefix = '', cursor, limit = 1000 }) {
    this.listCalls += 1;
    const keys = [...this.objects.keys()].filter((key) => key.startsWith(prefix)).sort();
    const start = cursor ? Number(cursor) : 0;
    const slice = keys.slice(start, start + limit);
    const next = start + slice.length;
    return {
      objects: slice.map((key) => ({ key })),
      truncated: next < keys.length,
      cursor: next < keys.length ? String(next) : undefined,
    };
  }
}

const analytics = new MemoryR2();
const releases = new MemoryR2();
await releases.put('v1/current.json', JSON.stringify({ pointer_revision: 16, release_id: 'release-16' }), {
  httpMetadata: { contentType: 'application/json' },
});
await releases.put('v1/releases/release-16/manifest.json', JSON.stringify({ release_id: 'release-16' }), {
  httpMetadata: { contentType: 'application/json' },
});
const env = {
  ANALYTICS: analytics,
  RELEASES: new MemoryR2(),
  MEDIA: releases,
  ADMIN_SECRET: 'test-secret',
};

function eventBody(overrides = {}) {
  return {
    schema_v: 2,
    batch_id: 'b2_stable_batch',
    did: 'install_legacy',
    device_id: 'dv2_0123456789abcdef',
    device_id_kind: 'android_id_hash',
    install_id: 'install_legacy',
    app_v: '0.2.5',
    version_code: '9',
    package_name: 'com.magnetgoogo.app.debug',
    build_type: 'debug',
    distribution: 'direct_apk',
    session_id: 'session_test',
    os: 'android',
    os_v: '13',
    events: [
      { id: 'event_a', e: 'app_start', ts: Date.now() },
      { id: 'event_a', e: 'app_start', ts: Date.now() },
      { id: 'event_b', e: 'copy_magnet', ts: Date.now(), surface: 'search', action: 'single' },
    ],
    ...overrides,
  };
}

async function call(path, init = {}) {
  const request = new Request(`https://example.test${path}`, init);
  return worker.fetch(request, env, {});
}

const first = await call('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(eventBody()),
});
assert.equal(first.status, 200);
const firstJson = await first.json();
assert.equal(firstJson.count, 2, 'duplicate event IDs must be removed before storage');
assert.equal(analytics.objects.size, 1);
const storedKey = [...analytics.objects.keys()][0];
assert.match(storedKey, /events\/\d{4}\/\d{2}\/\d{2}\/dv2_0123456789abcdef\/b2_stable_batch\.json$/);
const stored = JSON.parse(analytics.objects.get(storedKey).body);
assert.equal(stored.device_id, 'dv2_0123456789abcdef');
assert.equal(stored.install_id, 'install_legacy');
assert.equal(stored.build_type, 'debug');
assert.equal(stored.events.length, 2);

const second = await call('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(eventBody()),
});
assert.equal(second.status, 200);
assert.equal(analytics.objects.size, 1, 'same batch ID must overwrite instead of creating a second object');

const legacyPayload = {
  did: 'legacy_device',
  app_v: '0.1.13',
  os: 'android',
  os_v: '12',
  events: [
    { e: 'app_start', ts: Date.now() },
    { e: 'search', ts: Date.now(), q: 'legacy query', n: 3 },
  ],
};
const legacyFirst = await call('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(legacyPayload),
});
assert.equal(legacyFirst.status, 200);
const legacyId = (await legacyFirst.json()).batch_id;
assert.match(legacyId, /^legacy_/);
const legacySecond = await call('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(legacyPayload),
});
assert.equal(legacySecond.status, 200);
assert.equal((await legacySecond.json()).batch_id, legacyId);
assert.equal(analytics.objects.size, 2, 'legacy retries must derive the same deterministic batch key');

const day = storedKey.split('/').slice(1, 4).join('-');
const page = await call(`/api/events?raw=1&day=${day}&limit=40`, {
  headers: { 'X-Admin-Secret': 'test-secret' },
});
assert.equal(page.status, 200);
const pageJson = await page.json();
assert.equal(pageJson.page.complete, true);
assert.equal(pageJson.page.truncated, false);
assert.equal(pageJson.page.returned, 2);
assert.equal(pageJson.summary.devices, 2);
assert.equal(pageJson.summary.totalEvents, 4);
assert.deepEqual(pageJson.summary.eventCounts, { app_start: 2, copy_magnet: 1, search: 1 });
assert.ok(analytics.listCalls <= 1);
assert.ok(analytics.getCalls <= 2);

analytics.failGetOnce.add(storedKey);
const incompletePage = await call(`/api/events?raw=1&day=${day}&limit=100`, {
  headers: { 'X-Admin-Secret': 'test-secret' },
});
assert.equal(incompletePage.status, 503, 'one failed R2 object read must fail the page instead of claiming completeness');
assert.equal((await incompletePage.json()).error, 'analytics_page_object_read_failed');

const unauthorized = await call(`/api/events?raw=1&day=${day}`);
assert.equal(unauthorized.status, 401);

const mediaCurrent = await call('/media/v1/current.json');
assert.equal(mediaCurrent.status, 200);
assert.equal(mediaCurrent.headers.get('Cache-Control'), 'no-store, no-cache, must-revalidate');
assert.equal((await mediaCurrent.json()).pointer_revision, 16);
const mediaManifest = await call('/media/v1/releases/release-16/manifest.json');
assert.equal(mediaManifest.status, 200);
assert.equal(mediaManifest.headers.get('Cache-Control'), 'public, max-age=31536000, immutable');
const mediaHead = await call('/media/v1/current.json', { method: 'HEAD' });
assert.equal(mediaHead.status, 200);
assert.equal(await mediaHead.text(), '');
assert.equal((await call('/media/secret')).status, 400);
assert.equal((await call('/media/v1/releases/missing.json')).status, 404);
assert.equal((await call('/media/v1/current.json', { method: 'POST' })).status, 405);

const oversized = await call('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(eventBody({ events: [{ id: 'huge', e: 'app_start', ts: Date.now(), value: 'x'.repeat(33000) }] })),
});
assert.equal(oversized.status, 400);
assert.equal((await oversized.json()).error, 'payload_too_large');

const oversizedStream = new ReadableStream({
  start(controller) {
    controller.enqueue(new TextEncoder().encode('x'.repeat(20_000)));
    controller.enqueue(new TextEncoder().encode('y'.repeat(20_000)));
    controller.close();
  },
});
const streamedOversized = await call('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: oversizedStream,
  duplex: 'half',
});
assert.equal(streamedOversized.status, 400, 'chunked payloads must be stopped at the byte limit');
assert.equal((await streamedOversized.json()).error, 'payload_too_large');

console.log(JSON.stringify({
  status: 'PASS',
  stored_objects: analytics.objects.size,
  put_calls: analytics.putCalls,
  list_calls: analytics.listCalls,
  get_calls: analytics.getCalls,
  stored_key: storedKey,
}, null, 2));
