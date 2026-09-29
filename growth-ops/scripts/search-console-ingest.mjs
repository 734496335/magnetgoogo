import fs from 'node:fs';
import path from 'node:path';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..');
const ROOT = path.resolve(import.meta.dirname, '..');
const DEFAULT_OUTPUT = path.join(ROOT, 'search-console', 'latest.json');
const DEFAULT_STATUS = path.join(ROOT, 'search-console', 'ingest-status.json');
const DIMENSIONS = ['date', 'query', 'page', 'country', 'device'];
const ROW_LIMIT = 25000;
const MAX_PAGES = 20;
const READONLY_SCOPE = 'https://www.googleapis.com/auth/webmasters.readonly';
let writeStatusEnabled = false;
let writeStatusFile = DEFAULT_STATUS;

function writeIngestStatus(result) {
  if (!writeStatusEnabled) return;
  fs.mkdirSync(path.dirname(writeStatusFile), { recursive: true });
  fs.writeFileSync(writeStatusFile, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
}

function loadDotEnv() {
  const file = path.join(PROJECT_ROOT, '.env');
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    if (!line || /^\s*#/.test(line)) continue;
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match || process.env[match[1]] !== undefined) continue;
    process.env[match[1]] = match[2].trim();
  }
}

function resolveProjectFile(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return path.isAbsolute(raw) ? raw : path.join(PROJECT_ROOT, raw);
}

function oauthClient() {
  const directId = String(process.env.GOOGLE_SEARCH_CONSOLE_CLIENT_ID || '').trim();
  const directSecret = String(process.env.GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET || '').trim();
  if (directId && directSecret) return { client_id: directId, client_secret: directSecret };
  const file = resolveProjectFile(process.env.GOOGLE_SEARCH_CONSOLE_OAUTH_FILE);
  if (!file || !fs.existsSync(file)) return null;
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  const client = parsed.installed || parsed.web;
  if (!client?.client_id || !client?.client_secret) return null;
  return client;
}

function refreshToken() {
  const direct = String(process.env.GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN || '').trim();
  if (direct) return direct;
  const file = resolveProjectFile(process.env.GOOGLE_SEARCH_CONSOLE_TOKEN_FILE || 'google-search-console-token.json');
  if (!file || !fs.existsSync(file)) return '';
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  return String(parsed.refresh_token || '').trim();
}

function isoDay(date) {
  return date.toISOString().slice(0, 10);
}

function defaultRange() {
  const end = new Date();
  end.setUTCDate(end.getUTCDate() - 2);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 27);
  return { startDate: isoDay(start), endDate: isoDay(end) };
}

function parseArgs(argv) {
  const range = defaultRange();
  const out = { ...range, output: DEFAULT_OUTPUT, statusOutput: DEFAULT_STATUS, siteUrl: '', write: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--start') out.startDate = argv[++i];
    else if (arg === '--end') out.endDate = argv[++i];
    else if (arg === '--out') out.output = path.resolve(argv[++i]);
    else if (arg === '--status-out') out.statusOutput = path.resolve(argv[++i]);
    else if (arg === '--site-url') out.siteUrl = String(argv[++i] || '').trim();
    else if (arg === '--write') out.write = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(out.startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(out.endDate)) {
    throw new Error('start/end must be YYYY-MM-DD');
  }
  if (out.startDate > out.endDate) throw new Error('start date must be <= end date');
  return out;
}

async function refreshAccessToken() {
  const client = oauthClient();
  const token = refreshToken();
  if (!client || !token) return null;
  const body = new URLSearchParams({
    client_id: client.client_id,
    client_secret: client.client_secret,
    refresh_token: token,
    grant_type: 'refresh_token',
  });
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.access_token) {
    throw new Error(`oauth_refresh_failed:${response.status}:${String(data.error_description || data.error || 'unknown').slice(0, 160)}`);
  }
  return data.access_token;
}

async function resolveAccessToken() {
  const direct = String(process.env.GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN || '').trim();
  if (direct) return direct;
  return await refreshAccessToken();
}

function blocked(reason, extra = {}) {
  const result = {
    schema_version: 1,
    status: 'BLOCKED_EXTERNAL_AUTH',
    source: 'Google Search Console Search Analytics API',
    reason,
    generated_at: new Date().toISOString(),
    ...extra,
  };
  writeIngestStatus(result);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = 2;
  return null;
}

async function listSites(token) {
  const response = await fetch('https://www.googleapis.com/webmasters/v3/sites', {
    headers: { authorization: `Bearer ${token}` },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`search_console_sites_failed:${response.status}:${String(data?.error?.message || data?.error || 'unknown').slice(0, 240)}`);
  }
  return Array.isArray(data.siteEntry) ? data.siteEntry : [];
}

function isMagnetGoogoProperty(siteUrl) {
  const value = String(siteUrl || '').trim();
  if (value === 'sc-domain:magnetgoogo.com') return true;
  try {
    return new URL(value).hostname.toLowerCase() === 'magnetgoogo.com';
  } catch {
    return false;
  }
}

async function resolveSiteUrl(token, explicitArg = '') {
  const explicit = String(explicitArg || process.env.GOOGLE_SEARCH_CONSOLE_SITE_URL || '').trim();
  if (explicit) return explicit;
  const sites = await listSites(token);
  const candidates = sites.filter((entry) => isMagnetGoogoProperty(entry.siteUrl));
  candidates.sort((a, b) => {
    const score = (entry) => entry.siteUrl === 'sc-domain:magnetgoogo.com' ? 0 : String(entry.siteUrl).startsWith('https://') ? 1 : 2;
    return score(a) - score(b);
  });
  if (candidates.length) return candidates[0].siteUrl;
  return blocked('Authorized account has no Search Console property for magnetgoogo.com', {
    visible_sites: sites.map((entry) => entry.siteUrl),
  });
}

async function queryPage({ siteUrl, token, startDate, endDate, startRow }) {
  const endpoint = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      startDate,
      endDate,
      dimensions: DIMENSIONS,
      aggregationType: 'auto',
      dataState: 'final',
      rowLimit: ROW_LIMIT,
      startRow,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`search_console_query_failed:${response.status}:${String(data?.error?.message || data?.error || 'unknown').slice(0, 240)}`);
  }
  return data;
}

async function main() {
  loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  writeStatusEnabled = args.write;
  writeStatusFile = args.statusOutput;
  const token = await resolveAccessToken();
  if (!token) {
    return blocked('No Search Console OAuth authorization configured', {
      required_scope: READONLY_SCOPE,
      oauth_file_configured: Boolean(process.env.GOOGLE_SEARCH_CONSOLE_OAUTH_FILE),
      token_file_configured: Boolean(process.env.GOOGLE_SEARCH_CONSOLE_TOKEN_FILE),
    });
  }
  const siteUrl = await resolveSiteUrl(token, args.siteUrl);
  if (!siteUrl) return;

  const rows = [];
  let responseAggregationType = null;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const data = await queryPage({
      siteUrl,
      token,
      startDate: args.startDate,
      endDate: args.endDate,
      startRow: page * ROW_LIMIT,
    });
    const pageRows = Array.isArray(data.rows) ? data.rows : [];
    responseAggregationType = data.responseAggregationType || responseAggregationType;
    rows.push(...pageRows);
    if (pageRows.length < ROW_LIMIT) break;
    if (page === MAX_PAGES - 1) throw new Error(`search_console_pagination_cap_reached:${MAX_PAGES * ROW_LIMIT}`);
  }

  const result = {
    schema_version: 1,
    status: 'OK',
    source: 'Google Search Console Search Analytics API',
    generated_at: new Date().toISOString(),
    site_url: siteUrl,
    start_date: args.startDate,
    end_date: args.endDate,
    data_state: 'final',
    dimensions: DIMENSIONS,
    response_aggregation_type: responseAggregationType,
    row_count: rows.length,
    note: 'Search Console API returns top rows subject to internal service limits; this snapshot must not be described as exhaustive query inventory.',
    rows,
  };

  if (args.write) {
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    fs.writeFileSync(args.output, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    writeIngestStatus({
      schema_version: 1,
      status: 'OK',
      source: result.source,
      generated_at: result.generated_at,
      snapshot_file: path.relative(PROJECT_ROOT, args.output).replace(/\\/g, '/'),
      snapshot_end_date: result.end_date,
      row_count: result.row_count,
    });
    console.log(`WROTE ${args.output}`);
  }
  console.log(JSON.stringify({ ...result, rows: undefined }, null, 2));
}

function isExternalAuthError(error) {
  const message = String(error?.message || error || '');
  return /^oauth_refresh_failed:/i.test(message)
    || /^search_console_sites_failed:(401|403):/i.test(message)
    || /^search_console_query_failed:(401|403):/i.test(message);
}

loadDotEnv();
main().catch((error) => {
  if (isExternalAuthError(error)) {
    blocked('Search Console OAuth authorization is expired, revoked, or insufficient', {
      detail: String(error?.message || error || '').slice(0, 240),
      required_scope: READONLY_SCOPE,
    });
    return;
  }
  console.error(JSON.stringify({ status: 'ERROR', error: error.message }));
  process.exitCode = 1;
});
