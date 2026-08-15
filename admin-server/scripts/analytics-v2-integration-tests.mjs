import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const adminRoot = path.resolve(here, '..');
const serverSource = fs.readFileSync(path.join(adminRoot, 'server.js'), 'utf8');
assert.match(serverSource, /if \(process\.env\.ANALYTICS_ONLY !== '1'\) \{[\s\S]*?try \{[\s\S]*?require\('\.\/broadcast'\)[\s\S]*?catch \(error\)/);

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function json(res, value, status = 200) {
  const body = JSON.stringify(value);
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

const now = Date.now();
const utcDay = new Date(now).toISOString().slice(0, 10);
const eventTs = now - 60_000;
const releaseA = {
  id: 'events/test/release-a.json',
  schema_v: 2,
  batch_id: 'batch-a',
  device_id: 'dv2_user_a',
  install_id: 'install-a1',
  did: 'install-a1',
  app_v: '0.2.5',
  package_name: 'com.magnetgoogo.app',
  build_type: 'release',
  os: 'android',
  os_v: '13',
  country: 'CN',
  city: 'Shanghai',
  receivedAt: new Date(now - 30_000).toISOString(),
  events: [
    { id: 'first-a', e: 'first_open', ts: eventTs, installation_time: eventTs, session_id: 's1' },
    { id: 'start-a', e: 'app_start', ts: eventTs, session_id: 's1' },
    { id: 'submit-a', e: 'search_submitted', ts: eventTs, search_id: 'search-a', session_id: 's1' },
    { id: 'resources-a', e: 'resources_tab_view', ts: eventTs, content_kind: 'movie', session_id: 's1' },
    { id: 'refresh-a', e: 'resource_feed_refresh_result', ts: eventTs, content_kind: 'movie', reason: 'focus', success: 1, changed: 1, release_id: 'release-14', duration_ms: 420, session_id: 's1' },
    { id: 'copy-a', e: 'copy_magnet', ts: eventTs, surface: 'search', action: 'single', session_id: 's1' },
  ],
};
const releaseB = {
  ...releaseA,
  id: 'events/test/release-b.json',
  batch_id: 'batch-b',
  install_id: 'install-a2',
  did: 'install-a2',
  receivedAt: new Date(now - 20_000).toISOString(),
  events: [
    { id: 'copy-a', e: 'copy_magnet', ts: eventTs, surface: 'search', action: 'single', session_id: 's1' },
    { id: 'complete-a', e: 'search_completed', ts: eventTs, search_id: 'search-a', source_sample: [{ s: 'sample-source', o: 1, f: 0, m: 500 }], session_id: 's1' },
    { id: 'refresh-b', e: 'resource_feed_refresh_result', ts: eventTs, content_kind: 'movie', reason: 'foreground', success: 0, changed: 0, error_code: 'MEDIA_AUTO_SYNC_FAILED', session_id: 's1' },
    { id: 'open-a', e: 'open_magnet', ts: eventTs, surface: 'search', action: 'single', session_id: 's1' },
  ],
};
const legacy = {
  id: 'events/test/legacy.json',
  did: 'legacy-user-b',
  app_v: '0.1.13',
  os: 'android',
  os_v: '12',
  country: 'US',
  city: 'Dallas',
  receivedAt: new Date(now - 10_000).toISOString(),
  events: [
    { e: 'app_start', ts: eventTs },
    { e: 'search', ts: eventTs, q: 'legacy query', n: 4 },
  ],
};
const technicalOnlyBatch = {
  id: 'events/test/technical-only.json',
  schema_v: 2,
  batch_id: 'batch-tech',
  device_id: 'dv2_technical_only',
  install_id: 'install-tech',
  did: 'install-tech',
  app_v: '0.2.6',
  package_name: 'com.magnetgoogo.app',
  build_type: 'release',
  os: 'android',
  os_v: '13',
  country: 'CN',
  city: 'Shanghai',
  receivedAt: new Date(now - 15_000).toISOString(),
  events: [
    { id: 'tech-sync', e: 'source_sync_result', ts: eventTs, mode: 'remote', success: 1, source_count: 148 },
  ],
};
const debugBatch = {
  id: 'events/test/debug.json',
  schema_v: 2,
  device_id: 'dv2_debug',
  install_id: 'debug-install',
  did: 'debug-install',
  app_v: '0.2.5',
  package_name: 'com.magnetgoogo.app.debug',
  build_type: 'debug',
  country: 'CN',
  receivedAt: new Date(now).toISOString(),
  events: [{ id: 'debug-start', e: 'app_start', ts: eventTs }],
};

const gatewayPort = await freePort();
const adminPort = await freePort();
const requests = [];
let cursorPageAttempts = 0;
const gateway = http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://127.0.0.1:${gatewayPort}`);
  requests.push(url.search);
  if (req.headers['x-admin-secret'] !== 'test-secret') return json(res, { error: 'unauthorized' }, 401);
  const day = url.searchParams.get('day');
  if (!day) return json(res, { error: 'day_required' }, 400);
  if (day !== utcDay) {
    return json(res, { summary: { batches: 0, devices: 0, totalEvents: 0, eventCounts: {} }, batches: [], page: { day, truncated: false, next_cursor: null, complete: true, returned: 0 } });
  }
  const cursor = url.searchParams.get('cursor');
  if (!cursor) {
    return json(res, {
      summary: { batches: 2 },
      batches: [releaseA, releaseB],
      page: { day, truncated: true, next_cursor: 'page-2', complete: false, returned: 2 },
    });
  }
  assert.equal(cursor, 'page-2');
  cursorPageAttempts++;
  if (cursorPageAttempts === 1) {
    return json(res, { error: 'transient_gateway_failure' }, 503);
  }
  return json(res, {
    summary: { batches: 2 },
    batches: [legacy, technicalOnlyBatch, debugBatch],
    page: { day, truncated: false, next_cursor: null, complete: true, returned: 2 },
  });
});
await new Promise((resolve) => gateway.listen(gatewayPort, '127.0.0.1', resolve));

const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maggoogo-analytics-v2-'));
const child = spawn(process.execPath, ['server.js'], {
  cwd: adminRoot,
  env: {
    ...process.env,
    PORT: String(adminPort),
    CF_GATEWAY: `http://127.0.0.1:${gatewayPort}`,
    ADMIN_SECRET: 'test-secret',
    ANALYTICS_CACHE_DIR: cacheDir,
    ANALYTICS_ONLY: '1',
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let logs = '';
child.stdout.on('data', (chunk) => { logs += chunk.toString(); });
child.stderr.on('data', (chunk) => { logs += chunk.toString(); });

async function waitForAdmin() {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${adminPort}/`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`admin server did not start\n${logs}`);
}

try {
  await waitForAdmin();
  const refresh = await fetch(`http://127.0.0.1:${adminPort}/api/events/refresh`, { method: 'POST' });
  assert.equal(refresh.status, 200, logs);
  const result = await refresh.json();
  assert.equal(result._fetchComplete, true);
  assert.equal(result._fetchPages, 15, '14 UTC days plus one cursor continuation');
  assert.equal(result.summary.timeZone, 'Asia/Shanghai');
  assert.equal(result.summary.devices, 3, 'debug traffic must be excluded while release technical-only devices remain visible in the broad user count');
  assert.equal(result.summary.installs, 4, 'one stable user has two installs plus one legacy install and one technical-only install');
  assert.equal(result.summary.internalBatches, 1);
  assert.equal(result.summary.internalEvents, 1);
  assert.equal(result.summary.totalEvents, 12, 'duplicate event ID must be counted once');
  assert.equal(result.summary.eventCounts.search_submitted, 1);
  assert.equal(result.summary.eventCounts.search_completed, 1);
  assert.equal(result.summary.eventCounts.search, 1);
  assert.equal(result.summary.eventCounts.copy_magnet, 1);
  assert.equal(result.summary.eventCounts.resources_tab_view, 1);
  assert.equal(result.summary.eventCounts.resource_feed_refresh_result, 2);
  assert.equal(result.summary.resourceUsers, 1);
  assert.equal(result.summary.resourceRefreshes, 2);
  assert.equal(result.summary.resourceRefreshSuccess, 1);
  assert.equal(result.summary.resourceRefreshFailures, 1);
  assert.equal(result.summary.resourceRefreshChanged, 1);
  assert.equal(result.summary.resourceRefreshSuccessRate, 50);
  assert.equal(result.summary.resourceRefreshChangedRate, 100);
  assert.equal(result.versionDist['0.2.5'], 1, 'version distribution must count users, not batches');
  assert.equal(result.versionDist['0.2.6'], 1);
  assert.equal(result.cohortRetention.reduce((sum, row) => sum + row.size, 0), 2, 'technical-only devices must not enter retention cohort denominators');
  const daily = result.daily.find((item) => item.day === result.daily.at(-1).day);
  assert.ok(daily);
  assert.equal(daily.devices, 2);
  assert.equal(daily.newDevices, 2);
  assert.equal(daily.searches, 2);
  assert.equal(daily.searchCompletions, 1);
  assert.equal(daily.copies, 1);
  assert.equal(daily.resourceUsers, 1);
  assert.equal(daily.resourceRefreshes, 2);
  assert.equal(daily.resourceRefreshSuccess, 1);
  assert.equal(daily.resourceRefreshChanged, 1);
  assert.equal(daily.resourceRefreshSuccessRate, 50);
  assert.ok(result.sourcePerf.some((item) => item.src === 'sample-source'));
  assert.equal(result.devices.find((item) => item.did.endsWith('user_a'))?.installs, 2);
  assert.equal(cursorPageAttempts, 2, 'one transient cursor-page 503 must be retried exactly once before succeeding');
  assert.ok(requests.some((query) => query.includes('cursor=page-2')));
  assert.ok(requests.some((query) => query.includes('limit=100')), 'admin cursor fetch must use the optimized 100-batch page size');
  assert.ok(fs.existsSync(path.join(cacheDir, 'batches.json')));
  assert.ok(fs.existsSync(path.join(cacheDir, 'analytics.json')));

  console.log(JSON.stringify({
    status: 'PASS',
    fetch_pages: result._fetchPages,
    anonymous_users: result.summary.devices,
    installs: result.summary.installs,
    total_events: result.summary.totalEvents,
    internal_batches_excluded: result.summary.internalBatches,
    daily: {
      devices: daily.devices,
      newDevices: daily.newDevices,
      searches: daily.searches,
      searchCompletions: daily.searchCompletions,
      copies: daily.copies,
      resourceUsers: daily.resourceUsers,
      resourceRefreshes: daily.resourceRefreshes,
      resourceRefreshSuccessRate: daily.resourceRefreshSuccessRate,
    },
  }, null, 2));
} finally {
  if (child.exitCode === null) {
    child.kill('SIGTERM');
    await Promise.race([
      new Promise((resolve) => child.once('exit', resolve)),
      new Promise((resolve) => setTimeout(resolve, 2000)),
    ]);
  }
  await new Promise((resolve) => gateway.close(resolve));
  fs.rmSync(cacheDir, { recursive: true, force: true });
}
