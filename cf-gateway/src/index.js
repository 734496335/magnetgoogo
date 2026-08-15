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

function isValidMutableConfig(value) {
  return Boolean(
    value
    && typeof value === 'object'
    && typeof value.latest_version === 'string'
    && value.latest_version
    && typeof value.min_version === 'string'
    && value.min_version
    && value.download
    && typeof value.download === 'object'
  );
}

// Mutable config is correctness-sensitive control-plane state. Always ask the
// canonical GitHub Raw authority first and validate the JSON before accepting
// it. CF Pages is a fallback only; unlike immutable release objects, config is
// never served from the Gateway Cache API.
async function loadMutableConfig(env) {
  const candidates = [
    { name: 'github-raw', url: `${env.GITHUB_RAW}/config.json` },
    { name: 'cf-pages', url: `${CF_PAGES_BASE}/config.json` },
  ];
  let lastError = null;
  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate.url, {
        headers: {
          'User-Agent': 'MagGoogo-Gateway/1.0',
          'Cache-Control': 'no-cache',
        },
      });
      if (!response.ok) throw new Error(`${candidate.name} ${response.status}`);
      const text = await response.text();
      const config = JSON.parse(text);
      if (!isValidMutableConfig(config)) throw new Error(`${candidate.name} invalid_config`);
      return { config, text, authority: candidate.name };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('config_unavailable');
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

async function handleConfig(_request, env) {
  try {
    const loaded = await loadMutableConfig(env);
    return new Response(loaded.text, {
      status: 200,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Config-Authority': loaded.authority,
        ...corsHeaders(),
      },
    });
  } catch {
    return jsonResponse({ error: 'config_unavailable' }, 502, { 'Cache-Control': 'no-store' });
  }
}

async function handleSources(request, env) {
  const meta = parseRequestMeta(request);

  // ── Step 1: Fetch authoritative config to get min_version ──
  const noCache = (request.headers.get('Cache-Control') || '').includes('no-cache');
  let minVersion = '0.0.0';
  try {
    const loaded = await loadMutableConfig(env);
    minVersion = loaded.config.min_version || '0.0.0';
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

  // Fetch correctness-sensitive config from the same authority path used by
  // /config.json and the source-pack version gate.
  let config = {};
  try {
    config = (await loadMutableConfig(env)).config;
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
  // FR-07: Only accept X-Admin-Secret header — never query param (URL leaks into logs/Referer)
  const secret = request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET;
  if (!adminSecret) return jsonResponse({ error: 'ADMIN_SECRET not configured' }, 503);
  if (secret !== adminSecret) {
    return jsonResponse({ error: 'unauthorized' }, 401);
  }
  if (!env.FEEDBACK) {
    return jsonResponse({ error: 'kv_not_configured' }, 500);
  }
  const list = await env.FEEDBACK.list({ prefix: 'fb_', limit: 100 });
  const results = await Promise.all(
    list.keys.map(async (key) => {
      try {
        const val = await env.FEEDBACK.get(key.name);
        return val ? JSON.parse(val) : null;
      } catch {
        return null;
      }
    })
  );
  const items = results.filter(item => item !== null);
  items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  return jsonResponse({ count: items.length, items });
}

async function handleFeedbackDelete(request, env, path) {
  const secret = request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET;
  if (!adminSecret) return jsonResponse({ error: 'ADMIN_SECRET not configured' }, 503);
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

const ANALYTICS_MAX_BODY_BYTES = 32768;
const ANALYTICS_MAX_EVENTS_PER_BATCH = 100;
const ANALYTICS_PAGE_SIZE_MAX = 100; // 100 R2 GETs + one list remain far below the internal-service subrequest ceiling while reducing cursor round trips.
const ANALYTICS_MAX_EVENT_AGE_MS = 45 * 86400_000;
const ANALYTICS_MAX_FUTURE_SKEW_MS = 5 * 60_000;
const ANALYTICS_EVENT_NAMES = new Set([
  'first_open', 'app_start', 'source_sync_result',
  'search', 'search_submitted', 'search_completed',
  'open_magnet', 'copy_magnet',
  'src_ok', 'src_fail', 'src_empty', 'verify',
  'session_start', 'session_summary',
  'update_prompt_shown', 'update_action', 'update_download_started',
  'update_download_result', 'installer_launched', 'post_update_start',
  'resources_tab_view', 'resource_feed_refresh_result', 'media_detail_view', 'media_load_result',
  'media_resource_action', 'favorite_changed', 'config_check_result', 'crash_summary',
]);

function analyticsToken(value, fallback, maxLength = 160) {
  const normalized = String(value || '')
    .trim()
    .replace(/[^a-zA-Z0-9_.-]/g, '_')
    .slice(0, maxLength);
  return normalized || fallback;
}

function analyticsStableHash(value) {
  let hash = 2166136261;
  const input = String(value || '');
  for (let index = 0; index < input.length; index++) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function analyticsDayPrefix(day) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day || '')) return '';
  const [year, month, date] = day.split('-');
  return `events/${year}/${month}/${date}/`;
}

function eventsR2Key(deviceId, ts, batchId) {
  const d = new Date(ts);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const safeDevice = analyticsToken(deviceId, 'unknown-device', 96);
  const safeBatch = analyticsToken(batchId, `legacy_${ts}`, 180);
  return `events/${y}/${m}/${dd}/${safeDevice}/${safeBatch}.json`;
}

function dedupeAnalyticsEvents(events, now = Date.now()) {
  const seen = new Set();
  const result = [];
  for (const event of Array.isArray(events) ? events : []) {
    if (!event || typeof event !== 'object') continue;
    const name = typeof event.e === 'string' ? event.e.trim().slice(0, 64) : '';
    const ts = Number(event.ts);
    if (!ANALYTICS_EVENT_NAMES.has(name) || !Number.isFinite(ts) || ts <= 0) continue;
    if (ts < now - ANALYTICS_MAX_EVENT_AGE_MS || ts > now + ANALYTICS_MAX_FUTURE_SKEW_MS) continue;
    const id = typeof event.id === 'string' ? event.id.trim().slice(0, 180) : '';
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    result.push({ ...event, e: name, ts, ...(id ? { id } : {}) });
    if (result.length >= ANALYTICS_MAX_EVENTS_PER_BATCH) break;
  }
  return result;
}

function summarizeAnalyticsBatches(batches) {
  const devices = new Set();
  const eventIds = new Set();
  const eventCounts = {};
  let totalEvents = 0;
  for (const batch of batches) {
    const deviceId = batch.device_id || batch.did;
    if (deviceId) devices.add(deviceId);
    for (const event of (batch.events || [])) {
      if (event.id && eventIds.has(event.id)) continue;
      if (event.id) eventIds.add(event.id);
      eventCounts[event.e] = (eventCounts[event.e] || 0) + 1;
      totalEvents += 1;
    }
  }
  return { batches: batches.length, devices: devices.size, totalEvents, eventCounts };
}

async function readAnalyticsRequestBody(request) {
  const declaredLength = Number.parseInt(request.headers.get('content-length') || '', 10);
  if (Number.isFinite(declaredLength) && declaredLength > ANALYTICS_MAX_BODY_BYTES) {
    return { tooLarge: true, body: '' };
  }
  if (!request.body) return { tooLarge: false, body: '' };

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let totalBytes = 0;
  let body = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > ANALYTICS_MAX_BODY_BYTES) {
        await reader.cancel('analytics payload too large').catch(() => {});
        return { tooLarge: true, body: '' };
      }
      body += decoder.decode(value, { stream: true });
    }
    body += decoder.decode();
    return { tooLarge: false, body };
  } finally {
    reader.releaseLock();
  }
}

async function handleEventsPost(request, env) {
  const bodyResult = await readAnalyticsRequestBody(request);
  if (bodyResult.tooLarge) {
    return jsonResponse({ error: 'payload_too_large', max: ANALYTICS_MAX_BODY_BYTES }, 400);
  }
  const body = bodyResult.body;

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    return jsonResponse({ error: 'invalid_json' }, 400);
  }

  const now = Date.now();
  const installId = analyticsToken(data.install_id || data.did, '', 120);
  const legacyDid = analyticsToken(data.legacy_did || data.did, installId, 120);
  const deviceId = analyticsToken(data.device_id || data.did || installId, '', 120);
  const events = dedupeAnalyticsEvents(data.events, now);
  const legacyBatchId = `legacy_${analyticsStableHash(JSON.stringify(events))}`;
  const batchId = analyticsToken(data.batch_id || legacyBatchId, '', 180);
  if (!deviceId || !installId || events.length === 0) {
    return jsonResponse({ error: 'missing_fields' }, 400);
  }

  // Short device and IP guards reduce accidental loops and low-effort endpoint abuse.
  const meta = parseRequestMeta(request);
  if (await checkRateLimit(`ev_${deviceId}`, 5)) {
    return jsonResponse({ error: 'rate_limited', retry_after: 5 }, 429);
  }
  if (meta.ip && await checkRateLimit(`ev_ip_${analyticsToken(meta.ip, 'unknown-ip', 80)}`, 1)) {
    return jsonResponse({ error: 'rate_limited', retry_after: 1 }, 429);
  }

  const id = eventsR2Key(deviceId, now, batchId);
  const entry = {
    id,
    schema_v: Number(data.schema_v) || 1,
    batch_id: batchId,
    did: installId,
    legacy_did: legacyDid,
    device_id: deviceId,
    device_id_kind: analyticsToken(data.device_id_kind, 'legacy', 40),
    install_id: installId,
    app_v: String(data.app_v || '').slice(0, 32),
    version_code: String(data.version_code || '').slice(0, 24),
    package_name: String(data.package_name || '').slice(0, 120),
    build_type: data.build_type === 'debug' ? 'debug' : 'release',
    distribution: String(data.distribution || '').slice(0, 40),
    session_id: analyticsToken(data.session_id, '', 160),
    os: String(data.os || '').slice(0, 24),
    os_v: String(data.os_v || '').slice(0, 48),
    country: meta.country,
    city: meta.city,
    region: meta.region,
    timezone: meta.timezone,
    events,
    receivedAt: new Date(now).toISOString(),
  };

  // R2 is the raw 30-day event store. Bucket lifecycle must expire the events/ prefix.
  if (env.ANALYTICS) {
    await env.ANALYTICS.put(id, JSON.stringify(entry), {
      httpMetadata: { contentType: 'application/json' },
      customMetadata: {
        device_id: deviceId,
        install_id: installId,
        app_v: entry.app_v,
        build_type: entry.build_type,
        country: meta.country,
      },
    });
  } else if (env.EVENTS) {
    // Fallback: deterministic key also makes retries idempotent in KV.
    await env.EVENTS.put(`ev_${deviceId}_${batchId}`, JSON.stringify(entry), { expirationTtl: 86400 * 30 });
  }

  return jsonResponse({ ok: true, id, batch_id: batchId, count: entry.events.length, schema_v: entry.schema_v });
}

async function handleAnalyticsDayPage(url, env, day, raw) {
  if (!env.ANALYTICS) {
    return jsonResponse({ error: 'r2_analytics_not_configured' }, 503);
  }
  const prefix = analyticsDayPrefix(day);
  if (!prefix) return jsonResponse({ error: 'invalid_day', expected: 'YYYY-MM-DD' }, 400);

  const requestedLimit = Number.parseInt(url.searchParams.get('limit') || '', 10);
  const limit = Math.max(1, Math.min(Number.isFinite(requestedLimit) ? requestedLimit : ANALYTICS_PAGE_SIZE_MAX, ANALYTICS_PAGE_SIZE_MAX));
  const cursor = url.searchParams.get('cursor') || undefined;
  const listed = await env.ANALYTICS.list({ prefix, cursor, limit });
  const values = await Promise.all(listed.objects.map(async (object) => {
    try {
      const value = await env.ANALYTICS.get(object.key);
      if (!value) return { ok: false, key: object.key, batch: null };
      return { ok: true, key: object.key, batch: await value.json() };
    } catch {
      return { ok: false, key: object.key, batch: null };
    }
  }));
  const failedReads = values.filter((item) => !item.ok);
  if (failedReads.length > 0) {
    return jsonResponse({
      error: 'analytics_page_object_read_failed',
      day,
      failed_objects: failedReads.length,
      listed: listed.objects.length,
    }, 503);
  }
  const batches = values.map((item) => item.batch);
  const summary = summarizeAnalyticsBatches(batches);
  return jsonResponse({
    summary,
    ...(raw ? { batches } : {}),
    page: {
      day,
      prefix,
      listed: listed.objects.length,
      returned: batches.length,
      truncated: Boolean(listed.truncated),
      next_cursor: listed.truncated ? listed.cursor : null,
      complete: !listed.truncated,
      page_size: limit,
    },
  });
}

async function handleEventsGet(request, env) {
  const url = new URL(request.url);
  // FR-07: Only accept X-Admin-Secret header — never query param
  const secret = request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET;
  if (!adminSecret) return jsonResponse({ error: 'ADMIN_SECRET not configured' }, 503);
  if (secret !== adminSecret) {
    return jsonResponse({ error: 'unauthorized' }, 401);
  }

  const raw = url.searchParams.get('raw') === '1';
  const day = url.searchParams.get('day');
  if (day) {
    return handleAnalyticsDayPage(url, env, day, raw);
  }

  // Legacy multi-day endpoint remains during the admin migration window.
  const days = Math.min(parseInt(url.searchParams.get('days')) || 30, 90);

  const batches = [];
  let totalEvents = 0;
  const devices = new Set();
  const eventCounts = {};

  const seenIds = new Set();
  const seenEventIds = new Set();
  const addBatch = (batch) => {
    const key = batch.id || `${batch.device_id || batch.did}_${batch.receivedAt}`;
    if (seenIds.has(key)) return;
    seenIds.add(key);
    batches.push(batch);
    const deviceId = batch.device_id || batch.did;
    if (deviceId) devices.add(deviceId);
    for (const ev of (batch.events || [])) {
      if (ev.id && seenEventIds.has(ev.id)) continue;
      if (ev.id) seenEventIds.add(ev.id);
      eventCounts[ev.e] = (eventCounts[ev.e] || 0) + 1;
      totalEvents += 1;
    }
  };

  // Legacy compatibility stays below the Workers Free 1000 internal-service subrequest limit.
  // New admin clients use explicit day+cursor pages for completeness and bounded CPU.
  let subreqs = 0;
  const SUBREQ_LIMIT = 900;

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
        const remainingLimit = SUBREQ_LIMIT - subreqs;
        const objsToFetch = listResult.objects.slice(0, remainingLimit);

        const results = await Promise.all(
          objsToFetch.map(async (obj) => {
            try {
              const val = await env.ANALYTICS.get(obj.key);
              return val ? await val.json() : null;
            } catch {
              return null;
            }
          })
        );
        subreqs += objsToFetch.length;

        for (const data of results) {
          if (data) {
            addBatch(data);
          }
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
      const keysToFetch = [];
      for (const key of list.keys) {
        const ts = parseInt(key.name.split('_').pop());
        if (ts && ts < cutoffMs) continue;
        keysToFetch.push(key);
      }

      const remainingLimit = SUBREQ_LIMIT - subreqs;
      const limitedKeys = keysToFetch.slice(0, remainingLimit);

      const results = await Promise.all(
        limitedKeys.map(async (key) => {
          try {
            const val = await env.EVENTS.get(key.name);
            return val ? JSON.parse(val) : null;
          } catch {
            return null;
          }
        })
      );
      subreqs += limitedKeys.length;

      for (const data of results) {
        if (data) {
          addBatch(data);
        }
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
    page: {
      legacy: true,
      complete: subreqs < SUBREQ_LIMIT,
      truncated: subreqs >= SUBREQ_LIMIT,
      subrequests: subreqs,
      hint: 'Use ?day=YYYY-MM-DD&cursor=... for complete pagination',
    },
  });
}

// ────────────────────────────────────────────────────────────────────
// Media release proxy (read-only R2 network fallback)
// ────────────────────────────────────────────────────────────────────

async function handleMediaRelease(request, env, path) {
  if (!['GET', 'HEAD'].includes(request.method)) {
    return jsonResponse({ error: 'method_not_allowed' }, 405);
  }
  if (!env.MEDIA) {
    return jsonResponse({ error: 'media_release_store_unavailable' }, 503);
  }
  const key = path.slice('/media/'.length);
  if (
    !key
    || !key.startsWith('v1/')
    || key.includes('..')
    || key.includes('\\')
    || key.startsWith('/')
  ) {
    return jsonResponse({ error: 'invalid_media_path' }, 400);
  }
  const obj = await env.MEDIA.get(key);
  if (!obj) {
    return jsonResponse({ error: 'media_object_not_found' }, 404);
  }
  const headers = new Headers(corsHeaders());
  headers.set('Content-Type', obj.httpMetadata?.contentType || (key.endsWith('.json') ? 'application/json' : 'application/octet-stream'));
  headers.set('Content-Length', String(obj.size));
  if (obj.httpEtag) headers.set('ETag', obj.httpEtag);
  headers.set(
    'Cache-Control',
    key === 'v1/current.json'
      ? 'no-store, no-cache, must-revalidate'
      : 'public, max-age=31536000, immutable',
  );
  return new Response(request.method === 'HEAD' ? null : obj.body, {
    status: 200,
    headers,
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
          if (path.startsWith('/media/')) {
            return await handleMediaRelease(request, env, path);
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
