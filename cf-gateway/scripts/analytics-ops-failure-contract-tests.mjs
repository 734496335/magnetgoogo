import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const workerSource = fs.readFileSync(path.resolve('src/index.js'), 'utf8');
const { default: worker } = await import(`data:text/javascript;base64,${Buffer.from(workerSource).toString('base64')}`);

function event(id, name = 'app_start', ts = Date.now()) {
  return { id, e: name, ts };
}

async function post(env, ctx, body) {
  return worker.fetch(new Request('https://api.test.local/api/events', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }), env, ctx);
}

// D1 is rebuildable shadow: its failure must never turn a durable R2 write into App-visible failure.
// After bounded retry, the failure must become an R2-backed integrity marker so Admin cannot keep
// treating stale D1 numbers as verified operational truth.
{
  const r2Keys = [];
  let d1Attempts = 0;
  const waits = [];
  const env = {
    ANALYTICS: {
      async put(key) { r2Keys.push(key); },
    },
    OPS_DB: {
      prepare() { d1Attempts += 1; throw new Error('synthetic D1 unavailable'); },
    },
  };
  const ctx = { waitUntil(promise) { waits.push(Promise.resolve(promise)); } };
  const response = await post(env, ctx, { did: 'dev-d1-down', app_v: '0.2.7', events: [event('d1-1')] });
  assert.equal(response.status, 200, 'R2 success must remain App-visible success when D1 shadow fails');
  const payload = await response.json();
  assert.equal(payload.ok, true);
  assert.equal(waits.length, 1, 'D1 work must be scheduled after R2 success');
  await Promise.all(waits); // shadow rejection + marker persistence are contained in waitUntil
  assert.equal(d1Attempts, 3, 'transient D1 shadow writes require bounded retry');
  assert.equal(r2Keys.length, 2, 'durable event + unresolved shadow marker must both be written to R2');
  assert(r2Keys.some((key) => key === 'ops-index-health/unresolved.json'), r2Keys);
}

// Even if writing the health marker itself transiently fails, retry it independently and never
// change an already durable telemetry POST into an App-visible failure.
{
  let markerAttempts = 0;
  const waits = [];
  const env = {
    ANALYTICS: {
      async put(key) {
        if (key === 'ops-index-health/unresolved.json') {
          markerAttempts += 1;
          throw new Error('synthetic R2 marker outage');
        }
      },
    },
    OPS_DB: {
      prepare() { throw new Error('synthetic D1 outage with marker outage'); },
    },
  };
  const ctx = { waitUntil(promise) { waits.push(Promise.resolve(promise)); } };
  const response = await post(env, ctx, { did: 'dev-d1-marker-down', app_v: '0.2.7', events: [event('d1-marker-1')] });
  assert.equal(response.status, 200);
  await Promise.all(waits);
  assert.equal(markerAttempts, 3, 'R2 integrity marker needs its own bounded retry');
}

// R2 is the success boundary: if it fails, D1 must not run and the App must see failure.
{
  let d1Touched = false;
  const waits = [];
  const env = {
    ANALYTICS: {
      async put() { throw new Error('synthetic R2 unavailable'); },
    },
    OPS_DB: {
      prepare() { d1Touched = true; throw new Error('must not execute'); },
    },
  };
  const ctx = { waitUntil(promise) { waits.push(Promise.resolve(promise)); } };
  const response = await post(env, ctx, { did: 'dev-r2-down', app_v: '0.2.7', events: [event('r2-1')] });
  assert.equal(response.status, 500, 'R2 failure must be App-visible failure');
  assert.equal(d1Touched, false, 'D1 must not execute after R2 failure');
  assert.equal(waits.length, 0, 'no D1 shadow work may be scheduled after R2 failure');
}

// The operational read must fail closed after an unresolved D1 shadow failure, and automatically
// recover verification once a newer verified R2 backfill covers that failure.
{
  let backfill = {
    status: 'complete', inventoryVerified: true, inventoryDays: 31,
    sourceCachedAt: '2026-08-30T02:00:00.000Z', sourceBatchCount: 95793,
  };
  let marker = {
    failedAt: '2026-08-30T02:05:00.000Z',
    batchReceivedAt: '2026-08-30T02:05:00.000Z',
    r2Key: 'events/2026/08/30/dev_1.json',
    error: "D1_ERROR: Your account has exceeded D1's free tier daily row write limit.",
  };
  let shadowRepair = null;
  const legacyCounters = [{
    day: '2026-08-30', active_devices: 110, search_devices: 98, result_devices: 77,
    action_devices: 66, physical_installs: 11, sessions: 99, searches_submitted: 200,
    searches_completed: 180, searches_with_results: 170, zero_result_searches: 10,
  }];
  let deviceDaily = [{ day: '2026-08-30', active_devices: 10, search_devices: 8, result_devices: 7, action_devices: 6 }];
  const installDaily = [{ day: '2026-08-30', physical_installs: 1 }];
  const sessionDaily = [{ day: '2026-08-30', sessions: 9 }];
  const searchDaily = [{ day: '2026-08-30', searches_submitted: 20, searches_completed: 18, searches_with_results: 17, zero_result_searches: 1 }];
  const versions = [{ app_v: '0.2.7', version_code: '207', devices: 10 }];
  const cacheStore = new Map();
  globalThis.caches = {
    default: {
      async match(request) {
        const stored = cacheStore.get(request.url);
        return stored ? stored.clone() : undefined;
      },
      async put(request, response) {
        cacheStore.set(request.url, response.clone());
      },
    },
  };
  const env = {
    ADMIN_SECRET: 'ops-test-secret',
    ANALYTICS: {
      async get(key) {
        if (key !== 'ops-index-health/unresolved.json' || !marker) return null;
        return { async json() { return marker; } };
      },
    },
    OPS_DB: {
      prepare(sql) {
        return {
          sql,
          bind() { return this; },
          async first() {
            if (sql.includes("key='shadow_repair_complete'")) {
              return shadowRepair ? { value: JSON.stringify(shadowRepair), updated_at: Date.now() } : null;
            }
            if (sql.includes("key='backfill_complete'")) {
              return { value: JSON.stringify(backfill), updated_at: Date.now() };
            }
            return null;
          },
        };
      },
      async batch() {
        return [
          { results: legacyCounters },
          { results: deviceDaily },
          { results: installDaily },
          { results: sessionDaily },
          { results: searchDaily },
          { results: [{ value: JSON.stringify(backfill), updated_at: Date.now() }] },
          { results: versions },
          { results: [] },
          { results: [] },
        ];
      },
    },
  };
  const request = () => new Request('https://api.test.local/api/events?mode=ops_daily&days=31', {
    headers: { 'X-Admin-Secret': 'ops-test-secret' },
  });
  let response = await worker.fetch(request(), env, {});
  assert.equal(response.status, 200);
  let payload = await response.json();
  assert.equal(payload.operational_verified, false, 'newer unresolved D1 failure must revoke operational verification');
  assert.equal(payload.integrity.status, 'unresolved_shadow_failure');
  assert.equal(payload.integrity.failure_class, 'd1_daily_row_write_quota');
  assert.equal(payload.integrity.last_failure_received_at, marker.batchReceivedAt);
  assert.equal(payload.version_distribution.total_devices, 10);
  assert.equal(payload.rows[0].active_devices, 10, 'legacy ops_daily drift must never leak into public DAU');
  assert.equal(payload.rows[0].searches_submitted, 20);
  assert.equal(payload.integrity.exact_state_authority, true);
  assert.equal(payload.integrity.legacy_counter_diagnostic.max_abs_active_device_drift, 100);

  shadowRepair = {
    status: 'complete',
    mode: 'exact_r2_receive_day_checkpoint_replay',
    failureReceivedAt: marker.batchReceivedAt,
    failureClass: 'd1_daily_row_write_quota',
    repairedReceiveDays: ['2026-08-30'],
    r2CheckpointVerified: true,
    checkpointCount: 42,
    checkpointFingerprint: '42:feedbeef',
    completedAt: '2026-08-30T02:06:00.000Z',
  };
  deviceDaily = [{ day: '2026-08-30', active_devices: 12, search_devices: 10, result_devices: 9, action_devices: 8 }];
  response = await worker.fetch(request(), env, {});
  payload = await response.json();
  assert.equal(payload.operational_verified, true, 'exact receive-day checkpoint replay covering the current marker must restore verification');
  assert.equal(payload.integrity.status, 'repaired_by_incremental_checkpoint');
  assert.deepEqual(payload.integrity.repaired_receive_days, ['2026-08-30']);
  assert.equal(payload.rows[0].active_devices, 12, 'incremental checkpoint recovery must bypass stale cached rows');
  assert.equal(payload.snapshot_cache.hit, false, 'incremental checkpoint repair must replace the stale cached snapshot');

  shadowRepair = null;
  backfill = {
    ...backfill,
    sourceCachedAt: '2026-08-30T02:10:00.000Z',
    sourceBatchCount: 96000,
  };
  deviceDaily = [{ day: '2026-08-30', active_devices: 11, search_devices: 9, result_devices: 8, action_devices: 7 }];
  response = await worker.fetch(request(), env, {});
  payload = await response.json();
  assert.equal(payload.operational_verified, true, 'verified R2 backfill newer than the failure must restore operational verification');
  assert.equal(payload.integrity.status, 'repaired_by_backfill');
  assert.equal(payload.rows[0].active_devices, 11, 'newer backfill must bypass stale cached rows and rebuild the D1 snapshot');
  assert.equal(payload.snapshot_cache.hit, false, 'repair recovery must replace the stale cached snapshot instead of relabeling it');
}

// Duplicate event IDs inside one App batch are normalized before the durable R2 write.
{
  let stored = null;
  const env = {
    ANALYTICS: {
      async put(_key, value) { stored = JSON.parse(value); },
    },
  };
  const ctx = { waitUntil() {} };
  const ts = Date.now();
  const response = await post(env, ctx, {
    did: 'dev-dup-batch',
    app_v: '0.2.7',
    events: [event('dup', 'app_start', ts), event('dup', 'app_start', ts), event('unique', 'app_start', ts + 1)],
  });
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.count, 2, 'same-batch duplicate event_id must not be durably stored twice');
  assert.equal(stored.events.length, 2);
}

console.log(JSON.stringify({
  status: 'PASS',
  d1_failure_r2_success_returns_200: true,
  unresolved_shadow_failure_revokes_verification: true,
  incremental_checkpoint_repair_restores_verification: true,
  marker_retry_bounded: true,
  r2_failure_never_d1_success: true,
  duplicate_batch_event_id_deduped: true,
}));
