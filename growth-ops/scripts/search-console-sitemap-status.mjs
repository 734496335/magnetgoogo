import fs from 'node:fs';
import path from 'node:path';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..');
const SITE_URL = 'sc-domain:magnetgoogo.com';
const EXPECTED = new Set([
  'https://magnetgoogo.com/sitemap.xml',
  'https://magnetgoogo.com/sitemap_index.xml',
]);

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
  const file = resolveProjectFile(process.env.GOOGLE_SEARCH_CONSOLE_OAUTH_FILE);
  if (!file || !fs.existsSync(file)) throw new Error('GOOGLE_SEARCH_CONSOLE_OAUTH_FILE missing or unreadable');
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  const client = parsed.installed || parsed.web;
  if (!client?.client_id || !client?.client_secret) throw new Error('OAuth client JSON missing client_id/client_secret');
  return client;
}

function refreshToken() {
  const file = resolveProjectFile(process.env.GOOGLE_SEARCH_CONSOLE_TOKEN_FILE || 'google-search-console-token.json');
  if (!file || !fs.existsSync(file)) throw new Error('Search Console token file missing');
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  const token = String(parsed.refresh_token || '').trim();
  if (!token) throw new Error('Search Console refresh token missing');
  return token;
}

async function accessToken() {
  const client = oauthClient();
  const body = new URLSearchParams({
    client_id: client.client_id,
    client_secret: client.client_secret,
    refresh_token: refreshToken(),
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

async function main() {
  loadDotEnv();
  const token = await accessToken();
  const endpoint = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(SITE_URL)}/sitemaps`;
  const response = await fetch(endpoint, { headers: { authorization: `Bearer ${token}` } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`search_console_sitemaps_failed:${response.status}:${String(data?.error?.message || data?.error || 'unknown').slice(0, 200)}`);
  }
  const rows = (Array.isArray(data.sitemap) ? data.sitemap : []).map((row) => ({
    path: String(row.path || ''),
    lastSubmitted: row.lastSubmitted || null,
    lastDownloaded: row.lastDownloaded || null,
    isPending: row.isPending === true,
    isSitemapsIndex: row.isSitemapsIndex === true,
    errors: Number(row.errors || 0),
    warnings: Number(row.warnings || 0),
    contents: Array.isArray(row.contents) ? row.contents : [],
  }));
  const expectedRows = rows.filter((row) => EXPECTED.has(row.path));
  const healthy = expectedRows.some((row) => !row.isPending && row.errors === 0);
  console.log(JSON.stringify({
    status: healthy ? 'PASS' : 'WARN',
    site_url: SITE_URL,
    submitted_sitemaps: rows,
    expected_present: expectedRows.map((row) => row.path),
    healthy_expected_sitemap: healthy,
  }, null, 2));
  if (!healthy) process.exitCode = 2;
}

function isExternalAuthError(error) {
  const message = String(error?.message || error || '');
  return /^oauth_refresh_failed:/i.test(message)
    || /^search_console_sitemaps_failed:(401|403):/i.test(message)
    || /Search Console (token file|refresh token)/i.test(message)
    || /GOOGLE_SEARCH_CONSOLE_OAUTH_FILE/i.test(message);
}

main().catch((error) => {
  if (isExternalAuthError(error)) {
    console.error(JSON.stringify({
      status: 'BLOCKED_EXTERNAL_AUTH',
      error: String(error?.message || error || ''),
    }));
    process.exitCode = 2;
    return;
  }
  console.error(JSON.stringify({ status: 'ERROR', error: error.message }));
  process.exitCode = 1;
});
