import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(path.resolve('src/index.js'), 'utf8');
const wrangler = fs.readFileSync(path.resolve('wrangler.toml'), 'utf8');
const migration = fs.readFileSync(path.resolve('migrations/0001_analytics_ops_index.sql'), 'utf8');
const installUniqueMigration = fs.readFileSync(path.resolve('migrations/0002_ops_install_key_unique.sql'), 'utf8');
const latestDeviceMigration = fs.readFileSync(path.resolve('migrations/0003_ops_device_latest.sql'), 'utf8');
const latestDeviceDayMigration = fs.readFileSync(path.resolve('migrations/0004_ops_device_latest_day_index.sql'), 'utf8');
const growthNorthStarMigration = fs.readFileSync(path.resolve('migrations/0005_growth_north_star_indexes.sql'), 'utf8');
const canonicalIdentityMigration = fs.readFileSync(path.resolve('migrations/0006_ops_device_aliases_exact_authority.sql'), 'utf8');
const growthReadMigration = fs.readFileSync(path.resolve('migrations/0007_growth_read_model.sql'), 'utf8');
const firstPartyGrowthMigration = fs.readFileSync(path.resolve('migrations/0008_growth_first_party_verified.sql'), 'utf8');

assert.match(wrangler, /binding = "OPS_DB"/, 'OPS_DB D1 binding missing');
assert.match(wrangler, /database_name = "maggoogo-analytics-index"/, 'analytics D1 database binding missing');
assert.match(source, /async function indexAnalyticsEntryToOps\(env, entry\)/, 'ops shadow indexer missing');
assert.match(source, /async function handleEventsOpsDaily\(url, env\)/, 'ops daily read endpoint missing');
assert.match(source, /mode === 'ops_daily'/, 'ops daily route missing');
assert.match(source, /backfill_complete/, 'ops daily response must expose verified backfill state');
assert.match(source, /read_model: 'D1 exact operational index'/, 'ops daily response must identify D1 read model');
assert.match(source, /raw_audit: 'R2'/, 'ops daily response must identify R2 raw audit source');
assert.match(source, /ctx\.waitUntil\(retryOpsIndex\(env, entry\)\.catch/, 'D1 indexing must be asynchronous shadow work with bounded retry');
assert.match(source, /OPS_SHADOW_FAILURE_KEY = 'ops-index-health\/unresolved\.json'/, 'unresolved D1 shadow failures need an R2-backed integrity marker');
assert.match(source, /async function readOpsShadowIntegrity/, 'operational D1 reads must verify shadow integrity');
assert.match(source, /operational_verified: backfillComplete && integrity\.shadow_healthy === true/, 'ops read must expose fail-closed operational verification');
assert.match(source, /version_distribution:/, 'ops read must expose compact App version distribution');
assert.match(source, /exact_state_authority: true/, 'exact state tables must be the operational authority');
assert.match(source, /legacy_counter_diagnostic/, 'legacy counter drift must remain visible as diagnostic evidence');
assert.match(source, /rows: dailyRows/, 'public operational rows must come from exact state aggregation, never ops_daily counters');
assert.match(source, /north_star:/, 'ops read must expose device-level growth north star');
assert.match(source, /new_user_quality:/, 'ops read must expose New DSSU 1-7 day satisfied reuse cohorts');
assert.match(source, /reused_1_7d/, 'new-user quality must count any satisfied reuse on days +1 through +7');
assert.match(source, /search_value_funnel:/, 'ops read must expose search value funnel');
assert.match(source, /satisfied_without_completion/, 'search value funnel must preserve satisfied searches that never exhaust all sources');

const postStart = source.indexOf('async function handleEventsPost');
const postEnd = source.indexOf('async function handleEventsGet', postStart);
const postBlock = source.slice(postStart, postEnd);
const r2Write = postBlock.indexOf('await env.ANALYTICS.put');
const d1Shadow = postBlock.indexOf('ctx.waitUntil(retryOpsIndex');
assert(r2Write >= 0 && d1Shadow > r2Write, 'R2 durable write must happen before D1 shadow indexing');
assert.doesNotMatch(postBlock.slice(r2Write, d1Shadow), /await env\.OPS_DB/, 'D1 must never be part of the App-visible ingestion success boundary');
assert.match(source, /legacy_did \|\| data\?\.device_id \|\| data\?\.did/, 'cross-version legacy identity bridge missing');
assert.match(source, /function opsStrongDeviceAlias/, 'strong physical-device alias extraction missing');
assert.match(source, /INSERT INTO ops_device_aliases/, 'live canonical alias index missing');
assert.match(source, /INSERT INTO ops_device_days/, 'device-day exact index missing');
assert.match(source, /INSERT INTO ops_device_latest/, 'latest-device version index missing');
assert.match(source, /FROM ops_device_latest l LEFT JOIN ops_device_aliases/, 'version distribution must canonicalize duplicate legacy identities');
assert.match(source, /INSERT INTO ops_install_days/, 'install-day exact index missing');
assert.match(source, /ON CONFLICT\(install_key\)/, 'install_id must remain globally unique across days');
assert.match(source, /INSERT OR IGNORE INTO ops_session_days/, 'session-day exact index missing');
assert.match(source, /INSERT INTO ops_searches/, 'search lifecycle exact index missing');
assert.match(source, /opsExecuteStatementGroups/, 'explicit idempotent D1 compact-state transaction groups missing');
assert.match(source, /WHERE excluded\.first_event_ts<ops_device_days\.first_event_ts/, 'repeat device-day batches must be true no-op writes when state does not change');
assert.match(source, /excluded\.last_seen_day>ops_device_latest\.last_seen_day/, 'latest-device index must avoid same-day repeat writes');
assert.match(source, /excluded\.action>ops_searches\.action/, 'repeat search lifecycle batches must be true no-op writes unless semantic state advances');
const indexStart = source.indexOf('async function indexAnalyticsEntryToOps');
const indexEnd = source.indexOf('const OPS_DAILY_SNAPSHOT_TTL_SECONDS', indexStart);
const indexBlock = source.slice(indexStart, indexEnd);
assert.doesNotMatch(indexBlock, /(?:INSERT INTO|UPDATE) ops_daily/, 'legacy ops_daily counters are rebuild-only diagnostics and must not consume live D1 writes');
assert.match(source, /WHERE ops_device_aliases\.canonical_key<>excluded\.canonical_key/, 'stable canonical alias batches must be true no-op writes');
assert.doesNotMatch(migration, /CREATE\s+TRIGGER/i, 'D1 migration must stay trigger-free to avoid Wrangler statement-splitting failures');
assert.match(installUniqueMigration, /CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_install_days_install_key/i, 'global install_id uniqueness migration missing');
assert.match(latestDeviceMigration, /CREATE TABLE IF NOT EXISTS ops_device_latest/i, 'latest-device D1 migration missing');
assert.match(latestDeviceMigration, /idx_ops_device_latest_last_seen_ts/i, 'latest-device timestamp index missing');
assert.match(latestDeviceDayMigration, /idx_ops_device_latest_last_seen_day/i, 'latest-device operational-day index missing');
assert.match(growthNorthStarMigration, /idx_ops_device_days_device_day_action/i, 'growth north-star device/day/action index missing');
assert.match(growthNorthStarMigration, /idx_ops_searches_submitted_action_completed/i, 'search satisfaction index missing');
assert.match(canonicalIdentityMigration, /CREATE TABLE IF NOT EXISTS ops_device_aliases/i, 'canonical device alias migration missing');
assert.match(canonicalIdentityMigration, /CREATE VIEW IF NOT EXISTS ops_device_days_exact/i, 'exact canonical device-day view missing');
assert.match(canonicalIdentityMigration, /conflict INTEGER/i, 'ambiguous aliases must remain explicit and fail-open to separate identities');
assert.match(growthReadMigration, /CREATE TABLE IF NOT EXISTS growth_daily_dims/i, 'compact growth D1 read model migration missing');
assert.match(growthReadMigration, /PRIMARY KEY \([\s\S]*day,[\s\S]*event_type,[\s\S]*page,[\s\S]*placement/i, 'growth read-model dimensions must be idempotently keyed');
assert.match(growthReadMigration, /idx_growth_daily_dims_page_day/i, 'growth page/day opportunity index missing');
assert.match(firstPartyGrowthMigration, /CREATE TABLE IF NOT EXISTS growth_first_party_daily_dims/i, 'first-party verified growth table missing');
assert.match(firstPartyGrowthMigration, /source_page TEXT NOT NULL/i, 'first-party measurement must key by actual referrer page');
assert.match(source, /function growthReferrerClass\(request\)/, 'first-party referrer classifier missing');
assert.match(source, /referrer_class: 'first_party_prod'/, 'production first-party classification missing');
assert.match(source, /growthFirstPartyAggregateStatement/, 'first-party D1 aggregate writer missing');
assert.match(source, /trusted_first_party:/, 'growth API must expose trusted first-party lower bound separately');

console.log(JSON.stringify({
  status: 'PASS',
  raw_source_of_truth: 'R2',
  ops_index: 'D1 shadow',
  admin_read_model: 'canonical exact state + alias-aware latest-device version index',
  shadow_integrity_fail_closed: true,
  legacy_payload_compatible: true,
}));
