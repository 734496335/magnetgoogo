import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildBackfillStatements, buildOpsState } from './analytics-ops-backfill-lib.mjs';

const root = path.resolve(import.meta.dirname, '..', '..');
const migrationNames = [
  '0001_analytics_ops_index.sql',
  '0002_ops_install_key_unique.sql',
  '0003_ops_device_latest.sql',
  '0004_ops_device_latest_day_index.sql',
  '0005_growth_north_star_indexes.sql',
  '0006_ops_device_aliases_exact_authority.sql',
];
const schema = migrationNames.map((name) => fs.readFileSync(path.join(root, 'cf-gateway', 'migrations', name), 'utf8')).join('\n');
const analytics = JSON.parse(fs.readFileSync(path.join(root, 'admin-server', 'cache', 'analytics.json'), 'utf8'));
const batches = JSON.parse(fs.readFileSync(path.join(root, 'admin-server', 'cache', 'batches.json'), 'utf8'));
if (analytics?._inventoryVerified !== true || Number(analytics?._inventoryDays) !== 31) throw new Error('Verified 31-day cache required');
if (!Array.isArray(batches) || batches.length !== Number(analytics?._totalLocalBatches || -1)) throw new Error('Cache batch count mismatch');

const state = buildOpsState(batches);
const statements = buildBackfillStatements(state, {
  inventoryDays: analytics._inventoryDays,
  sourceCachedAt: analytics._cachedAt,
  sourceBatchCount: batches.length,
});
const sql = statements.join('\n');
const python = String.raw`
import json, sqlite3, sys
p=json.load(sys.stdin)
db=sqlite3.connect(':memory:')
db.executescript(p['schema'])
db.executescript(p['sql'])
first=db.total_changes
before=db.total_changes
db.executescript(p['sql'])
replay=db.total_changes-before
counts={
 'aliases': db.execute('SELECT COUNT(*) FROM ops_device_aliases').fetchone()[0],
 'latest': db.execute('SELECT COUNT(*) FROM ops_device_latest').fetchone()[0],
 'device_days': db.execute('SELECT COUNT(*) FROM ops_device_days').fetchone()[0],
 'sessions': db.execute('SELECT COUNT(*) FROM ops_session_days').fetchone()[0],
 'searches': db.execute('SELECT COUNT(*) FROM ops_searches').fetchone()[0],
}
print(json.dumps({'firstChanges':first,'replayChanges':replay,'counts':counts}))
`;
const result = spawnSync('python', ['-c', python], {
  input: JSON.stringify({ schema, sql }),
  encoding: 'utf8',
  maxBuffer: 50 * 1024 * 1024,
});
if (result.status !== 0) throw new Error(result.stderr || `python exit ${result.status}`);
const payload = JSON.parse(result.stdout.trim());
if (payload.replayChanges !== 1) throw new Error(`Expected only backfill_complete metadata write on identical replay; got ${payload.replayChanges}`);
console.log(JSON.stringify({
  status: 'PASS',
  source_batches: batches.length,
  first_logical_row_changes: payload.firstChanges,
  identical_replay_compact_row_changes: payload.replayChanges - 1,
  replay_metadata_changes: 1,
  counts: payload.counts,
}));
