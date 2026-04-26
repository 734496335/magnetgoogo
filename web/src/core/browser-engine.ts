/**
 * BrowserEngine — equivalent of Legado's BackstageWebView.
 *
 * Uses Playwright headless Chromium to:
 *  1. Auto-solve Cloudflare JS challenges (no user interaction needed)
 *  2. Render SPA pages that cheerio cannot parse
 *  3. Extract cookies after browser navigation for future fetch reuse
 *  4. Detect interactive CAPTCHAs that still need user intervention
 *
 * Cookie flow mirrors Legado's CookieStore: domain-keyed, shared with
 * the normal fetch path via globalThis.__cookieStore.
 */

import { chromium, type Browser, type BrowserContext, type Page } from 'playwright-core';

/* ---- Singleton browser instance ---- */
let _browser: Browser | null = null;
let _launching: Promise<Browser> | null = null;

async function getBrowser(): Promise<Browser> {
  if (_browser?.isConnected()) return _browser;
  if (_launching) return _launching;
  _launching = (async () => {
    try {
      // Use playwright's bundled Chromium
      const { executablePath } = await findChromium();
      const b = await chromium.launch({
        executablePath,
        headless: true,
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          '--disable-blink-features=AutomationControlled',
          '--disable-dev-shm-usage',
        ],
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

async function findChromium(): Promise<{ executablePath: string }> {
  // Try playwright's managed browsers first
  try {
    const pw = await import('playwright-core');
    // playwright-core stores browser path internally
    const browsers = (pw as any).registry?.executables?.();
    if (browsers) {
      for (const b of browsers) {
        if (b.name === 'chromium' && b.executablePath) {
          return { executablePath: b.executablePath };
        }
      }
    }
  } catch {}

  // Fallback: check common Playwright install paths
  const fs = await import('fs');
  const path = await import('path');
  const home = process.env.USERPROFILE || process.env.HOME || '';
  const playwrightDir = path.join(home, 'AppData', 'Local', 'ms-playwright');

  if (fs.existsSync(playwrightDir)) {
    const dirs = fs.readdirSync(playwrightDir)
      .filter((d: string) => d.startsWith('chromium-'))
      .sort()
      .reverse();
    for (const dir of dirs) {
      // Try both chrome-win64 and chrome-win paths
      for (const sub of ['chrome-win64', 'chrome-win']) {
        const exe = path.join(playwrightDir, dir, sub, 'chrome.exe');
        if (fs.existsSync(exe)) return { executablePath: exe };
      }
    }
  }

  // Last resort: system Chrome
  const systemChrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  if (fs.existsSync(systemChrome)) return { executablePath: systemChrome };

  throw new Error('No Chromium/Chrome found. Run: npx playwright install chromium');
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
  auto_solved?: boolean;   // true if CF was auto-solved by browser
}

/**
 * Fetch a URL using headless Chromium.
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
    // Stealth: remove webdriver flag
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => false });
      // @ts-ignore
      delete navigator.__proto__.webdriver;
    });

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
        // CF JS still running but no interactive element — give up
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
      // Brief wait for dynamic content
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
      auto_solved: hasCfChallenge, // was there a CF challenge that we solved
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
 * Tier 2: Interactive Verification (headed browser)
 * Equivalent of Legado's WebViewActivity + SourceVerificationHelp
 *
 * Flow:
 *   1. Launch visible Chrome window at verification URL
 *   2. User sees Turnstile/hCaptcha/etc. and completes it manually
 *   3. Detect page change (title no longer "Just a moment")
 *   4. Extract cf_clearance + all cookies
 *   5. Store cookies in shared cookieStore → future fetch reuses them
 *   6. Return cookies to caller
 * ============================================================== */

export interface VerifyResult {
  success: boolean;
  cookies: string;
  html?: string;
  url?: string;
  error?: string;
}

/**
 * Launch standalone Chromium (no CDP) with cookie-bridge extension.
 *
 * Flow (mirrors Legado's WebViewActivity + saveVerificationResult):
 *   1. Launch Playwright Chromium via execFile (NO CDP → Turnstile can't detect)
 *   2. Extension auto-submits cookies (incl. HttpOnly) + page HTML to /api/verify
 *   3. Server polls cookieStore for results
 *   4. Returns cookies + HTML (HTML allows direct parsing without cf_clearance)
 */
export async function interactiveVerify(
  url: string,
  timeoutMs: number = 120_000,
): Promise<VerifyResult> {
  const origin = new URL(url).origin;
  console.log(`[BrowserEngine] Interactive verify (uncontrolled): ${url}`);

  const { execFile } = await import('child_process');
  const fs = await import('fs');
  const path = await import('path');
  const os = await import('os');

  // Strategy: use Playwright's Chromium binary (NOT system Chrome) to avoid
  // process reuse issues. Launch via exec (NO CDP) so Turnstile can't detect.
  // Load our cookie-bridge extension to auto-submit HttpOnly cookies.
  const { executablePath: chromiumPath } = await findChromium();

  // Create a temp user-data-dir
  const tmpDir = path.join(os.tmpdir(), `magnet-verify-${Date.now()}`);

  // Clear any old verification cookies for this origin
  cookieStore.delete(origin);

  // Locate our extension
  const extDir = path.resolve(path.join(process.cwd(), 'verify-extension'));
  const hasExt = fs.existsSync(path.join(extDir, 'manifest.json'));
  console.log(`[BrowserEngine] Extension: ${hasExt ? extDir : 'NOT FOUND'}`);

  // Build args for standalone Chromium (no CDP connection)
  const args = [
    `--user-data-dir=${tmpDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--window-size=1024,700',
    '--disable-blink-features=AutomationControlled',
  ];

  if (hasExt) {
    args.push(`--load-extension=${extDir}`);
    args.push(`--disable-extensions-except=${extDir}`);
  } else {
    args.push('--disable-extensions');
  }

  args.push(url);

  console.log(`[BrowserEngine] Launching Chromium: ${chromiumPath}`);
  const child = execFile(chromiumPath, args, { windowsHide: false });
  child.unref();

  // Log any Chrome stderr for debugging
  child.stderr?.on('data', (d: Buffer) => {
    const s = d.toString().trim();
    if (s && !s.includes('DevTools listening') && !s.includes('ERROR:'))
      console.log(`[Chrome] ${s.slice(0, 120)}`);
  });

  // Poll cookieStore for HTML submitted by extension (content.js enriches + submits)
  console.log(`[BrowserEngine] Waiting for HTML via /api/verify (max ${timeoutMs / 1000}s)...`);

  const startTime = Date.now();
  let verified = false;
  let resultCookies = '';
  let cookiesSeenAt = 0;

  while (Date.now() - startTime < timeoutMs) {
    await new Promise(r => setTimeout(r, 2000));

    // Check if cookies/HTML were submitted via /api/verify
    const entry = cookieStore.get(origin);
    if (entry && entry.ts > startTime) {
      if (!cookiesSeenAt) {
        cookiesSeenAt = Date.now();
        console.log(`[BrowserEngine] Cookies arrived for ${origin}, waiting for HTML...`);
      }
      if (entry.html) {
        // HTML received — content.js finished enrichment + submission
        verified = true;
        resultCookies = entry.cookies;
        console.log(`[BrowserEngine] HTML received for ${origin}: ${Math.round(entry.html.length / 1024)}KB`);
        break;
      }
      // Cookies but no HTML yet — wait up to 30s more for content.js enrichment
      if (Date.now() - cookiesSeenAt > 30_000) {
        console.log(`[BrowserEngine] HTML timeout, using cookies only for ${origin}`);
        verified = true;
        resultCookies = entry.cookies;
        break;
      }
    }
  }

  const entry = cookieStore.get(origin);

  // Cleanup temp dir (async, don't wait)
  fs.rm(tmpDir, { recursive: true, force: true }, () => {});
  try { child.kill(); } catch {}

  return {
    success: verified,
    cookies: resultCookies,
    html: entry?.html,
    url: entry?.url,
    error: verified ? undefined : 'Verification timed out — cookies not received',
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
