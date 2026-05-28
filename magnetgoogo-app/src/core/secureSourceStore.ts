/**
 * Source storage layer.
 *
 * Security model (3-layer):
 *   Layer 1 — Transit: AES-256-CBC encrypted payload (sources.enc.json)
 *   Layer 2 — Disk: encrypted payload cached locally (still AES-encrypted,
 *             NOT plaintext). Expires after source_expiry_hours (default 72h).
 *   Layer 3 — Memory: sources stored XOR-obfuscated with a random session
 *             key. A Frida memory dump sees only garbled bytes.
 *
 * Fetch strategy: parallel race (Promise.any) across all endpoints.
 * Whichever responds first with a valid payload wins. Typical latency
 * drops from 10-15s (sequential) to 1-3s (parallel).
 *
 * Auth: Pre-reserved for future member tier.
 *   - Free: GitHub CDN static files (no auth)
 *   - Member: CF Worker validates Authorization: Bearer <token>
 */
import * as SecureStore from 'expo-secure-store';
import { File, Paths, Directory } from 'expo-file-system';
import { decryptSources } from './crypto';
import { getAppVersion } from './configChecker';
import { COMPLIANCE_MODE } from './complianceConfig';

const SOURCE_FILE = COMPLIANCE_MODE ? '/sources-green.enc.json' : '/sources.enc.json';

// ── Endpoints (new repo: mg-data) ────────────────────────────────────
// All endpoints are raced in parallel; first valid response wins.
const CN_ALI = 'https://cn.magnetgoogo.com';
const CDN_BASE = 'https://cdn.jsdelivr.net/gh/734496335/mg-data@main';
const RAW_BASE = 'https://raw.githubusercontent.com/734496335/mg-data/main';
const GATEWAY_BASE = 'https://api.naoshiquan.com';
const GATEWAY_OLD = 'https://maggoogo-gateway.734496335lp.workers.dev';
const CN_BASE = 'https://magnetgoogo.com';
const DEFAULT_REMOTE_URL = CDN_BASE;

// Disk cache (new expo-file-system API)
const CACHE_DIR = new Directory(Paths.document, 'source-cache');
const CACHE_FILE = new File(CACHE_DIR, 'sources.cache.json');
const DEFAULT_EXPIRY_HOURS = 72;

// Auth token key in SecureStore
const AUTH_TOKEN_KEY = 'mg_auth_token';

/** Fetch with timeout (default 8s — shorter because we race). */
function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 8000): Promise<Response> {
  return new Promise((resolve, reject) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => { ctrl.abort(); reject(new Error('timeout')); }, timeoutMs);
    fetch(url, { ...options, signal: ctrl.signal })
      .then(r => { clearTimeout(timer); resolve(r); })
      .catch(e => { clearTimeout(timer); reject(e); });
  });
}

/**
 * Race multiple URLs in parallel. Returns the first that responds OK.
 * If all fail, throws the last error.
 */
async function raceFetchOk(
  urls: string[],
  path: string,
  headers: Record<string, string>,
  timeoutMs = 8000,
): Promise<{ text: string; url: string }> {
  const promises = urls.map(async (base) => {
    const fullUrl = `${base}${path}`;
    const resp = await fetchWithTimeout(fullUrl, { headers }, timeoutMs);
    if (resp.status === 403) {
      const errBody = await resp.json().catch(() => ({}));
      throw new Error(errBody.message || '请更新App到最新版本');
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status} from ${base}`);
    const text = await resp.text();
    if (!text || text.length < 10) throw new Error(`Empty response from ${base}`);
    console.log(`[SourceStore] ✓ ${base} responded first`);
    return { text, url: base };
  });
  return Promise.any(promises);
}

// ── types ───────────────────────────────────────────────────────────
export interface SourceMeta {
  updatedAt: string;
  count: number;
  remoteUrl: string;
}

export interface SourceRule {
  id: string;
  [key: string]: unknown;
}

interface DiskCache {
  encPayload: string;    // raw AES-encrypted text (still encrypted!)
  savedAt: string;       // ISO timestamp
  expiryHours: number;   // how long this cache is valid
  count: number;         // source count for quick display
  remoteUrl: string;     // which endpoint was used
}

// ── In-memory obfuscated vault ──────────────────────────────────────
let _sessionKey: Uint8Array = _randomKey(64);
let _vault: Uint8Array[] = [];
let _sourceCount = 0;
let _cachedMeta: SourceMeta | null = null;

function _randomKey(len: number): Uint8Array {
  const arr = new Uint8Array(len);
  for (let i = 0; i < len; i++) arr[i] = Math.floor(Math.random() * 256);
  return arr;
}

function _obfuscate(plainJson: string): Uint8Array {
  const bytes = new Uint8Array(plainJson.length);
  for (let i = 0; i < plainJson.length; i++) {
    bytes[i] = plainJson.charCodeAt(i) ^ _sessionKey[i % _sessionKey.length];
  }
  return bytes;
}

function _deobfuscate(blob: Uint8Array): string {
  const chars: string[] = [];
  for (let i = 0; i < blob.length; i++) {
    chars.push(String.fromCharCode(blob[i] ^ _sessionKey[i % _sessionKey.length]));
  }
  return chars.join('');
}

function _compareSemver(a: string, b: string): number {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    const na = pa[i] || 0;
    const nb = pb[i] || 0;
    if (na < nb) return -1;
    if (na > nb) return 1;
  }
  return 0;
}

// ── Disk cache helpers ──────────────────────────────────────────────

function _saveToDisk(encPayload: string, meta: SourceMeta, expiryHours: number) {
  try {
    if (!CACHE_DIR.exists) {
      CACHE_DIR.create();
    }
    const cache: DiskCache = {
      encPayload,
      savedAt: new Date().toISOString(),
      expiryHours,
      count: meta.count,
      remoteUrl: meta.remoteUrl,
    };
    if (!CACHE_FILE.exists) {
      CACHE_FILE.create();
    }
    CACHE_FILE.write(JSON.stringify(cache));
    console.log(`[SourceStore] Saved ${meta.count} sources to disk cache (expires in ${expiryHours}h)`);
  } catch (e: any) {
    console.log(`[SourceStore] Disk save failed: ${e.message}`);
  }
}

function _loadFromDisk(): { green: SourceRule[]; meta: SourceMeta } | null {
  try {
    if (!CACHE_FILE.exists) return null;

    const text = CACHE_FILE.textSync();
    const cache: DiskCache = JSON.parse(text);

    // Check expiry
    const savedAt = new Date(cache.savedAt).getTime();
    const expiresAt = savedAt + cache.expiryHours * 3600000;
    if (Date.now() > expiresAt) {
      const expiredAgo = Math.round((Date.now() - expiresAt) / 3600000);
      console.log(`[SourceStore] Disk cache expired ${expiredAgo}h ago, will re-sync`);
      return null;
    }

    // Decrypt the cached encrypted payload
    const decrypted = decryptSources(cache.encPayload);
    const raw = JSON.parse(decrypted);

    // Unwrap + filter green
    const green = _extractGreen(raw);

    const meta: SourceMeta = {
      updatedAt: cache.savedAt,
      count: green.length,
      remoteUrl: cache.remoteUrl + ' (cached)',
    };

    console.log(`[SourceStore] Loaded ${green.length} sources from disk cache \u2713`);
    return { green, meta };
  } catch (e: any) {
    console.log(`[SourceStore] Disk load failed: ${e.message}`);
    return null;
  }
}

/** Extract green sources from raw parsed data. */
function _extractGreen(raw: any): SourceRule[] {
  let sourceData = raw;
  if (raw.payload && raw.expires_at) {
    if (raw.min_app_version) {
      const appVer = getAppVersion();
      if (_compareSemver(appVer, raw.min_app_version) < 0) return [];
    }
    sourceData = raw.payload;
  }

  let list: SourceRule[] = [];
  if (Array.isArray(sourceData)) {
    list = sourceData;
  } else if (sourceData.rulesets && Array.isArray(sourceData.rulesets)) {
    // Flatten all rules from ALL rulesets (not just the first one)
    for (const rs of sourceData.rulesets) {
      if (rs.rules && Array.isArray(rs.rules)) {
        list.push(...rs.rules);
      }
    }
  } else if (sourceData.sources) {
    list = sourceData.sources;
  }

  return list.filter((s: any) => s.health?.status === 'green');
}

/** Load sources into memory vault from an array. */
function _loadIntoVault(green: SourceRule[], meta: SourceMeta) {
  _sessionKey = _randomKey(64);
  _vault = green.map((rule) => _obfuscate(JSON.stringify(rule)));
  _sourceCount = green.length;
  _cachedMeta = meta;
}

// ── public API ──────────────────────────────────────────────────────

/** Get all sources. Tries memory first, then disk cache. */
export async function loadSources(): Promise<SourceRule[] | null> {
  // Memory vault has data → use it
  if (_vault.length > 0) {
    return _vault.map((blob) => JSON.parse(_deobfuscate(blob)));
  }

  // Try disk cache
  const disk = _loadFromDisk();
  if (disk) {
    _loadIntoVault(disk.green, disk.meta);
    return disk.green;
  }

  return null;
}

export async function loadMeta(): Promise<SourceMeta | null> {
  if (_cachedMeta) return _cachedMeta;

  // Try reading meta from disk cache without full decrypt
  try {
    if (!CACHE_FILE.exists) return null;
    const text = CACHE_FILE.textSync();
    const cache: DiskCache = JSON.parse(text);
    return {
      updatedAt: cache.savedAt,
      count: cache.count,
      remoteUrl: cache.remoteUrl + ' (cached)',
    };
  } catch {
    return null;
  }
}

export function getSourceCount(): number {
  return _sourceCount;
}

export function getSourceAt(index: number): SourceRule | null {
  if (index < 0 || index >= _vault.length) return null;
  return JSON.parse(_deobfuscate(_vault[index]));
}

export async function syncSources(
  url?: string,
): Promise<{ sources: SourceRule[]; meta: SourceMeta }> {
  const endpoints = url
    ? [url.replace(/\/$/, '')]
    : [CN_ALI, CN_BASE, CDN_BASE, RAW_BASE, GATEWAY_BASE, GATEWAY_OLD];

  const appVer = getAppVersion();
  const authToken = await getAuthToken();
  const headers: Record<string, string> = {
    'Cache-Control': 'no-cache',
    'X-App-Version': appVer,
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  let raw: any;
  let encPayload = '';
  let usedUrl = '';

  // ── Strategy: race all endpoints, sequential fallback ──
  const allEndpoints = [...endpoints, CN_BASE].filter((v, i, a) => a.indexOf(v) === i);

  // Tier 1: race all endpoints (8s timeout) — fastest wins
  try {
    const result = await raceFetchOk(allEndpoints, SOURCE_FILE, headers);
    encPayload = result.text;
    const decrypted = decryptSources(encPayload);
    raw = JSON.parse(decrypted);
    usedUrl = result.url;
  } catch (raceErr: any) {
    console.log(`[SourceStore] Tier 1 failed: ${raceErr.message}, trying sequentially...`);
    // Tier 2: try each endpoint sequentially with longer timeout (CN first)
    const fallbackOrder = [CN_ALI, CN_BASE, GATEWAY_BASE, CDN_BASE, RAW_BASE, GATEWAY_OLD];
    let found = false;
    for (const base of fallbackOrder) {
      try {
        const resp = await fetchWithTimeout(`${base}${SOURCE_FILE}`, { headers }, 15000);
        if (!resp.ok) continue;
        const text = await resp.text();
        if (!text || text.length < 10) continue;
        const decrypted = decryptSources(text);
        raw = JSON.parse(decrypted);
        encPayload = text;
        usedUrl = base;
        found = true;
        console.log(`[SourceStore] ✓ Fallback succeeded via ${base}`);
        break;
      } catch (e: any) {
        console.log(`[SourceStore] ${base} failed: ${e.message}`);
      }
    }
    if (!found) {
      throw new Error(`所有端点均不可达，请检查网络`);
    }
  }

  // ── Unwrap envelope — only enforce version gating, ignore expiry ──
  let expiryHours = DEFAULT_EXPIRY_HOURS;
  if (raw.payload && raw.expires_at) {
    if (raw.min_app_version && _compareSemver(appVer, raw.min_app_version) < 0) {
      throw new Error(`请更新App到 ${raw.min_app_version} 以上版本`);
    }
    console.log(`[SourceStore] Envelope: schema=${raw.schema_version}, issued=${raw.issued_at}`);
  }

  const green = _extractGreen(raw);

  const meta: SourceMeta = {
    updatedAt: new Date().toISOString(),
    count: green.length,
    remoteUrl: usedUrl,
  };

  // Load into memory vault
  _loadIntoVault(green, meta);

  // Persist encrypted payload to disk (still AES-encrypted, safe)
  if (encPayload) {
    _saveToDisk(encPayload, meta, expiryHours);
  }

  return { sources: green, meta };
}

export async function getRemoteUrl(): Promise<string> {
  try {
    const saved = await SecureStore.getItemAsync('mg_remote_url');
    return saved || DEFAULT_REMOTE_URL;
  } catch {
    return DEFAULT_REMOTE_URL;
  }
}

export async function setRemoteUrl(url: string): Promise<void> {
  try {
    await SecureStore.setItemAsync('mg_remote_url', url);
  } catch {
    // SecureStore may not be available in Expo Go on some devices
  }
}

// ── Auth token (pre-reserved for future member tier) ─────────────────

/** Get stored auth token (null if free user). */
export async function getAuthToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Store auth token after member login. */
export async function setAuthToken(token: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, token);
  } catch {
    console.log('[SourceStore] Failed to store auth token');
  }
}

/** Clear auth token (logout). */
export async function clearAuthToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY);
  } catch {
    // ignore
  }
}
