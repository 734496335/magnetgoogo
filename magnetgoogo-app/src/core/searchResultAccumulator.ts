import type { DedupedResult } from './dedup';
import type { ResultCardModel, SearchResult } from './types';

const HIGH_RELEVANCE_THRESHOLD = 30;

type AccumulatedResult = DedupedResult & {
  _sizeBytes: number;
  _videoQ: number;
  _relevance: number;
  _dirty?: boolean;
};

export interface SearchResultAccumulatorState {
  _dedupMap: Map<string, AccumulatedResult>;
  _noHashResults: AccumulatedResult[];
  _noHashKeys: Set<string>;
  _processedCount: number;
  _cardModels: ResultCardModel[];
  _cardModelCache: Map<string, ResultCardModel>;
  _orderKeys: string[];
  _finalSorted: boolean;
}

export interface SearchResultAccumulatorDeps {
  extractInfoHash: (magnet: string) => string | null;
  getStableId: (result: SearchResult) => string;
  computeRelevance: (title: string, query: string) => number;
  parseSizeBytes: (label?: string) => number;
}

export interface RebuildCardModelsOptions {
  searching: boolean;
  forceFullSort: boolean;
  query: string;
  extractInfoHash: (magnet: string) => string | null;
  getStableId: (result: SearchResult) => string;
  buildCard: (result: SearchResult, index: number) => ResultCardModel;
}

export function createSearchResultAccumulatorState(): SearchResultAccumulatorState {
  return {
    _dedupMap: new Map(),
    _noHashResults: [],
    _noHashKeys: new Set(),
    _processedCount: 0,
    _cardModels: [],
    _cardModelCache: new Map(),
    _orderKeys: [],
    _finalSorted: false,
  };
}

const QUALITY_PATTERNS: Array<[RegExp, number]> = [
  [/remux/i, 100],
  [/blu[\s.-]?ray|bluray|bdrip|bdremux|brrip/i, 95],
  [/web[\s.-]?dl|webdl|webrip|web[\s.-]?rip/i, 80],
  [/hdrip|hdtv|pdtv/i, 65],
  [/dvdrip|dvd[\s.-]?scr|dvd/i, 50],
  [/hdcam|cam[\s.-]?rip|\bcam\b/i, 15],
  [/ts\b|telesync|tc\b|telecine/i, 10],
];

function videoQuality(title: string): number {
  for (const [pattern, score] of QUALITY_PATTERNS) {
    if (pattern.test(title)) return score;
  }
  return 50;
}

function shouldReplaceMergedTitle(
  currentTitle: string,
  nextTitle: string,
  query: string,
  computeRelevance: SearchResultAccumulatorDeps['computeRelevance'],
): boolean {
  const currentRelevance = computeRelevance(currentTitle, query);
  const nextRelevance = computeRelevance(nextTitle, query);
  if (nextRelevance !== currentRelevance) return nextRelevance > currentRelevance;
  return nextTitle.length > currentTitle.length;
}

export function mergePendingSearchResults(
  state: SearchResultAccumulatorState,
  rawResults: SearchResult[],
  query: string,
  deps: SearchResultAccumulatorDeps,
): boolean {
  const newResults = rawResults.slice(state._processedCount);
  if (newResults.length === 0) return false;

  let listChanged = false;
  for (const result of newResults) {
    const hash = deps.extractInfoHash(result.magnet);
    const sourceName = result.site_name || result.source || '';

    if (!hash) {
      const key = deps.getStableId(result);
      if (state._noHashKeys.has(key)) continue;
      state._noHashKeys.add(key);
      state._noHashResults.push({
        ...result,
        sourceCount: 1,
        sourceNames: [sourceName],
        bestSeeders: result.seeders || 0,
        _sizeBytes: deps.parseSizeBytes(result.size),
        _videoQ: videoQuality(result.title),
        _relevance: deps.computeRelevance(result.title, query),
      });
      listChanged = true;
      continue;
    }

    const existing = state._dedupMap.get(hash);
    if (!existing) {
      state._dedupMap.set(hash, {
        ...result,
        sourceCount: 1,
        sourceNames: [sourceName],
        bestSeeders: result.seeders || 0,
        _sizeBytes: deps.parseSizeBytes(result.size),
        _videoQ: videoQuality(result.title),
        _relevance: deps.computeRelevance(result.title, query),
      });
      state._orderKeys.push(hash);
      listChanged = true;
      continue;
    }

    let existingChanged = false;
    if (sourceName && !existing.sourceNames.includes(sourceName)) {
      existing.sourceNames.push(sourceName);
      existing.sourceCount = existing.sourceNames.length;
      existingChanged = true;
    }
    if (shouldReplaceMergedTitle(existing.title, result.title, query, deps.computeRelevance)) {
      existing.title = result.title;
      existing._videoQ = videoQuality(result.title);
      existing._relevance = deps.computeRelevance(result.title, query);
      existing.site_name = result.site_name;
      existing.source = result.source;
      existingChanged = true;
    }
    const incomingSizeBytes = deps.parseSizeBytes(result.size);
    // Identical info hashes describe the same torrent. The total torrent size
    // is at least as large as any sample/file size exposed by another source.
    if (incomingSizeBytes > existing._sizeBytes) {
      existing.size = result.size;
      existing._sizeBytes = incomingSizeBytes;
      existingChanged = true;
    }
    if ((result.seeders || 0) > existing.bestSeeders) {
      existing.bestSeeders = result.seeders || 0;
      existing.seeders = result.seeders;
      existingChanged = true;
    }
    if (!existing.date && result.date) {
      existing.date = result.date;
      existingChanged = true;
    }
    if (!existing.fileCount && result.fileCount) {
      existing.fileCount = result.fileCount;
      existingChanged = true;
    }
    if (existingChanged) {
      existing._dirty = true;
      listChanged = true;
    }
  }

  state._processedCount = rawResults.length;
  return listChanged;
}

export function rebuildSearchCardModels(
  state: SearchResultAccumulatorState,
  options: RebuildCardModelsOptions,
): void {
  const shouldFullSort = options.forceFullSort || (!options.searching && !state._finalSorted);
  let deduped: AccumulatedResult[];

  if (shouldFullSort) {
    const sorted = [...state._dedupMap.values()];
    sorted.sort((a, b) => {
      const aRelevant = a._relevance >= HIGH_RELEVANCE_THRESHOLD ? 1 : 0;
      const bRelevant = b._relevance >= HIGH_RELEVANCE_THRESHOLD ? 1 : 0;
      if (bRelevant !== aRelevant) return bRelevant - aRelevant;
      if (b.sourceCount !== a.sourceCount) return b.sourceCount - a.sourceCount;
      if (b._relevance !== a._relevance) return b._relevance - a._relevance;
      const sizeDelta = b._sizeBytes - a._sizeBytes;
      if (sizeDelta !== 0) return sizeDelta;
      const qualityDelta = b._videoQ - a._videoQ;
      if (qualityDelta !== 0) return qualityDelta;
      return b.bestSeeders - a.bestSeeders;
    });
    state._orderKeys = sorted.map(
      (result) => options.extractInfoHash(result.magnet) || options.getStableId(result),
    );
    deduped = [...sorted, ...state._noHashResults];
    if (!options.searching) state._finalSorted = true;
  } else {
    const ordered: AccumulatedResult[] = [];
    for (const key of state._orderKeys) {
      const result = state._dedupMap.get(key);
      if (result) ordered.push(result);
    }
    deduped = [...ordered, ...state._noHashResults];
  }

  state._cardModels = deduped.map((result, index) => {
    const key = options.getStableId(result);
    const cached = state._cardModelCache.get(key);
    if (cached && !result._dirty) return cached;

    result._dirty = false;
    const model = options.buildCard(result, index);
    state._cardModelCache.set(key, model);
    return model;
  });
}
