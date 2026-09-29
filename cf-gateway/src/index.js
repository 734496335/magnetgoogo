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

  // GitHub Raw is the auto-renewed source authority. CF Pages is a static
  // deployment fallback and may lag behind envelope refresh commits.
  let response;
  try {
    response = await fetch(url, {
      headers: { 'User-Agent': 'MagGoogo-Gateway/1.0' },
    });
    if (!response.ok) throw new Error(`GitHub Raw ${response.status}`);
  } catch {
    response = await fetch(`${CF_PAGES_BASE}${path}`, {
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

function eventsR2Key(did, ts) {
  const d = new Date(ts);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `events/${y}/${m}/${dd}/${did}_${ts}.json`;
}

function utcDayString(offsetDays = 0) {
  const d = new Date(Date.now() - offsetDays * 86400_000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
}

function eventsDayPrefix(day) {
  const match = String(day || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return '';
  return `events/${match[1]}/${match[2]}/${match[3]}/`;
}

function updateKeyFingerprintHash(hash, key) {
  const text = `${String(key)}\n`;
  let next = hash >>> 0;
  for (let i = 0; i < text.length; i += 1) {
    next ^= text.charCodeAt(i);
    next = Math.imul(next, 0x01000193) >>> 0;
  }
  return next >>> 0;
}

function keyFingerprint(keys) {
  const sorted = [...keys].map(String).sort();
  let hash = 0x811c9dc5;
  for (const key of sorted) hash = updateKeyFingerprintHash(hash, key);
  return `${sorted.length}:${hash.toString(16).padStart(8, '0')}`;
}

function inventoryFingerprint(count, firstKey, lastKey) {
  let hash = 0x811c9dc5;
  if (firstKey) hash = updateKeyFingerprintHash(hash, firstKey);
  if (lastKey && lastKey !== firstKey) hash = updateKeyFingerprintHash(hash, lastKey);
  return `${count}:${hash.toString(16).padStart(8, '0')}`;
}

function analyticsUploadedBeforeMs(url) {
  const raw = url.searchParams.get('uploadedBefore');
  if (!raw) return 0;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.trunc(value) : -1;
}

function analyticsObjectsAtCutoff(objects, uploadedBefore) {
  if (!uploadedBefore) return objects;
  return objects.filter((obj) => obj?.uploaded instanceof Date && obj.uploaded.getTime() <= uploadedBefore);
}

async function listEventsDayInventory(env, day, uploadedBefore = 0) {
  const prefix = eventsDayPrefix(day);
  if (!prefix) throw new Error(`invalid analytics day: ${day}`);
  // Worker Free CPU is extremely tight. Do no per-object JS work here: R2 list
  // already returns lexicographically ordered keys, so count + first/last key
  // gives a deterministic append-only partition signature in O(number of R2
  // pages), not O(number of objects). Full page recovery still verifies exact
  // batch count and de-duplicates IDs before a repaired partition is accepted.
  let count = 0;
  let firstKey = '';
  let lastKey = '';
  let pages = 0;
  let cursor;
  do {
    const listed = await env.ANALYTICS.list({ prefix, cursor, limit: 1000, include: [] });
    pages += 1;
    const objects = analyticsObjectsAtCutoff(listed.objects, uploadedBefore);
    count += objects.length;
    if (objects.length > 0) {
      if (!firstKey) firstKey = objects[0].key;
      lastKey = objects[objects.length - 1].key;
    }
    cursor = listed.truncated ? listed.cursor : undefined;
    if (pages > 100) throw new Error(`analytics inventory pagination exceeded safety limit for ${day}`);
  } while (cursor);
  return {
    day,
    prefix,
    count,
    fingerprint: inventoryFingerprint(count, firstKey, lastKey),
    firstKey,
    lastKey,
    pages,
    uploadedBefore: uploadedBefore || null,
  };
}

async function handleEventsInventory(url, env) {
  if (!env.ANALYTICS) return jsonResponse({ error: 'storage_not_configured' }, 500);
  const uploadedBefore = analyticsUploadedBeforeMs(url);
  if (uploadedBefore < 0) return jsonResponse({ error: 'invalid_uploadedBefore', expected: 'positive epoch milliseconds' }, 400);
  const exactDay = String(url.searchParams.get('day') || '');
  if (exactDay) {
    if (!eventsDayPrefix(exactDay)) return jsonResponse({ error: 'invalid_day', expected: 'YYYY-MM-DD' }, 400);
    return jsonResponse({ mode: 'inventory', complete: true, uploadedBefore: uploadedBefore || null, inventory: [await listEventsDayInventory(env, exactDay, uploadedBefore)] });
  }
  const days = Math.min(Math.max(parseInt(url.searchParams.get('days')) || 31, 1), 90);
  const dayOffset = Math.max(parseInt(url.searchParams.get('dayOffset')) || 0, 0);
  const inventory = [];
  for (let i = dayOffset; i < dayOffset + days; i += 1) {
    inventory.push(await listEventsDayInventory(env, utcDayString(i), uploadedBefore));
  }
  return jsonResponse({ mode: 'inventory', complete: true, uploadedBefore: uploadedBefore || null, inventory });
}

async function handleEventsInventoryPage(url, env) {
  if (!env.ANALYTICS) return jsonResponse({ error: 'storage_not_configured' }, 500);
  const uploadedBefore = analyticsUploadedBeforeMs(url);
  if (uploadedBefore < 0) return jsonResponse({ error: 'invalid_uploadedBefore', expected: 'positive epoch milliseconds' }, 400);
  const day = String(url.searchParams.get('day') || '');
  const prefix = eventsDayPrefix(day);
  if (!prefix) return jsonResponse({ error: 'invalid_day', expected: 'YYYY-MM-DD' }, 400);
  const limit = Math.min(Math.max(parseInt(url.searchParams.get('limit')) || 250, 1), 250);
  const cursor = url.searchParams.get('cursor') || undefined;
  // Exactly one R2.list per Worker invocation. Large-day aggregation happens in
  // the local Admin process so Worker CPU is independent of daily batch volume.
  const listed = await env.ANALYTICS.list({ prefix, cursor, limit, include: [] });
  const objects = analyticsObjectsAtCutoff(listed.objects, uploadedBefore);
  return jsonResponse({
    mode: 'inventory_page',
    day,
    uploadedBefore: uploadedBefore || null,
    page: {
      count: objects.length,
      firstKey: objects.length ? objects[0].key : '',
      lastKey: objects.length ? objects[objects.length - 1].key : '',
      nextCursor: listed.truncated ? listed.cursor : null,
      complete: !listed.truncated,
    },
  });
}

async function handleEventsPage(url, env) {
  if (!env.ANALYTICS) return jsonResponse({ error: 'storage_not_configured' }, 500);
  const uploadedBefore = analyticsUploadedBeforeMs(url);
  if (uploadedBefore < 0) return jsonResponse({ error: 'invalid_uploadedBefore', expected: 'positive epoch milliseconds' }, 400);
  const day = String(url.searchParams.get('day') || '');
  const prefix = eventsDayPrefix(day);
  if (!prefix) return jsonResponse({ error: 'invalid_day', expected: 'YYYY-MM-DD' }, 400);
  const limit = Math.min(Math.max(parseInt(url.searchParams.get('limit')) || 20, 1), 25);
  const cursor = url.searchParams.get('cursor') || undefined;
  const listed = await env.ANALYTICS.list({ prefix, cursor, limit });
  const objects = analyticsObjectsAtCutoff(listed.objects, uploadedBefore);
  const results = await Promise.all(objects.map(async (obj) => {
    const stored = await env.ANALYTICS.get(obj.key);
    if (!stored) throw new Error(`analytics object disappeared during page read: ${obj.key}`);
    return await stored.json();
  }));
  return jsonResponse({
    mode: 'page',
    day,
    prefix,
    uploadedBefore: uploadedBefore || null,
    batches: results,
    page: {
      count: results.length,
      fingerprint: keyFingerprint(objects.map((obj) => obj.key)),
      nextCursor: listed.truncated ? listed.cursor : null,
      complete: !listed.truncated,
    },
  });
}

function growthR2Key(ts) {
  const d = new Date(ts);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `growth-events/${y}/${m}/${dd}/${ts}_${crypto.randomUUID()}.json`;
}

function sanitizeGrowthToken(value, max = 96) {
  return String(value || '')
    .trim()
    .slice(0, max)
    .replace(/[^a-zA-Z0-9._~:/-]/g, '');
}

const ACQUISITION_SOURCES = new Set([
  'direct', 'internal', 'google', 'baidu', 'bing', 'sogou', '360', 'shenma',
  'yahoo', 'yandex', 'duckduckgo', 'brave', 'ecosia',
  'chatgpt', 'perplexity', 'copilot', 'gemini', 'claude',
  'naoshiquan', 'github', 'reddit', 'zhihu', 'v2ex', 'coolapk', '52pojie',
  'bilibili', 'telegram', 'producthunt', 'uptodown', 'alternativeto', 'x', 'youtube',
  'referral', 'unknown',
]);

function sanitizeAcquisitionSource(value) {
  const source = String(value || '').trim().toLowerCase();
  return ACQUISITION_SOURCES.has(source) ? source : 'unknown';
}

function opsDayKey(ts) {
  return new Date(ts + 8 * 3600_000).toISOString().slice(0, 10);
}

async function resolveLatestDownload(env) {
  const configResp = await fetchUpstream(env, '/config.json', env.CACHE_TTL, false);
  if (!configResp.ok) throw new Error('latest_download_config_unavailable');
  const config = await configResp.clone().json();
  const target = String(config?.download?.primary || '').trim();
  if (!/^https:\/\//i.test(target)) throw new Error('latest_download_url_invalid');
  return {
    target,
    version: sanitizeGrowthToken(config.latest_version || '', 24),
  };
}

const GROWTH_INDEX_FAILURE_KEY = 'growth-index-health/unresolved.json';
const GROWTH_READ_INITIALIZED_META = 'growth_read_model_initialized';

function growthAggregateStatement(env, payload, count = 1) {
  const day = opsDayKey(Number(payload.ts) || Date.now());
  const ts = Number(payload.ts) || Date.now();
  return env.OPS_DB.prepare(`
    INSERT INTO growth_daily_dims(
      day,event_type,page,locale,placement,country,requested_version,target_version,event_count,first_ts,last_ts
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(day,event_type,page,locale,placement,country,requested_version,target_version)
    DO UPDATE SET
      event_count=growth_daily_dims.event_count+excluded.event_count,
      first_ts=MIN(growth_daily_dims.first_ts,excluded.first_ts),
      last_ts=MAX(growth_daily_dims.last_ts,excluded.last_ts)
  `).bind(
    day,
    String(payload.type || ''),
    String(payload.page || ''),
    String(payload.locale || ''),
    String(payload.placement || ''),
    String(payload.country || ''),
    String(payload.requested_version || ''),
    String(payload.target_version || ''),
    count,
    ts,
    ts,
  );
}

function growthAttributionSource(payload) {
  const explicit = sanitizeAcquisitionSource(payload?.source);
  if (explicit !== 'unknown') return explicit;
  const placement = String(payload?.placement || '');
  if (String(payload?.type || '') === 'landing_view' && placement.startsWith('qualified_view:')) {
    return sanitizeAcquisitionSource(placement.slice('qualified_view:'.length));
  }
  if (String(payload?.type || '') === 'seo_download_click' && String(payload?.page || '').startsWith('nsq:')) {
    return 'naoshiquan';
  }
  return 'unknown';
}

function growthAttributionAggregateStatement(env, payload, count = 1) {
  const day = opsDayKey(Number(payload.ts) || Date.now());
  const ts = Number(payload.ts) || Date.now();
  const source = growthAttributionSource(payload);
  return env.OPS_DB.prepare(`
    INSERT INTO growth_attribution_daily_dims(
      day,event_type,page,source,locale,placement,country,event_count,first_ts,last_ts
    ) VALUES (?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(day,event_type,page,source,locale,placement,country)
    DO UPDATE SET
      event_count=growth_attribution_daily_dims.event_count+excluded.event_count,
      first_ts=MIN(growth_attribution_daily_dims.first_ts,excluded.first_ts),
      last_ts=MAX(growth_attribution_daily_dims.last_ts,excluded.last_ts)
  `).bind(
    day,
    String(payload.type || ''),
    String(payload.page || ''),
    source,
    String(payload.locale || ''),
    String(payload.placement || ''),
    String(payload.country || ''),
    count,
    ts,
    ts,
  );
}

function growthFirstPartyAggregateStatement(env, payload, count = 1) {
  const day = opsDayKey(Number(payload.ts) || Date.now());
  const ts = Number(payload.ts) || Date.now();
  // Cross-origin requests from magnetgoogo.com to api.naoshiquan.com normally
  // reduce Referer to the site origin, so referrer_path becomes '/'. Trust is
  // established separately by referrer_class; use the explicit CTA/page key for
  // page attribution so every first-party SEO click is not collapsed into '/'.
  const sourcePage = String(payload.page || payload.referrer_path || '');
  return env.OPS_DB.prepare(`
    INSERT INTO growth_first_party_daily_dims(
      day,event_type,source_page,locale,placement,country,target_version,event_count,first_ts,last_ts
    ) VALUES (?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(day,event_type,source_page,locale,placement,country,target_version)
    DO UPDATE SET
      event_count=growth_first_party_daily_dims.event_count+excluded.event_count,
      first_ts=MIN(growth_first_party_daily_dims.first_ts,excluded.first_ts),
      last_ts=MAX(growth_first_party_daily_dims.last_ts,excluded.last_ts)
  `).bind(
    day,
    String(payload.type || ''),
    sourcePage,
    String(payload.locale || ''),
    String(payload.placement || ''),
    String(payload.country || ''),
    String(payload.target_version || ''),
    count,
    ts,
    ts,
  );
}

function growthReferrerClass(request) {
  const ref = String(request.headers.get('Referer') || '').trim();
  if (!ref) return { referrer_class: 'unverified', referrer_path: '' };
  try {
    const parsed = new URL(ref);
    const host = parsed.hostname.toLowerCase();
    if (host === 'magnetgoogo.com' || host === 'www.magnetgoogo.com') {
      return {
        referrer_class: 'first_party_prod',
        referrer_path: sanitizeGrowthToken(parsed.pathname || '/', 120),
      };
    }
    return { referrer_class: 'external', referrer_path: '' };
  } catch {
    return { referrer_class: 'invalid', referrer_path: '' };
  }
}

function growthMetaStatement(env, key, value, ts = Date.now()) {
  return env.OPS_DB.prepare(`
    INSERT INTO ops_index_meta(key,value,updated_at) VALUES (?,?,?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
  `).bind(key, String(value), ts);
}

async function writeGrowthIndexFailure(env, payload, error) {
  if (!env.ANALYTICS) return;
  const marker = {
    unresolved: true,
    failure_at: Date.now(),
    day: opsDayKey(Number(payload?.ts) || Date.now()),
    event_type: String(payload?.type || ''),
    reason: String(error?.message || error || 'growth_index_failed').slice(0, 300),
  };
  await env.ANALYTICS.put(GROWTH_INDEX_FAILURE_KEY, JSON.stringify(marker), {
    httpMetadata: { contentType: 'application/json' },
  });
}

async function persistGrowthEvent(env, key, payload) {
  await env.ANALYTICS.put(key, JSON.stringify(payload), {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: {
      type: payload.type,
      page: payload.page,
      locale: payload.locale,
      placement: payload.placement,
      country: payload.country,
      target_version: payload.target_version,
      source: growthAttributionSource(payload),
      referrer_class: payload.referrer_class,
    },
  });
  if (!env.OPS_DB) return;
  try {
    const statements = [growthAggregateStatement(env, payload)];
    if (payload.type === 'landing_view' || payload.type === 'seo_download_click') {
      statements.push(growthAttributionAggregateStatement(env, payload));
    }
    if (payload.referrer_class === 'first_party_prod') {
      statements.push(growthFirstPartyAggregateStatement(env, payload));
    }
    await env.OPS_DB.batch(statements);
  } catch (error) {
    await writeGrowthIndexFailure(env, payload, error).catch((markerError) => {
      console.error('[growth-index-marker]', markerError?.message || markerError);
    });
    throw error;
  }
}

function queueGrowthEvent(request, env, ctx, event) {
  if (!env.ANALYTICS || !ctx) return;
  const now = Date.now();
  const meta = parseRequestMeta(request);
  const referrer = growthReferrerClass(request);
  const payload = {
    type: event.type,
    ts: now,
    page: sanitizeGrowthToken(event.page || '', 120),
    locale: sanitizeGrowthToken(event.locale || '', 16),
    placement: sanitizeGrowthToken(event.placement || '', 40),
    source: sanitizeAcquisitionSource(event.source),
    requested_version: sanitizeGrowthToken(event.requestedVersion || '', 24),
    target_version: sanitizeGrowthToken(event.targetVersion || '', 24),
    country: sanitizeGrowthToken(meta.country || '', 8),
    region: sanitizeGrowthToken(meta.region || '', 48),
    referrer_class: referrer.referrer_class,
    referrer_path: referrer.referrer_path,
  };
  const key = growthR2Key(now);
  ctx.waitUntil(persistGrowthEvent(env, key, payload).catch((error) => {
    console.error('[growth-event]', error?.message || error);
  }));
}

function growthRequestIsFirstParty(request) {
  const origin = String(request.headers.get('Origin') || '').trim();
  if (origin) {
    try {
      const host = new URL(origin).hostname.toLowerCase();
      if (host === 'magnetgoogo.com' || host === 'www.magnetgoogo.com') return true;
    } catch { /* fall through to Referer */ }
  }
  return growthReferrerClass(request).referrer_class === 'first_party_prod';
}

async function handleGrowthView(request, env, ctx) {
  if (request.method !== 'POST') {
    return jsonResponse({ error: 'method_not_allowed' }, 405, { Allow: 'POST' });
  }
  if (!env.ANALYTICS || !env.OPS_DB) {
    return jsonResponse({ error: 'growth_storage_not_configured' }, 503);
  }
  if (!growthRequestIsFirstParty(request)) {
    return jsonResponse({ error: 'first_party_only' }, 403);
  }
  let body;
  try { body = await request.json(); } catch { return jsonResponse({ error: 'invalid_json' }, 400); }
  const page = sanitizeGrowthToken(body?.page || '', 120);
  if (!page || page.startsWith('__')) return jsonResponse({ error: 'valid_page_required' }, 400);
  const acquisitionSource = sanitizeAcquisitionSource(body?.source);
  queueGrowthEvent(request, env, ctx, {
    type: 'landing_view',
    page,
    locale: body?.locale || '',
    placement: `qualified_view:${acquisitionSource}`,
    source: acquisitionSource,
  });
  return new Response(null, {
    status: 204,
    headers: { 'Cache-Control': 'no-store', ...corsHeaders() },
  });
}

async function handleGrowthDownload(request, env, ctx) {
  if (request.method !== 'GET') {
    return jsonResponse({ error: 'method_not_allowed' }, 405, { Allow: 'GET' });
  }
  const url = new URL(request.url);
  const latest = await resolveLatestDownload(env);
  const page = sanitizeGrowthToken(url.searchParams.get('page') || '', 120);
  if (!page.startsWith('__')) {
    const referrer = growthReferrerClass(request);
    let acquisitionSource = 'unknown';
    if (page.startsWith('nsq:')) acquisitionSource = 'naoshiquan';
    else if (referrer.referrer_class === 'first_party_prod') acquisitionSource = sanitizeAcquisitionSource(url.searchParams.get('source'));
    queueGrowthEvent(request, env, ctx, {
      type: 'seo_download_click',
      page,
      locale: url.searchParams.get('locale') || '',
      placement: url.searchParams.get('placement') || '',
      source: acquisitionSource,
      targetVersion: latest.version,
    });
  }
  return new Response(null, {
    status: 302,
    headers: {
      Location: latest.target,
      'Cache-Control': 'no-store',
      ...corsHeaders(),
    },
  });
}

async function readGrowthIndexFailure(env) {
  if (!env.ANALYTICS) return null;
  const stored = await env.ANALYTICS.get(GROWTH_INDEX_FAILURE_KEY);
  if (!stored) return null;
  try { return await stored.json(); } catch { return { unresolved: true, reason: 'invalid_failure_marker' }; }
}

function growthStartDay(days) {
  return opsDayKey(Date.now() - (Math.max(1, days) - 1) * 86400_000);
}

function growthIncrement(target, key, amount) {
  if (!key || !amount) return;
  target[key] = (target[key] || 0) + amount;
}

function growthAggregateRows(rows) {
  const byDay = {};
  const byPage = {};
  const byPageDay = {};
  const byLocale = {};
  const byPlacement = {};
  const byPlacementDay = {};
  const byCountry = {};
  const byType = {};
  const engines = {
    domestic: { definition: 'Cloudflare country=CN', download_clicks: 0 },
    international: { definition: 'known Cloudflare country != CN', download_clicks: 0 },
    unknown: { definition: 'country unavailable; never inferred from locale', download_clicks: 0 },
    priority_markets: { US: 0, HK: 0, TW: 0, JP: 0, SG: 0, DE: 0 },
  };
  let total = 0;
  let lastEventTs = 0;
  for (const row of rows || []) {
    const amount = Number(row.event_count || 0);
    if (amount <= 0) continue;
    total += amount;
    lastEventTs = Math.max(lastEventTs, Number(row.last_ts || 0));
    growthIncrement(byDay, row.day, amount);
    growthIncrement(byPage, row.page || 'unknown', amount);
    if (row.day) {
      if (!byPageDay[row.day]) byPageDay[row.day] = {};
      growthIncrement(byPageDay[row.day], row.page || 'unknown', amount);
    }
    growthIncrement(byLocale, row.locale || 'unknown', amount);
    growthIncrement(byPlacement, row.placement || 'unknown', amount);
    if (row.day) {
      if (!byPlacementDay[row.day]) byPlacementDay[row.day] = {};
      growthIncrement(byPlacementDay[row.day], row.placement || 'unknown', amount);
    }
    growthIncrement(byCountry, row.country || 'unknown', amount);
    growthIncrement(byType, row.event_type || 'unknown', amount);
    if (row.event_type === 'seo_download_click') {
      const country = String(row.country || '').toUpperCase();
      if (country === 'CN') engines.domestic.download_clicks += amount;
      else if (country) engines.international.download_clicks += amount;
      else engines.unknown.download_clicks += amount;
      if (Object.prototype.hasOwnProperty.call(engines.priority_markets, country)) {
        engines.priority_markets[country] += amount;
      }
    }
  }
  return { total, byDay, byPage, byPageDay, byLocale, byPlacement, byPlacementDay, byCountry, byType, engines, lastEventTs };
}

function growthAttributionFunnel(rows) {
  const bySource = {};
  const bySourcePage = {};
  const bySourcePageDay = {};
  let firstTs = 0;
  let lastTs = 0;
  for (const row of rows || []) {
    const amount = Number(row.event_count || 0);
    if (amount <= 0) continue;
    const eventType = String(row.event_type || '');
    const metric = eventType === 'landing_view' ? 'landing_views' : eventType === 'seo_download_click' ? 'download_clicks' : '';
    if (!metric) continue;
    const source = sanitizeAcquisitionSource(row.source);
    const page = String(row.page || 'unknown') || 'unknown';
    const day = String(row.day || '');
    const rowFirstTs = Number(row.first_ts || 0);
    const rowLastTs = Number(row.last_ts || 0);
    if (rowFirstTs > 0 && (firstTs === 0 || rowFirstTs < firstTs)) firstTs = rowFirstTs;
    lastTs = Math.max(lastTs, rowLastTs);

    if (!bySource[source]) bySource[source] = { landing_views: 0, download_clicks: 0 };
    bySource[source][metric] += amount;

    if (!bySourcePage[source]) bySourcePage[source] = {};
    if (!bySourcePage[source][page]) bySourcePage[source][page] = { landing_views: 0, download_clicks: 0 };
    bySourcePage[source][page][metric] += amount;

    if (day) {
      if (!bySourcePageDay[day]) bySourcePageDay[day] = {};
      if (!bySourcePageDay[day][source]) bySourcePageDay[day][source] = {};
      if (!bySourcePageDay[day][source][page]) bySourcePageDay[day][source][page] = { landing_views: 0, download_clicks: 0 };
      bySourcePageDay[day][source][page][metric] += amount;
    }
  }

  const withRates = (entry) => ({
    ...entry,
    conversion_pct: entry.landing_views > 0
      ? Math.round((entry.download_clicks / entry.landing_views) * 10000) / 100
      : null,
  });
  for (const source of Object.keys(bySource)) bySource[source] = withRates(bySource[source]);
  for (const pages of Object.values(bySourcePage)) {
    for (const page of Object.keys(pages)) pages[page] = withRates(pages[page]);
  }
  for (const sources of Object.values(bySourcePageDay)) {
    for (const pages of Object.values(sources)) {
      for (const page of Object.keys(pages)) pages[page] = withRates(pages[page]);
    }
  }
  return { bySource, bySourcePage, bySourcePageDay, firstTs, lastTs };
}

async function handleGrowthGet(request, env) {
  const secret = request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET;
  if (!adminSecret) return jsonResponse({ error: 'ADMIN_SECRET not configured' }, 503);
  if (secret !== adminSecret) return jsonResponse({ error: 'unauthorized' }, 401);
  if (!env.OPS_DB) return jsonResponse({ error: 'growth_read_model_storage_not_configured', available: false }, 500);

  const url = new URL(request.url);
  const days = Math.min(Math.max(parseInt(url.searchParams.get('days')) || 14, 1), 90);
  const startDay = growthStartDay(days);
  const [rowsResult, attributionRowsResult, trustedRowsResult, initializedResult, failureMarker] = await Promise.all([
    env.OPS_DB.prepare(`
      SELECT day,event_type,page,locale,placement,country,requested_version,target_version,event_count,first_ts,last_ts
      FROM growth_daily_dims WHERE day>=? ORDER BY day,event_type,page,placement
    `).bind(startDay).all(),
    env.OPS_DB.prepare(`
      SELECT day,event_type,page,source,locale,placement,country,event_count,first_ts,last_ts
      FROM growth_attribution_daily_dims WHERE day>=? ORDER BY day,source,event_type,page,placement
    `).bind(startDay).all(),
    env.OPS_DB.prepare(`
      SELECT day,event_type,source_page AS page,locale,placement,country,'' AS requested_version,target_version,event_count,first_ts,last_ts
      FROM growth_first_party_daily_dims WHERE day>=? ORDER BY day,event_type,source_page,placement
    `).bind(startDay).all(),
    env.OPS_DB.prepare('SELECT value,updated_at FROM ops_index_meta WHERE key=?').bind(GROWTH_READ_INITIALIZED_META).first(),
    readGrowthIndexFailure(env),
  ]);
  if (!initializedResult || initializedResult.value !== '1') {
    return jsonResponse({
      error: 'growth_read_model_uninitialized',
      available: false,
      source: 'D1 growth read model',
      days,
    }, 503);
  }

  const allRows = rowsResult.results || [];
  const downloadRows = allRows.filter((row) => row.event_type === 'seo_download_click');
  const landingViewRows = allRows.filter((row) => row.event_type === 'landing_view');
  const aggregated = growthAggregateRows(downloadRows);
  const landingViews = growthAggregateRows(landingViewRows);
  const landingViewFirstTs = landingViewRows.reduce((min, row) => {
    const ts = Number(row.first_ts || 0);
    return ts > 0 && (min === 0 || ts < min) ? ts : min;
  }, 0);
  const attributionFunnel = growthAttributionFunnel(attributionRowsResult.results || []);
  const trustedRows = (trustedRowsResult.results || []).filter((row) => row.event_type === 'seo_download_click');
  const trusted = growthAggregateRows(trustedRows);
  const trustedFirstTs = trustedRows.reduce((min, row) => {
    const ts = Number(row.first_ts || 0);
    return ts > 0 && (min === 0 || ts < min) ? ts : min;
  }, 0);
  const now = Date.now();
  const ageSeconds = aggregated.lastEventTs > 0 ? Math.max(0, Math.floor((now - aggregated.lastEventTs) / 1000)) : null;
  return jsonResponse({
    available: true,
    complete: !failureMarker,
    source: 'D1 growth read model',
    raw_audit: 'R2',
    days,
    total: aggregated.total,
    byDay: aggregated.byDay,
    byPage: aggregated.byPage,
    byPageDay: aggregated.byPageDay,
    byLocale: aggregated.byLocale,
    byPlacement: aggregated.byPlacement,
    byCountry: aggregated.byCountry,
    byType: aggregated.byType,
    engines: aggregated.engines,
    landing_views: {
      definition: 'qualified first-party page view; emitted after a visible dwell threshold; no user/device identifier is stored',
      measurement_start_at: landingViewFirstTs > 0 ? new Date(landingViewFirstTs).toISOString() : null,
      total: landingViews.total,
      byDay: landingViews.byDay,
      byPage: landingViews.byPage,
      byPageDay: landingViews.byPageDay,
      byLocale: landingViews.byLocale,
      byCountry: landingViews.byCountry,
      byPlacement: landingViews.byPlacement,
      acquisition_sources: {
        definition: 'privacy-safe category derived in the browser from document.referrer host; no full referrer URL, query or visitor identifier is sent',
        bySource: Object.fromEntries(Object.entries(landingViews.byPlacement || {})
          .filter(([key]) => key.startsWith('qualified_view:'))
          .map(([key, value]) => [key.slice('qualified_view:'.length), value])),
        bySourceDay: Object.fromEntries(Object.entries(landingViews.byPlacementDay || {}).map(([day, placements]) => [
          day,
          Object.fromEntries(Object.entries(placements || {})
            .filter(([key]) => key.startsWith('qualified_view:'))
            .map(([key, value]) => [key.slice('qualified_view:'.length), value])),
        ])),
      },
      freshness: {
        last_event_at: landingViews.lastEventTs > 0 ? new Date(landingViews.lastEventTs).toISOString() : null,
      },
    },
    attribution_funnel: {
      definition: 'prospective source × landing page × download-click aggregate; source is a finite privacy-safe category and never contains raw referrer, UTM, query, user or device identifiers',
      total_scope: 'landing_view + seo_download_click only; conversion_pct is directional and only computed when the same source/page has a landing-view denominator',
      measurement_start_at: attributionFunnel.firstTs > 0 ? new Date(attributionFunnel.firstTs).toISOString() : null,
      bySource: attributionFunnel.bySource,
      bySourcePage: attributionFunnel.bySourcePage,
      bySourcePageDay: attributionFunnel.bySourcePageDay,
      freshness: {
        last_event_at: attributionFunnel.lastTs > 0 ? new Date(attributionFunnel.lastTs).toISOString() : null,
      },
    },
    trusted_first_party: {
      definition: 'lower bound: browser Referer host is magnetgoogo.com; direct/unverified traffic excluded',
      measurement_start_at: trustedFirstTs > 0 ? new Date(trustedFirstTs).toISOString() : null,
      total: trusted.total,
      byDay: trusted.byDay,
      byPage: trusted.byPage,
      byPageDay: trusted.byPageDay,
      byLocale: trusted.byLocale,
      byPlacement: trusted.byPlacement,
      byCountry: trusted.byCountry,
      byType: trusted.byType,
      engines: trusted.engines,
      freshness: {
        last_event_at: trusted.lastEventTs > 0 ? new Date(trusted.lastEventTs).toISOString() : null,
      },
    },
    freshness: {
      last_event_at: aggregated.lastEventTs > 0 ? new Date(aggregated.lastEventTs).toISOString() : null,
      age_seconds: ageSeconds,
      read_at: new Date(now).toISOString(),
    },
    integrity: {
      initialized_at: new Date(Number(initializedResult.updated_at || 0)).toISOString(),
      unresolved_shadow_failure: failureMarker || null,
    },
  });
}

function growthUtcPrefixesForOpsDay(day) {
  const nominal = Date.parse(`${day}T00:00:00Z`);
  if (!Number.isFinite(nominal)) return [];
  const startUtc = nominal - 8 * 3600_000;
  const nextUtc = startUtc + 86400_000;
  return [startUtc, nextUtc].map((ts) => {
    const d = new Date(ts);
    return `growth-events/${d.getUTCFullYear()}/${String(d.getUTCMonth() + 1).padStart(2, '0')}/${String(d.getUTCDate()).padStart(2, '0')}/`;
  });
}

async function readGrowthRawOpsDay(env, day, maxObjects = 800) {
  const events = [];
  let seenObjects = 0;
  for (const prefix of growthUtcPrefixesForOpsDay(day)) {
    let cursor;
    do {
      const listed = await env.ANALYTICS.list({ prefix, cursor, limit: 250 });
      seenObjects += listed.objects.length;
      if (seenObjects > maxObjects) throw new Error(`growth_rebuild_day_too_large:${day}:${seenObjects}`);
      for (let i = 0; i < listed.objects.length; i += 40) {
        const chunk = listed.objects.slice(i, i + 40);
        const rows = await Promise.all(chunk.map(async (object) => {
          const stored = await env.ANALYTICS.get(object.key);
          return stored ? await stored.json() : null;
        }));
        for (const row of rows) {
          if (row?.type && opsDayKey(Number(row.ts) || 0) === day) events.push(row);
        }
      }
      cursor = listed.truncated ? listed.cursor : undefined;
    } while (cursor);
  }
  return events;
}

function normalizeGrowthEventForRebuild(event) {
  return {
    type: sanitizeGrowthToken(event?.type || '', 40),
    ts: Number(event?.ts) || 0,
    page: sanitizeGrowthToken(event?.page || '', 120),
    locale: sanitizeGrowthToken(event?.locale || '', 16),
    placement: sanitizeGrowthToken(event?.placement || '', 40),
    source: sanitizeAcquisitionSource(event?.source),
    requested_version: sanitizeGrowthToken(event?.requested_version || '', 24),
    target_version: sanitizeGrowthToken(event?.target_version || '', 24),
    country: sanitizeGrowthToken(event?.country || '', 8),
    referrer_class: sanitizeGrowthToken(event?.referrer_class || '', 32),
    referrer_path: sanitizeGrowthToken(event?.referrer_path || '', 120),
  };
}

function aggregateGrowthEventsForRebuild(events) {
  const groups = new Map();
  for (const event of events || []) {
    const payload = normalizeGrowthEventForRebuild(event);
    if (!payload.type || !payload.ts) continue;
    const key = JSON.stringify([
      opsDayKey(payload.ts), payload.type, payload.page, payload.locale, payload.placement,
      payload.country, payload.requested_version, payload.target_version,
    ]);
    const current = groups.get(key);
    if (!current) groups.set(key, { payload, count: 1, firstTs: payload.ts, lastTs: payload.ts });
    else {
      current.count += 1;
      current.firstTs = Math.min(current.firstTs, payload.ts);
      current.lastTs = Math.max(current.lastTs, payload.ts);
    }
  }
  return [...groups.values()];
}

function aggregateAttributionGrowthEventsForRebuild(events) {
  const groups = new Map();
  for (const event of events || []) {
    const payload = normalizeGrowthEventForRebuild(event);
    if (!payload.type || !payload.ts || !['landing_view', 'seo_download_click'].includes(payload.type)) continue;
    payload.source = growthAttributionSource(payload);
    const key = JSON.stringify([
      opsDayKey(payload.ts), payload.type, payload.page, payload.source, payload.locale, payload.placement, payload.country,
    ]);
    const current = groups.get(key);
    if (!current) groups.set(key, { payload, count: 1, firstTs: payload.ts, lastTs: payload.ts });
    else {
      current.count += 1;
      current.firstTs = Math.min(current.firstTs, payload.ts);
      current.lastTs = Math.max(current.lastTs, payload.ts);
    }
  }
  return [...groups.values()];
}

function aggregateFirstPartyGrowthEventsForRebuild(events) {
  const groups = new Map();
  for (const event of events || []) {
    const payload = normalizeGrowthEventForRebuild(event);
    const sourcePage = String(payload.page || payload.referrer_path || '');
    if (!payload.type || !payload.ts || payload.referrer_class !== 'first_party_prod' || !sourcePage) continue;
    const key = JSON.stringify([
      opsDayKey(payload.ts), payload.type, sourcePage, payload.locale, payload.placement,
      payload.country, payload.target_version,
    ]);
    const current = groups.get(key);
    if (!current) groups.set(key, { payload, sourcePage, count: 1, firstTs: payload.ts, lastTs: payload.ts });
    else {
      current.count += 1;
      current.firstTs = Math.min(current.firstTs, payload.ts);
      current.lastTs = Math.max(current.lastTs, payload.ts);
    }
  }
  return [...groups.values()];
}

async function rebuildGrowthDay(env, day) {
  const events = await readGrowthRawOpsDay(env, day);
  const groups = aggregateGrowthEventsForRebuild(events);
  const attributionGroups = aggregateAttributionGrowthEventsForRebuild(events);
  const trustedGroups = aggregateFirstPartyGrowthEventsForRebuild(events);
  await env.OPS_DB.batch([
    env.OPS_DB.prepare('DELETE FROM growth_daily_dims WHERE day=?').bind(day),
    env.OPS_DB.prepare('DELETE FROM growth_attribution_daily_dims WHERE day=?').bind(day),
    env.OPS_DB.prepare('DELETE FROM growth_first_party_daily_dims WHERE day=?').bind(day),
  ]);
  const statements = groups.map((group) => env.OPS_DB.prepare(`
    INSERT INTO growth_daily_dims(
      day,event_type,page,locale,placement,country,requested_version,target_version,event_count,first_ts,last_ts
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
  `).bind(
    day,
    group.payload.type,
    group.payload.page,
    group.payload.locale,
    group.payload.placement,
    group.payload.country,
    group.payload.requested_version,
    group.payload.target_version,
    group.count,
    group.firstTs,
    group.lastTs,
  ));
  statements.push(...attributionGroups.map((group) => env.OPS_DB.prepare(`
    INSERT INTO growth_attribution_daily_dims(
      day,event_type,page,source,locale,placement,country,event_count,first_ts,last_ts
    ) VALUES (?,?,?,?,?,?,?,?,?,?)
  `).bind(
    day,
    group.payload.type,
    group.payload.page,
    group.payload.source,
    group.payload.locale,
    group.payload.placement,
    group.payload.country,
    group.count,
    group.firstTs,
    group.lastTs,
  )));
  statements.push(...trustedGroups.map((group) => env.OPS_DB.prepare(`
    INSERT INTO growth_first_party_daily_dims(
      day,event_type,source_page,locale,placement,country,target_version,event_count,first_ts,last_ts
    ) VALUES (?,?,?,?,?,?,?,?,?,?)
  `).bind(
    day,
    group.payload.type,
    group.sourcePage,
    group.payload.locale,
    group.payload.placement,
    group.payload.country,
    group.payload.target_version,
    group.count,
    group.firstTs,
    group.lastTs,
  )));
  for (let i = 0; i < statements.length; i += 50) {
    await env.OPS_DB.batch(statements.slice(i, i + 50));
  }
  await growthMetaStatement(env, 'growth_read_model_last_rebuild_day', day).run();
  return {
    day,
    raw_events: events.length,
    dimensions: groups.length,
    attribution_dimensions: attributionGroups.length,
    trusted_first_party_dimensions: trustedGroups.length,
  };
}

async function handleGrowthRebuild(request, env) {
  const secret = request.headers.get('X-Admin-Secret') || '';
  const adminSecret = env.ADMIN_SECRET;
  if (!adminSecret) return jsonResponse({ error: 'ADMIN_SECRET not configured' }, 503);
  if (secret !== adminSecret) return jsonResponse({ error: 'unauthorized' }, 401);
  if (!env.ANALYTICS || !env.OPS_DB) return jsonResponse({ error: 'growth_storage_not_configured' }, 500);
  const url = new URL(request.url);
  if (url.searchParams.get('finalize') === '1') {
    const now = Date.now();
    await growthMetaStatement(env, GROWTH_READ_INITIALIZED_META, '1', now).run();
    await env.ANALYTICS.delete(GROWTH_INDEX_FAILURE_KEY);
    return jsonResponse({ ok: true, finalized: true, initialized_at: new Date(now).toISOString() });
  }
  const day = String(url.searchParams.get('day') || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return jsonResponse({ error: 'valid_day_required' }, 400);
  const rebuildTs = Date.parse(`${day}T12:00:00+08:00`);
  if (!Number.isFinite(rebuildTs) || opsDayKey(rebuildTs) !== day) return jsonResponse({ error: 'valid_day_required' }, 400);
  const currentOpsDay = opsDayKey(Date.now());
  if (day >= currentOpsDay) {
    return jsonResponse({
      error: 'current_or_future_day_rebuild_forbidden',
      day,
      current_operational_day: currentOpsDay,
      reason: 'Destructive aggregate rebuilds are restricted to completed operational days to avoid racing live growth writes.',
    }, 409);
  }
  try {
    const result = await rebuildGrowthDay(env, day);
    return jsonResponse({ ok: true, ...result });
  } catch (error) {
    await writeGrowthIndexFailure(env, { type: 'growth_rebuild', ts: rebuildTs }, error).catch((markerError) => {
      console.error('[growth-rebuild-marker]', markerError?.message || markerError);
    });
    throw error;
  }
}

function opsDeviceKey(data) {
  const schemaV = Number(data?.schema_v || 0);
  if (schemaV >= 2) return String(data?.legacy_did || data?.device_id || data?.did || '').trim();
  return String(data?.did || '').trim();
}

function opsStrongDeviceAlias(data) {
  if (Number(data?.schema_v || 0) < 2 || String(data?.device_id_kind || '').trim() !== 'android_id_hash') return null;
  const aliasKey = String(data?.legacy_did || data?.did || '').trim();
  const canonicalKey = String(data?.device_id || '').trim();
  if (!aliasKey || !canonicalKey || aliasKey === canonicalKey) return null;
  return { aliasKey, canonicalKey, kind: 'android_id_hash' };
}

function opsInstallKey(data) {
  return String(data?.install_id || data?.did || '').trim();
}

function opsEventTs(value) {
  const ts = Number(value);
  return Number.isFinite(ts) && ts > 0 ? ts : null;
}

const OPS_MIN_EPOCH_MS = Date.UTC(2000, 0, 1);
function opsInstallationTs(value, firstOpenTs) {
  const ts = opsEventTs(value);
  if (ts === null || ts < OPS_MIN_EPOCH_MS || ts > firstOpenTs + 5 * 60_000) return null;
  return ts;
}

async function opsExecuteStatementGroups(env, groups, maxStatements = 60) {
  let batch = [];
  for (const group of groups) {
    if (batch.length > 0 && batch.length + group.length > maxStatements) {
      await env.OPS_DB.batch(batch);
      batch = [];
    }
    batch.push(...group);
  }
  if (batch.length > 0) await env.OPS_DB.batch(batch);
}

const OPS_SHADOW_FAILURE_KEY = 'ops-index-health/unresolved.json';

function opsRetryJitter(maxMs = 100) {
  const values = new Uint32Array(1);
  crypto.getRandomValues(values);
  return values[0] % (maxMs + 1);
}

async function retryOpsIndex(env, entry, maxAttempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await indexAnalyticsEntryToOps(env, entry);
      return;
    } catch (error) {
      lastError = error;
      if (attempt >= maxAttempts) break;
      const delayMs = 100 * (2 ** (attempt - 1)) + opsRetryJitter(100);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw lastError || new Error('analytics ops shadow indexing failed');
}

async function recordOpsShadowFailure(env, entry, error, maxAttempts = 3) {
  if (!env.ANALYTICS) return;
  const failedAt = new Date().toISOString();
  const marker = {
    failedAt,
    batchReceivedAt: String(entry?.receivedAt || failedAt),
    r2Key: String(entry?.id || ''),
    error: String(error?.message || error || 'unknown').slice(0, 240),
  };
  let lastError;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await env.ANALYTICS.put(OPS_SHADOW_FAILURE_KEY, JSON.stringify(marker), {
        httpMetadata: { contentType: 'application/json' },
        customMetadata: { type: 'ops_shadow_failure' },
      });
      return;
    } catch (markerError) {
      lastError = markerError;
      if (attempt >= maxAttempts) break;
      const delayMs = 100 * (2 ** (attempt - 1)) + opsRetryJitter(100);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw lastError || new Error('failed to persist D1 shadow health marker');
}

function opsShadowFailureClass(errorText) {
  const message = String(errorText || '');
  if (/daily row write limit/i.test(message)) return 'd1_daily_row_write_quota';
  if (/daily row read limit/i.test(message)) return 'd1_daily_row_read_quota';
  return 'd1_shadow_index_failure';
}

async function readOpsShadowIntegrity(env, backfill) {
  if (!env.ANALYTICS) {
    return { shadow_healthy: false, status: 'unknown', reason: 'R2 raw audit binding unavailable' };
  }
  try {
    const stored = await env.ANALYTICS.get(OPS_SHADOW_FAILURE_KEY);
    if (!stored) return { shadow_healthy: true, status: 'healthy', reason: '' };
    const marker = await stored.json();
    const failureMeta = {
      last_failure_at: marker?.failedAt || null,
      last_failure_received_at: marker?.batchReceivedAt || null,
      failure_class: opsShadowFailureClass(marker?.error),
    };
    const failureReceivedAt = String(marker?.batchReceivedAt || marker?.failedAt || '');
    const failedMs = Date.parse(failureReceivedAt);
    const backfillMs = Date.parse(String(backfill?.sourceCachedAt || ''));
    if (Number.isFinite(failedMs) && Number.isFinite(backfillMs) && failedMs <= backfillMs) {
      return { shadow_healthy: true, status: 'repaired_by_backfill', reason: '', ...failureMeta };
    }
    if (env.OPS_DB && Number.isFinite(failedMs)) {
      try {
        const repairMetaRow = await env.OPS_DB.prepare(
          "SELECT value,updated_at FROM ops_index_meta WHERE key='shadow_repair_complete' LIMIT 1"
        ).first();
        let repairMeta = null;
        try {
          if (repairMetaRow?.value) repairMeta = JSON.parse(repairMetaRow.value);
        } catch { /* malformed incremental repair metadata stays fail-closed */ }
        const repairedDays = Array.isArray(repairMeta?.repairedReceiveDays) ? repairMeta.repairedReceiveDays : [];
        const failureDay = failureReceivedAt.slice(0, 10);
        const repairMatchesFailure = repairMeta?.status === 'complete'
          && repairMeta?.r2CheckpointVerified === true
          && String(repairMeta?.failureReceivedAt || '') === failureReceivedAt
          && repairedDays.includes(failureDay);
        if (repairMatchesFailure) {
          return {
            shadow_healthy: true,
            status: 'repaired_by_incremental_checkpoint',
            reason: '',
            repaired_receive_days: repairedDays,
            ...failureMeta,
          };
        }
      } catch { /* D1 may still be quota-blocked; keep fail-closed */ }
    }
    return {
      shadow_healthy: false,
      status: 'unresolved_shadow_failure',
      reason: 'D1 shadow has an R2-backed indexing failure newer than the verified backfill; values are observational until rebuilt',
      ...failureMeta,
    };
  } catch (error) {
    return {
      shadow_healthy: false,
      status: 'integrity_check_failed',
      reason: `Unable to verify D1 shadow against R2 health marker: ${String(error?.message || error).slice(0, 160)}`,
    };
  }
}

async function indexAnalyticsEntryToOps(env, entry) {
  if (!env.OPS_DB || !entry || !Array.isArray(entry.events) || entry.events.length === 0) return;
  const deviceKey = opsDeviceKey(entry);
  if (!deviceKey) return;
  const appV = String(entry.app_v || '');
  const versionCode = String(entry.version_code || '');
  const country = String(entry.country || '');
  const installKey = opsInstallKey(entry);
  const receivedParsed = Date.parse(String(entry.receivedAt || ''));
  const lastSeenTs = Number.isFinite(receivedParsed) && receivedParsed > 0 ? receivedParsed : Date.now();
  const lastSeenDay = opsDayKey(lastSeenTs);
  const dayFlags = new Map();
  const sessions = new Map();
  const installs = new Map();
  const searches = new Map();

  for (const ev of entry.events) {
    const ts = opsEventTs(ev?.ts);
    if (!ts) continue;
    const day = opsDayKey(ts);
    const flags = dayFlags.get(day) || { day, firstTs: ts, searched: 0, gotResult: 0, action: 0 };
    flags.firstTs = Math.min(flags.firstTs, ts);
    if (ev.e === 'search_submitted') flags.searched = 1;
    if (ev.e === 'search_completed' && Math.max(0, Number(ev.result_count || 0)) > 0) flags.gotResult = 1;
    if (ev.e === 'open_magnet' || ev.e === 'copy_magnet') flags.action = 1;
    dayFlags.set(day, flags);

    const sessionId = String(ev?.session_id || entry.session_id || '').trim();
    if (sessionId) {
      const sessionKey = `${day}\u0000${sessionId}`;
      const existingSession = sessions.get(sessionKey);
      if (!existingSession || ts < existingSession.firstTs) sessions.set(sessionKey, { day, sessionId, firstTs: ts });
    }

    if (ev.e === 'first_open' && installKey) {
      const installationTs = opsInstallationTs(ev.installation_time, ts);
      if (installationTs !== null) {
        const installDay = opsDayKey(installationTs);
        const existingInstall = installs.get(installKey);
        if (!existingInstall || installationTs < existingInstall.installationTs) {
          installs.set(installKey, { installDay, installKey, installationTs, firstOpenTs: ts });
        }
      }
    }

    const searchId = String(ev?.search_id || '').trim();
    if (searchId) {
      const s = searches.get(searchId) || {
        searchId, deviceKey, submittedDay: null, submittedTs: null,
        completedDay: null, completedTs: null, resultCount: null, ttfrMs: null, action: 0,
      };
      if (ev.e === 'search_submitted' && (s.submittedTs === null || ts < s.submittedTs)) {
        s.submittedTs = ts;
        s.submittedDay = day;
      }
      if (ev.e === 'search_completed' && (s.completedTs === null || ts >= s.completedTs)) {
        s.completedTs = ts;
        s.completedDay = day;
        s.resultCount = Math.max(0, Number(ev.result_count || 0));
        const ttfr = Number(ev.ttfr_ms);
        s.ttfrMs = Number.isFinite(ttfr) && ttfr >= 0 ? Math.round(ttfr) : null;
      }
      if (ev.e === 'open_magnet' || ev.e === 'copy_magnet') s.action = 1;
      searches.set(searchId, s);
    }
  }

  const groups = [];
  const strongAlias = opsStrongDeviceAlias(entry);
  if (strongAlias) {
    groups.push([
      env.OPS_DB.prepare(
        'INSERT INTO ops_device_aliases(alias_key,canonical_key,kind,last_seen_ts,conflict) VALUES (?,?,?,?,0) '
        + 'ON CONFLICT(alias_key) DO UPDATE SET '
        + 'last_seen_ts=MAX(ops_device_aliases.last_seen_ts,excluded.last_seen_ts),'
        + 'conflict=MAX(ops_device_aliases.conflict,CASE WHEN ops_device_aliases.canonical_key<>excluded.canonical_key THEN 1 ELSE 0 END),'
        + "kind=CASE WHEN ops_device_aliases.kind='' THEN excluded.kind ELSE ops_device_aliases.kind END "
        + "WHERE ops_device_aliases.canonical_key<>excluded.canonical_key OR (ops_device_aliases.kind='' AND excluded.kind<>'')"
      ).bind(strongAlias.aliasKey, strongAlias.canonicalKey, strongAlias.kind, lastSeenTs),
    ]);
  }
  const latestDeviceUpsertSql = 'INSERT INTO ops_device_latest(device_key,last_seen_ts,last_seen_day,app_v,version_code,country) VALUES (?,?,?,?,?,?) '
    + 'ON CONFLICT(device_key) DO UPDATE SET '
    + 'last_seen_ts=excluded.last_seen_ts,last_seen_day=excluded.last_seen_day,'
    + "app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_device_latest.app_v END,"
    + "version_code=CASE WHEN excluded.version_code<>'' THEN excluded.version_code ELSE ops_device_latest.version_code END,"
    + "country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_device_latest.country END "
    + 'WHERE excluded.last_seen_day>ops_device_latest.last_seen_day '
    + "OR (excluded.last_seen_day=ops_device_latest.last_seen_day AND excluded.last_seen_ts>ops_device_latest.last_seen_ts AND ((excluded.app_v<>'' AND excluded.app_v<>ops_device_latest.app_v) OR (excluded.version_code<>'' AND excluded.version_code<>ops_device_latest.version_code) OR (excluded.country<>'' AND excluded.country<>ops_device_latest.country)))";
  groups.push([
    env.OPS_DB.prepare(latestDeviceUpsertSql).bind(deviceKey, lastSeenTs, lastSeenDay, appV, versionCode, country),
  ]);

  const deviceUpsertSql = 'INSERT INTO ops_device_days(day,device_key,first_event_ts,app_v,country,searched,got_result,action) VALUES (?,?,?,?,?,?,?,?) '
    + 'ON CONFLICT(day,device_key) DO UPDATE SET first_event_ts=MIN(ops_device_days.first_event_ts,excluded.first_event_ts),'
    + "app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_device_days.app_v END,"
    + "country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_device_days.country END,"
    + 'searched=MAX(ops_device_days.searched,excluded.searched),got_result=MAX(ops_device_days.got_result,excluded.got_result),action=MAX(ops_device_days.action,excluded.action) '
    + 'WHERE excluded.first_event_ts<ops_device_days.first_event_ts '
    + "OR (excluded.app_v<>'' AND excluded.app_v<>ops_device_days.app_v) OR (excluded.country<>'' AND excluded.country<>ops_device_days.country) "
    + 'OR excluded.searched>ops_device_days.searched OR excluded.got_result>ops_device_days.got_result OR excluded.action>ops_device_days.action';
  for (const row of dayFlags.values()) {
    groups.push([
      env.OPS_DB.prepare(deviceUpsertSql).bind(row.day, deviceKey, row.firstTs, appV, country, row.searched, row.gotResult, row.action),
    ]);
  }

  for (const row of sessions.values()) {
    groups.push([
      env.OPS_DB.prepare('INSERT OR IGNORE INTO ops_session_days(day,session_id,device_key,first_event_ts,app_v,country) VALUES (?,?,?,?,?,?)')
        .bind(row.day, row.sessionId, deviceKey, row.firstTs, appV, country),
    ]);
  }

  const installUpsertSql = 'INSERT INTO ops_install_days(install_day,install_key,installation_ts,first_open_ts,app_v,country) VALUES (?,?,?,?,?,?) '
    + 'ON CONFLICT(install_key) DO UPDATE SET '
    + 'install_day=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts THEN excluded.install_day ELSE ops_install_days.install_day END,'
    + 'installation_ts=MIN(ops_install_days.installation_ts,excluded.installation_ts),'
    + 'first_open_ts=MIN(ops_install_days.first_open_ts,excluded.first_open_ts),'
    + "app_v=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts AND excluded.app_v<>'' THEN excluded.app_v ELSE ops_install_days.app_v END,"
    + "country=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts AND excluded.country<>'' THEN excluded.country ELSE ops_install_days.country END";
  for (const row of installs.values()) {
    groups.push([
      env.OPS_DB.prepare(installUpsertSql)
        .bind(row.installDay, row.installKey, row.installationTs, row.firstOpenTs, appV, country),
    ]);
  }

  const searchUpsertSql = 'INSERT INTO ops_searches(search_id,device_key,submitted_day,submitted_ts,completed_day,completed_ts,result_count,ttfr_ms,action,app_v,country) VALUES (?,?,?,?,?,?,?,?,?,?,?) '
    + 'ON CONFLICT(search_id) DO UPDATE SET '
    + "device_key=CASE WHEN excluded.device_key<>'' THEN excluded.device_key ELSE ops_searches.device_key END,"
    + 'submitted_day=CASE WHEN ops_searches.submitted_ts IS NULL OR (excluded.submitted_ts IS NOT NULL AND excluded.submitted_ts<ops_searches.submitted_ts) THEN excluded.submitted_day ELSE ops_searches.submitted_day END,'
    + 'submitted_ts=CASE WHEN ops_searches.submitted_ts IS NULL OR (excluded.submitted_ts IS NOT NULL AND excluded.submitted_ts<ops_searches.submitted_ts) THEN excluded.submitted_ts ELSE ops_searches.submitted_ts END,'
    + 'completed_day=CASE WHEN ops_searches.completed_ts IS NULL OR (excluded.completed_ts IS NOT NULL AND excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.completed_day ELSE ops_searches.completed_day END,'
    + 'completed_ts=CASE WHEN ops_searches.completed_ts IS NULL OR (excluded.completed_ts IS NOT NULL AND excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.completed_ts ELSE ops_searches.completed_ts END,'
    + 'result_count=CASE WHEN excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.result_count ELSE ops_searches.result_count END,'
    + 'ttfr_ms=CASE WHEN excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.ttfr_ms ELSE ops_searches.ttfr_ms END,'
    + "action=MAX(ops_searches.action,excluded.action),app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_searches.app_v END,"
    + "country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_searches.country END "
    + "WHERE (excluded.device_key<>'' AND excluded.device_key<>ops_searches.device_key) "
    + 'OR (excluded.submitted_ts IS NOT NULL AND (ops_searches.submitted_ts IS NULL OR excluded.submitted_ts<ops_searches.submitted_ts)) '
    + 'OR (excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>ops_searches.completed_ts '
    + 'OR (excluded.completed_ts=ops_searches.completed_ts AND (COALESCE(excluded.result_count,-1)<>COALESCE(ops_searches.result_count,-1) OR COALESCE(excluded.ttfr_ms,-1)<>COALESCE(ops_searches.ttfr_ms,-1))))) '
    + 'OR excluded.action>ops_searches.action '
    + "OR (excluded.app_v<>'' AND excluded.app_v<>ops_searches.app_v) "
    + "OR (excluded.country<>'' AND excluded.country<>ops_searches.country)";
  for (const row of searches.values()) {
    const group = [];
    group.push(env.OPS_DB.prepare(searchUpsertSql).bind(
      row.searchId, row.deviceKey, row.submittedDay, row.submittedTs, row.completedDay, row.completedTs,
      row.resultCount, row.ttfrMs, row.action, appV, country,
    ));
    groups.push(group);
  }

  if (groups.length > 0) await opsExecuteStatementGroups(env, groups);
}

const OPS_DAILY_SNAPSHOT_TTL_SECONDS = 30 * 60;

function opsDailySnapshotCacheRequest(days) {
  return new Request(`https://ops-daily-cache.internal/v2?days=${days}`);
}

async function readOpsDailySnapshotCache(days) {
  try {
    const cached = await caches.default.match(opsDailySnapshotCacheRequest(days));
    if (!cached) return null;
    const payload = await cached.json();
    if (!payload || payload.schema !== 'analytics-ops-d1/2' || !Array.isArray(payload.rows)) return null;
    return payload;
  } catch {
    return null;
  }
}

async function writeOpsDailySnapshotCache(days, payload) {
  try {
    const body = JSON.stringify(payload);
    await caches.default.put(opsDailySnapshotCacheRequest(days), new Response(body, {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': `public, max-age=${OPS_DAILY_SNAPSHOT_TTL_SECONDS}`,
      },
    }));
  } catch { /* local tests / cache unavailable */ }
}

async function handleEventsOpsDaily(url, env) {
  if (!env.OPS_DB) return jsonResponse({ error: 'ops_index_not_configured' }, 503);
  const days = Math.min(Math.max(parseInt(url.searchParams.get('days')) || 31, 1), 90);
  const now = Date.now();
  const minDay = opsDayKey(now - (days - 1) * 86400_000);
  const cachedSnapshot = await readOpsDailySnapshotCache(days);
  if (cachedSnapshot) {
    const currentIntegrity = await readOpsShadowIntegrity(env, cachedSnapshot.backfill);
    let repairedBackfillRequiresRefresh = currentIntegrity.status === 'repaired_by_incremental_checkpoint'
      && cachedSnapshot.integrity?.status !== 'repaired_by_incremental_checkpoint';
    if (currentIntegrity.shadow_healthy !== true && currentIntegrity.status === 'unresolved_shadow_failure') {
      try {
        const latestMeta = await env.OPS_DB.prepare(
          "SELECT value,updated_at FROM ops_index_meta WHERE key='backfill_complete' LIMIT 1"
        ).first();
        let latestBackfill = null;
        try {
          if (latestMeta?.value) latestBackfill = JSON.parse(latestMeta.value);
        } catch { /* malformed metadata stays fail-closed */ }
        const latestBackfillComplete = latestBackfill?.status === 'complete'
          && latestBackfill?.inventoryVerified === true
          && Number(latestBackfill?.inventoryDays) === 31;
        const cachedBackfillMs = Date.parse(String(cachedSnapshot.backfill?.sourceCachedAt || ''));
        const latestBackfillMs = Date.parse(String(latestBackfill?.sourceCachedAt || ''));
        if (latestBackfillComplete && Number.isFinite(latestBackfillMs)
          && (!Number.isFinite(cachedBackfillMs) || latestBackfillMs > cachedBackfillMs)) {
          const latestIntegrity = await readOpsShadowIntegrity(env, latestBackfill);
          repairedBackfillRequiresRefresh = latestIntegrity.shadow_healthy === true;
        }
      } catch { /* D1 may still be quota-blocked; keep serving cached fail-closed data */ }
    }
    if (!repairedBackfillRequiresRefresh) {
      const cachedAtMs = Date.parse(String(cachedSnapshot.snapshot_cache?.cached_at || ''));
      const legacyDiagnostic = cachedSnapshot.integrity?.legacy_counter_diagnostic || {
        authority: false,
        drifted_days: 0,
        max_abs_active_device_drift: 0,
      };
      return jsonResponse({
        ...cachedSnapshot,
        operational_verified: cachedSnapshot.backfill_complete === true && currentIntegrity.shadow_healthy === true,
        integrity: {
          ...cachedSnapshot.integrity,
          ...currentIntegrity,
          exact_state_authority: true,
          legacy_counter_diagnostic: legacyDiagnostic,
        },
        snapshot_cache: {
          hit: true,
          ttl_seconds: OPS_DAILY_SNAPSHOT_TTL_SECONDS,
          cached_at: cachedSnapshot.snapshot_cache?.cached_at || null,
          age_seconds: Number.isFinite(cachedAtMs) ? Math.max(0, Math.floor((now - cachedAtMs) / 1000)) : null,
        },
      });
    }
  }
  const [legacyCounterResult, deviceDailyResult, installDailyResult, sessionDailyResult, searchDailyResult, metaResult, versionResult, growthResult, searchFunnelResult, newUserQualityResult] = await env.OPS_DB.batch([
    // ops_daily is retained only as a legacy diagnostic counter. It is never the
    // DAU authority because incremental counters can drift under retries/repairs.
    env.OPS_DB.prepare(
      'SELECT day,active_devices,search_devices,result_devices,action_devices,physical_installs,sessions,searches_submitted,searches_completed,searches_with_results,zero_result_searches FROM ops_daily WHERE day>=? ORDER BY day'
    ).bind(minDay),
    env.OPS_DB.prepare(
      'WITH canonical AS ('
      + 'SELECT d.day,COALESCE(a.canonical_key,d.device_key) AS device_key,'
      + 'MAX(d.searched) AS searched,MAX(d.got_result) AS got_result,MAX(d.action) AS action '
      + 'FROM ops_device_days d LEFT JOIN ops_device_aliases a ON a.alias_key=d.device_key AND a.conflict=0 '
      + 'WHERE d.day>=? GROUP BY d.day,COALESCE(a.canonical_key,d.device_key)) '
      + 'SELECT day,COUNT(*) AS active_devices,SUM(searched) AS search_devices,SUM(got_result) AS result_devices,SUM(action) AS action_devices '
      + 'FROM canonical GROUP BY day ORDER BY day'
    ).bind(minDay),
    env.OPS_DB.prepare(
      'SELECT install_day AS day,COUNT(*) AS physical_installs FROM ops_install_days WHERE install_day>=? GROUP BY install_day ORDER BY install_day'
    ).bind(minDay),
    env.OPS_DB.prepare(
      'SELECT day,COUNT(*) AS sessions FROM ops_session_days WHERE day>=? GROUP BY day ORDER BY day'
    ).bind(minDay),
    env.OPS_DB.prepare(
      'SELECT day,SUM(searches_submitted) AS searches_submitted,SUM(searches_completed) AS searches_completed,'
      + 'SUM(searches_with_results) AS searches_with_results,SUM(zero_result_searches) AS zero_result_searches FROM ('
      + 'SELECT submitted_day AS day,1 AS searches_submitted,0 AS searches_completed,0 AS searches_with_results,0 AS zero_result_searches '
      + 'FROM ops_searches WHERE submitted_day>=? AND submitted_ts IS NOT NULL UNION ALL '
      + 'SELECT completed_day AS day,0,1,CASE WHEN COALESCE(result_count,0)>0 THEN 1 ELSE 0 END,CASE WHEN COALESCE(result_count,0)=0 THEN 1 ELSE 0 END '
      + 'FROM ops_searches WHERE completed_day>=? AND completed_ts IS NOT NULL) x GROUP BY day ORDER BY day'
    ).bind(minDay, minDay),
    env.OPS_DB.prepare("SELECT value,updated_at FROM ops_index_meta WHERE key='backfill_complete' LIMIT 1"),
    env.OPS_DB.prepare(
      'WITH ranked AS ('
      + 'SELECT COALESCE(a.canonical_key,l.device_key) AS canonical_key,l.app_v,l.version_code,l.last_seen_ts,'
      + 'ROW_NUMBER() OVER (PARTITION BY COALESCE(a.canonical_key,l.device_key) ORDER BY l.last_seen_ts DESC,l.device_key) AS rn '
      + 'FROM ops_device_latest l LEFT JOIN ops_device_aliases a ON a.alias_key=l.device_key AND a.conflict=0 WHERE l.last_seen_day>=?) '
      + 'SELECT app_v,version_code,COUNT(*) AS devices FROM ranked WHERE rn=1 GROUP BY app_v,version_code ORDER BY devices DESC,app_v,version_code'
    ).bind(minDay),
    env.OPS_DB.prepare(
      'WITH firsts AS ('
      + 'SELECT COALESCE(a.canonical_key,d.device_key) AS device_key,MIN(d.day) AS first_day '
      + 'FROM ops_device_days d LEFT JOIN ops_device_aliases a ON a.alias_key=d.device_key AND a.conflict=0 '
      + 'GROUP BY COALESCE(a.canonical_key,d.device_key)), '
      + 'windowed AS ('
      + 'SELECT d.day,COALESCE(a.canonical_key,d.device_key) AS device_key,'
      + "CASE WHEN MAX(CASE WHEN d.country='CN' THEN 1 ELSE 0 END)=1 THEN 'CN' ELSE MAX(CASE WHEN d.country<>'' THEN d.country ELSE '' END) END AS country,"
      + 'MAX(d.searched) AS searched,MAX(d.got_result) AS got_result,MAX(d.action) AS action '
      + 'FROM ops_device_days d LEFT JOIN ops_device_aliases a ON a.alias_key=d.device_key AND a.conflict=0 '
      + "WHERE d.day>=date(?,'-7 day') GROUP BY d.day,COALESCE(a.canonical_key,d.device_key)) "
      + "SELECT d.day,CASE WHEN d.country='CN' THEN 'cn' WHEN d.country='' THEN 'unknown' ELSE 'intl' END AS segment,"
      + 'COUNT(*) AS active_devices,SUM(d.searched) AS search_devices,SUM(d.got_result) AS result_devices,SUM(d.action) AS satisfied_devices,'
      + 'SUM(CASE WHEN f.first_day=d.day THEN 1 ELSE 0 END) AS first_observed_devices,'
      + 'SUM(CASE WHEN d.searched=1 AND f.first_day=d.day THEN 1 ELSE 0 END) AS first_observed_search_devices,'
      + 'SUM(CASE WHEN d.action=1 AND f.first_day=d.day THEN 1 ELSE 0 END) AS new_dssu,'
      + 'SUM(CASE WHEN d.action=1 AND COALESCE(p.action,0)=1 THEN 1 ELSE 0 END) AS d7_returning_dssu '
      + 'FROM windowed d JOIN firsts f ON f.device_key=d.device_key '
      + "LEFT JOIN windowed p ON p.device_key=d.device_key AND p.day=date(d.day,'-7 day') "
      + 'WHERE d.day>=? GROUP BY d.day,segment ORDER BY d.day,segment'
    ).bind(minDay, minDay),
    env.OPS_DB.prepare(
      'SELECT submitted_day AS day,COUNT(*) AS submitted_searches,'
      + 'SUM(CASE WHEN completed_ts IS NOT NULL THEN 1 ELSE 0 END) AS completed_searches,'
      + 'SUM(CASE WHEN action=1 THEN 1 ELSE 0 END) AS satisfied_searches,'
      + 'SUM(CASE WHEN action=1 AND completed_ts IS NULL THEN 1 ELSE 0 END) AS satisfied_without_completion,'
      + 'SUM(CASE WHEN action=1 AND completed_ts IS NOT NULL THEN 1 ELSE 0 END) AS satisfied_with_completion '
      + 'FROM ops_searches WHERE submitted_day>=? GROUP BY submitted_day ORDER BY submitted_day'
    ).bind(minDay),
    env.OPS_DB.prepare(
      'WITH firsts AS ('
      + 'SELECT COALESCE(a.canonical_key,d.device_key) AS device_key,MIN(d.day) AS first_day '
      + 'FROM ops_device_days d LEFT JOIN ops_device_aliases a ON a.alias_key=d.device_key AND a.conflict=0 '
      + 'GROUP BY COALESCE(a.canonical_key,d.device_key)), '
      + 'windowed AS ('
      + 'SELECT d.day,COALESCE(a.canonical_key,d.device_key) AS device_key,MAX(d.action) AS action '
      + 'FROM ops_device_days d LEFT JOIN ops_device_aliases a ON a.alias_key=d.device_key AND a.conflict=0 '
      + 'WHERE d.day>=? GROUP BY d.day,COALESCE(a.canonical_key,d.device_key)), '
      + 'new_dssu AS ('
      + 'SELECT f.first_day,w.device_key FROM firsts f JOIN windowed w ON w.device_key=f.device_key AND w.day=f.first_day '
      + 'WHERE f.first_day>=? AND w.action=1), '
      + 'reuse AS ('
      + 'SELECT n.first_day,n.device_key,MAX(CASE WHEN COALESCE(r.action,0)=1 THEN 1 ELSE 0 END) AS reused '
      + 'FROM new_dssu n LEFT JOIN windowed r ON r.device_key=n.device_key '
      + "AND r.day>n.first_day AND r.day<=date(n.first_day,'+7 day') GROUP BY n.first_day,n.device_key) "
      + 'SELECT first_day,COUNT(*) AS new_dssu,SUM(reused) AS reused_1_7d '
      + 'FROM reuse GROUP BY first_day ORDER BY first_day'
    ).bind(minDay, minDay),
  ]);
  let backfill = null;
  try {
    const raw = metaResult?.results?.[0]?.value;
    if (raw) backfill = JSON.parse(raw);
  } catch { /* malformed metadata stays fail-closed */ }
  const backfillComplete = backfill?.status === 'complete'
    && backfill?.inventoryVerified === true
    && Number(backfill?.inventoryDays) === 31;
  const shadowIntegrity = await readOpsShadowIntegrity(env, backfill);
  const dailyByDay = new Map();
  const rowForDay = (day) => {
    const key = String(day || '');
    if (!dailyByDay.has(key)) {
      dailyByDay.set(key, {
        day: key,
        active_devices: 0,
        search_devices: 0,
        result_devices: 0,
        action_devices: 0,
        physical_installs: 0,
        sessions: 0,
        searches_submitted: 0,
        searches_completed: 0,
        searches_with_results: 0,
        zero_result_searches: 0,
      });
    }
    return dailyByDay.get(key);
  };
  for (const row of deviceDailyResult?.results || []) Object.assign(rowForDay(row.day), {
    active_devices: Math.max(0, Number(row?.active_devices || 0)),
    search_devices: Math.max(0, Number(row?.search_devices || 0)),
    result_devices: Math.max(0, Number(row?.result_devices || 0)),
    action_devices: Math.max(0, Number(row?.action_devices || 0)),
  });
  for (const row of installDailyResult?.results || []) rowForDay(row.day).physical_installs = Math.max(0, Number(row?.physical_installs || 0));
  for (const row of sessionDailyResult?.results || []) rowForDay(row.day).sessions = Math.max(0, Number(row?.sessions || 0));
  for (const row of searchDailyResult?.results || []) Object.assign(rowForDay(row.day), {
    searches_submitted: Math.max(0, Number(row?.searches_submitted || 0)),
    searches_completed: Math.max(0, Number(row?.searches_completed || 0)),
    searches_with_results: Math.max(0, Number(row?.searches_with_results || 0)),
    zero_result_searches: Math.max(0, Number(row?.zero_result_searches || 0)),
  });
  const dailyRows = [...dailyByDay.values()].filter((row) => row.day).sort((a, b) => a.day.localeCompare(b.day));
  const legacyCounterByDay = new Map((legacyCounterResult?.results || []).map((row) => [String(row?.day || ''), row]));
  let driftedDays = 0;
  let maxActiveDeviceDrift = 0;
  for (const row of dailyRows) {
    const legacy = legacyCounterByDay.get(row.day);
    if (!legacy) continue;
    const drift = Math.abs(Number(legacy.active_devices || 0) - row.active_devices);
    maxActiveDeviceDrift = Math.max(maxActiveDeviceDrift, drift);
    if (drift > 0
      || Number(legacy.search_devices || 0) !== row.search_devices
      || Number(legacy.result_devices || 0) !== row.result_devices
      || Number(legacy.action_devices || 0) !== row.action_devices
      || Number(legacy.physical_installs || 0) !== row.physical_installs
      || Number(legacy.sessions || 0) !== row.sessions
      || Number(legacy.searches_submitted || 0) !== row.searches_submitted
      || Number(legacy.searches_completed || 0) !== row.searches_completed) driftedDays += 1;
  }
  const integrity = {
    ...shadowIntegrity,
    exact_state_authority: true,
    identity_basis: 'canonical device identity: strong android_id_hash alias when provable, otherwise legacy observed identity',
    legacy_counter_diagnostic: {
      authority: false,
      drifted_days: driftedDays,
      max_abs_active_device_drift: maxActiveDeviceDrift,
    },
  };
  const versionRows = (versionResult?.results || []).map((row) => ({
    app_v: String(row?.app_v || 'unknown'),
    version_code: String(row?.version_code || ''),
    devices: Math.max(0, Number(row?.devices || 0)),
  }));
  const growthRows = (growthResult?.results || []).map((row) => ({
    day: String(row?.day || ''),
    segment: String(row?.segment || 'unknown'),
    active_devices: Math.max(0, Number(row?.active_devices || 0)),
    search_devices: Math.max(0, Number(row?.search_devices || 0)),
    result_devices: Math.max(0, Number(row?.result_devices || 0)),
    satisfied_devices: Math.max(0, Number(row?.satisfied_devices || 0)),
    first_observed_devices: Math.max(0, Number(row?.first_observed_devices || 0)),
    first_observed_search_devices: Math.max(0, Number(row?.first_observed_search_devices || 0)),
    new_dssu: Math.max(0, Number(row?.new_dssu || 0)),
    d7_returning_dssu: Math.max(0, Number(row?.d7_returning_dssu || 0)),
  }));
  const searchFunnelRows = (searchFunnelResult?.results || []).map((row) => ({
    day: String(row?.day || ''),
    submitted_searches: Math.max(0, Number(row?.submitted_searches || 0)),
    completed_searches: Math.max(0, Number(row?.completed_searches || 0)),
    satisfied_searches: Math.max(0, Number(row?.satisfied_searches || 0)),
    satisfied_without_completion: Math.max(0, Number(row?.satisfied_without_completion || 0)),
    satisfied_with_completion: Math.max(0, Number(row?.satisfied_with_completion || 0)),
  }));
  const maturedThrough = opsDayKey(now - 7 * 86400_000);
  const newUserQualityRows = (newUserQualityResult?.results || []).map((row) => {
    const firstDay = String(row?.first_day || '');
    const newDssu = Math.max(0, Number(row?.new_dssu || 0));
    const reused = Math.max(0, Number(row?.reused_1_7d || 0));
    return {
      first_day: firstDay,
      new_dssu: newDssu,
      reused_1_7d: reused,
      reuse_1_7d_pct: newDssu > 0 ? Math.round((reused / newDssu) * 1000) / 10 : null,
      matured: Boolean(firstDay && firstDay <= maturedThrough),
    };
  });
  const payload = {
    mode: 'ops_daily',
    schema: 'analytics-ops-d1/2',
    read_model: 'D1 exact operational index',
    identity_model: 'canonical-device-v2',
    raw_audit: 'R2',
    days,
    complete: true,
    backfill_complete: backfillComplete,
    operational_verified: backfillComplete && integrity.shadow_healthy === true,
    integrity,
    backfill,
    version_distribution: {
      basis: 'latest observed app version per active device',
      window_days: days,
      total_devices: versionRows.reduce((sum, row) => sum + row.devices, 0),
      rows: versionRows,
    },
    north_star: {
      definition: 'DSSU = unique device with copy_magnet/open_magnet on the operational day',
      new_definition: 'New DSSU = first-observed device that also performs a Magnet Action that day',
      d7_definition: 'D7 Returning DSSU = device with Magnet Action today and exactly 7 operational days earlier',
      segment_definition: "cn=country CN; intl=known non-CN; unknown=missing country",
      rows: growthRows,
      new_user_quality: {
        definition: 'New DSSU cohort reuse = first-observed satisfied device that performs another Magnet Action on any of days +1 through +7',
        mature_through: maturedThrough,
        rows: newUserQualityRows,
      },
    },
    search_value_funnel: {
      definition: 'search_completed means exhaustive source workflow terminal, not user value completion',
      satisfied_definition: 'satisfied search = submitted search_id with copy_magnet/open_magnet',
      rows: searchFunnelRows,
    },
    rows: dailyRows,
    snapshot_cache: {
      hit: false,
      ttl_seconds: OPS_DAILY_SNAPSHOT_TTL_SECONDS,
      cached_at: new Date(now).toISOString(),
      age_seconds: 0,
    },
  };
  await writeOpsDailySnapshotCache(days, payload);
  return jsonResponse(payload);
}

async function handleEventsPost(request, env, ctx) {
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
  if (data.events.length > 64) {
    return jsonResponse({ error: 'too_many_events', max: 64 }, 400);
  }

  // Keep the public telemetry endpoint abuse-bounded without fighting the App's
  // normal queue drain cadence (successful batches schedule the next flush ~1.2s
  // later). The old 30s gate created avoidable 429 delays for legitimate queues.
  const meta = parseRequestMeta(request);
  if (await checkRateLimit(`ev_${data.did}`, 1)) {
    return jsonResponse({ error: 'rate_limited', retry_after: 1 }, 429);
  }

  // R2 is the durable source of truth. Never put per-event dedupe markers in KV:
  // the daily KV write quota is much smaller than analytics event volume and can
  // otherwise turn telemetry ingestion into 5xx/partial-day outages. Deduplicate
  // only within the incoming batch; Admin performs cross-batch event_id dedupe.
  const normalized = [];
  const seenIncoming = new Set();
  for (const ev of data.events) {
    if (!ev || typeof ev !== 'object' || !ev.id || !ev.e || !ev.ts) continue;
    const eventId = String(ev.id);
    if (seenIncoming.has(eventId)) continue;
    seenIncoming.add(eventId);
    normalized.push(ev);
  }

  if (normalized.length === 0) {
    return jsonResponse({ ok: true, deduped: true, count: 0 });
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
    events: normalized,
    receivedAt: new Date(now).toISOString(),
  };
  // Production schema_v=2 clients send anonymous identity/session metadata at
  // batch level. Preserve it explicitly so a Gateway deploy cannot regress the
  // Admin's install/session/cross-version identity model.
  for (const field of [
    'schema_v', 'batch_id', 'legacy_did', 'device_id', 'device_id_kind',
    'install_id', 'version_code', 'package_name', 'build_type', 'distribution',
    'session_id',
  ]) {
    if (data[field] !== undefined && data[field] !== null) entry[field] = data[field];
  }

  // Write to R2 (primary storage, no TTL — permanent). Keep compact identity/day
  // metadata alongside the immutable body so future DAU audits can use cheap R2
  // listings without object-body fan-out. Older objects remain body-auditable.
  if (env.ANALYTICS) {
    const operationalDays = normalized
      .map((ev) => opsEventTs(ev?.ts))
      .filter((ts) => ts !== null)
      .map((ts) => opsDayKey(ts))
      .sort();
    await env.ANALYTICS.put(id, JSON.stringify(entry), {
      httpMetadata: { contentType: 'application/json' },
      customMetadata: {
        did: String(data.did || ''),
        legacy_did: String(data.legacy_did || ''),
        device_id: String(data.device_id || ''),
        device_id_kind: String(data.device_id_kind || ''),
        schema_v: String(data.schema_v || ''),
        app_v: String(data.app_v || ''),
        country: String(meta.country || ''),
        op_day_min: operationalDays[0] || '',
        op_day_max: operationalDays.at(-1) || '',
      },
    });
    // R2 is the ingestion success boundary. The compact D1 operational index is
    // a rebuildable shadow: index failures must never turn a durable telemetry
    // write into an App-visible 5xx. Historical R2 can always backfill D1 later.
    if (env.OPS_DB && ctx) {
      ctx.waitUntil(retryOpsIndex(env, entry).catch(async (error) => {
        console.error('[analytics-ops] shadow index failed after retries', error?.message || error);
        try {
          await recordOpsShadowFailure(env, entry, error);
        } catch (markerError) {
          console.error('[analytics-ops] failed to persist shadow health marker', markerError?.message || markerError);
        }
      }));
    }
  } else if (env.EVENTS) {
    // Fallback: write to KV if R2 not configured yet
    await env.EVENTS.put(`ev_${data.did}_${now}`, JSON.stringify(entry), { expirationTtl: 86400 * 30 });
  }

  return jsonResponse({ ok: true, id, count: entry.events.length });
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

  const mode = String(url.searchParams.get('mode') || 'legacy');
  if (mode === 'inventory') return await handleEventsInventory(url, env);
  if (mode === 'inventory_page') return await handleEventsInventoryPage(url, env);
  if (mode === 'page') return await handleEventsPage(url, env);
  if (mode === 'ops_daily') return await handleEventsOpsDaily(url, env);
  if (mode !== 'legacy') return jsonResponse({ error: 'invalid_mode' }, 400);

  // Legacy compatibility path. Admin no longer relies on this fan-out read for
  // completeness; scalable recovery uses inventory + one-day cursor pages.
  // Determine date range: ?days=N (default 30, max 90), ?dayOffset=N
  const days = Math.min(parseInt(url.searchParams.get('days')) || 30, 90);
  const dayOffset = parseInt(url.searchParams.get('dayOffset')) || 0;
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
    for (let i = dayOffset; i < dayOffset + days; i++) {
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
    const cutoffMs = Date.now() - (dayOffset + days) * 86400_000;
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
  });
}

// ────────────────────────────────────────────────────────────────────
// APK download proxy (mirrors GitHub Releases for China users)
// ────────────────────────────────────────────────────────────────────

async function handleDownload(request, env, path, ctx) {
  // Path format: /download/v0.1.8/MagGoogo-v0.1.8.apk
  const match = path.match(/^\/download\/(v[\d.]+)\/(.+\.apk)$/);
  if (!match) {
    return jsonResponse({ error: 'invalid_download_path', example: '/download/v0.1.8/MagGoogo-v0.1.8.apk' }, 400);
  }

  const [, tag, filename] = match;
  const r2Key = `${tag}/${filename}`;

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return jsonResponse({ error: 'method_not_allowed' }, 405, { Allow: 'GET, HEAD' });
  }

  // Growth safety net: old static SEO pages may temporarily retain a versioned
  // gateway URL after an app release. Only recover browser clicks that came from
  // magnetgoogo.com; direct/version-pinned callers keep immutable semantics.
  if (request.method === 'GET') {
    try {
      const ref = request.headers.get('Referer') || '';
      const refUrl = ref ? new URL(ref) : null;
      if (refUrl?.hostname === 'magnetgoogo.com') {
        const latest = await resolveLatestDownload(env);
        const currentTag = latest.version ? `v${latest.version}` : '';
        if (currentTag && tag !== currentTag) {
          queueGrowthEvent(request, env, ctx, {
            type: 'legacy_cta_recovered',
            page: refUrl.pathname || '/',
            locale: '',
            placement: 'legacy_versioned_cta',
            requestedVersion: tag.replace(/^v/, ''),
            targetVersion: latest.version,
          });
          return new Response(null, {
            status: 302,
            headers: {
              Location: latest.target,
              'Cache-Control': 'no-store',
              ...corsHeaders(),
            },
          });
        }
      }
    } catch (error) {
      console.error('[download-recovery]', error?.message || error);
    }
  }

  // Try R2 first (fast, no egress fees, global CDN). Passing the request
  // headers lets R2 apply HTTP Range/conditional semantics without buffering
  // the APK in Worker memory.
  if (env.RELEASES) {
    let obj;
    try {
      obj = await env.RELEASES.get(r2Key, {
        onlyIf: request.headers,
        range: request.headers,
      });
    } catch (error) {
      if (request.headers.has('Range')) {
        return jsonResponse({ error: 'invalid_range', tag, filename }, 416);
      }
      throw error;
    }

    if (obj) {
      if (!('body' in obj)) {
        return new Response(null, { status: 412, headers: corsHeaders() });
      }

      const headers = new Headers(corsHeaders());
      obj.writeHttpMetadata(headers);
      headers.set('Content-Type', 'application/vnd.android.package-archive');
      headers.set('Content-Disposition', `attachment; filename="${filename}"`);
      headers.set('Cache-Control', 'public, max-age=86400');
      headers.set('Accept-Ranges', 'bytes');
      headers.set('ETag', obj.httpEtag);

      const requestedRange = request.headers.get('Range');
      const partialRange = requestedRange && obj.range ? obj.range : null;
      if (partialRange) {
        const rangeEnd = partialRange.offset + partialRange.length - 1;
        headers.set('Content-Length', partialRange.length.toString());
        headers.set('Content-Range', `bytes ${partialRange.offset}-${rangeEnd}/${obj.size}`);
      } else {
        headers.set('Content-Length', obj.size.toString());
      }

      return new Response(request.method === 'HEAD' ? null : obj.body, {
        status: partialRange ? 206 : 200,
        headers,
      });
    }
  }

  // Fallback: proxy the same release asset from GitHub, preserving Range.
  const githubUrl = `https://github.com/734496335/magnetgoogo/releases/download/${tag}/${filename}`;
  const upstreamHeaders = { 'User-Agent': 'MagGoogo-Gateway/1.0' };
  const rangeHeader = request.headers.get('Range');
  if (rangeHeader) upstreamHeaders.Range = rangeHeader;

  const upstream = await fetch(githubUrl, {
    method: request.method,
    headers: upstreamHeaders,
    redirect: 'follow',
  });

  if (!upstream.ok) {
    return jsonResponse({ error: 'download_not_found', tag, filename }, upstream.status === 416 ? 416 : 404);
  }

  const responseHeaders = new Headers(corsHeaders());
  for (const headerName of ['Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified']) {
    const value = upstream.headers.get(headerName);
    if (value) responseHeaders.set(headerName, value);
  }
  responseHeaders.set('Content-Type', 'application/vnd.android.package-archive');
  responseHeaders.set('Content-Disposition', `attachment; filename="${filename}"`);
  responseHeaders.set('Cache-Control', 'public, max-age=86400');

  return new Response(request.method === 'HEAD' ? null : upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
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
          if (request.method === 'POST') return await handleEventsPost(request, env, ctx);
          if (request.method === 'GET') return await handleEventsGet(request, env);
          return jsonResponse({ error: 'method_not_allowed' }, 405);
        case '/api/growth':
          if (request.method === 'GET') return await handleGrowthGet(request, env);
          return jsonResponse({ error: 'method_not_allowed' }, 405);
        case '/api/growth/view':
          return await handleGrowthView(request, env, ctx);
        case '/api/growth/rebuild':
          if (request.method === 'POST') return await handleGrowthRebuild(request, env);
          return jsonResponse({ error: 'method_not_allowed' }, 405);
        case '/go/download':
          return await handleGrowthDownload(request, env, ctx);
        default:
          // Handle /api/feedback/:id DELETE
          if (path.startsWith('/api/feedback/') && request.method === 'DELETE') {
            return await handleFeedbackDelete(request, env, path);
          }
          // Handle /download/vX.Y.Z/filename.apk
          if (path.startsWith('/download/')) {
            return await handleDownload(request, env, path, ctx);
          }
          return jsonResponse({ error: 'not_found' }, 404);
      }
    } catch (err) {
      const message = String(err?.message || err || 'Unknown error');
      console.error('[Gateway Error]', err?.stack || message);
      if (/D1_ERROR:.*daily row read limit/i.test(message) || /D1.*free tier daily row read limit/i.test(message)) {
        return jsonResponse({
          error: 'd1_daily_read_quota_exhausted',
          available: false,
          retry_after: '00:00 UTC',
          message: 'D1 daily read capacity is exhausted; retry after the platform daily reset.',
        }, 503, { 'Cache-Control': 'no-store' });
      }
      return jsonResponse({
        error: 'internal_error',
        message,
      }, 500);
    }
  },
};
