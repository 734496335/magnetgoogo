export interface AnalyticsEventLike {
  id?: string;
  e?: string;
  ts?: number;
}

export interface SourceRollupLike {
  src?: string;
  cat?: string;
  pool?: string;
  called?: number;
  ok?: number;
  empty?: number;
  fail?: number;
  results?: number;
  unique_results?: number;
  relevant_results?: number;
  relevant_precision?: number;
  hit_searches?: number;
  ms?: number;
  verify?: number;
}

export interface CompactSourceSample {
  s: string;
  c?: string;
  p?: string;
  o: number;
  e: number;
  f: number;
  r: number;
  u?: number;
  q?: number;
  h: number;
  m: number;
}

export interface SourceRollupSummary {
  called: number;
  ok: number;
  empty: number;
  fail: number;
  results: number;
  unique_results: number;
  relevant_results: number;
  hit_sources: number;
  total_ms: number;
  max_ms: number;
}

function finiteInt(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.round(value));
}

function finiteRatio(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
  return Math.max(0, Math.min(1, Math.round(value * 1000) / 1000));
}

function trimText(value: unknown, maxLength: number): string {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

export function utf8ByteLength(value: string): number {
  let bytes = 0;
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code < 0x80) {
      bytes += 1;
    } else if (code < 0x800) {
      bytes += 2;
    } else if (code >= 0xd800 && code <= 0xdbff && i + 1 < value.length) {
      const next = value.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        bytes += 4;
        i += 1;
      } else {
        bytes += 3;
      }
    } else {
      bytes += 3;
    }
  }
  return bytes;
}

export function dedupeEventsById<T extends AnalyticsEventLike>(events: T[]): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  for (const event of events) {
    if (!event || typeof event !== 'object') continue;
    const id = typeof event.id === 'string' ? event.id : '';
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    result.push(event);
  }
  return result;
}

export function deterministicSample(key: string, denominator = 10): boolean {
  if (!key || denominator <= 1) return true;
  let hash = 2166136261;
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % denominator === 0;
}

export function classifyQuery(term: string): 'cjk' | 'latin' | 'code' | 'mixed' | 'other' {
  const value = (term || '').trim();
  if (!value) return 'other';
  const hasCjk = /[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/u.test(value);
  const hasLatin = /[A-Za-z]/.test(value);
  const hasDigitOrSymbol = /[0-9_\-.]/.test(value);
  if (hasCjk && !hasLatin) return 'cjk';
  if (hasLatin && !hasCjk && !hasDigitOrSymbol) return 'latin';
  if (!hasCjk && hasDigitOrSymbol) return 'code';
  if (hasCjk || hasLatin) return 'mixed';
  return 'other';
}

export function compactSourceRollup(
  rollup: SourceRollupLike[],
  includeSample: boolean,
  sampleLimit = 48,
): { summary: SourceRollupSummary; sample?: CompactSourceSample[] } {
  const summary: SourceRollupSummary = {
    called: 0,
    ok: 0,
    empty: 0,
    fail: 0,
    results: 0,
    unique_results: 0,
    relevant_results: 0,
    hit_sources: 0,
    total_ms: 0,
    max_ms: 0,
  };
  const sample: CompactSourceSample[] = [];

  for (const item of Array.isArray(rollup) ? rollup : []) {
    const called = finiteInt(item.called);
    const ok = finiteInt(item.ok);
    const empty = finiteInt(item.empty);
    const fail = finiteInt(item.fail);
    const results = finiteInt(item.results);
    const uniqueResults = finiteInt(item.unique_results);
    const relevantResults = finiteInt(item.relevant_results);
    const hitSearches = finiteInt(item.hit_searches);
    const ms = finiteInt(item.ms);

    summary.called += called;
    summary.ok += ok;
    summary.empty += empty;
    summary.fail += fail;
    summary.results += results;
    summary.unique_results += uniqueResults;
    summary.relevant_results += relevantResults;
    summary.hit_sources += hitSearches > 0 || results > 0 ? 1 : 0;
    summary.total_ms += ms;
    summary.max_ms = Math.max(summary.max_ms, ms);

    if (!includeSample || sample.length >= sampleLimit) continue;
    const src = trimText(item.src, 80);
    if (!src) continue;
    const entry: CompactSourceSample = {
      s: src,
      o: ok,
      e: empty,
      f: fail,
      r: results,
      h: hitSearches,
      m: ms,
    };
    const cat = trimText(item.cat, 24);
    const pool = trimText(item.pool, 80);
    const precision = finiteRatio(item.relevant_precision);
    if (cat) entry.c = cat;
    if (pool) entry.p = pool;
    if (uniqueResults > 0) entry.u = uniqueResults;
    if (precision !== undefined) entry.q = precision;
    sample.push(entry);
  }

  return includeSample && sample.length > 0 ? { summary, sample } : { summary };
}

export function selectBatchByBytes<T extends AnalyticsEventLike>(
  events: T[],
  envelope: Record<string, unknown>,
  maxBytes: number,
  maxEvents: number,
): T[] {
  const selected: T[] = [];
  const limit = Math.max(1, Math.min(maxEvents, events.length));
  for (let i = 0; i < limit; i += 1) {
    const next = [...selected, events[i]];
    const body = JSON.stringify({ ...envelope, events: next });
    if (utf8ByteLength(body) > maxBytes) break;
    selected.push(events[i]);
  }
  return selected;
}
