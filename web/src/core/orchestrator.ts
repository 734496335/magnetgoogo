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
  [/0cili/i, '0cili'],
  [/clb\d/i, 'clb'],
  [/rutor/i, 'rutor'],
  [/1337|1377/i, '1337x'],
  [/tokyotosho/i, 'tokyotosho'],
  [/dmhy|動漫花園/i, 'dmhy'],
  [/yts\./i, 'yts'],
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
  threshold: 0.8,
  ignoreLocation: true,
  minMatchCharLength: 2,
};

export function computeRelevance(title: string, query: string, _sourceScore: number): number {
  if (!title || !query) return 0;
  const fuse = new Fuse([{ t: title }], FUSE_OPTS);
  const hits = fuse.search(query);
  if (hits.length === 0) return 0;
  return Math.round((1 - (hits[0].score ?? 1)) * 1000) / 1000;
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
