/**
 * Source Bench Runner — runs benchmark tests against all configured sources.
 *
 * Tests each source with two queries, measures response times, extracts info
 * hashes for overlap analysis, and reports results with concurrency control.
 *
 * Designed for developer/tester use — NOT shipped in production search flows.
 */
import { searchSource, type SourceRule, type ResultItem } from './searchEngine';
import { clearVerifyBlacklist } from './VerifyManager';

// ── Types ────────────────────────────────────────────────────────────

export const OVERLAP_THRESHOLD = 0.8;

export type BenchStatus =
  | 'pending' | 'running' | 'ok' | 'partial' | 'empty' | 'error' | 'timeout'
  | 'skipped_webview' | 'hallucinating' | 'pending_new_build';

export const NEW_HANDLERS = new Set([
  'ssbc', 'thatcdn', 'lulutang', 'btsow', 'snowfl', 'yts', 'wuji',
]);

export interface BenchSourceResult {
  ruleId: string;
  name: string;
  origin: string;
  handler: string;
  isNewHandler: boolean;
  status: BenchStatus;
  q1ResultCount: number;
  q1Hashes: string[];
  q1SampleTitles: string[];
  q1DurationMs: number;
  q1Error?: string;
  q2ResultCount: number;
  q2Hashes: string[];
  q2DurationMs: number;
  q2Error?: string;
  hashOverlapRatio: number;
  builtUrl: string;
}

export interface BenchConfig {
  query1: string;
  query2: string;
  onlyNewHandlers: boolean;
  onlyGreen: boolean;
  concurrency: 1 | 3 | 5;
  timeoutMs: number;
}

export interface BenchSession {
  config: BenchConfig;
  sources: BenchSourceResult[];
  running: boolean;
  startedAt: number;
  completedCount: number;
  aborted: boolean;
}

// ── URL construction (mirrors searchEngine.ts) ───────────────────────

/**
 * Build the search URL for a source rule, applying the same template
 * substitutions as searchEngine.ts:
 *   {query}       → encodeURIComponent
 *   {query_b64}   → btoa(unescape(encodeURIComponent(...)))
 *   {query_b64url}→ base64url (no padding)
 */
export function buildSearchUrl(rule: SourceRule, query: string): string {
  const origin = rule.site.origin.replace(/\/$/, '');
  const template = rule.search.request_template;

  const queryB64 =
    typeof btoa === 'function'
      ? btoa(unescape(encodeURIComponent(query)))
      : Buffer.from(query, 'utf-8').toString('base64');
  const queryB64url = queryB64
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  return (
    origin +
    template
      .replace('{query}', encodeURIComponent(query))
      .replace('{query_b64}', queryB64)
      .replace('{query_b64url}', queryB64url)
  );
}

// ── Hash extraction ──────────────────────────────────────────────────

/**
 * Extract unique info hashes (lowercase, max 10) from magnet URIs in the
 * result set.
 */
export function extractHashes(results: ResultItem[]): string[] {
  const seen = new Set<string>();
  for (const r of results) {
    if (!r.magnet) continue;
    const m = r.magnet.match(/btih:([a-fA-F0-9]+)/i);
    if (!m) continue;
    const hash = m[1].toLowerCase();
    if (!seen.has(hash)) {
      seen.add(hash);
      if (seen.size >= 10) break;
    }
  }
  return [...seen];
}

// ── Overlap calculation ──────────────────────────────────────────────

/**
 * Compute hash overlap ratio: |intersection| / max(|set1|, |set2|).
 * Returns 0 if both are empty.
 */
export function calcOverlapRatio(hashes1: string[], hashes2: string[]): number {
  if (hashes1.length === 0 && hashes2.length === 0) return 0;
  const set1 = new Set(hashes1);
  let intersection = 0;
  for (const h of hashes2) {
    if (set1.has(h)) intersection++;
  }
  return intersection / Math.max(hashes1.length, hashes2.length);
}

// ── Single-source test ───────────────────────────────────────────────

/**
 * Test a single source with two queries. Only runs q2 if q1 returned results.
 * Uses Promise.race with the configured timeout.
 */
export async function testSource(
  rule: SourceRule,
  config: BenchConfig,
): Promise<{
  q1: { results: ResultItem[]; durationMs: number; error?: string };
  q2: { results: ResultItem[]; durationMs: number; error?: string };
}> {
  const timeout = config.timeoutMs;

  // --- Q1 ---
  let q1Results: ResultItem[] = [];
  let q1Duration = 0;
  let q1Error: string | undefined;
  try {
    const start = Date.now();
    q1Results = await Promise.race([
      searchSource(rule, config.query1),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), timeout),
      ),
    ]);
    q1Duration = Date.now() - start;
  } catch (e: any) {
    q1Duration = 0;
    q1Error = e?.message || String(e);
  }

  // --- Q2 (only if q1 had results) ---
  let q2Results: ResultItem[] = [];
  let q2Duration = 0;
  let q2Error: string | undefined;
  if (q1Results.length > 0) {
    try {
      const start = Date.now();
      q2Results = await Promise.race([
        searchSource(rule, config.query2),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('timeout')), timeout),
        ),
      ]);
      q2Duration = Date.now() - start;
    } catch (e: any) {
      q2Duration = 0;
      q2Error = e?.message || String(e);
    }
  }

  return {
    q1: { results: q1Results, durationMs: q1Duration, error: q1Error },
    q2: { results: q2Results, durationMs: q2Duration, error: q2Error },
  };
}

// ── Concurrency-controlled task runner ───────────────────────────────

/**
 * Run async tasks with bounded concurrency using a signal-based queue
 * (NOT Promise.all which would fire everything at once).
 */
export async function runWithConcurrency<T>(
  tasks: (() => Promise<T>)[],
  concurrency: number,
): Promise<T[]> {
  const results: T[] = new Array(tasks.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < tasks.length) {
      const idx = nextIndex++;
      results[idx] = await tasks[idx]();
    }
  }

  const workers: Promise<void>[] = [];
  for (let i = 0; i < Math.min(concurrency, tasks.length); i++) {
    workers.push(worker());
  }
  await Promise.all(workers);
  return results;
}

// ── Main bench entry ─────────────────────────────────────────────────

/**
 * Run the full benchmark test across all matching sources.
 *
 * @param allRules  - all source rules from sources.json
 * @param config    - bench configuration
 * @param onProgress - called after each source completes (or is skipped)
 * @param abortRef  - mutable ref; if `.aborted` is set to true, remaining
 *                    sources are skipped
 */
export async function runBenchTest(
  allRules: SourceRule[],
  config: BenchConfig,
  onProgress: (session: BenchSession) => void,
  abortRef: { aborted: boolean },
): Promise<BenchSession> {
  const session: BenchSession = {
    config,
    sources: [],
    running: true,
    startedAt: Date.now(),
    completedCount: 0,
    aborted: false,
  };

  // Clear blacklist so all sources get a fair chance
  clearVerifyBlacklist();

  try {
    // ── Filter sources ──
    let rules = allRules.filter((r) => {
      // Must have a search template or handler
      if (!r.search?.request_template && !r.search?.handler) return false;
      // onlyGreen: must have quality.score >= 60
      if (config.onlyGreen && (r.quality?.score ?? 0) < 60) return false;
      // onlyNewHandlers: must be in NEW_HANDLERS set
      if (config.onlyNewHandlers && !NEW_HANDLERS.has(r.search.handler || '')) return false;
      return true;
    });

    // ── Build placeholder results ──
    for (const rule of rules) {
      const handler = rule.search.handler || '';
      const builtUrl =
        rule.search.requires_browser
          ? '(browser-only)'
          : buildSearchUrl(rule, config.query1);

      session.sources.push({
        ruleId: rule.site.origin,
        name: rule.site.name,
        origin: rule.site.origin,
        handler,
        isNewHandler: NEW_HANDLERS.has(handler),
        status: 'pending',
        q1ResultCount: 0,
        q1Hashes: [],
        q1SampleTitles: [],
        q1DurationMs: 0,
        q2ResultCount: 0,
        q2Hashes: [],
        q2DurationMs: 0,
        hashOverlapRatio: 0,
        builtUrl,
      });
    }

    // ── Build task list ──
    const tasks = rules.map((rule, idx) => async () => {
      if (abortRef.aborted) {
        session.sources[idx].status = 'error';
        session.completedCount++;
        onProgress(session);
        return;
      }

      const entry = session.sources[idx];

      // Skip browser-required sources
      if (rule.search.requires_browser) {
        entry.status = 'skipped_webview';
        session.completedCount++;
        onProgress(session);
        return;
      }

      // Skip sources with handlers not yet available in this app build
      const handler = rule.search.handler || '';
      if (NEW_HANDLERS.has(handler)) {
        entry.status = 'pending_new_build';
        session.completedCount++;
        onProgress(session);
        return;
      }

      entry.status = 'running';
      onProgress(session);

      try {
        const { q1, q2 } = await testSource(rule, config);

        // Q1
        entry.q1ResultCount = q1.results.length;
        entry.q1Hashes = extractHashes(q1.results);
        entry.q1SampleTitles = q1.results.slice(0, 3).map((r) => r.title);
        entry.q1DurationMs = q1.durationMs;
        if (q1.error) entry.q1Error = q1.error;

        // Q2
        entry.q2ResultCount = q2.results.length;
        entry.q2Hashes = extractHashes(q2.results);
        entry.q2DurationMs = q2.durationMs;
        if (q2.error) entry.q2Error = q2.error;

        // Overlap
        entry.hashOverlapRatio = calcOverlapRatio(entry.q1Hashes, entry.q2Hashes);

        // Determine status (aligned with source_qualification GREEN standard)
        if (q1.error === 'timeout' || q2.error === 'timeout') {
          entry.status = 'timeout';
        } else if (q1.error === '__blacklisted__') {
          entry.status = 'error';
        } else if (q1.error) {
          entry.status = 'error';
        } else if (entry.q1Hashes.length === 0) {
          entry.status = 'empty';
        } else if (entry.q2Hashes.length === 0) {
          // Single-bait magnets only → YELLOW equivalent
          entry.status = 'partial';
        } else if (entry.hashOverlapRatio >= OVERLAP_THRESHOLD) {
          // Same magnets regardless of query → homepage hallucination
          entry.status = 'hallucinating';
        } else {
          // Two baits, distinct magnet sets → GREEN equivalent
          entry.status = 'ok';
        }
      } catch (e: any) {
        entry.status = 'error';
        entry.q1Error = e?.message || String(e);
      }

      session.completedCount++;
      onProgress(session);
    });

    // ── Run with concurrency control ──
    await runWithConcurrency(tasks, config.concurrency);

    if (abortRef.aborted) {
      session.aborted = true;
    }
  } finally {
    session.running = false;
    // Clear blacklist again to restore normal search behavior
    clearVerifyBlacklist();
  }

  return session;
}

// ── Export report ────────────────────────────────────────────────────

/**
 * Export bench session as a JSON string with summary statistics and
 * per-source details, focused on new handler results.
 */
export function exportBenchReport(session: BenchSession): string {
  const newHandlerResults = session.sources.filter((s) => s.isNewHandler);
  const allResults = session.sources;

  const summary = {
    totalSources: allResults.length,
    okCount: allResults.filter((s) => s.status === 'ok').length,
    emptyCount: allResults.filter((s) => s.status === 'empty').length,
    errorCount: allResults.filter((s) => s.status === 'error').length,
    timeoutCount: allResults.filter((s) => s.status === 'timeout').length,
    skippedCount: allResults.filter((s) => s.status === 'skipped_webview').length,
    partialCount: allResults.filter((s) => s.status === 'partial').length,
    hallucinatingCount: allResults.filter((s) => s.status === 'hallucinating').length,
    pendingNewBuildCount: allResults.filter((s) => s.status === 'pending_new_build').length,
    newHandlerOkCount: newHandlerResults.filter((s) => s.status === 'ok').length,
    newHandlerTotal: newHandlerResults.length,
    durationMs: Date.now() - session.startedAt,
    aborted: session.aborted,
    config: session.config,
  };

  const report = {
    summary,
    newHandlerResults: newHandlerResults.map((s) => ({
      name: s.name,
      handler: s.handler,
      status: s.status,
      q1ResultCount: s.q1ResultCount,
      q1DurationMs: s.q1DurationMs,
      q1Error: s.q1Error,
      q2ResultCount: s.q2ResultCount,
      q2DurationMs: s.q2DurationMs,
      q2Error: s.q2Error,
      hashOverlapRatio: s.hashOverlapRatio,
      builtUrl: s.builtUrl,
    })),
    allResults: allResults.map((s) => ({
      name: s.name,
      handler: s.handler,
      isNewHandler: s.isNewHandler,
      status: s.status,
      q1ResultCount: s.q1ResultCount,
      q1DurationMs: s.q1DurationMs,
      q2ResultCount: s.q2ResultCount,
      hashOverlapRatio: s.hashOverlapRatio,
    })),
  };

  return JSON.stringify(report, null, 2);
}
