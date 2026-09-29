import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildBackfillStatements, buildOpsState, expectedCanonicalDailyRows } from './analytics-ops-backfill-lib.mjs';

const root = path.resolve(import.meta.dirname, '..', '..');
const cacheDir = path.join(root, 'admin-server', 'cache');
const analyticsPath = path.join(cacheDir, 'analytics.json');
const batchesPath = path.join(cacheDir, 'batches.json');
const apply = process.argv.includes('--apply');
const dayArg = process.argv.find((arg) => arg.startsWith('--day='));
const day = dayArg ? dayArg.slice('--day='.length) : '';

if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error('Usage: node repair-analytics-ops-day.mjs --day=YYYY-MM-DD [--apply]');

const analytics = JSON.parse(fs.readFileSync(analyticsPath, 'utf8'));
if (analytics?._inventoryVerified !== true || Number(analytics?._inventoryDays) !== 31) {
  throw new Error('Refusing incremental D1 repair: analytics.json is not a verified 31-day R2 snapshot');
}
const baseBatches = JSON.parse(fs.readFileSync(batchesPath, 'utf8'));
if (!Array.isArray(baseBatches) || baseBatches.length !== Number(analytics?._totalLocalBatches || -1)) {
  throw new Error('Refusing incremental D1 repair: verified cache batch count mismatch');
}

const receivePrefix = `events/${day.replaceAll('-', '/')}/`;
const baseDayCount = baseBatches.filter((row) => String(row?.id || '').startsWith(receivePrefix)).length;
if (baseDayCount <= 0) {
  throw new Error(`Refusing incremental D1 repair: verified 31-day base does not contain receive day ${day}; refresh the verified Admin cache first`);
}

const checkpointPath = path.join(cacheDir, 'repair-partitions', `${day}.json`);
const checkpoint = JSON.parse(fs.readFileSync(checkpointPath, 'utf8'));
const checkpointRows = Array.isArray(checkpoint?.batches) ? checkpoint.batches : null;
if (!checkpointRows || checkpoint?.inventory?.day !== day || checkpointRows.length !== Number(checkpoint?.inventory?.count)) {
  throw new Error(`Refusing incremental D1 repair: checkpoint ${day} is incomplete`);
}
const checkpointIds = checkpointRows.map((row) => String(row?.id || '')).filter(Boolean);
if (checkpointIds.length !== checkpointRows.length || checkpointIds.some((id) => !id.startsWith(receivePrefix))) {
  throw new Error(`Refusing incremental D1 repair: checkpoint ${day} contains invalid partition rows`);
}
if (checkpointRows.length < baseDayCount) {
  throw new Error(`Refusing incremental D1 repair: R2 partition regressed ${day} ${checkpointRows.length}<${baseDayCount}`);
}

const sourceCachedAt = new Date(Math.max(
  Date.parse(String(analytics._cachedAt || '')) || 0,
  fs.statSync(checkpointPath).mtimeMs,
)).toISOString();
const sourceBatchCount = baseBatches.length - baseDayCount + checkpointRows.length;
const state = buildOpsState(checkpointRows);
const statements = buildBackfillStatements(state, {
  inventoryDays: 31,
  sourceCachedAt,
  sourceBatchCount,
});

function splitSql(statementsToSplit, maxChars = 420_000) {
  const files = [];
  let current = [];
  let size = 0;
  for (const stmt of statementsToSplit) {
    const nextSize = stmt.length + 2;
    if (current.length > 0 && size + nextSize > maxChars) {
      files.push(current.join('\n\n'));
      current = [];
      size = 0;
    }
    current.push(stmt);
    size += nextSize;
  }
  if (current.length > 0) files.push(current.join('\n\n'));
  return files;
}

function runWranglerFile(sql, index, total) {
  const tmp = path.join(os.tmpdir(), `maggoogo-ops-day-repair-${process.pid}-${index}.sql`);
  const wranglerCli = path.join(root, 'cf-gateway', 'node_modules', 'wrangler', 'bin', 'wrangler.js');
  if (!fs.existsSync(wranglerCli)) {
    throw new Error(`Local Wrangler CLI missing: ${wranglerCli}`);
  }
  fs.writeFileSync(tmp, sql, 'utf8');
  let result;
  try {
    result = spawnSync(process.execPath, [wranglerCli, 'd1', 'execute', 'maggoogo-analytics-index', '--remote', '--file', tmp], {
      cwd: path.join(root, 'cf-gateway'),
      stdio: 'inherit',
      timeout: 90_000,
      windowsHide: true,
      env: { ...process.env, NODE_OPTIONS: '--dns-result-order=ipv4first' },
    });
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* best effort */ }
  }
  if (result?.error?.code === 'ETIMEDOUT') {
    throw new Error(`Wrangler D1 incremental repair chunk ${index}/${total} timed out after 90s`);
  }
  if (result?.status !== 0) {
    throw new Error(`Wrangler D1 incremental repair chunk ${index}/${total} failed with exit ${result?.status ?? 'null'} signal=${result?.signal || 'none'}`);
  }
}

const sqlChunks = splitSql(statements);
if (apply) {
  for (let i = 0; i < sqlChunks.length; i += 1) runWranglerFile(sqlChunks[i], i + 1, sqlChunks.length);
}

const canonicalRows = expectedCanonicalDailyRows(state);
console.log(JSON.stringify({
  status: apply ? 'APPLIED' : 'READY',
  mode: 'incremental_receive_day_replay',
  day,
  baseDayCount,
  checkpointCount: checkpointRows.length,
  addedBatches: checkpointRows.length - baseDayCount,
  sourceCachedAt,
  sourceBatchCount,
  validEvents: state.validEvents,
  deviceDays: state.deviceDays.size,
  aliases: state.aliases.size,
  deviceLatest: state.deviceLatest.size,
  installs: state.installs.size,
  sessions: state.sessions.size,
  searches: state.searches.size,
  canonicalDeviceDaysInOverlay: canonicalRows.reduce((sum, row) => sum + row.active_devices, 0),
  sqlStatements: statements.length,
  sqlChunks: sqlChunks.length,
}, null, 2));
