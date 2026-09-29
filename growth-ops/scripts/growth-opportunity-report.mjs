import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const DEFAULT_GROWTH_URL = 'https://api.naoshiquan.com/api/growth?days=28';
const DEFAULT_OPS_URL = 'https://api.naoshiquan.com/api/events?mode=ops_daily&days=31';
const DEFAULT_GSC = path.join(ROOT, 'search-console', 'latest.json');
const DEFAULT_GSC_STATUS = path.join(ROOT, 'search-console', 'ingest-status.json');
const DEFAULT_EXPERIMENTS = path.join(ROOT, 'experiments.json');
const DEFAULT_OUTPUT = path.join(ROOT, 'latest-opportunity-report.json');
const SITE_DIR = path.resolve(ROOT, '..', 'magnetgoogo-site');

function loadDotEnv() {
  const file = path.join(path.resolve(import.meta.dirname, '..', '..'), '.env');
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    if (!line || /^\s*#/.test(line)) continue;
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match || process.env[match[1]] !== undefined) continue;
    process.env[match[1]] = match[2].trim();
  }
}

function parseArgs(argv) {
  const out = {
    growthUrl: DEFAULT_GROWTH_URL,
    opsUrl: DEFAULT_OPS_URL,
    gsc: DEFAULT_GSC,
    experiments: DEFAULT_EXPERIMENTS,
    output: DEFAULT_OUTPUT,
    write: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--growth-url') out.growthUrl = argv[++i];
    else if (arg === '--ops-url') out.opsUrl = argv[++i];
    else if (arg === '--gsc') out.gsc = path.resolve(argv[++i]);
    else if (arg === '--experiments') out.experiments = path.resolve(argv[++i]);
    else if (arg === '--out') out.output = path.resolve(argv[++i]);
    else if (arg === '--write') out.write = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return out;
}

function readJsonIfExists(file) {
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
}

async function fetchJson(url) {
  const parsed = new URL(url);
  const headers = { accept: 'application/json' };
  if (parsed.hostname === 'api.naoshiquan.com') {
    const secret = String(process.env.ADMIN_SECRET || '').trim();
    if (!secret) throw new Error('ADMIN_SECRET missing for production growth read');
    headers['X-Admin-Secret'] = secret;
  }
  const response = await fetch(url, { headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${parsed.pathname}_http_${response.status}:${data.error || data.message || 'unknown'}`);
  return data;
}

function aggregateSearchConsole(snapshot) {
  if (!snapshot || snapshot.status !== 'OK' || !Array.isArray(snapshot.rows)) return { rows: [], cannibalization: [] };
  const dims = snapshot.dimensions || [];
  const index = Object.fromEntries(dims.map((name, i) => [name, i]));
  const groups = new Map();
  const queryPages = new Map();
  for (const row of snapshot.rows) {
    const keys = row.keys || [];
    const query = String(keys[index.query] || '').trim();
    const page = String(keys[index.page] || '').trim();
    if (!query || !page) continue;
    const impressions = Number(row.impressions || 0);
    const clicks = Number(row.clicks || 0);
    const position = Number(row.position || 0);
    const key = `${query}\u0000${page}`;
    const current = groups.get(key) || { query, page, impressions: 0, clicks: 0, weightedPosition: 0 };
    current.impressions += impressions;
    current.clicks += clicks;
    current.weightedPosition += position * impressions;
    groups.set(key, current);
    if (!queryPages.has(query)) queryPages.set(query, new Map());
    queryPages.get(query).set(page, (queryPages.get(query).get(page) || 0) + impressions);
  }
  const rows = [...groups.values()].map((row) => ({
    query: row.query,
    page: row.page,
    impressions: row.impressions,
    clicks: row.clicks,
    ctr: row.impressions ? row.clicks / row.impressions : 0,
    position: row.impressions ? row.weightedPosition / row.impressions : 0,
  }));
  const cannibalization = [];
  for (const [query, pages] of queryPages) {
    const ranked = [...pages.entries()].filter(([, impressions]) => impressions >= 10).sort((a, b) => b[1] - a[1]);
    if (ranked.length >= 2) {
      cannibalization.push({ query, pages: ranked.slice(0, 5).map(([page, impressions]) => ({ page, impressions })) });
    }
  }
  cannibalization.sort((a, b) => b.pages.reduce((n, p) => n + p.impressions, 0) - a.pages.reduce((n, p) => n + p.impressions, 0));
  return { rows, cannibalization };
}

function rankOpportunities(rows) {
  const nearBreakthrough = rows
    .filter((r) => r.impressions >= 50 && r.position >= 4 && r.position <= 15)
    .map((r) => ({ ...r, opportunity: 'O1_NEAR_BREAKTHROUGH', score: Math.round(r.impressions * (16 - r.position) * 100) / 100 }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);
  const lowCtr = rows
    .filter((r) => r.impressions >= 50 && r.position > 0 && r.position <= 10 && r.ctr < 0.03)
    .map((r) => ({ ...r, opportunity: 'O2_LOW_CTR', score: Math.round(r.impressions * (0.03 - r.ctr) * 10000) / 100 }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);
  return { nearBreakthrough, lowCtr };
}

function sumPageFromDay(matrix, page, startDay) {
  let total = 0;
  for (const [day, pages] of Object.entries(matrix || {})) {
    if (day < startDay) continue;
    total += Number(pages?.[page] || 0);
  }
  return total;
}

function evaluateExperiments(registry, growth) {
  const trusted = growth?.trusted_first_party || {};
  const landing = growth?.landing_views || {};
  return (registry?.experiments || []).map((experiment) => {
    if (experiment.id !== 'EXP-CRO-HOME-TRUST-001') {
      return { id: experiment.id, status: experiment.status || 'UNKNOWN' };
    }
    if (experiment.status && experiment.status !== 'BASELINE_COLLECTION') {
      return {
        id: experiment.id,
        status: experiment.status,
        baseline_start_day: experiment.baseline_start_day || null,
        invalidated_baseline: experiment.invalidated_baseline || null,
      };
    }
    const startDay = String(experiment.baseline_start_day || '9999-12-31');
    const pageKey = String(experiment.baseline_gate?.page_key || 'home');
    const views = sumPageFromDay(landing.byPageDay, pageKey, startDay);
    const clicks = sumPageFromDay(trusted.byPageDay, pageKey, startDay);
    const minViews = Number(experiment.baseline_gate?.minimum_qualified_views || 0);
    const minClicks = Number(experiment.baseline_gate?.minimum_clicks || 0);
    const ready = views >= minViews && clicks >= minClicks;
    return {
      id: experiment.id,
      status: ready ? 'READY_FOR_BASELINE_FREEZE' : 'BASELINE_COLLECTION',
      baseline_start_day: startDay,
      page_key: pageKey,
      qualified_views: views,
      trusted_clicks: clicks,
      observed_ctr: views > 0 ? Math.round((clicks / views) * 10000) / 10000 : null,
      required: { qualified_views: minViews, trusted_clicks: minClicks },
    };
  });
}

function attributionCoverage() {
  const sitemapPath = path.join(SITE_DIR, 'sitemap.xml');
  if (!fs.existsSync(sitemapPath)) return { status: 'UNKNOWN', tracked: 0, indexable: 0, coverage_pct: 0 };
  const xml = fs.readFileSync(sitemapPath, 'utf8');
  const urls = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1].trim()).filter(Boolean);
  let tracked = 0;
  let resolved = 0;
  for (const url of urls) {
    const pathname = new URL(url).pathname;
    let candidates;
    if (pathname === '/') candidates = ['index.html'];
    else if (pathname.endsWith('/')) candidates = [`${pathname.slice(1)}index.html`];
    else if (pathname.endsWith('.html')) candidates = [pathname.slice(1)];
    else candidates = [`${pathname.slice(1)}.html`, `${pathname.slice(1)}/index.html`];
    const file = candidates.map((candidate) => path.join(SITE_DIR, candidate)).find((candidate) => fs.existsSync(candidate));
    if (!file) continue;
    resolved += 1;
    if (fs.readFileSync(file, 'utf8').includes('/js/growth-attribution.js')) tracked += 1;
  }
  const coveragePct = urls.length > 0 ? Math.round((tracked / urls.length) * 1000) / 10 : 0;
  const completeCoverage = urls.length > 0 && tracked === urls.length && resolved === urls.length;
  return {
    status: completeCoverage ? 'FULL_STATIC_COVERAGE' : 'PARTIAL_COVERAGE',
    tracked,
    resolved,
    indexable: urls.length,
    coverage_pct: coveragePct,
    static_coverage_complete: completeCoverage,
  };
}

function evaluateChannelAttribution(registry, growth, coverage) {
  const gate = registry?.rules?.channel_attribution_gate || {};
  const startDay = String(gate.first_full_coverage_day || '').trim();
  const minDays = Math.max(1, Number(gate.minimum_complete_days || 3));
  const minViews = Math.max(1, Number(gate.minimum_qualified_views || 200));
  const todayOps = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
  const landingByDay = growth?.landing_views?.byDay || {};
  const sourceByDay = growth?.landing_views?.acquisition_sources?.bySourceDay || {};
  const candidateDays = Object.keys(landingByDay)
    .filter((day) => startDay && day >= startDay && day < todayOps)
    .sort();
  const completeDays = [];
  const observedSources = {};
  let qualifiedViews = 0;
  for (const day of candidateDays) {
    const daySources = sourceByDay[day] || {};
    const sourceTotal = Object.values(daySources).reduce((sum, value) => sum + Number(value || 0), 0);
    const landingTotal = Number(landingByDay[day] || 0);
    if (landingTotal <= 0 || sourceTotal !== landingTotal) continue;
    completeDays.push(day);
    qualifiedViews += landingTotal;
    for (const [source, value] of Object.entries(daySources)) {
      observedSources[source] = Number(observedSources[source] || 0) + Number(value || 0);
    }
  }
  const ready = coverage.static_coverage_complete === true
    && completeDays.length >= minDays
    && qualifiedViews >= minViews;
  return {
    ...coverage,
    status: ready ? 'READY' : (coverage.static_coverage_complete ? 'BASELINE_COLLECTION' : 'PARTIAL_COVERAGE'),
    full_coverage_deployed_at: gate.full_coverage_deployed_at || null,
    first_full_coverage_day: startDay || null,
    day_timezone: gate.day_timezone || 'UTC+08:00',
    complete_days: completeDays,
    complete_day_count: completeDays.length,
    qualified_views_in_decision_window: qualifiedViews,
    required: { minimum_complete_days: minDays, minimum_qualified_views: minViews },
    observed_sources: observedSources,
    channel_mix_decision_ready: ready,
  };
}

function evaluateGeoAttribution(registry, growth) {
  const gate = registry?.rules?.geo_attribution_gate || {};
  const sources = Array.isArray(gate.sources) ? gate.sources.map(String) : [];
  const startDay = String(gate.first_full_coverage_day || '').trim();
  const minDays = Math.max(1, Number(gate.minimum_complete_days || 7));
  const minAiViews = Math.max(1, Number(gate.minimum_ai_referred_views_for_directional_signal || 10));
  const todayOps = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
  const landingByDay = growth?.landing_views?.byDay || {};
  const sourceByDay = growth?.landing_views?.acquisition_sources?.bySourceDay || {};
  const completeDays = [];
  const bySource = Object.fromEntries(sources.map((source) => [source, 0]));
  let qualifiedViews = 0;
  for (const day of Object.keys(landingByDay).filter((d) => startDay && d >= startDay && d < todayOps).sort()) {
    const daySources = sourceByDay[day] || {};
    const sourceTotal = Object.values(daySources).reduce((sum, value) => sum + Number(value || 0), 0);
    const landingTotal = Number(landingByDay[day] || 0);
    if (landingTotal <= 0 || sourceTotal !== landingTotal) continue;
    completeDays.push(day);
    qualifiedViews += landingTotal;
    for (const source of sources) bySource[source] += Number(daySources[source] || 0);
  }
  const aiReferredViews = Object.values(bySource).reduce((sum, value) => sum + Number(value || 0), 0);
  const measurementReady = completeDays.length >= minDays;
  const directionalSignalReady = measurementReady && aiReferredViews >= minAiViews;
  return {
    status: directionalSignalReady ? 'DIRECTIONAL_SIGNAL_READY' : (measurementReady ? 'MEASUREMENT_READY_LOW_SAMPLE' : 'BASELINE_COLLECTION'),
    deployed_at: gate.deployed_at || null,
    first_full_coverage_day: startDay || null,
    complete_days: completeDays,
    complete_day_count: completeDays.length,
    qualified_views_in_window: qualifiedViews,
    ai_referred_views: aiReferredViews,
    by_source: bySource,
    required: { minimum_complete_days: minDays, minimum_ai_referred_views_for_directional_signal: minAiViews },
    historical_referral_reclassification_allowed: gate.historical_referral_reclassification_allowed === true,
    note: 'AI referral classification is prospective only. Historical generic referral/direct traffic is never guessed or reclassified.',
  };
}

function evaluateReferralDetail(registry, growth) {
  const gate = registry?.rules?.referral_detail_gate || {};
  const sources = Array.isArray(gate.sources) ? gate.sources.map(String) : [];
  const startDay = String(gate.first_full_coverage_day || '').trim();
  const minDays = Math.max(1, Number(gate.minimum_complete_days || 3));
  const minViews = Math.max(1, Number(gate.minimum_categorized_referral_views_for_directional_signal || 20));
  const todayOps = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
  const landingByDay = growth?.landing_views?.byDay || {};
  const sourceByDay = growth?.landing_views?.acquisition_sources?.bySourceDay || {};
  const completeDays = [];
  const bySource = Object.fromEntries(sources.map((source) => [source, 0]));
  let qualifiedViews = 0;
  for (const day of Object.keys(landingByDay).filter((d) => startDay && d >= startDay && d < todayOps).sort()) {
    const daySources = sourceByDay[day] || {};
    const sourceTotal = Object.values(daySources).reduce((sum, value) => sum + Number(value || 0), 0);
    const landingTotal = Number(landingByDay[day] || 0);
    if (landingTotal <= 0 || sourceTotal !== landingTotal) continue;
    completeDays.push(day);
    qualifiedViews += landingTotal;
    for (const source of sources) bySource[source] += Number(daySources[source] || 0);
  }
  const categorizedReferralViews = Object.values(bySource).reduce((sum, value) => sum + Number(value || 0), 0);
  const measurementReady = completeDays.length >= minDays;
  const directionalSignalReady = measurementReady && categorizedReferralViews >= minViews;
  return {
    status: directionalSignalReady ? 'DIRECTIONAL_SIGNAL_READY' : (measurementReady ? 'MEASUREMENT_READY_LOW_SAMPLE' : 'BASELINE_COLLECTION'),
    deployed_at: gate.deployed_at || null,
    first_full_coverage_day: startDay || null,
    complete_days: completeDays,
    complete_day_count: completeDays.length,
    qualified_views_in_window: qualifiedViews,
    categorized_referral_views: categorizedReferralViews,
    by_source: bySource,
    required: { minimum_complete_days: minDays, minimum_categorized_referral_views_for_directional_signal: minViews },
    historical_referral_reclassification_allowed: gate.historical_referral_reclassification_allowed === true,
    note: 'Actionable referral categories are prospective only. Historical generic referral traffic is never guessed or reclassified.',
  };
}

function evaluateConversionAttribution(registry, growth) {
  const gate = registry?.rules?.conversion_attribution_gate || {};
  const startDay = String(gate.first_full_coverage_day || '').trim();
  const minDays = Math.max(1, Number(gate.minimum_complete_days || 3));
  const minDownloads = Math.max(1, Number(gate.minimum_source_attributed_download_clicks || 20));
  const todayOps = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
  const landingByDay = growth?.landing_views?.byDay || {};
  const funnelByDay = growth?.attribution_funnel?.bySourcePageDay || {};
  const completeDays = [];
  const bySource = {};
  const bySourcePage = {};
  let attributedDownloads = 0;
  let qualifiedViews = 0;

  for (const day of Object.keys(landingByDay).filter((d) => startDay && d >= startDay && d < todayOps).sort()) {
    const sourcePages = funnelByDay[day] || {};
    let dayLanding = 0;
    for (const [source, pages] of Object.entries(sourcePages)) {
      for (const [page, metrics] of Object.entries(pages || {})) {
        const landing = Number(metrics?.landing_views || 0);
        const clicks = Number(metrics?.download_clicks || 0);
        dayLanding += landing;
        if (!bySource[source]) bySource[source] = { landing_views: 0, download_clicks: 0 };
        bySource[source].landing_views += landing;
        bySource[source].download_clicks += clicks;
        if (!bySourcePage[source]) bySourcePage[source] = {};
        if (!bySourcePage[source][page]) bySourcePage[source][page] = { landing_views: 0, download_clicks: 0 };
        bySourcePage[source][page].landing_views += landing;
        bySourcePage[source][page].download_clicks += clicks;
        if (source !== 'unknown') attributedDownloads += clicks;
      }
    }
    const landingTotal = Number(landingByDay[day] || 0);
    if (landingTotal > 0 && dayLanding === landingTotal) {
      completeDays.push(day);
      qualifiedViews += landingTotal;
    }
  }

  function addRates(target) {
    for (const metrics of Object.values(target || {})) {
      if (metrics && typeof metrics.landing_views === 'number') {
        metrics.conversion_pct = metrics.landing_views > 0
          ? Math.round((metrics.download_clicks / metrics.landing_views) * 10000) / 100
          : null;
      } else if (metrics && typeof metrics === 'object') addRates(metrics);
    }
  }
  addRates(bySource);
  addRates(bySourcePage);

  const measurementReady = completeDays.length >= minDays;
  const directionalSignalReady = measurementReady && attributedDownloads >= minDownloads;
  return {
    status: directionalSignalReady ? 'DIRECTIONAL_SIGNAL_READY' : (measurementReady ? 'MEASUREMENT_READY_LOW_SAMPLE' : 'BASELINE_COLLECTION'),
    deployed_at: gate.deployed_at || null,
    first_full_coverage_day: startDay || null,
    complete_days: completeDays,
    complete_day_count: completeDays.length,
    qualified_views_in_window: qualifiedViews,
    source_attributed_download_clicks: attributedDownloads,
    by_source: bySource,
    by_source_page: bySourcePage,
    required: { minimum_complete_days: minDays, minimum_source_attributed_download_clicks: minDownloads },
    historical_conversion_reclassification_allowed: false,
    note: 'Source×page conversion is prospective only. Historical download clicks are never joined back to a guessed source.',
  };
}

function topEntries(obj, limit = 20) {
  return Object.entries(obj || {})
    .map(([key, value]) => ({ key, value: Number(value || 0) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

function summarizeAppQuality(ops, registry) {
  const partial = new Set(registry?.rules?.partial_days_excluded || []);
  const today = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
  const daily = Array.isArray(ops?.rows) ? ops.rows : [];
  const completeDays = daily.filter((row) => row.day && row.day < today && !partial.has(row.day)).slice(-7);
  const northRows = Array.isArray(ops?.north_star?.rows) ? ops.north_star.rows : [];
  const byDay = new Map();
  for (const row of northRows) {
    if (!byDay.has(row.day)) byDay.set(row.day, { first_observed_devices: 0, new_dssu: 0, satisfied_devices: 0 });
    const target = byDay.get(row.day);
    target.first_observed_devices += Number(row.first_observed_devices || 0);
    target.new_dssu += Number(row.new_dssu || 0);
    target.satisfied_devices += Number(row.satisfied_devices || 0);
  }
  const latest = completeDays.map((row) => ({
    day: row.day,
    dau: Number(row.active_devices || 0),
    search_devices: Number(row.search_devices || 0),
    dssu: Number(row.action_devices || 0),
    new_devices: Number(byDay.get(row.day)?.first_observed_devices || 0),
    new_dssu: Number(byDay.get(row.day)?.new_dssu || 0),
    searches_completed: Number(row.searches_completed || 0),
    zero_result_searches: Number(row.zero_result_searches || 0),
  }));
  const qualityRows = Array.isArray(ops?.north_star?.new_user_quality?.rows)
    ? ops.north_star.new_user_quality.rows.filter((row) => row.matured && !partial.has(row.first_day))
    : [];
  const recentQuality = qualityRows.slice(-8);
  const totalNewDssu = recentQuality.reduce((n, row) => n + Number(row.new_dssu || 0), 0);
  const totalReused = recentQuality.reduce((n, row) => n + Number(row.reused_1_7d || 0), 0);
  const sum = (key) => latest.reduce((n, row) => n + Number(row[key] || 0), 0);
  const dau = sum('dau');
  const searchesCompleted = sum('searches_completed');
  const newDevices = sum('new_devices');
  const newDssu = sum('new_dssu');
  const activationPct = dau > 0 ? Math.round((sum('search_devices') / dau) * 1000) / 10 : null;
  const dssuPct = dau > 0 ? Math.round((sum('dssu') / dau) * 1000) / 10 : null;
  const newDssuActivationPct = newDevices > 0 ? Math.round((newDssu / newDevices) * 1000) / 10 : null;
  const zeroResultPct = searchesCompleted > 0 ? Math.round((sum('zero_result_searches') / searchesCompleted) * 10000) / 100 : null;
  const reusePctValue = totalNewDssu > 0 ? Math.round((totalReused / totalNewDssu) * 1000) / 10 : null;
  const returnUseCaseGap = activationPct !== null && activationPct >= 92
    && dssuPct !== null && dssuPct >= 80
    && newDssuActivationPct !== null && newDssuActivationPct >= 80
    && zeroResultPct !== null && zeroResultPct <= 2
    && reusePctValue !== null && reusePctValue < 45;
  return {
    operational_verified: ops?.operational_verified === true,
    complete_days: latest,
    activation_diagnosis: {
      search_activation_pct: activationPct,
      dssu_per_dau_pct: dssuPct,
      new_dssu_per_new_device_pct: newDssuActivationPct,
      zero_result_pct: zeroResultPct,
      retention_target_pct: 45,
      status: returnUseCaseGap ? 'RETURN_USE_CASE_GAP_HYPOTHESIS' : 'NO_SINGLE_RETENTION_HYPOTHESIS_YET',
      app_change_allowed: false,
      note: returnUseCaseGap
        ? 'Activation and search outcome guardrails are healthy while mature reuse remains below target. Diagnose a return-use case before changing the App; this is a hypothesis, not a causal claim.'
        : 'Do not introduce a retention feature until the aggregate activation/search/reuse pattern yields a bounded hypothesis.',
    },
    reuse_1_7d: {
      mature_through: ops?.north_star?.new_user_quality?.mature_through || null,
      cohorts: recentQuality,
      weighted_pct: reusePctValue,
    },
  };
}

async function main() {
  loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  const [growth, ops] = await Promise.all([fetchJson(args.growthUrl), fetchJson(args.opsUrl)]);
  if (!growth.available) throw new Error(`growth_read_unavailable:${growth.error || 'unknown'}`);
  const gsc = readJsonIfExists(args.gsc);
  const gscIngestStatus = readJsonIfExists(DEFAULT_GSC_STATUS);
  const registry = readJsonIfExists(args.experiments) || { experiments: [], rules: {} };
  const trusted = growth.trusted_first_party || {};
  const gscSnapshotReady = gsc?.status === 'OK' && Array.isArray(gsc.rows);
  const snapshotGeneratedMs = Date.parse(String(gsc?.generated_at || ''));
  const ingestGeneratedMs = Date.parse(String(gscIngestStatus?.generated_at || ''));
  const gscAuthBlocked = gscIngestStatus?.status === 'BLOCKED_EXTERNAL_AUTH'
    && Number.isFinite(ingestGeneratedMs)
    && (!Number.isFinite(snapshotGeneratedMs) || ingestGeneratedMs >= snapshotGeneratedMs);
  const search = aggregateSearchConsole(gsc);
  const opportunities = rankOpportunities(search.rows);
  const experimentGates = evaluateExperiments(registry, growth);
  const appQuality = summarizeAppQuality(ops, registry);
  const channelCoverage = attributionCoverage();
  const channelAttribution = evaluateChannelAttribution(registry, growth, channelCoverage);
  const geoAttribution = evaluateGeoAttribution(registry, growth);
  const referralDetail = evaluateReferralDetail(registry, growth);
  const conversionAttribution = evaluateConversionAttribution(registry, growth);

  const blockers = [];
  const warnings = [];
  if (!gscSnapshotReady) blockers.push('BLOCKED_EXTERNAL_AUTH_OR_NO_GSC_SNAPSHOT');
  else if (gscAuthBlocked) warnings.push('GSC_EXTERNAL_AUTH_BLOCKED_USING_LAST_GOOD');
  if (growth.complete !== true) blockers.push('GROWTH_READ_MODEL_INCOMPLETE');
  if (!appQuality.operational_verified) blockers.push('APP_D1_NOT_OPERATIONALLY_VERIFIED');
  if (experimentGates.some((row) => row.status === 'BASELINE_COLLECTION')) blockers.push('CRO_BASELINE_COLLECTION');

  const report = {
    schema_version: 2,
    generated_at: new Date().toISOString(),
    status: blockers.length ? 'GATED' : 'READY',
    blockers,
    warnings,
    evidence: {
      l1_search_console: gscSnapshotReady
        ? {
            status: gscAuthBlocked ? 'STALE_LAST_GOOD' : 'OK',
            generated_at: gsc.generated_at,
            start_date: gsc.start_date,
            end_date: gsc.end_date,
            rows: gsc.row_count,
            ingest_status: gscIngestStatus?.status || 'UNKNOWN',
            ingest_status_at: gscIngestStatus?.generated_at || null,
            note: gscAuthBlocked
              ? 'Using the last authorized final Search Console snapshot for historical experiments only; current ingest is blocked by external OAuth authorization.'
              : 'Current Search Console ingest status is healthy or no newer blocked status exists.',
          }
        : {
            status: 'BLOCKED_EXTERNAL_AUTH',
            ingest_status: gscIngestStatus?.status || 'UNKNOWN',
            ingest_status_at: gscIngestStatus?.generated_at || null,
          },
      l2_growth: {
        status: growth.complete === true ? 'OK' : 'INCOMPLETE',
        source: growth.source,
        raw_audit: growth.raw_audit,
        download_clicks: Number(growth.total || 0),
        trusted_first_party_clicks: Number(trusted.total || 0),
        qualified_landing_views: Number(growth.landing_views?.total || 0),
        trusted_measurement_start_at: trusted.measurement_start_at || null,
        landing_view_measurement_start_at: growth.landing_views?.measurement_start_at || null,
        channel_attribution: {
          ...channelAttribution,
          historical_observed_sources_diagnostic: growth.landing_views?.acquisition_sources?.bySource || {},
          note: channelAttribution.channel_mix_decision_ready
            ? 'Post-full-coverage complete-day sample gate passed; channel mix is ready for directional analysis.'
            : 'Do not infer whole-site channel share until the post-full-coverage complete-day and qualified-view gates pass.',
        },
        geo_attribution: geoAttribution,
        referral_detail: referralDetail,
        conversion_attribution: conversionAttribution,
        note: 'Only page-key-matched qualified views and trusted_first_party clicks are eligible for CRO judging. Unverified/direct clicks remain diagnostic.',
      },
      l3_app: {
        status: appQuality.operational_verified ? 'OK' : 'INCOMPLETE',
        attribution_limit: 'Aggregate direction only; no user-level sideload web-to-install join.',
        ...appQuality,
      },
    },
    existing_winners: {
      all_download_clicks_diagnostic: topEntries(growth.byPage, 20),
      trusted_first_party_lower_bound: topEntries(trusted.byPage, 20),
    },
    opportunities: {
      near_breakthrough: opportunities.nearBreakthrough,
      low_ctr: opportunities.lowCtr,
      cannibalization: search.cannibalization.slice(0, 20),
    },
    experiment_gates: experimentGates,
    decisions: {
      create_new_indexable_url: false,
      auto_publish_changes: false,
      maximum_concurrent_page_experiments: 3,
      channel_mix_decision_ready: channelAttribution.channel_mix_decision_ready,
      geo_measurement_status: geoAttribution.status,
      referral_detail_status: referralDetail.status,
      conversion_attribution_status: conversionAttribution.status,
      retention_diagnosis_status: appQuality.activation_diagnosis?.status || 'UNKNOWN',
      app_retention_change_allowed: appQuality.activation_diagnosis?.app_change_allowed === true,
    },
  };

  if (args.write) {
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    fs.writeFileSync(args.output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    console.log(`WROTE ${args.output}`);
  }
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ status: 'ERROR', error: error.message }));
  process.exitCode = 1;
});
