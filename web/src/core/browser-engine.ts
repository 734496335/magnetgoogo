/**
 * BrowserEngine — equivalent of Legado's BackstageWebView.
 *
 * Uses CloakBrowser (anti-fingerprint Chromium) to:
 *  1. Auto-solve Cloudflare JS challenges (no user interaction needed)
 *  2. Render SPA pages that cheerio cannot parse
 *  3. Extract cookies after browser navigation for future fetch reuse
 *  4. Detect interactive CAPTCHAs that still need user intervention
 *
 * Cookie flow mirrors Legado's CookieStore: domain-keyed, shared with
 * the normal fetch path via globalThis.__cookieStore.
 */

import type { Browser, BrowserContext } from 'playwright-core';

/* ---- CloakBrowser launcher (lazy, ESM-only package) ---- */
let _launchCloak: typeof import('cloakbrowser')['launch'] | null = null;

async function getLaunch() {
  if (_launchCloak) return _launchCloak;
  const mod = await import('cloakbrowser');
  _launchCloak = mod.launch;
  return _launchCloak;
}

/* ---- Singleton browser instance ---- */
let _browser: Browser | null = null;
let _launching: Promise<Browser> | null = null;

const FORCE_HEADLESS = process.env.CLOAK_FORCE_HEADLESS === '1';

async function getBrowser(): Promise<Browser> {
  if (_browser?.isConnected()) return _browser;
  if (_launching) return _launching;
  _launching = (async () => {
    try {
      const launch = await getLaunch();
      const b = await launch({
        headless: FORCE_HEADLESS ? true : true,  // default headless for browserFetch
        humanize: true,
      });
      _browser = b;
      b.on('disconnected', () => { _browser = null; });
      return b;
    } finally {
      _launching = null;
    }
  })();
  return _launching;
}

/* ---- Shared cookie store (same as route.ts) ---- */
const cookieStore: Map<string, { cookies: string; html?: string; url?: string; ts: number }> =
  (globalThis as any).__cookieStore ??= new Map();
const COOKIE_TTL = 30 * 60 * 1000;

/* ---- Public API ---- */

export interface BrowserFetchResult {
  html: string | null;
  cookies: string;
  challenge?: { type: string; verifyUrl: string };
  auto_solved?: boolean;
}

/**
 * Fetch a URL using headless CloakBrowser.
 * Auto-solves CF JS challenges. Returns challenge info if interactive CAPTCHA detected.
 */
export async function browserFetch(
  url: string,
  opts: { timeout?: number; waitForSelector?: string } = {},
): Promise<BrowserFetchResult> {
  const timeout = opts.timeout ?? 30_000;
  const browser = await getBrowser();
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });

  // Inject stored cookies
  const origin = new URL(url).origin;
  const storedEntry = cookieStore.get(origin);
  if (storedEntry && Date.now() - storedEntry.ts < COOKIE_TTL) {
    const parsed = storedEntry.cookies.split(';').map(p => {
      const [name, ...rest] = p.trim().split('=');
      return { name: name?.trim(), value: rest.join('=')?.trim(), url: origin };
    }).filter(c => c.name);
    if (parsed.length) await context.addCookies(parsed);
  }

  const page = await context.newPage();

  try {
    const response = await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout,
    });

    // Detect CF challenge via JS var + DOM + title (mirrors Legado's _cf_chl_opt check)
    const hasCfChallenge = await page.evaluate(() =>
      !!(window as any)._cf_chl_opt ||
      !!document.querySelector('#cf-challenge-running') ||
      !!document.querySelector('.cf-browser-verification') ||
      /just a moment|稍候|checking your browser/i.test(document.title)
    );

    if (hasCfChallenge) {
      console.log(`[BrowserEngine] CF challenge detected on ${url}, waiting for auto-solve...`);
      try {
        // Wait for title to change (more reliable than URL-based detection)
        await page.waitForFunction(
          () => !/just a moment|稍候|checking/i.test(document.title),
          { timeout: 20_000 },
        );
        console.log(`[BrowserEngine] CF challenge auto-solved for ${url}`);
      } catch {
        // Still on challenge page — check if interactive CAPTCHA
        const needsInteraction = await page.evaluate(() =>
          !!document.querySelector('iframe[src*="turnstile"]') ||
          !!document.querySelector('iframe[src*="hcaptcha"]') ||
          !!document.querySelector('iframe[src*="recaptcha"]') ||
          !!document.querySelector('.g-recaptcha') ||
          !!document.querySelector('.h-captcha')
        );
        if (needsInteraction) {
          console.log(`[BrowserEngine] Interactive CAPTCHA on ${url}, escalating to user`);
          const cookies = await extractBrowserCookies(context, origin);
          await context.close();
          return {
            html: null,
            cookies,
            challenge: { type: 'interactive_captcha', verifyUrl: url },
          };
        }
        console.log(`[BrowserEngine] CF challenge timeout on ${url}`);
        await context.close();
        return {
          html: null,
          cookies: '',
          challenge: { type: 'cloudflare_timeout', verifyUrl: url },
        };
      }
    }

    // Wait for content to render
    if (opts.waitForSelector) {
      try {
        await page.waitForSelector(opts.waitForSelector, { timeout: 8_000 });
      } catch {}
    } else {
      await page.waitForTimeout(1500);
    }

    // Check again for late CAPTCHA / WAF
    const bodyHtml = await page.content();
    const needsCaptcha =
      /captcha|recaptcha|hcaptcha|verify.you.are.human/i.test(bodyHtml.slice(0, 5000)) &&
      bodyHtml.length < 20_000;

    if (needsCaptcha) {
      const cookies = await extractBrowserCookies(context, origin);
      await context.close();
      return {
        html: null,
        cookies,
        challenge: { type: 'captcha', verifyUrl: url },
      };
    }

    // Extract cookies and persist
    const cookies = await extractBrowserCookies(context, origin);
    if (cookies) {
      cookieStore.set(origin, { cookies, ts: Date.now() });
    }

    await context.close();
    return {
      html: bodyHtml,
      cookies,
      auto_solved: hasCfChallenge,
    };
  } catch (err: any) {
    console.error(`[BrowserEngine] Error fetching ${url}: ${err.message}`);
    await context.close().catch(() => {});
    return { html: null, cookies: '' };
  }
}

async function extractBrowserCookies(context: BrowserContext, origin: string): Promise<string> {
  try {
    const allCookies = await context.cookies(origin);
    return allCookies.map(c => `${c.name}=${c.value}`).join('; ');
  } catch {
    return '';
  }
}

/* ==============================================================
 * Tier 2: Interactive Verification (headed CloakBrowser)
 *
 * Flow:
 *   1. Launch visible CloakBrowser (humanize=True for Turnstile auto-pass)
 *   2. Navigate to verification URL
 *   3. CloakBrowser auto-solves Turnstile/CF challenges
 *   4. Extract cf_clearance + all cookies
 *   5. Store cookies in shared cookieStore → future fetch reuses them
 * ============================================================== */

export interface VerifyResult {
  success: boolean;
  cookies: string;
  html?: string;
  url?: string;
  error?: string;
}

/**
 * Launch headed CloakBrowser for interactive verification.
 *
 * CloakBrowser's humanize mode auto-solves Turnstile via C++-level patches.
 * No extension needed — the browser itself handles the challenge.
 */
export async function interactiveVerify(
  url: string,
  timeoutMs: number = 120_000,
): Promise<VerifyResult> {
  const origin = new URL(url).origin;
  console.log(`[BrowserEngine] Interactive verify (CloakBrowser headed): ${url}`);

  // Clear any old verification cookies for this origin
  cookieStore.delete(origin);

  const launch = await getLaunch();
  const headed = !FORCE_HEADLESS;
  const browser = await launch({
    headless: headed ? false : true,
    humanize: true,
  });

  let resultCookies = '';
  let resultHtml: string | undefined;
  let verified = false;

  try {
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
      locale: 'zh-CN',
      timezoneId: 'Asia/Shanghai',
    });

    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });

    // Wait for CF/Turnstile to auto-solve (CloakBrowser humanize handles this)
    try {
      await page.waitForFunction(
        () => !/just a moment|稍候|checking/i.test(document.title),
        { timeout: Math.min(timeoutMs, 60_000) },
      );
    } catch {
      console.log(`[BrowserEngine] Challenge timeout for ${url}`);
    }

    // Brief wait for SPA content to hydrate
    await page.waitForTimeout(2000);

    resultHtml = await page.content();
    resultCookies = await extractBrowserCookies(context, origin);
    verified = true;

    // Persist cookies for future fetch reuse
    if (resultCookies) {
      cookieStore.set(origin, { cookies: resultCookies, html: resultHtml, url, ts: Date.now() });
    }

    await context.close();
  } catch (err: any) {
    console.error(`[BrowserEngine] Interactive verify error: ${err.message}`);
  } finally {
    try { await browser.close(); } catch {}
  }

  return {
    success: verified,
    cookies: resultCookies,
    html: resultHtml,
    url,
    error: verified ? undefined : 'Verification timed out or failed',
  };
}

/**
 * Gracefully close the shared headless browser instance.
 */
export async function closeBrowser(): Promise<void> {
  if (_browser) {
    await _browser.close().catch(() => {});
    _browser = null;
  }
}
