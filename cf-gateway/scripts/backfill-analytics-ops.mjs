import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildBackfillStatements, buildOpsState, expectedCanonicalDailyRows, expectedDailyRows } from './analytics-ops-backfill-lib.mjs';

const root = path.resolve(import.meta.dirname, '..', '..');
const adminCache = path.join(root, 'admin-server', 'cache');
const analyticsPath = path.join(adminCache, 'analytics.json');
const batchesPath = path.join(adminCache, 'batches.json');
const apply = process.argv.includes('--apply');
const allowFullApply = process.argv.includes('--allow-full-apply');
const forceOverFreeBudget = process.argv.includes('--force-over-free-budget');
const repairDayArg = process.argv.find((arg) => arg.startsWith('--repair-day='));
const repairDay = repairDayArg ? repairDayArg.slice('--repair-day='.length) : '';

if (apply && !repairDay && !allowFullApply) {
  throw new Error('Refusing unbounded full D1 apply on the Free tier. Use incremental repair-analytics-ops-day.mjs for normal recovery, or pass --allow-full-apply only after an explicit write-budget review / Paid-plan decision.');
}

const analytics = JSON.parse(fs.readFileSync(analyticsPath, 'utf8'));
if (analytics?._inventoryVerified !== true || Number(analytics?._inventoryDays) !== 31) {
  throw new Error('Refusing D1 backfill: analytics.json is not a verified 31-day R2 rebuild');
}
let batches = JSON.parse(fs.readFileSync(batchesPath, 'utf8'));
if (!Array.isArray(batches) || batches.length !== Number(analytics?._totalLocalBatches || -1)) {
  throw new Error(`Refusing D1 backfill: batches.json count ${Array.isArray(batches) ? batches.length : 'invalid'} != analytics ${analytics?._totalLocalBatches}`);
}

let sourceCachedAt = analytics._cachedAt;
let repairOverlay = null;
if (repairDay) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(repairDay)) throw new Error(`Invalid --repair-day=${repairDay}`);
  const receivePrefix = `events/${repairDay.replaceAll('-', '/')}/`;
  const checkpointPath = path.join(adminCache, 'repair-partitions', `${repairDay}.json`);
  const checkpoint = JSON.parse(fs.readFileSync(checkpointPath, 'utf8'));
  const checkpointRows = Array.isArray(checkpoint?.batches) ? checkpoint.batches : null;
  if (!checkpointRows || checkpoint?.inventory?.day !== repairDay || checkpointRows.length !== Number(checkpoint?.inventory?.count)) {
    throw new Error(`Refusing repair overlay: checkpoint ${repairDay} is incomplete`);
  }
  const checkpointIds = checkpointRows.map((row) => String(row?.id || '')).filter(Boolean);
  if (checkpointIds.length !== checkpointRows.length || checkpointIds.some((id) => !id.startsWith(receivePrefix))) {
    throw new Error(`Refusing repair overlay: checkpoint ${repairDay} contains invalid partition rows`);
  }
  const previousCount = batches.filter((row) => String(row?.id || '').startsWith(receivePrefix)).length;
  batches = batches.filter((row) => !String(row?.id || '').startsWith(receivePrefix));
  batches.push(...checkpointRows);
  sourceCachedAt = fs.statSync(checkpointPath).mtime.toISOString();
  repairOverlay = { day: repairDay, previousCount, checkpointCount: checkpointRows.length, sourceCachedAt };
}

const state = buildOpsState(batches);
const expected = expectedDailyRows(state);
const expectedCanonical = expectedCanonicalDailyRows(state);
const fullRebuildPhysicalWriteLowerBound = state.aliases.size * 2
  + state.deviceLatest.size * 3
  + state.deviceDays.size * 2
  + state.installs.size * 2
  + state.sessions.size
  + state.searches.size * 4
  + expectedCanonical.length
  + 1;
if (apply && !repairDay && fullRebuildPhysicalWriteLowerBound > 70_000 && !forceOverFreeBudget) {
  throw new Error(`Refusing full D1 apply: estimated empty-DB physical writes >= ${fullRebuildPhysicalWriteLowerBound}, above the 70k Free-tier engineering budget. Use incremental repair, Workers Paid, or pass --force-over-free-budget only after explicit capacity approval.`);
}
const statements = buildBackfillStatements(state, {
  inventoryDays: analytics._inventoryDays,
  sourceCachedAt,
  sourceBatchCount: batches.length,
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
  const tmp = path.join(os.tmpdir(), `maggoogo-ops-backfill-${process.pid}-${index}.sql`);
  fs.writeFileSync(tmp, sql, 'utf8');
  const baseArgs = ['wrangler@4.126.0', 'd1', 'execute', 'maggoogo-analytics-index', '--remote', '--file', tmp];
  const isWindows = process.platform === 'win32';
  const command = isWindows ? (process.env.ComSpec || 'cmd.exe') : 'npx';
  const args = isWindows
    ? ['/d', '/c', 'npx', ...baseArgs]
    : baseArgs;
  let lastResult = null;
  try {
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      lastResult = spawnSync(command, args, {
        cwd: path.resolve(root, 'cf-gateway'),
        stdio: 'inherit',
        env: { ...process.env, NODE_OPTIONS: '--dns-result-order=ipv4first' },
      });
      if (lastResult.status === 0) return;
      if (attempt < 3) {
        console.warn(`[backfill] chunk ${index}/${total} process failed with exit ${lastResult.status}; retrying (${attempt}/3)`);
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500 * attempt);
      }
    }
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* best effort */ }
  }
  throw new Error(`Wrangler D1 backfill chunk ${index}/${total} failed after retries with exit ${lastResult?.status}: ${lastResult?.error?.message || 'no spawn error detail'}`);
}

const sqlChunks = splitSql(statements);
if (apply) {
  for (let i = 0; i < sqlChunks.length; i += 1) runWranglerFile(sqlChunks[i], i + 1, sqlChunks.length);
}

console.log(JSON.stringify({
  status: apply ? 'APPLIED' : 'READY',
  verifiedCache: true,
  sourceCachedAt,
  sourceBatches: batches.length,
  repairOverlay,
  validEvents: state.validEvents,
  fullRebuildPhysicalWriteLowerBound,
  deviceDays: state.deviceDays.size,
  canonicalDeviceDays: expectedCanonical.reduce((sum, row) => sum + row.active_devices, 0),
  aliases: state.aliases.size,
  aliasConflicts: [...state.aliases.values()].filter((row) => row.conflict).length,
  deviceLatest: state.deviceLatest.size,
  installs: state.installs.size,
  sessions: state.sessions.size,
  searches: state.searches.size,
  dailyRows: expected.length,
  sqlStatements: statements.length,
  sqlChunks: sqlChunks.length,
  range: expected.length ? [expected[0].day, expected.at(-1).day] : [],
  dailyTail: expected.slice(-12),
  canonicalDailyTail: expectedCanonical.slice(-12),
}, null, 2));
