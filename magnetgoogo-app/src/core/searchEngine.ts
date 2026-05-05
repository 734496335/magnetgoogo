/**
 * Local Search Engine — runs entirely on user's device.
 *
 * Architecture (same as Legado):
 *   Server → provides sources.json (rules only)
 *   App    → fetches source sites directly via local network
 *          → parses HTML locally with cheerio
 *          → extracts magnet links, titles, metadata
 *
 * No server proxy involved in searching.
 */
import * as cheerio from 'cheerio';
import {
  fetchPage,
  fetchPageManual,
  storeCookiesForOrigin,
  invalidateCookies,
  extractCookies,
  mergeCookies,
  FETCH_HEADERS,
  type FetchResult,
} from './httpClient';
import { VerifyManager } from './VerifyManager';

// ── Types ────────────────────────────────────────────────────────────

export interface ResultItem {
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

export interface SourceRule {
  site: { name: string; origin: string; [k: string]: any };
  capabilities?: { supports_search?: boolean; supports_detail?: boolean };
  search: {
    request_template: string;
    handler?: string;
    requires_csrf?: boolean;
    requires_browser?: boolean;
    parse_metadata: { selectors: any };
    detail?: { selectors: any };
    [k: string]: any;
  };
  quality?: { score?: number; [k: string]: any };
  [k: string]: any;
}

// ── Utility functions ────────────────────────────────────────────────

function normalizeSize(raw: string): string {
  if (!raw) return '';
  return raw.replace(/\bTiB\b/gi, 'TB').replace(/\bGiB\b/gi, 'GB').replace(/\bMiB\b/gi, 'MB').replace(/\bKiB\b/gi, 'KB');
}

function cleanTitle(raw: string): string {
  return (
    raw
      .replace(/^Details\s+for\s+/i, '')
      .replace(/^Download\s+/i, '')
      .replace(/\s*Torrent\s*$/i, '')
      .replace(
        /\s*[-\u2013|:]+\s*(The\s*Pirate\s*Bay|TPB|1337x\.?\w*|torrent\w*|RARBG|EZTV|YTS|YIFY|Kickass|LimeTorrents|TorrentGalaxy).*$/i,
        '',
      )
      .trim() || raw
  );
}

function cleanDate(raw: string): string {
  if (!raw) return '';
  const d1 = raw.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
  if (d1) return d1[1].replace(/\//g, '-');
  const d2 = raw.match(/(\d{1,2}[-/]\d{1,2}[-/]\d{4})/);
  if (d2) return d2[1].replace(/\//g, '-');
  const d3 = raw.match(
    /((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})/i,
  );
  if (d3) return d3[1];
  const d4 = raw.match(
    /(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})/i,
  );
  if (d4) return d4[1];
  return raw.trim();
}

function extractTitleFromMagnet(magnet: string): string {
  try {
    const m = magnet.match(/[?&]dn=([^&]+)/);
    if (m) {
      const decoded = decodeURIComponent(m[1].replace(/\+/g, ' ')).trim();
      // Detect mojibake: if decoded string has common Latin-1→UTF-8 mojibake
      // patterns (e.g. Ã¤, Ã¥, Ã£ for CJK chars), try re-decoding as Shift-JIS
      if (/[\u00c0-\u00ff]{2,}/.test(decoded) && decoded.length > 4) {
        try {
          const iconv = require('iconv-lite');
          const { Buffer } = require('buffer');
          // Encode back to Latin-1 bytes, then decode as Shift-JIS
          const raw = Buffer.from(decoded, 'latin1');
          const sjis = iconv.decode(raw, 'shift_jis');
          // If Shift-JIS produces CJK chars, prefer it
          if (/[\u3000-\u9fff\uff00-\uffef]/.test(sjis)) return sjis;
        } catch {}
      }
      return decoded;
    }
  } catch {}
  return '';
}

// ── Search page parsing ──────────────────────────────────────────────

function extractFromSearchPage(
  $: cheerio.CheerioAPI,
  selectors: any,
  origin: string,
  siteName: string,
  score: number,
): {
  results: ResultItem[];
  detailUrls: string[];
  titleHints: string[];
  sizeHints: string[];
  dateHints: string[];
} {
  const results: ResultItem[] = [];
  const detailUrls: string[] = [];
  const titleHints: string[] = [];
  const sizeHints: string[] = [];
  const dateHints: string[] = [];
  const items = $(selectors.list_item);

  items.each((_: number, el: any) => {
    const item = $(el);

    // Magnet
    let magnet = '';
    if (selectors.magnet) {
      magnet = item.find(selectors.magnet).first().attr('href') || '';
    }
    if (!magnet) {
      magnet = item.find('a[href^="magnet:"]').first().attr('href') || '';
    }

    // Title
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

    // Size
    let size = '';
    if (selectors.size) {
      size = item.find(selectors.size).first().text().trim();
    }
    if (!size && magnet) {
      const sizeMatch = item.text().match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
      if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');
    }

    // Date
    let date = '';
    if (selectors.date) {
      date = item.find(selectors.date).first().text().trim();
    }
    if (!date) {
      const txt = item.text();
      const dateMatch =
        txt.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/) ||
        txt.match(/(\d{1,2}[-/]\d{1,2}[-/]\d{4})/) ||
        txt.match(
          /((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})/i,
        ) ||
        txt.match(
          /(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})/i,
        );
      if (dateMatch) date = dateMatch[1];
    }

    // Seeders / Leechers
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
    if (seeders < 0) {
      const m = itemText.match(/seed(?:er)?s?[:\s]+(\d+)/i);
      if (m) seeders = parseInt(m[1], 10);
    }
    if (leechers < 0) {
      const m = itemText.match(/leech(?:er)?s?[:\s]+(\d+)/i);
      if (m) leechers = parseInt(m[1], 10);
    }
    // Table-row heuristic
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
        size: normalizeSize(size),
        date: cleanDate(date),
        seeders: seeders >= 0 ? seeders : 0,
        leechers: leechers >= 0 ? leechers : 0,
        source: origin,
        site_name: siteName,
        score,
      });
    }

    // Detail link
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
      if (
        anyLink &&
        !anyLink.startsWith('magnet:') &&
        !anyLink.startsWith('#') &&
        !anyLink.startsWith('javascript:')
      ) {
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

// ── Detail page following ────────────────────────────────────────────

const KNOWN_SITE_NAMES = [
  '1337x','1377x','nyaa','piratebay','tpb','rarbg','yts','eztv','kickass',
  'limetorrents','torrentgalaxy','magnetdl','rutor','bitsearch','knaben',
  '0magnet','0cili','btdig','javbus','sukebei','tokyotosho','animetosho',
  'fitgirl','clb','btsow','u3c3',
];

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
  searchQuery = '',
  referer?: string,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  const seen = new Set<string>();
  const urlsToFetch = detailUrls.slice(0, Math.min(detailUrls.length, 8));

  const _norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  const _sln = _norm(siteName);
  const _looksLikeSite = (t: string) => {
    if (!t || t.length < 3) return true;
    const n = _norm(t);
    if (n === _sln || n.includes(_sln) || _sln.includes(n) || (n.length < 12 && _sln.startsWith(n)))
      return true;
    if (
      n.length < 20 &&
      KNOWN_SITE_NAMES.some(
        (sn) => n === sn || n === sn + 'to' || n === sn + 'com' || n === sn + 'org',
      )
    )
      return true;
    return false;
  };

  const fetches = urlsToFetch.map(async (url, urlIdx) => {
    const { html } = await fetchPage(url, undefined, undefined, referer);
    if (!html) return [];

    const $ = cheerio.load(html);
    const items: ResultItem[] = [];
    const hint = titleHints[urlIdx] || '';
    const sizeHint = sizeHints[urlIdx] || '';
    const dateHint = dateHints[urlIdx] || '';

    const magnetLinks = $(detailSelectors.magnet || 'a[href^="magnet:"]');
    // Collect magnets from CSS selector matches
    const foundMagnets: string[] = [];
    magnetLinks.each((_: number, el: any) => {
      const mag = $(el).attr('href') || '';
      if (mag.startsWith('magnet:?')) foundMagnets.push(mag);
    });
    // Fallback: regex extract from full HTML (handles onclick="copyMagnetLink('magnet:...')" etc.)
    if (foundMagnets.length === 0) {
      const htmlStr = $.html();
      const re = /magnet:\?xt=urn:btih:[a-fA-F0-9]{40}/gi;
      let m;
      while ((m = re.exec(htmlStr)) !== null) foundMagnets.push(m[0]);
    }

    for (const magnet of foundMagnets) {
      if (seen.has(magnet)) continue;
      seen.add(magnet);

      let title = '';
      // 1) Configured selector
      if (detailSelectors.title) {
        const candidate = $(detailSelectors.title).first().text().trim();
        if (candidate && !_looksLikeSite(candidate)) title = candidate;
      }
      // 2) Fallback selectors
      if (!title) {
        const candidates = [
          $('.box-info-heading h1').first().text().trim(),
          $('h1.title').first().text().trim(),
          $('h1').eq(1).text().trim(),
          $('h1').first().text().trim(),
          cleanTitle($('title').first().text().trim()),
        ];
        for (const c of candidates) {
          if (c && c.length >= 3 && !_looksLikeSite(c)) {
            title = c;
            break;
          }
        }
      }
      // 3) Keyword check
      if (title && title.length < 30 && searchQuery) {
        const kws = searchQuery
          .toLowerCase()
          .split(/[\s_\-+]+/)
          .filter((w) => w.length >= 2);
        const tl = title.toLowerCase();
        const hasKeyword = kws.length === 0 || kws.some((kw) => tl.includes(kw));
        if (!hasKeyword) title = '';
      }
      // 4) Hint fallback
      if (!title && hint) title = hint;
      // 5) Magnet dn= fallback
      if (!title || title.length < 3) title = extractTitleFromMagnet(magnet);

      // Size
      let _bodyText: string | null = null;
      const getBodyText = () => (_bodyText ??= $('body').text());

      let size = '';
      if (detailSelectors.size) {
        size = $(detailSelectors.size).first().text().trim();
      }
      if (!size) {
        const sizeMatch = getBodyText().match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
        if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');
      }

      // Date
      let date = '';
      if (detailSelectors.date) {
        date = $(detailSelectors.date).first().text().trim();
      }
      if (!date) {
        const dateMatch = getBodyText().match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
        if (dateMatch) date = dateMatch[1];
      }

      // Seeders / Leechers
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

      items.push({
        title: cleanTitle(title || 'Unknown Title'),
        magnet,
        size: normalizeSize(size || sizeHint),
        date: cleanDate(date || dateHint),
        seeders: seeders >= 0 ? seeders : 0,
        leechers: leechers >= 0 ? leechers : 0,
        source: origin,
        site_name: siteName,
        score,
      });
    }

    return items;
  });

  const allItems = await Promise.all(fetches);
  for (const items of allItems) {
    results.push(...items);
    if (results.length >= limit) break;
  }

  return results.slice(0, limit);
}

// ── Custom handlers ──────────────────────────────────────────────────

async function fetchJavBus(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15_000);
  const sig = ac.signal;
  try {
    // Step 1: GET homepage → grab session cookies (age verify no longer needed)
    const r0 = await fetch(origin, {
      headers: FETCH_HEADERS,
      redirect: 'follow',
      signal: sig,
    });
    const sessionCookies = extractCookies(r0);

    // Step 2: Search
    const searchUrl = `${origin}/search/${encodeURIComponent(query)}`;
    const r2 = await fetch(searchUrl, {
      headers: { ...FETCH_HEADERS, Cookie: sessionCookies, Referer: origin + '/' },
      redirect: 'follow',
      signal: sig,
    });
    if (!r2.ok) return results;
    const searchHtml = await r2.text();
    const $ = cheerio.load(searchHtml);
    const detailUrls: string[] = [];
    $('a.movie-box').each((_: number, el: any) => {
      const href = $(el).attr('href');
      if (href) detailUrls.push(href.startsWith('http') ? href : `${origin}${href}`);
    });
    if (detailUrls.length === 0) return results;

    // Step 4: Detail pages → AJAX magnets
    const seen = new Set<string>();
    const pagesToFetch = detailUrls.slice(0, 6);
    const detailFetches = pagesToFetch.map(async (dUrl) => {
      try {
        const dr = await fetch(dUrl, {
          headers: { ...FETCH_HEADERS, Cookie: sessionCookies },
          redirect: 'follow',
          signal: sig,
        });
        if (!dr.ok) return;
        const dHtml = await dr.text();
        const d$ = cheerio.load(dHtml);
        const pageTitle =
          d$('h3').first().text().trim() || d$('title').first().text().trim();

        const gidM = dHtml.match(/var\s+gid\s*=\s*(\d+)/);
        const ucM = dHtml.match(/var\s+uc\s*=\s*(\d+)/);
        if (!gidM) return;
        const gid = gidM[1];
        const uc = ucM ? ucM[1] : '0';

        const ajaxUrl = `${origin}/ajax/uncledatoolsbyajax.php?gid=${gid}&lang=zh&uc=${uc}&floor=${Math.floor(Math.random() * 1000 + 1)}`;
        const ar = await fetch(ajaxUrl, {
          headers: { ...FETCH_HEADERS, Referer: dUrl, Cookie: sessionCookies },
          signal: sig,
        });
        if (!ar.ok) return;
        const aHtml = await ar.text();
        const a$ = cheerio.load(aHtml);

        a$('a[href^="magnet:"]').each((_: number, mel: any) => {
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
            size: normalizeSize(size),
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
  } catch {} finally {
    clearTimeout(timer);
  }
  return results;
}

async function fetchMeijumi(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const seen = new Set<string>();
    const searchUrl = `${origin}/?s=${encodeURIComponent(query)}`;

    // Step 1: GET → captcha answer in cookie
    const resp1 = await fetchPageManual(searchUrl, { method: 'GET' });
    if (!resp1) return results;
    const answerMatch = resp1.cookies.match(/result=(\d+)/);
    if (!answerMatch) return results;
    const answer = answerMatch[1];

    // Step 2: POST answer
    await fetchPageManual(searchUrl, {
      method: 'POST',
      body: `result=${answer}`,
      contentType: 'application/x-www-form-urlencoded',
      cookies: `result=${answer}`,
      referer: searchUrl,
    });

    // Step 3: GET with captcha-passed cookie
    const resp3 = await fetchPage(searchUrl, `result=${answer}; esc_search_captcha=1`);
    if (!resp3.html) return results;
    const $ = cheerio.load(resp3.html);
    const allCookies = `result=${answer}; esc_search_captcha=1`;
    const detailUrls: string[] = [];

    $('a[href]').each((_: number, el: any) => {
      const href = $(el).attr('href') || '';
      if (/meijumi\.net\/\d+\.html/.test(href) && !detailUrls.includes(href)) {
        detailUrls.push(href);
      }
    });

    // Step 4: Follow detail pages
    const pages = detailUrls.slice(0, 8);
    const fetches = pages.map(async (dUrl) => {
      try {
        const dr = await fetchPage(dUrl, allCookies);
        if (!dr.html) return;
        const d$ = cheerio.load(dr.html);
        const title =
          d$('h1.entry-title, h1.article-title, h1').first().text().trim() ||
          d$('title').first().text().replace(/-.*$/, '').trim();

        d$('a[href^="magnet:"]').each((_: number, mel: any) => {
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
            size: normalizeSize(size),
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
  } catch {}
  return results;
}

async function fetchYhg(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    // Step 1: GET homepage → CSRF token
    const homeResp = await fetchPage(origin + '/');
    if (!homeResp.html) return results;
    const csrfMatch = homeResp.html.match(/csrf_token[^>]*value="([^"]+)"/);
    if (!csrfMatch) return results;

    // We need cookies from the home page
    // Re-fetch manually to get cookies
    const homeManual = await fetchPageManual(origin + '/', { method: 'GET' });
    if (!homeManual) return results;

    // Step 2: POST search
    const body = new URLSearchParams({ csrf_token: csrfMatch[1], search: query });
    const searchResp = await fetchPageManual(origin + '/search', {
      method: 'POST',
      body: body.toString(),
      contentType: 'application/x-www-form-urlencoded',
      cookies: homeManual.cookies,
      referer: origin + '/',
    });
    if (!searchResp || !searchResp.html) return results;

    const $ = cheerio.load(searchResp.html);
    const seen = new Set<string>();

    $('.ssbox').each((_: number, el: any) => {
      const item = $(el);
      const title = item.find('.title h3 a').first().text().trim();
      const magnetLink = item.find('.sbar a[href^="magnet:"]').first().attr('href') || '';
      if (!magnetLink || !title || seen.has(magnetLink)) return;
      seen.add(magnetLink);

      const sbar = item.find('.sbar').text();
      let size = '';
      const sizeMatch = sbar.match(/大小[：:]\s*([\d.]+\s*[TGMK]i?B)/i);
      if (sizeMatch) size = sizeMatch[1];
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
        size: normalizeSize(size),
        date,
        seeders: 0,
        leechers: 0,
        source: origin,
        site_name: siteName,
        score,
      });
    });
  } catch {}
  return results;
}

async function fetchRarbggo(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchUrl = `${origin}/search/?search=${encodeURIComponent(query)}`;
    const resp = await fetchPage(searchUrl);
    if (!resp.html) return results;
    const $ = cheerio.load(resp.html);

    const detailUrls: string[] = [];
    $('a[href*="/torrent/"]').each((_: number, el: any) => {
      const href = $(el).attr('href') || '';
      if (href.includes('/torrent/') && href.endsWith('.html')) {
        const full = href.startsWith('http') ? href : `${origin}${href}`;
        if (!detailUrls.includes(full)) detailUrls.push(full);
      }
    });

    const seen = new Set<string>();
    const pages = detailUrls.slice(0, 10);
    const fetches = pages.map(async (dUrl) => {
      try {
        const dr = await fetchPage(dUrl);
        if (!dr.html) return;
        const d$ = cheerio.load(dr.html);
        const title =
          d$('h1').first().text().trim() ||
          d$('title').first().text().replace(/\s*[-|].*$/, '').trim();
        d$('a[href^="magnet:"]').each((_: number, el: any) => {
          const mag = d$(el).attr('href') || '';
          const hash = mag.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase();
          if (hash && !seen.has(hash)) {
            seen.add(hash);
            results.push({
              title: title || 'Unknown Title',
              magnet: mag,
              size: '',  // no size available
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
  } catch {}
  return results;
}

async function fetchRrjav(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchUrl = `${origin}/?s=${encodeURIComponent(query)}`;
    const resp = await fetchPage(searchUrl);
    if (!resp.html) return results;
    const $ = cheerio.load(resp.html);

    const seen = new Set<string>();
    $('a[href^="magnet:"]').each((_: number, el: any) => {
      const mag = $(el).attr('href') || '';
      const hash = mag.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase();
      if (!hash || seen.has(hash)) return;
      seen.add(hash);

      const container = $(el).closest('article, .torrent-item, tr, li, div.entry, div.post');
      let title = '';
      if (container.length) {
        title = container.find('h2, h3, h4, .entry-title, a[title]').first().text().trim();
      }
      if (!title) title = extractTitleFromMagnet(mag);

      let size = '';
      const nearby = container.length ? container.text() : $(el).parent().text();
      const sizeMatch = nearby.match(/([\d.]+)\s*(GB|MB|TB)/i);
      if (sizeMatch) size = sizeMatch[0];

      let date = '';
      const dateMatch = nearby.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
      if (dateMatch) date = dateMatch[1];

      results.push({
        title: title || 'Unknown Title',
        magnet: mag,
        size: normalizeSize(size),
        date,
        seeders: 0,
        leechers: 0,
        source: searchUrl,
        site_name: siteName,
        score,
      });
    });
  } catch {}
  return results;
}

/* ---- 1337x family custom handler ---- */
async function fetch1337x(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  // 1. Fetch search page
  const searchUrl = `${origin}/search/${encodeURIComponent(query)}/1/`;
  console.log(`[fetch1337x] Fetching search: ${searchUrl}`);
  const searchResult = await fetchPage(searchUrl);
  if (!searchResult.html) {
    console.log(`[fetch1337x] No HTML returned for ${searchUrl} challenge=${JSON.stringify(searchResult.challenge)}`);
    return [];
  }
  console.log(`[fetch1337x] Got HTML, length=${searchResult.html.length}`);

  const $ = cheerio.load(searchResult.html);
  const rows = $('tr:has(a[href*="/torrent/"])');
  if (rows.length === 0) return [];

  // 2. Parse search result rows (titles are ALWAYS correct here)
  const searchRows: Array<{
    title: string;
    detailUrl: string;
    size: string;
    date: string;
    seeders: number;
    leechers: number;
  }> = [];

  rows.each((_: number, el: any) => {
    const row = $(el);
    const titleLink = row.find('td.coll-1 a:not(.icon)').first();
    const title = titleLink.attr('title') || titleLink.text().trim();
    const href = titleLink.attr('href') || '';
    if (!title || title.length < 3 || !href) return;

    const detailUrl = href.startsWith('http') ? href : new URL(href, origin).href;

    // Size: td.coll-4 has a hidden <span> that concats, so regex-extract
    const rawSize = row.find('td.coll-4').first().text().trim();
    const sizeMatch = rawSize.match(/([\d.]+)\s*(TB|GB|MB|KB)/i);
    const size = sizeMatch ? `${sizeMatch[1]} ${sizeMatch[2]}` : '';

    const date = row.find('td.coll-date').first().text().trim();
    const seeders = parseInt(row.find('td.coll-2').first().text().trim(), 10) || 0;
    const leechers = parseInt(row.find('td.coll-3').first().text().trim(), 10) || 0;

    searchRows.push({ title, detailUrl, size, date, seeders, leechers });
  });

  console.log(`[fetch1337x] Parsed ${searchRows.length} rows from search page`);
  if (searchRows.length === 0) return [];
  searchRows.slice(0, 3).forEach((r, i) => console.log(`[fetch1337x]   row${i}: title="${r.title}" detail=${r.detailUrl.slice(0, 80)}`));

  // 2b. Relevance pre-filter: 1337x shows trending when no results match.
  //     Require at least min(2, total) query words present in the title.
  const qWords = query.toLowerCase().split(/[\s.+\-_]+/).filter(w => w.length >= 2);
  const minMatch = Math.min(2, qWords.length);
  const relevant = searchRows.filter(r => {
    const tLow = r.title.toLowerCase();
    const hits = qWords.filter(w => tLow.includes(w)).length;
    return hits >= minMatch;
  });
  if (relevant.length === 0) {
    console.log(`[fetch1337x] No titles match ≥${minMatch} of query words [${qWords.join(',')}] — likely trending page, returning empty`);
    return [];
  }
  console.log(`[fetch1337x] ${relevant.length}/${searchRows.length} titles match ≥${minMatch} query words`);

  // 3. Follow detail pages concurrently (max 8) to extract magnet links
  const toFetch = relevant.slice(0, 8);
  const seen = new Set<string>();

  const fetches = toFetch.map(async (row) => {
    try {
      const { html: detailHtml } = await fetchPage(row.detailUrl);
      if (!detailHtml) return null;

      const d$ = cheerio.load(detailHtml);
      const magnet = d$('a[href^="magnet:"]').first().attr('href') || '';
      if (!magnet.startsWith('magnet:?')) return null;

      const hash = magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase();
      if (!hash || seen.has(hash)) return null;
      seen.add(hash);

      // Key fix: use SEARCH PAGE title (always correct) — not detail page title
      return {
        title: cleanTitle(row.title),
        magnet,
        size: normalizeSize(row.size),
        date: cleanDate(row.date),
        seeders: row.seeders,
        leechers: row.leechers,
        source: origin,
        site_name: siteName,
        score,
      } as ResultItem;
    } catch {
      return null;
    }
  });

  const items = await Promise.all(fetches);
  const results: ResultItem[] = [];
  for (const item of items) {
    if (item) results.push(item);
  }
  console.log(`[fetch1337x] Final results: ${results.length} items`);
  results.slice(0, 3).forEach((r, i) => console.log(`[fetch1337x]   result${i}: title="${r.title}" magnet=${r.magnet.slice(0, 50)}`));
  return results;
}

/* ---- CiliMo (cilimo.com) handler: JSON API with info_hash ---- */
async function fetchCiliMo(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const url = `${origin}/api/search?q=${encodeURIComponent(query)}`;
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 10_000);
    const resp = await fetch(url, {
      headers: { ...FETCH_HEADERS, 'Accept': 'application/json' },
      signal: ac.signal,
    });
    clearTimeout(timer);
    if (!resp.ok) return results;
    const data = await resp.json() as any;
    const items = data.results || [];
    for (const item of items.slice(0, 20)) {
      const hash = item.info_hash;
      if (!hash) continue;
      const magnet = `magnet:?xt=urn:btih:${hash}`;
      const sizeBytes = item.length || 0;
      let size = '';
      if (sizeBytes >= 1e12) size = `${(sizeBytes / 1e12).toFixed(2)} TB`;
      else if (sizeBytes >= 1e9) size = `${(sizeBytes / 1e9).toFixed(2)} GB`;
      else if (sizeBytes >= 1e6) size = `${(sizeBytes / 1e6).toFixed(1)} MB`;
      else if (sizeBytes > 0) size = `${(sizeBytes / 1e3).toFixed(0)} KB`;

      const name = item.name || extractTitleFromMagnet(magnet) || 'Unknown';
      const date = item.created_at ? item.created_at.split('T')[0] : '';

      results.push({
        title: name,
        magnet,
        size,
        date,
        seeders: 0,
        leechers: 0,
        source: origin,
        site_name: siteName,
        score,
      });
    }
    console.log(`[CiliMo] Found ${results.length} results for "${query}"`);
  } catch (e: any) {
    console.error(`[CiliMo] Error: ${e.message}`);
  }
  return results;
}

/* ---- CLKD / 磁力口袋 (kd705.site) handler: JSON API with hashInfo ---- */
async function fetchClkd(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const url = `${origin}/api/search?q=${encodeURIComponent(query)}`;
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 10_000);
    const resp = await fetch(url, {
      headers: { ...FETCH_HEADERS, 'Accept': 'application/json' },
      signal: ac.signal,
    });
    clearTimeout(timer);
    if (!resp.ok) return results;
    const data = await resp.json() as any;
    const items = data.list || [];
    for (const item of items.slice(0, 20)) {
      const hash = item.hashInfo;
      if (!hash) continue;
      const magnet = `magnet:?xt=urn:btih:${hash}`;
      const sizeBytes = item.torrentSize || 0;
      let size = '';
      if (sizeBytes >= 1e12) size = `${(sizeBytes / 1e12).toFixed(2)} TB`;
      else if (sizeBytes >= 1e9) size = `${(sizeBytes / 1e9).toFixed(2)} GB`;
      else if (sizeBytes >= 1e6) size = `${(sizeBytes / 1e6).toFixed(1)} MB`;
      else if (sizeBytes > 0) size = `${(sizeBytes / 1e3).toFixed(0)} KB`;

      const name = item.torrentName || extractTitleFromMagnet(magnet) || 'Unknown';
      const date = item.createTime ? item.createTime.split('T')[0] : '';

      results.push({
        title: name,
        magnet,
        size,
        date,
        seeders: 0,
        leechers: 0,
        source: origin,
        site_name: siteName,
        score,
      });
    }
    console.log(`[CLKD] Found ${results.length} results for "${query}"`);
  } catch (e: any) {
    console.error(`[CLKD] Error: ${e.message}`);
  }
  return results;
}

// ── Main search entry point ──────────────────────────────────────────

/**
 * Search a single source locally on device.
 * This is the equivalent of the old POST /api/search route,
 * but running entirely on the user's device.
 */
export async function searchSource(
  rule: SourceRule,
  query: string,
): Promise<ResultItem[]> {
  const origin = rule.site.origin.replace(/\/$/, '');

  // Skip blacklisted origins (failed verification this session)
  if (VerifyManager.isBlacklisted(origin)) {
    console.log(`[Verify:Skip] ${rule.site.name} (${origin}) blacklisted — skipping`);
    throw new Error('__blacklisted__');
  }
  const template = rule.search.request_template;
  // Build search URL: {query} → URL-encoded, {query_b64} → base64-encoded
  const queryB64 = typeof btoa === 'function'
    ? btoa(unescape(encodeURIComponent(query)))
    : Buffer.from(query, 'utf-8').toString('base64');
  const searchUrl =
    origin +
    template
      .replace('{query}', encodeURIComponent(query))
      .replace('{query_b64}', queryB64);
  const selectors = rule.search.parse_metadata.selectors;
  const supportsDetail = rule.capabilities?.supports_detail ?? false;
  const detailSelectors = rule.search.detail?.selectors
    ? { ...rule.search.detail.selectors }
    : undefined;
  // 1337x override
  if (/1337x|1377x/i.test(origin) && detailSelectors) {
    detailSelectors.title = '.box-info-heading h1';
  }
  const siteName = rule.site.name;
  const score = rule.quality?.score ?? 50;
  const handler = rule.search.handler || '';
  const customReferer = rule.search.referer || '';
  // ── Custom handler dispatch ──
  if (handler === 'javbus') return (await fetchJavBus(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'meijumi') return (await fetchMeijumi(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'yhg') return (await fetchYhg(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'rarbggo') return (await fetchRarbggo(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'rrjav') return (await fetchRrjav(origin, query, siteName, score)).slice(0, 30);
  if (handler === '1337x') return (await fetch1337x(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'cilimo') return (await fetchCiliMo(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'clkd') return (await fetchClkd(origin, query, siteName, score)).slice(0, 20);

  // ── SPA sources: render via WebView (like Legado's BackstageWebView) ──
  if (rule.search.requires_browser) {
    console.log(`[SearchEngine] ${siteName} requires browser rendering — requesting WebView`);
    const vr = await VerifyManager.requestVerification(
      searchUrl, 'spa_render', origin, siteName,
    );
    if (vr.success && vr.html) {
      // Store any cookies from the WebView session
      if (vr.cookies) storeCookiesForOrigin(origin, vr.cookies);
      const $ = cheerio.load(vr.html);
      const { results: spaResults, detailUrls: spaDetailUrls, titleHints: spaTH, sizeHints: spaSH, dateHints: spaDH } =
        extractFromSearchPage($, selectors, origin, siteName, score);
      const spaCleaned = spaResults.filter((r) => r.title && r.title !== 'Unknown Title' && r.title.length >= 4);
      // Follow detail pages if needed
      if (supportsDetail && detailSelectors && spaDetailUrls.length > 0 && spaCleaned.length < 20) {
        const spaDetailResults = await fetchDetailResults(
          spaDetailUrls, detailSelectors, origin, siteName, score,
          20 - spaCleaned.length, spaTH, spaSH, spaDH, query,
        );
        spaCleaned.push(...spaDetailResults);
      }
      return spaCleaned.slice(0, 30);
    }
    console.log(`[SearchEngine] WebView render failed for ${siteName}: ${vr.error}`);
    return [];
  }

  // ── Standard flow ──
  let html: string | null = null;

  if (rule.search.requires_csrf) {
    // CSRF POST flow
    const homeResp = await fetchPage(origin);
    if (homeResp.html) {
      const csrfMatch = homeResp.html.match(/name=["']csrf_token["']\s+value=["']([^"']+)["']/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';
      const homeManual = await fetchPageManual(origin, { method: 'GET' });
      const cookies = homeManual?.cookies || '';
      const body = new URLSearchParams({ csrf_token: csrfToken, search: query });
      const searchResp = await fetchPageManual(`${origin}/search`, {
        method: 'POST',
        body: body.toString(),
        contentType: 'application/x-www-form-urlencoded',
        cookies,
        referer: origin + '/',
      });
      html = searchResp?.html || null;
    }
  } else {
    const result = await fetchPage(searchUrl, undefined, undefined, customReferer || undefined);
    // Challenge detected → trigger WebView verification (Legado-style)
    if (result.challenge) {
      // Old cookies didn't work → invalidate so fresh ones get persisted
      invalidateCookies(origin);
      console.log(`[SearchEngine] Challenge on ${siteName}: ${result.challenge.type} — requesting WebView`);
      const vr = await VerifyManager.requestVerification(
        result.challenge.verifyUrl,
        result.challenge.type as any,
        origin,
        siteName,
      );
      if (vr.success) {
        // Store cookies from verification session
        if (vr.cookies) storeCookiesForOrigin(origin, vr.cookies);
        if (vr.html) {
          // Use pre-rendered HTML directly (avoid re-fetch)
          html = vr.html;
        } else {
          // Re-fetch with new cookies (like Legado's cookie-based retry)
          const retryResult = await fetchPage(searchUrl, vr.cookies);
          html = retryResult.html;
        }
      } else {
        console.log(`[SearchEngine] Verification failed for ${siteName}: ${vr.error}`);
        return [];
      }
    } else {
      html = result.html;
    }
  }

  if (!html) return [];

  const $ = cheerio.load(html);
  const { results, detailUrls, titleHints, sizeHints, dateHints } =
    extractFromSearchPage($, selectors, origin, siteName, score);

  // Filter garbage — also reject titles that are just known site names
  const _normT = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  const cleaned = results.filter((r) => {
    if (!r.title || r.title === 'Unknown Title') return false;
    if (r.title.length < 4) return false;
    const tl = r.title.toLowerCase();
    const sl = siteName.toLowerCase();
    if (tl === sl || (tl.includes(' home') && tl.length < 30)) return false;
    // Reject titles that are just a known site name (e.g. "1337x" from nav links)
    const nt = _normT(r.title);
    if (nt.length < 20 && KNOWN_SITE_NAMES.some(
      (sn) => nt === sn || nt === sn + 'to' || nt === sn + 'com' || nt === sn + 'org' || nt === sn + 'site',
    )) return false;
    return true;
  });

  // Follow detail pages
  let detailCleaned: ResultItem[] = [];
  if (supportsDetail && detailSelectors && detailUrls.length > 0 && cleaned.length < 20) {
    const remainingSlots = 20 - cleaned.length;
    const urlsToFollow = detailUrls.filter(
      (url) =>
        !cleaned.some((r) =>
          url.includes(r.magnet.match(/btih:([a-fA-F0-9]+)/)?.[1] || '__none__'),
        ),
    );
    if (urlsToFollow.length > 0) {
      const hintMap = detailUrls.map((u, i) => ({
        u,
        t: titleHints[i] || '',
        s: sizeHints[i] || '',
        d: dateHints[i] || '',
      }));
      const filteredTitleHints = urlsToFollow.map((url) => hintMap.find((h) => h.u === url)?.t || '');
      const filteredSizeHints = urlsToFollow.map((url) => hintMap.find((h) => h.u === url)?.s || '');
      const filteredDateHints = urlsToFollow.map((url) => hintMap.find((h) => h.u === url)?.d || '');
      const detailResults = await fetchDetailResults(
        urlsToFollow,
        detailSelectors,
        origin,
        siteName,
        score,
        remainingSlots,
        filteredTitleHints,
        filteredSizeHints,
        filteredDateHints,
        query,
        customReferer || undefined,
      );
      const siteNorm = siteName.toLowerCase().replace(/[^a-z0-9]/g, '');
      detailCleaned = detailResults.filter((r) => {
        if (!r.title || r.title === 'Unknown Title') return false;
        if (r.title.length < 4) return false;
        const tn = r.title.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (
          tn === siteNorm ||
          siteNorm.includes(tn) ||
          (tn.includes(siteNorm) && tn.length < siteNorm.length + 5)
        )
          return false;
        return true;
      });
    }
  }

  // Merge + dedup
  const allResults = [...cleaned, ...detailCleaned];
  const seen = new Set<string>();
  const merged = allResults.filter((r) => {
    const hash = r.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1]?.toLowerCase() || r.magnet;
    if (seen.has(hash)) return false;
    seen.add(hash);
    return true;
  });

  return merged.slice(0, 20);
}
