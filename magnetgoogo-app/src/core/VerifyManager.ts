/**
 * VerifyManager — Legado-style verification bridge.
 *
 * Flow (mirrors Legado's SourceVerificationHelp):
 *   1. searchEngine detects a challenge (CF / captcha / SPA)
 *   2. Calls VerifyManager.requestVerification(url, type)
 *   3. This returns a Promise that parks the search task
 *   4. UI layer picks up the pending request → shows WebView modal
 *   5. User (or auto-solve) completes the challenge in WebView
 *   6. WebView injectedJS extracts cookies + rendered HTML
 *   7. UI calls VerifyManager.submitResult() → resolves the parked Promise
 *   8. searchEngine resumes with cookies / pre-rendered HTML
 *
 * Equivalent to Legado:
 *   requestVerification()  ≈  java.startBrowser(url, title)
 *   parked Promise         ≈  LockSupport.parkNanos()
 *   submitResult()         ≈  SourceVerificationHelp.checkResult()
 *   onVerifyRequest cb     ≈  Intent → WebViewActivity
 */

export interface VerifyRequest {
  id: string;
  url: string;
  type: 'cloudflare' | 'cloudflare_block' | 'captcha' | 'ddos_guard' | 'spa_render';
  origin: string;
  siteName: string;
}

export interface VerifyResult {
  success: boolean;
  cookies?: string;     // Extracted cookies string: "k1=v1; k2=v2"
  html?: string;        // Rendered page HTML (for SPA sources)
  error?: string;
}

type VerifyListener = (request: VerifyRequest) => void;

class _VerifyManager {
  private _listener: VerifyListener | null = null;
  private _pendingResolve: Map<string, (result: VerifyResult) => void> = new Map();
  private _counter = 0;
  private _timeout = 120_000; // 2 min max wait (Legado uses 1 min)

  /**
   * Per-origin cache: remembers verification outcomes within a session.
   * Prevents repeated challenge popups for sources that already failed/succeeded.
   * Key = origin, Value = { success, cookies } or { success: false, error }
   */
  private _originCache: Map<string, VerifyResult> = new Map();

  /** Check if an origin was already verified (success or permanent failure). */
  hasOriginResult(origin: string): boolean {
    return this._originCache.has(origin);
  }

  /** Get cached result for an origin (if any). */
  getOriginResult(origin: string): VerifyResult | undefined {
    return this._originCache.get(origin);
  }

  /** Origins that required verification during this session. */
  private _verifyOrigins = new Set<string>();

  /** Mark an origin as requiring verification (for priority sorting). */
  markRequiresVerify(origin: string) { this._verifyOrigins.add(origin); }

  /** Check if an origin has historically needed verification. */
  isVerifyOrigin(origin: string): boolean { return this._verifyOrigins.has(origin); }

  /**
   * Register the UI listener that will show the WebView.
   * Called once from the root layout / search screen.
   */
  setListener(listener: VerifyListener | null) {
    this._listener = listener;
  }

  /**
   * Called by searchEngine when a challenge is detected.
   * Returns a Promise that resolves when the user completes verification.
   * Equivalent to Legado's LockSupport.parkNanos() + getVerificationResult().
   */
  requestVerification(
    url: string,
    type: VerifyRequest['type'],
    origin: string,
    siteName: string,
  ): Promise<VerifyResult> {
    // Return cached result if origin was already verified this session
    const cached = this._originCache.get(origin);
    if (cached) {
      console.log(`[VerifyManager] Using cached result for ${origin}: success=${cached.success}`);
      return Promise.resolve(cached);
    }

    // Track that this origin requires verification
    this._verifyOrigins.add(origin);

    const id = `verify_${++this._counter}_${Date.now()}`;
    const request: VerifyRequest = { id, url, type, origin, siteName };

    return new Promise<VerifyResult>((resolve) => {
      // Park: store resolve callback, set timeout
      this._pendingResolve.set(id, resolve);
      const timer = setTimeout(() => {
        if (this._pendingResolve.has(id)) {
          this._pendingResolve.delete(id);
          const timeoutResult: VerifyResult = { success: false, error: 'timeout' };
          this._originCache.set(origin, timeoutResult);
          resolve(timeoutResult);
        }
      }, this._timeout);

      // Store timer ref for cleanup
      (request as any)._timer = timer;

      // Notify UI to show WebView
      if (this._listener) {
        this._listener(request);
      } else {
        // No listener registered — can't verify
        clearTimeout(timer);
        this._pendingResolve.delete(id);
        const noUiResult: VerifyResult = { success: false, error: 'no_ui_listener' };
        this._originCache.set(origin, noUiResult);
        resolve(noUiResult);
      }
    });
  }

  /**
   * Called by WebView component when verification completes.
   * Equivalent to Legado's saveVerificationResult().
   */
  submitResult(id: string, result: VerifyResult, origin?: string) {
    const resolve = this._pendingResolve.get(id);
    if (resolve) {
      this._pendingResolve.delete(id);
      // Cache the result for this origin
      if (origin) {
        this._originCache.set(origin, result);
      }
      resolve(result);
    }
  }

  /**
   * Cancel a pending verification (user dismisses modal).
   */
  cancel(id: string) {
    this.submitResult(id, { success: false, error: 'user_cancelled' });
  }

  /** Check if there's a pending verification. */
  get hasPending(): boolean {
    return this._pendingResolve.size > 0;
  }
}

/** Singleton — shared between searchEngine and UI layer */
export const VerifyManager = new _VerifyManager();
