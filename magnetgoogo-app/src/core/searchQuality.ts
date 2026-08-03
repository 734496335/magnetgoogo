import { SOURCE_QUALITY_PRIORS } from '../data/sourceQualityPriors.ts';
import { extractInfoHash } from './infoHash.ts';
import type { SearchResult } from './types';

export const HIGH_RELEVANCE_THRESHOLD = 30;
export const FAST_POOL_STAGE_LIMIT = 12;
export const EXPANSION_POOL_STAGE_LIMIT = 16;
export const FAST_SEARCH_UX_WINDOW_MS = 10_000;
export const TAIL_SEARCH_POOL_RATIO = 0.75;

export type QueryProfile = 'code' | 'cjk' | 'latin' | 'mixed';
export type SearchProgressStage = 'fast' | 'expanding' | 'tail';

export interface SourceQualitySummary {
  uniqueResultCount: number;
  relevantResultCount: number;
  exactResultCount: number;
  relevancePrecision: number;
  uniqueItems: Array<{
    item: SearchResult;
    key: string;
    relevance: number;
  }>;
}

export interface SourcePoolPlan {
  poolId: string;
  candidates: any[];
}

export interface SourceLearningSnapshot {
  successRate: number;
  emptyRate: number;
  failRate: number;
  challengeRate: number;
  avgMs: number;
  relevantYield: number;
  precision: number;
  qualitySamples: number;
}

function normalizedHost(origin: string): string {
  try {
    return new URL(origin).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return origin.toLowerCase().replace(/^https?:\/\//, '').split('/')[0] || 'unknown';
  }
}

export function classifyQueryProfile(query: string): QueryProfile {
  const trimmed = query.trim();
  const hasCjk = /[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(trimmed);
  const hasLatin = /[a-z]/i.test(trimmed);
  const codeLike = /^[a-z]{2,10}[\s._-]*\d{2,6}(?:[\s._-]*[a-z0-9]+)?$/i.test(trimmed);
  if (codeLike) return 'code';
  if (hasCjk && hasLatin) return 'mixed';
  if (hasCjk) return 'cjk';
  return 'latin';
}

export function getSourcePoolKey(rule: any): string {
  const explicit = String(rule?.quality?.pool_id || '').trim().toLowerCase();
  if (explicit) return explicit;

  const origin = String(rule?.site?.origin || '').trim();
  const host = normalizedHost(origin);
  const brand = String(rule?.site?.brand || '').trim().toLowerCase();
  const name = String(rule?.site?.name || '').trim().toLowerCase();
  const bag = `${host} ${brand} ${name}`;

  // Older encrypted source payloads may not yet carry pool_id. Keep the
  // well-known fallback families collapsed so mirrors never occupy a wave.
  if (/(?:the)?piratebay|pirate[- ]?proxy|pirateproxy|apibay|thehiddenbay|\btpb\b/.test(bag)) {
    return 'tpb';
  }
  if (/(?:^|\.)proxyit\.de\b/.test(host)) return 'proxyit.de';
  if (/cilibao|磁力宝|\bclb\d*/.test(bag)) return 'cilibao/clb';
  if (/cilimao|磁力猫|\bclm\d*/.test(bag)) return 'cilimao/clm';
  if (/seed8|zhongziba|种子吧|\bzzb\d*/.test(bag)) return 'seed8/zzb';
  if (/\bsobt\b|\bsbt\d+/.test(bag)) return 'sobt';

  if (brand) return `brand:${brand}`;
  if (origin) return `host:${host}`;
  return `source:${String(rule?.id || rule?.site?.name || 'unknown').toLowerCase()}`;
}

export function getSourceBenchmarkBoost(rule: any, query: string): number {
  if (!SOURCE_QUALITY_PRIORS.trusted) return 0;
  const prior = SOURCE_QUALITY_PRIORS.pools[getSourcePoolKey(rule)];
  if (!prior) return 0;

  const profile = classifyQueryProfile(query);
  let score = prior.global;
  let confidence = 0.65 + Math.min(1, Math.max(0, prior.coverage)) * 0.35;
  if (profile === 'latin' || profile === 'cjk') {
    score = prior[profile] * 0.75 + prior.global * 0.25;
  } else if (profile === 'code') {
    score = prior.code * 0.55 + prior.global * 0.45;
    confidence = 0.55 + Math.min(1, Math.max(0, prior.coverage)) * 0.35;
  } else {
    score = prior.mixed * 0.75 + prior.global * 0.25;
  }

  const confidenceAdjusted = 50 + (score - 50) * confidence;
  return Math.max(-12, Math.min(15, (confidenceAdjusted - 50) * 0.3));
}

export function buildSourcePoolPlans(orderedSources: any[]): SourcePoolPlan[] {
  const groups = new Map<string, Array<{ rule: any; index: number }>>();
  orderedSources.forEach((rule, index) => {
    const poolId = getSourcePoolKey(rule);
    const existing = groups.get(poolId) || [];
    existing.push({ rule, index });
    groups.set(poolId, existing);
  });

  return [...groups.entries()].map(([poolId, entries]) => ({
    poolId,
    // orderedSources already contains the benchmark, local-learning and role
    // priors. Preserve that order so fresh evidence can override stale
    // primary/fallback declarations within the same mirror pool.
    candidates: entries
      .sort((a, b) => a.index - b.index)
      .map((entry) => entry.rule),
  }));
}

export function splitPoolStages(plans: SourcePoolPlan[]): SourcePoolPlan[][] {
  return [
    plans.slice(0, FAST_POOL_STAGE_LIMIT),
    plans.slice(FAST_POOL_STAGE_LIMIT, FAST_POOL_STAGE_LIMIT + EXPANSION_POOL_STAGE_LIMIT),
    plans.slice(FAST_POOL_STAGE_LIMIT + EXPANSION_POOL_STAGE_LIMIT),
  ].filter((stage) => stage.length > 0);
}

export function getSearchResultQualityKey(result: Pick<SearchResult, 'magnet' | 'title'>): string {
  const hash = extractInfoHash(result.magnet);
  if (hash) return `btih:${hash}`;
  const cleanMagnet = result.magnet.split('&')[0]?.trim().toLowerCase();
  if (cleanMagnet) return `magnet:${cleanMagnet}`;
  return `title:${result.title.trim().toLowerCase().replace(/\s+/g, ' ')}`;
}

export function summarizeSourceQuality(
  items: SearchResult[],
  query: string,
  computeRelevance: (title: string, query: string) => number,
): SourceQualitySummary {
  const unique = new Map<string, { item: SearchResult; key: string; relevance: number }>();
  for (const item of items) {
    const key = getSearchResultQualityKey(item);
    const relevance = computeRelevance(item.title, query);
    const existing = unique.get(key);
    if (!existing || relevance > existing.relevance) {
      unique.set(key, { item, key, relevance });
    }
  }

  const uniqueItems = [...unique.values()];
  const relevantResultCount = uniqueItems.filter((entry) => entry.relevance >= HIGH_RELEVANCE_THRESHOLD).length;
  const exactResultCount = uniqueItems.filter((entry) => entry.relevance === 100).length;
  return {
    uniqueResultCount: uniqueItems.length,
    relevantResultCount,
    exactResultCount,
    relevancePrecision: uniqueItems.length > 0 ? relevantResultCount / uniqueItems.length : 0,
    uniqueItems,
  };
}

export function getSearchProgressStage(
  elapsedMs: number,
  completedPoolCount: number,
  totalPoolCount: number,
): SearchProgressStage {
  const safeCompleted = Math.max(0, completedPoolCount);
  const safeTotal = Math.max(0, totalPoolCount);
  if (safeTotal > 0 && safeCompleted >= Math.ceil(safeTotal * TAIL_SEARCH_POOL_RATIO)) {
    return 'tail';
  }
  if (elapsedMs >= FAST_SEARCH_UX_WINDOW_MS || safeCompleted >= FAST_POOL_STAGE_LIMIT) {
    return 'expanding';
  }
  return 'fast';
}

export function computeSourceLearningBoost(snapshot: SourceLearningSnapshot): number {
  const relevantYield = Math.min(Math.max(snapshot.relevantYield, 0), 15);
  const precision = Math.min(Math.max(snapshot.precision, 0), 1);
  const avgMs = Math.max(snapshot.avgMs, 0);

  let boost = 0;
  boost += snapshot.successRate * 22;
  boost -= snapshot.emptyRate * 10;
  boost -= snapshot.failRate * 24;
  boost -= snapshot.challengeRate * 14;
  boost += relevantYield * 2.4;
  boost += precision * 28;
  boost -= Math.min(avgMs / 500, 14);

  if (snapshot.qualitySamples === 0) boost += 4;
  else if (snapshot.qualitySamples < 3) boost += 2;
  return boost;
}
