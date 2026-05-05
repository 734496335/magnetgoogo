/**
 * VerifyManager — 3-tier verification strategy.
 *
 * Tier 0: Cookie bypass — fetchPage sends stored cookies, no challenge.
 * Tier 1: Silent WebView — invisible to user, auto-solves CF JS challenges.
 * Tier 2: Interactive WebView — shown to user for manual CAPTCHA/Turnstile.
 *
 * Session blacklist: origins that failed verification are skipped for the rest
 * of the app session, avoiding pointless retries.
 *
 * Flow:
 *   1. searchEngine detects challenge → requestVerification()
 *   2. Check blacklist → reject immediately if blacklisted
 *   3. Check origin cache → return cached cookies if available
 *   4. Emit request with silent=true → UI renders hidden WebView
 *   5a. Auto-resolves within SILENT_TIMEOUT → done, mark as auto-pass
 *   5b. Doesn't resolve → UI escalates to interactive modal
 *   6. User completes or cancels → result cached, blacklist if failed
 */

import { trackVerify } from './analytics';

export interface VerifyRequest {
  id: string;
  url: string;
  type: 'cloudflare' | 'cloudflare_block' | 'captcha' | 'ddos_guard' | 'spa_render';
  origin: string;
  siteName: string;
  silent: boolean;  // true = start in silent mode
}

export interface VerifyResult {
  success: boolean;
  cookies?: string;
  html?: string;
  error?: string;
}

type VerifyListener = (request: VerifyRequest) => void;

class _VerifyManager {
  private _listener: VerifyListener | null = null;
  private _pendingResolve: Map<string, (result: VerifyResult) => void> = new Map();
  private _counter = 0;
  private _timeout_challenge = 45_000; // 45s max for interactive challenge
  private _timeout_spa = 20_000;      // 20s max for SPA render (fast or fail)

  /** Per-origin cache: successful cookies or failure record. */
  private _originCache: Map<string, VerifyResult> = new Map();

  /** Session blacklist: origins that failed → skip for BLACKLIST_TTL_MS. */
  private _sessionBlacklist = new Map<string, number>();
  private static BLACKLIST_TTL_MS = 10 * 60_000; // 10 minutes

  /** Origins where challenge auto-resolved silently (never need modal). */
  private _autoPassOrigins = new Set<string>();

  /** Origins that required verification during this session (for priority sorting). */
  private _verifyOrigins = new Set<string>();

  /** Queue: only one request is emitted to UI at a time; others wait here. */
  private _queue: VerifyRequest[] = [];
  private _activeRequest: VerifyRequest | null = null;
  private _timers: Map<string, ReturnType<typeof setTimeout>> = new Map();

  // ── Public API ──

  hasOriginResult(origin: string): boolean {
    return this._originCache.has(origin);
  }

  getOriginResult(origin: string): VerifyResult | undefined {
    return this._originCache.get(origin);
  }

  isVerifyOrigin(origin: string): boolean { return this._verifyOrigins.has(origin); }
  markRequiresVerify(origin: string) { this._verifyOrigins.add(origin); }

  /** Is this origin blacklisted (with TTL)? */
  isBlacklisted(origin: string): boolean {
    const ts = this._sessionBlacklist.get(origin);
    if (ts === undefined) return false;
    if (Date.now() - ts > VerifyManager.BLACKLIST_TTL_MS) {
      this._sessionBlacklist.delete(origin);
      this._originCache.delete(origin);
      return false;
    }
    return true;
  }

  /** Has this origin previously auto-passed silently? */
  isAutoPass(origin: string): boolean {
    return this._autoPassOrigins.has(origin);
  }

  setListener(listener: VerifyListener | null) {
    this._listener = listener;
  }

  /**
   * Called by searchEngine when a challenge is detected.
   */
  requestVerification(
    url: string,
    type: VerifyRequest['type'],
    origin: string,
    siteName: string,
  ): Promise<VerifyResult> {
    // 1. Blacklist check (with TTL)
    if (this.isBlacklisted(origin)) {
      console.log(`[VerifyManager] ${origin} is blacklisted, skipping`);
      return Promise.resolve({ success: false, error: 'blacklisted' });
    }

    // 2. Cache check — return stored cookies (strip old HTML)
    //    Skip cache for spa_render: each query needs fresh HTML rendering
    if (type !== 'spa_render') {
      const cached = this._originCache.get(origin);
      if (cached) {
        if (!cached.success) {
          // Previously failed → blacklist now
          this._sessionBlacklist.set(origin, Date.now());
          console.log(`[VerifyManager] ${origin} previously failed → blacklisted`);
          return Promise.resolve({ success: false, error: 'previously_failed' });
        }
        console.log(`[VerifyManager] Using cached cookies for ${origin}`);
        return Promise.resolve({ ...cached, html: undefined });
      }
    }

    // 3. Track that this origin needs verification
    this._verifyOrigins.add(origin);

    // 4. Create request — always start silent
    const id = `verify_${++this._counter}_${Date.now()}`;
    const request: VerifyRequest = { id, url, type, origin, siteName, silent: true };
    (request as any)._startTs = Date.now();

    return new Promise<VerifyResult>((resolve) => {
      this._pendingResolve.set(id, resolve);

      if (!this._listener) {
        this._pendingResolve.delete(id);
        const noUiResult: VerifyResult = { success: false, error: 'no_ui_listener' };
        this._originCache.set(origin, noUiResult);
        resolve(noUiResult);
        return;
      }

      // Queue: only emit if no active request
      if (this._activeRequest) {
        console.log(`[VerifyManager] Queued ${siteName} (${this._queue.length + 1} in queue)`);
        this._queue.push(request);
      } else {
        this._activeRequest = request;
        this._startTimer(request);
        this._listener(request);
      }
    });
  }

  /** Start the timeout timer for a request (only when it becomes active). */
  private _startTimer(request: VerifyRequest) {
    const timer = setTimeout(() => {
      const resolve = this._pendingResolve.get(request.id);
      if (resolve) {
        this._pendingResolve.delete(request.id);
        const timeoutResult: VerifyResult = { success: false, error: 'timeout' };
        this._originCache.set(request.origin, timeoutResult);
        this._sessionBlacklist.set(request.origin, Date.now());
        console.log(`[VerifyManager] ${request.origin} timed out → blacklisted`);
        resolve(timeoutResult);
      }
      this._timers.delete(request.id);
      if (this._activeRequest?.id === request.id) {
        this._activeRequest = null;
        this._emitNext();
      }
    }, request.type === 'spa_render' ? this._timeout_spa : this._timeout_challenge);
    this._timers.set(request.id, timer);
  }

  /** Emit the next queued request to UI (if any). */
  private _emitNext() {
    if (this._queue.length === 0 || !this._listener) return;
    const next = this._queue.shift()!;
    // Skip if origin was already resolved/blacklisted while queued
    if (this.isBlacklisted(next.origin) || this._originCache.has(next.origin)) {
      const resolve = this._pendingResolve.get(next.id);
      if (resolve) {
        this._pendingResolve.delete(next.id);
        const cached = this._originCache.get(next.origin);
        resolve(cached || { success: false, error: 'blacklisted_while_queued' });
      }
      // Try next in queue
      this._emitNext();
      return;
    }
    console.log(`[VerifyManager] Dequeued ${next.siteName} (${this._queue.length} remaining)`);
    this._activeRequest = next;
    this._startTimer(next);
    this._listener(next);
  }

  /**
   * Called by WebView when verification completes (auto or manual).
   * @param wasSilent  true if resolved during silent phase (no user interaction)
   */
  submitResult(id: string, result: VerifyResult, origin?: string, wasSilent = false) {
    const resolve = this._pendingResolve.get(id);
    if (resolve) {
      this._pendingResolve.delete(id);
      if (origin) {
        this._originCache.set(origin, result);
        if (result.success && wasSilent) {
          this._autoPassOrigins.add(origin);
          console.log(`[VerifyManager] ${origin} auto-passed silently ✓`);
        }
        if (!result.success) {
          this._sessionBlacklist.set(origin, Date.now());
          console.log(`[VerifyManager] ${origin} failed → blacklisted`);
        }
      }
      // Analytics
      const req = this._activeRequest;
      if (req) {
        const ms = Date.now() - ((req as any)._startTs || Date.now());
        const tier = wasSilent ? 1 : 2;
        const r = result.success ? 'pass' : (result.error === 'timeout' ? 'timeout' : (result.error === 'user_cancelled' ? 'cancel' : 'fail'));
        trackVerify(req.siteName, tier, r as any, ms);
      }
      resolve(result);
    }
    // Clear timer and dequeue next request
    const timer = this._timers.get(id);
    if (timer) {
      clearTimeout(timer);
      this._timers.delete(id);
    }
    if (this._activeRequest?.id === id) {
      this._activeRequest = null;
      this._emitNext();
    }
  }

  /**
   * Cancel a pending verification (user dismisses interactive modal).
   */
  cancel(id: string, origin?: string) {
    if (origin) {
      this._sessionBlacklist.set(origin, Date.now());
      console.log(`[VerifyManager] ${origin} cancelled → blacklisted`);
    }
    // submitResult will handle dequeue
    this.submitResult(id, { success: false, error: 'user_cancelled' }, origin);
  }

  get hasPending(): boolean {
    return this._pendingResolve.size > 0;
  }

  /** Session stats for debugging. */
  getStats() {
    return {
      blacklisted: [...this._sessionBlacklist.keys()],
      autoPass: [...this._autoPassOrigins],
      cached: this._originCache.size,
      pending: this._pendingResolve.size,
      queued: this._queue.length,
    };
  }
}

/** Singleton — shared between searchEngine and UI layer */
export const VerifyManager = new _VerifyManager();
