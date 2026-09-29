import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildBackfillStatements, buildOpsState } from './analytics-ops-backfill-lib.mjs';

const root = path.resolve(import.meta.dirname, '..', '..');
const cacheDir = path.join(root, 'admin-server', 'cache');
const apply = process.argv.includes('--apply');
const dayArg = process.argv.find((arg) => arg.startsWith('--day='));
const day = dayArg ? dayArg.slice('--day='.length) : '';
const gateway = process.env.GROWTH_GATEWAY_URL || 'https://api.naoshiquan.com';

function readLocalEnvValue(key) {
  const envPath = path.join(root, '.env');
  if (!fs.existsSync(envPath)) return '';
  const line = fs.readFileSync(envPath, 'utf8')
    .split(/\r?\n/)
    .find((entry) => entry.startsWith(`${key}=`));
  if (!line) return '';
  return line.slice(key.length + 1).trim().replace(/^(["'])(.*)\1$/, '$2');
}

const adminSecret = String(process.env.ADMIN_SECRET || readLocalEnvValue('ADMIN_SECRET') || '').trim();

if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
  throw new Error('Usage: node repair-analytics-shadow-deep.mjs --day=YYYY-MM-DD [--apply]');
}
if (!adminSecret) throw new Error('ADMIN_SECRET missing');

function inventoryFingerprint(batches) {
  let count = 0;
  let firstKey = '';
  let lastKey = '';
  for (const batch of batches || []) {
    const id = String(batch?.id || '').trim();
    if (!id) continue;
    count += 1;
    if (!firstKey || id < firstKey) firstKey = id;
    if (!lastKey || id > lastKey) lastKey = id;
  }
  let hash = 0x811c9dc5;
  for (const key of [firstKey, lastKey]) {
    if (!key || (key === lastKey && lastKey === firstKey && hash !== 0x811c9dc5)) continue;
    const text = `${key}\n`;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
  }
  return `${count}:${hash.toString(16).padStart(8, '0')}`;
}

async function readOpsHealth() {
  const response = await fetch(`${gateway}/api/events?mode=ops_daily&days=31`, {
    headers: { 'X-Admin-Secret': adminSecret, 'Cache-Control': 'no-cache' },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`ops_daily HTTP ${response.status}: ${payload?.error || 'unknown'}`);
  return payload;
}

function splitSql(statements, maxChars = 420_000) {
  const files = [];
  let current = [];
  let size = 0;
  for (const stmt of statements) {
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
  const tmp = path.join(os.tmpdir(), `maggoogo-shadow-deep-${process.pid}-${index}.sql`);
  fs.writeFileSync(tmp, sql, 'utf8');
  const isWindows = process.platform === 'win32';
  const command = isWindows ? (process.env.ComSpec || 'cmd.exe') : 'npx';
  const wranglerArgs = ['wrangler@4.137.0', 'd1', 'execute', 'maggoogo-analytics-index', '--remote', '--file', tmp];
  const args = isWindows ? ['/d', '/c', 'npx', '--yes', ...wranglerArgs] : ['--yes', ...wranglerArgs];
  let result;
  try {
    result = spawnSync(command, args, {
      cwd: path.join(root, 'cf-gateway'),
      stdio: 'inherit',
      timeout: 90_000,
      windowsHide: true,
      env: { ...process.env, NODE_OPTIONS: '--dns-result-order=ipv4first' },
    });
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* best effort */ }
  }
  if (result?.error?.code === 'ETIMEDOUT') throw new Error(`D1 deep repair chunk ${index}/${total} timed out`);
  if (result?.status !== 0) throw new Error(`D1 deep repair chunk ${index}/${total} failed: exit=${result?.status ?? 'null'} signal=${result?.signal || 'none'}`);
}

const before = await readOpsHealth();
if (before.operational_verified === true && before?.integrity?.shadow_healthy === true) {
  console.log(JSON.stringify({ status: 'PASS_NOOP', operational_verified: true }, null, 2));
} else {
if (before?.integrity?.status !== 'unresolved_shadow_failure') {
  throw new Error(`unsupported shadow state: ${before?.integrity?.status || 'unknown'}`);
}
if (before?.integrity?.failure_class !== 'd1_daily_row_read_quota') {
  throw new Error(`deep single-day checkpoint repair is only approved for d1_daily_row_read_quota; got ${before?.integrity?.failure_class || 'unknown'}`);
}
const failureReceivedAt = String(before?.integrity?.last_failure_received_at || '').trim();
if (!failureReceivedAt || failureReceivedAt.slice(0, 10) !== day) {
  throw new Error(`failure receive day ${failureReceivedAt.slice(0, 10) || 'unknown'} does not match --day=${day}`);
}

const checkpointPath = path.join(cacheDir, 'repair-partitions', `${day}.json`);
const checkpoint = JSON.parse(fs.readFileSync(checkpointPath, 'utf8'));
const rows = Array.isArray(checkpoint?.batches) ? checkpoint.batches : null;
if (!rows || checkpoint?.inventory?.day !== day || rows.length !== Number(checkpoint?.inventory?.count)) {
  throw new Error(`checkpoint ${day} is incomplete`);
}
const receivePrefix = `events/${day.replaceAll('-', '/')}/`;
if (rows.some((row) => !String(row?.id || '').startsWith(receivePrefix))) {
  throw new Error(`checkpoint ${day} contains a row outside its receive partition`);
}
const localFingerprint = inventoryFingerprint(rows);
if (localFingerprint !== String(checkpoint?.inventory?.fingerprint || '')) {
  throw new Error(`checkpoint ${day} fingerprint mismatch: local=${localFingerprint} remote=${checkpoint?.inventory?.fingerprint || 'missing'}`);
}

const state = buildOpsState(rows);
const allStatements = buildBackfillStatements(state, { inventoryDays: 0, sourceCachedAt: '', sourceBatchCount: 0 });
const replayStatements = allStatements.slice(0, -1); // Never impersonate a verified 31-day full backfill.
const repairMeta = {
  status: 'complete',
  mode: 'exact_r2_receive_day_checkpoint_replay',
  failureReceivedAt,
  failureClass: before.integrity.failure_class,
  repairedReceiveDays: [day],
  r2CheckpointVerified: true,
  checkpointCount: rows.length,
  checkpointFingerprint: localFingerprint,
  completedAt: new Date().toISOString(),
};
const escapedMeta = JSON.stringify(repairMeta).replace(/'/g, "''");
replayStatements.push(`INSERT INTO ops_index_meta(key,value,updated_at) VALUES('shadow_repair_complete','${escapedMeta}',${Date.now()}) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at;`);

const conservativePhysicalWriteUpperBound = state.aliases.size * 2
  + state.deviceLatest.size * 3
  + state.deviceDays.size * 2
  + state.installs.size * 2
  + state.sessions.size
  + state.searches.size * 4
  + 2;
if (conservativePhysicalWriteUpperBound > 70_000) {
  throw new Error(`refusing deep repair: conservative physical write upper bound ${conservativePhysicalWriteUpperBound} exceeds 70k engineering budget`);
}

const chunks = splitSql(replayStatements);
const plan = {
  status: apply ? 'APPLYING' : 'READY',
  mode: repairMeta.mode,
  day,
  failure_received_at: failureReceivedAt,
  checkpoint_count: rows.length,
  checkpoint_fingerprint: localFingerprint,
  valid_events: state.validEvents,
  aliases: state.aliases.size,
  device_latest: state.deviceLatest.size,
  device_days: state.deviceDays.size,
  installs: state.installs.size,
  sessions: state.sessions.size,
  searches: state.searches.size,
  conservative_physical_write_upper_bound: conservativePhysicalWriteUpperBound,
  sql_statements: replayStatements.length,
  sql_chunks: chunks.length,
};
if (!apply) {
  console.log(JSON.stringify(plan, null, 2));
  process.exit(0);
}

for (let i = 0; i < chunks.length; i += 1) runWranglerFile(chunks[i], i + 1, chunks.length);
const after = await readOpsHealth();
if (after.operational_verified !== true || after?.integrity?.shadow_healthy !== true
  || after?.integrity?.status !== 'repaired_by_incremental_checkpoint') {
  throw new Error(`deep repair did not restore verification: ${after?.integrity?.status || 'unknown'} / verified=${after?.operational_verified}`);
}
console.log(JSON.stringify({
  ...plan,
  status: 'PASS_REPAIRED',
  operational_verified: true,
  integrity_status: after.integrity.status,
  latest_day: after.rows?.at?.(-1)?.day || null,
}, null, 2));
}
