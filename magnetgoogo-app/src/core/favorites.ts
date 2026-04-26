/**
 * Favorites — persisted in AsyncStorage.
 * Stores magnet links + metadata for quick access.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

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

export async function getFavorites(): Promise<FavoriteItem[]> {
  if (_cache) return _cache;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    _cache = raw ? JSON.parse(raw) : [];
  } catch {
    _cache = [];
  }
  return _cache!;
}

async function _save(): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_cache || []));
}

export async function addFavorite(item: Omit<FavoriteItem, 'addedAt'>): Promise<void> {
  const list = await getFavorites();
  // Prevent duplicate by magnet
  if (list.some((f) => f.magnet === item.magnet)) return;
  list.unshift({ ...item, addedAt: Date.now() });
  _cache = list;
  await _save();
}

export async function removeFavorite(magnet: string): Promise<void> {
  const list = await getFavorites();
  _cache = list.filter((f) => f.magnet !== magnet);
  await _save();
}

export async function isFavorited(magnet: string): Promise<boolean> {
  const list = await getFavorites();
  return list.some((f) => f.magnet === magnet);
}

export async function clearFavorites(): Promise<void> {
  _cache = [];
  await AsyncStorage.removeItem(STORAGE_KEY);
}
