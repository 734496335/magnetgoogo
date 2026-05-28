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

// ── Cache-based rate limiting (no KV consumption) ──
async function checkRateLimit(key, ttlSeconds) {
  try {
    const cache = caches.default;
    const fakeUrl = `https://rate-limit.internal/${key}`;
    const cached = await cache.match(new Request(fakeUrl));
    if (cached) return true; // rate-limited
    const resp = new Response('1', {
      headers: { 'Cache-Control': `public, max-age=${ttlSeconds}` },
    });
    await cache.put(new Request(fakeUrl), resp);
  } catch { /* local dev — no cache, allow */ }
  return false;
}

// ── CORS headers (allow any origin for the app) ──
function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-App-Version, X-Device-Id, X-Member-Token, X-Admin-Secret',
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

// ── Upstream sources (GitHub primary, CF Pages fallback) ──
const CF_PAGES_BASE = 'https://magnetgoogo.com';

// ── Fetch from upstream with edge caching + fallback ──
async function fetchUpstream(env, path, cacheTtl, skipCache = false) {
  const url = `${env.GITHUB_RAW}${path}`;

  // Try CF Cache API (available in deployed Workers; may fail in local dev)
  if (!skipCache) {
    try {
      const cache = caches.default;
      if (cache) {
        const cacheKey = new Request(url);
        const cached = await cache.match(cacheKey);
        if (cached) return cached;
      }
    } catch { /* local dev — no cache, fall through */ }
  }

  // Try CF Pages first (always up-to-date), GitHub as fallback
  let response;
  try {
    response = await fetch(`${CF_PAGES_BASE}${path}`, {
      headers: { 'User-Agent': 'MagGoogo-Gateway/1.0' },
    });
    if (!response.ok) throw new Error(`CF Pages ${response.status}`);
  } catch {
    // Fallback to GitHub
    response = await fetch(url, {
      headers: { 'User-Agent': 'MagGoogo-Gateway/1.0' },
    });
  }

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
  const cf = request.cf || {};
  return {
    appVersion: request.headers.get('X-App-Version') || '',
    deviceId: request.headers.get('X-Device-Id') || '',
    memberToken: request.headers.get('X-Member-Token') || '',
    country: request.headers.get('CF-IPCountry') || cf.country || '',
    ip: request.headers.get('CF-Connecting-IP') || '',
    city: cf.city || '',
    region: cf.region || '',
    timezone: cf.timezone || '',
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
  const noCache = (request.headers.get('Cache-Control') || '').includes('no-cache');
  const upstream = await fetchUpstream(env, '/config.json', env.CACHE_TTL, noCache);
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
  const noCache = (request.headers.get('Cache-Control') || '').includes('no-cache');
  let minVersion = '0.0.0';
  try {
    const configResp = await fetchUpstream(env, '/config.json', env.CACHE_TTL, noCache);
    if (configResp.ok) {
      const config = await configResp.clone().json();
      minVersion = config.min_version || '0.0.0';
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
  const upstream = await fetchUpstream(env, sourceFile, env.CACHE_TTL, noCache);
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

  const minVersion = config.min_version || '0.0.0';
  const latestVersion = config.latest_version || '0.0.0';

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

  // Per-IP rate limit: 1 feedback per 60 seconds (Cache API, no KV cost)
  const meta = parseRequestMeta(request);
  if (await checkRateLimit(`fb_${meta.ip}`, 60)) {
    return jsonResponse({ error: 'rate_limited', retry_after: 60 }, 429);
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

async function handleFeedbackDelete(request, env, path) {
  const secret = request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET || 'maggoogo-admin-2026';
  if (secret !== adminSecret) {
    return jsonResponse({ error: 'unauthorized' }, 401);
  }
  if (!env.FEEDBACK) {
    return jsonResponse({ error: 'kv_not_configured' }, 500);
  }
  const id = path.replace('/api/feedback/', '');
  if (!id || !id.startsWith('fb_')) {
    return jsonResponse({ error: 'invalid_id' }, 400);
  }
  await env.FEEDBACK.delete(id);
  return jsonResponse({ ok: true, deleted: id });
}

// ────────────────────────────────────────────────────────────────────
// Analytics events (stored in R2, rate-limit keys in KV)
//
// R2 key structure: events/{YYYY}/{MM}/{DD}/{did}_{ts}.json
// This allows efficient prefix-based listing by date range.
// ────────────────────────────────────────────────────────────────────

function eventsR2Key(did, ts) {
  const d = new Date(ts);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `events/${y}/${m}/${dd}/${did}_${ts}.json`;
}

async function handleEventsPost(request, env) {
  const body = await request.text();
  if (body.length > 32768) {
    return jsonResponse({ error: 'payload_too_large', max: 32768 }, 400);
  }

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    return jsonResponse({ error: 'invalid_json' }, 400);
  }

  if (!data.did || !Array.isArray(data.events) || data.events.length === 0) {
    return jsonResponse({ error: 'missing_fields' }, 400);
  }

  // Rate limit: 1 batch per 30s per device ID (Cache API, no KV cost)
  const meta = parseRequestMeta(request);
  if (await checkRateLimit(`ev_${data.did}`, 30)) {
    return jsonResponse({ error: 'rate_limited', retry_after: 30 }, 429);
  }

  const now = Date.now();
  const id = eventsR2Key(data.did, now);
  const entry = {
    id,
    did: data.did,
    app_v: data.app_v || '',
    os: data.os || '',
    os_v: data.os_v || '',
    country: meta.country,
    city: meta.city,
    region: meta.region,
    timezone: meta.timezone,
    events: data.events.slice(0, 100), // raised cap: 100 events per batch
    receivedAt: new Date(now).toISOString(),
  };

  // Write to R2 (primary storage, no TTL — permanent)
  if (env.ANALYTICS) {
    await env.ANALYTICS.put(id, JSON.stringify(entry), {
      httpMetadata: { contentType: 'application/json' },
      customMetadata: { did: data.did, app_v: data.app_v || '', country: meta.country, city: meta.city, region: meta.region },
    });
  } else if (env.EVENTS) {
    // Fallback: write to KV if R2 not configured yet
    await env.EVENTS.put(`ev_${data.did}_${now}`, JSON.stringify(entry), { expirationTtl: 86400 * 30 });
  }

  return jsonResponse({ ok: true, id, count: entry.events.length });
}

async function handleEventsGet(request, env) {
  const url = new URL(request.url);
  const secret = url.searchParams.get('secret') || request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET || 'maggoogo-admin-2026';
  if (secret !== adminSecret) {
    return jsonResponse({ error: 'unauthorized' }, 401);
  }

  // Determine date range: ?days=N (default 30, max 90)
  const days = Math.min(parseInt(url.searchParams.get('days')) || 30, 90);
  const raw = url.searchParams.get('raw') === '1';

  const batches = [];
  let totalEvents = 0;
  const devices = new Set();
  const eventCounts = {};

  const seenIds = new Set();
  const addBatch = (batch) => {
    const key = batch.id || `${batch.did}_${batch.receivedAt}`;
    if (seenIds.has(key)) return;
    seenIds.add(key);
    batches.push(batch);
    devices.add(batch.did);
    totalEvents += (batch.events || []).length;
    for (const ev of (batch.events || [])) {
      eventCounts[ev.e] = (eventCounts[ev.e] || 0) + 1;
    }
  };

  // Subrequest budget (Workers limit = 1000)
  let subreqs = 0;
  const SUBREQ_LIMIT = 900; // leave headroom

  // ── R2 (new data) ──
  if (env.ANALYTICS) {
    const prefixes = [];
    for (let i = 0; i < days; i++) {
      const d = new Date(Date.now() - i * 86400_000);
      const y = d.getUTCFullYear();
      const m = String(d.getUTCMonth() + 1).padStart(2, '0');
      const dd = String(d.getUTCDate()).padStart(2, '0');
      prefixes.push(`events/${y}/${m}/${dd}/`);
    }
    for (const prefix of prefixes) {
      if (subreqs >= SUBREQ_LIMIT) break;
      let cursor = undefined;
      let safety = 0;
      do {
        const listResult = await env.ANALYTICS.list({ prefix, cursor, limit: 500 });
        subreqs++;
        for (const obj of listResult.objects) {
          if (subreqs >= SUBREQ_LIMIT) break;
          const val = await env.ANALYTICS.get(obj.key);
          subreqs++;
          if (!val) continue;
          addBatch(await val.json());
        }
        cursor = listResult.truncated ? listResult.cursor : undefined;
        safety++;
      } while (cursor && safety < 20 && subreqs < SUBREQ_LIMIT);
    }
  }

  // ── KV data (date-filtered by key timestamp to avoid reading everything) ──
  if (env.EVENTS && subreqs < SUBREQ_LIMIT) {
    const cutoffMs = Date.now() - days * 86400_000;
    let kvCursor = undefined;
    let safety = 0;
    do {
      const list = await env.EVENTS.list({ prefix: 'ev_', limit: 1000, cursor: kvCursor });
      subreqs++;
      for (const key of list.keys) {
        if (subreqs >= SUBREQ_LIMIT) break;
        // Key format: ev_{did}_{timestamp} — extract timestamp (last segment)
        const ts = parseInt(key.name.split('_').pop());
        if (ts && ts < cutoffMs) continue; // skip without subrequest
        const val = await env.EVENTS.get(key.name);
        subreqs++;
        if (!val) continue;
        addBatch(JSON.parse(val));
      }
      kvCursor = list.list_complete ? undefined : list.cursor;
      safety++;
    } while (kvCursor && safety < 10 && subreqs < SUBREQ_LIMIT);
  }

  if (batches.length === 0 && !env.ANALYTICS && !env.EVENTS) {
    return jsonResponse({ error: 'storage_not_configured' }, 500);
  }

  return jsonResponse({
    summary: {
      batches: batches.length,
      devices: devices.size,
      totalEvents,
      eventCounts,
    },
    ...(raw ? { batches } : {}),
  });
}

// ────────────────────────────────────────────────────────────────────
// APK download proxy (mirrors GitHub Releases for China users)
// ────────────────────────────────────────────────────────────────────

async function handleDownload(request, env, path) {
  // Path format: /download/v0.1.8/MagGoogo-v0.1.8.apk
  const match = path.match(/^\/download\/(v[\d.]+)\/(.+\.apk)$/);
  if (!match) {
    return jsonResponse({ error: 'invalid_download_path', example: '/download/v0.1.8/MagGoogo-v0.1.8.apk' }, 400);
  }

  const [, tag, filename] = match;
  const r2Key = `${tag}/${filename}`;

  // Try R2 first (fast, no egress fees, global CDN)
  if (env.RELEASES) {
    const obj = await env.RELEASES.get(r2Key);
    if (obj) {
      return new Response(obj.body, {
        status: 200,
        headers: {
          'Content-Type': 'application/vnd.android.package-archive',
          'Content-Disposition': `attachment; filename="${filename}"`,
          'Content-Length': obj.size.toString(),
          'Cache-Control': 'public, max-age=86400',
          ...corsHeaders(),
        },
      });
    }
  }

  // Fallback: proxy from GitHub Releases
  const githubUrl = `https://github.com/734496335/maggoogo-sources/releases/download/${tag}/${filename}`;
  const upstream = await fetch(githubUrl, {
    headers: { 'User-Agent': 'MagGoogo-Gateway/1.0' },
    redirect: 'follow',
  });

  if (!upstream.ok) {
    return jsonResponse({ error: 'download_not_found', tag, filename }, 404);
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': 'application/vnd.android.package-archive',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Content-Length': upstream.headers.get('Content-Length') || '',
      'Cache-Control': 'public, max-age=86400',
      ...corsHeaders(),
    },
  });
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
        case '/api/events':
          if (request.method === 'POST') return await handleEventsPost(request, env);
          if (request.method === 'GET') return await handleEventsGet(request, env);
          return jsonResponse({ error: 'method_not_allowed' }, 405);
        default:
          // Handle /api/feedback/:id DELETE
          if (path.startsWith('/api/feedback/') && request.method === 'DELETE') {
            return await handleFeedbackDelete(request, env, path);
          }
          // Handle /download/vX.Y.Z/filename.apk
          if (path.startsWith('/download/')) {
            return await handleDownload(request, env, path);
          }
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
