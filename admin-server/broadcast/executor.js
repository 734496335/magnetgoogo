const store = require('./store');
const { loadConfig, canonicalPlatform } = require('./config');
const {
  canAct,
  recordActionTimestamp,
  recordFailure,
  recordAntiBot,
  clearFailureStreak,
} = require('./rateLimiter');
const tieredPost = require('./tieredPost');

let intervalId = null;
let isRunning = false;
let hasRecovered = false;

// ── Concurrency semaphore ───────────────────────────────────────────────────

class Semaphore {
  constructor(max) {
    this.max = max;
    this.current = 0;
    this.queue = [];
  }

  async acquire() {
    if (this.current < this.max) {
      this.current++;
      return;
    }
    await new Promise(resolve => this.queue.push(resolve));
  }

  release() {
    if (this.queue.length > 0) {
      this.queue.shift()();
    } else {
      this.current--;
    }
  }
}

// ── Per-platform/account lock ──────────────────────────────────────────────

const platformLocks = new Map(); // key: "platform:account" -> Promise chain

/**
 * Serialise async work for a given platform:account pair.
 * Concurrent callers with the same key wait in order.
 * FR-09: Uses canonical platform so 'x' and 'twitter' share the same lock.
 */
async function withPlatformLock(platform, account, fn) {
  const key = canonicalPlatform(platform) + ':' + account;
  const prev = platformLocks.get(key) || Promise.resolve();
  const current = prev.then(() => fn(), () => fn());
  platformLocks.set(key, current);
  try {
    return await current;
  } finally {
    // Clean up the map entry when this is the last link in the chain
    if (platformLocks.get(key) === current) {
      platformLocks.delete(key);
    }
  }
}

// ── Defer delay calculation ──────────────────────────────────────────────────

/**
 * Calculate how long to defer a job based on the rate limit reason.
 * Returns delay in milliseconds.
 * Note: platform parameter is expected to be canonical (set by createJob).
 */
function _calcDeferDelay(limit, cfg, platform, account) {
  const pCfg = cfg.platforms[platform] || {};
  const baseMinGap = (pCfg.min_gap_min || 30) * 60 * 1000;

  switch (limit.reason) {
    case 'account_busy': {
      // Another job is running for this account. Wait for it to finish + small buffer.
      return 60_000;
    }
    case 'min_gap_not_elapsed': {
      // P1-5 fix: calculate REMAINING time, not full min_gap
      const remainingMs = limit.remaining_ms != null ? limit.remaining_ms : baseMinGap;
      const jitter = Math.floor(Math.random() * Math.min(remainingMs * 0.1, 30_000));
      return Math.max(remainingMs + jitter, 5_000); // at least 5s to avoid tight loops
    }
    case 'anti_bot_cooldown': {
      const cooldownMin = (pCfg.anti_bot_cooldown_min || 60) * 60 * 1000;
      const jitter = Math.floor(Math.random() * cooldownMin * 0.1);
      return cooldownMin + jitter;
    }
    case 'hourly_cap_reached': {
      return 65 * 60 * 1000; // 65 minutes
    }
    case 'daily_cap_reached': {
      // P1-5 fix: defer to next day instead of skipping
      const now = new Date();
      const midnight = new Date(now);
      midnight.setHours(24, 0, 0, 0);
      const offset = Math.floor(Math.random() * 10 * 60 * 1000); // 0-10 min
      // RL-04: Floor guard for clock skew / DST edge cases
      return Math.max(midnight.getTime() - now.getTime() + offset, 60_000);
    }
    default: {
      return 5 * 60 * 1000;
    }
  }
}

// ── Retry wrapper ───────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Sleep that checks kill switch every 5 seconds.
 * Returns true if kill switch was activated (sleep interrupted).
 */
async function interruptibleSleep(ms, cfg) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    if (cfg && cfg.global && cfg.global.kill_switch) return true;
    await sleep(Math.min(ms - (Date.now() - start), 5000));
  }
  return false;
}

/**
 * Execute a single job with retry and exponential backoff.
 * @param {object} job       - row from the jobs table
 * @param {object} ctx       - { cfg, account, contentHash }
 * @returns {Promise<{success: boolean, retried: number}>}
 */
async function executeJobWithRetry(job, ctx) {
  const { account, contentHash } = ctx;
  const platformCfg = ctx.cfg.platforms[job.platform];
  const maxRetries = (platformCfg && platformCfg.max_retries) || ctx.cfg.global.max_retries || 3;
  const baseDelay = ctx.cfg.global.retry_base_delay_ms || 30000;

  let attempt = 0;

  while (attempt <= maxRetries) {
    // Mark as running on first attempt; keep running on retries
    store.updateJob(job.id, {
      status: 'running',
      retry_count: attempt,
    });

    try {
      const result = await tieredPost.execute(job);

      if (result.success) {
        // ── Success ──
        store.updateJob(job.id, {
          status: 'done',
          result_json: result,
          tier_used: (result.data?.tier_used || '?'),
          last_error: null,
        });
        store.addLog({
          job_id: job.id,
          platform: job.platform,
          account,
          action: 'post',
          content_hash: contentHash,
          status: 'done',
          detail: `Success (tier ${result.data?.tier_used || '?'}): ${result.data?.stdout || ''}`,
          ts: new Date().toISOString(),
        });
        clearFailureStreak(job.platform, account);
        recordActionTimestamp(job.platform, account);
        if (job.task_id) store.refreshTaskCounts(job.task_id);
        // P0-4: Update discovered_post status on success
        _syncDiscoveredPost(job, 'replied');
        return { ok: true, retried: attempt };
      }

      // ── Not OK — check retryable ──
      if (result.retryable && attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt); // 30s, 60s, 120s …
        console.warn(
          `[executor] Job ${job.id} attempt ${attempt + 1} failed (retryable). Retrying in ${delay / 1000}s.`
        );
        store.updateJob(job.id, {
          last_error: (result.data?.error || result.summary || 'retryable failure'),
        });
        recordFailure(job.platform, account);
        const killed = await interruptibleSleep(delay, ctx.cfg);
        if (killed) {
          store.updateJob(job.id, { status: 'failed', last_error: 'kill_switch_during_retry' });
          return { ok: false, retried: attempt };
        }
        attempt++;
        continue;
      }

      // ── Non-retryable or retries exhausted ──
      store.updateJob(job.id, {
        status: 'failed',
        result_json: result,
        tier_used: (result.data?.tier_used || '?'),
        last_error: (result.data?.error || result.summary || 'unknown'),
      });
      store.addLog({
        job_id: job.id,
        platform: job.platform,
        account,
        action: 'post',
        content_hash: contentHash,
        status: 'failed',
        detail: `Failed after ${attempt + 1} attempt(s): ${result.data?.error || result.summary || 'unknown'}`,
        ts: new Date().toISOString(),
      });
      recordFailure(job.platform, account);

      // Handle anti-bot specifically
      if (result.hint === 'antibot_blocked') {
        const cooldownMin =
          (platformCfg && platformCfg.anti_bot_cooldown_min) || 60;
        recordAntiBot(job.platform, account, cooldownMin);
      }

      if (job.task_id) store.refreshTaskCounts(job.task_id);
      // P0-4: Update discovered_post status on failure (allow retry)
      _syncDiscoveredPost(job, 'failed');
      return { ok: false, retried: attempt };
    } catch (err) {
      // ── Unexpected exception ──
      if (attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt);
        console.warn(
          `[executor] Job ${job.id} attempt ${attempt + 1} threw: ${err.message}. Retrying in ${delay / 1000}s.`
        );
        store.updateJob(job.id, { last_error: err.message });
        recordFailure(job.platform, account);
        const killed = await interruptibleSleep(delay, ctx.cfg);
        if (killed) {
          store.updateJob(job.id, { status: 'failed', last_error: 'kill_switch_during_retry' });
          return { ok: false, retried: attempt };
        }
        attempt++;
        continue;
      }

      store.updateJob(job.id, {
        status: 'failed',
        result_json: { error: err.message },
        last_error: err.message,
      });
      store.addLog({
        job_id: job.id,
        platform: job.platform,
        account,
        action: 'post',
        content_hash: contentHash,
        status: 'failed',
        detail: `Exception after ${attempt + 1} attempt(s): ${err.message}`,
        ts: new Date().toISOString(),
      });
      recordFailure(job.platform, account);
      if (job.task_id) store.refreshTaskCounts(job.task_id);
      return { ok: false, retried: attempt };
    }
  }

  // Should not reach here, but safety net
  return { ok: false, retried: attempt };
}

// ── Sync discovered_post status after job completion ──────────────────────

function _syncDiscoveredPost(job, status) {
  try {
    const payload = JSON.parse(job.payload_json || '{}');
    const targetUrl = payload.target;
    if (!targetUrl) return;
    const post = store.getDiscoveredByUrl(targetUrl);
    if (post) {
      const updates = { status };
      if (status === 'replied') updates.replied_at = new Date().toISOString();
      store.updateDiscoveredPost(post.id, updates);
    }
  } catch (_) { /* best effort */ }
}

// ── Prepare a single job (validation + content hash) ────────────────────────

function prepareJob(job) {
  const cfg = loadConfig();
  // FR-09: job.platform is always canonical in the DB (set by createJob via canonicalPlatform).
  // The canonicalization below is defense-in-depth for any code path that bypasses createJob.
  const canonPlatform = canonicalPlatform(job.platform);
  const pCfg = cfg.platforms[canonPlatform];
  // FR-01: Account should already be resolved from DB, but fallback for defense-in-depth
  const account = (job.account && job.account !== 'default') ? job.account : (pCfg ? pCfg.account_profile : 'default');

  // Skip job if its task is paused
  if (job.task_id) {
    const task = store.getTask(job.task_id);
    if (task && task.status === 'paused') {
      return null; // keep job queued, task is paused
    }
  }

  const limit = canAct(job.platform, account);
  const payload = JSON.parse(job.payload_json || '{}');
  const tpl = job.template_id ? store.getTemplate(job.template_id) : null;
  const body = payload.body || (tpl ? tpl.body : '');
  const contentHash = store.hashContent(body);

  // NOTE: hasRunningJob check moved inside withPlatformLock in pollAndExecute
  // to avoid race condition where concurrent jobs all pass the check simultaneously

  if (!limit.allowed) {
    // ── Transient conditions: defer (keep queued) instead of skip ──
    const deferReasons = new Set(['account_busy', 'min_gap_not_elapsed', 'anti_bot_cooldown', 'hourly_cap_reached', 'daily_cap_reached']);

    if (deferReasons.has(limit.reason)) {
      // Enforce max defer count per reason to prevent infinite deferral
      const MAX_DEFERS = { account_busy: 20, min_gap_not_elapsed: 10, anti_bot_cooldown: 5, hourly_cap_reached: 12, daily_cap_reached: 3 };
      const currentDeferCount = job.defer_count || 0;
      const maxForReason = MAX_DEFERS[limit.reason] || 10;
      if (currentDeferCount >= maxForReason) {
        store.updateJob(job.id, { status: 'failed', last_error: `max_defers_exceeded:${limit.reason}` });
        store.addLog({
          job_id: job.id, platform: job.platform, account,
          action: 'fail', content_hash: contentHash,
          status: 'failed',
          detail: `Max defers (${maxForReason}) exceeded for ${limit.reason}`,
          ts: new Date().toISOString(),
        });
        return null;
      }
      // Calculate next allowed time
      const delayMs = _calcDeferDelay(limit, cfg, job.platform, account);
      const deferredAt = new Date(Date.now() + delayMs).toISOString();
      store.updateJob(job.id, { scheduled_at: deferredAt, defer_count: currentDeferCount + 1 });
      store.addLog({
        job_id: job.id,
        platform: job.platform,
        account,
        action: 'defer',
        content_hash: contentHash,
        status: 'deferred',
        detail: `${limit.reason} → deferred ${Math.round(delayMs/1000)}s to ${deferredAt}`,
        ts: new Date().toISOString(),
      });
      return null; // keep job queued, will be picked up next poll
    }

    // ── Permanent conditions: skip ──
    store.updateJob(job.id, { status: 'skipped' });
    store.addLog({
      job_id: job.id,
      platform: job.platform,
      account,
      action: 'skip',
      content_hash: contentHash,
      status: 'skipped',
      detail: `Rate limit check failed: ${limit.reason}`,
      ts: new Date().toISOString(),
    });
    return null;
  }

  return { cfg, account, contentHash };
}

// ── Poll-and-execute loop ───────────────────────────────────────────────────

async function pollAndExecute() {
  if (isRunning) return;
  isRunning = true;

  try {
    // Recovery: reset jobs stuck in 'running' state from previous crash
    if (!hasRecovered) {
      hasRecovered = true;
      store.resetRunningJobs();
    }

    const cfg = loadConfig();
    if (cfg.global.kill_switch || !cfg.global.enabled) {
      return;
    }

    const now = new Date().toISOString();
    const queuedJobs = store.listJobs({ status: 'queued' });
    const runnableJobs = queuedJobs.filter(j => !j.scheduled_at || j.scheduled_at <= now);

    if (runnableJobs.length === 0) {
      return;
    }

    const maxConcurrent = cfg.global.max_concurrent || 3;
    const semaphore = new Semaphore(maxConcurrent);

    const tasks = runnableJobs.map(job =>
      (async () => {
        // Re-verify global switches before acquiring the semaphore
        const currentCfg = loadConfig();
        if (currentCfg.global.kill_switch || !currentCfg.global.enabled) {
          return;
        }

        await semaphore.acquire();
        try {
          const ctx = prepareJob(job);
          if (!ctx) return; // skipped by rate limiter

          await withPlatformLock(job.platform, ctx.account, async () => {
            // ── Double-check: is another job for this account already running? ──
            // This check is INSIDE the platform lock, so it sees the DB state
            // after any previously-locked job has started.
            if (store.hasRunningJob(job.platform, ctx.account)) {
              const currentDeferCount = job.defer_count || 0;
              if (currentDeferCount >= 20) {
                store.updateJob(job.id, { status: 'failed', last_error: 'max_defers_exceeded:account_busy' });
                store.addLog({
                  job_id: job.id, platform: job.platform, account: ctx.account,
                  action: 'fail', content_hash: ctx.contentHash,
                  status: 'failed',
                  detail: `Max defers (20) exceeded for account_busy (double-check)`,
                  ts: new Date().toISOString(),
                });
                return;
              }
              const cfg2 = loadConfig();
              const pCfg2 = cfg2.platforms[job.platform] || {};
              const delayMs = 60_000; // wait 60s for the running job to finish
              const deferredAt = new Date(Date.now() + delayMs).toISOString();
              store.updateJob(job.id, { scheduled_at: deferredAt, defer_count: currentDeferCount + 1 });
              store.addLog({
                job_id: job.id, platform: job.platform, account: ctx.account,
                action: 'defer', content_hash: ctx.contentHash,
                status: 'deferred',
                detail: `account_busy → deferred ${delayMs/1000}s to ${deferredAt}`,
                ts: new Date().toISOString(),
              });
              return; // keep queued
            }
            await executeJobWithRetry(job, ctx);
          });
        } catch (err) {
          console.error(`[executor] Unexpected error on job ${job.id}:`, err.message);
        } finally {
          semaphore.release();
        }
      })()
    );

    await Promise.allSettled(tasks);
  } catch (err) {
    console.error('[executor] Poller encountered error:', err.message);
  } finally {
    isRunning = false;
  }
}

// ── Public API ──────────────────────────────────────────────────────────────

function startExecutor(intervalSec = 60) {
  if (intervalId) clearInterval(intervalId);
  // Fire-and-forget the initial poll; errors are caught inside pollAndExecute
  pollAndExecute();
  intervalId = setInterval(() => {
    pollAndExecute();
  }, intervalSec * 1000);
}

function stopExecutor() {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
}

module.exports = { startExecutor, stopExecutor, pollAndExecute };
