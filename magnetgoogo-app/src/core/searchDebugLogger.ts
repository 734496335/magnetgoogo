/**
 * SearchDebugLogger — captures detailed per-search reports for debugging.
 *
 * Persistence strategy:
 *   - All reports saved to AsyncStorage as a single JSON array
 *   - Each recordSource() triggers an incremental persist (debounced 500ms)
 *   - Interrupted/aborted searches auto-snapshot as partial reports
 *   - Reports survive app restart; loadReports() restores on startup
 *   - exportReportsJson() returns full JSON for analysis
 *   - Max 50 reports kept; oldest trimmed on save
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Application from 'expo-application';
import { File, Directory, Paths } from 'expo-file-system/next';

// Search reports may contain user queries and result titles. Keep the device
// report channel available only in the dedicated Debug application ID; the
// production package must use the no-op builder.
const DEV_ONLY = Application.applicationId?.endsWith('.debug') === true;
const STORAGE_KEY = 'mg_search_debug_reports';
const MAX_REPORTS = 50;

export interface ResultItemLog {
  title: string;
  hash: string;       // first 16 chars of btih
  size: string;
  relevance: number;  // relevance score vs query
}

export interface SourceResult {
  name: string;
  origin: string;
  poolId: string;
  status: 'ok' | 'empty' | 'error' | 'timeout' | 'skipped';
  resultCount: number;
  uniqueResultCount: number;
  relevantResultCount: number;
  relevancePrecision: number;
  durationMs: number;
  error?: string;
  sampleTitles: string[];
  sampleHashes: string[];
  /** Full per-result breakdown with relevance scores */
  items: ResultItemLog[];
  requiresWaf: boolean;
  requiresBrowser: boolean;
  qualityScore: number;
}

export interface SearchInventoryLog {
  benchmarkMode: boolean;
  coldStartMode: boolean;
  loadedHostCount: number;
  loadedPoolCount: number;
  sourcePackCount: number;
  sourcePackOrigin: string;
  sourcePackUpdatedAt: string;
  sourcePackIssuedAt: string;
  sourcePackExpiresAt: string;
}

export interface SearchReport {
  id: string;
  query: string;
  startedAt: string;      // ISO
  totalDurationMs: number;
  completed: boolean;      // false = interrupted/partial
  completedSources: number;
  sourceResults: SourceResult[];
  totalSources: number;
  attemptedHostCount: number;
  attemptedPoolCount: number;
  inventory: SearchInventoryLog;
  accessibleCount: number;
  resultCount: number;
  emptyCount: number;
  errorCount: number;
  skippedCount: number;
  totalMagnets: number;
  fastestSource: string;
  mostResultsSource: string;
}

let _reports: SearchReport[] = [];
let _loaded = false;
let _currentBuilder: ReportBuilder | null = null;
let _listeners: Array<() => void> = [];
let _persistTimer: ReturnType<typeof setTimeout> | null = null;

export function subscribe(fn: () => void) {
  if (!DEV_ONLY) return () => {};
  _listeners.push(fn);
  return () => { _listeners = _listeners.filter(l => l !== fn); };
}

function notify() {
  _listeners.forEach(fn => fn());
}

/** Load persisted reports from disk. Call once at app startup. */
export async function loadReports() {
  if (!DEV_ONLY) { _loaded = true; return; }
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) _reports = arr;
    }
  } catch { /* ignore */ }
  _loaded = true;
  notify();
}

/** Debounced persist — batches rapid recordSource() calls */
function schedulePersist() {
  if (!DEV_ONLY) return;
  if (_persistTimer) clearTimeout(_persistTimer);
  _persistTimer = setTimeout(() => persistNow(), 500);
}

async function persistNow() {
  if (!DEV_ONLY) return;
  try {
    const trimmed = _reports.slice(0, MAX_REPORTS);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch { /* ignore */ }
}

export function getReports(): SearchReport[] {
  return DEV_ONLY ? _reports : [];
}

export function getLatestReport(): SearchReport | null {
  return DEV_ONLY && _reports.length > 0 ? _reports[0] : null;
}

export async function clearReports() {
  if (!DEV_ONLY) return;
  _reports = [];
  try { await AsyncStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  notify();
}

/** Return full JSON string of all reports (for adb pull / share) */
export function exportReportsJson(): string {
  return DEV_ONLY ? JSON.stringify(_reports, null, 2) : '[]';
}

/** Start a new search report. Auto-snapshots previous unfinished builder. */
export function startReport(
  query: string,
  totalSources: number,
  inventory?: Partial<SearchInventoryLog>,
): ReportBuilder {
  if (!DEV_ONLY) return new NoopReportBuilder() as unknown as ReportBuilder;
  // Auto-snapshot previous builder if it was never finished
  if (_currentBuilder && !_currentBuilder._finished) {
    _currentBuilder.snapshot();
  }
  const builder = new ReportBuilder(query, totalSources, inventory);
  _currentBuilder = builder;
  return builder;
}

function computeAggregates(sources: SourceResult[]) {
  const accessibleCount = sources.filter(s => s.status === 'ok' || s.status === 'empty').length;
  const resultCount = sources.filter(s => s.status === 'ok').length;
  const emptyCount = sources.filter(s => s.status === 'empty').length;
  const errorCount = sources.filter(s => s.status === 'error' || s.status === 'timeout').length;
  const skippedCount = sources.filter(s => s.status === 'skipped').length;
  const totalMagnets = sources.reduce((sum, s) => sum + s.resultCount, 0);
  const okSources = sources.filter(s => s.status === 'ok');
  const fastestSource = okSources.length > 0
    ? [...okSources].sort((a, b) => a.durationMs - b.durationMs)[0].name : '-';
  const mostResultsSource = okSources.length > 0
    ? [...okSources].sort((a, b) => b.resultCount - a.resultCount)[0].name : '-';
  return { accessibleCount, resultCount, emptyCount, errorCount, skippedCount, totalMagnets, fastestSource, mostResultsSource };
}

function sortSourceResults(arr: SourceResult[]): SourceResult[] {
  return [...arr].sort((a, b) => {
    const order = { ok: 0, empty: 1, skipped: 2, timeout: 3, error: 4 };
    const ao = order[a.status] ?? 5;
    const bo = order[b.status] ?? 5;
    if (ao !== bo) return ao - bo;
    return b.resultCount - a.resultCount;
  });
}

export class ReportBuilder {
  private query: string;
  private totalSources: number;
  private startTime: number;
  private sourceResults: SourceResult[] = [];
  private inventory: SearchInventoryLog;
  _finished = false;
  private _reportId: string;

  constructor(query: string, totalSources: number, inventory?: Partial<SearchInventoryLog>) {
    this.query = query;
    this.totalSources = totalSources;
    this.startTime = Date.now();
    this.inventory = {
      benchmarkMode: !!inventory?.benchmarkMode,
      coldStartMode: !!inventory?.coldStartMode,
      loadedHostCount: Math.max(0, Math.trunc(inventory?.loadedHostCount || 0)),
      loadedPoolCount: Math.max(0, Math.trunc(inventory?.loadedPoolCount || 0)),
      sourcePackCount: Math.max(0, Math.trunc(inventory?.sourcePackCount || 0)),
      sourcePackOrigin: inventory?.sourcePackOrigin || '',
      sourcePackUpdatedAt: inventory?.sourcePackUpdatedAt || '',
      sourcePackIssuedAt: inventory?.sourcePackIssuedAt || '',
      sourcePackExpiresAt: inventory?.sourcePackExpiresAt || '',
    };
    this._reportId = `sr_${Date.now().toString(36)}`;
  }

  recordSource(
    name: string,
    origin: string,
    status: 'ok' | 'empty' | 'error' | 'timeout' | 'skipped',
    resultCount: number,
    durationMs: number,
    opts?: {
      error?: string;
      sampleTitles?: string[];
      sampleHashes?: string[];
      items?: ResultItemLog[];
      requiresWaf?: boolean;
      requiresBrowser?: boolean;
      qualityScore?: number;
      poolId?: string;
      uniqueResultCount?: number;
      relevantResultCount?: number;
      relevancePrecision?: number;
    },
  ) {
    this.sourceResults.push({
      name,
      origin,
      poolId: opts?.poolId || '',
      status,
      resultCount,
      uniqueResultCount: opts?.uniqueResultCount ?? resultCount,
      relevantResultCount: opts?.relevantResultCount || 0,
      relevancePrecision: opts?.relevancePrecision || 0,
      durationMs,
      error: opts?.error,
      sampleTitles: opts?.sampleTitles || [],
      sampleHashes: opts?.sampleHashes || [],
      items: opts?.items || [],
      requiresWaf: opts?.requiresWaf || false,
      requiresBrowser: opts?.requiresBrowser || false,
      qualityScore: opts?.qualityScore || 0,
    });
    // Incremental save: update the in-progress report in _reports
    this._upsertCurrent(false);
    schedulePersist();
  }

  setTotalSources(totalSources: number) {
    this.totalSources = Math.max(0, Math.trunc(totalSources || 0));
    this._upsertCurrent(false);
  }

  /** Save current state as a partial (interrupted) report */
  snapshot() {
    this._upsertCurrent(false);
    persistNow();
    notify();
  }

  /** Finalize the report. Aborted foreground handoffs remain partial. */
  finish(completed = true): SearchReport {
    if (this._finished) return _reports.find(r => r.id === this._reportId) || _reports[0];
    this._finished = true;
    this._upsertCurrent(completed);
    _currentBuilder = null;

    const report = _reports.find(r => r.id === this._reportId)!;
    // Always persist last-search-report.json for adb pull / dual-bait device tests.
    // (Previously gated on __DEV__, which is false in Hermes release-mode debug APKs.)
    try {
      printReport(report);
    } catch {
      /* ignore file write failures */
    }

    // Final persist
    persistNow();
    notify();
    return report;
  }

  /** Upsert current builder state into _reports array */
  private _upsertCurrent(completed: boolean) {
    const agg = computeAggregates(this.sourceResults);
    const report: SearchReport = {
      id: this._reportId,
      query: this.query,
      startedAt: new Date(this.startTime).toISOString(),
      totalDurationMs: Date.now() - this.startTime,
      completed,
      completedSources: this.sourceResults.length,
      sourceResults: sortSourceResults(this.sourceResults),
      totalSources: this.totalSources,
      attemptedHostCount: this.sourceResults.length,
      attemptedPoolCount: new Set(this.sourceResults.map((source) => source.poolId).filter(Boolean)).size,
      inventory: this.inventory,
      ...agg,
    };
    const idx = _reports.findIndex(r => r.id === this._reportId);
    if (idx >= 0) {
      _reports[idx] = report;
    } else {
      _reports.unshift(report);
      if (_reports.length > MAX_REPORTS) _reports.pop();
    }
  }
}

export function printReport(r: SearchReport) {
  const lines = [
    `\n══════ 搜索报告 ══════`,
    `关键词: "${r.query}"`,
    `时间: ${r.startedAt}`,
    `总耗时: ${(r.totalDurationMs / 1000).toFixed(1)}s`,
    `状态: ${r.completed ? '完成' : `中断 (${r.completedSources}/${r.totalSources})`}`,
    `───────────────────`,
    `计划/实际源主机: ${r.totalSources}/${r.attemptedHostCount}`,
    `运行时加载源主机/池: ${r.inventory.loadedHostCount}/${r.inventory.loadedPoolCount}`,
    `实际尝试池: ${r.attemptedPoolCount}`,
    `可访问: ${r.accessibleCount} (${pct(r.accessibleCount, r.totalSources)})`,
    `有结果: ${r.resultCount} (${pct(r.resultCount, r.totalSources)})`,
    `无结果: ${r.emptyCount}`,
    `失败:   ${r.errorCount}`,
    `跳过:   ${r.skippedCount}`,
    `磁力总数: ${r.totalMagnets}`,
    `最快源: ${r.fastestSource}`,
    `最多结果: ${r.mostResultsSource}`,
    `───────────────────`,
  ];
  const showSources = [
    ...r.sourceResults.filter(s => s.status === 'ok').slice(0, 10),
    ...r.sourceResults.filter(s => s.status === 'error' || s.status === 'timeout'),
  ];
  for (const s of showSources) {
    const icon = s.status === 'ok' ? '✓' : s.status === 'empty' ? '○' : '✗';
    const time = s.durationMs > 0 ? `${(s.durationMs / 1000).toFixed(1)}s` : '-';
    const detail = s.status === 'ok'
      ? `${s.resultCount} 条 [${time}]${s.sampleTitles[0] ? ' "' + s.sampleTitles[0].slice(0, 40) + '"' : ''}`
      : `${s.status} [${time}]${s.error ? ' ' + s.error.slice(0, 60) : ''}`;
    lines.push(`  ${icon} ${s.name}: ${detail}`);
  }
  lines.push(`══════════════════\n`);
  console.log(lines.join('\n'));
  // Write full report JSON to file for adb pull
  try {
    const dir = new Directory(Paths.document);
    const file = new File(dir, 'last-search-report.json');
    file.write(JSON.stringify(r, null, 2));
    console.log(`[SearchDebug] Report saved to: ${file.uri}`);
  } catch (e) {
    console.log(`[SearchDebug] Failed to save report: ${e}`);
  }
}

function pct(n: number, total: number): string {
  if (total === 0) return '0%';
  return Math.round(n / total * 100) + '%';
}

/** No-op builder for release builds — zero overhead, same interface. */
class NoopReportBuilder {
  _finished = true;
  recordSource() { /* no-op */ }
  setTotalSources() { /* no-op */ }
  snapshot() { /* no-op */ }
  finish(_completed = true): SearchReport {
    return {
      id: 'noop',
      query: '',
      startedAt: new Date().toISOString(),
      totalDurationMs: 0,
      completed: true,
      completedSources: 0,
      sourceResults: [],
      totalSources: 0,
      attemptedHostCount: 0,
      attemptedPoolCount: 0,
      inventory: {
        benchmarkMode: false,
        coldStartMode: false,
        loadedHostCount: 0,
        loadedPoolCount: 0,
        sourcePackCount: 0,
        sourcePackOrigin: '',
        sourcePackUpdatedAt: '',
        sourcePackIssuedAt: '',
        sourcePackExpiresAt: '',
      },
      accessibleCount: 0,
      resultCount: 0,
      emptyCount: 0,
      errorCount: 0,
      skippedCount: 0,
      totalMagnets: 0,
      fastestSource: '-',
      mostResultsSource: '-',
    };
  }
}
