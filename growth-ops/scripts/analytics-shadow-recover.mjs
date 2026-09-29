import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const root = path.resolve(import.meta.dirname, '..', '..');
const runtimeDir = path.join(root, 'growth-ops', 'runtime');
const statusPath = path.join(runtimeDir, 'analytics-shadow-recovery.json');
const lockPath = path.join(runtimeDir, 'analytics-shadow-recovery.lock');
const apply = process.argv.includes('--apply');
const skipRefresh = process.argv.includes('--skip-refresh');
const gateway = process.env.GROWTH_GATEWAY_URL || 'https://api.naoshiquan.com';
const adminSecret = String(process.env.ADMIN_SECRET || '');

fs.mkdirSync(runtimeDir, { recursive: true });

function writeStatus(status, extra = {}) {
  const payload = {
    schema_version: 1,
    status,
    mode: apply ? 'apply' : 'plan',
    checked_at: new Date().toISOString(),
    ...extra,
  };
  fs.writeFileSync(statusPath, JSON.stringify(payload, null, 2), 'utf8');
  console.log(JSON.stringify(payload, null, 2));
  return payload;
}

function nextUtcResetIso(nowMs = Date.now()) {
  const now = new Date(nowMs);
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)).toISOString();
}

function utcDay(value) {
  const ms = Date.parse(String(value || ''));
  return Number.isFinite(ms) ? new Date(ms).toISOString().slice(0, 10) : '';
}

function utcDayRange(startDay, endDay, maxDays = 3) {
  const start = Date.parse(`${startDay}T00:00:00Z`);
  const end = Date.parse(`${endDay}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start > end) throw new Error('invalid recovery day range');
  const days = [];
  for (let ts = start; ts <= end; ts += 86400_000) {
    days.push(new Date(ts).toISOString().slice(0, 10));
    if (days.length > maxDays) throw new Error(`recovery window exceeds ${maxDays} receive days; require explicit deep repair`);
  }
  return days;
}

function isSameUtcDayQuotaBlocked(failureClass, failureDay, currentUtcDay) {
  return (failureClass === 'd1_daily_row_write_quota' || failureClass === 'd1_daily_row_read_quota')
    && failureDay === currentUtcDay;
}

if (process.argv.includes('--self-test')) {
  assert.deepEqual(utcDayRange('2026-09-02', '2026-09-03'), ['2026-09-02', '2026-09-03']);
  assert.throws(() => utcDayRange('2026-09-01', '2026-09-04'), /exceeds 3/);
  assert.equal(utcDay('2026-09-02T23:59:00Z'), '2026-09-02');
  assert.equal(nextUtcResetIso(Date.parse('2026-09-02T23:59:00Z')), '2026-09-03T00:00:00.000Z');
  assert.equal(isSameUtcDayQuotaBlocked('d1_daily_row_write_quota', '2026-09-02', '2026-09-02'), true);
  assert.equal(isSameUtcDayQuotaBlocked('d1_daily_row_write_quota', '2026-09-02', '2026-09-03'), false);
  assert.equal(isSameUtcDayQuotaBlocked('d1_shadow_index_failure', '2026-09-02', '2026-09-02'), false);
  console.log(JSON.stringify({ status: 'PASS', quota_reset_guard: true, bounded_repair_window: true }));
  process.exit(0);
}

function runNode(args, label) {
  const result = spawnSync(process.execPath, args, {
    cwd: root,
    stdio: 'inherit',
    timeout: 15 * 60_000,
    windowsHide: true,
    env: { ...process.env, NODE_OPTIONS: '--dns-result-order=ipv4first' },
  });
  if (result?.error?.code === 'ETIMEDOUT') throw new Error(`${label} timed out after 15m`);
  if (result.status !== 0) throw new Error(`${label} failed: exit=${result.status ?? 'null'} signal=${result.signal || 'none'}`);
}

async function readOpsHealth() {
  if (!adminSecret) throw new Error('ADMIN_SECRET is required');
  let lastNetworkError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(`${gateway}/api/events?mode=ops_daily&days=31`, {
        headers: { 'X-Admin-Secret': adminSecret, 'Cache-Control': 'no-cache' },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(`ops_daily HTTP ${response.status}: ${payload?.error || payload?.message || 'unknown'}`);
      return payload;
    } catch (error) {
      const message = String(error?.message || error);
      if (/^ops_daily HTTP /.test(message)) throw error;
      lastNetworkError = error;
      if (attempt < 3) await new Promise((resolve) => setTimeout(resolve, 1_500 * attempt));
    }
  }
  throw new Error(`ops_daily network read failed after 3 attempts: ${String(lastNetworkError?.message || lastNetworkError || 'unknown')}`);
}

async function refreshVerifiedR2Cache() {
  const require = createRequire(import.meta.url);
  process.env.DISABLE_ANALYTICS_BACKGROUND_REFRESH = 'true';
  const admin = require(path.join(root, 'admin-server', 'server.js'));
  admin.loadCacheFromFile();
  const result = await admin.refreshAnalyticsCache({ throwOnError: true, returnMeta: true });
  const data = result?.data || result;
  if (data?._inventoryVerified !== true || Number(data?._inventoryDays) !== 31) {
    throw new Error('R2 refresh did not produce a verified 31-day cache');
  }
  return {
    cached_at: data._cachedAt || null,
    total_batches: Number(data._totalLocalBatches || 0),
    repaired_days: Array.isArray(data._repairedDays) ? data._repairedDays : [],
  };
}

function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function acquireRecoveryLock() {
  fs.mkdirSync(runtimeDir, { recursive: true });
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = fs.openSync(lockPath, 'wx');
      fs.writeFileSync(fd, JSON.stringify({ pid: process.pid, started_at: new Date().toISOString() }), 'utf8');
      fs.closeSync(fd);
      return { acquired: true };
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error;
      let existing = null;
      try { existing = JSON.parse(fs.readFileSync(lockPath, 'utf8')); } catch { /* stale/corrupt lock */ }
      if (processAlive(Number(existing?.pid))) {
        return { acquired: false, existing };
      }
      try { fs.unlinkSync(lockPath); } catch { /* retry once */ }
    }
  }
  throw new Error('Unable to acquire analytics shadow recovery lock');
}

function releaseRecoveryLock() {
  try {
    const existing = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
    if (Number(existing?.pid) === process.pid) fs.unlinkSync(lockPath);
  } catch { /* best effort */ }
}

async function main() {
  const before = await readOpsHealth();
  if (before.operational_verified === true && before?.integrity?.shadow_healthy === true) {
    writeStatus('PASS_NOOP', {
      operational_verified: true,
      integrity_status: before.integrity.status,
      source_batch_count: Number(before?.backfill?.sourceBatchCount || 0),
    });
    return;
  }
  if (before?.integrity?.status !== 'unresolved_shadow_failure') {
    throw new Error(`unsupported shadow state: ${before?.integrity?.status || 'unknown'}`);
  }

  const failureReceivedAt = before.integrity.last_failure_received_at || before.integrity.last_failure_at;
  const failureDay = utcDay(failureReceivedAt);
  const currentUtcDay = new Date().toISOString().slice(0, 10);
  if (!failureDay) throw new Error('unresolved shadow marker does not expose a valid failure receive time');
  const repairDays = utcDayRange(failureDay, currentUtcDay);
  const failureClass = String(before.integrity.failure_class || 'd1_shadow_index_failure');
  const quotaBlockedSameUtcDay = isSameUtcDayQuotaBlocked(failureClass, failureDay, currentUtcDay);

  if (quotaBlockedSameUtcDay) {
    writeStatus('BLOCKED_PLATFORM_QUOTA', {
      operational_verified: false,
      integrity_status: before.integrity.status,
      failure_class: failureClass,
      failure_received_at: failureReceivedAt,
      repair_days: repairDays,
      retry_after_utc: nextUtcResetIso(),
      reason: 'D1 Free daily quota is still exhausted in the same UTC quota day; fail closed until reset.',
    });
    process.exitCode = 2;
    return;
  }

  if (!apply) {
    writeStatus('READY', {
      operational_verified: false,
      integrity_status: before.integrity.status,
      failure_class: failureClass,
      failure_received_at: failureReceivedAt,
      repair_days: repairDays,
      requires_verified_r2_refresh: !skipRefresh,
    });
    return;
  }

  const refresh = skipRefresh ? null : await refreshVerifiedR2Cache();
  for (const day of repairDays) {
    runNode(['admin-server/scripts/repair-analytics-day.js', day], `R2 checkpoint ${day}`);
    runNode(['cf-gateway/scripts/repair-analytics-ops-day.mjs', `--day=${day}`, '--apply'], `D1 incremental repair ${day}`);
  }

  const after = await readOpsHealth();
  if (after.operational_verified !== true || after?.integrity?.shadow_healthy !== true) {
    throw new Error(`shadow repair did not restore verification: ${after?.integrity?.status || 'unknown'}`);
  }
  writeStatus('PASS_REPAIRED', {
    operational_verified: true,
    integrity_status: after.integrity.status,
    failure_class: failureClass,
    failure_received_at: failureReceivedAt,
    repaired_days: repairDays,
    verified_r2_refresh: refresh,
    source_batch_count: Number(after?.backfill?.sourceBatchCount || 0),
  });
}

const lock = acquireRecoveryLock();
if (!lock.acquired) {
  console.log(JSON.stringify({
    schema_version: 1,
    status: 'SKIP_ALREADY_RUNNING',
    mode: apply ? 'apply' : 'plan',
    checked_at: new Date().toISOString(),
    active_pid: Number(lock.existing?.pid || 0) || null,
    active_started_at: lock.existing?.started_at || null,
  }, null, 2));
  process.exitCode = 3;
} else {
  main().catch((error) => {
    writeStatus('ERROR', { error: String(error?.message || error).slice(0, 500) });
    process.exitCode = 1;
  }).finally(() => {
    releaseRecoveryLock();
  });
}
