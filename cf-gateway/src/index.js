/**
 * MagGoogo API Gateway — Cloudflare Worker
 *
 * Responsibilities:
 *   1. Serve config.json and sources.enc.json (cached from GitHub upstream)
 *   2. Version gate: reject requests from outdated app versions
 *   3. [Future] Membership gate: return different source tiers based on token
 *   4. Edge caching: minimize upstream GitHub fetches
 *
 * Endpoints:
 *   GET /                    → health check
 *   GET /config.json         → remote config (version control, announcements)
 *   GET /sources.enc.json    → encrypted sources (version-gated)
 *   GET /api/check           → version + membership status check
 */

// ── CORS headers (allow any origin for the app) ──
function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-App-Version, X-Device-Id, X-Member-Token',
    'Access-Control-Max-Age': '86400',
  };
}

function jsonResponse(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      ...corsHeaders(),
      ...extraHeaders,
    },
  });
}

// ── Semver comparison ──
function semverCompare(a, b) {
  const pa = (a || '0.0.0').split('.').map(Number);
  const pb = (b || '0.0.0').split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) < (pb[i] || 0)) return -1;
    if ((pa[i] || 0) > (pb[i] || 0)) return 1;
  }
  return 0;
}

// ── Fetch from GitHub with edge caching ──
async function fetchUpstream(env, path, cacheTtl) {
  const url = `${env.GITHUB_RAW}${path}`;

  // Try CF Cache API (available in deployed Workers; may fail in local dev)
  try {
    const cache = caches.default;
    if (cache) {
      const cacheKey = new Request(url);
      const cached = await cache.match(cacheKey);
      if (cached) return cached;
    }
  } catch { /* local dev — no cache, fall through */ }

  // Cache miss or no cache available → fetch from GitHub
  const response = await fetch(url, {
    headers: { 'User-Agent': 'MagGoogo-Gateway/1.0' },
  });

  // Store in cache for next time (best-effort)
  try {
    const cache = caches.default;
    if (response.ok && cache) {
      const ttl = parseInt(cacheTtl) || 300;
      const toCache = new Response(response.clone().body, response);
      toCache.headers.set('Cache-Control', `public, max-age=${ttl}`);
      cache.put(new Request(url), toCache);
    }
  } catch { /* ignore cache write failure */ }

  return response;
}

// ── Parse common request headers ──
function parseRequestMeta(request) {
  return {
    appVersion: request.headers.get('X-App-Version') || '',
    deviceId: request.headers.get('X-Device-Id') || '',
    memberToken: request.headers.get('X-Member-Token') || '',
    country: request.headers.get('CF-IPCountry') || '',
    ip: request.headers.get('CF-Connecting-IP') || '',
  };
}

// ────────────────────────────────────────────────────────────────────
// Route handlers
// ────────────────────────────────────────────────────────────────────

async function handleHealth() {
  return jsonResponse({
    service: 'MagGoogo Gateway',
    status: 'ok',
    timestamp: new Date().toISOString(),
  });
}

async function handleConfig(request, env) {
  const upstream = await fetchUpstream(env, '/config.json', env.CACHE_TTL);
  if (!upstream.ok) {
    return jsonResponse({ error: 'config_unavailable' }, 502);
  }

  const body = await upstream.clone().text();
  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': `public, max-age=${env.CACHE_TTL || 300}`,
      ...corsHeaders(),
    },
  });
}

async function handleSources(request, env) {
  const meta = parseRequestMeta(request);

  // ── Step 1: Fetch config to get min_version ──
  let minVersion = '1.0.0';
  try {
    const configResp = await fetchUpstream(env, '/config.json', env.CACHE_TTL);
    if (configResp.ok) {
      const config = await configResp.clone().json();
      minVersion = config.min_version || '1.0.0';
    }
  } catch { /* use default */ }

  // ── Step 2: Version gate ──
  if (meta.appVersion && semverCompare(meta.appVersion, minVersion) < 0) {
    return jsonResponse({
      error: 'update_required',
      min_version: minVersion,
      message: `请更新App到 ${minVersion} 以上版本`,
    }, 403);
  }

  // ── Step 3: Membership gate (STUB — always returns full sources) ──
  // TODO Phase 3: validate memberToken, decide source tier
  //
  // const tier = await validateMembership(meta.memberToken, meta.deviceId, env);
  // const sourceFile = tier === 'pro' ? '/sources.pro.enc.json' : '/sources.free.enc.json';
  //
  const sourceFile = '/sources.enc.json';

  // ── Step 4: Fetch and return sources ──
  const upstream = await fetchUpstream(env, sourceFile, env.CACHE_TTL);
  if (!upstream.ok) {
    return jsonResponse({ error: 'sources_unavailable' }, 502);
  }

  const body = await upstream.clone().text();
  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': `public, max-age=${env.CACHE_TTL || 300}`,
      ...corsHeaders(),
    },
  });
}

async function handleCheck(request, env) {
  const meta = parseRequestMeta(request);

  // Fetch config
  let config = {};
  try {
    const configResp = await fetchUpstream(env, '/config.json', env.CACHE_TTL);
    if (configResp.ok) config = await configResp.json();
  } catch { /* ignore */ }

  const minVersion = config.min_version || '1.0.0';
  const latestVersion = config.latest_version || '1.0.0';

  const forceUpdate = meta.appVersion
    ? semverCompare(meta.appVersion, minVersion) < 0
    : false;
  const updateAvailable = meta.appVersion
    ? semverCompare(meta.appVersion, latestVersion) < 0
    : false;

  // TODO Phase 3: membership status
  // const membership = await validateMembership(meta.memberToken, meta.deviceId, env);
  const membership = {
    tier: 'free',
    expires_at: null,
    valid: true,
  };

  return jsonResponse({
    app_version: meta.appVersion,
    force_update: forceUpdate,
    update_available: updateAvailable,
    min_version: minVersion,
    latest_version: latestVersion,
    announcement: config.announcement || '',
    download: config.download || {},
    membership,
    country: meta.country,
  });
}

// ────────────────────────────────────────────────────────────────────
// Feedback (anonymous, stored in KV)
// ────────────────────────────────────────────────────────────────────

async function handleFeedbackPost(request, env) {
  // Rate limit: max 2KB body
  const body = await request.text();
  if (body.length > 2048) {
    return jsonResponse({ error: 'feedback_too_long', max: 2048 }, 400);
  }

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    return jsonResponse({ error: 'invalid_json' }, 400);
  }

  const text = (data.text || '').trim();
  if (!text || text.length > 1000) {
    return jsonResponse({ error: text ? 'feedback_too_long' : 'empty_feedback' }, 400);
  }

  // Per-IP rate limit: 1 feedback per 60 seconds (KV min TTL = 60)
  const meta = parseRequestMeta(request);
  if (env.FEEDBACK) {
    const rateKey = `rl_${meta.ip}`;
    const last = await env.FEEDBACK.get(rateKey);
    if (last) {
      return jsonResponse({ error: 'rate_limited', retry_after: 60 }, 429);
    }
    await env.FEEDBACK.put(rateKey, '1', { expirationTtl: 60 });
  }

  const id = `fb_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  const entry = {
    id,
    text,
    appVersion: meta.appVersion,
    country: meta.country,
    platform: data.platform || '',
    createdAt: new Date().toISOString(),
  };

  // Store in KV (TTL 90 days)
  if (env.FEEDBACK) {
    await env.FEEDBACK.put(id, JSON.stringify(entry), { expirationTtl: 86400 * 90 });
  }

  return jsonResponse({ ok: true, id });
}

async function handleFeedbackList(request, env) {
  // Simple admin guard: require ?secret= or X-Admin-Secret header
  const url = new URL(request.url);
  const secret = url.searchParams.get('secret') || request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET || 'maggoogo-admin-2026';
  if (secret !== adminSecret) {
    return jsonResponse({ error: 'unauthorized' }, 401);
  }
  if (!env.FEEDBACK) {
    return jsonResponse({ error: 'kv_not_configured' }, 500);
  }
  const list = await env.FEEDBACK.list({ prefix: 'fb_', limit: 100 });
  const items = [];
  for (const key of list.keys) {
    const val = await env.FEEDBACK.get(key.name);
    if (val) items.push(JSON.parse(val));
  }
  items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  return jsonResponse({ count: items.length, items });
}

// ────────────────────────────────────────────────────────────────────
// Router
// ────────────────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    try {
      switch (path) {
        case '/':
          return handleHealth();
        case '/config.json':
          return await handleConfig(request, env);
        case '/sources.enc.json':
          return await handleSources(request, env);
        case '/api/check':
          return await handleCheck(request, env);
        case '/api/feedback':
          if (request.method === 'POST') return await handleFeedbackPost(request, env);
          if (request.method === 'GET') return await handleFeedbackList(request, env);
          return jsonResponse({ error: 'method_not_allowed' }, 405);
        default:
          return jsonResponse({ error: 'not_found' }, 404);
      }
    } catch (err) {
      console.error('[Gateway Error]', err.stack || err.message || err);
      return jsonResponse({
        error: 'internal_error',
        message: err.message || 'Unknown error',
      }, 500);
    }
  },
};
