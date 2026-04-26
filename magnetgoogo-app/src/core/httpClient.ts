/**
 * HTTP Client for local source fetching.
 * Runs on the user's device — no server proxy needed.
 */

const FETCH_HEADERS: Record<string, string> = {
  'User-Agent':
    'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
  Accept:
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
};

// ── Simple in-memory cookie store ────────────────────────────────────
const cookieJar = new Map<string, { cookies: string; ts: number }>();
const COOKIE_TTL = 30 * 60 * 1000; // 30 min

function getStoredCookies(origin: string): string {
  const entry = cookieJar.get(origin);
  if (!entry) return '';
  if (Date.now() - entry.ts > COOKIE_TTL) {
    cookieJar.delete(origin);
    return '';
  }
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

/**
 * Fetch a page with automatic cookie management and challenge detection.
 */
export async function fetchPage(
  url: string,
  extraCookies?: string,
  timeoutMs = 10_000,
): Promise<FetchResult> {
  try {
    const origin = new URL(url).origin;
    const storedCookies = getStoredCookies(origin);
    const allCookies = [storedCookies, extraCookies]
      .filter(Boolean)
      .join('; ');
    const headers: Record<string, string> = { ...FETCH_HEADERS };
    if (allCookies) headers['Cookie'] = allCookies;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const resp = await fetch(url, {
      headers,
      redirect: 'follow',
      signal: controller.signal,
    });
    clearTimeout(timer);

    const html = await resp.text();

    // Challenge detection
    const challenge = detectChallenge(resp.status, html, url);
    if (challenge) {
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
    timeoutMs?: number;
  },
): Promise<{ html: string; cookies: string; status: number } | null> {
  try {
    const headers: Record<string, string> = { ...FETCH_HEADERS };
    if (options?.cookies) headers['Cookie'] = options.cookies;
    if (options?.contentType) headers['Content-Type'] = options.contentType;
    if (options?.referer) headers['Referer'] = options.referer;

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

    const html = await resp.text();
    const cookies = extractCookies(resp);
    return { html, cookies, status: resp.status };
  } catch {
    return null;
  }
}

export { FETCH_HEADERS };
