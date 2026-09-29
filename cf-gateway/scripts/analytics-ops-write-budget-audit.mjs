import fs from 'node:fs';
import path from 'node:path';
import { buildOpsState, expectedCanonicalDailyRows } from './analytics-ops-backfill-lib.mjs';

const root = path.resolve(import.meta.dirname, '..', '..');
const batchesPath = path.join(root, 'admin-server', 'cache', 'batches.json');
const dayArg = process.argv.find((arg) => arg.startsWith('--day='));
const day = dayArg ? dayArg.slice('--day='.length) : '';
if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error('Usage: node scripts/analytics-ops-write-budget-audit.mjs --day=YYYY-MM-DD');

const batches = JSON.parse(fs.readFileSync(batchesPath, 'utf8'));
if (!Array.isArray(batches)) throw new Error('admin-server/cache/batches.json must be an array');
const prefix = `events/${day.replaceAll('-', '/')}/`;
const rows = batches.filter((row) => String(row?.id || '').startsWith(prefix));
if (rows.length === 0) throw new Error(`No verified receive-day batches found for ${day}`);

const devices = new Set();
const sessions = new Set();
const aliasKeys = new Map();
const searchIds = new Set();
const submittedIds = new Set();
const completedIds = new Set();
const actionIds = new Set();
const operationalDeviceDays = new Set();
const searchedDeviceDays = new Set();
const resultDeviceDays = new Set();
const actionDeviceDays = new Set();
let searchUpsertGroups = 0;
let sessionGroups = 0;
let strongAliasBatches = 0;

function opsDay(ts) {
  return new Date(Number(ts) + 8 * 3600_000).toISOString().slice(0, 10);
}

for (const batch of rows) {
  const deviceKey = String(batch?.legacy_did || batch?.device_id || batch?.did || '').trim();
  if (deviceKey) devices.add(deviceKey);
  if (batch?.session_id) {
    sessions.add(String(batch.session_id));
    sessionGroups += 1;
  }
  if (Number(batch?.schema_v || 0) >= 2 && batch?.device_id_kind === 'android_id_hash'
    && batch?.legacy_did && batch?.device_id && batch.legacy_did !== batch.device_id) {
    strongAliasBatches += 1;
    const alias = String(batch.legacy_did);
    const canonical = String(batch.device_id);
    const previous = aliasKeys.get(alias);
    aliasKeys.set(alias, previous && previous !== canonical ? '__CONFLICT__' : canonical);
  }

  const batchSearchIds = new Set();
  for (const event of batch?.events || []) {
    const ts = Number(event?.ts);
    if (Number.isFinite(ts) && ts > 0 && deviceKey) {
      const key = `${opsDay(ts)}\u0000${deviceKey}`;
      operationalDeviceDays.add(key);
      if (event.e === 'search_submitted') searchedDeviceDays.add(key);
      if (event.e === 'search_completed' && Number(event.result_count || 0) > 0) resultDeviceDays.add(key);
      if (event.e === 'copy_magnet' || event.e === 'open_magnet') actionDeviceDays.add(key);
    }
    const searchId = String(event?.search_id || '').trim();
    if (!searchId) continue;
    searchIds.add(searchId);
    batchSearchIds.add(searchId);
    if (event.e === 'search_submitted') submittedIds.add(searchId);
    if (event.e === 'search_completed') completedIds.add(searchId);
    if (event.e === 'copy_magnet' || event.e === 'open_magnet') actionIds.add(searchId);
  }
  searchUpsertGroups += batchSearchIds.size;
}

// D1 bills secondary-index maintenance as additional rows written. These are
// conservative planning estimates, not a replacement for Cloudflare Row Metrics.
// The formulas intentionally over-count state transitions when multiple flags
// advance in one SQL statement so the safety gate errs on the safe side.
const removedLegacyCounterRows = operationalDeviceDays.size + searchedDeviceDays.size + resultDeviceDays.size + actionDeviceDays.size
  + sessions.size + submittedIds.size + completedIds.size;
const semanticSearchTransitions = searchIds.size + completedIds.size + actionIds.size;
const duplicateSearchGroupsAvoided = Math.max(0, searchUpsertGroups - semanticSearchTransitions);
const currentSchemaEstimate = {
  alias_mapping_rows: aliasKeys.size * 2, // table + canonical index; worst case each alias is new/changed
  device_latest_rows: devices.size * 3, // table + last_seen_ts + last_seen_day indexes
  device_day_rows: (operationalDeviceDays.size + searchedDeviceDays.size + resultDeviceDays.size + actionDeviceDays.size) * 2,
  session_rows: sessions.size,
  search_state_rows: semanticSearchTransitions * 4, // table + 3 current secondary indexes
};
currentSchemaEstimate.total = Object.values(currentSchemaEstimate).reduce((sum, value) => sum + value, 0);

const fullState = buildOpsState(batches);
const fullRebuildLowerBound = {
  aliases: fullState.aliases.size * 2,
  device_latest: fullState.deviceLatest.size * 3,
  device_days: fullState.deviceDays.size * 2,
  installs: fullState.installs.size * 2,
  sessions: fullState.sessions.size,
  searches: fullState.searches.size * 4,
  ops_daily: expectedCanonicalDailyRows(fullState).length,
  backfill_meta: 1,
};
fullRebuildLowerBound.total = Object.values(fullRebuildLowerBound).reduce((sum, value) => sum + value, 0);

const freeDailyWriteLimit = 100_000;
const engineeringBudget = 70_000;
const activeDeviceEstimate = Math.max(1, devices.size);
const safeLinearDau = Math.floor(activeDeviceEstimate * engineeringBudget / Math.max(1, currentSchemaEstimate.total));
const scale5000 = Math.round(currentSchemaEstimate.total * (5000 / activeDeviceEstimate));
const scale5000Month = scale5000 * 30;

console.log(JSON.stringify({
  schema_version: 1,
  status: 'PASS',
  note: 'Planning estimate from verified local R2 cache; Cloudflare dashboard/GraphQL Row Metrics remains billing authority.',
  receive_day: day,
  observed: {
    batches: rows.length,
    devices: devices.size,
    session_groups: sessionGroups,
    unique_sessions: sessions.size,
    strong_alias_batches: strongAliasBatches,
    unique_alias_keys: aliasKeys.size,
    search_upsert_groups_before_noop_guard: searchUpsertGroups,
    unique_search_ids: searchIds.size,
    submitted_search_ids: submittedIds.size,
    completed_search_ids: completedIds.size,
    action_search_ids: actionIds.size,
    operational_device_days: operationalDeviceDays.size,
  },
  optimized_steady_state_conservative_rows_written: currentSchemaEstimate,
  hot_path_savings: {
    legacy_ops_daily_rows_removed: removedLegacyCounterRows,
    duplicate_alias_batch_rows_avoided_upper_bound: Math.max(0, strongAliasBatches - aliasKeys.size) * 2,
    duplicate_search_upsert_groups_avoided_upper_bound: duplicateSearchGroupsAvoided,
    duplicate_search_rows_avoided_upper_bound: duplicateSearchGroupsAvoided * 4,
  },
  free_tier: {
    daily_rows_written_limit: freeDailyWriteLimit,
    engineering_budget_70pct: engineeringBudget,
    observed_day_budget_pct: Math.round(currentSchemaEstimate.total / freeDailyWriteLimit * 1000) / 10,
    conservative_linear_safe_dau_at_same_intensity: safeLinearDau,
    projected_rows_written_at_5000_dau_same_intensity: scale5000,
    five_thousand_dau_free_tier_safe: scale5000 <= engineeringBudget,
  },
  paid_tier: {
    included_rows_written_month: 50_000_000,
    projected_rows_written_at_5000_dau_30d: scale5000Month,
    five_thousand_dau_within_included_writes: scale5000Month <= 50_000_000,
  },
  full_rebuild_empty_db_lower_bound: fullRebuildLowerBound,
}, null, 2));
