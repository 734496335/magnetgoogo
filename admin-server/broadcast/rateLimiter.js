const { loadConfig, canonicalPlatform } = require('./config');
const { countActionsToday, lastActionTs, hasRunningJob } = require('./store');

// --- Sliding window state ---
const slidingWindows = new Map();     // key: "platform:account" -> [timestamps]
const failureStreaks = new Map();     // key: "platform:account" -> {count, lastFailureAt}
const antiBotCooldowns = new Map();   // key: "platform:account" -> cooldownUntil (ms timestamp)

// --- Sliding window helpers ---

function _key(platform, account) {
  // FR-09: Canonicalize platform so 'x' and 'twitter' share the same rate-limit key
  return `${canonicalPlatform(platform)}:${account}`;
}

function _pruneWindow(timestamps, windowMin) {
  const cutoff = Date.now() - windowMin * 60000;
  return timestamps.filter(t => t > cutoff);
}

function _windowCount(platform, account, windowMin) {
  const k = _key(platform, account);
  let ts = slidingWindows.get(k);
  if (!ts) return 0;
  ts = _pruneWindow(ts, windowMin);
  if (ts.length === 0) {
    slidingWindows.delete(k);
    return 0;
  }
  slidingWindows.set(k, ts);
  return ts.length;
}

// --- Exported functions ---

function recordActionTimestamp(platform, account) {
  const k = _key(platform, account);
  let ts = slidingWindows.get(k) || [];
  ts.push(Date.now());
  // Keep at most 100 entries to prevent unbounded growth
  if (ts.length > 100) ts = ts.slice(-100);
  slidingWindows.set(k, ts);
}

function recordFailure(platform, account) {
  const k = _key(platform, account);
  const entry = failureStreaks.get(k) || { count: 0, lastFailureAt: 0 };
  entry.count += 1;
  entry.lastFailureAt = Date.now();
  failureStreaks.set(k, entry);
}

function recordAntiBot(platform, account, cooldownMinutes = 60) {
  const k = _key(platform, account);
  antiBotCooldowns.set(k, Date.now() + cooldownMinutes * 60000);
}

function clearFailureStreak(platform, account) {
  const k = _key(platform, account);
  failureStreaks.delete(k);
}

function getPlatformHealth(platform, account) {
  const k = _key(platform, account);
  const streak = failureStreaks.get(k) || { count: 0, lastFailureAt: 0 };
  return {
    failureStreak: streak.count,
    cooldownUntil: antiBotCooldowns.get(k) || null,
  };
}

// --- Core gate ---

function canAct(platform, account) {
  let cfg;
  try {
    cfg = loadConfig();
  } catch (e) {
    return { allowed: false, reason: 'config_error' };
  }

  if (cfg.global.kill_switch) return { allowed: false, reason: 'kill_switch' };
  if (!cfg.global.enabled) return { allowed: false, reason: 'global_disabled' };

  // FR-09: Use canonical platform for config lookup
  const canonPlatform = canonicalPlatform(platform);
  const pCfg = cfg.platforms[canonPlatform];
  if (!pCfg || !pCfg.enabled) return { allowed: false, reason: 'platform_disabled' };

  // FR-01: Resolve account to real profile
  const acct = (account && account !== 'default') ? account : (pCfg.account_profile || 'default');

  // --- New: Concurrency safety check ---
  if (hasRunningJob(canonPlatform, acct)) {
    return { allowed: false, reason: 'account_busy' };
  }

  // --- New: Anti-bot cooldown check ---
  const k = _key(platform, acct);
  const cooldownUntil = antiBotCooldowns.get(k);
  if (cooldownUntil && Date.now() < cooldownUntil) {
    return { allowed: false, reason: 'anti_bot_cooldown' };
  }
  // Clean up expired cooldown
  if (cooldownUntil) antiBotCooldowns.delete(k);

  // --- New: Sliding window hourly cap ---
  const windowMin = pCfg.hourly_window_min || 60;
  const hourlyCap = pCfg.hourly_cap || 5;
  const windowCount = _windowCount(platform, acct, windowMin);
  if (windowCount >= hourlyCap) {
    return { allowed: false, reason: 'hourly_cap_reached' };
  }

  // --- Existing: Daily cap ---
  if (countActionsToday(canonPlatform, acct) >= pCfg.daily_cap) {
    return { allowed: false, reason: 'daily_cap_reached' };
  }

  // --- Existing: Min gap (with failure streak multiplier) ---
  // Failure streak TTL — auto-expire after 2 hours (unconditional)
  // RL-03: Use single variable to avoid TOCTOU race with concurrent recordFailure
  let streak = failureStreaks.get(k);
  if (streak && streak.lastFailureAt && Date.now() - streak.lastFailureAt > 2 * 3600 * 1000) {
    failureStreaks.delete(k);
    streak = null;
  }
  const last = lastActionTs(canonPlatform, acct);
  if (last) {
    const multiplier = streak && streak.count >= 2
      ? Math.min(Math.pow(2, streak.count - 1), 8)
      : 1;
    const effectiveGap = pCfg.min_gap_min * multiplier;
    const elapsedMin = (Date.now() - new Date(last).getTime()) / 60000;
    if (elapsedMin < effectiveGap) {
      const remainingMs = Math.ceil((effectiveGap - elapsedMin) * 60000);
      return { allowed: false, reason: 'min_gap_not_elapsed', remaining_ms: remainingMs };
    }
  }

  return { allowed: true, reason: 'ok' };
}

module.exports = {
  canAct,
  recordActionTimestamp,
  recordFailure,
  recordAntiBot,
  clearFailureStreak,
  getPlatformHealth,
};
