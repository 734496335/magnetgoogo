/**
 * Favorites — persisted in AsyncStorage.
 * Stores magnet links + metadata for quick access.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncSerialQueue } from './asyncSerialQueue';
import { sanitizeFavoriteItems } from './storageSanitizers';

const STORAGE_KEY = 'mg_favorites';

export interface FavoriteItem {
  id: string;       // info hash or magnet tail
  title: string;
  magnet: string;
  size: string;
  sourceName: string;
  addedAt: number;
}

let _cache: FavoriteItem[] | null = null;
let _loadPromise: Promise<FavoriteItem[]> | null = null;
const enqueueMutation = createAsyncSerialQueue();

export async function getFavorites(): Promise<FavoriteItem[]> {
  if (_cache) return _cache.slice();
  if (!_loadPromise) {
    const task = (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        _cache = sanitizeFavoriteItems(raw ? JSON.parse(raw) : []);
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

async function _save(): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_cache || []));
}

export function addFavorite(item: Omit<FavoriteItem, 'addedAt'>): Promise<void> {
  return enqueueMutation(async () => {
    const list = await getFavorites();
    // Prevent duplicate by magnet
    if (list.some((f) => f.magnet === item.magnet)) return;
    _cache = [{ ...item, addedAt: Date.now() }, ...list];
    await _save();
  });
}

export function removeFavorite(magnet: string): Promise<void> {
  return enqueueMutation(async () => {
    const list = await getFavorites();
    _cache = list.filter((f) => f.magnet !== magnet);
    await _save();
  });
}

export async function isFavorited(magnet: string): Promise<boolean> {
  const list = await getFavorites();
  return list.some((f) => f.magnet === magnet);
}

export function clearFavorites(): Promise<void> {
  return enqueueMutation(async () => {
    _cache = [];
    await AsyncStorage.removeItem(STORAGE_KEY);
  });
}
