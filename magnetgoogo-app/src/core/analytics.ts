/**
 * Analytics — lightweight anonymous event collection + batch upload.
 *
 * Events are queued locally and flushed to the API on:
 *   1. App startup (previous session's events)
 *   2. Periodically (every FLUSH_INTERVAL while app is active)
 *   3. Manually via flush()
 *
 * No PII collected. Device ID is a random UUID generated once and persisted.
 */
import { Platform, AppState, type AppStateStatus } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAppVersion } from './configChecker';

const EVENTS_API = 'https://api.naoshiquan.com/api/events';
const STORAGE_KEY = 'mg_analytics_queue';
const DEVICE_ID_KEY = 'mg_device_id';
const FLUSH_INTERVAL = 5 * 60_000; // 5 min
const MAX_QUEUE = 200; // cap local queue size

// ── Types ──

interface AnalyticsEvent {
  e: string;       // event name
  ts: number;      // timestamp ms
  [k: string]: any;
}

// ── State ──

let _queue: AnalyticsEvent[] = [];
let _deviceId = '';
let _flushTimer: ReturnType<typeof setInterval> | null = null;
let _flushing = false;

// ── Device ID ──

async function ensureDeviceId(): Promise<string> {
  if (_deviceId) return _deviceId;
  try {
    const stored = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (stored) {
      _deviceId = stored;
      return stored;
    }
  } catch { /* ignore */ }
  // Generate a random ID (no crypto needed, just uniqueness)
  const id = `d_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  _deviceId = id;
  try { await AsyncStorage.setItem(DEVICE_ID_KEY, id); } catch { /* ignore */ }
  return id;
}

// ── Queue management ──

/** Track an event. Fire-and-forget, never throws. */
export function track(name: string, props?: Record<string, any>) {
  const event: AnalyticsEvent = { e: name, ts: Date.now(), ...props };
  _queue.push(event);
  if (_queue.length > MAX_QUEUE) _queue.shift(); // drop oldest
}

/** Persist queue to AsyncStorage (called before flush or on background). */
async function persistQueue() {
  try {
    if (_queue.length === 0) {
      await AsyncStorage.removeItem(STORAGE_KEY);
    } else {
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_queue));
    }
  } catch { /* ignore */ }
}

/** Load any queued events from previous session. */
async function loadQueue() {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (raw) {
      const prev: AnalyticsEvent[] = JSON.parse(raw);
      _queue = [...prev, ..._queue];
      if (_queue.length > MAX_QUEUE) _queue = _queue.slice(-MAX_QUEUE);
    }
  } catch { /* ignore */ }
}

// ── Flush ──

/** Send queued events to API. Safe to call anytime. */
export async function flush() {
  if (_flushing || _queue.length === 0) return;
  _flushing = true;

  const did = await ensureDeviceId();
  const batch = _queue.splice(0, _queue.length); // take all

  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 10_000);
    const resp = await fetch(EVENTS_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-App-Version': getAppVersion(),
      },
      body: JSON.stringify({
        did,
        app_v: getAppVersion(),
        os: Platform.OS,
        os_v: String(Platform.Version),
        ts: Date.now(),
        events: batch,
      }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);

    if (!resp.ok) {
      // Put events back for retry
      _queue = [...batch, ..._queue].slice(-MAX_QUEUE);
      console.log(`[Analytics] Flush failed: HTTP ${resp.status}`);
    } else {
      console.log(`[Analytics] Flushed ${batch.length} events`);
      await AsyncStorage.removeItem(STORAGE_KEY);
    }
  } catch (e: any) {
    // Network error → put events back
    _queue = [...batch, ..._queue].slice(-MAX_QUEUE);
    console.log(`[Analytics] Flush error: ${e.message}`);
  } finally {
    _flushing = false;
    await persistQueue();
  }
}

// ── Lifecycle ──

/** Initialize analytics. Call once at app startup. */
export async function initAnalytics() {
  await ensureDeviceId();
  await loadQueue();

  // Track app start
  track('app_start');

  // Flush previous session's events
  flush();

  // Start periodic flush
  if (_flushTimer) clearInterval(_flushTimer);
  _flushTimer = setInterval(() => {
    if (_queue.length > 0) flush();
  }, FLUSH_INTERVAL);

  // Flush when app goes to background (prevents data loss on kill)
  AppState.addEventListener('change', (state: AppStateStatus) => {
    if (state === 'background' || state === 'inactive') {
      if (_queue.length > 0) flush();
    }
  });
}

// ── Convenience helpers ──

export function trackSearch(query: string, resultCount: number) {
  track('search', { q: query, n: resultCount });
}

export function trackCopy() {
  track('copy_magnet');
}

export function trackOpen() {
  track('open_magnet');
}

export function trackSourceResult(
  srcName: string,
  ok: boolean,
  count: number,
  ms: number,
  reason?: string,
) {
  if (ok && count > 0) {
    track('src_ok', { src: srcName, n: count, ms });
  } else if (ok) {
    // Reachable but no results — still valuable for health tracking
    track('src_empty', { src: srcName, ms });
  } else {
    track('src_fail', { src: srcName, reason: reason || 'unknown', ms });
  }
}

export function trackVerify(
  srcName: string,
  tier: number,
  result: 'pass' | 'fail' | 'timeout' | 'cancel',
  ms: number,
) {
  track('verify', { src: srcName, tier, result, ms });
}
