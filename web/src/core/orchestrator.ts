import { SourcesSchema, SourceRule, MagnetResult } from './types';
import Fuse from 'fuse.js';

const CONCURRENCY = 10;
const STORAGE_KEY = 'nebula_source_hits';

/* ---- Source memory: remember which origins returned results ---- */
interface SourceHitRecord {
  origin: string;
  hitCount: number;
  lastHit: number;
}

function loadHits(): Map<string, SourceHitRecord> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Map();
    const arr: SourceHitRecord[] = JSON.parse(raw);
    return new Map(arr.map(h => [h.origin, h]));
  } catch { return new Map(); }
}

function saveHits(hits: Map<string, SourceHitRecord>) {
  try {
    const arr = Array.from(hits.values())
      .sort((a, b) => b.hitCount - a.hitCount)
      .slice(0, 50);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(arr));
  } catch {}
}

function recordHit(origin: string) {
  const hits = loadHits();
  const prev = hits.get(origin) || { origin, hitCount: 0, lastHit: 0 };
  prev.hitCount++;
  prev.lastHit = Date.now();
  hits.set(origin, prev);
  saveHits(hits);
}

/* ---- Mirror-group detection ---- */
const MIRROR_PATTERNS: [RegExp, string][] = [
  [/piratebay|pirateproxy|tpb\.|pirate-proxy/i, 'tpb'],
  [/magnetdl/i, 'magnetdl'],
  [/0cili|wuji\.me|cilisousuo/i, '0magnet'],
  [/clb\d/i, 'clb'],
  [/sobt\d/i, 'sobt'],
  [/clm\d|magnetcatcat/i, 'clm'],
  [/zzb\d|zhongziba|seed8\.org/i, 'zzb'],
  [/cld\d|529\d{3}/i, 'cld'],
  [/rutor/i, 'rutor'],
  [/1337|1377/i, '1337x'],
  [/tokyotosho/i, 'tokyotosho'],
  [/dmhy|anoneko/i, 'dmhy'],
  [/yts\./i, 'yts'],
  [/nyaa/i, 'nyaa'],
];

function detectMirrorGroup(origin: string): string {
  for (const [re, group] of MIRROR_PATTERNS) {
    if (re.test(origin)) return group;
  }
  return origin; // unique source = its own group
}

/* ---- Relevance scoring (Fuse.js) ---- */
const FUSE_OPTS = {
  keys: ['t'],
  includeScore: true,
  threshold: 0.5,
  ignoreLocation: true,
  minMatchCharLength: 2,
};

export function computeRelevance(title: string, query: string, _sourceScore: number): number {
  if (!title || !query) return 0;

  // Signal 1: keyword containment (most reliable for CJK)
  const titleLower = title.toLowerCase();
  const queryLower = query.toLowerCase();
  const keywords = queryLower.split(/[\s_\-+.]+/).filter(w => w.length >= 2);
  const fullMatch = titleLower.includes(queryLower);
  const kwHits = keywords.length > 0
    ? keywords.filter(kw => titleLower.includes(kw)).length / keywords.length
    : 0;

  // Signal 2: Fuse.js fuzzy match (better for typos / transliterations)
  const fuse = new Fuse([{ t: title }], FUSE_OPTS);
  const hits = fuse.search(query);
  const fuseScore = hits.length > 0 ? (1 - (hits[0].score ?? 1)) : 0;

  // Combine: keyword match dominates, fuse supplements
  const combined = fullMatch ? 1.0
    : Math.max(kwHits * 0.9, fuseScore);

  return Math.round(combined * 1000) / 1000;
}

/* ---- Concurrency runner ---- */
async function runPool<T>(
  items: T[],
  concurrency: number,
  fn: (item: T) => Promise<void>,
  signal: AbortSignal,
) {
  let idx = 0;
  const next = async () => {
    while (idx < items.length) {
      if (signal.aborted) return;
      const item = items[idx++];
      await fn(item);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => next()));
}

/* ---- Orchestrator ---- */
export class SearchOrchestrator {
  private abortController: AbortController | null = null;

  async fetchSources() {
    const resp = await fetch('/sources.json');
    if (!resp.ok) throw new Error('Failed to load sources.json');
    const data = await resp.json();
    return SourcesSchema.parse(data);
  }

  async search(
    query: string,
    onResults: (results: MagnetResult[]) => void,
    onStatus: (site: string, status: 'searching' | 'done' | 'error') => void,
  ) {
    this.abortController?.abort();
    this.abortController = new AbortController();
    const signal = this.abortController.signal;

    try {
      const sourcesData = await this.fetchSources();
      const allRules: SourceRule[] = [];
      for (const rs of sourcesData.rulesets) allRules.push(...rs.rules);

      // Deduplicate green sources by origin
      const seen = new Set<string>();
      const greenRules = allRules
        .filter(r => r.health?.status === 'green')
        .filter(r => { const o = r.site.origin; if (seen.has(o)) return false; seen.add(o); return true; });

      // Sort: previously successful sources first, then by quality score
      const hits = loadHits();
      greenRules.sort((a, b) => {
        const aHit = hits.get(a.site.origin)?.hitCount ?? 0;
        const bHit = hits.get(b.site.origin)?.hitCount ?? 0;
        if (aHit !== bHit) return bHit - aHit;
        return b.quality.score - a.quality.score;
      });

      // Group mirrors: each group becomes one "task" with fallback mirrors
      const groupMap = new Map<string, SourceRule[]>();
      for (const r of greenRules) {
        const g = detectMirrorGroup(r.site.origin);
        if (!groupMap.has(g)) groupMap.set(g, []);
        groupMap.get(g)!.push(r);
      }

      type SearchTask = { mirrors: SourceRule[]; group: string };
      const tasks: SearchTask[] = Array.from(groupMap.entries())
        .map(([group, mirrors]) => ({ group, mirrors }));

      const searchTask = async (task: SearchTask) => {
        for (const rule of task.mirrors) {
          if (signal.aborted) return;
          onStatus(rule.site.name, 'searching');
          try {
            const resp = await fetch('/api/search', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ rule, query }),
              signal,
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            if (data.results?.length > 0) {
              const scored = data.results.map((r: MagnetResult) => ({
                ...r,
                relevance: computeRelevance(r.title, query, r.score),
              }));
              // No hard filter — sortResults will rank by relevance, slice(0,24) trims the tail.
              // This avoids censoring legitimate adult/niche searches where keywords may not match exactly.
              onResults(scored);
              recordHit(rule.site.origin);
            }
            onStatus(rule.site.name, 'done');
            return;
          } catch (err: any) {
            if (err.name === 'AbortError') return;
            console.error(`Search failed for ${rule.site.name}:`, err);
            onStatus(rule.site.name, 'error');
          }
        }
      };

      await runPool(tasks, CONCURRENCY, searchTask, signal);
    } catch (err: any) {
      if (err.name !== 'AbortError') throw err;
    }
  }

  cancel() {
    this.abortController?.abort();
    this.abortController = null;
  }
}
