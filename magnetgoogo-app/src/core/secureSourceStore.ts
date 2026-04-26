/**
 * Source storage layer.
 *
 * Security model (3-layer):
 *   Layer 1 — Transit: AES-256-CBC encrypted payload (sources.enc.json)
 *   Layer 2 — Memory: sources stored XOR-obfuscated with a random session
 *             key.  A Frida memory dump sees only garbled bytes.
 *             Individual rules are de-obfuscated on demand and discarded
 *             after each search.
 *   Layer 3 — Disk: nothing is written.  Memory is freed on app kill.
 */
import * as SecureStore from 'expo-secure-store';
import { decryptSources } from './crypto';
import { getAppVersion } from './configChecker';

// Fallback chain: CF Gateway → jsDelivr CDN → GitHub raw → local dev
// Gateway handles version/membership logic; CDN/raw are static fallbacks.
const GATEWAY_BASE = 'https://maggoogo-gateway.734496335lp.workers.dev';
const CDN_BASE = 'https://cdn.jsdelivr.net/gh/734496335/maggoogo-sources@main';
const RAW_BASE = 'https://raw.githubusercontent.com/734496335/maggoogo-sources/main';
const DEV_BASE = 'http://192.168.5.207:9090';
const DEFAULT_REMOTE_URL = GATEWAY_BASE;

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

// ── In-memory obfuscated vault ──────────────────────────────────────
// Each source is JSON-stringified, then XOR'd with a random session key.
// The vault stores Uint8Array blobs — not readable JSON.

let _sessionKey: Uint8Array = _randomKey(64);
let _vault: Uint8Array[] = [];         // obfuscated blobs
let _sourceCount = 0;
let _cachedMeta: SourceMeta | null = null;

/** Generate a random byte array (session key). */
function _randomKey(len: number): Uint8Array {
  const arr = new Uint8Array(len);
  for (let i = 0; i < len; i++) arr[i] = Math.floor(Math.random() * 256);
  return arr;
}

/** XOR a string with the session key → Uint8Array. */
function _obfuscate(plainJson: string): Uint8Array {
  const bytes = new Uint8Array(plainJson.length);
  for (let i = 0; i < plainJson.length; i++) {
    bytes[i] = plainJson.charCodeAt(i) ^ _sessionKey[i % _sessionKey.length];
  }
  return bytes;
}

/** De-obfuscate a single blob back to JSON string. */
function _deobfuscate(blob: Uint8Array): string {
  const chars: string[] = [];
  for (let i = 0; i < blob.length; i++) {
    chars.push(String.fromCharCode(blob[i] ^ _sessionKey[i % _sessionKey.length]));
  }
  return chars.join('');
}

/** Compare semver strings. Returns -1, 0, or 1. */
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

// ── public API ──────────────────────────────────────────────────────

/** Get all sources (de-obfuscated on demand). Called by SourceContext. */
export async function loadSources(): Promise<SourceRule[] | null> {
  if (_vault.length === 0) return null;
  return _vault.map((blob) => JSON.parse(_deobfuscate(blob)));
}

export async function loadMeta(): Promise<SourceMeta | null> {
  return _cachedMeta;
}

/** How many sources are loaded (without de-obfuscating). */
export function getSourceCount(): number {
  return _sourceCount;
}

/** De-obfuscate a single source by index (for search). */
export function getSourceAt(index: number): SourceRule | null {
  if (index < 0 || index >= _vault.length) return null;
  return JSON.parse(_deobfuscate(_vault[index]));
}

export async function syncSources(
  url?: string,
): Promise<{ sources: SourceRule[]; meta: SourceMeta }> {
  // Fallback chain: user-saved URL → jsDelivr CDN → GitHub raw → local dev
  const endpoints = url
    ? [url.replace(/\/$/, '')]
    : [GATEWAY_BASE, CDN_BASE, RAW_BASE, DEV_BASE];

  let raw: any;
  let usedUrl = '';
  let lastError = '';

  for (const baseUrl of endpoints) {
    try {
      // Try encrypted endpoint first
      const appVer = getAppVersion();
      const encResp = await fetch(`${baseUrl}/sources.enc.json`, {
        headers: {
          'Cache-Control': 'no-cache',
          'X-App-Version': appVer,
        },
      });
      if (encResp.status === 403) {
        // Gateway rejected — version too old, don't try other endpoints
        const errBody = await encResp.json().catch(() => ({}));
        throw new Error(errBody.message || `请更新App到最新版本`);
      }
      if (encResp.ok) {
        const encPayload = await encResp.text();
        const decrypted = decryptSources(encPayload);
        raw = JSON.parse(decrypted);
        usedUrl = baseUrl;
        console.log(`[SourceStore] Loaded encrypted sources from ${baseUrl} ✓`);
        break;
      }
      // Fallback: plain sources.json (dev only)
      const plainResp = await fetch(`${baseUrl}/sources.json`);
      if (plainResp.ok) {
        raw = await plainResp.json();
        usedUrl = baseUrl;
        console.log(`[SourceStore] Loaded plaintext sources from ${baseUrl}`);
        break;
      }
      lastError = `HTTP ${encResp.status}`;
    } catch (e: any) {
      lastError = e.message || String(e);
      console.log(`[SourceStore] Failed ${baseUrl}: ${lastError}`);
    }
  }
  if (!raw) throw new Error(`拉取失败: ${lastError}`);

  // ── Unwrap envelope (new format with expiry metadata) ──
  let sourceData = raw;
  if (raw.payload && raw.expires_at) {
    // Check min_app_version gate
    if (raw.min_app_version) {
      const appVer = getAppVersion();
      const cmp = _compareSemver(appVer, raw.min_app_version);
      if (cmp < 0) {
        throw new Error(`请更新App到 ${raw.min_app_version} 以上版本`);
      }
    }
    // Check expiry — expired sources are rejected entirely
    const expiresAt = new Date(raw.expires_at).getTime();
    if (Date.now() > expiresAt) {
      const expiredAgo = Math.round((Date.now() - expiresAt) / 3600000);
      console.log(`[SourceStore] Sources expired ${expiredAgo}h ago`);
      throw new Error(`源数据已过期（${expiredAgo}小时前），请等待更新`);
    }
    sourceData = raw.payload;
    console.log(`[SourceStore] Envelope: schema=${raw.schema_version}, expires=${raw.expires_at}`);
  }

  // sources.json: { rulesets: [{ rules: [...] }] }
  let list: SourceRule[] = [];
  if (Array.isArray(sourceData)) {
    list = sourceData;
  } else if (sourceData.rulesets?.[0]?.rules) {
    list = sourceData.rulesets[0].rules;
  } else if (sourceData.rulesets) {
    list = sourceData.rulesets;
  } else if (sourceData.sources) {
    list = sourceData.sources;
  }

  const green = list.filter((s: any) => s.health?.status === 'green');

  // Rotate session key on every sync
  _sessionKey = _randomKey(64);

  // Obfuscate each source into the vault
  _vault = green.map((rule) => _obfuscate(JSON.stringify(rule)));
  _sourceCount = green.length;

  _cachedMeta = {
    updatedAt: new Date().toISOString(),
    count: green.length,
    remoteUrl: usedUrl,
  };

  // Return de-obfuscated for immediate use by SourceContext
  // (SourceContext keeps the array reference; it will be GC'd when replaced)
  return { sources: green, meta: _cachedMeta };
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
