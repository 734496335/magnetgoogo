import { NextRequest, NextResponse } from 'next/server';
import * as cheerio from 'cheerio';
import { ProxyAgent, fetch as undiciFetch } from 'undici';
import * as iconv from 'iconv-lite';
import { browserFetch, interactiveVerify } from '@/core/browser-engine';

/* ---- Proxy support ---- */
const PROXY_URL = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || process.env.ALL_PROXY || '';
const fetchDispatcher = PROXY_URL ? new ProxyAgent({ uri: PROXY_URL }) : undefined;
if (PROXY_URL) console.log(`[Proxy] Using proxy: ${PROXY_URL}`);

// Use undici.fetch when proxy is active (Node v24 global fetch ignores dispatcher)
const pfetch: typeof globalThis.fetch = fetchDispatcher
  ? ((url: any, init?: any) => undiciFetch(url, { ...init, dispatcher: fetchDispatcher }) as any)
  : globalThis.fetch;

const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
};

interface FetchResult {
  html: string | null;
  challenge?: { type: string; verifyUrl: string };
}

function detectChallenge(status: number, html: string, url: string): { type: string; verifyUrl: string } | undefined {
  // Cloudflare JS challenge / Turnstile
  if (html.includes('cf-browser-verification') || html.includes('cf_chl_opt') ||
      html.includes('Just a moment') && html.includes('cloudflare')) {
    return { type: 'cloudflare', verifyUrl: url };
  }
  // Cloudflare 403 with challenge
  if (status === 403 && (html.includes('cf-error') || html.includes('cloudflare') || html.length < 6000)) {
    return { type: 'cloudflare_block', verifyUrl: url };
  }
  // Generic CAPTCHA detection
  if (/captcha|recaptcha|hcaptcha|verify.you.are.human/i.test(html.slice(0, 5000))) {
    return { type: 'captcha', verifyUrl: url };
  }
  // DDoS-Guard / similar WAF
  if (html.includes('DDoS-Guard') || html.includes('ddos-guard')) {
    return { type: 'ddos_guard', verifyUrl: url };
  }
  return undefined;
}

// In-memory cookie store shared with /api/verify route
const cookieStore: Map<string, { cookies: string; html?: string; url?: string; ts: number }> =
  (globalThis as any).__cookieStore ??= new Map();
const COOKIE_TTL = 30 * 60 * 1000; // 30 minutes

function getStoredCookies(origin: string): string {
  const entry = cookieStore.get(origin);
  if (!entry) return '';
  if (Date.now() - entry.ts > COOKIE_TTL) { cookieStore.delete(origin); return ''; }
  return entry.cookies;
}

async function fetchPage(url: string, extraCookies?: string): Promise<FetchResult> {
  try {
    const origin = new URL(url).origin;
    const storedCookies = getStoredCookies(origin);
    const allCookies = [storedCookies, extraCookies].filter(Boolean).join('; ');
    const headers: Record<string, string> = { ...FETCH_HEADERS };
    if (allCookies) headers['Cookie'] = allCookies;
    const opts: any = { headers, redirect: 'follow', signal: AbortSignal.timeout(10_000) };
    const resp = await pfetch(url, opts);
    const html = await resp.text();

    // Detect challenge
    const challenge = detectChallenge(resp.status, html, url);
    if (challenge) {
      console.log(`[Challenge] ${url} → ${challenge.type}`);
      return { html: null, challenge };
    }

    if (!resp.ok) return { html: null };

    // Store any new cookies from successful response
    const newCookies = extractCookies(resp);
    if (newCookies) {
      const merged = mergeCookies(storedCookies, newCookies);
      cookieStore.set(origin, { cookies: merged, ts: Date.now() });
    }

    return { html };
  } catch {
    return { html: null };
  }
}

async function fetchWithCsrfPost(
  origin: string,
  query: string,
): Promise<string | null> {
  try {
    // Step 1: GET homepage to obtain CSRF token + session cookie
    const homeResp = await pfetch(origin, { headers: FETCH_HEADERS, redirect: 'follow' });
    if (!homeResp.ok) return null;
    const homeHtml = await homeResp.text();
    const cookies = homeResp.headers.get('set-cookie') || '';

    const csrfMatch = homeHtml.match(/name=["']csrf_token["']\s+value=["']([^"']+)["']/);
    const csrfToken = csrfMatch ? csrfMatch[1] : '';

    // Step 2: POST search with CSRF token and session cookie
    const body = new URLSearchParams({ csrf_token: csrfToken, search: query });
    const resp = await pfetch(`${origin}/search`, {
      method: 'POST',
      headers: {
        ...FETCH_HEADERS,
        'Content-Type': 'application/x-www-form-urlencoded',
        ...(cookies ? { Cookie: cookies.split(',').map(c => c.split(';')[0]).join('; ') } : {}),
      },
      body: body.toString(),
      redirect: 'follow',
    });
    if (!resp.ok) return null;
    return await resp.text();
  } catch {
    return null;
  }
}

interface ResultItem {
  title: string;
  magnet: string;
  size: string;
  date: string;
  seeders: number;
  leechers: number;
  source: string;
  site_name: string;
  score: number;
}

function cleanTitle(raw: string): string {
  return raw
    .replace(/^Details\s+for\s+/i, '')
    .replace(/^Download\s+/i, '')
    .replace(/\s*Torrent\s*$/i, '')
    .replace(/\s*[-\u2013|:]+\s*(The\s*Pirate\s*Bay|TPB|1337x\.?\w*|torrent\w*|RARBG|EZTV|YTS|YIFY|Kickass|LimeTorrents|TorrentGalaxy).*$/i, '')
    .trim() || raw;
}

/** Strip time portion from date strings, keep only the date part. */
function cleanDate(raw: string): string {
  if (!raw) return '';
  // Already YYYY-MM-DD or DD/MM/YYYY — strip any trailing time
  const d1 = raw.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
  if (d1) return d1[1].replace(/\//g, '-');
  const d2 = raw.match(/(\d{1,2}[-/]\d{1,2}[-/]\d{4})/);
  if (d2) return d2[1].replace(/\//g, '-');
  // "Jan 15, 2024" or "15 Jan 2024"
  const d3 = raw.match(/((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})/i);
  if (d3) return d3[1];
  const d4 = raw.match(/(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})/i);
  if (d4) return d4[1];
  return raw.trim();
}

function extractTitleFromMagnet(magnet: string): string {
  try {
    const m = magnet.match(/[?&]dn=([^&]+)/);
    if (m) return decodeURIComponent(m[1].replace(/\+/g, ' ')).trim();
  } catch {}
  return '';
}

function extractFromSearchPage(
  $: cheerio.CheerioAPI,
  selectors: any,
  origin: string,
  siteName: string,
  score: number,
): { results: ResultItem[]; detailUrls: string[]; titleHints: string[]; sizeHints: string[]; dateHints: string[] } {
  const results: ResultItem[] = [];
  const detailUrls: string[] = [];
  const titleHints: string[] = [];
  const sizeHints: string[] = [];
  const dateHints: string[] = [];
  const items = $(selectors.list_item);

  items.each((_, el) => {
    const item = $(el);

    let magnet = '';
    if (selectors.magnet) {
      magnet = item.find(selectors.magnet).first().attr('href') || '';
    }
    if (!magnet) {
      magnet = item.find('a[href^="magnet:"]').first().attr('href') || '';
    }

    let title = '';
    if (selectors.title) {
      const titleEl = item.find(selectors.title).first();
      title = titleEl.attr('title') || titleEl.text().trim();
    }
    if (!title || title.length < 3) {
      const titleLink = item.find('a[title]').first();
      if (titleLink.length) title = titleLink.attr('title') || titleLink.text().trim();
    }
    if (!title || title.length < 3) {
      title = extractTitleFromMagnet(magnet);
    }

    let size = '';
    if (selectors.size) {
      size = item.find(selectors.size).first().text().trim();
    }
    if (!size && magnet) {
      const sizeMatch = item.text().match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
      if (sizeMatch) {
        // Normalize: GiB → GB etc.
        size = sizeMatch[0].replace(/iB\b/i, 'B');
      }
    }

    let date = '';
    if (selectors.date) {
      date = item.find(selectors.date).first().text().trim();
    }
    if (!date) {
      const txt = item.text();
      const dateMatch =
        txt.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/) ||
        txt.match(/(\d{1,2}[-/]\d{1,2}[-/]\d{4})/) ||
        txt.match(/((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})/i) ||
        txt.match(/(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})/i);
      if (dateMatch) date = dateMatch[1];
    }

    // Seeders / Leechers extraction
    let seeders = -1;
    let leechers = -1;
    const itemText = item.text();
    if (selectors.seeders) {
      const v = parseInt(item.find(selectors.seeders).first().text().trim(), 10);
      if (!isNaN(v)) seeders = v;
    }
    if (selectors.leechers) {
      const v = parseInt(item.find(selectors.leechers).first().text().trim(), 10);
      if (!isNaN(v)) leechers = v;
    }
    // Regex fallback for labeled formats (e.g. "Seeders: 10 Leechers: 3")
    if (seeders < 0) {
      const m = itemText.match(/seed(?:er)?s?[:\s]+(\d+)/i);
      if (m) seeders = parseInt(m[1], 10);
    }
    if (leechers < 0) {
      const m = itemText.match(/leech(?:er)?s?[:\s]+(\d+)/i);
      if (m) leechers = parseInt(m[1], 10);
    }
    // Table-row heuristic: last two numeric-only TDs → seeders/leechers
    // Works for TPB, magnetdl, rutor, knaben and similar table-based sites
    if (seeders < 0 && leechers < 0 && el.tagName === 'tr') {
      const tds = item.find('td');
      const numericTails: number[] = [];
      for (let i = tds.length - 1; i >= 0 && numericTails.length < 2; i--) {
        const txt = $(tds[i]).text().trim();
        if (/^\d+$/.test(txt)) numericTails.unshift(parseInt(txt, 10));
        else break;
      }
      if (numericTails.length === 2) {
        seeders = numericTails[0];
        leechers = numericTails[1];
      }
    }

    if (magnet && magnet.startsWith('magnet:?')) {
      results.push({
        title: cleanTitle(title || 'Unknown Title'),
        magnet,
        size: size || '',
        date: cleanDate(date),
        seeders: seeders >= 0 ? seeders : 0,
        leechers: leechers >= 0 ? leechers : 0,
        source: origin,
        site_name: siteName,
        score,
      });
    }

    if (selectors.detail_link) {
      const detailHref = item.find(selectors.detail_link).first().attr('href');
      if (detailHref) {
        const detailUrl = detailHref.startsWith('http')
          ? detailHref
          : new URL(detailHref, origin).href;
        detailUrls.push(detailUrl);
        titleHints.push(title || '');
        sizeHints.push(size || '');
        dateHints.push(date || '');
      }
    }

    if (!selectors.detail_link && !magnet) {
      const anyLink = item.find('a[href]').first().attr('href');
      if (anyLink && !anyLink.startsWith('magnet:') && !anyLink.startsWith('#') && !anyLink.startsWith('javascript:')) {
        const detailUrl = anyLink.startsWith('http')
          ? anyLink
          : new URL(anyLink, origin).href;
        detailUrls.push(detailUrl);
        titleHints.push(title || '');
        sizeHints.push(size || '');
        dateHints.push(date || '');
      }
    }
  });

  return { results, detailUrls, titleHints, sizeHints, dateHints };
}

async function fetchDetailResults(
  detailUrls: string[],
  detailSelectors: any,
  origin: string,
  siteName: string,
  score: number,
  limit: number,
  titleHints: string[] = [],
  sizeHints: string[] = [],
  dateHints: string[] = [],
  searchQuery: string = '',
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  const seen = new Set<string>();
  const urlsToFetch = detailUrls.slice(0, Math.min(detailUrls.length, 8));

  const overallTimeout = AbortSignal.timeout(15_000);
  const fetches = urlsToFetch.map(async (url, urlIdx) => {
    if (overallTimeout.aborted) return [];
    const { html } = await fetchPage(url);
    if (!html) return [];

    const $ = cheerio.load(html);
    const items: ResultItem[] = [];
    const hint = titleHints[urlIdx] || '';
    const sizeHint = sizeHints[urlIdx] || '';
    const dateHint = dateHints[urlIdx] || '';

    // Site-name guard helpers (reused per page)
    const _norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    const _sln = _norm(siteName);
    const KNOWN_SITE_NAMES = ['1337x','1377x','nyaa','piratebay','tpb','rarbg','yts','eztv','kickass','limetorrents','torrentgalaxy','magnetdl','rutor','bitsearch','knaben','0magnet','0cili','btdig','javbus','sukebei','tokyotosho','animetosho','fitgirl','clb','btsow','u3c3'];
    const _looksLikeSite = (t: string) => {
      if (!t || t.length < 3) return true;
      const n = _norm(t);
      if (n === _sln || n.includes(_sln) || _sln.includes(n) || (n.length < 12 && _sln.startsWith(n))) return true;
      if (n.length < 20 && KNOWN_SITE_NAMES.some(sn => n === sn || n === sn + 'to' || n === sn + 'com' || n === sn + 'org')) return true;
      return false;
    };

    const magnetLinks = $(detailSelectors.magnet || 'a[href^="magnet:"]');
    magnetLinks.each((_, el) => {
      const magnet = $(el).attr('href') || '';
      if (!magnet.startsWith('magnet:?') || seen.has(magnet)) return;
      seen.add(magnet);

      let title = '';
      // 1) Use configured selector
      if (detailSelectors.title) {
        const candidate = $(detailSelectors.title).first().text().trim();
        if (candidate && !_looksLikeSite(candidate)) title = candidate;
      }
      // 2) Try specific selectors (handles 1337x .box-info-heading h1 etc.)
      if (!title) {
        const candidates = [
          $('.box-info-heading h1').first().text().trim(),
          $('h1.title').first().text().trim(),
          $('h1').eq(1).text().trim(),
          $('h1').first().text().trim(),
          cleanTitle($('title').first().text().trim()),
        ];
        for (const c of candidates) {
          if (c && c.length >= 3 && !_looksLikeSite(c)) { title = c; break; }
        }
      }
      // 3) If title is short and doesn't contain any search keyword, discard it
      if (title && title.length < 30 && searchQuery) {
        const kws = searchQuery.toLowerCase().split(/[\s_\-+]+/).filter(w => w.length >= 2);
        const tl = title.toLowerCase();
        const hasKeyword = kws.length === 0 || kws.some(kw => tl.includes(kw));
        if (!hasKeyword) title = '';
      }
      // 4) Use search-page hint
      if (!title && hint) title = hint;
      // 5) Extract from magnet dn= param
      if (!title || title.length < 3) title = extractTitleFromMagnet(magnet);

      // Lazy body text for regex fallbacks
      let _bodyText: string | null = null;
      const getBodyText = () => _bodyText ??= $('body').text();

      let size = '';
      if (detailSelectors.size) {
        size = $(detailSelectors.size).first().text().trim();
      }
      if (!size) {
        const sizeMatch = getBodyText().match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
        if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');
      }

      let date = '';
      if (detailSelectors.date) {
        date = $(detailSelectors.date).first().text().trim();
      }
      if (!date) {
        const dateMatch = getBodyText().match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
        if (dateMatch) date = dateMatch[1];
      }

      // Seeders / Leechers from detail page
      let seeders = -1;
      let leechers = -1;
      if (detailSelectors.seeders) {
        const v = parseInt($(detailSelectors.seeders).first().text().trim(), 10);
        if (!isNaN(v)) seeders = v;
      }
      if (detailSelectors.leechers) {
        const v = parseInt($(detailSelectors.leechers).first().text().trim(), 10);
        if (!isNaN(v)) leechers = v;
      }
      if (seeders < 0) {
        const m = getBodyText().match(/seed(?:er)?s?[:\s]+(\d+)/i);
        if (m) seeders = parseInt(m[1], 10);
      }
      if (leechers < 0) {
        const m = getBodyText().match(/leech(?:er)?s?[:\s]+(\d+)/i);
        if (m) leechers = parseInt(m[1], 10);
      }

      title = cleanTitle(title || 'Unknown Title');

      items.push({
        title,
        magnet,
        size: size || sizeHint || '',
        date: cleanDate(date || dateHint),
        seeders: seeders >= 0 ? seeders : 0,
        leechers: leechers >= 0 ? leechers : 0,
        source: origin,
        site_name: siteName,
        score,
      });
    });

    return items;
  });

  const allItems = await Promise.all(fetches);
  for (const items of allItems) {
    results.push(...items);
    if (results.length >= limit) break;
  }

  return results.slice(0, limit);
}

/* ---- JavBus special handler ---- */
async function fetchJavBus(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  // Step 1: GET homepage → redirects to age-verify page
  const r0 = await pfetch(origin, { headers: FETCH_HEADERS, redirect: 'follow' });
  const cookies0 = extractCookies(r0);
  // Step 2: POST age verification
  const verifyUrl = r0.url; // age verify page URL
  const r1 = await pfetch(verifyUrl, {
    method: 'POST',
    headers: {
      ...FETCH_HEADERS,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Referer': verifyUrl,
      'Origin': origin,
      Cookie: cookies0,
    },
    body: 'Submit=%E7%A2%BA%E8%AA%8D', // 確認
    redirect: 'follow',
  });
  const sessionCookies = mergeCookies(cookies0, extractCookies(r1));

  // Step 3: Search
  const searchUrl = `${origin}/search/${encodeURIComponent(query)}`;
  const r2 = await pfetch(searchUrl, {
    headers: { ...FETCH_HEADERS, Cookie: sessionCookies },
    redirect: 'follow',
  });
  if (!r2.ok) return [];
  const searchHtml = await r2.text();
  const $ = cheerio.load(searchHtml);
  const detailUrls: string[] = [];
  $('a.movie-box').each((_, el) => {
    const href = $(el).attr('href');
    if (href) detailUrls.push(href.startsWith('http') ? href : `${origin}${href}`);
  });
  if (detailUrls.length === 0) return [];

  // Step 4: Fetch detail pages → extract gid/uc → AJAX magnets
  const results: ResultItem[] = [];
  const seen = new Set<string>();
  const pagesToFetch = detailUrls.slice(0, 6);

  const detailFetches = pagesToFetch.map(async (dUrl) => {
    try {
      const dr = await pfetch(dUrl, {
        headers: { ...FETCH_HEADERS, Cookie: sessionCookies },
        redirect: 'follow',
      });
      if (!dr.ok) return;
      const dHtml = await dr.text();

      const d$ = cheerio.load(dHtml);
      const pageTitle = d$('h3').first().text().trim() || d$('title').first().text().trim();

      // Extract gid, uc for AJAX
      const gidM = dHtml.match(/var\s+gid\s*=\s*(\d+)/);
      const ucM = dHtml.match(/var\s+uc\s*=\s*(\d+)/);
      if (!gidM) return;
      const gid = gidM[1];
      const uc = ucM ? ucM[1] : '0';

      const ajaxUrl = `${origin}/ajax/uncledatoolsbyajax.php?gid=${gid}&lang=zh&uc=${uc}&floor=${Math.floor(Math.random() * 1000 + 1)}`;
      const ar = await pfetch(ajaxUrl, {
        headers: { ...FETCH_HEADERS, Referer: dUrl, Cookie: sessionCookies },
      });
      if (!ar.ok) return;
      const aHtml = await ar.text();
      const a$ = cheerio.load(aHtml);

      a$('a[href^="magnet:"]').each((_, mel) => {
        const magnet = a$(mel).attr('href') || '';
        if (!magnet.startsWith('magnet:?') || seen.has(magnet)) return;
        seen.add(magnet);
        let size = '';
        const tr = a$(mel).closest('tr');
        if (tr.length) {
          const cells = tr.find('td');
          if (cells.length >= 2) size = cells.eq(1).text().trim();
        }
        results.push({
          title: pageTitle || extractTitleFromMagnet(magnet) || 'Unknown Title',
          magnet,
          size,
          date: '',
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      });
    } catch {}
  });

  await Promise.all(detailFetches);
  return results;
}

/* ---- 6v520.com handler (POST search, gb2312 encoding, detail-following) ---- */
async function fetch6v520(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
  const seen = new Set<string>();

  // Encode query as gb2312 percent-encoded (帝国CMS requires gb2312)
  const gb2312Buf = iconv.encode(query, 'gb2312');
  const kw = Array.from(gb2312Buf).map(b => '%' + b.toString(16).toUpperCase().padStart(2, '0')).join('');
  const body = `show=title,smalltext&tempid=1&keyboard=${kw}&tbname=article`;

  const searchResp = await pfetch(`${origin}/e/search/index.php`, {
    method: 'POST',
    headers: {
      ...FETCH_HEADERS,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Referer': `${origin}/`,
    },
    body,
    redirect: 'follow',
  });

  if (!searchResp.ok) return results;
  const buf = Buffer.from(await searchResp.arrayBuffer());
  // Detect charset and decode
  let html: string;
  try {
    const decoder = new TextDecoder('gb2312');
    html = decoder.decode(buf);
  } catch {
    html = buf.toString('utf-8');
  }

  // Extract detail page links, filtering out announcement/ranking pages
  const $ = cheerio.load(html);
  const detailUrls: string[] = [];
  const skipRe = /公告|榜单|排行|帮助|教程|佳片推荐|新手必看/;
  $('a[href]').each((_, el) => {
    const href = $(el).attr('href') || '';
    const text = $(el).text().trim();
    if (/\/(dy|dlz|zydy|gq)\/\d{4}/.test(href)) {
      if (text && skipRe.test(text)) return; // skip announcements
      const full = href.startsWith('http') ? href : `${origin}/${href.replace(/^\//, '')}`;
      if (!detailUrls.includes(full)) detailUrls.push(full);
    }
  });

  console.log(`[6v520] Found ${detailUrls.length} detail links for "${query}"`);

  // Follow detail pages (limit to 12)
  const pages = detailUrls.slice(0, 12);
  const fetches = pages.map(async (dUrl) => {
    try {
      const dr = await pfetch(dUrl, {
        headers: FETCH_HEADERS,
        redirect: 'follow',
      });
      if (!dr.ok) return;
      const dBuf = Buffer.from(await dr.arrayBuffer());
      let dHtml: string;
      try {
        dHtml = new TextDecoder('gb2312').decode(dBuf);
      } catch {
        dHtml = dBuf.toString('utf-8');
      }

      const d$ = cheerio.load(dHtml);
      const title = d$('title').first().text().replace(/[,，].*$/, '').replace(/免费下载.*$/, '').trim();

      d$('a[href^="magnet:"]').each((_, mel) => {
        const magnet = d$(mel).attr('href')?.replace(/&amp;/g, '&') || '';
        if (!magnet.startsWith('magnet:?') || seen.has(magnet)) return;
        seen.add(magnet);

        // Extract size and date from body text
        const bodyText = d$('body').text();
        let size = '';
        const sizeMatch = bodyText.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
        if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');

        let date = '';
        const dateMatch = bodyText.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
        if (dateMatch) date = dateMatch[1];

        results.push({
          title: title || extractTitleFromMagnet(magnet) || 'Unknown Title',
          magnet,
          size,
          date,
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      });
    } catch {}
  });

  await Promise.all(fetches);
  } catch (e: any) {
    console.error(`[6v520] Error: ${e.message}`);
  }
  return results;
}

/* ---- meijumi.net handler (GET search + math captcha solving) ---- */
async function fetchMeijumi(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
  const seen = new Set<string>();

  // Step 1: GET search page → captcha page, answer is in 'result' cookie
  const searchUrl = `${origin}/?s=${encodeURIComponent(query)}`;
  const resp1 = await pfetch(searchUrl, {
    headers: FETCH_HEADERS,
    redirect: 'manual',
  });

  const sc1 = resp1.headers.get('set-cookie') || '';
  const answerMatch = sc1.match(/result=(\d+)/);
  await resp1.text(); // drain body

  if (!answerMatch) {
    console.log(`[Meijumi] No captcha cookie found`);
    return results;
  }
  const answer = answerMatch[1];
  console.log(`[Meijumi] Captcha answer from cookie: ${answer}`);

  // Step 2: POST answer → get esc_search_captcha=1 cookie
  const resp2 = await pfetch(searchUrl, {
    method: 'POST',
    headers: {
      ...FETCH_HEADERS,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Cookie': `result=${answer}`,
      'Referer': searchUrl,
    },
    body: `result=${answer}`,
    redirect: 'manual',
  });
  await resp2.text(); // drain body (contains location.reload())

  // Step 3: GET again with captcha-passed cookie → real results
  const resp3 = await pfetch(searchUrl, {
    headers: {
      ...FETCH_HEADERS,
      'Cookie': `result=${answer}; esc_search_captcha=1`,
    },
    redirect: 'follow',
  });

  if (!resp3.ok) return results;
  const searchHtml = await resp3.text();
  const $ = cheerio.load(searchHtml);
  const allCookies = `result=${answer}; esc_search_captcha=1`;
  const detailUrls: string[] = [];

  $('a[href]').each((_, el) => {
    const href = $(el).attr('href') || '';
    if (/meijumi\.net\/\d+\.html/.test(href) && !detailUrls.includes(href)) {
      detailUrls.push(href);
    }
  });

  console.log(`[Meijumi] Found ${detailUrls.length} detail links for "${query}"`);

  // Step 4: Follow detail pages (limit to 8)
  const pages = detailUrls.slice(0, 8);
  const fetches = pages.map(async (dUrl) => {
    try {
      const dr = await pfetch(dUrl, {
        headers: { ...FETCH_HEADERS, Cookie: allCookies },
        redirect: 'follow',
      });
      if (!dr.ok) return;
      const dHtml = await dr.text();
      const d$ = cheerio.load(dHtml);

      const title = d$('h1.entry-title, h1.article-title, h1').first().text().trim()
        || d$('title').first().text().replace(/-.*$/, '').trim();

      d$('a[href^="magnet:"]').each((_, mel) => {
        const magnet = d$(mel).attr('href')?.replace(/&amp;/g, '&') || '';
        if (!magnet.startsWith('magnet:?') || seen.has(magnet)) return;
        seen.add(magnet);

        const bodyText = d$('body').text();
        let size = '';
        const sizeMatch = bodyText.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
        if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');

        let date = '';
        const dateMatch = bodyText.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
        if (dateMatch) date = dateMatch[1];

        results.push({
          title: title || extractTitleFromMagnet(magnet) || 'Unknown Title',
          magnet,
          size,
          date,
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      });
    } catch {}
  });

  await Promise.all(fetches);
  } catch (e: any) {
    console.error(`[Meijumi] Error: ${e.message}`);
  }
  return results;
}

/* ---- yhg007.com (移花宫) handler: CSRF POST search, magnets on search page ---- */
async function fetchYhg(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {

  // Step 1: GET homepage to extract CSRF token
  const homeResp = await pfetch(origin + '/', {
    headers: FETCH_HEADERS,
  });
  if (!homeResp.ok) return results;
  const homeHtml = await homeResp.text();
  const cookies = extractCookies(homeResp);
  const csrfMatch = homeHtml.match(/csrf_token[^>]*value="([^"]+)"/);
  if (!csrfMatch) {
    console.log(`[YHG] No CSRF token found`);
    return results;
  }

  // Step 2: POST search
  const body = new URLSearchParams({ csrf_token: csrfMatch[1], search: query });
  const searchResp = await pfetch(origin + '/search', {
    method: 'POST',
    headers: {
      ...FETCH_HEADERS,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Cookie': cookies,
      'Referer': origin + '/',
    },
    body: body.toString(),
    redirect: 'follow',
  });

  if (!searchResp.ok) return results;
  const html = await searchResp.text();
  const $ = cheerio.load(html);

  // Step 3: Parse results — each .ssbox is a result item
  const seen = new Set<string>();
  $('.ssbox').each((_, el) => {
    const item = $(el);
    const title = item.find('.title h3 a').first().text().trim();
    const magnetLink = item.find('.sbar a[href^="magnet:"]').first().attr('href') || '';
    if (!magnetLink || !title || seen.has(magnetLink)) return;
    seen.add(magnetLink);

    const sbar = item.find('.sbar').text();
    let size = '';
    const sizeMatch = sbar.match(/大小[：:]\s*([\d.]+\s*[TGMK]i?B)/i);
    if (sizeMatch) size = sizeMatch[1];
    // Also try from cpill
    if (!size) {
      const pill = item.find('.cpill').text().trim();
      if (/([\d.]+)\s*(TB|GB|MB|KB)/i.test(pill)) size = pill;
    }

    let date = '';
    const dateMatch = sbar.match(/添加时间[：:]\s*(\d{4}-\d{2}-\d{2})/);
    if (dateMatch) date = dateMatch[1];

    results.push({
      title,
      magnet: magnetLink,
      size,
      date,
      seeders: 0,
      leechers: 0,
      source: origin,
      site_name: siteName,
      score,
    });
  });

  console.log(`[YHG] Found ${results.length} results for "${query}"`);
  } catch (e: any) {
    console.error(`[YHG] Error: ${e.message}`);
  }
  return results;
}

/* ---- zhongzidi.com (种子帝) handler: GET search, magnets on search page ---- */
async function fetchZhongzidi(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {

  const searchUrl = `${origin}/list/${encodeURIComponent(query)}/1`;
  const resp = await pfetch(searchUrl, {
    headers: FETCH_HEADERS,
    redirect: 'follow',
  });

  if (!resp.ok) return results;
  const html = await resp.text();
  const $ = cheerio.load(html);
  const seen = new Set<string>();

  // Each result is in ul.list-group > li items
  $('ul.list-group').each((_, ul) => {
    const group = $(ul);
    const titleEl = group.find('a.text-success').first();
    const title = titleEl.text().trim();
    if (!title) return;

    // Extract magnet from both commented and uncommented links
    const groupHtml = group.html() || '';
    const magnetMatch = groupHtml.match(/magnet:\?xt=urn:btih:([a-fA-F0-9]+)/i);
    if (!magnetMatch) return;

    const magnet = `magnet:?xt=urn:btih:${magnetMatch[1]}`;
    if (seen.has(magnet)) return;
    seen.add(magnet);

    let date = '';
    const dateEl = group.find('.text-time').first().text().trim();
    if (dateEl) date = dateEl;

    let size = '';
    const sizeEl = group.find('.text-filesize').first().text().trim();
    if (sizeEl) size = sizeEl;
    if (!size) {
      const sizeMatch = groupHtml.match(/([\d.]+)\s*(TB|GB|MB|KB)\b/i);
      if (sizeMatch) size = sizeMatch[0];
    }

    results.push({
      title,
      magnet,
      size,
      date,
      seeders: 0,
      leechers: 0,
      source: origin,
      site_name: siteName,
      score,
    });
  });

  console.log(`[Zhongzidi] Found ${results.length} results for "${query}"`);
  } catch (e: any) {
    console.error(`[Zhongzidi] Error: ${e.message}`);
  }
  return results;
}

/* ---- RARBG (rarbggo.to) handler: detail-following ---- */
async function fetchRarbggo(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchUrl = `${origin}/search/?search=${encodeURIComponent(query)}`;
    const resp = await pfetch(searchUrl, { headers: FETCH_HEADERS, redirect: 'follow' });
    if (!resp.ok) return results;
    const html = await resp.text();
    const $ = cheerio.load(html);

    // Collect detail page links from search results
    const detailUrls: string[] = [];
    $('a[href*="/torrent/"]').each((_, el) => {
      const href = $(el).attr('href') || '';
      if (href.includes('/torrent/') && href.endsWith('.html')) {
        const full = href.startsWith('http') ? href : `${origin}${href}`;
        if (!detailUrls.includes(full)) detailUrls.push(full);
      }
    });
    console.log(`[RARBG] Found ${detailUrls.length} detail links for "${query}"`);

    // Extract size from search page rows (td elements near each link)
    const sizeMap = new Map<string, string>();
    $('tr').each((_, row) => {
      const link = $(row).find('a[href*="/torrent/"]').attr('href') || '';
      const cells = $(row).find('td');
      cells.each((__, cell) => {
        const t = $(cell).text().trim();
        if (/^\d+\.?\d*\s*(GB|MB|TB|KB)/i.test(t) && link) {
          sizeMap.set(link, t);
        }
      });
    });

    // Follow detail pages (limit 10, parallel)
    const seen = new Set<string>();
    const pages = detailUrls.slice(0, 10);
    const fetches = pages.map(async (dUrl) => {
      try {
        const dr = await pfetch(dUrl, { headers: FETCH_HEADERS, redirect: 'follow' });
        if (!dr.ok) return;
        const dHtml = await dr.text();
        const d$ = cheerio.load(dHtml);
        const title = d$('h1').first().text().trim() ||
                      d$('title').first().text().replace(/\s*[-|].*$/, '').trim();
        d$('a[href^="magnet:"]').each((_, el) => {
          const mag = d$(el).attr('href') || '';
          const hash = mag.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase();
          if (hash && !seen.has(hash)) {
            seen.add(hash);
            // Try to get size from search page or detail page
            const relPath = dUrl.replace(origin, '');
            const size = sizeMap.get(relPath) || '';
            results.push({
              title: title || 'Unknown Title',
              magnet: mag,
              size,
              date: '',
              seeders: 0,
              leechers: 0,
              source: dUrl,
              site_name: siteName,
              score,
            });
          }
        });
      } catch {}
    });
    await Promise.all(fetches);
  } catch (e: any) {
    console.error(`[RARBG] Error: ${e.message}`);
  }
  console.log(`[RARBG] Found ${results.length} results for "${query}"`);
  return results;
}

/* ---- RRJAV handler: search page has magnets directly ---- */
async function fetchRrjav(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchUrl = `${origin}/?s=${encodeURIComponent(query)}`;
    const resp = await pfetch(searchUrl, { headers: FETCH_HEADERS, redirect: 'follow' });
    if (!resp.ok) return results;
    const html = await resp.text();
    const $ = cheerio.load(html);

    const seen = new Set<string>();
    // Each torrent entry is in an <article> or similar container
    $('a[href^="magnet:"]').each((_, el) => {
      const mag = $(el).attr('href') || '';
      const hash = mag.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase();
      if (!hash || seen.has(hash)) return;
      seen.add(hash);

      // Walk up to find title and size
      const container = $(el).closest('article, .torrent-item, tr, li, div.entry, div.post');
      let title = '';
      if (container.length) {
        title = container.find('h2, h3, h4, .entry-title, a[title]').first().text().trim();
      }
      if (!title) title = extractTitleFromMagnet(mag);

      // Size: look for GB/MB pattern near the magnet
      let size = '';
      const nearby = container.length ? container.text() : $(el).parent().text();
      const sizeMatch = nearby.match(/([\d.]+)\s*(GB|MB|TB)/i);
      if (sizeMatch) size = sizeMatch[0];

      // Date
      let date = '';
      const dateMatch = nearby.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
      if (dateMatch) date = dateMatch[1];

      results.push({
        title: title || 'Unknown Title',
        magnet: mag,
        size,
        date,
        seeders: 0,
        leechers: 0,
        source: searchUrl,
        site_name: siteName,
        score,
      });
    });
  } catch (e: any) {
    console.error(`[RRJAV] Error: ${e.message}`);
  }
  console.log(`[RRJAV] Found ${results.length} results for "${query}"`);
  return results;
}

function extractCookies(resp: Response): string {
  const raw = resp.headers.get('set-cookie') || '';
  return raw.split(',').map(c => c.split(';')[0].trim()).filter(Boolean).join('; ');
}

function mergeCookies(a: string, b: string): string {
  const map = new Map<string, string>();
  for (const s of [a, b]) {
    for (const pair of s.split(';').map(p => p.trim()).filter(Boolean)) {
      const eq = pair.indexOf('=');
      if (eq > 0) map.set(pair.substring(0, eq), pair.substring(eq + 1));
    }
  }
  return [...map.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
}

export async function POST(req: NextRequest) {
  try {
    const { rule, query } = await req.json();

    if (!rule || !query) {
      return NextResponse.json({ error: 'Missing rule or query' }, { status: 400 });
    }

    const origin = rule.site.origin.replace(/\/$/, '');
    const template = rule.search.request_template;
    const queryB64 = Buffer.from(query, 'utf-8').toString('base64');
    const searchUrl = origin + template
      .replace('{query}', encodeURIComponent(query))
      .replace('{query_b64}', queryB64);
    const selectors = rule.search.parse_metadata.selectors;
    const supportsDetail = rule.capabilities?.supports_detail ?? false;
    const detailSelectors = rule.search.detail?.selectors ? { ...rule.search.detail.selectors } : undefined;
    // Server-side override: 1337x family uses h1 for site logo; real title is in .box-info-heading h1
    if (/1337x|1377x/i.test(origin) && detailSelectors) {
      detailSelectors.title = '.box-info-heading h1';
    }
    const siteName = rule.site.name;
    const score = rule.quality?.score ?? 50;

    const requiresCsrf = rule.search.requires_csrf === true;
    const handler = rule.search.handler || '';
    const requiresBrowser = rule.search.requires_browser === true;

    console.log(`[Proxy] Fetching: ${searchUrl} (csrf=${requiresCsrf}, handler=${handler || 'default'})`);

    // Custom handler dispatch
    if (handler === 'javbus') {
      const jbResults = await fetchJavBus(origin, query, siteName, score);
      return NextResponse.json({ results: jbResults.slice(0, 30) });
    }
    if (handler === '6v520') {
      const r = await fetch6v520(origin, query, siteName, score);
      return NextResponse.json({ results: r.slice(0, 30) });
    }
    if (handler === 'meijumi') {
      const r = await fetchMeijumi(origin, query, siteName, score);
      return NextResponse.json({ results: r.slice(0, 30) });
    }
    if (handler === 'yhg') {
      const r = await fetchYhg(origin, query, siteName, score);
      return NextResponse.json({ results: r.slice(0, 30) });
    }
    if (handler === 'zhongzidi') {
      const r = await fetchZhongzidi(origin, query, siteName, score);
      return NextResponse.json({ results: r.slice(0, 30) });
    }
    if (handler === 'rarbggo') {
      const r = await fetchRarbggo(origin, query, siteName, score);
      return NextResponse.json({ results: r.slice(0, 30) });
    }
    if (handler === 'rrjav') {
      const r = await fetchRrjav(origin, query, siteName, score);
      return NextResponse.json({ results: r.slice(0, 30) });
    }

    let fetchResult: FetchResult;

    if (requiresBrowser) {
      // SPA source — go straight to browser engine (like Legado's BackstageWebView)
      console.log(`[BrowserEngine] Direct browser fetch for ${siteName}: ${searchUrl}`);
      const br = await browserFetch(searchUrl, {
        waitForSelector: selectors.list_item,
      });
      fetchResult = br.challenge
        ? { html: null, challenge: br.challenge }
        : { html: br.html };
    } else if (requiresCsrf) {
      fetchResult = { html: await fetchWithCsrfPost(origin, query) } as FetchResult;
    } else {
      fetchResult = await fetchPage(searchUrl);
    }

    // Challenge detected — transparent 3-tier fallback
    if (fetchResult.challenge) {
      if (!requiresBrowser) {
        // Tier 1: Playwright headless + CDP (auto-solves JS challenges)
        console.log(`[Tier1] Challenge on ${siteName}, trying headless browser...`);
        const br = await browserFetch(searchUrl, {
          waitForSelector: selectors.list_item,
        });
        if (br.html && !br.challenge) {
          console.log(`[Tier1] Auto-solved challenge for ${siteName}`);
          fetchResult = { html: br.html };
        }
      }
      // Tier 2: If still challenged (or requiresBrowser already tried Tier 1)
      if (fetchResult.challenge) {
        console.log(`[Tier2] Turnstile detected on ${siteName}, launching standalone Chromium...`);
        try {
          const vr = await interactiveVerify(searchUrl, 90_000);
          if (vr.success && vr.html) {
            // Extension returned page HTML — parse it directly
            console.log(`[Tier2] Got ${Math.round(vr.html.length / 1024)}KB HTML from ${siteName}`);
            fetchResult = { html: vr.html };
          } else if (vr.success && vr.cookies) {
            // Got cookies but no HTML — retry fetch with cookies
            console.log(`[Tier2] Got cookies for ${siteName}, retrying fetch...`);
            fetchResult = await fetchPage(searchUrl, vr.cookies);
          } else {
            console.log(`[Tier2] Failed for ${siteName}: ${vr.error}`);
            fetchResult = { html: null };
          }
        } catch (err: any) {
          console.log(`[Tier2] Error for ${siteName}: ${err.message}`);
          fetchResult = { html: null };
        }
      }
    }

    // If still a challenge (shouldn't happen with Tier 2), return empty
    if (fetchResult.challenge) {
      console.log(`[Search] All tiers failed for ${siteName}`);
      fetchResult = { html: null };
    }

    const html = fetchResult.html;
    if (!html) {
      return NextResponse.json({ error: 'Site unreachable', url: searchUrl }, { status: 502 });
    }

    const $ = cheerio.load(html);
    const { results, detailUrls, titleHints, sizeHints, dateHints } = extractFromSearchPage($, selectors, origin, siteName, score);

    // Filter out garbage: titles that are too short, same as site name, or "Unknown"
    const cleaned = results.filter(r => {
      if (!r.title || r.title === 'Unknown Title') return false;
      if (r.title.length < 4) return false;
      const tl = r.title.toLowerCase();
      const sl = siteName.toLowerCase();
      if (tl === sl || tl.includes(' home') && tl.length < 30) return false;
      return true;
    });

    // Follow detail pages for items without magnet (or when search page had no results)
    let detailCleaned: ResultItem[] = [];
    if (supportsDetail && detailSelectors && detailUrls.length > 0 && cleaned.length < 20) {
      const remainingSlots = 20 - cleaned.length;
      const urlsToFollow = detailUrls.filter(url => {
        // Skip detail URLs whose magnets we already have from the search page
        return !cleaned.some(r => url.includes(r.magnet.match(/btih:([a-fA-F0-9]+)/)?.[1] || '__none__'));
      });
      if (urlsToFollow.length > 0) {
        console.log(`[Proxy] Following ${urlsToFollow.length} detail pages for ${siteName}`);
        // Build matching titleHints for the filtered URLs
        const hintMap = detailUrls.map((u, i) => ({ u, t: titleHints[i] || '', s: sizeHints[i] || '', d: dateHints[i] || '' }));
        const filteredTitleHints = urlsToFollow.map(url => hintMap.find(h => h.u === url)?.t || '');
        const filteredSizeHints = urlsToFollow.map(url => hintMap.find(h => h.u === url)?.s || '');
        const filteredDateHints = urlsToFollow.map(url => hintMap.find(h => h.u === url)?.d || '');
        const detailResults = await fetchDetailResults(
          urlsToFollow, detailSelectors, origin, siteName, score, remainingSlots, filteredTitleHints, filteredSizeHints, filteredDateHints, query,
        );
        const siteNorm = siteName.toLowerCase().replace(/[^a-z0-9]/g, '');
        detailCleaned = detailResults.filter(r => {
          if (!r.title || r.title === 'Unknown Title') return false;
          if (r.title.length < 4) return false;
          const tn = r.title.toLowerCase().replace(/[^a-z0-9]/g, '');
          if (tn === siteNorm || siteNorm.includes(tn) || tn.includes(siteNorm) && tn.length < siteNorm.length + 5) return false;
          return true;
        });
      }
    }

    // Merge search page + detail page results, dedup by magnet hash
    const allResults = [...cleaned, ...detailCleaned];
    const seen = new Set<string>();
    const merged = allResults.filter(r => {
      const hash = r.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase() || r.magnet;
      if (seen.has(hash)) return false;
      seen.add(hash);
      return true;
    });

    return NextResponse.json({ results: merged.slice(0, 20) });

  } catch (error: any) {
    console.error(`[Proxy Error] ${error.message}`);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
