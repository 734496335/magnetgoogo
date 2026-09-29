import fs from 'node:fs';
import path from 'node:path';
import { estimateD1WriteCapacity } from './d1-write-capacity.mjs';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const OUT = path.join(ROOT, 'docs', 'project-nebula', '_growth_kpi.json');
const OPS_URL = 'https://api.naoshiquan.com/api/events?mode=ops_daily&days=31';
const GROWTH_URL = 'https://api.naoshiquan.com/api/growth?days=28';
const PARTIAL_DAYS = new Set(['2026-08-26', '2026-08-27', '2026-08-28', '2026-08-29']);

function operationalDay(ts = Date.now()) {
  return new Date(ts + 8 * 3600_000).toISOString().slice(0, 10);
}

async function fetchJson(url, secret) {
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'X-Admin-Secret': secret,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`HTTP ${response.status} ${new URL(url).pathname}: ${data.error || data.detail || 'unknown'}`);
  return data;
}

function aggregateNorthStar(ops) {
  const byDay = new Map();
  for (const row of ops?.north_star?.rows || []) {
    const day = String(row.day || '');
    if (!day) continue;
    if (!byDay.has(day)) byDay.set(day, { new_devices: 0, new_dssu: 0, dssu: 0, search_devices: 0 });
    const target = byDay.get(day);
    target.new_devices += Number(row.first_observed_devices || 0);
    target.new_dssu += Number(row.new_dssu || 0);
    target.dssu += Number(row.satisfied_devices || 0);
    target.search_devices += Number(row.search_devices || 0);
  }
  return byDay;
}

function mean(values) {
  return values.length ? Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10 : null;
}

function atomicWriteJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
  try {
    fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
    fs.renameSync(tmp, file);
  } finally {
    try { if (fs.existsSync(tmp)) fs.unlinkSync(tmp); } catch { /* best effort */ }
  }
}

async function main() {
  const secret = String(process.env.ADMIN_SECRET || '').trim();
  if (!secret) throw new Error('ADMIN_SECRET missing; refusing to emit zero/guessed growth metrics');
  const [ops, growth] = await Promise.all([fetchJson(OPS_URL, secret), fetchJson(GROWTH_URL, secret)]);
  if (ops.operational_verified !== true) throw new Error('D1 operational read is not verified; refusing to replace last-known-good KPI');
  if (growth.available !== true || growth.complete !== true) throw new Error('growth read model unavailable/incomplete; refusing to replace last-known-good KPI');

  const today = operationalDay();
  const north = aggregateNorthStar(ops);
  const completeRows = (ops.rows || []).filter((row) => row.day && row.day < today && !PARTIAL_DAYS.has(row.day));
  const latest7Rows = completeRows.slice(-7);
  const latestComplete = completeRows.at(-1) || null;
  const current = (ops.rows || []).find((row) => row.day === today) || null;
  const daily = latest7Rows.map((row) => {
    const ns = north.get(row.day) || {};
    return {
      day: row.day,
      dau: Number(row.active_devices || 0),
      search_devices: Number(row.search_devices || 0),
      dssu: Number(row.action_devices || 0),
      new_devices: Number(ns.new_devices || 0),
      new_dssu: Number(ns.new_dssu || 0),
    };
  });

  const qualityRows = (ops?.north_star?.new_user_quality?.rows || [])
    .filter((row) => row.matured === true && !PARTIAL_DAYS.has(row.first_day))
    .slice(-8);
  const qualityNew = qualityRows.reduce((sum, row) => sum + Number(row.new_dssu || 0), 0);
  const qualityReused = qualityRows.reduce((sum, row) => sum + Number(row.reused_1_7d || 0), 0);
  const reusePct = qualityNew > 0 ? Math.round((qualityReused / qualityNew) * 1000) / 10 : null;
  const trusted = growth.trusted_first_party || {};
  const landing = growth.landing_views || {};
  const topPages = Object.entries(growth.byPage || {})
    .map(([page, clicks]) => ({ page, clicks: Number(clicks || 0) }))
    .sort((a, b) => b.clicks - a.clicks)
    .slice(0, 15);

  const latestDay = latestComplete?.day || null;
  const latestNs = latestDay ? north.get(latestDay) || {} : {};
  const d1WriteCapacity = estimateD1WriteCapacity(ops, latestComplete);
  const report = {
    schema_version: 3,
    generated_at: new Date().toISOString(),
    authority: {
      app: 'D1 exact canonical-device-v2',
      growth: 'D1 compact growth read model',
      raw_audit: 'R2',
      operational_verified: true,
    },
    excluded_partial_days: [...PARTIAL_DAYS].sort(),
    latest_complete: latestComplete ? {
      day: latestDay,
      dau: Number(latestComplete.active_devices || 0),
      search_devices: Number(latestComplete.search_devices || 0),
      dssu: Number(latestComplete.action_devices || 0),
      new_devices: Number(latestNs.new_devices || 0),
      new_dssu: Number(latestNs.new_dssu || 0),
    } : null,
    current_partial: {
      day: today,
      dau_lower_bound: Number(current?.active_devices || 0),
      dssu_lower_bound: Number(current?.action_devices || 0),
      label: 'partial current operational day; never compare as a completed day',
    },
    verified_complete_last7: daily,
    averages_last7_complete: {
      dau: mean(daily.map((row) => row.dau)),
      new_devices: mean(daily.map((row) => row.new_devices)),
      new_dssu: mean(daily.map((row) => row.new_dssu)),
      search_activation_pct: mean(daily.filter((row) => row.dau > 0).map((row) => 100 * row.search_devices / row.dau)),
      dssu_per_dau_pct: mean(daily.filter((row) => row.dau > 0).map((row) => 100 * row.dssu / row.dau)),
    },
    d1_write_capacity: d1WriteCapacity,
    new_dssu_quality: {
      definition: 'first-observed satisfied device performs another Magnet Action on any of days +1 through +7',
      mature_through: ops?.north_star?.new_user_quality?.mature_through || null,
      cohorts: qualityRows,
      weighted_reuse_1_7d_pct: reusePct,
    },
    website_growth: {
      download_clicks: Number(growth.total || 0),
      trusted_first_party_clicks: Number(trusted.total || 0),
      qualified_landing_views: Number(landing.total || 0),
      landing_view_measurement_start_at: landing.measurement_start_at || null,
      trusted_measurement_start_at: trusted.measurement_start_at || null,
      top_download_pages_diagnostic: topPages,
    },
    growth_objective: 'increase verified New Device and New DSSU while preserving 1-7 day satisfied reuse; do not optimize raw traffic alone',
  };
  atomicWriteJson(OUT, report);
  console.log('=== MagnetGoogo Growth KPI — exact authority ===');
  console.log(`Latest complete: ${JSON.stringify(report.latest_complete)}`);
  console.log(`Current partial: ${JSON.stringify(report.current_partial)}`);
  console.log(`D1 write budget: ${d1WriteCapacity ? `${d1WriteCapacity.estimated_rows_written}/${d1WriteCapacity.engineering_budget_rows_written} engineering rows; safe DAU~${d1WriteCapacity.conservative_linear_safe_dau}` : 'n/a'}`);
  console.log(`New DSSU 1-7d reuse: ${reusePct}%`);
  console.log(`Website clicks/trusted/views: ${report.website_growth.download_clicks}/${report.website_growth.trusted_first_party_clicks}/${report.website_growth.qualified_landing_views}`);
  console.log(`Written: ${OUT}`);
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exitCode = 1;
});
