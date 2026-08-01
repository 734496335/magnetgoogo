import { isBlockedContent } from './complianceConfig';
import { searchSource } from './searchEngine';
import { recordSourceRun, getSourcePerfBoost } from './sourceStats';
import type { SearchSourceRollup } from './analytics';
import { startReport, type ResultItemLog, type SearchReport } from './searchDebugLogger';
import { computeRelevance, type SearchResult } from './types';
import { VerifyManager } from './VerifyManager';
import { isBackgroundNetworkMode } from './httpClient';
import {
  buildSourcePoolPlans,
  getSourcePoolKey,
  splitPoolStages,
  summarizeSourceQuality,
  type SourcePoolPlan,
} from './searchQuality';

export interface SearchRunnerProgress {
  doneHostCount: number;
  scheduledHostCount: number;
  completedPoolCount: number;
  scheduledPoolCount: number;
  totalPoolCount: number;
  elapsedMs: number;
}

export interface SearchRunnerOptions {
  term: string;
  sources: any[];
  shouldAbort?: () => boolean;
  onItems?: (items: SearchResult[]) => void;
  onProgress?: (doneCount: number, sourceCount: number, progress: SearchRunnerProgress) => void;
  backgroundMode?: boolean;
  exhaustive?: boolean;
  ignoreLocalLearning?: boolean;
  sourceMeta?: {
    count?: number;
    remoteUrl?: string;
    updatedAt?: string;
    issuedAt?: string;
    expiresAt?: string;
  } | null;
}

export interface SearchRunnerResult {
  results: SearchResult[];
  report: SearchReport;
  aborted: boolean;
  sourceCount: number;
  doneCount: number;
  hostCount: number;
  poolCount: number;
  completedPoolCount: number;
  totalPoolCount: number;
  stopReason: 'exhausted' | 'aborted';
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

function sourceHost(rule: any): string {
  const srcName = rule?.site?.name || 'unknown';
  const srcOrigin = rule?.site?.origin || '';
  if (!srcOrigin) return srcName;
  try {
    return new URL(srcOrigin).hostname;
  } catch {
    return srcName;
  }
}

export async function runSearchTask({
  term,
  sources,
  shouldAbort,
  onItems,
  onProgress,
  backgroundMode,
  exhaustive = false,
  ignoreLocalLearning = false,
  sourceMeta,
}: SearchRunnerOptions): Promise<SearchRunnerResult> {
  const noJsTimers = backgroundMode ?? isBackgroundNetworkMode();
  const allSources = [...sources].sort((a, b) => {
    const aTier = noJsTimers ? getBackgroundSpeedTier(a) : getSpeedTier(a);
    const bTier = noJsTimers ? getBackgroundSpeedTier(b) : getSpeedTier(b);
    if (noJsTimers && aTier !== bTier) return aTier - bTier;

    // Foreground HTTP tiers are a latency hint, not an absolute wall. A fast
    // but irrelevant parser must not displace a slightly heavier source that
    // reliably satisfies the query in the first wave.
    const aPriority = getSourcePerfBoost(a, term, ignoreLocalLearning) - aTier * 6;
    const bPriority = getSourcePerfBoost(b, term, ignoreLocalLearning) - bTier * 6;
    const perfDelta = bPriority - aPriority;
    if (perfDelta !== 0) return perfDelta;
    const aScore = (a as any).quality?.score ?? 50;
    const bScore = (b as any).quality?.score ?? 50;
    return bScore - aScore;
  });

  const loadedPoolCount = new Set(allSources.map((source) => getSourcePoolKey(source))).size;
  const allPoolPlans = exhaustive
    ? allSources.map((source) => ({ poolId: getSourcePoolKey(source), candidates: [source] }))
    : buildSourcePoolPlans(allSources);
  const httpPoolPlans = allPoolPlans.filter((plan) => getSpeedTier(plan.candidates[0]) < 2);
  const browserPoolPlans = allPoolPlans.filter((plan) => getSpeedTier(plan.candidates[0]) === 2);
  const httpStages = splitPoolStages(httpPoolPlans);
  const totalPoolCount = exhaustive ? loadedPoolCount : allPoolPlans.length;

  const debugReport = startReport(term, 0, {
    benchmarkMode: exhaustive,
    coldStartMode: ignoreLocalLearning,
    loadedHostCount: allSources.length,
    loadedPoolCount,
    sourcePackCount: sourceMeta?.count ?? sources.length,
    sourcePackOrigin: sourceMeta?.remoteUrl || '',
    sourcePackUpdatedAt: sourceMeta?.updatedAt || '',
    sourcePackIssuedAt: sourceMeta?.issuedAt || '',
    sourcePackExpiresAt: sourceMeta?.expiresAt || '',
  });
  const rawResults: SearchResult[] = [];
  const scheduledPoolIds = new Set<string>();
  const completedPoolIds = new Set<string>();
  let doneCount = 0;
  let scheduledCount = 0;
  const startedAt = Date.now();
  let timeToFirstResultMs: number | null = null;
  const sourceRollup: SearchSourceRollup[] = [];

  const aborted = () => !!shouldAbort?.();
  const publishProgress = () => {
    debugReport.setTotalSources(scheduledCount);
    onProgress?.(doneCount, scheduledCount, {
      doneHostCount: doneCount,
      scheduledHostCount: scheduledCount,
      completedPoolCount: completedPoolIds.size,
      scheduledPoolCount: scheduledPoolIds.size,
      totalPoolCount,
      elapsedMs: Date.now() - startedAt,
    });
  };

  type AttemptOutcome = 'success' | 'empty' | 'failed';

  const runSource = async (rule: any, poolId: string, timeoutMs: number): Promise<AttemptOutcome> => {
    const srcName = rule?.site?.name || 'unknown';
    const srcOrigin = rule?.site?.origin || '';
    const srcQuality = rule?.quality?.score ?? 0;
    const srcWaf = !!rule?.search?.requires_waf_bypass;
    const srcBrowser = !!rule?.search?.requires_browser;
    const srcHost = sourceHost(rule);
    const t0 = Date.now();

    if (noJsTimers) {
      console.log(`[BackgroundSearch] source start name=${srcName} host=${srcHost} pool=${poolId}`);
    }

    try {
      const searchPromise = searchSource(rule, term);
      const items = timeoutMs
        ? await Promise.race([
          searchPromise,
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs)),
        ])
        : await searchPromise;
      const elapsed = Date.now() - t0;
      const usableItems = items.filter((item) => !isBlockedContent(item.title));
      const qualitySummary = summarizeSourceQuality(usableItems, term, computeRelevance);
      const orderedUniqueItems = [...qualitySummary.uniqueItems].sort((a, b) => b.relevance - a.relevance);
      const mapped: SearchResult[] = orderedUniqueItems.map(({ item }) => ({
        title: item.title,
        magnet: item.magnet,
        size: item.size,
        date: item.date,
        fileCount: item.fileCount,
        score: item.score,
        seeders: item.seeders,
        leechers: item.leechers,
        source: item.source,
        site_name: item.site_name,
      }));

      if (!exhaustive) {
        recordSourceRun(rule, {
          ok: true,
          count: mapped.length,
          ms: elapsed,
          query: term,
          uniqueCount: qualitySummary.uniqueResultCount,
          relevantCount: qualitySummary.relevantResultCount,
          relevancePrecision: qualitySummary.relevancePrecision,
        });
      }
      sourceRollup.push({
        src: srcHost,
        cat: classifySourceCategory(rule),
        pool: poolId,
        called: 1,
        ok: mapped.length > 0 ? 1 : 0,
        empty: mapped.length > 0 ? 0 : 1,
        fail: 0,
        results: mapped.length,
        unique_results: qualitySummary.uniqueResultCount,
        relevant_results: qualitySummary.relevantResultCount,
        relevant_precision: Math.round(qualitySummary.relevancePrecision * 100),
        hit_searches: mapped.length > 0 ? 1 : 0,
        ms: elapsed,
        verify: VerifyManager.isVerifyOrigin(srcOrigin) ? 1 : 0,
      });
      const itemLogs: ResultItemLog[] = orderedUniqueItems.map(({ item, relevance }) => ({
        title: item.title,
        hash: (item.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 16),
        size: item.size || '',
        date: item.date || '',
        fileCount: item.fileCount,
        relevance,
      }));
      debugReport.recordSource(
        srcName,
        srcOrigin,
        mapped.length > 0 ? 'ok' : 'empty',
        mapped.length,
        elapsed,
        {
          sampleTitles: mapped.slice(0, 3).map((item) => item.title),
          sampleHashes: mapped
            .slice(0, 3)
            .map((item) => (item.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 12)),
          items: itemLogs,
          requiresWaf: srcWaf,
          requiresBrowser: srcBrowser,
          qualityScore: srcQuality,
          poolId,
          uniqueResultCount: qualitySummary.uniqueResultCount,
          relevantResultCount: qualitySummary.relevantResultCount,
          relevancePrecision: qualitySummary.relevancePrecision,
        },
      );

      if (noJsTimers) {
        console.log(
          `[BackgroundSearch] source done name=${srcName} status=${mapped.length > 0 ? 'ok' : 'empty'} count=${mapped.length} relevant=${qualitySummary.relevantResultCount} ms=${elapsed}`,
        );
      }

      if (mapped.length > 0 && !aborted()) {
        if (timeToFirstResultMs === null) timeToFirstResultMs = Date.now() - startedAt;
        rawResults.push(...mapped);
        onItems?.(mapped);
      }

      if (!noJsTimers) await new Promise<void>((resolve) => setTimeout(resolve, 0));
      return mapped.length > 0 ? 'success' : 'empty';
    } catch (err: any) {
      const elapsed = Date.now() - t0;
      const msg = err?.message || 'unknown';
      const isBlacklisted = msg === '__blacklisted__';
      const challengeLike = /challenge|captcha|cloudflare|verify/i.test(msg);
      if (!exhaustive) {
        recordSourceRun(rule, {
          ok: false,
          count: 0,
          ms: elapsed,
          query: term,
          relevantCount: 0,
          relevancePrecision: 0,
          challenge: challengeLike,
        });
      }
      sourceRollup.push({
        src: srcHost,
        cat: classifySourceCategory(rule),
        pool: poolId,
        called: 1,
        ok: 0,
        empty: 0,
        fail: 1,
        results: 0,
        unique_results: 0,
        relevant_results: 0,
        relevant_precision: 0,
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
          poolId,
          uniqueResultCount: 0,
          relevantResultCount: 0,
          relevancePrecision: 0,
        },
      );
      if (noJsTimers) {
        console.log(
          `[BackgroundSearch] source done name=${srcName} status=${isBlacklisted ? 'skipped' : elapsed > 9000 ? 'timeout' : 'error'} count=0 ms=${elapsed} error=${msg}`,
        );
      }
      return 'failed';
    } finally {
      doneCount += 1;
      publishProgress();
      if (!noJsTimers) await new Promise<void>((resolve) => setTimeout(resolve, 0));
    }
  };

  const runPool = async (plan: SourcePoolPlan, timeoutMs: number): Promise<void> => {
    let completed = false;
    try {
      for (let index = 0; index < plan.candidates.length && !aborted(); index += 1) {
        if (index > 0) {
          scheduledCount += 1;
          publishProgress();
        }
        const candidate = plan.candidates[index];
        const candidateTimeoutMs = getSpeedTier(candidate) === 2 ? BROWSER_TIMEOUT_MS : timeoutMs;
        const outcome = await runSource(candidate, plan.poolId, candidateTimeoutMs);
        // A valid empty response still proves the content pool was searched.
        // Only transport failures, timeouts, challenges or parser errors move
        // to the next mirror in the same pool.
        if (outcome !== 'failed') {
          completed = true;
          return;
        }
      }
      completed = !aborted();
    } finally {
      if (completed) completedPoolIds.add(plan.poolId);
      publishProgress();
    }
  };

  const runPoolStage = async (
    plans: SourcePoolPlan[],
    timeoutMs: number,
    concurrency: number,
  ): Promise<void> => {
    if (plans.length === 0 || aborted()) return;
    plans.forEach((plan) => scheduledPoolIds.add(plan.poolId));
    scheduledCount += plans.length;
    publishProgress();
    let cursor = 0;
    const runNextPool = async () => {
      while (cursor < plans.length && !aborted()) {
        const plan = plans[cursor++];
        await runPool(plan, timeoutMs);
      }
    };
    await Promise.allSettled(
      Array.from({ length: Math.min(concurrency, plans.length) }, () => runNextPool()),
    );
  };

  let stopReason: SearchRunnerResult['stopReason'] = 'exhausted';
  for (let stageIndex = 0; stageIndex < httpStages.length && !aborted(); stageIndex += 1) {
    await runPoolStage(
      httpStages[stageIndex],
      stageIndex === 0 ? FAST_HTTP_TIMEOUT_MS : TAIL_HTTP_TIMEOUT_MS,
      CONCURRENCY,
    );
  }

  if (browserPoolPlans.length > 0 && !aborted()) {
    await runPoolStage(browserPoolPlans, BROWSER_TIMEOUT_MS, BROWSER_CONCURRENCY);
  }

  if (aborted()) stopReason = 'aborted';
  debugReport.setTotalSources(scheduledCount);

  return {
    results: rawResults,
    report: debugReport.finish(!aborted()),
    aborted: aborted(),
    sourceCount: scheduledCount,
    doneCount,
    hostCount: allSources.length,
    poolCount: scheduledPoolIds.size,
    completedPoolCount: completedPoolIds.size,
    totalPoolCount,
    stopReason,
    analytics: {
      durationMs: Date.now() - startedAt,
      timeToFirstResultMs,
      sourceRollup,
    },
  };
}
