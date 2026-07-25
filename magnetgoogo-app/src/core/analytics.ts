import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

const ENDPOINT = 'https://api.naoshiquan.com/api/events';
const DEVICE_ID_KEY = 'mg_device_id';
const QUEUE_KEY = 'mg_analytics_queue';
const MAX_QUEUE = 200;
const MAX_BATCH_EVENTS = 40;

export type AnalyticsEventName =
  | 'app_start'
  | 'source_sync_result'
  | 'search_submitted'
  | 'search_completed'
  | 'open_magnet'
  | 'copy_magnet';

export interface SearchSourceRollup {
  src: string;
  cat: string;
  called: number;
  ok: number;
  empty: number;
  fail: number;
  results: number;
  hit_searches: number;
  ms: number;
  verify: number;
}

interface AnalyticsEventBase {
  id: string;
  e: AnalyticsEventName;
  ts: number;
}

interface AppStartEvent extends AnalyticsEventBase {
  e: 'app_start';
}

interface SourceSyncEvent extends AnalyticsEventBase {
  e: 'source_sync_result';
  mode: 'cache' | 'remote';
  success: 0 | 1;
  source_count: number;
  duration_ms?: number;
  error_code?: string;
}

interface SearchSubmittedEvent extends AnalyticsEventBase {
  e: 'search_submitted';
  search_id: string;
  query_len: number;
  source_count: number;
  background_capable: 0 | 1;
}

interface SearchCompletedEvent extends AnalyticsEventBase {
  e: 'search_completed';
  search_id: string;
  query_len: number;
  source_count: number;
  source_done: number;
  result_count: number;
  success: 0 | 1;
  zero_result: 0 | 1;
  aborted: 0 | 1;
  background: 0 | 1;
  duration_ms: number;
  ttfr_ms?: number;
  source_rollup: SearchSourceRollup[];
}

interface MagnetActionEvent extends AnalyticsEventBase {
  e: 'open_magnet' | 'copy_magnet';
  search_id?: string;
}

type AnalyticsEvent =
  | AppStartEvent
  | SourceSyncEvent
  | SearchSubmittedEvent
  | SearchCompletedEvent
  | MagnetActionEvent;

export interface SearchSubmitParams {
  term: string;
  sourceCount: number;
  backgroundCapable?: boolean;
}

export interface SearchCompleteParams {
  searchId: string;
  term: string;
  sourceCount: number;
  doneCount: number;
  resultCount: number;
  aborted: boolean;
  background?: boolean;
  durationMs: number;
  timeToFirstResultMs?: number | null;
  sourceRollup: SearchSourceRollup[];
}

let _deviceId = '';
let _queue: AnalyticsEvent[] = [];
let _inited = false;
let _flushing = false;
let _flushTimer: ReturnType<typeof setTimeout> | null = null;

function appVersion(): string {
  return Constants.expoConfig?.version || '0.1.14';
}

function osVersion(): string {
  const v = Platform.Version;
  return typeof v === 'string' ? v : String(v ?? '');
}

function randomId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function sanitizeMs(value: number | null | undefined): number | undefined {
  if (!Number.isFinite(value as number)) return undefined;
  const v = Math.max(0, Math.round(value as number));
  return v;
}

function boundedQueue(events: AnalyticsEvent[]): AnalyticsEvent[] {
  if (events.length <= MAX_QUEUE) return events;
  return events.slice(events.length - MAX_QUEUE);
}

async function persistQueue() {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(_queue));
}

async function ensureDeviceId(): Promise<string> {
  if (_deviceId) return _deviceId;
  const cached = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (cached) {
    _deviceId = cached;
    return _deviceId;
  }
  _deviceId = randomId('dev');
  await AsyncStorage.setItem(DEVICE_ID_KEY, _deviceId);
  return _deviceId;
}

function scheduleFlush(delayMs = 5000) {
  if (_flushTimer) return;
  _flushTimer = setTimeout(() => {
    _flushTimer = null;
    void flush();
  }, delayMs);
}

async function pushEvent(event: AnalyticsEvent) {
  _queue = boundedQueue([..._queue, event]);
  await persistQueue();
  if (_queue.length >= 8) {
    void flush();
  } else {
    scheduleFlush();
  }
}

export function makeSearchId(): string {
  return randomId('search');
}

export async function initAnalytics(): Promise<void> {
  if (_inited) return;
  _inited = true;
  await ensureDeviceId();
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        _queue = boundedQueue(parsed.filter((item) => item && item.id && item.e && item.ts));
      }
    }
  } catch {
    _queue = [];
  }
  await trackAppStart();
  scheduleFlush(2500);
}

export async function flush(): Promise<void> {
  if (_flushing || _queue.length === 0) return;
  _flushing = true;
  try {
    const did = await ensureDeviceId();
    const snapshot = _queue.slice(0, MAX_BATCH_EVENTS);
    if (snapshot.length === 0) return;
    const snapshotIds = new Set(snapshot.map((item) => item.id));
    await persistQueue();
    const resp = await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        batch_id: randomId('batch'),
        did,
        app_v: appVersion(),
        os: Platform.OS,
        os_v: osVersion(),
        ts: Date.now(),
        events: snapshot,
      }),
    });
    if (!resp.ok) return;
    _queue = _queue.filter((item) => !snapshotIds.has(item.id));
    await persistQueue();
    if (_queue.length > 0) scheduleFlush(1200);
  } catch {
    scheduleFlush(8000);
  } finally {
    _flushing = false;
  }
}

async function trackAppStart() {
  await pushEvent({
    id: randomId('app'),
    e: 'app_start',
    ts: Date.now(),
  });
}

export async function trackSourceSyncResult(params: {
  mode: 'cache' | 'remote';
  success: boolean;
  sourceCount: number;
  durationMs?: number;
  errorCode?: string;
}) {
  await pushEvent({
    id: randomId('srcsync'),
    e: 'source_sync_result',
    ts: Date.now(),
    mode: params.mode,
    success: params.success ? 1 : 0,
    source_count: Math.max(0, Math.round(params.sourceCount || 0)),
    duration_ms: sanitizeMs(params.durationMs),
    error_code: params.errorCode || undefined,
  });
}

export async function trackSearchSubmitted(params: SearchSubmitParams): Promise<string> {
  const searchId = makeSearchId();
  await pushEvent({
    id: randomId('ss'),
    e: 'search_submitted',
    ts: Date.now(),
    search_id: searchId,
    query_len: Math.min((params.term || '').trim().length, 100),
    source_count: Math.max(0, Math.round(params.sourceCount || 0)),
    background_capable: params.backgroundCapable === false ? 0 : 1,
  });
  return searchId;
}

export async function trackSearchCompleted(params: SearchCompleteParams) {
  await pushEvent({
    id: randomId('sc'),
    e: 'search_completed',
    ts: Date.now(),
    search_id: params.searchId,
    query_len: Math.min((params.term || '').trim().length, 100),
    source_count: Math.max(0, Math.round(params.sourceCount || 0)),
    source_done: Math.max(0, Math.round(params.doneCount || 0)),
    result_count: Math.max(0, Math.round(params.resultCount || 0)),
    success: params.aborted ? 0 : 1,
    zero_result: params.resultCount > 0 ? 0 : 1,
    aborted: params.aborted ? 1 : 0,
    background: params.background ? 1 : 0,
    duration_ms: Math.max(0, Math.round(params.durationMs || 0)),
    ttfr_ms: sanitizeMs(params.timeToFirstResultMs),
    source_rollup: Array.isArray(params.sourceRollup) ? params.sourceRollup.slice(0, 120) : [],
  });
}

async function trackMagnetAction(action: 'open_magnet' | 'copy_magnet', searchId?: string) {
  await pushEvent({
    id: randomId(action === 'open_magnet' ? 'open' : 'copy'),
    e: action,
    ts: Date.now(),
    search_id: searchId || undefined,
  });
}

export function trackCopy(searchId?: string) {
  void trackMagnetAction('copy_magnet', searchId);
}

export function trackOpen(searchId?: string) {
  void trackMagnetAction('open_magnet', searchId);
}

// Compatibility no-op: verification no longer emits standalone analytics events.
export function trackVerify(_siteName: string, _tier: number, _result: string, _ms: number) {}
