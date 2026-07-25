import { isBlockedContent } from './complianceConfig';
import { searchSource } from './searchEngine';
import { recordSourceRun, getSourcePerfBoost } from './sourceStats';
import type { SearchSourceRollup } from './analytics';
import { startReport, type ResultItemLog, type SearchReport } from './searchDebugLogger';
import { computeRelevance, type SearchResult } from './types';
import { VerifyManager } from './VerifyManager';
import { isBackgroundNetworkMode } from './httpClient';

export interface SearchRunnerOptions {
  term: string;
  sources: any[];
  shouldAbort?: () => boolean;
  onItems?: (items: SearchResult[]) => void;
  onProgress?: (doneCount: number, sourceCount: number) => void;
  backgroundMode?: boolean;
}

export interface SearchRunnerResult {
  results: SearchResult[];
  report: SearchReport;
  aborted: boolean;
  sourceCount: number;
  doneCount: number;
  analytics: {
    durationMs: number;
    timeToFirstResultMs: number | null;
    sourceRollup: SearchSourceRollup[];
  };
}

const CONCURRENCY = 8;
const BROWSER_CONCURRENCY = 4;
const FAST_HTTP_TIMEOUT_MS = 6_000;
const TAIL_HTTP_TIMEOUT_MS = 8_000;
const BROWSER_TIMEOUT_MS = 10_000;
const FAST_STAGE_LIMIT = 12;

function classifySourceCategory(rule: any): string {
  const tags = Array.isArray(rule?.quality?.tags) ? rule.quality.tags.join(' ').toLowerCase() : '';
  const name = `${rule?.site?.name || ''} ${rule?.site?.origin || ''}`.toLowerCase();
  const bag = `${tags} ${name}`;
  if (/(anime|nyaa|acg|bangumi|mikan)/.test(bag)) return 'anime';
  if (/(movie|film|bluray|yts)/.test(bag)) return 'movie';
  if (/(tv|show|series|meiju)/.test(bag)) return 'tv';
  if (/(game|switch|ps5|xbox)/.test(bag)) return 'game';
  if (/(software|app|windows|mac|android|linux)/.test(bag)) return 'software';
  if (/(adult|porn|av)/.test(bag)) return 'adult';
  return 'general';
}

function getSpeedTier(rule: any): number {
  if (rule.search?.requires_browser) return 2;
  if (VerifyManager.isVerifyOrigin(rule.site?.origin)) return 2;
  if (rule.capabilities?.supports_detail) return 1;
  if (rule.search?.requires_csrf) return 1;
  const handler = rule.search?.handler || '';
  if (handler && handler !== 'std') return 1;
  return 0;
}

function getBackgroundSpeedTier(rule: any): number {
  if (rule.search?.requires_browser) return 4;
  if (VerifyManager.isVerifyOrigin(rule.site?.origin)) return 4;
  const handler = rule.search?.handler || '';
  if (handler && handler !== 'std') return 3;
  if (rule.capabilities?.supports_detail) return 2;
  if (rule.search?.requires_csrf) return 1;
  return 0;
}

export async function runSearchTask({
  term,
  sources,
  shouldAbort,
  onItems,
  onProgress,
  backgroundMode,
}: SearchRunnerOptions): Promise<SearchRunnerResult> {
  const noJsTimers = backgroundMode ?? isBackgroundNetworkMode();
  const allSources = [...sources].sort((a, b) => {
    const aTier = noJsTimers ? getBackgroundSpeedTier(a) : getSpeedTier(a);
    const bTier = noJsTimers ? getBackgroundSpeedTier(b) : getSpeedTier(b);
    if (aTier !== bTier) return aTier - bTier;
    const perfDelta = getSourcePerfBoost(b) - getSourcePerfBoost(a);
    if (perfDelta !== 0) return perfDelta;
    const aScore = (a as any).quality?.score ?? 50;
    const bScore = (b as any).quality?.score ?? 50;
    return bScore - aScore;
  });

  const debugReport = startReport(term, allSources.length);
  const rawResults: SearchResult[] = [];
  let doneCount = 0;
  const startedAt = Date.now();
  let timeToFirstResultMs: number | null = null;
  const sourceRollup: SearchSourceRollup[] = [];

  const aborted = () => !!shouldAbort?.();

  let cursor = 0;
  const runNext = async (bucket: any[], timeoutMs?: number): Promise<void> => {
    while (cursor < bucket.length && !aborted()) {
      const idx = cursor++;
      const rule = bucket[idx];
      const srcName = (rule as any).site?.name || 'unknown';
      const srcOrigin = (rule as any).site?.origin || '';
      const srcQuality = (rule as any).quality?.score ?? 0;
      const srcWaf = !!(rule as any).search?.requires_waf_bypass;
      const srcBrowser = !!(rule as any).search?.requires_browser;

      const srcHost = srcOrigin
        ? (() => {
            try {
              return new URL(srcOrigin).hostname;
            } catch {
              return srcName;
            }
          })()
        : srcName;

      const t0 = Date.now();
      if (noJsTimers) {
        console.log(`[BackgroundSearch] source start name=${srcName} host=${srcHost}`);
      }
      try {
        const searchPromise = searchSource(rule as any, term);
        const items = timeoutMs
          ? await Promise.race([
            searchPromise,
            new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs)),
          ])
          : await searchPromise;
        const elapsed = Date.now() - t0;
        recordSourceRun(rule, { ok: true, count: items.length, ms: elapsed });
        sourceRollup.push({
          src: srcHost,
          cat: classifySourceCategory(rule),
          called: 1,
          ok: items.length > 0 ? 1 : 0,
          empty: items.length > 0 ? 0 : 1,
          fail: 0,
          results: items.length,
          hit_searches: items.length > 0 ? 1 : 0,
          ms: elapsed,
          verify: VerifyManager.isVerifyOrigin(srcOrigin) ? 1 : 0,
        });
        const itemLogs: ResultItemLog[] = items.map((r) => ({
          title: r.title,
          hash: (r.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 16),
          size: r.size || '',
          relevance: computeRelevance(r.title, term),
        }));
        debugReport.recordSource(
          srcName,
          srcOrigin,
          items.length > 0 ? 'ok' : 'empty',
          items.length,
          elapsed,
          {
            sampleTitles: items.slice(0, 3).map((r) => r.title),
            sampleHashes: items
              .slice(0, 3)
              .map((r) => (r.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 12)),
            items: itemLogs,
            requiresWaf: srcWaf,
            requiresBrowser: srcBrowser,
            qualityScore: srcQuality,
          },
        );
        if (noJsTimers) {
          console.log(
            `[BackgroundSearch] source done name=${srcName} status=${items.length > 0 ? 'ok' : 'empty'} count=${items.length} ms=${elapsed}`,
          );
        }
        if (items.length > 0 && !aborted()) {
          if (timeToFirstResultMs === null) {
            timeToFirstResultMs = Date.now() - startedAt;
          }
          const mapped: SearchResult[] = items
            .filter((r) => !isBlockedContent(r.title))
            .map((r) => ({
              title: r.title,
              magnet: r.magnet,
              size: r.size,
              date: r.date,
              score: r.score,
              seeders: r.seeders,
              leechers: r.leechers,
              source: r.source,
              site_name: r.site_name,
            }));
          rawResults.push(...mapped);
          onItems?.(mapped);
        }
        if (!noJsTimers) {
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
        }
      } catch (err: any) {
        const elapsed = Date.now() - t0;
        const msg = err?.message || 'unknown';
        const isBlacklisted = msg === '__blacklisted__';
        const challengeLike = /challenge|captcha|cloudflare|verify/i.test(msg);
        recordSourceRun(rule, { ok: false, count: 0, ms: elapsed, challenge: challengeLike });
        sourceRollup.push({
          src: srcHost,
          cat: classifySourceCategory(rule),
          called: 1,
          ok: 0,
          empty: 0,
          fail: 1,
          results: 0,
          hit_searches: 0,
          ms: elapsed,
          verify: VerifyManager.isVerifyOrigin(srcOrigin) ? 1 : 0,
        });
        debugReport.recordSource(
          srcName,
          srcOrigin,
          isBlacklisted ? 'skipped' : elapsed > 9000 ? 'timeout' : 'error',
          0,
          elapsed,
          {
            error: isBlacklisted ? 'blacklisted (session)' : msg,
            requiresWaf: srcWaf,
            requiresBrowser: srcBrowser,
            qualityScore: srcQuality,
          },
        );
        if (noJsTimers) {
          console.log(
            `[BackgroundSearch] source done name=${srcName} status=${isBlacklisted ? 'skipped' : elapsed > 9000 ? 'timeout' : 'error'} count=0 ms=${elapsed} error=${msg}`,
          );
        }
      } finally {
        doneCount++;
        onProgress?.(doneCount, allSources.length);
      }
      if (!noJsTimers) {
        await new Promise<void>((resolve) => setTimeout(resolve, 0));
      }
    }
  };

  const httpSources = allSources.filter((s) => {
    const tier = getSpeedTier(s);
    return tier === 0 || tier === 1;
  });
  const fastHttpSources = httpSources.slice(0, FAST_STAGE_LIMIT);
  const tailHttpSources = httpSources.slice(FAST_STAGE_LIMIT);
  const browserSources = allSources.filter((s) => getSpeedTier(s) === 2);

  onProgress?.(doneCount, allSources.length);
  cursor = 0;
  await Promise.allSettled(
    Array.from(
      { length: Math.min(CONCURRENCY, fastHttpSources.length) },
      () => runNext(fastHttpSources, FAST_HTTP_TIMEOUT_MS),
    ),
  );

  if (tailHttpSources.length > 0 && !aborted()) {
    cursor = 0;
    await Promise.allSettled(
      Array.from({ length: Math.min(CONCURRENCY, tailHttpSources.length) }, () => runNext(tailHttpSources, TAIL_HTTP_TIMEOUT_MS)),
    );
  }

  if (browserSources.length > 0 && !aborted()) {
    cursor = 0;
    await Promise.allSettled(
      Array.from({ length: Math.min(BROWSER_CONCURRENCY, browserSources.length) }, () => runNext(browserSources, BROWSER_TIMEOUT_MS)),
    );
  }

  return {
    results: rawResults,
    report: debugReport.finish(),
    aborted: aborted(),
    sourceCount: allSources.length,
    doneCount,
    analytics: {
      durationMs: Date.now() - startedAt,
      timeToFirstResultMs,
      sourceRollup,
    },
  };
}
