/**
 * HTTP Client for local source fetching.
 * Runs on the user's device — no server proxy needed.
 */
import iconv from 'iconv-lite';
import { Buffer } from 'buffer';
import { Paths, File as FSFile } from 'expo-file-system';

const FETCH_HEADERS: Record<string, string> = {
  'User-Agent':
    'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
  Accept:
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
};
let _backgroundNetworkMode = false;

// ── Persistent cookie store ──────────────────────────────────────────
// Cookies are saved permanently. If they expire, the server returns a
// challenge and the verification flow re-triggers automatically.
const cookieJar = new Map<string, { cookies: string; ts: number }>();

function getCookieFile(): FSFile {
  return new FSFile(Paths.document, 'verify-cookies.json');
}

/** Load persisted cookies from disk (call once at app startup). */
export async function loadPersistedCookies(): Promise<void> {
  try {
    const file = getCookieFile();
    if (!file.exists) return;
    const json = await file.text();
    const data = JSON.parse(json) as Record<string, { cookies: string; ts: number }>;
    let loaded = 0;
    for (const [origin, entry] of Object.entries(data)) {
      cookieJar.set(origin, entry);
      loaded++;
    }
    if (loaded > 0) console.log(`[httpClient] Loaded ${loaded} persisted cookie origins`);
  } catch (e) {
    console.log('[httpClient] Failed to load persisted cookies:', e);
  }
}

let _persistTimer: ReturnType<typeof setTimeout> | null = null;
function schedulePersist() {
  if (_persistTimer) return;
  _persistTimer = setTimeout(() => {
    _persistTimer = null;
    try {
      const data: Record<string, { cookies: string; ts: number }> = {};
      for (const [origin, entry] of cookieJar.entries()) {
        data[origin] = entry;
      }
      const file = getCookieFile();
      if (!file.exists) file.create();
      file.write(JSON.stringify(data));
    } catch (e) {
      console.log('[httpClient] Failed to persist cookies:', e);
    }
  }, 500);
}

/** Remove persisted cookies for an origin (called when challenge re-appears). */
export function invalidateCookies(origin: string) {
  console.log(`[Verify:Cookie] Invalidating cookies for ${origin}`);
  cookieJar.delete(origin);
  schedulePersist();
}

export function getStoredCookies(origin: string): string {
  const entry = cookieJar.get(origin);
  if (!entry) return '';
  return entry.cookies;
}

export function extractCookies(resp: Response): string {
  // React Native allows reading set-cookie unlike browser fetch
  const raw = resp.headers.get('set-cookie') || '';
  if (!raw) return '';
  return raw
    .split(',')
    .map((c) => c.split(';')[0].trim())
    .filter(Boolean)
    .join('; ');
}

export function mergeCookies(a: string, b: string): string {
  const map = new Map<string, string>();
  for (const s of [a, b]) {
    for (const pair of s
      .split(';')
      .map((p) => p.trim())
      .filter(Boolean)) {
      const eq = pair.indexOf('=');
      if (eq > 0) map.set(pair.substring(0, eq), pair.substring(eq + 1));
    }
  }
  return [...map.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
}

export interface FetchResult {
  html: string | null;
  status?: number;
  challenge?: { type: string; verifyUrl: string };
}

interface XhrResult {
  status: number;
  responseText: string;
  headers: Record<string, string>;
  responseURL?: string;
}

export function setBackgroundNetworkMode(enabled: boolean) {
  _backgroundNetworkMode = enabled;
}

export function isBackgroundNetworkMode(): boolean {
  return _backgroundNetworkMode;
}

function parseRawHeaders(raw: string): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const line of raw.split(/\r?\n/)) {
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim().toLowerCase();
    const value = line.slice(idx + 1).trim();
    if (!key) continue;
    headers[key] = headers[key] ? `${headers[key]}, ${value}` : value;
  }
  return headers;
}

function xhrRequest(
  url: string,
  options?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    timeoutMs?: number;
  },
): Promise<XhrResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options?.method || 'GET', url, true);
    xhr.timeout = options?.timeoutMs ?? 10_000;
    for (const [k, v] of Object.entries(options?.headers || {})) {
      xhr.setRequestHeader(k, v);
    }
    xhr.onreadystatechange = () => {
      if (xhr.readyState !== 4) return;
      resolve({
        status: xhr.status,
        responseText: xhr.responseText || '',
        headers: parseRawHeaders(xhr.getAllResponseHeaders?.() || ''),
        responseURL: (xhr as any).responseURL || undefined,
      });
    };
    xhr.ontimeout = () => reject(new Error('timeout'));
    xhr.onerror = () => reject(new Error('network_error'));
    xhr.send(options?.body ?? null);
  });
}

function detectChallenge(
  status: number,
  html: string,
  url: string,
): { type: string; verifyUrl: string } | undefined {
  if (
    html.includes('cf-browser-verification') ||
    html.includes('cf_chl_opt') ||
    (html.includes('Just a moment') && html.includes('cloudflare'))
  ) {
    return { type: 'cloudflare', verifyUrl: url };
  }
  if (
    status === 403 &&
    (html.includes('cf-error') ||
      html.includes('cloudflare') ||
      html.length < 6000)
  ) {
    return { type: 'cloudflare_block', verifyUrl: url };
  }
  if (
    /captcha|recaptcha|hcaptcha|verify.you.are.human/i.test(html.slice(0, 5000))
  ) {
    return { type: 'captcha', verifyUrl: url };
  }
  if (html.includes('DDoS-Guard') || html.includes('ddos-guard')) {
    return { type: 'ddos_guard', verifyUrl: url };
  }
  return undefined;
}

// ── Charset-aware response decoding ─────────────────────────────────
// Many Asian torrent sites serve Shift-JIS, GB2312, or EUC-JP pages.
// Default `resp.text()` assumes UTF-8, causing mojibake.

async function decodeResponse(resp: Response): Promise<string> {
  // 1) Check Content-Type header for charset
  const ct = resp.headers.get('content-type') || '';
  const headerCharset = ct.match(/charset\s*=\s*["']?([^\s;"']+)/i)?.[1]?.toLowerCase();

  // 2) If header says UTF-8 or no charset, try text() first (fast path)
  if (!headerCharset || headerCharset === 'utf-8' || headerCharset === 'utf8') {
    const buf = Buffer.from(await resp.arrayBuffer());
    // Quick sniff: check for <meta charset="xxx"> in first 2KB
    const head = buf.slice(0, 2048).toString('ascii');
    const metaCharset = head.match(
      /charset\s*=\s*["']?([^\s;"'/>]+)/i,
    )?.[1]?.toLowerCase();

    if (metaCharset && metaCharset !== 'utf-8' && metaCharset !== 'utf8' && iconv.encodingExists(metaCharset)) {
      return iconv.decode(buf, metaCharset);
    }
    // Check for mojibake indicators: if bytes look like non-UTF-8
    return buf.toString('utf-8');
  }

  // 3) Explicit non-UTF-8 charset from header
  const buf = Buffer.from(await resp.arrayBuffer());
  const enc = headerCharset.replace(/^x-/, '');
  if (iconv.encodingExists(enc)) {
    return iconv.decode(buf, enc);
  }
  return buf.toString('utf-8');
}

/**
 * Fetch a page with automatic cookie management and challenge detection.
 */
export async function fetchPage(
  url: string,
  extraCookies?: string,
  timeoutMs = 10_000,
  referer?: string,
): Promise<FetchResult> {
  try {
    const origin = new URL(url).origin;
    const storedCookies = getStoredCookies(origin);
    const allCookies = [storedCookies, extraCookies]
      .filter(Boolean)
      .join('; ');
    if (storedCookies) console.log(`[Verify:Cookie] Sending stored cookies for ${origin}: ${storedCookies.slice(0, 80)}...`);
    const headers: Record<string, string> = { ...FETCH_HEADERS };
    if (allCookies) headers['Cookie'] = allCookies;
    if (referer) headers['Referer'] = referer;

    const host = new URL(url).hostname;
    if (_backgroundNetworkMode) {
      let xr: XhrResult;
      try {
        xr = await xhrRequest(url, {
          method: 'GET',
          headers,
          timeoutMs,
        });
      } catch (e: any) {
        console.log(`[httpClient] ${host} XHR FAILED: ${e?.message || 'unknown'} (${timeoutMs}ms)`);
        return { html: null };
      }
      const html = xr.responseText || '';
      console.log(`[httpClient] ${host} xhr status=${xr.status} htmlLen=${html.length}`);
      const challenge = detectChallenge(xr.status, html, xr.responseURL || url);
      if (challenge) {
        console.log(`[Verify:Challenge] Detected ${challenge.type} on ${new URL(url).origin} (status=${xr.status}, hasCookies=${!!storedCookies})`);
        return { html: null, status: xr.status, challenge };
      }
      if (xr.status < 200 || xr.status >= 300) return { html: null, status: xr.status };
      const newCookies = xr.headers['set-cookie'] || '';
      if (newCookies) {
        const merged = mergeCookies(storedCookies, newCookies);
        cookieJar.set(origin, { cookies: merged, ts: Date.now() });
      }
      return { html, status: xr.status };
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let resp: Response;
    try {
      resp = await fetch(url, {
        headers,
        redirect: 'follow',
        signal: controller.signal,
      });
    } catch (e: any) {
      clearTimeout(timer);
      const reason = e?.name === 'AbortError' ? 'timeout' : (e?.message || 'unknown');
      console.log(`[httpClient] ${host} FETCH FAILED: ${reason} (${timeoutMs}ms)`);
      return { html: null };
    }
    clearTimeout(timer);

    const html = await decodeResponse(resp);
    console.log(`[httpClient] ${host} status=${resp.status} htmlLen=${html.length}`);

    // Challenge detection
    const challenge = detectChallenge(resp.status, html, url);
    if (challenge) {
      console.log(`[Verify:Challenge] Detected ${challenge.type} on ${new URL(url).origin} (status=${resp.status}, hasCookies=${!!storedCookies})`);
      return { html: null, status: resp.status, challenge };
    }

    if (!resp.ok) return { html: null, status: resp.status };

    // Store cookies
    const newCookies = extractCookies(resp);
    if (newCookies) {
      const merged = mergeCookies(storedCookies, newCookies);
      cookieJar.set(origin, { cookies: merged, ts: Date.now() });
    }

    return { html, status: resp.status };
  } catch {
    return { html: null };
  }
}

/**
 * Store cookies for an origin (from WebView verification sessions).
 * Called by searchEngine after successful verification.
 */
export function storeCookiesForOrigin(origin: string, cookies: string) {
  if (!cookies) return;
  const existing = getStoredCookies(origin);
  const merged = existing ? mergeCookies(existing, cookies) : cookies;
  cookieJar.set(origin, { cookies: merged, ts: Date.now() });
  console.log(`[Verify:Cookie] Stored cookies for ${origin}: ${merged.slice(0, 80)}...`);
  schedulePersist();
}

/**
 * Fetch page with manual redirect handling (for sites needing cookie chains).
 */
export async function fetchPageManual(
  url: string,
  options?: {
    method?: string;
    body?: string;
    contentType?: string;
    cookies?: string;
    referer?: string;
    extraHeaders?: Record<string, string>;
    timeoutMs?: number;
  },
): Promise<{ html: string; cookies: string; status: number; responseUrl?: string } | null> {
  try {
    const headers: Record<string, string> = { ...FETCH_HEADERS, ...(options?.extraHeaders ?? {}) };
    if (options?.cookies) headers['Cookie'] = options.cookies;
    if (options?.contentType) headers['Content-Type'] = options.contentType;
    if (options?.referer) headers['Referer'] = options.referer;

    if (_backgroundNetworkMode) {
      const xr = await xhrRequest(url, {
        method: options?.method ?? 'GET',
        headers,
        body: options?.body,
        timeoutMs: options?.timeoutMs ?? 10_000,
      });
      return {
        html: xr.responseText || '',
        cookies: xr.headers['set-cookie'] || '',
        status: xr.status,
        responseUrl: xr.responseURL,
      };
    }

    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(),
      options?.timeoutMs ?? 10_000,
    );

    const resp = await fetch(url, {
      method: options?.method ?? 'GET',
      headers,
      body: options?.body,
      redirect: 'manual',
      signal: controller.signal,
    });
    clearTimeout(timer);

    const location = resp.headers.get('location');
    const responseUrl = location
      ? (location.startsWith('http') ? location : new URL(location, url).href)
      : undefined;
    const html = await decodeResponse(resp);
    const cookies = extractCookies(resp);
    return { html, cookies, status: resp.status, responseUrl };
  } catch {
    return null;
  }
}

export { FETCH_HEADERS };
