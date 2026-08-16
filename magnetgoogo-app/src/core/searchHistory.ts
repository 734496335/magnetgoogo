/**
 * Search history — persisted in AsyncStorage.
 * Max 50 entries, newest first. Duplicate queries move to top.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncSerialQueue } from './asyncSerialQueue';
import { sanitizeHistoryItems } from './storageSanitizers';

const STORAGE_KEY = 'mg_search_history';
const MAX_ITEMS = 50;

export interface HistoryItem {
  query: string;
  timestamp: number;
}

let _cache: HistoryItem[] | null = null;
let _loadPromise: Promise<HistoryItem[]> | null = null;
const enqueueMutation = createAsyncSerialQueue();

export async function getHistory(): Promise<HistoryItem[]> {
  if (_cache) return _cache.slice();
  if (!_loadPromise) {
    const task = (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        _cache = sanitizeHistoryItems(raw ? JSON.parse(raw) : [], MAX_ITEMS);
      } catch {
        _cache = [];
      }
      return _cache.slice();
    })();
    _loadPromise = task;
    void task.finally(() => {
      if (_loadPromise === task) _loadPromise = null;
    });
  }
  return (await _loadPromise).slice();
}

export function addHistory(query: string): Promise<void> {
  return enqueueMutation(async () => {
    const q = query.trim();
    if (!q) return;
    const list = await getHistory();
    // Remove duplicate
    const filtered = list.filter((h) => h.query !== q);
    // Prepend
    filtered.unshift({ query: q, timestamp: Date.now() });
    // Trim
    _cache = filtered.slice(0, MAX_ITEMS);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_cache));
  });
}

export function removeHistory(query: string): Promise<void> {
  return enqueueMutation(async () => {
    const list = await getHistory();
    _cache = list.filter((h) => h.query !== query);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_cache));
  });
}

export function clearHistory(): Promise<void> {
  return enqueueMutation(async () => {
    _cache = [];
    await AsyncStorage.removeItem(STORAGE_KEY);
  });
}
