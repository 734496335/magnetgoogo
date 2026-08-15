import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState, Platform, type AppStateStatus } from 'react-native';
import Constants from 'expo-constants';
import * as Application from 'expo-application';
import * as Crypto from 'expo-crypto';
import {
  classifyQuery,
  compactSourceRollup,
  dedupeEventsById,
  deterministicSample,
  selectBatchByBytes,
  utf8ByteLength,
} from './analyticsPolicy';

const ENDPOINT = process.env.EXPO_PUBLIC_ANALYTICS_ENDPOINT || 'https://api.naoshiquan.com/api/events';
const LEGACY_DID_KEY = 'mg_device_id';
const QUEUE_KEY = 'mg_analytics_queue';
const FIRST_OPEN_STATE_KEY = 'mg_analytics_first_open_v2';
const SCHEMA_VERSION = 2;
const MAX_QUEUE = 200;
const MAX_BATCH_EVENTS = 40;
const MAX_BATCH_BYTES = 24 * 1024;
const FLUSH_EVENT_THRESHOLD = 16;
const SOURCE_SAMPLE_DENOMINATOR = 10;
const SOURCE_SAMPLE_LIMIT = 48;
const REQUEST_TIMEOUT_MS = 12_000;
const INITIAL_RETRY_MS = 15_000;
const MAX_RETRY_MS = 5 * 60_000;

export type AnalyticsEventName =
  | 'first_open'
  | 'app_start'
  | 'source_sync_result'
  | 'search_submitted'
  | 'search_completed'
  | 'resources_tab_view'
  | 'resource_feed_refresh_result'
  | 'open_magnet'
  | 'copy_magnet';

export interface SearchSourceRollup {
  src: string;
  cat: string;
  pool?: string;
  called: number;
  ok: number;
  empty: number;
  fail: number;
  results: number;
  unique_results?: number;
  relevant_results?: number;
  relevant_precision?: number;
  hit_searches: number;
  ms: number;
  verify: number;
}

interface AnalyticsEventBase {
  id: string;
  e: AnalyticsEventName;
  ts: number;
  session_id: string;
}

interface FirstOpenEvent extends AnalyticsEventBase {
  e: 'first_open';
  installation_time: number;
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
  query_type: ReturnType<typeof classifyQuery>;
  source_count: number;
  background_capable: 0 | 1;
}

interface SearchCompletedEvent extends AnalyticsEventBase {
  e: 'search_completed';
  search_id: string;
  query_len: number;
  query_type: ReturnType<typeof classifyQuery>;
  source_count: number;
  source_done: number;
  result_count: number;
  success: 0 | 1;
  zero_result: 0 | 1;
  aborted: 0 | 1;
  background: 0 | 1;
  duration_ms: number;
  ttfr_ms?: number;
  source_summary: ReturnType<typeof compactSourceRollup>['summary'];
  source_sample?: ReturnType<typeof compactSourceRollup>['sample'];
}

export type ResourceRefreshReason = 'focus' | 'foreground' | 'foreground_interval' | 'manual';

interface ResourcesTabViewEvent extends AnalyticsEventBase {
  e: 'resources_tab_view';
  content_kind: 'movie' | 'series';
}

interface ResourceFeedRefreshEvent extends AnalyticsEventBase {
  e: 'resource_feed_refresh_result';
  content_kind: 'movie' | 'series';
  reason: ResourceRefreshReason;
  success: 0 | 1;
  changed: 0 | 1;
  release_id?: string;
  duration_ms?: number;
  error_code?: string;
}

export type AnalyticsSurface = 'search' | 'media_detail' | 'unknown';
export type AnalyticsActionKind = 'single' | 'all';

interface MagnetActionEvent extends AnalyticsEventBase {
  e: 'open_magnet' | 'copy_magnet';
  search_id?: string;
  surface: AnalyticsSurface;
  action: AnalyticsActionKind;
}

type AnalyticsEvent =
  | FirstOpenEvent
  | AppStartEvent
  | SourceSyncEvent
  | SearchSubmittedEvent
  | SearchCompletedEvent
  | ResourcesTabViewEvent
  | ResourceFeedRefreshEvent
  | MagnetActionEvent;

interface AnalyticsIdentity {
  deviceId: string;
  deviceIdKind: 'android_id_hash' | 'install_fallback';
  installId: string;
  legacyDid: string;
  packageName: string;
  buildType: 'debug' | 'release';
  distribution: 'direct_apk';
  installationTime: number;
  versionCode: string;
}

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

export interface ResourceFeedRefreshParams {
  kind: 'movie' | 'series';
  reason: ResourceRefreshReason;
  success: boolean;
  changed: boolean;
  releaseId?: string | null;
  durationMs?: number;
  errorCode?: string;
}

export interface MagnetActionContext {
  searchId?: string;
  surface?: AnalyticsSurface;
  action?: AnalyticsActionKind;
}

let _identity: AnalyticsIdentity | null = null;
let _queue: AnalyticsEvent[] = [];
let _inited = false;
let _flushing = false;
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _flushDueAt = 0;
let _persistTimer: ReturnType<typeof setTimeout> | null = null;
let _persistChain: Promise<void> = Promise.resolve();
let _appStateSubscription: { remove: () => void } | null = null;
let _retryDelayMs = INITIAL_RETRY_MS;
let _appState: AppStateStatus = AppState.currentState;
const _sessionId = randomId('session');

function appVersion(): string {
  return Constants.expoConfig?.version || '0.1.14';
}

function osVersion(): string {
  const value = Platform.Version;
  return typeof value === 'string' ? value : String(value ?? '');
}

function randomId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function sanitizeMs(value: number | null | undefined): number | undefined {
  if (!Number.isFinite(value as number)) return undefined;
  return Math.max(0, Math.round(value as number));
}

function trimText(value: string | undefined, maxLength: number): string | undefined {
  const normalized = (value || '').trim().slice(0, maxLength);
  return normalized || undefined;
}

function boundedQueue(events: AnalyticsEvent[]): AnalyticsEvent[] {
  const deduped = dedupeEventsById(events) as AnalyticsEvent[];
  return deduped.length <= MAX_QUEUE ? deduped : deduped.slice(deduped.length - MAX_QUEUE);
}

function persistQueue(): Promise<void> {
  const payload = JSON.stringify(_queue);
  _persistChain = _persistChain
    .catch(() => {})
    .then(async () => {
      try {
        await AsyncStorage.setItem(QUEUE_KEY, payload);
      } catch {
        // Analytics persistence must never block the product path.
      }
    });
  return _persistChain;
}

function schedulePersist(delayMs = 250): void {
  if (_persistTimer) return;
  _persistTimer = setTimeout(() => {
    _persistTimer = null;
    void persistQueue();
  }, delayMs);
}

async function ensureLegacyDid(): Promise<string> {
  try {
    const cached = await AsyncStorage.getItem(LEGACY_DID_KEY);
    if (cached) return cached;
  } catch {
    // Continue with an in-memory legacy ID when storage is temporarily unavailable.
  }
  const created = randomId('legacy');
  try {
    await AsyncStorage.setItem(LEGACY_DID_KEY, created);
  } catch {
    // The v2 installation ID is derived from native installation time and does not depend on this write.
  }
  return created;
}

async function sha256(value: string): Promise<string> {
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, value);
}

async function ensureIdentity(): Promise<AnalyticsIdentity> {
  if (_identity) return _identity;

  const legacyDid = await ensureLegacyDid();
  const packageName = Application.applicationId || Constants.expoConfig?.android?.package || 'com.magnetgoogo.app';
  const buildType: 'debug' | 'release' = packageName.endsWith('.debug') ? 'debug' : 'release';
  let deviceIdKind: AnalyticsIdentity['deviceIdKind'] = 'install_fallback';
  let deviceSeed = `legacy:${legacyDid}`;

  if (Platform.OS === 'android') {
    try {
      const androidId = Application.getAndroidId();
      if (androidId) {
        deviceSeed = `android:${packageName.replace(/\.debug$/, '')}:${androidId}`;
        deviceIdKind = 'android_id_hash';
      }
    } catch {
      // Older or unusual Android builds fall back to the legacy installation ID.
    }
  }

  let installationTime = 0;
  try {
    const nativeInstallationTime = (await Application.getInstallationTimeAsync()).getTime();
    if (Number.isFinite(nativeInstallationTime) && nativeInstallationTime > 0) {
      installationTime = nativeInstallationTime;
    }
  } catch {
    // A zero value makes the fallback installation ID stable instead of changing every process start.
  }

  const deviceId = `dv2_${await sha256(`magnetgoogo:device:v2:${deviceSeed}`)}`;
  const installSeed = installationTime > 0
    ? `${deviceSeed}:installed:${installationTime}`
    : `legacy:${legacyDid}`;
  _identity = {
    deviceId,
    deviceIdKind,
    installId: `iv2_${await sha256(`magnetgoogo:install:v2:${installSeed}`)}`,
    legacyDid,
    packageName,
    buildType,
    distribution: 'direct_apk',
    installationTime,
    versionCode: Application.nativeBuildVersion || '',
  };
  return _identity;
}

function scheduleFlush(delayMs = 20_000): void {
  const dueAt = Date.now() + Math.max(0, delayMs);
  if (_flushTimer && _flushDueAt <= dueAt) return;
  if (_flushTimer) clearTimeout(_flushTimer);
  _flushDueAt = dueAt;
  _flushTimer = setTimeout(() => {
    _flushTimer = null;
    _flushDueAt = 0;
    void flush('scheduled');
  }, Math.max(0, dueAt - Date.now()));
}

function queueEvent(event: AnalyticsEvent): void {
  _queue = boundedQueue([..._queue, event]);
  schedulePersist();
  if (_queue.length >= FLUSH_EVENT_THRESHOLD) {
    scheduleFlush(1500);
  } else {
    scheduleFlush();
  }
}

function deterministicBatchId(events: AnalyticsEvent[]): string {
  const first = events[0];
  const last = events[events.length - 1];
  const firstSuffix = first.id.slice(-12).replace(/[^a-zA-Z0-9_-]/g, '');
  const lastSuffix = last.id.slice(-12).replace(/[^a-zA-Z0-9_-]/g, '');
  return `b2_${first.ts}_${last.ts}_${events.length}_${firstSuffix}_${lastSuffix}`;
}

function batchEnvelope(identity: AnalyticsIdentity, batchId: string): Record<string, unknown> {
  return {
    schema_v: SCHEMA_VERSION,
    batch_id: batchId,
    did: identity.legacyDid,
    legacy_did: identity.legacyDid,
    device_id: identity.deviceId,
    device_id_kind: identity.deviceIdKind,
    install_id: identity.installId,
    app_v: appVersion(),
    version_code: identity.versionCode,
    package_name: identity.packageName,
    build_type: identity.buildType,
    distribution: identity.distribution,
    session_id: _sessionId,
    os: Platform.OS,
    os_v: osVersion(),
    ts: Date.now(),
  };
}

function debugLog(message: string, fields: Record<string, unknown>): void {
  if (_identity?.buildType !== 'debug') return;
  console.log('[AnalyticsV2]', JSON.stringify({ message, ...fields }));
}

async function markFirstOpenSent(snapshot: AnalyticsEvent[], installId: string): Promise<void> {
  if (snapshot.some((event) => event.e === 'first_open')) {
    try {
      await AsyncStorage.setItem(FIRST_OPEN_STATE_KEY, installId);
    } catch {
      // A later launch will safely resend the deterministic event ID.
    }
  }
}

function handleAppStateChange(nextState: AppStateStatus): void {
  const previous = _appState;
  _appState = nextState;
  if (nextState === 'background' || nextState === 'inactive') {
    void persistQueue();
    void flush('background');
  } else if (nextState === 'active' && previous !== 'active' && _queue.length > 0) {
    scheduleFlush(5000);
  }
}

export function makeSearchId(): string {
  return randomId('search');
}

export async function initAnalytics(): Promise<void> {
  if (_inited) return;
  _inited = true;

  try {
    try {
      const raw = await AsyncStorage.getItem(QUEUE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          const persisted = parsed.filter((item) => item && item.id && item.e && item.ts);
          _queue = boundedQueue([...persisted, ..._queue]);
        }
      }
    } catch {
      // Preserve events already queued during asynchronous app initialization.
    }

    const identity = await ensureIdentity();
    const firstOpenState = await AsyncStorage.getItem(FIRST_OPEN_STATE_KEY).catch(() => null);
    if (firstOpenState !== identity.installId) {
      queueEvent({
        id: `first_open_${identity.installId}`,
        e: 'first_open',
        ts: Date.now(),
        session_id: _sessionId,
        installation_time: identity.installationTime,
      });
    }

    queueEvent({
      id: randomId('app'),
      e: 'app_start',
      ts: Date.now(),
      session_id: _sessionId,
    });

    if (!_appStateSubscription) {
      _appStateSubscription = AppState.addEventListener('change', handleAppStateChange);
    }
    scheduleFlush(_queue.length > 2 ? 5000 : 15_000);
    debugLog('initialized', {
      endpoint: ENDPOINT,
      queue_events: _queue.length,
      device_id_kind: identity.deviceIdKind,
      package_name: identity.packageName,
    });
  } catch (error) {
    _inited = false;
    if (typeof __DEV__ !== 'undefined' && __DEV__) {
      console.warn('[AnalyticsV2]', {
        message: 'init_failed',
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
}

export async function flush(reason = 'manual'): Promise<void> {
  if (_flushing || _queue.length === 0) return;
  if (_persistTimer) {
    clearTimeout(_persistTimer);
    _persistTimer = null;
  }
  _flushing = true;
  let retryAfterMs = 0;

  try {
    const identity = await ensureIdentity();
    const sizingEnvelope = batchEnvelope(identity, 'b2_0000000000000_0000000000000_40_abcdefghijkl_abcdefghijkl');
    let snapshot = selectBatchByBytes(
      _queue,
      sizingEnvelope,
      MAX_BATCH_BYTES,
      MAX_BATCH_EVENTS,
    ) as AnalyticsEvent[];

    if (snapshot.length === 0) {
      const first = _queue[0] as SearchCompletedEvent;
      if (first?.e === 'search_completed' && first.source_sample) {
        const compacted = { ...first };
        delete compacted.source_sample;
        _queue = [compacted, ..._queue.slice(1)];
        snapshot = [compacted];
      } else {
        debugLog('dropped_oversized_event', { event: first?.e || 'unknown' });
        _queue = _queue.slice(1);
        await persistQueue();
        return;
      }
    }

    const batchId = deterministicBatchId(snapshot);
    const envelope = batchEnvelope(identity, batchId);
    while (snapshot.length > 1 && utf8ByteLength(JSON.stringify({ ...envelope, events: snapshot })) > MAX_BATCH_BYTES) {
      snapshot = snapshot.slice(0, -1);
    }

    const snapshotIds = new Set(snapshot.map((event) => event.id));
    const body = JSON.stringify({ ...envelope, events: snapshot });
    await persistQueue();

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response: Response;
    try {
      response = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (response.status === 429) {
      try {
        const payload = await response.json();
        retryAfterMs = Math.max(5000, Math.min(MAX_RETRY_MS, Number(payload?.retry_after || 15) * 1000));
      } catch {
        retryAfterMs = _retryDelayMs;
      }
      return;
    }
    if (!response.ok) {
      retryAfterMs = _retryDelayMs;
      return;
    }

    _queue = _queue.filter((event) => !snapshotIds.has(event.id));
    await markFirstOpenSent(snapshot, identity.installId);
    await persistQueue();
    _retryDelayMs = INITIAL_RETRY_MS;
    debugLog('flush_ok', {
      reason,
      batch_id: batchId,
      events: snapshot.length,
      bytes: utf8ByteLength(body),
      remaining: _queue.length,
    });
    if (_queue.length > 0) scheduleFlush(6000);
  } catch (error) {
    retryAfterMs = _retryDelayMs;
    debugLog('flush_failed', {
      reason,
      error: error instanceof Error ? error.message : String(error),
      retry_ms: retryAfterMs,
    });
  } finally {
    _flushing = false;
    if (retryAfterMs > 0 && _queue.length > 0) {
      _retryDelayMs = Math.min(MAX_RETRY_MS, Math.max(INITIAL_RETRY_MS, retryAfterMs * 2));
      scheduleFlush(retryAfterMs);
    }
  }
}

export async function trackSourceSyncResult(params: {
  mode: 'cache' | 'remote';
  success: boolean;
  sourceCount: number;
  durationMs?: number;
  errorCode?: string;
}): Promise<void> {
  queueEvent({
    id: randomId('srcsync'),
    e: 'source_sync_result',
    ts: Date.now(),
    session_id: _sessionId,
    mode: params.mode,
    success: params.success ? 1 : 0,
    source_count: Math.max(0, Math.round(params.sourceCount || 0)),
    duration_ms: sanitizeMs(params.durationMs),
    error_code: trimText(params.errorCode, 120),
  });
}

export async function trackSearchSubmitted(params: SearchSubmitParams): Promise<string> {
  const searchId = makeSearchId();
  queueEvent({
    id: `ss_${searchId}`,
    e: 'search_submitted',
    ts: Date.now(),
    session_id: _sessionId,
    search_id: searchId,
    query_len: Math.min((params.term || '').trim().length, 100),
    query_type: classifyQuery(params.term),
    source_count: Math.max(0, Math.round(params.sourceCount || 0)),
    background_capable: params.backgroundCapable === false ? 0 : 1,
  });
  return searchId;
}

export async function trackSearchCompleted(params: SearchCompleteParams): Promise<void> {
  const compact = compactSourceRollup(
    params.sourceRollup,
    deterministicSample(params.searchId, SOURCE_SAMPLE_DENOMINATOR),
    SOURCE_SAMPLE_LIMIT,
  );
  queueEvent({
    id: `sc_${params.searchId}`,
    e: 'search_completed',
    ts: Date.now(),
    session_id: _sessionId,
    search_id: params.searchId,
    query_len: Math.min((params.term || '').trim().length, 100),
    query_type: classifyQuery(params.term),
    source_count: Math.max(0, Math.round(params.sourceCount || 0)),
    source_done: Math.max(0, Math.round(params.doneCount || 0)),
    result_count: Math.max(0, Math.round(params.resultCount || 0)),
    success: params.aborted ? 0 : 1,
    zero_result: params.resultCount > 0 ? 0 : 1,
    aborted: params.aborted ? 1 : 0,
    background: params.background ? 1 : 0,
    duration_ms: Math.max(0, Math.round(params.durationMs || 0)),
    ttfr_ms: sanitizeMs(params.timeToFirstResultMs),
    source_summary: compact.summary,
    source_sample: compact.sample,
  });
}

export function trackResourcesTabView(kind: 'movie' | 'series'): void {
  queueEvent({
    id: randomId('resources'),
    e: 'resources_tab_view',
    ts: Date.now(),
    session_id: _sessionId,
    content_kind: kind,
  });
}

export function trackResourceFeedRefreshResult(params: ResourceFeedRefreshParams): void {
  queueEvent({
    id: randomId('refresh'),
    e: 'resource_feed_refresh_result',
    ts: Date.now(),
    session_id: _sessionId,
    content_kind: params.kind,
    reason: params.reason,
    success: params.success ? 1 : 0,
    changed: params.changed ? 1 : 0,
    release_id: trimText(params.releaseId || undefined, 120),
    duration_ms: sanitizeMs(params.durationMs),
    error_code: trimText(params.errorCode, 120),
  });
}

function normalizeActionContext(value?: string | MagnetActionContext): Required<Pick<MagnetActionContext, 'surface' | 'action'>> & Pick<MagnetActionContext, 'searchId'> {
  if (typeof value === 'string') {
    return { searchId: value, surface: 'search', action: 'single' };
  }
  return {
    searchId: value?.searchId,
    surface: value?.surface || 'unknown',
    action: value?.action || 'single',
  };
}

async function trackMagnetAction(
  eventName: 'open_magnet' | 'copy_magnet',
  value?: string | MagnetActionContext,
): Promise<void> {
  const context = normalizeActionContext(value);
  queueEvent({
    id: randomId(eventName === 'open_magnet' ? 'open' : 'copy'),
    e: eventName,
    ts: Date.now(),
    session_id: _sessionId,
    search_id: context.searchId,
    surface: context.surface,
    action: context.action,
  });
}

export function trackCopy(value?: string | MagnetActionContext): void {
  void trackMagnetAction('copy_magnet', value);
}

export function trackOpen(value?: string | MagnetActionContext): void {
  void trackMagnetAction('open_magnet', value);
}

// Compatibility no-op: verification no longer emits standalone analytics events.
export function trackVerify(_siteName: string, _tier: number, _result: string, _ms: number): void {}
