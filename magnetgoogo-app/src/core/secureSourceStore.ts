/**
 * Source storage layer.
 *
 * Security model:
 *   Layer 1: transit payload remains encrypted (sources.enc.json)
 *   Layer 2: disk cache stores the encrypted payload, not plaintext
 *   Layer 3: in-memory rules are obfuscated with a session key
 */
import * as SecureStore from 'expo-secure-store';
import { Directory, File, Paths } from 'expo-file-system';
import { decryptSources } from './crypto';
import { getAppVersion } from './configChecker';
import { COMPLIANCE_MODE } from './complianceConfig';
import bootstrapPayload from '../../assets/bootstrap-sources.enc.json';

const SOURCE_FILE = COMPLIANCE_MODE ? '/sources-green.enc.json' : '/sources.enc.json';
const DEBUG_SOURCE_FILE = new File(Paths.document, 'debug-sources.enc.json');

const CN_ALI = 'https://cn.magnetgoogo.com';
const CN_BASE = 'https://magnetgoogo.com';
const CDN_BASE = 'https://cdn.jsdelivr.net/gh/734496335/mg-data@main';
const RAW_BASE = 'https://raw.githubusercontent.com/734496335/mg-data/main';
const GATEWAY_BASE = 'https://api.naoshiquan.com';
const GATEWAY_OLD = 'https://maggoogo-gateway.734496335lp.workers.dev';
const DEFAULT_REMOTE_URL = CDN_BASE;

const CACHE_DIR = new Directory(Paths.document, 'source-cache');
const CACHE_FILE = new File(CACHE_DIR, 'sources.cache.json');
const DEFAULT_EXPIRY_HOURS = 72;
const BOOTSTRAP_EXPIRY_HOURS = 24 * 7;
const BOOTSTRAP_FIRST_USED_KEY = 'mg_bootstrap_first_used_at';
const AUTH_TOKEN_KEY = 'mg_auth_token';

function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 8000): Promise<Response> {
  return new Promise((resolve, reject) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      ctrl.abort();
      reject(new Error('timeout'));
    }, timeoutMs);
    fetch(url, { ...options, signal: ctrl.signal })
      .then((resp) => {
        clearTimeout(timer);
        resolve(resp);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

async function raceFetchOk(
  urls: string[],
  path: string,
  headers: Record<string, string>,
  timeoutMs = 12000,
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
    console.log(`[SourceStore] ${base} responded first`);
    return { text, url: base };
  });
  return Promise.any(promises);
}

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
  encPayload: string;
  savedAt: string;
  expiryHours: number;
  count: number;
  remoteUrl: string;
}

let _sessionKey: Uint8Array = randomKey(64);
let _vault: Uint8Array[] = [];
let _sourceCount = 0;
let _cachedMeta: SourceMeta | null = null;
let _activeSourceKind: 'bootstrap' | 'remote' | null = null;
const _textEncoder = new TextEncoder();
const _textDecoder = new TextDecoder();

function randomKey(len: number): Uint8Array {
  const arr = new Uint8Array(len);
  for (let i = 0; i < len; i++) arr[i] = Math.floor(Math.random() * 256);
  return arr;
}

function obfuscate(plainJson: string): Uint8Array {
  const bytes = _textEncoder.encode(plainJson);
  const out = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) {
    out[i] = bytes[i] ^ _sessionKey[i % _sessionKey.length];
  }
  return out;
}

function deobfuscate(blob: Uint8Array): string {
  const bytes = new Uint8Array(blob.length);
  for (let i = 0; i < blob.length; i++) {
    bytes[i] = blob[i] ^ _sessionKey[i % _sessionKey.length];
  }
  return _textDecoder.decode(bytes);
}

function compareSemver(a: string, b: string): number {
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

function saveToDisk(encPayload: string, meta: SourceMeta, expiryHours: number) {
  try {
    if (!CACHE_DIR.exists) CACHE_DIR.create();
    const cache: DiskCache = {
      encPayload,
      savedAt: new Date().toISOString(),
      expiryHours,
      count: meta.count,
      remoteUrl: meta.remoteUrl,
    };
    if (!CACHE_FILE.exists) CACHE_FILE.create();
    CACHE_FILE.write(JSON.stringify(cache));
    console.log(`[SourceStore] Saved ${meta.count} sources to disk cache`);
  } catch (e: any) {
    console.log(`[SourceStore] Disk save failed: ${e.message}`);
  }
}

function loadFromDisk(): { green: SourceRule[]; meta: SourceMeta } | null {
  try {
    if (!CACHE_FILE.exists) return null;
    const text = CACHE_FILE.textSync();
    const cache: DiskCache = JSON.parse(text);
    const savedAt = new Date(cache.savedAt).getTime();
    const expiresAt = savedAt + cache.expiryHours * 3600000;
    if (Date.now() > expiresAt) {
      const expiredAgo = Math.round((Date.now() - expiresAt) / 3600000);
      console.log(`[SourceStore] Disk cache expired ${expiredAgo}h ago, will re-sync`);
      return null;
    }

    const decrypted = decryptSources(cache.encPayload);
    const raw = JSON.parse(decrypted);
    const green = extractGreen(raw);
    const meta: SourceMeta = {
      updatedAt: cache.savedAt,
      count: green.length,
      remoteUrl: `${cache.remoteUrl} (cached)`,
    };
    console.log(`[SourceStore] Loaded ${green.length} sources from disk cache`);
    return { green, meta };
  } catch (e: any) {
    console.log(`[SourceStore] Disk load failed: ${e.message}`);
    return null;
  }
}

function extractGreen(raw: any): SourceRule[] {
  let sourceData = raw;
  if (raw.payload) {
    if (raw.min_app_version) {
      const appVer = getAppVersion();
      if (compareSemver(appVer, raw.min_app_version) < 0) return [];
    }
    sourceData = raw.payload;
  }

  let list: SourceRule[] = [];
  if (Array.isArray(sourceData)) {
    list = sourceData;
  } else if (sourceData.rulesets && Array.isArray(sourceData.rulesets)) {
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

function loadIntoVault(green: SourceRule[], meta: SourceMeta) {
  _sessionKey = randomKey(64);
  _vault = green.map((rule) => obfuscate(JSON.stringify(rule)));
  _sourceCount = green.length;
  _cachedMeta = meta;
}

async function getBootstrapFirstUsedAt(): Promise<number> {
  try {
    const saved = await SecureStore.getItemAsync(BOOTSTRAP_FIRST_USED_KEY);
    const parsed = saved ? Number(saved) : 0;
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
    const now = Date.now();
    await SecureStore.setItemAsync(BOOTSTRAP_FIRST_USED_KEY, String(now));
    return now;
  } catch {
    return Date.now();
  }
}

async function loadBootstrapSources(): Promise<{ green: SourceRule[]; meta: SourceMeta } | null> {
  try {
    const firstUsedAt = await getBootstrapFirstUsedAt();
    const expiresAt = firstUsedAt + BOOTSTRAP_EXPIRY_HOURS * 3600000;
    if (Date.now() > expiresAt) {
      const expiredAgo = Math.round((Date.now() - expiresAt) / 3600000);
      console.log(`[SourceStore] Bootstrap sources expired ${expiredAgo}h ago`);
      return null;
    }

    const text = JSON.stringify(bootstrapPayload);
    if (!text || text.length < 10) {
      throw new Error('bootstrap asset empty');
    }

    const decrypted = decryptSources(text);
    const raw = JSON.parse(decrypted);
    const green = extractGreen(raw);
    const remainingHours = Math.max(0, Math.round((expiresAt - Date.now()) / 3600000));
    const meta: SourceMeta = {
      updatedAt: new Date(firstUsedAt).toISOString(),
      count: green.length,
      remoteUrl: `bootstrap://assets/bootstrap-sources.enc.json (${remainingHours}h left)`,
    };
    console.log(`[SourceStore] Loaded ${green.length} bootstrap sources from bundled asset`);
    return { green, meta };
  } catch (e: any) {
    console.log(`[SourceStore] Bootstrap load failed: ${e.message}`);
    return null;
  }
}

export async function loadSources(): Promise<SourceRule[] | null> {
  if (_vault.length > 0) {
    return _vault.map((blob) => JSON.parse(deobfuscate(blob)));
  }

  const disk = loadFromDisk();
  if (disk) {
    _activeSourceKind = 'remote';
    loadIntoVault(disk.green, disk.meta);
    return disk.green;
  }

  const bootstrap = await loadBootstrapSources();
  if (bootstrap) {
    _activeSourceKind = 'bootstrap';
    loadIntoVault(bootstrap.green, bootstrap.meta);
    return bootstrap.green;
  }

  return null;
}

export async function loadMeta(): Promise<SourceMeta | null> {
  if (_cachedMeta) return _cachedMeta;
  try {
    if (!CACHE_FILE.exists) return null;
    const text = CACHE_FILE.textSync();
    const cache: DiskCache = JSON.parse(text);
    return {
      updatedAt: cache.savedAt,
      count: cache.count,
      remoteUrl: `${cache.remoteUrl} (cached)`,
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
  return JSON.parse(deobfuscate(_vault[index]));
}

export async function syncSources(url?: string): Promise<{ sources: SourceRule[]; meta: SourceMeta }> {
  // Prefer explicit on-device debug override when present (adb push files/debug-sources.enc.json).
  // Not gated on __DEV__ so Hermes release-mode debug APKs can still load pushed source packs.
  if (!url && DEBUG_SOURCE_FILE.exists) {
    try {
      const encPayload = DEBUG_SOURCE_FILE.textSync();
      if (encPayload && encPayload.length > 100) {
        const decrypted = decryptSources(encPayload);
        const envelope = JSON.parse(decrypted);
        const green = extractGreen(envelope);
        loadIntoVault(green, {
          updatedAt: envelope.issued_at || new Date().toISOString(),
          count: green.length,
          remoteUrl: 'local://debug-sources.enc.json',
        });
        console.log(`[SourceStore] loaded ${green.length} green from debug-sources.enc.json`);
        return { sources: green, meta: _cachedMeta! };
      }
    } catch (e: any) {
      console.log(`[SourceStore] debug source file failed: ${e.message}, falling back to remote`);
    }
  } else if (__DEV__ && !url) {
    console.log('[SourceStore] __DEV__ no explicit debug source file, using normal cache + remote sync');
  }

  const endpoints = url
    ? [url.replace(/\/$/, '')]
    : [CN_BASE, GATEWAY_BASE, CDN_BASE, RAW_BASE, GATEWAY_OLD, CN_ALI];

  const appVer = getAppVersion();
  const authToken = await getAuthToken();
  const headers: Record<string, string> = {
    'Cache-Control': 'no-cache',
    'X-App-Version': appVer,
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let raw: any;
  let encPayload = '';
  let usedUrl = '';

  try {
    const result = await raceFetchOk(endpoints, SOURCE_FILE, headers, 12000);
    encPayload = result.text;
    const decrypted = decryptSources(encPayload);
    raw = JSON.parse(decrypted);
    usedUrl = result.url;
  } catch (raceErr: any) {
    console.log(`[SourceStore] Tier 1 failed: ${raceErr.message}, trying sequentially...`);
    let found = false;
    for (const base of endpoints) {
      try {
        const resp = await fetchWithTimeout(`${base}${SOURCE_FILE}`, { headers }, 20000);
        if (resp.status === 403) {
          const errBody = await resp.json().catch(() => ({}));
          throw new Error(errBody.message || '请更新App到最新版本');
        }
        if (!resp.ok) continue;
        const text = await resp.text();
        if (!text || text.length < 10) continue;
        const decrypted = decryptSources(text);
        raw = JSON.parse(decrypted);
        encPayload = text;
        usedUrl = base;
        found = true;
        console.log(`[SourceStore] Fallback succeeded via ${base}`);
        break;
      } catch (e: any) {
        console.log(`[SourceStore] ${base} failed: ${e.message}`);
      }
    }
    if (!found) {
      throw new Error('所有端点均不可达，请检查网络');
    }
  }

  let expiryHours = DEFAULT_EXPIRY_HOURS;
  if (raw.payload) {
    if (raw.min_app_version && compareSemver(appVer, raw.min_app_version) < 0) {
      throw new Error(`请更新App到 ${raw.min_app_version} 以上版本`);
    }
    if (raw.expires_at) {
      const exp = new Date(raw.expires_at);
      if (!isNaN(exp.getTime())) {
        expiryHours = Math.max(1, Math.round((exp.getTime() - Date.now()) / 3600_000));
      }
    }
    console.log(`[SourceStore] Envelope: schema=${raw.schema_version}, issued=${raw.issued_at}`);
  }

  const green = extractGreen(raw);
  const meta: SourceMeta = {
    updatedAt: new Date().toISOString(),
    count: green.length,
    remoteUrl: usedUrl,
  };

  loadIntoVault(green, meta);
  _activeSourceKind = 'remote';
  if (encPayload) {
    saveToDisk(encPayload, meta, expiryHours);
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
    // ignore
  }
}

export async function getAuthToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function setAuthToken(token: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, token);
  } catch {
    console.log('[SourceStore] Failed to store auth token');
  }
}

export async function clearAuthToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY);
  } catch {
    // ignore
  }
}
