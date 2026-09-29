import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { buildBackfillStatements, buildOpsState, expectedCanonicalDailyRows, expectedDailyRows, expectedVersionRows } from './analytics-ops-backfill-lib.mjs';

const dayTs = Date.parse('2026-08-30T00:00:00.000Z');
const capacityNow = dayTs + 3600_000;
const batches = [];
for (let i = 0; i < 5000; i += 1) {
  const appV = i < 3500 ? '0.2.7' : '0.2.6';
  const versionCode = i < 3500 ? '207' : '206';
  batches.push({
    id: `cap-${i}`,
    did: `dev-${i}`,
    app_v: appV,
    version_code: versionCode,
    schema_v: 2,
    legacy_did: `dev-${i}`,
    install_id: `install-${i}`,
    receivedAt: new Date(dayTs + i).toISOString(),
    events: [{ id: `e-${i}`, e: 'app_start', ts: dayTs + i }],
  });
}
// Same device repeated across 100 batches must remain one device-day.
for (let i = 0; i < 100; i += 1) {
  batches.push({
    id: `replay-${i}`,
    did: 'dev-0',
    app_v: '0.2.7',
    version_code: '207',
    schema_v: 2,
    legacy_did: 'dev-0',
    receivedAt: new Date(dayTs + 10000 + i).toISOString(),
    events: [{ id: `replay-event-${i}`, e: 'app_start', ts: dayTs + 10000 + i }],
  });
}
// Same whole batch replayed should collapse through exact compact keys.
const replayed = JSON.parse(JSON.stringify(batches[1]));
batches.push(replayed, replayed);
// completed-before-submitted across separate batches must merge into one lifecycle.
batches.push({
  id: 'search-completed-first', did: 'dev-0', app_v: '0.2.7', version_code: '207', schema_v: 2, legacy_did: 'dev-0',
  receivedAt: new Date(dayTs + 20000).toISOString(),
  events: [{ id: 'search-complete-e', e: 'search_completed', ts: dayTs + 20000, search_id: 'search-cap', result_count: 3 }],
});
batches.push({
  id: 'search-submitted-later', did: 'dev-0', app_v: '0.2.7', version_code: '207', schema_v: 2, legacy_did: 'dev-0',
  receivedAt: new Date(dayTs + 19000).toISOString(),
  events: [{ id: 'search-submit-e', e: 'search_submitted', ts: dayTs + 19000, search_id: 'search-cap' }],
});
// Uptime-like installation_time must not generate a 1970 physical install.
batches.push({
  id: 'bad-install', did: 'dev-0', app_v: '0.2.7', version_code: '207', schema_v: 2, legacy_did: 'dev-0', install_id: 'install-bad',
  receivedAt: new Date(dayTs + 30000).toISOString(),
  events: [{ id: 'bad-install-e', e: 'first_open', ts: dayTs + 30000, installation_time: 2580891395 }],
});
// Same install_id may be observed across batches with conflicting valid timestamps.
// Global physical-install identity must keep only the earliest installation day.
batches.push({
  id: 'install-late', did: 'dev-0', app_v: '0.2.7', version_code: '207', schema_v: 2, legacy_did: 'dev-0', install_id: 'install-move',
  receivedAt: new Date(dayTs + 31000).toISOString(),
  events: [{ id: 'install-late-e', e: 'first_open', ts: dayTs + 31000, installation_time: Date.parse('2026-08-29T03:00:00.000Z') }],
});
batches.push({
  id: 'install-earlier', did: 'dev-0', app_v: '0.2.7', version_code: '207', schema_v: 2, legacy_did: 'dev-0', install_id: 'install-move',
  receivedAt: new Date(dayTs + 32000).toISOString(),
  events: [{ id: 'install-earlier-e', e: 'first_open', ts: dayTs + 32000, installation_time: Date.parse('2026-08-28T03:00:00.000Z') }],
});
// A later server observation upgrades dev-0; version distribution must move the
// device rather than count both historical versions.
batches.push({
  id: 'version-upgrade', did: 'dev-0', app_v: '0.2.8', version_code: '208', schema_v: 2, legacy_did: 'dev-0',
  receivedAt: new Date(dayTs + 50000).toISOString(),
  events: [{ id: 'version-upgrade-e', e: 'app_start', ts: dayTs + 50000 }],
});

const state = buildOpsState(batches);
const daily = expectedDailyRows(state);
const target = daily.find((row) => row.day === '2026-08-30');
assert(target, 'capacity day missing');
assert.equal(target.active_devices, 5000, '5000 distinct devices must remain exact; 100 replays and adversarial events must not inflate DAU');
assert.equal(target.searches_submitted, 1, 'completed-before-submitted lifecycle must count submitted once');
assert.equal(target.searches_completed, 1, 'completed-before-submitted lifecycle must count completed once');
assert.equal(target.searches_with_results, 1);
assert.equal(state.installs.size, 1, 'global install_id must collapse conflicting installation days');
assert.equal([...state.installs.values()][0].installDay, '2026-08-28', 'earliest valid installation_time must win globally');
assert.equal(daily.find((row) => row.day === '2026-08-28')?.physical_installs, 1, 'physical install must be counted once on earliest day');
assert.equal(state.searches.size, 1);
assert.equal(state.deviceLatest.size, 5000, 'latest-version read model must remain one row per anonymous device');
const versions = expectedVersionRows(state, 31, capacityNow);
assert.equal(versions.reduce((sum, row) => sum + row.devices, 0), 5000, 'version distribution must count each active device exactly once');
assert.deepEqual(
  Object.fromEntries(versions.map((row) => [row.app_v, row.devices])),
  { '0.2.7': 3499, '0.2.6': 1500, '0.2.8': 1 },
  'last observed version must replace, not duplicate, a device',
);

const aliasBatches = [
  { id: 'alias-a', did: 'legacy-a', legacy_did: 'legacy-a', device_id: 'dv2-same-phone', device_id_kind: 'android_id_hash', schema_v: 2, app_v: '0.2.7', receivedAt: new Date(dayTs).toISOString(), events: [{ id: 'alias-a-e', e: 'app_start', ts: dayTs }] },
  { id: 'alias-b', did: 'legacy-b', legacy_did: 'legacy-b', device_id: 'dv2-same-phone', device_id_kind: 'android_id_hash', schema_v: 2, app_v: '0.2.7', receivedAt: new Date(dayTs + 1).toISOString(), events: [{ id: 'alias-b-e', e: 'app_start', ts: dayTs + 1 }] },
];
const aliasState = buildOpsState(aliasBatches);
assert.equal(aliasState.aliases.size, 2);
assert.equal(expectedDailyRows(aliasState)[0].active_devices, 2, 'legacy observed identities remain separately auditable');
assert.equal(expectedCanonicalDailyRows(aliasState)[0].active_devices, 1, 'two proven legacy IDs for one android_id_hash device must collapse to one canonical DAU');
const conflictState = buildOpsState([...aliasBatches, { ...aliasBatches[0], id: 'alias-conflict', device_id: 'dv2-other-phone', receivedAt: new Date(dayTs + 2).toISOString(), events: [{ id: 'alias-conflict-e', e: 'app_start', ts: dayTs + 2 }] }]);
assert.equal(conflictState.aliases.get('legacy-a').conflict, 1, 'one legacy alias mapping to two physical IDs must be marked ambiguous');
assert.equal(expectedCanonicalDailyRows(conflictState)[0].active_devices, 2, 'ambiguous alias must fail open to separate identities, never force-merge');

const statements = buildBackfillStatements(state, { inventoryDays: 31, sourceBatchCount: batches.length });
assert(statements.length > 0);
assert(statements.at(-2).includes('FROM ops_device_days_exact'), 'historical rebuild must reconstruct legacy ops_daily diagnostic from canonical exact state');
assert(statements.at(-1).includes("'backfill_complete'"), 'backfill completion marker must be written last');

const source = fs.readFileSync(path.resolve('src/index.js'), 'utf8');
const opsStart = source.indexOf('async function handleEventsOpsDaily');
const opsEnd = source.indexOf('async function handleEventsPost', opsStart);
const opsBlock = source.slice(opsStart, opsEnd);
assert.match(opsBlock, /FROM ops_daily WHERE day>=\? ORDER BY day/, 'legacy counter diagnostic must remain queryable for drift evidence');
assert.match(opsBlock, /WITH firsts AS \(/, 'north-star read must precompute canonical first-seen state instead of correlated history scans');
assert.match(opsBlock, /windowed AS \(/, 'north-star read must bound repeated device-day work to the requested window');
assert.match(opsBlock, /rows: dailyRows/, 'public DAU rows must never come from ops_daily counters');
assert.doesNotMatch(opsBlock, /handleEvents(?:Inventory|Page)/, '31-day primary query must not scan raw R2 partitions');
assert.match(opsBlock, /FROM ops_device_latest l LEFT JOIN ops_device_aliases/, 'version distribution must use alias-aware compact latest-device state');
assert.match(opsBlock, /readOpsShadowIntegrity/, 'operational read must verify D1 shadow integrity instead of trusting stale backfill metadata');
assert.match(opsBlock, /FROM ops_device_days d LEFT JOIN ops_device_aliases/, 'growth north star must canonicalize compact device-day state');
assert.match(opsBlock, /FROM ops_searches WHERE submitted_day>=\?/, 'search satisfaction funnel must query compact search lifecycle state');
assert.doesNotMatch(opsBlock, /NOT EXISTS\(SELECT 1 FROM canonical/, 'north-star read must not use per-device correlated historical scans');
assert.doesNotMatch(opsBlock, /EXISTS\(SELECT 1 FROM canonical/, 'reuse/D7 read must use joins rather than correlated historical scans');
assert.match(source, /OPS_DAILY_SNAPSHOT_TTL_SECONDS = 30 \* 60/, 'ops exact snapshot must have a bounded edge-cache TTL to stay below D1 free-tier reads');
assert.match(source, /d1_daily_row_write_quota/, 'shadow integrity must classify D1 daily row-write quota failures for bounded recovery');
assert.match(source, /last_failure_received_at/, 'shadow integrity must expose the receive-time boundary required for exact R2 replay');
assert.match(opsBlock, /readOpsDailySnapshotCache\(days\)/, 'ops read must consult edge snapshot cache before issuing D1 queries');
assert.match(opsBlock, /writeOpsDailySnapshotCache\(days, payload\)/, 'fresh exact ops response must populate edge snapshot cache');
assert.doesNotMatch(opsBlock, /growth-events\//, 'ops north-star query must not scan raw growth R2 objects');
const incrementalRepairSource = fs.readFileSync(path.resolve('scripts/repair-analytics-ops-day.mjs'), 'utf8');
assert.match(incrementalRepairSource, /buildOpsState\(checkpointRows\)/, 'quota recovery must replay only the verified receive-day checkpoint, not the full 31-day batch set');
assert.match(incrementalRepairSource, /baseDayCount <= 0/, 'incremental repair must refuse a stale verified base that does not contain the target receive day');
assert.doesNotMatch(incrementalRepairSource, /DELETE FROM ops_/, 'incremental repair must be append/upsert based and must not delete exact compact state');

// Real production currently produces roughly tens of batches per active device.
// Exercise a 25 batches/device day so the 5k capacity gate covers ~125k raw R2
// objects rather than the unrealistic one-batch-per-device happy path.
const amplified = [];
for (let i = 0; i < 5000; i += 1) {
  for (let j = 0; j < 25; j += 1) {
    const ts = dayTs + i * 25 + j;
    amplified.push({
      id: `amp-${i}-${j}`,
      did: `amp-dev-${i}`,
      app_v: i % 2 ? '0.2.7' : '0.2.6',
      version_code: i % 2 ? '207' : '206',
      schema_v: 2,
      legacy_did: `amp-dev-${i}`,
      receivedAt: new Date(ts).toISOString(),
      events: [{ id: `amp-e-${i}-${j}`, e: 'app_start', ts }],
    });
  }
}
const amplifiedState = buildOpsState(amplified);
assert.equal(amplified.length, 125000);
assert.equal(amplifiedState.deviceDays.size, 5000, '125k raw batches must still collapse to exact 5k DAU');
assert.equal(amplifiedState.deviceLatest.size, 5000, '125k raw batches must still collapse to exact 5k current-version identities');

console.log(JSON.stringify({
  status: 'PASS',
  synthetic_devices: 5000,
  repeated_batches_same_device: 100,
  exact_active_devices: target.active_devices,
  completed_before_submitted: true,
  global_install_id_unique: true,
  version_distribution_exact: true,
  amplified_raw_batches: amplified.length,
  amplified_exact_devices: amplifiedState.deviceDays.size,
  historical_rebuild_from_compact_index: true,
  primary_query_raw_object_independent: true,
}));
