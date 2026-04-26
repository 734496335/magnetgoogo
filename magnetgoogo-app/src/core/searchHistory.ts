/**
 * Search history — persisted in AsyncStorage.
 * Max 50 entries, newest first. Duplicate queries move to top.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'mg_search_history';
const MAX_ITEMS = 50;

export interface HistoryItem {
  query: string;
  timestamp: number;
}

let _cache: HistoryItem[] | null = null;

export async function getHistory(): Promise<HistoryItem[]> {
  if (_cache) return _cache;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    _cache = raw ? JSON.parse(raw) : [];
  } catch {
    _cache = [];
  }
  return _cache!;
}

export async function addHistory(query: string): Promise<void> {
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
}

export async function removeHistory(query: string): Promise<void> {
  const list = await getHistory();
  _cache = list.filter((h) => h.query !== query);
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_cache));
}

export async function clearHistory(): Promise<void> {
  _cache = [];
  await AsyncStorage.removeItem(STORAGE_KEY);
}
