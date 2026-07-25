/**
 * Debug Search Server — allows automated testing via ADB.
 * Only active in __DEV__ mode. Listens on port 9998.
 *
 * Usage (after ADB reverse):
 *   curl http://localhost:9998/search?q=Inception
 *   curl http://localhost:9998/status
 */
import { searchSource, type SourceRule, type ResultItem } from './searchEngine';

let _sources: SourceRule[] = [];
let _searching = false;
let _lastResults: any = null;

export function setDebugSources(sources: SourceRule[]) {
  _sources = sources;
}

export async function handleDebugSearch(query: string): Promise<any> {
  if (_searching) return { error: 'search in progress', query };
  _searching = true;
  const start = Date.now();

  const results: any[] = [];
  const CONCURRENCY = 4;
  let cursor = 0;

  const runNext = async () => {
    while (cursor < _sources.length) {
      const idx = cursor++;
      const rule = _sources[idx];
      const origin = rule.site?.origin || '';
      const id = (rule as any).id || rule.site?.name || '?';
      const handler = rule.search?.handler || 'template';
      const t0 = Date.now();

      try {
        const items = await searchSource(rule, query);
        results.push({
          id, origin, handler,
          status: items.length > 0 ? 'ok' : 'empty',
          results: items.length,
          ms: Date.now() - t0,
          sample: items.slice(0, 2).map(i => ({
            title: i.title?.slice(0, 50),
            hash: (i.magnet?.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 16),
            size: i.size,
          })),
        });
      } catch (err: any) {
        const msg = err?.message || 'unknown';
        results.push({
          id, origin, handler,
          status: msg === '__blacklisted__' ? 'blacklisted' : 'error',
          results: 0,
          ms: Date.now() - t0,
          error: msg === '__blacklisted__' ? undefined : msg,
        });
      }
    }
  };

  const workers = Array.from(
    { length: Math.min(CONCURRENCY, _sources.length) },
    () => runNext(),
  );
  await Promise.allSettled(workers);

  const elapsed = Date.now() - start;
  const ok = results.filter(r => r.status === 'ok');
  _lastResults = {
    query,
    totalSources: _sources.length,
    elapsed,
    ok: ok.length,
    empty: results.filter(r => r.status === 'empty').length,
    error: results.filter(r => r.status === 'error').length,
    blacklisted: results.filter(r => r.status === 'blacklisted').length,
    totalResults: ok.reduce((s, r) => s + r.results, 0),
    results: results.sort((a, b) => b.results - a.results),
  };
  _searching = false;
  return _lastResults;
}

export function getDebugStatus() {
  return {
    searching: _searching,
    sourceCount: _sources.length,
    lastResults: _lastResults,
  };
}
