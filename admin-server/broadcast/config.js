const fs = require('fs');
const path = require('path');

// P2-10: Support BROADCAST_CONFIG_PATH env var for test isolation
const CONFIG_PATH = process.env.BROADCAST_CONFIG_PATH || path.resolve(__dirname, '..', '..', 'broadcast-config.json');

const PLATFORM_DEFAULTS = {
  enabled: false,
  engine: 'opencli',
  daily_cap: 3,
  min_gap_min: 30,
  account_profile: 'default',
  max_retries: null,
  tiers: null,
  hourly_cap: 5,
  hourly_window_min: 60,
  anti_bot_cooldown_min: 60,
};

const GLOBAL_DEFAULTS = {
  enabled: true,
  approval_required: true,
  kill_switch: false,
  max_concurrent: 3,
  max_retries: 3,
  retry_base_delay_ms: 30000,
  discovery: {
    enabled: false,
    dry_run: true,
    cron_interval_min: 180,
    queries: {},
    max_results_per_query: 20,
    max_replies_per_run: 3,
    relevance_threshold: 0.5,
    product_name: 'MagnetGoogo',
  },
};

function mergePlatform(p) {
  const merged = { ...PLATFORM_DEFAULTS, ...p };
  if (typeof merged.daily_cap !== 'number' || merged.daily_cap < 0) {
    merged.daily_cap = PLATFORM_DEFAULTS.daily_cap;
  }
  if (typeof merged.min_gap_min !== 'number' || merged.min_gap_min < 0) {
    merged.min_gap_min = PLATFORM_DEFAULTS.min_gap_min;
  }
  return merged;
}

function normalize(raw) {
  const rawGlobal = raw.global || {};
  const global = {
    ...GLOBAL_DEFAULTS,
    ...rawGlobal,
    discovery: { ...GLOBAL_DEFAULTS.discovery, ...(raw.discovery || {}), ...(rawGlobal.discovery || {}) },
  };

  // PF-02: Canonicalize platform keys so aliases (e.g. twitter) merge into canonical (e.g. x)
  const rawPlatforms = raw.platforms && typeof raw.platforms === 'object' ? raw.platforms : {};
  const canonicalPlatforms = {};
  for (const [name, p] of Object.entries(rawPlatforms)) {
    const canon = canonicalPlatform(name);
    if (!canonicalPlatforms[canon]) {
      canonicalPlatforms[canon] = mergePlatform(p);
    } else {
      // Canonical key already exists — alias fills missing fields only
      const merged = mergePlatform(p);
      for (const [k, v] of Object.entries(merged)) {
        if (canonicalPlatforms[canon][k] == null || canonicalPlatforms[canon][k] === PLATFORM_DEFAULTS[k]) {
          canonicalPlatforms[canon][k] = v;
        }
      }
    }
  }

  return {
    global,
    platforms: canonicalPlatforms,
    campaigns: Array.isArray(raw.campaigns) ? raw.campaigns : [],
  };
}

function loadConfig() {
  let raw = {};
  try {
    const text = fs.readFileSync(CONFIG_PATH, 'utf8');
    try {
      raw = JSON.parse(text);
    } catch (parseErr) {
      if (parseErr instanceof SyntaxError) {
        console.error('[broadcast:config] JSON parse error, falling back to defaults:', parseErr.message);
        raw = {};
      } else {
        throw parseErr;
      }
    }
  } catch (e) {
    if (e.code !== 'ENOENT') throw e;
  }
  return normalize(raw);
}

function saveConfig(obj) {
  const config = normalize(obj);
  const tmpPath = CONFIG_PATH + '.tmp';
  fs.writeFileSync(tmpPath, JSON.stringify(config, null, 2) + '\n', 'utf8');
  fs.renameSync(tmpPath, CONFIG_PATH);
  return config;
}

function getPlatform(name) {
  const cfg = loadConfig();
  return cfg.platforms[canonicalPlatform(name)] || null;
}

// ── Identity normalization (FR-01 / FR-09) ──────────────────────────────────

const PLATFORM_ALIASES = {
  twitter: 'x',
  testplatform: 'x',
};

/**
 * Canonicalise a platform name so that aliases share one identity.
 * Used ONLY for internal bookkeeping (locks, rate limits, DB queries).
 * The actual OpenCLI command must still use the original CLI-recognised name.
 */
function canonicalPlatform(name) {
  if (!name) return name;
  const lower = name.toLowerCase();
  return PLATFORM_ALIASES[lower] || lower;
}

/**
 * Resolve the effective account profile for a job.
 * Returns `requestedAccount` if it is a real profile (not null, not 'default', not empty).
 * Otherwise falls back to the platform's configured account_profile, then 'default'.
 */
function resolveAccount(platform, requestedAccount, cfg) {
  if (requestedAccount && requestedAccount !== 'default') return requestedAccount;
  const platforms = (cfg && cfg.platforms) ? cfg.platforms : null;
  if (!platforms) return 'default';
  // Try direct lookup first, then canonical form (e.g. 'twitter' -> 'x')
  const pCfg = platforms[platform]
    || platforms[canonicalPlatform(platform)]
    || null;
  return (pCfg && pCfg.account_profile) || 'default';
}

module.exports = { loadConfig, saveConfig, getPlatform, canonicalPlatform, resolveAccount, PLATFORM_ALIASES };
