import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..');
const SCOPE = 'https://www.googleapis.com/auth/webmasters.readonly';
const STATUS_FILE = path.join(PROJECT_ROOT, 'growth-ops', 'runtime', 'search-console-auth-status.json');

function writeStatus(value) {
  fs.mkdirSync(path.dirname(STATUS_FILE), { recursive: true });
  fs.writeFileSync(STATUS_FILE, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
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

function resolveSecretFile(name, fallback = '') {
  const value = String(process.env[name] || fallback || '').trim();
  if (!value) return '';
  return path.isAbsolute(value) ? value : path.join(PROJECT_ROOT, value);
}

function oauthClient() {
  const file = resolveSecretFile('GOOGLE_SEARCH_CONSOLE_OAUTH_FILE');
  if (!file || !fs.existsSync(file)) throw new Error('GOOGLE_SEARCH_CONSOLE_OAUTH_FILE missing or unreadable');
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  const client = parsed.installed || parsed.web;
  if (!client?.client_id || !client?.client_secret) throw new Error('OAuth client JSON missing client_id/client_secret');
  return { ...client, file };
}

function tokenFile() {
  const file = resolveSecretFile('GOOGLE_SEARCH_CONSOLE_TOKEN_FILE', 'google-search-console-token.json');
  if (!file) throw new Error('GOOGLE_SEARCH_CONSOLE_TOKEN_FILE missing');
  return file;
}

function openBrowser(url) {
  if (process.platform === 'win32') {
    spawn('rundll32.exe', ['url.dll,FileProtocolHandler', url], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  } else if (process.platform === 'darwin') {
    spawn('open', [url], { detached: true, stdio: 'ignore' }).unref();
  } else {
    spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
  }
}

function base64Url(buffer) {
  return Buffer.from(buffer).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function createPkce() {
  const verifier = base64Url(crypto.randomBytes(64));
  const challenge = base64Url(crypto.createHash('sha256').update(verifier).digest());
  return { verifier, challenge };
}

async function exchangeCode({ client, code, redirectUri, codeVerifier }) {
  const body = new URLSearchParams({
    client_id: client.client_id,
    client_secret: client.client_secret,
    code,
    code_verifier: codeVerifier,
    redirect_uri: redirectUri,
    grant_type: 'authorization_code',
  });
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.access_token) {
    throw new Error(`oauth_code_exchange_failed:${response.status}:${String(data.error_description || data.error || 'unknown').slice(0, 200)}`);
  }
  return data;
}

async function listSites(accessToken) {
  const response = await fetch('https://www.googleapis.com/webmasters/v3/sites', {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`search_console_sites_failed:${response.status}:${String(data?.error?.message || data?.error || 'unknown').slice(0, 200)}`);
  return Array.isArray(data.siteEntry) ? data.siteEntry : [];
}

function waitForOAuthCallback(server, expectedState) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('oauth_callback_timeout')), 10 * 60_000);
    server.on('request', (req, res) => {
      try {
        const url = new URL(req.url, 'http://127.0.0.1');
        if (url.pathname !== '/') {
          res.writeHead(404).end('Not found');
          return;
        }
        const state = url.searchParams.get('state');
        const code = url.searchParams.get('code');
        const error = url.searchParams.get('error');
        if (state !== expectedState) throw new Error('oauth_state_mismatch');
        if (error) throw new Error(`oauth_denied:${error}`);
        if (!code) throw new Error('oauth_code_missing');
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
        res.end('<!doctype html><meta charset="utf-8"><title>MagnetGoogo Search Console</title><h2>Google Search Console 授权成功</h2><p>可以关闭此页面，ChatGPT 会继续执行。</p>');
        clearTimeout(timer);
        resolve(code);
      } catch (error) {
        clearTimeout(timer);
        reject(error);
      }
    });
  });
}

async function main() {
  loadDotEnv();
  const client = oauthClient();
  const outFile = tokenFile();
  if (process.argv.includes('--check')) {
    const result = {
      status: 'CONFIG_OK',
      client_type: Array.isArray(client.redirect_uris) && client.redirect_uris.includes('http://localhost') ? 'desktop_loopback' : 'oauth_client',
      scope: SCOPE,
      oauth_file: path.basename(client.file),
      token_file: path.basename(outFile),
      loopback: '127.0.0.1:random-port',
      pkce: 'S256',
    };
    console.log(JSON.stringify(result, null, 2));
    return;
  }
  const server = http.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const { port } = server.address();
  const redirectUri = `http://127.0.0.1:${port}`;
  const state = crypto.randomBytes(24).toString('hex');
  const pkce = createPkce();
  const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  authUrl.searchParams.set('client_id', client.client_id);
  authUrl.searchParams.set('redirect_uri', redirectUri);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('scope', SCOPE);
  authUrl.searchParams.set('access_type', 'offline');
  authUrl.searchParams.set('prompt', 'consent');
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('code_challenge', pkce.challenge);
  authUrl.searchParams.set('code_challenge_method', 'S256');

  writeStatus({
    status: 'WAITING_FOR_USER_CONSENT',
    started_at: new Date().toISOString(),
    port,
    redirect_uri: redirectUri,
    auth_url: authUrl.toString(),
    scope: SCOPE,
  });
  console.log(`OAuth browser opened; waiting on 127.0.0.1:${port} (scope=${SCOPE})`);
  openBrowser(authUrl.toString());
  try {
    const code = await waitForOAuthCallback(server, state);
    const token = await exchangeCode({ client, code, redirectUri, codeVerifier: pkce.verifier });
    if (!token.refresh_token) throw new Error('Google did not return a refresh_token; revoke prior grant and retry with consent');
    const stored = {
      schema_version: 1,
      created_at: new Date().toISOString(),
      scope: token.scope || SCOPE,
      token_type: token.token_type || 'Bearer',
      refresh_token: token.refresh_token,
    };
    fs.writeFileSync(outFile, `${JSON.stringify(stored, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 });
    const sites = await listSites(token.access_token);
    const publicResult = {
      status: 'AUTHORIZED',
      authorized_at: new Date().toISOString(),
      token_file: path.basename(outFile),
      sites: sites.map((entry) => ({ siteUrl: entry.siteUrl, permissionLevel: entry.permissionLevel })),
    };
    writeStatus(publicResult);
    console.log(JSON.stringify(publicResult, null, 2));
  } finally {
    server.close();
  }
}

main().catch((error) => {
  const result = { status: 'ERROR', failed_at: new Date().toISOString(), error: error.message };
  try { writeStatus(result); } catch { /* best effort */ }
  console.error(JSON.stringify(result));
  process.exitCode = 1;
});
