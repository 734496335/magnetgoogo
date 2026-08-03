import { mergeResourceFileCount } from './resourceFileCount.ts';
import {
  resolveResourceSizeConsensus,
  upsertResourceSizeObservation,
} from './resourceSize.ts';
import type { SearchResult } from './types.ts';

export const BACKGROUND_SEARCH_POLL_INTERVAL_MS = 1500;
export const BACKGROUND_SEARCH_TASK_TIMEOUT_MS = 30 * 60 * 1000;

export interface BackgroundSearchSnapshot {
  query: string;
  token: number;
  searchId?: string;
  updatedAt: string;
  startedAt?: number;
  sourceCount: number;
  doneCount: number;
  completedPoolCount: number;
  totalPoolCount: number;
  searching: boolean;
  completed: boolean;
  resultCount: number;
  results: SearchResult[];
  error?: string;
}

function finiteNonNegative(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;
}

function sanitizeResults(value: unknown): SearchResult[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is SearchResult => {
    if (!item || typeof item !== 'object') return false;
    const record = item as Record<string, unknown>;
    return typeof record.title === 'string' && typeof record.magnet === 'string';
  });
}

export function mergeBackgroundSearchResults(
  current: SearchResult[],
  incoming: SearchResult[],
  getStableId: (result: SearchResult) => string,
): SearchResult[] {
  const merged: SearchResult[] = [];
  const indexById = new Map<string, number>();

  for (const item of [...current, ...incoming]) {
    const id = getStableId(item);
    const existingIndex = indexById.get(id);
    if (existingIndex === undefined) {
      indexById.set(id, merged.length);
      const sourceName = item.site_name || item.source || '';
      merged.push({
        ...item,
        _sizeObservations: upsertResourceSizeObservation(item._sizeObservations, item.size, sourceName),
      });
      continue;
    }

    const existing = merged[existingIndex];
    let sizeObservations = [...(existing._sizeObservations || [])];
    for (const observation of item._sizeObservations || []) {
      sizeObservations = upsertResourceSizeObservation(
        sizeObservations,
        observation.label,
        observation.source,
      );
    }
    sizeObservations = upsertResourceSizeObservation(
      sizeObservations,
      item.size,
      item.site_name || item.source || '',
    );
    const consensusSize = resolveResourceSizeConsensus(sizeObservations);
    const fileCountMerge = mergeResourceFileCount(
      existing.fileCount,
      item.fileCount,
      existing._fileCountConflict || item._fileCountConflict,
    );
    merged[existingIndex] = {
      ...existing,
      ...item,
      title: item.title.length >= existing.title.length ? item.title : existing.title,
      size: consensusSize || existing.size || item.size,
      _sizeObservations: sizeObservations,
      date: item.date || existing.date,
      fileCount: fileCountMerge.fileCount,
      _fileCountConflict: fileCountMerge.conflict || undefined,
      seeders: Math.max(item.seeders || 0, existing.seeders || 0),
      leechers: Math.max(item.leechers || 0, existing.leechers || 0),
    };
  }

  return merged;
}

export function parseBackgroundSearchSnapshot(value: unknown): BackgroundSearchSnapshot | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  const query = typeof record.query === 'string' ? record.query.trim() : '';
  if (!query) return null;

  const results = sanitizeResults(record.results);
  const searching = record.searching === true;
  const completed = record.completed === true || (!searching && record.completed !== false);
  const searchId = typeof record.searchId === 'string' && record.searchId ? record.searchId : undefined;
  const error = typeof record.error === 'string' && record.error ? record.error : undefined;
  const updatedAt = typeof record.updatedAt === 'string' && record.updatedAt
    ? record.updatedAt
    : new Date(0).toISOString();

  return {
    query,
    token: Math.trunc(finiteNonNegative(record.token)),
    searchId,
    updatedAt,
    startedAt: finiteNonNegative(record.startedAt) || undefined,
    sourceCount: Math.trunc(finiteNonNegative(record.sourceCount)),
    doneCount: Math.trunc(finiteNonNegative(record.doneCount)),
    completedPoolCount: Math.trunc(finiteNonNegative(record.completedPoolCount)),
    totalPoolCount: Math.trunc(finiteNonNegative(record.totalPoolCount)),
    searching,
    completed,
    resultCount: Math.max(Math.trunc(finiteNonNegative(record.resultCount)), results.length),
    results,
    error,
  };
}

export function backgroundSnapshotMatches(
  snapshot: BackgroundSearchSnapshot,
  query: string,
  token = 0,
): boolean {
  if (snapshot.query !== query.trim()) return false;
  if (!token || !snapshot.token) return false;
  return snapshot.token === token;
}

export function isBackgroundSearchTerminal(snapshot: BackgroundSearchSnapshot): boolean {
  return snapshot.completed || !snapshot.searching;
}
