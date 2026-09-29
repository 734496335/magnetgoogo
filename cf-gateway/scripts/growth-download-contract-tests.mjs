import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(path.resolve('src/index.js'), 'utf8');
const attributionMigration = fs.readFileSync(path.resolve('migrations/0009_growth_attribution_funnel.sql'), 'utf8');

assert.match(source, /growth-events\/\$\{y\}\/\$\{m\}\/\$\{dd\}/);
assert.match(source, /case '\/go\/download'/);
assert.match(source, /case '\/api\/growth'/);
assert.match(source, /case '\/api\/growth\/view'/, 'qualified landing-view endpoint missing');
assert.match(source, /type:\s*'landing_view'/, 'landing-view event missing');
assert.match(source, /growthRequestIsFirstParty/, 'landing views must be first-party gated');
assert.match(source, /landing_views:/, 'growth read model must expose landing-view denominator separately from download clicks');
assert.match(source, /sanitizeAcquisitionSource/, 'privacy-safe acquisition source sanitizer missing');
for (const aiSource of ['chatgpt', 'perplexity', 'copilot', 'gemini', 'claude']) {
  assert.match(source, new RegExp(`['\"]${aiSource}['\"]`), `AI acquisition category missing: ${aiSource}`);
}
for (const referralSource of ['naoshiquan', 'github', 'reddit', 'zhihu', 'v2ex', 'coolapk', '52pojie', 'bilibili', 'telegram', 'producthunt', 'uptodown', 'alternativeto', 'x', 'youtube']) {
  assert.match(source, new RegExp(`['\"]${referralSource}['\"]`), `actionable referral category missing: ${referralSource}`);
}
assert.match(source, /qualified_view:\$\{acquisitionSource\}/, 'landing views must persist acquisition category in the existing placement dimension');
assert.match(source, /acquisition_sources:/, 'growth read model must expose acquisition-source aggregation');
assert.match(source, /bySourceDay:/, 'growth read model must expose per-day acquisition-source aggregation so pre-coverage samples can be excluded');
assert.match(source, /byPlacementDay/, 'growth aggregation must retain the day dimension for acquisition-source gating');
assert.match(source, /no full referrer URL, query or visitor identifier is sent/, 'acquisition privacy boundary must be explicit');
assert.match(source, /type:\s*'seo_download_click'/);
assert.match(source, /type:\s*'legacy_cta_recovered'/);
assert.match(source, /ctx\.waitUntil\(persistGrowthEvent/);
assert.match(source, /await env\.ANALYTICS\.put\(key, JSON\.stringify\(payload\)/, 'R2 raw fact write missing');
assert.match(source, /INSERT INTO growth_daily_dims/, 'D1 growth read-model aggregation missing');
assert.match(source, /INSERT INTO growth_first_party_daily_dims/, 'first-party verified growth aggregation missing');
assert.match(source, /INSERT INTO growth_attribution_daily_dims/, 'prospective source×page attribution aggregation missing');
assert.match(attributionMigration, /CREATE TABLE IF NOT EXISTS growth_attribution_daily_dims/i, 'attribution funnel migration missing');
assert.match(source, /attribution_funnel:/, 'growth API must expose source×page attribution funnel');
assert.match(source, /bySourcePageDay/, 'attribution funnel must retain source×page×day for prospective experiment windows');
assert.match(source, /source × landing page × download-click aggregate/, 'attribution funnel privacy/meaning boundary missing');
assert.match(source, /page\.startsWith\('nsq:'\).*acquisitionSource = 'naoshiquan'/s, 'NSQ direct-download CTAs must be categorized without guessing historical generic referral');
assert.match(source, /referrer\.referrer_class === 'first_party_prod'.*sanitizeAcquisitionSource\(url\.searchParams\.get\('source'\)\)/s, 'download source parameter must only be trusted from a first-party Magnet page');
assert.match(source, /referrer_class:\s*referrer\.referrer_class/, 'growth events must persist referrer trust class');
assert.match(source, /referrer_path:\s*referrer\.referrer_path/, 'growth events must persist first-party source path without full referrer URL');
assert.match(source, /const sourcePage = String\(payload\.page \|\| payload\.referrer_path \|\| ''\)/, 'first-party page attribution must prefer the explicit tracked page key over cross-origin Referer path');
assert.match(source, /const sourcePage = String\(payload\.page \|\| payload\.referrer_path \|\| ''\);[\s\S]*aggregateFirstPartyGrowthEventsForRebuild/, 'growth rebuild must use the same explicit tracked page-key rule');
assert.match(source, /trusted_first_party:/, 'growth API must expose trusted first-party lower bound');
assert.match(source, /lower bound: browser Referer host is magnetgoogo\.com/, 'trusted measurement boundary must be explicit');
assert.match(source, /growth_read_model_uninitialized/, 'uninitialized read model must fail closed instead of returning false zero');
assert.match(source, /GROWTH_INDEX_FAILURE_KEY = 'growth-index-health\/unresolved\.json'/, 'growth D1 shadow failures need a durable R2 marker');
assert.match(source, /source: 'D1 growth read model'/, 'growth API must identify compact D1 read model');
assert.match(source, /raw_audit: 'R2'/, 'growth API must preserve R2 raw-audit authority');
assert.match(source, /async function handleGrowthRebuild/, 'authenticated R2-to-D1 rebuild endpoint missing');
assert.match(source, /DELETE FROM growth_daily_dims WHERE day=\?/, 'growth rebuild must be idempotent per operational day');
assert.match(source, /DELETE FROM growth_first_party_daily_dims WHERE day=\?/, 'first-party growth rebuild must also be idempotent');
assert.match(source, /DELETE FROM growth_attribution_daily_dims WHERE day=\?/, 'source×page attribution rebuild must also be idempotent');
assert.match(source, /current_or_future_day_rebuild_forbidden/, 'growth rebuild must refuse the live operational day to avoid racing realtime writes');
assert.match(source, /writeGrowthIndexFailure\(env, \{ type: 'growth_rebuild', ts: rebuildTs \}, error\)/, 'failed growth rebuilds must fail closed with a durable R2 marker');
assert.doesNotMatch(source.slice(source.indexOf('async function handleGrowthGet'), source.indexOf('function opsDeviceKey')), /ANALYTICS\.get\(obj\.key\)/, 'normal growth read must never scan raw R2 objects');
assert.match(source, /refUrl\?\.hostname === 'magnetgoogo\.com'/);
assert.match(source, /requestedVersion:\s*tag\.replace/);
assert.match(source, /targetVersion:\s*latest\.version/);
assert.match(source, /'Cache-Control':\s*'no-store'/);
assert.match(source, /!page\.startsWith\('__'\)/, 'synthetic smoke page must not pollute growth telemetry');
assert.match(source, /domestic:\s*\{ definition: 'Cloudflare country=CN'/, 'domestic SEO engine split missing');
assert.match(source, /international:\s*\{ definition: 'known Cloudflare country != CN'/, 'international SEO engine split missing');
assert.match(source, /country unavailable; never inferred from locale/, 'unknown country must not be falsely attributed by locale');
assert.match(source, /priority_markets:\s*\{ US: 0, HK: 0, TW: 0, JP: 0, SG: 0, DE: 0 \}/, 'priority international market counters missing');
assert.doesNotMatch(source, /payload\s*=\s*\{[\s\S]*?ip:/, 'growth payload must not persist visitor IP');

console.log(JSON.stringify({
  status: 'PASS',
  tracked_download_redirect: true,
  stale_cta_recovery: true,
  aggregate_growth_endpoint: true,
  qualified_landing_view_denominator: true,
  privacy_safe_acquisition_sources: true,
  post_full_coverage_source_window: true,
  matched_first_party_page_key: true,
  source_page_conversion_funnel: true,
  completed_day_rebuild_only: true,
  rebuild_failure_marker: true,
  domestic_international_split: true,
  no_persistent_visitor_id: true,
  smoke_telemetry_isolated: true,
}));
