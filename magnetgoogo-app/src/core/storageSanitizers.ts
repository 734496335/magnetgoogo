export interface StoredHistoryItem {
  query: string;
  timestamp: number;
}

export interface StoredFavoriteItem {
  id: string;
  title: string;
  magnet: string;
  size: string;
  sourceName: string;
  addedAt: number;
}

function finiteTimestamp(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;
}

export function sanitizeHistoryItems(value: unknown, maxItems = 50): StoredHistoryItem[] {
  if (!Array.isArray(value)) return [];

  const seen = new Set<string>();
  const out: StoredHistoryItem[] = [];
  for (const candidate of value) {
    if (!candidate || typeof candidate !== 'object') continue;
    const raw = candidate as Record<string, unknown>;
    if (typeof raw.query !== 'string') continue;
    const query = raw.query.trim();
    if (!query || seen.has(query)) continue;
    seen.add(query);
    out.push({ query, timestamp: finiteTimestamp(raw.timestamp) });
    if (out.length >= maxItems) break;
  }
  return out;
}

export function sanitizeFavoriteItems(value: unknown): StoredFavoriteItem[] {
  if (!Array.isArray(value)) return [];

  const seenMagnets = new Set<string>();
  const out: StoredFavoriteItem[] = [];
  for (const candidate of value) {
    if (!candidate || typeof candidate !== 'object') continue;
    const raw = candidate as Record<string, unknown>;
    if (typeof raw.magnet !== 'string') continue;
    const magnet = raw.magnet.trim();
    if (!magnet || seenMagnets.has(magnet)) continue;
    seenMagnets.add(magnet);

    const title = typeof raw.title === 'string' && raw.title.trim() ? raw.title.trim() : magnet;
    const id = typeof raw.id === 'string' && raw.id.trim() ? raw.id.trim() : magnet.split('&')[0];
    out.push({
      id,
      title,
      magnet,
      size: typeof raw.size === 'string' ? raw.size : '',
      sourceName: typeof raw.sourceName === 'string' ? raw.sourceName : '',
      addedAt: finiteTimestamp(raw.addedAt),
    });
  }
  return out;
}
