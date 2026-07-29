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
  getStoredCookies,
  invalidateCookies,
  extractCookies,
  mergeCookies,
  FETCH_HEADERS,
  type FetchResult,
  isBackgroundNetworkMode,
} from './httpClient';
import { VerifyManager } from './VerifyManager';
import { extractInfoHash } from './dedup';
import {
  isHashPlaceholderTitle,
  recoverResultTitle,
} from './searchResultTitle';

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
  // Chinese date: 2024年3月15日
  const d5 = raw.match(/(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5/);
  if (d5) return `${d5[1]}-${d5[2].padStart(2, '0')}-${d5[3].padStart(2, '0')}`;
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

type RawFetchTextResult = {
  ok: boolean;
  status: number;
  text: string;
  finalUrl: string;
  cookies: string;
};

function getRemainingSourceBudget(deadlineAt: number, maxSliceMs: number): number {
  const remainingMs = deadlineAt - Date.now();
  if (remainingMs <= 0) return 0;
  return Math.min(maxSliceMs, remainingMs);
}

async function fetchTextWithTimeout(
  url: string,
  options?: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    referer?: string;
    contentType?: string;
    timeoutMs?: number;
    redirect?: RequestRedirect;
  },
): Promise<RawFetchTextResult | null> {
  const timeoutMs = options?.timeoutMs ?? 10_000;
  const headers = { ...(options?.headers || {}) };
  if (options?.referer) headers.Referer = options.referer;
  if (options?.contentType) headers['Content-Type'] = options.contentType;

  if (isBackgroundNetworkMode()) {
    const bgResp = await fetchPageManual(url, {
      method: options?.method ?? 'GET',
      body: options?.body,
      contentType: headers['Content-Type'],
      cookies: headers.Cookie,
      referer: headers.Referer,
      extraHeaders: Object.fromEntries(
        Object.entries(headers).filter(([key]) => key !== 'Content-Type' && key !== 'Cookie' && key !== 'Referer'),
      ),
      timeoutMs,
    });
    if (!bgResp) return null;
    return {
      ok: bgResp.status >= 200 && bgResp.status < 400,
      status: bgResp.status,
      text: bgResp.html || '',
      finalUrl: bgResp.responseUrl || url,
      cookies: bgResp.cookies || '',
    };
  }

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      method: options?.method ?? 'GET',
      headers,
      body: options?.body,
      redirect: options?.redirect ?? 'follow',
      signal: ac.signal,
    });
    const text = await resp.text();
    return {
      ok: resp.ok,
      status: resp.status,
      text,
      finalUrl: resp.url || url,
      cookies: extractCookies(resp),
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
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

function magnetFromLooseValue(raw: string): string {
  const value = String(raw || '').trim();
  if (!value) return '';
  if (/^magnet:\?/i.test(value) && extractInfoHash(value)) return value;

  const match = value.match(
    /(?:btih:|\/hash\/|\/torrent\/|[?&](?:hash|info_?hash|infohash|btih)=)([a-f0-9]{40}|[a-z2-7]{32})(?:\b|[./?&#_-])/i,
  ) || value.match(/^([a-f0-9]{40}|[a-z2-7]{32})$/i);
  if (!match) return '';
  return `magnet:?xt=urn:btih:${match[1]}`;
}

function titleFromLooseValue(raw: string): string {
  const value = String(raw || '').trim();
  if (!value) return '';
  try {
    const parsed = new URL(value, 'https://local.invalid');
    for (const key of ['title', 'dn', 'name', 'filename']) {
      const candidate = parsed.searchParams.get(key);
      if (candidate) return decodeURIComponent(candidate.replace(/\+/g, ' ')).trim();
    }
  } catch {}
  return '';
}

function formatStructuredSize(value: unknown): string {
  if (typeof value === 'string' && /\b(?:TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i.test(value)) {
    return normalizeSize(value.trim());
  }
  const bytes = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(2)} TB`;
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${Math.trunc(bytes)} B`;
}

function parseStructuredSearchPayload(
  raw: string,
  origin: string,
  siteName: string,
  score: number,
): { parsed: boolean; results: ResultItem[]; unresolvedHashCount: number } {
  const trimmed = raw.trim();
  if (!trimmed || !/^[\[{]/.test(trimmed)) {
    return { parsed: false, results: [], unresolvedHashCount: 0 };
  }

  let payload: unknown;
  try {
    payload = JSON.parse(trimmed);
  } catch {
    return { parsed: false, results: [], unresolvedHashCount: 0 };
  }

  const results: ResultItem[] = [];
  const seen = new Set<string>();
  let unresolvedHashCount = 0;
  const visit = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== 'object') return;
    const row = value as Record<string, unknown>;
    const rawMagnet = [row.magnet, row.magnet_uri, row.magnetUri, row.url]
      .find((candidate) => typeof candidate === 'string' && /^magnet:\?/i.test(candidate)) as string | undefined;
    const rawHash = [row.info_hash, row.infohash, row.infoHash, row.btih, row.hash]
      .find((candidate) => typeof candidate === 'string') as string | undefined;
    const magnet = rawMagnet || magnetFromLooseValue(rawHash || '');
    const hash = extractInfoHash(magnet);
    if (hash && !/^0+$/.test(hash) && !seen.has(hash)) {
      const titleCandidate = [
        row.name,
        row.title,
        row.torrent_name,
        row.torrentName,
        row.filename,
        row.file_name,
        row.name_simple,
        row.name_IK,
      ].find((candidate) => typeof candidate === 'string') as string | undefined;
      const title = recoverResultTitle(titleCandidate || '', magnet);
      if (title) {
        seen.add(hash);
        const added = row.added ?? row.created_at ?? row.createdAt ?? row.date;
        let date = typeof added === 'string' ? added : '';
        if (!date && typeof added === 'number' && added > 0) {
          date = new Date(added * (added < 10_000_000_000 ? 1000 : 1)).toISOString().slice(0, 10);
        }
        results.push({
          title: cleanTitle(title),
          magnet,
          size: formatStructuredSize(row.size ?? row.size_bytes ?? row.sizeBytes),
          date: cleanDate(date),
          seeders: Math.max(0, Number(row.seeders ?? row.seeds) || 0),
          leechers: Math.max(0, Number(row.leechers ?? row.peers) || 0),
          source: origin,
          site_name: siteName,
          score,
        });
      } else {
        unresolvedHashCount += 1;
      }
    }
    Object.values(row).forEach(visit);
  };
  visit(payload);
  return { parsed: true, results, unresolvedHashCount };
}

function resolveResultTitle(rawTitle: string, magnet: string): string {
  const recovered = recoverResultTitle(cleanTitle(String(rawTitle || '').trim()), magnet);
  return recovered ? cleanTitle(recovered) : '';
}

function finalizeSearchResults(items: ResultItem[]): ResultItem[] {
  const seen = new Set<string>();
  const finalized: ResultItem[] = [];
  let rejectedHashTitles = 0;
  for (const item of items) {
    const title = resolveResultTitle(item.title, item.magnet);
    if (!title || title.length < 4) {
      if (isHashPlaceholderTitle(item.title, item.magnet)) rejectedHashTitles += 1;
      continue;
    }
    const hash = extractInfoHash(item.magnet) || item.magnet;
    if (seen.has(hash)) continue;
    seen.add(hash);
    finalized.push({ ...item, title });
  }
  if (items.length > 0 && finalized.length === 0 && rejectedHashTitles > 0) {
    throw new Error('INVALID_RESULT_TITLE_PARSE');
  }
  return finalized;
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
  unboundEvidenceCount: number;
} {
  const results: ResultItem[] = [];
  const detailUrls: string[] = [];
  const titleHints: string[] = [];
  const sizeHints: string[] = [];
  const dateHints: string[] = [];
  let unboundEvidenceCount = 0;
  // Union a few stable result-container patterns so broad/old source rules do
  // not fall through to a global evidence scan when the site changed a wrapper
  // tag. The source-specific selector remains first and authoritative.
  const items = $(
    `${selectors.list_item}, article.item, article.torrent-item, tr.list-entry, `
    + `div.bg-white.rounded-lg.border, [data-info-hash], [data-infohash]`,
  );
  const htmlStr = $.html();
  const rawMagnetEvidenceCount = Math.max(
    $('a[href^="magnet:"]').length,
    (htmlStr.match(/magnet:\?xt=urn:btih:/gi) || []).length,
  );

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
    if (!magnet) {
      const looseValues: string[] = [];
      item.find('a[href]').each((__, link) => {
        looseValues.push($(link).attr('href') || '');
      });
      item.find('[data-hash], [data-info-hash], [data-infohash], [data-btih]').each((__, node) => {
        looseValues.push(
          $(node).attr('data-hash')
          || $(node).attr('data-info-hash')
          || $(node).attr('data-infohash')
          || $(node).attr('data-btih')
          || '',
        );
      });
      magnet = looseValues.map(magnetFromLooseValue).find(Boolean) || '';
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
      // Chinese sites often have no space: "1.5GB"
      if (!size) {
        const cnSize = item.text().match(/([\d.]+)(TB|GB|MB|KB)/i);
        if (cnSize) size = `${cnSize[1]} ${cnSize[2]}`;
      }
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
        txt.match(/(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5/) ||
        txt.match(
          /((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})/i,
        ) ||
        txt.match(
          /(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})/i,
        );
      if (dateMatch) {
        if (dateMatch[2] && dateMatch[3]) {
          date = `${dateMatch[1]}-${dateMatch[2].padStart(2, '0')}-${dateMatch[3].padStart(2, '0')}`;
        } else {
          date = dateMatch[1];
        }
      }
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

  // Selector drift recovery: only recover a result when the title and magnet
  // are bound by the same anchor/container or by the magnet's own `dn` field.
  // Never convert an arbitrary page-level hash into a user-visible result.
  if (results.length === 0 && rawMagnetEvidenceCount > 0) {
    const seen = new Set<string>();
    $('a[href^="magnet:"]').each((_: number, el: any) => {
      if (results.length >= 20) return false;
      const anchor = $(el);
      const magnet = anchor.attr('href') || '';
      const hash = extractInfoHash(magnet);
      if (!hash || seen.has(hash)) return;
      seen.add(hash);

      const container = anchor.closest(
        'tr, article, li, .card, .item, .search-item, .torrent-item, '
        + '.result-item, .list-entry, div.bg-white.rounded-lg.border',
      );
      const scope = container.length ? container : anchor.parent();
      const titleCandidates = [
        extractTitleFromMagnet(magnet),
        scope.find('[data-title]').first().attr('data-title') || '',
        scope.find('.item-title a, .item-name a, h1 a, h2 a, h3 a, h4 a').first().text(),
        scope.find('h1, h2, h3, h4, .item-title, .title').first().text(),
        scope.find('a[title]').first().attr('title') || '',
      ];
      const title = titleCandidates
        .map((candidate) => recoverResultTitle(candidate, magnet))
        .find((candidate): candidate is string => !!candidate);
      if (!title) {
        unboundEvidenceCount += 1;
        return;
      }

      const scopeText = scope.text();
      const size = scopeText.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i)?.[0] || '';
      const date = scopeText.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})/)?.[0] || '';
      const seeders = Number(scopeText.match(/(\d+)\s*seeders?/i)?.[1] || 0);
      const leechers = Number(scopeText.match(/(\d+)\s*leechers?/i)?.[1] || 0);
      results.push({
        title: cleanTitle(title),
        magnet,
        size: normalizeSize(size),
        date: cleanDate(date),
        seeders,
        leechers,
        source: origin,
        site_name: siteName,
        score,
      });
    });

    // Some pages emit magnet URIs inside scripts instead of anchors. Preserve
    // the complete URI so a `dn` title can prove the binding; a bare BTIH is
    // diagnostic evidence only and must not become a result.
    if (results.length === 0) {
      const scriptMagnetRe = /magnet:\?[^"'<>\s]+/gi;
      let match: RegExpExecArray | null;
      while ((match = scriptMagnetRe.exec(htmlStr)) !== null && results.length < 20) {
        const magnet = match[0]
          .replace(/&amp;/gi, '&')
          .replace(/&#x3d;/gi, '=')
          .replace(/&#61;/gi, '=');
        const hash = extractInfoHash(magnet);
        if (!hash || seen.has(hash)) continue;
        seen.add(hash);
        const title = recoverResultTitle('', magnet);
        if (!title) {
          unboundEvidenceCount += 1;
          continue;
        }
        results.push({
          title: cleanTitle(title),
          magnet,
          size: '',
          date: '',
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      }
    }
  }

  // Bare hashes may still be useful when a same-element URL carries a title
  // parameter (for example `/download/torrent/<hash>?title=...`). Otherwise
  // they prove parser drift and must trigger same-pool fallback.
  if (results.length === 0) {
    const seen = new Set<string>();
    $('a[href], [data-hash], [data-info-hash], [data-infohash], [data-btih]').each((_: number, el: any) => {
      if (results.length >= 20) return false;
      const node = $(el);
      const looseValue = node.attr('href')
        || node.attr('data-hash')
        || node.attr('data-info-hash')
        || node.attr('data-infohash')
        || node.attr('data-btih')
        || '';
      const magnet = magnetFromLooseValue(looseValue);
      const hash = extractInfoHash(magnet);
      if (!hash || seen.has(hash)) return;
      seen.add(hash);

      const container = node.closest(
        'tr, article, li, .card, .item, .search-item, .torrent-item, '
        + '.result-item, .list-entry, div.bg-white.rounded-lg.border',
      );
      const scope = container.length ? container : node.parent();
      const titleCandidates = [
        titleFromLooseValue(looseValue),
        scope.find('[data-title]').first().attr('data-title') || '',
        scope.find('.item-title a, .item-name a, h1 a, h2 a, h3 a, h4 a').first().text(),
        scope.find('h1, h2, h3, h4, .item-title, .title').first().text(),
      ];
      const title = titleCandidates
        .map((candidate) => recoverResultTitle(candidate, magnet))
        .find((candidate): candidate is string => !!candidate);
      if (!title) {
        unboundEvidenceCount += 1;
        return;
      }
      results.push({
        title: cleanTitle(title),
        magnet,
        size: normalizeSize(scope.text().match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i)?.[0] || ''),
        date: cleanDate(scope.text().match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})/)?.[0] || ''),
        seeders: Number(scope.text().match(/(\d+)\s*seeders?/i)?.[1] || 0),
        leechers: Number(scope.text().match(/(\d+)\s*leechers?/i)?.[1] || 0),
        source: origin,
        site_name: siteName,
        score,
      });
    });
  }

  if (results.length === 0) {
    const bareHashes = new Set(
      htmlStr.match(/\b(?:[a-fA-F0-9]{40}|[A-Za-z2-7]{32})\b/g) || [],
    );
    unboundEvidenceCount += bareHashes.size;
  }

  return { results, detailUrls, titleHints, sizeHints, dateHints, unboundEvidenceCount };
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
  // Cap at 5 on mobile (was 12) — prevents 12 simultaneous cheerio.load() bursts
  const urlsToFetch = detailUrls.slice(0, Math.min(detailUrls.length, 5));

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

  // Helper: parse one detail page (synchronous cheerio work isolated here)
  const parseOne = async (url: string, urlIdx: number): Promise<ResultItem[]> => {
    const { html } = await fetchPage(url, undefined, undefined, referer);
    if (!html) return [];

    const $ = cheerio.load(html);
    const items: ResultItem[] = [];
    const hint = titleHints[urlIdx] || '';
    const sizeHint = sizeHints[urlIdx] || '';
    const dateHint = dateHints[urlIdx] || '';

    const magnetLinks = $(detailSelectors.magnet || 'a[href^="magnet:"]');
    const foundMagnets: string[] = [];
    magnetLinks.each((_: number, el: any) => {
      const mag = $(el).attr('href') || '';
      if (mag.startsWith('magnet:?')) foundMagnets.push(mag);
    });
    // Fallback: regex extract from full HTML (support both hex and Base32 btih)
    if (foundMagnets.length === 0) {
      const htmlStr = $.html();
      const re = /magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}|magnet:\?xt=urn:btih:[A-Za-z2-7]{32}/gi;
      let m;
      while ((m = re.exec(htmlStr)) !== null) foundMagnets.push(m[0]);
    }
    // Second fallback: bare 40-char hex info hashes in data attributes, copy buttons, spans, etc.
    // Sites like cld141.buzz store hashes as bare text, not in magnet URIs.
    if (foundMagnets.length === 0) {
      const htmlStr = $.html();
      const hashRe = /\b([a-fA-F0-9]{40})\b/g;
      const hashSeen = new Set<string>();
      let hm: RegExpExecArray | null;
      while ((hm = hashRe.exec(htmlStr)) !== null) {
        const hex = hm[1].toLowerCase();
        if (hashSeen.has(hex)) continue;
        hashSeen.add(hex);
        foundMagnets.push(`magnet:?xt=urn:btih:${hex}`);
        if (foundMagnets.length >= 5) break;
      }
    }

    for (const magnet of foundMagnets) {
      if (seen.has(magnet)) continue;
      seen.add(magnet);

      let title = '';
      if (detailSelectors.title) {
        const candidate = recoverResultTitle($(detailSelectors.title).first().text(), magnet);
        if (candidate && !_looksLikeSite(candidate)) title = candidate;
      }
      if (!title) {
        const candidates = [
          $('.box-info-heading h1').first().text(),
          $('h1.title').first().text(),
          $('h1').eq(1).text(),
          $('h1').first().text(),
          cleanTitle($('title').first().text()),
        ];
        for (const candidate of candidates) {
          const recovered = recoverResultTitle(candidate, magnet);
          if (recovered && recovered.length >= 3 && !_looksLikeSite(recovered)) {
            title = recovered;
            break;
          }
        }
      }
      if (title && title.length < 30 && searchQuery) {
        const kws = searchQuery.toLowerCase().split(/[\s_\-+]+/).filter((w) => w.length >= 2);
        const tl = title.toLowerCase();
        const hasKeyword = kws.length === 0 || kws.some((kw) => tl.includes(kw));
        if (!hasKeyword) title = '';
      }
      if (!title && hint) title = recoverResultTitle(hint, magnet) || '';
      if (!title || title.length < 3) title = recoverResultTitle('', magnet) || '';

      let _bodyText: string | null = null;
      const getBodyText = () => (_bodyText ??= $('body').text());

      let size = '';
      if (detailSelectors.size) size = $(detailSelectors.size).first().text().trim();
      if (!size) {
        const sizeMatch = getBodyText().match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
        if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');
      }
      if (!size) {
        const cnSize = getBodyText().match(/([\d.]+)(TB|GB|MB|KB)/i);
        if (cnSize) size = `${cnSize[1]} ${cnSize[2]}`;
      }

      let date = '';
      if (detailSelectors.date) date = $(detailSelectors.date).first().text().trim();
      if (!date) {
        const dateMatch = getBodyText().match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
        if (dateMatch) date = dateMatch[1];
      }
      if (!date) {
        const cnDate = getBodyText().match(/(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5/);
        if (cnDate) date = `${cnDate[1]}-${cnDate[2].padStart(2, '0')}-${cnDate[3].padStart(2, '0')}`;
      }

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
  };

  // Process in batches of 3 with a macrotask yield between batches.
  // Prevents N simultaneous cheerio.load() calls cascading on JS thread.
  const BATCH = 3;
  for (let i = 0; i < urlsToFetch.length && results.length < limit; i += BATCH) {
    const batch = urlsToFetch.slice(i, i + BATCH);
    const batchItems = await Promise.all(batch.map((url, j) => parseOne(url, i + j)));
    for (const items of batchItems) {
      results.push(...items);
      if (results.length >= limit) break;
    }
    // Yield to event loop between batches so UI can process scroll/touch events
    if (i + BATCH < urlsToFetch.length && !isBackgroundNetworkMode()) {
      await new Promise<void>((r) => setTimeout(r, 0));
    }
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
  const requestTimeoutMs = isBackgroundNetworkMode() ? 3_000 : 15_000;
  const sourceDeadlineAt = Date.now() + (isBackgroundNetworkMode() ? 10_000 : 18_000);
  try {
    // Step 1: GET homepage → grab session cookies (age verify no longer needed)
    const homeBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
    if (homeBudgetMs <= 0) return results;
    const r0 = await fetchTextWithTimeout(origin, {
      headers: FETCH_HEADERS,
      redirect: 'follow',
      timeoutMs: homeBudgetMs,
    });
    if (!r0) return results;
    const sessionCookies = r0.cookies;

    // Step 2: Search
    const searchUrl = `${origin}/search/${encodeURIComponent(query)}`;
    const searchBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
    if (searchBudgetMs <= 0) return results;
    const r2 = await fetchTextWithTimeout(searchUrl, {
      headers: { ...FETCH_HEADERS, Cookie: sessionCookies, Referer: origin + '/' },
      redirect: 'follow',
      timeoutMs: searchBudgetMs,
    });
    if (!r2?.ok) return results;
    const searchHtml = r2.text;
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
        const detailBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
        if (detailBudgetMs <= 0) return;
        const dResp = await fetchTextWithTimeout(dUrl, {
          headers: { ...FETCH_HEADERS, Cookie: sessionCookies },
          redirect: 'follow',
          timeoutMs: detailBudgetMs,
        });
        if (!dResp?.ok) return;
        const dHtml = dResp.text;
        const d$ = cheerio.load(dHtml);
        const pageTitle =
          d$('h3').first().text().trim() || d$('title').first().text().trim();

        const gidM = dHtml.match(/var\s+gid\s*=\s*(\d+)/);
        const ucM = dHtml.match(/var\s+uc\s*=\s*(\d+)/);
        if (!gidM) return;
        const gid = gidM[1];
        const uc = ucM ? ucM[1] : '0';

        const ajaxUrl = `${origin}/ajax/uncledatoolsbyajax.php?gid=${gid}&lang=zh&uc=${uc}&floor=${Math.floor(Math.random() * 1000 + 1)}`;
        const ajaxBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
        if (ajaxBudgetMs <= 0) return;
        const ar = await fetchTextWithTimeout(ajaxUrl, {
          headers: { ...FETCH_HEADERS, Referer: dUrl, Cookie: sessionCookies },
          timeoutMs: ajaxBudgetMs,
        });
        if (!ar?.ok) return;
        const aHtml = ar.text;
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
  } catch {}
  return results;
}

async function fetchMeijumi(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  const requestTimeoutMs = isBackgroundNetworkMode() ? 3_000 : 15_000;
  const sourceDeadlineAt = Date.now() + (isBackgroundNetworkMode() ? 10_000 : 18_000);
  try {
    const seen = new Set<string>();
    const searchUrl = `${origin}/?s=${encodeURIComponent(query)}`;

    // Step 1: GET → captcha answer in cookie
    // Use raw fetch with redirect:'follow' to get the full cookie set
    const step1BudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
    if (step1BudgetMs <= 0) return results;
    const r1 = await fetchTextWithTimeout(searchUrl, {
      headers: FETCH_HEADERS,
      redirect: 'follow',
      timeoutMs: step1BudgetMs,
    });
    if (!r1) return results;
    const cookies1 = r1.cookies;
    if (!cookies1) return results;
    // Store cookies immediately so subsequent fetches can use them
    storeCookiesForOrigin(origin, cookies1);

    const answerMatch = cookies1.match(/result=(\d+)/);
    if (!answerMatch) return results;
    const answer = answerMatch[1];

    // Step 2: POST answer (must include the result cookie from step 1)
    const step2BudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
    if (step2BudgetMs <= 0) return results;
    const r2 = await fetchTextWithTimeout(searchUrl, {
      method: 'POST',
      headers: {
        ...FETCH_HEADERS,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cookie': cookies1,
        'Referer': searchUrl,
      },
      body: `result=${answer}`,
      redirect: 'follow',
      timeoutMs: step2BudgetMs,
    });
    if (!r2) return results;
    const cookies2 = r2.cookies;
    // Merge step2 cookies with step1 and store (server sets esc_search_captcha=1)
    const mergedCookies = mergeCookies(cookies1, cookies2);
    storeCookiesForOrigin(origin, mergedCookies);

    // Step 3: GET with all captcha cookies (fetchPage reads stored cookies from cookieJar)
    const step3BudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
    if (step3BudgetMs <= 0) return results;
    const resp3 = await fetchPage(searchUrl, undefined, step3BudgetMs);
    if (!resp3.html) return results;
    const $ = cheerio.load(resp3.html);
    const detailUrls: string[] = [];

    $('a[href]').each((_: number, el: any) => {
      const href = $(el).attr('href') || '';
      if (/meijumi\.net\/\d+\.html/.test(href) && !detailUrls.includes(href)) {
        detailUrls.push(href);
      }
    });

    // Step 4: Follow detail pages (fetchPage carries stored cookies)
    const pages = detailUrls.slice(0, 8);
    const fetches = pages.map(async (dUrl) => {
      try {
        const detailBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
        if (detailBudgetMs <= 0) return;
        const dr = await fetchPage(dUrl, undefined, detailBudgetMs);
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

async function fetch6v520(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    // Step 1: POST search form (server requires gb2312 encoding for CJK queries)
    let encodedQuery: string;
    const isAscii = /^[\x20-\x7E]+$/.test(query);
    if (isAscii) {
      encodedQuery = encodeURIComponent(query);
    } else {
      try {
        const iconv = require('iconv-lite');
        const buf: Buffer = iconv.encode(query, 'gbk');
        encodedQuery = Array.from(buf).map(b => '%' + b.toString(16).toUpperCase().padStart(2, '0')).join('');
      } catch {
        encodedQuery = encodeURIComponent(query);
      }
    }
    const body = 'show=title%2Csmalltext&tempid=1&tbname=article&mid=1&classid=0&keyboard=' + encodedQuery;

    let respText = '';
    let finalUrl = '';
    if (isBackgroundNetworkMode()) {
      const stored = getStoredCookies(origin);
      const resp = await fetchPageManual(origin + '/e/search/index.php', {
        method: 'POST',
        body,
        contentType: 'application/x-www-form-urlencoded',
        cookies: stored || undefined,
        referer: origin + '/',
        timeoutMs: 15_000,
      });
      if (!resp) return results;
      respText = resp.html || '';
      finalUrl = resp.responseUrl || '';
      if (resp.cookies) storeCookiesForOrigin(origin, resp.cookies);
    } else {
      // Foreground keeps the existing redirect-follow behavior because some mirrors
      // only reveal searchid after the POST redirect chain resolves.
      const ac = new AbortController();
      const timer = setTimeout(() => ac.abort(), 15_000);
      try {
        const stored = getStoredCookies(origin);
        const headers: Record<string, string> = {
          ...FETCH_HEADERS,
          'Content-Type': 'application/x-www-form-urlencoded',
          'Referer': origin + '/',
        };
        if (stored) headers['Cookie'] = stored;
        const resp = await fetch(origin + '/e/search/index.php', {
          method: 'POST',
          headers,
          body,
          redirect: 'follow',
          signal: ac.signal,
        });
        clearTimeout(timer);
        respText = await resp.text();
        finalUrl = resp.url || '';
        const newCookies = extractCookies(resp);
        if (newCookies) storeCookiesForOrigin(origin, newCookies);
      } catch (e: any) {
        clearTimeout(timer);
        return results;
      }
    }

    // Step 2: Extract searchid from final URL (after redirect) or response body
    let searchId = '';
    if (finalUrl) {
      const m = finalUrl.match(/searchid=(\d+)/);
      if (m) searchId = m[1];
    }
    if (!searchId && respText) {
      const m = respText.match(/searchid=(\d+)/);
      if (m) searchId = m[1];
    }
    if (!searchId) return results;

    // Step 3: GET results page
    const resultResp = await fetchPage(origin + '/e/search/result/?searchid=' + searchId);
    if (!resultResp.html) return results;

    // Step 4: Extract detail links from RESULTS section only (skip navigation)
    const countIdx = resultResp.html.indexOf('项符合');
    const mainIdx = resultResp.html.indexOf('<div id="main">');
    const sliceFrom = countIdx > 0 ? countIdx : (mainIdx > 0 ? mainIdx : 0);
    const resultSection = resultResp.html.slice(sliceFrom);

    const detailUrls: string[] = [];
    const linkRe = /<a[^>]*href="\/([a-z]+\/\d{4}-\d{2}-\d{2}\/\d+\.html)"[^>]*target="?_blank"?[^>]*>/g;
    let lm: RegExpExecArray | null;
    while ((lm = linkRe.exec(resultSection)) !== null) {
      const full = origin + '/' + lm[1];
      if (!detailUrls.includes(full)) detailUrls.push(full);
    }

    // Step 5: Fetch detail pages and extract magnets
    const seen = new Set<string>();
    for (const detailUrl of detailUrls.slice(0, 10)) {
      const detailResp = await fetchPage(detailUrl);
      if (!detailResp.html) continue;
      const $d = cheerio.load(detailResp.html);

      const pageTitle = $d('title').text().replace(/[-–|].*$/, '').trim()
        || $d('h1').first().text().trim();

      $d('a[href^="magnet:"]').each((_: number, el: any) => {
        const magnet = $d(el).attr('href') || '';
        if (!magnet || seen.has(magnet)) return;
        seen.add(magnet);
        const linkText = $d(el).text().trim();
        results.push({
          title: linkText || pageTitle || query,
          magnet,
          size: '',
          date: '',
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      });
    }
  } catch {}
  return results;
}

// ── 种子帝 (zhongzidi) handler — list page + detail follow ─────────
async function fetchZhongzidi(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchUrl = `${origin}/list/${encodeURIComponent(query)}/1`;
    const resp = await fetchPage(searchUrl);
    if (!resp.html) return results;
    const $ = cheerio.load(resp.html);

    // Parse list items: each <li class="list-group-item"> has title link, size, date
    const detailUrls: string[] = [];
    const titleHints: string[] = [];
    const sizeHints: string[] = [];
    const dateHints: string[] = [];

    $('ul.list-group li').each((_: number, el: any) => {
      const item = $(el);
      const titleLink = item.find('a.text-success').first();
      const title = titleLink.text().trim();
      if (!title) return;

      const href = titleLink.attr('href') || '';
      if (href && !href.startsWith('magnet:') && !href.startsWith('#')) {
        const detailUrl = href.startsWith('http') ? href : new URL(href, origin).href;
        detailUrls.push(detailUrl);
        titleHints.push(title);
        sizeHints.push(item.find('.text-filesize').text().trim());
        dateHints.push(item.find('.text-time').text().trim());
      }
    });

    // Also check for any direct magnets on the page
    const seen = new Set<string>();
    $('a[href^="magnet:"]').each((_: number, el: any) => {
      const magnet = $(el).attr('href') || '';
      if (!magnet || seen.has(magnet)) return;
      seen.add(magnet);
      results.push({
        title: $(el).text().trim() || query,
        magnet,
        size: '',
        date: '',
        seeders: 0,
        leechers: 0,
        source: origin,
        site_name: siteName,
        score,
      });
    });

    // Follow detail pages to extract magnets
    for (let i = 0; i < Math.min(detailUrls.length, 10); i++) {
      const dUrl = detailUrls[i];
      try {
        const dr = await fetchPage(dUrl);
        if (!dr.html) continue;
        const d$ = cheerio.load(dr.html);

        const pageTitle = titleHints[i]
          || d$('h1').first().text().trim()
          || d$('title').text().replace(/[-–|].*$/, '').trim();

        d$('a[href^="magnet:"]').each((_: number, el: any) => {
          const magnet = d$(el).attr('href') || '';
          if (!magnet || seen.has(magnet)) return;
          seen.add(magnet);

          const bodyText = d$('body').text();
          let size = sizeHints[i] || '';
          if (!size) {
            const sizeMatch = bodyText.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
            if (sizeMatch) size = sizeMatch[0].replace(/iB\b/i, 'B');
          }
          let date = dateHints[i] || '';
          if (!date) {
            const dateMatch = bodyText.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
            if (dateMatch) date = dateMatch[1];
          }

          results.push({
            title: pageTitle || query,
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
    }
  } catch {}
  return results;
}

// ── BTSOW JSON API handler ─────────────────────────────────────────
async function fetchBtsow(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const body = JSON.stringify([{ search: query }, 30, 1]);
    const resp = await fetchPageManual(origin + '/bts/data/api/search', {
      method: 'POST',
      body,
      contentType: 'application/json',
    });
    if (!resp?.html) return results;

    let json: any;
    try { json = JSON.parse(resp.html); } catch { return results; }
    if (json.code !== 200 || !json.data) return results;

    const seen = new Set<string>();
    for (const item of json.data) {
      const hash: string = (item.hash || '').toUpperCase();
      if (!hash || seen.has(hash)) continue;
      seen.add(hash);
      const name: string = (item.name || '').replace(/<[^>]+>/g, '').replace(/​/g, '');
      const sizeBytes: number = item.size || 0;
      let size = '';
      if (sizeBytes > 1024 * 1024 * 1024) size = (sizeBytes / (1024 ** 3)).toFixed(2) + ' GB';
      else if (sizeBytes > 1024 * 1024) size = (sizeBytes / (1024 ** 2)).toFixed(1) + ' MB';
      results.push({
        title: name || query,
        magnet: 'magnet:?xt=urn:btih:' + hash,
        size,
        date: item.lastUpdateTime ? new Date(item.lastUpdateTime * 1000).toISOString().slice(0, 10) : '',
        seeders: 0, leechers: 0,
        source: origin, site_name: siteName, score,
      });
    }
  } catch {}
  return results;
}

// ── Snowfl meta-search JSON API handler ────────────────────────────
// Prefix rotates in /b.min.js — last verified 2026-06-11
const SNOWFL_API_PREFIX = 'phHKGSoKzgIcensvRHjReEMyHOnfLoFjSsqPHeyzMd';

async function fetchSnowfl(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const session = Math.random().toString(36).slice(2, 10);
    const url = `${origin}/${SNOWFL_API_PREFIX}/${encodeURIComponent(query)}/${session}/0/NONE/NONE/0`;
    const resp = await fetchPageManual(url, {
      method: 'GET',
      referer: origin + '/',
      extraHeaders: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!resp?.html) return results;

    let items: any[];
    try { items = JSON.parse(resp.html); } catch { return results; }
    if (!Array.isArray(items)) return results;

    const seen = new Set<string>();
    for (const item of items) {
      let magnet: string = item.magnet || '';
      magnet = magnet.replace(/\\u003d/gi, '=').replace(/\\u0026/gi, '&');
      if (!magnet || seen.has(magnet)) continue;
      seen.add(magnet);
      results.push({
        title: (item.name || query).replace(/<[^>]+>/g, ''),
        magnet,
        size: item.size || '',
        date: item.age || '',
        seeders: parseInt(item.seeder) || 0,
        leechers: parseInt(item.leecher) || 0,
        source: item.site || origin,
        site_name: siteName,
        score,
      });
    }
  } catch {}
  return results;
}

// ── YTS movie torrent handler ──────────────────────────────────────
async function fetchYts(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchResp = await fetchPage(origin + '/browse-movies/' + encodeURIComponent(query));
    if (!searchResp.html) return results;
    const $ = cheerio.load(searchResp.html);

    const detailUrls: string[] = [];
    const seen = new Set<string>();
    $('a[href*="/movie/"]').each((_: number, el: any) => {
      const href = $(el).attr('href') || '';
      if (!href.includes('/movie/')) return;
      const fullUrl = href.startsWith('http') ? href : origin + href;
      if (seen.has(fullUrl)) return;
      seen.add(fullUrl);
      detailUrls.push(fullUrl);
    });

    if (detailUrls.length === 0) return results;

    const magnetSeen = new Set<string>();
    const fetches = detailUrls.slice(0, 10).map(async (detailUrl) => {
      const { html } = await fetchPage(detailUrl);
      if (!html) return [] as ResultItem[];

      const d$ = cheerio.load(html);
      const movieTitle = d$('h1').first().text().trim() || query;
      let year = '';
      d$('h2').each((_: number, h2: any) => {
        const t = d$(h2).text().trim();
        if (/^\d{4}$/.test(t)) year = t;
      });

      const items: ResultItem[] = [];
      d$('a.download-torrent[href^="magnet:"]').each((_: number, el: any) => {
        const magnet = (d$(el).attr('href') || '').replace(/&amp;/g, '&');
        if (!magnet.startsWith('magnet:?')) return;
        const hash = extractInfoHash(magnet);
        if (!hash || magnetSeen.has(hash)) return;
        magnetSeen.add(hash);

        const quality = d$(el).text().trim();
        const title = year ? `${movieTitle} (${year}) ${quality}` : `${movieTitle} ${quality}`;
        let size = '';
        const container = d$(el).closest('div.torrent-qualities');
        if (container.length) {
          const sm = container.text().match(/([\d,.]+)\s*(TB|GB|MB|KB)/i);
          if (sm) size = sm[0];
        }
        items.push({
          title: title.trim(),
          magnet,
          size,
          date: year,
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      });
      return items;
    });

    const batches = await Promise.all(fetches);
    for (const batch of batches) results.push(...batch);
  } catch (e) {
    console.error('[fetchYts]', e);
  }
  return results;
}

// ── Wuji (无极磁链) handler ────────────────────────────────────────
async function fetchWuji(
  origin: string,
  query: string,
  siteName: string,
  score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const searchResp = await fetchPage(origin + '/search?q=' + encodeURIComponent(query));
    if (!searchResp.html) return results;
    const $ = cheerio.load(searchResp.html);

    const rows: Array<{ title: string; detailUrl: string }> = [];
    const seen = new Set<string>();
    $('a[href^="/!"]').each((_: number, el: any) => {
      const href = $(el).attr('href') || '';
      if (!href || seen.has(href)) return;
      seen.add(href);
      const title = $(el).text().trim();
      if (!title) return;
      rows.push({ title, detailUrl: origin + href });
    });

    if (rows.length === 0) return results;

    const finalResults: ResultItem[] = [];
    const fetches = rows.slice(0, 8).map(async (row) => {
      const detailResp = await fetchPage(row.detailUrl);
      if (!detailResp.html) return;
      const $d = cheerio.load(detailResp.html);
      $d('a[href^="magnet:"]').each((_: number, el: any) => {
        const magnet = ($d(el).attr('href') || '').replace(/&amp;/g, '&');
        if (!magnet.startsWith('magnet:?')) return;
        finalResults.push({
          title: row.title,
          magnet,
          size: '',
          date: '',
          seeders: 0,
          leechers: 0,
          source: origin,
          site_name: siteName,
          score,
        });
      });
    });
    await Promise.all(fetches);
    return finalResults;
  } catch (e) {
    console.error('[fetchWuji]', e);
  }
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
        const bodyText = d$('body').text();
        let detailSize = '';
        const sizeM = bodyText.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)\b/i);
        if (sizeM) detailSize = sizeM[0].replace(/iB\b/i, 'B');
        let detailDate = '';
        const dateM = bodyText.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
        if (dateM) detailDate = dateM[1];

        d$('a[href^="magnet:"]').each((_: number, el: any) => {
          const mag = d$(el).attr('href') || '';
          const hash = extractInfoHash(mag);
          if (hash && !seen.has(hash)) {
            seen.add(hash);
            results.push({
              title: title || 'Unknown Title',
              magnet: mag,
              size: normalizeSize(detailSize),
              date: cleanDate(detailDate),
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
    const seen = new Set<string>();

    // The v3 uses tier1_cloak (browser rendering) + brute-force hash extraction.
    // The App needs to use WebView verification since the site has CF protection.
    let html: string | null = null;

    // Try regular fetch first (may work if CF cookies are cached)
    const resp = await fetchPage(searchUrl);
    if (resp.challenge) {
      // CF challenge detected — use WebView verification
      if (isBackgroundNetworkMode()) {
        return [];
      }
      invalidateCookies(origin);
      const vr = await VerifyManager.requestVerification(
        searchUrl, resp.challenge.type as any, origin, siteName,
      );
      if (vr.success && vr.html) {
        if (vr.cookies) storeCookiesForOrigin(origin, vr.cookies);
        html = vr.html;
      }
    } else if (resp.html) {
      html = resp.html;
    }

    if (!html) return results;
    const $ = cheerio.load(html);

    // Try to find magnets in the search results page
    $('a[href^="magnet:"]').each((_: number, el: any) => {
      const mag = $(el).attr('href') || '';
      const hash = extractInfoHash(mag);
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

    // Follow detail pages if we have them (supports_detail: true)
    if (results.length === 0) {
      const detailUrls: string[] = [];
      $('a[href]').each((_: number, el: any) => {
        const href = $(el).attr('href') || '';
        if (href.match(/rrjav\.com\/\d+\.html/) && !detailUrls.includes(href)) {
          detailUrls.push(href.startsWith('http') ? href : new URL(href, origin).href);
        }
      });

      for (const dUrl of detailUrls.slice(0, 5)) {
        try {
          const dr = await fetchPage(dUrl);
          if (!dr.html) continue;
          const d$ = cheerio.load(dr.html);
          d$('a[href^="magnet:"]').each((_: number, el: any) => {
            const mag = d$(el).attr('href') || '';
            const hash = extractInfoHash(mag);
            if (!hash || seen.has(hash)) return;
            seen.add(hash);
            const title = d$('h1, h2, h3').first().text().trim() || extractTitleFromMagnet(mag) || 'Unknown Title';
            results.push({
              title, magnet: mag, size: '', date: '', seeders: 0, leechers: 0,
              source: origin, site_name: siteName, score,
            });
          });
        } catch {}
      }
    }
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
  const searchResult = await fetchPage(searchUrl);
  if (isBackgroundNetworkMode() && searchResult.challenge) {
    return [];
  }
  if (!searchResult.html) {
    return [];
  }

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

  if (searchRows.length === 0) return [];

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
    return [];
  }

  // 3. Follow detail pages concurrently (max 8) to extract magnet links
  const toFetch = relevant.slice(0, 8);
  const seen = new Set<string>();

  const fetches = toFetch.map(async (row) => {
    try {
      const detailResult = await fetchPage(row.detailUrl);
      if (isBackgroundNetworkMode() && detailResult.challenge) {
        return null;
      }
      const detailHtml = detailResult.html;
      if (!detailHtml) return null;

      const d$ = cheerio.load(detailHtml);
      const magnet = d$('a[href^="magnet:"]').first().attr('href') || '';
      if (!magnet.startsWith('magnet:?')) return null;

      const hash = extractInfoHash(magnet);
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
  return results;
}

/* ---- CiliMo (cilimo.com) handler: JSON API with info_hash ---- */
async function fetchCiliMo(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const url = `${origin}/api/search?q=${encodeURIComponent(query)}`;
    const resp = await fetchTextWithTimeout(url, {
      headers: { ...FETCH_HEADERS, 'Accept': 'application/json' },
      timeoutMs: 10_000,
    });
    if (!resp?.ok) return results;
    const data = JSON.parse(resp.text || '{}') as any;
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
  } catch (e: any) {
  }
  return results;
}

/* ---- CLKD / 磁力口袋 (kd705.site) handler: JSON API with hashInfo ---- */
async function fetchClkd(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const url = `${origin}/clkd/api/search?keyword=${encodeURIComponent(query)}`;
    const resp = await fetchTextWithTimeout(url, {
      headers: { ...FETCH_HEADERS, 'Accept': 'application/json' },
      timeoutMs: 10_000,
    });
    if (!resp?.ok) return results;
    const json = JSON.parse(resp.text || '{}') as any;
    const items = json.data?.list || json.list || [];
    for (const item of items.slice(0, 20)) {
      const hash = item.hashInfo || item.id;
      if (!hash) continue;
      const magnet = `magnet:?xt=urn:btih:${hash}`;
      const sizeBytes = item.torrentSize || 0;
      let size = '';
      if (sizeBytes >= 1e12) size = `${(sizeBytes / 1e12).toFixed(2)} TB`;
      else if (sizeBytes >= 1e9) size = `${(sizeBytes / 1e9).toFixed(2)} GB`;
      else if (sizeBytes >= 1e6) size = `${(sizeBytes / 1e6).toFixed(1)} MB`;
      else if (sizeBytes > 0) size = `${(sizeBytes / 1e3).toFixed(0)} KB`;

      let name = item.torrentName || extractTitleFromMagnet(magnet) || 'Unknown';
      // Clean HTML highlight tags
      name = name.replace(/<em[^>]*>/g, '').replace(/<\/em>/g, '');

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
  } catch (e: any) {
  }
  return results;
}

/* ---- LuLuTang (噜噜糖) handler: JSON API /api/search?keyword=  ---- */
async function fetchLulutang(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const url = `${origin}/api/search?keyword=${encodeURIComponent(query)}&page=1`;
    const resp = await fetchTextWithTimeout(url, {
      headers: { ...FETCH_HEADERS, 'Accept': 'application/json' },
      timeoutMs: 10_000,
    });
    if (!resp?.ok) return results;
    const json = JSON.parse(resp.text || '{}') as any;
    if (json.code !== 0) return results;
    const items: any[] = json.data || [];
    for (const item of items.slice(0, 20)) {
      const infoHash: string = item.info_hash || '';
      if (!infoHash) continue;
      // info_hash is base64url-encoded (20 raw bytes). Convert to 40-char hex for btih.
      const b64 = infoHash.replace(/-/g, '+').replace(/_/g, '/');
      const hex = (() => {
        try {
          const binary = atob(b64);
          return Array.from(binary, (c) => c.charCodeAt(0).toString(16).padStart(2, '0')).join('');
        } catch {
          return infoHash;
        }
      })();
      const magnet = `magnet:?xt=urn:btih:${hex}`;
      // Title may contain <mark> tags — strip them
      let title = (item.title || '').replace(/<\/?[^>]+>/g, '').trim();
      if (!title) title = 'Unknown';
      const sizeRaw: number = typeof item.size === 'number' ? item.size : 0;
      let size = '';
      if (sizeRaw >= 1e12) size = `${(sizeRaw / 1e12).toFixed(2)} TB`;
      else if (sizeRaw >= 1e9) size = `${(sizeRaw / 1e9).toFixed(2)} GB`;
      else if (sizeRaw >= 1e6) size = `${(sizeRaw / 1e6).toFixed(1)} MB`;
      else if (sizeRaw > 0) size = `${(sizeRaw / 1e3).toFixed(0)} KB`;
      const date = item.created_at ? String(item.created_at).slice(0, 10) : '';
      results.push({ title, magnet, size, date, seeders: 0, leechers: 0, source: origin, site_name: siteName, score });
    }
  } catch (e: any) {
  }
  return results;
}

/* ---- SSBC platform handler (磁力天堂/磁力发/磁力王 — CryptoJS+AJAX framework) ---- */
async function fetchSsbc(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  const requestTimeoutMs = isBackgroundNetworkMode() ? 3_000 : 10_000;
  const sourceDeadlineAt = Date.now() + (isBackgroundNetworkMode() ? 9_000 : 15_000);
  try {
    // Step 1: Resolve redirect (movih.com → jzciliwang123.shop, berrl.com → cltt1.shop)
    // Only the final followed URL is needed here. A prior fetchPage() call added
    // a redundant full request without contributing any data.
    let realOrigin = origin;
    try {
      const redirectBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
      if (redirectBudgetMs <= 0) return results;
      const rawResp = await fetchTextWithTimeout(origin + '/', {
        headers: FETCH_HEADERS,
        redirect: 'follow',
        timeoutMs: redirectBudgetMs,
      });
      // The final URL after redirect chain
      const finalUrl = rawResp?.finalUrl || '';
      if (finalUrl) {
        const parsed = new URL(finalUrl);
        realOrigin = parsed.origin;
      }
    } catch {}

    // Step 2: POST /api/ssbc — try resolved origin first, then original
    const origins = realOrigin !== origin ? [realOrigin, origin] : [origin];
    for (const tryOrigin of origins) {
      const apiUrl = `${tryOrigin}/api/ssbc`;
      const body = new URLSearchParams({ key: query, type: 'all', from: '1' });

      // Use raw fetch with redirect:'follow' to avoid fetchPageManual issues
      let respText = '';
      try {
        const apiBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, requestTimeoutMs);
        if (apiBudgetMs <= 0) break;
        const rawResp = await fetchTextWithTimeout(apiUrl, {
          method: 'POST',
          headers: {
            ...FETCH_HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': tryOrigin + '/',
          },
          body: body.toString(),
          redirect: 'follow',
          timeoutMs: apiBudgetMs,
        });
        respText = rawResp?.text || '';
      } catch {
        continue;
      }

      if (!respText) continue;

      // Step 3: Parse JSON response
      let json: any;
      try { json = JSON.parse(respText); } catch { continue; }
      if (json.code !== 200) continue;

      const torrents: any[] = json.data?.infos?.torrent || [];
      const seen = new Set<string>();

      for (const t of torrents) {
        const infohash: string = t.infohash || t.infohash_IK || '';
        if (!infohash || seen.has(infohash)) continue;
        seen.add(infohash);

        const magnet = `magnet:?xt=urn:btih:${infohash}`;
        let name: string = t.name_simple || t.name_IK || '';
        name = name.replace(/<[^>]+>/g, '');

        const sizeBytes = parseInt(t.size, 10) || 0;
        let size = '';
        if (sizeBytes >= 1e12) size = `${(sizeBytes / 1e12).toFixed(2)} TB`;
        else if (sizeBytes >= 1e9) size = `${(sizeBytes / 1e9).toFixed(2)} GB`;
        else if (sizeBytes >= 1e6) size = `${(sizeBytes / 1e6).toFixed(1)} MB`;
        else if (sizeBytes > 0) size = `${(sizeBytes / 1e3).toFixed(0)} KB`;

        const date = t.createdate || '';

        results.push({
          title: name || query, magnet, size, date,
          seeders: 0, leechers: 0, source: origin, site_name: siteName, score,
        });
      }
      break; // Success — don't try other origins
    }
  } catch {}
  return results;
}

/* ---- ThatCDN platform handler (磁力熊猫/磁力柠檬/吴签/老王 family) ---- *
 * Reverse-engineered captcha bypass: POST to /anti/recaptcha/v4/gen + verify.
 * Mirrors crawler_v3/handlers/thatcdn.py logic exactly.
 */
async function fetchThatCdn(
  origin: string, query: string, siteName: string, score: number,
): Promise<ResultItem[]> {
  const results: ResultItem[] = [];
  try {
    const TIMEOUT_MS = isBackgroundNetworkMode() ? 8_000 : 25_000;
    const sourceDeadlineAt = Date.now() + (isBackgroundNetworkMode() ? 12_000 : 25_000);
    const baseHdr = { ...FETCH_HEADERS };

    // Step 1: Resolve rdata redirect (xiongmaogb.top → xiongmaoqv.top, etc.)
    let realOrigin = origin.replace(/\?.*$/, '').replace(/\/$/, '');
    try {
      const homeBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, TIMEOUT_MS);
      if (homeBudgetMs <= 0) return results;
      const homeResp = await fetchTextWithTimeout(realOrigin + '/', {
        headers: baseHdr,
        redirect: 'follow',
        timeoutMs: homeBudgetMs,
      });
      const homeHtml = homeResp?.text || '';
      const rdataM = homeHtml.match(/<meta[^>]*name=["']rdata["'][^>]*content=["']([^"']+)["']/i);
      if (rdataM) {
        const reversed = rdataM[1].split('').reverse().join('');
        const decoded = Buffer.from(reversed, 'base64').toString('utf-8');
        const data = JSON.parse(decoded) as { urls?: string[] };
        if (data.urls?.length) realOrigin = data.urls[0].replace(/\/$/, '');
      }
    } catch {}

    // Step 2: Initial search request — may return captcha challenge or results directly
    // RN native fetch auto-manages cookie jar (JSESSIONID set here, fct set after verify)
    const searchUrl = `${realOrigin}/search?keyword=${encodeURIComponent(query)}`;
    const searchBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, TIMEOUT_MS);
    if (searchBudgetMs <= 0) return results;
    const s1 = await fetchTextWithTimeout(searchUrl, {
      headers: { ...baseHdr, Referer: realOrigin + '/' },
      redirect: 'follow',
      timeoutMs: searchBudgetMs,
    });
    let searchHtml = s1?.text || '';

    // Step 3: Captcha bypass (auto-solvable API token flow — no user interaction needed)
    if (/challenge|recaptcha/i.test(searchHtml.slice(0, 4000))) {
      const uid = Math.random().toString(36).slice(2, 12) + '_' + Date.now();

      // 3a: Fetch token from gen endpoint (cookie jar auto-included by native fetch)
      const genBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, TIMEOUT_MS);
      if (genBudgetMs <= 0) return results;
      const genResp = await fetchTextWithTimeout(
        `${realOrigin}/anti/recaptcha/v4/gen?aywcUid=${encodeURIComponent(uid)}&_=${Date.now()}`,
        {
          headers: { ...baseHdr, Referer: searchUrl },
          timeoutMs: genBudgetMs,
        },
      );
      const genData = JSON.parse(genResp?.text || '{}') as { errno?: number; token?: string };
      if (genData?.errno !== 0 || !genData?.token) {
        return results;
      }

      // 3b: Submit verify — server returns search-results HTML and sets fct cookie
      const costtime = 3000 + Math.floor(Math.random() * 2000);
      const verifyBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, TIMEOUT_MS);
      if (verifyBudgetMs <= 0) return results;
      const verifyResp = await fetchTextWithTimeout(
        `${realOrigin}/anti/recaptcha/v4/verify?token=${encodeURIComponent(genData.token)}&aywcUid=${encodeURIComponent(uid)}&costtime=${costtime}`,
        {
          headers: { ...baseHdr, Referer: searchUrl },
          redirect: 'follow',
          timeoutMs: verifyBudgetMs,
        },
      );
      searchHtml = verifyResp?.text || '';
      if (searchHtml.length < 3000) { return results; }
    }

    // Step 4: Parse search results — each result is h3.panel-title > a[href^=/detail/]
    const $s = cheerio.load(searchHtml);
    const detailLinks: { url: string; title: string }[] = [];
    $s('h3.panel-title a[href]').each((_, el) => {
      const href = $s(el).attr('href') || '';
      const title = $s(el).text().replace(/<[^>]+>/g, '').trim();
      if (href.startsWith('/detail/') && title && title.length > 1) {
        detailLinks.push({ url: `${realOrigin}${href}`, title });
      }
    });

    if (detailLinks.length === 0) { return results; }

    // Step 5: Parallel detail-page fetch to extract magnet URIs (max 8)
    const MAGNET_RE = /magnet:\?xt=urn:btih:[A-Za-z0-9]{32,}/i;
    const limit = Math.min(detailLinks.length, 8);
    const fetched = await Promise.allSettled(
      detailLinks.slice(0, limit).map(async ({ url, title: listTitle }) => {
        const detailBudgetMs = getRemainingSourceBudget(sourceDeadlineAt, TIMEOUT_MS);
        if (detailBudgetMs <= 0) return null;
        const r = await fetchTextWithTimeout(url, {
          headers: { ...baseHdr, Referer: searchUrl },
          timeoutMs: detailBudgetMs,
        });
        const html = r?.text || '';
        const m = html.match(MAGNET_RE);
        if (!m) return null;
        const $d = cheerio.load(html);
        const detailTitle = [
          $d('h1').first().text(),
          $d('h2').first().text(),
          $d('meta[property="og:title"]').attr('content') || '',
          $d('title').first().text(),
          listTitle,
        ]
          .map((candidate) => recoverResultTitle(candidate, m[0]))
          .find((candidate): candidate is string => !!candidate);
        return { title: detailTitle || listTitle, magnet: m[0] };
      }),
    );

    const seen = new Set<string>();
    for (const r of fetched) {
      if (r.status !== 'fulfilled' || !r.value) continue;
      const hash = extractInfoHash(r.value.magnet) || r.value.magnet;
      if (seen.has(hash)) continue;
      seen.add(hash);
      results.push({
        title: r.value.title,
        magnet: r.value.magnet,
        size: '',
        date: '',
        seeders: 0,
        leechers: 0,
        source: origin,
        site_name: siteName,
        score,
      });
    }
  } catch {}
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
    throw new Error('__blacklisted__');
  }

  const siteName = rule.site.name;
  const score = rule.quality?.score ?? 50;
  const handler = rule.search.handler || '';

  // ── Custom handler dispatch (before template/selectors — handler-only rules omit parse_metadata) ──
  if (handler === 'javbus') return finalizeSearchResults(await fetchJavBus(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'meijumi') return finalizeSearchResults(await fetchMeijumi(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'yhg') return finalizeSearchResults(await fetchYhg(origin, query, siteName, score)).slice(0, 30);
  if (handler === '6v520') return finalizeSearchResults(await fetch6v520(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'rarbggo') return finalizeSearchResults(await fetchRarbggo(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'rrjav') return finalizeSearchResults(await fetchRrjav(origin, query, siteName, score)).slice(0, 30);
  if (handler === '1337x') return finalizeSearchResults(await fetch1337x(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'cilimo') return finalizeSearchResults(await fetchCiliMo(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'clkd') return finalizeSearchResults(await fetchClkd(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'lulutang') return finalizeSearchResults(await fetchLulutang(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'btsow') return finalizeSearchResults(await fetchBtsow(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'snowfl') return finalizeSearchResults(await fetchSnowfl(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'yts') return finalizeSearchResults(await fetchYts(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'wuji') return finalizeSearchResults(await fetchWuji(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'ssbc') return finalizeSearchResults(await fetchSsbc(origin, query, siteName, score)).slice(0, 30);
  if (handler === 'thatcdn') return finalizeSearchResults(await fetchThatCdn(origin, query, siteName, score)).slice(0, 20);
  if (handler === 'zhongzidi') return finalizeSearchResults(await fetchZhongzidi(origin, query, siteName, score)).slice(0, 20);

  // ── Template flow ──
  const template = rule.search.request_template;
  // Build search URL: {query} → URL-encoded, {query_b64} → base64-encoded
  const queryB64 = typeof btoa === 'function'
    ? btoa(unescape(encodeURIComponent(query)))
    : Buffer.from(query, 'utf-8').toString('base64');
  const queryB64url = queryB64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const searchUrl =
    origin +
    template
      .replace('{query}', encodeURIComponent(query))
      .replace('{query_b64}', queryB64)
      .replace('{query_b64url}', queryB64url);
  const selectors = rule.search.parse_metadata?.selectors;
  if (!selectors) {
    return [];
  }
  const supportsDetail = rule.capabilities?.supports_detail ?? false;
  const detailSelectors = rule.search.detail?.selectors
    ? { ...rule.search.detail.selectors }
    : undefined;
  // 1337x override
  if (/1337x|1377x/i.test(origin) && detailSelectors) {
    detailSelectors.title = '.box-info-heading h1';
  }
  const customReferer = rule.search.referer || '';

  // ── SPA sources: render via WebView (like Legado's BackstageWebView) ──
  if (rule.search.requires_browser) {
    if (isBackgroundNetworkMode()) {
      return [];
    }
    const vr = await VerifyManager.requestVerification(
      searchUrl, 'spa_render', origin, siteName,
    );
    if (vr.success && vr.html) {
      // Store any cookies from the WebView session
      if (vr.cookies) storeCookiesForOrigin(origin, vr.cookies);
      const $ = cheerio.load(vr.html);
      const {
        results: spaResults,
        detailUrls: spaDetailUrls,
        titleHints: spaTH,
        sizeHints: spaSH,
        dateHints: spaDH,
        unboundEvidenceCount: spaUnboundEvidenceCount,
      } = extractFromSearchPage($, selectors, origin, siteName, score);
      let spaHadHashPlaceholder = spaUnboundEvidenceCount > 0
        || spaResults.some((r) => isHashPlaceholderTitle(r.title, r.magnet));
      const spaCleaned = spaResults.flatMap((r) => {
        const recoveredTitle = resolveResultTitle(r.title, r.magnet);
        return recoveredTitle && recoveredTitle.length >= 4 ? [{ ...r, title: recoveredTitle }] : [];
      });
      // Follow detail pages if needed
      if (supportsDetail && detailSelectors && spaDetailUrls.length > 0 && spaCleaned.length < 20) {
        const spaDetailResults = await fetchDetailResults(
          spaDetailUrls, detailSelectors, origin, siteName, score,
          20 - spaCleaned.length, spaTH, spaSH, spaDH, query,
        );
        if (spaDetailResults.some((r) => isHashPlaceholderTitle(r.title, r.magnet))) {
          spaHadHashPlaceholder = true;
        }
        spaCleaned.push(...spaDetailResults.flatMap((r) => {
          const recoveredTitle = resolveResultTitle(r.title, r.magnet);
          return recoveredTitle && recoveredTitle.length >= 4 ? [{ ...r, title: recoveredTitle }] : [];
        }));
      }
      if (spaCleaned.length === 0 && spaHadHashPlaceholder) {
        throw new Error('INVALID_RESULT_TITLE_PARSE');
      }
      return finalizeSearchResults(spaCleaned).slice(0, 30);
    }
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
      if (isBackgroundNetworkMode()) {
        return [];
      }
      // Old cookies didn't work → invalidate so fresh ones get persisted
      invalidateCookies(origin);
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
        return [];
      }
    } else {
      html = result.html;
    }
  }

  if (!html || html.trim().length === 0) {
    throw new Error('EMPTY_SEARCH_RESPONSE');
  }

  const structured = parseStructuredSearchPayload(html, origin, siteName, score);
  if (structured.parsed) {
    if (structured.results.length === 0 && structured.unresolvedHashCount > 0) {
      throw new Error('INVALID_RESULT_TITLE_PARSE');
    }
    return finalizeSearchResults(structured.results).slice(0, 30);
  }

  const $ = cheerio.load(html);
  const {
    results,
    detailUrls,
    titleHints,
    sizeHints,
    dateHints,
    unboundEvidenceCount,
  } = extractFromSearchPage($, selectors, origin, siteName, score);

  // Filter garbage — also reject titles that are just known site names.
  // Hash-only rows are excluded before deciding whether detail pages need to
  // be followed, otherwise a page full of hashes would incorrectly look full.
  const _normT = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  let hadHashPlaceholder = unboundEvidenceCount > 0
    || results.some((r) => isHashPlaceholderTitle(r.title, r.magnet));
  const cleaned = results.flatMap((r) => {
    const recoveredTitle = resolveResultTitle(r.title, r.magnet);
    if (!recoveredTitle || recoveredTitle.length < 4) return [];
    return [{ ...r, title: recoveredTitle }];
  }).filter((r) => {
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
          url.includes(extractInfoHash(r.magnet) || '__none__'),
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
      if (detailResults.some((r) => isHashPlaceholderTitle(r.title, r.magnet))) {
        hadHashPlaceholder = true;
      }
      detailCleaned = detailResults.flatMap((r) => {
        const recoveredTitle = resolveResultTitle(r.title, r.magnet);
        if (!recoveredTitle || recoveredTitle.length < 4) return [];
        return [{ ...r, title: recoveredTitle }];
      }).filter((r) => {
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
    const hash = extractInfoHash(r.magnet) || r.magnet;
    if (seen.has(hash)) return false;
    seen.add(hash);
    return true;
  });

  if (merged.length === 0 && hadHashPlaceholder) {
    throw new Error('INVALID_RESULT_TITLE_PARSE');
  }
  return finalizeSearchResults(merged).slice(0, 20);
}
