import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const DEFAULT_INPUT = path.join(ROOT, 'search-console', 'nsq-latest.json');
const DEFAULT_OUTPUT = path.join(ROOT, 'search-console', 'nsq-opportunities.json');
const TARGET_CTR = 0.10;
const WINNER_PATHS = new Set([
  '/blog/cili-search-tools-2026',
  '/blog/bt-search-engine-status-2026',
  '/blog/android-magnet-app-review',
  '/blog/magnet-search-backup-10',
  '/blog/best-magnet-apps-android-2026',
]);

function parseArgs(argv) {
  const out = { input: DEFAULT_INPUT, output: DEFAULT_OUTPUT, write: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--in') out.input = path.resolve(argv[++i]);
    else if (arg === '--out') out.output = path.resolve(argv[++i]);
    else if (arg === '--write') out.write = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return out;
}

function pagePath(value) {
  try { return new URL(value).pathname.replace(/\.html$/, '') || '/'; } catch { return ''; }
}

function aggregate(snapshot) {
  const dims = snapshot.dimensions || [];
  const index = Object.fromEntries(dims.map((name, i) => [name, i]));
  const pairs = new Map();
  const pages = new Map();
  for (const row of snapshot.rows || []) {
    const keys = row.keys || [];
    const query = String(keys[index.query] || '').trim();
    const page = String(keys[index.page] || '').trim();
    if (!query || !page) continue;
    const impressions = Number(row.impressions || 0);
    const clicks = Number(row.clicks || 0);
    const position = Number(row.position || 0);
    const key = `${query}\u0000${page}`;
    const current = pairs.get(key) || { query, page, impressions: 0, clicks: 0, position_weighted: 0 };
    current.impressions += impressions;
    current.clicks += clicks;
    current.position_weighted += position * impressions;
    pairs.set(key, current);

    const p = pages.get(page) || { page, impressions: 0, clicks: 0, position_weighted: 0 };
    p.impressions += impressions;
    p.clicks += clicks;
    p.position_weighted += position * impressions;
    pages.set(page, p);
  }
  const normalizedPairs = [...pairs.values()].map((item) => ({
    query: item.query,
    page: item.page,
    path: pagePath(item.page),
    impressions: item.impressions,
    clicks: item.clicks,
    ctr_pct: item.impressions ? Math.round(item.clicks / item.impressions * 10000) / 100 : 0,
    position: item.impressions ? Math.round(item.position_weighted / item.impressions * 100) / 100 : null,
  }));
  const normalizedPages = [...pages.values()].map((item) => ({
    page: item.page,
    path: pagePath(item.page),
    impressions: item.impressions,
    clicks: item.clicks,
    ctr_pct: item.impressions ? Math.round(item.clicks / item.impressions * 10000) / 100 : 0,
    position: item.impressions ? Math.round(item.position_weighted / item.impressions * 100) / 100 : null,
  }));
  return { pairs: normalizedPairs, pages: normalizedPages };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const snapshot = JSON.parse(fs.readFileSync(args.input, 'utf8').replace(/^\uFEFF/, ''));
  if (snapshot.status !== 'OK' || snapshot.site_url !== 'sc-domain:naoshiquan.com') {
    throw new Error(`invalid NSQ GSC snapshot: status=${snapshot.status} site=${snapshot.site_url}`);
  }
  const { pairs, pages } = aggregate(snapshot);
  const queryOpportunities = pairs
    .filter((x) => x.impressions >= 50 && x.position >= 3 && x.position <= 15 && x.ctr_pct < TARGET_CTR * 100)
    .map((x) => ({
      ...x,
      target_ctr_pct: TARGET_CTR * 100,
      incremental_clicks_at_target: Math.max(0, Math.round((x.impressions * TARGET_CTR - x.clicks) * 10) / 10),
    }))
    .sort((a, b) => b.incremental_clicks_at_target - a.incremental_clicks_at_target);
  const winnerPages = pages
    .filter((x) => WINNER_PATHS.has(x.path))
    .sort((a, b) => b.clicks - a.clicks || b.impressions - a.impressions);
  const result = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    status: 'READY',
    source_snapshot: { generated_at: snapshot.generated_at, start_date: snapshot.start_date, end_date: snapshot.end_date, rows: snapshot.row_count },
    rules: { target_ctr_pct: TARGET_CTR * 100, minimum_impressions: 50, position_range: [3, 15], no_new_indexable_urls: true },
    query_opportunities: queryOpportunities.slice(0, 30),
    winner_pages: winnerPages,
    note: 'Use this only to harvest existing NSQ pages. It does not authorize new indexable URLs or multi-variable edits.',
  };
  if (args.write) {
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    fs.writeFileSync(args.output, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    console.log(`WROTE ${args.output}`);
  }
  console.log(JSON.stringify(result, null, 2));
}

main();
