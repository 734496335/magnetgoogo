import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildBackfillStatements, buildOpsState } from './analytics-ops-backfill-lib.mjs';

const root = path.resolve(import.meta.dirname, '..');
const migrationNames = [
  '0001_analytics_ops_index.sql',
  '0002_ops_install_key_unique.sql',
  '0003_ops_device_latest.sql',
  '0004_ops_device_latest_day_index.sql',
  '0005_growth_north_star_indexes.sql',
  '0006_ops_device_aliases_exact_authority.sql',
];
const schema = migrationNames.map((name) => fs.readFileSync(path.join(root, 'migrations', name), 'utf8')).join('\n');
const baseTs = Date.parse('2026-09-02T01:00:00.000Z');
const base = [{
  id: 'events/2026/09/02/base-a', did: 'dev-a', legacy_did: 'dev-a', schema_v: 2, app_v: '0.2.7', receivedAt: '2026-09-02T01:00:01.000Z',
  events: [
    { id: 'base-start', e: 'app_start', ts: baseTs },
    { id: 'base-search', e: 'search_submitted', ts: baseTs + 10, search_id: 'search-a' },
  ],
}];
const checkpoint = [...base, {
  id: 'events/2026/09/02/delta-b', did: 'dev-b', legacy_did: 'dev-b', schema_v: 2, app_v: '0.2.7', receivedAt: '2026-09-02T01:10:01.000Z',
  events: [{ id: 'delta-start', e: 'app_start', ts: baseTs + 600_000 }],
}, {
  id: 'events/2026/09/02/delta-complete', did: 'dev-a', legacy_did: 'dev-a', schema_v: 2, app_v: '0.2.7', receivedAt: '2026-09-02T01:11:01.000Z',
  events: [{ id: 'delta-search-complete', e: 'search_completed', ts: baseTs + 660_000, search_id: 'search-a', result_count: 4 }],
}];

const baseSql = buildBackfillStatements(buildOpsState(base), {
  inventoryDays: 31,
  sourceCachedAt: '2026-09-02T01:00:05.000Z',
  sourceBatchCount: 100,
}).join('\n');
const repairSql = buildBackfillStatements(buildOpsState(checkpoint), {
  inventoryDays: 31,
  sourceCachedAt: '2026-09-02T01:12:00.000Z',
  sourceBatchCount: 102,
}).join('\n');
assert.doesNotMatch(repairSql, /DELETE FROM ops_/, 'incremental replay must never delete compact state');

const python = String.raw`
import json, sqlite3, sys
p=json.load(sys.stdin)
db=sqlite3.connect(':memory:')
db.executescript(p['schema'])
db.executescript(p['base'])
def snap():
    day=db.execute("SELECT active_devices,searches_submitted,searches_completed,searches_with_results FROM ops_daily WHERE day='2026-09-02'").fetchone()
    exact=db.execute("SELECT COUNT(*) FROM ops_device_days_exact WHERE day='2026-09-02'").fetchone()[0]
    meta=json.loads(db.execute("SELECT value FROM ops_index_meta WHERE key='backfill_complete'").fetchone()[0])
    return {'day': day, 'exact': exact, 'sourceBatchCount': meta['sourceBatchCount'], 'sourceCachedAt': meta['sourceCachedAt']}
base=snap()
db.executescript(p['repair'])
after=snap()
changes_before_replay=db.total_changes
db.executescript(p['repair'])
replay_changes=db.total_changes-changes_before_replay
replay=snap()
print(json.dumps({'base':base,'after':after,'replay':replay,'replayChanges':replay_changes}))
`;
const result = spawnSync('python', ['-c', python], {
  input: JSON.stringify({ schema, base: baseSql, repair: repairSql }),
  encoding: 'utf8',
});
if (result.status !== 0) throw new Error(result.stderr || `python exit ${result.status}`);
const payload = JSON.parse(result.stdout.trim());
assert.deepEqual(payload.base.day, [1, 1, 0, 0]);
assert.equal(payload.base.exact, 1);
assert.deepEqual(payload.after.day, [2, 1, 1, 1]);
assert.equal(payload.after.exact, 2);
assert.equal(payload.after.sourceBatchCount, 102);
assert.equal(payload.after.sourceCachedAt, '2026-09-02T01:12:00.000Z');
assert.deepEqual(payload.replay, payload.after, 'replaying the same verified receive-day checkpoint must be state-idempotent');
assert.equal(payload.replayChanges, 1, 'identical repair replay may refresh only backfill_complete metadata; compact rows must be true SQL no-ops');

console.log(JSON.stringify({
  status: 'PASS',
  baseline_devices: payload.base.exact,
  repaired_devices: payload.after.exact,
  search_lifecycle_merged: true,
  replay_state_idempotent: true,
  replay_compact_row_changes: payload.replayChanges - 1,
  no_delete_repair: true,
}));
