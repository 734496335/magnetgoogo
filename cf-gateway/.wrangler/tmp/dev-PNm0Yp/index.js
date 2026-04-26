var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// .wrangler/tmp/bundle-1Y08yM/checked-fetch.js
var urls = /* @__PURE__ */ new Set();
function checkURL(request, init) {
  const url = request instanceof URL ? request : new URL(
    (typeof request === "string" ? new Request(request, init) : request).url
  );
  if (url.port && url.port !== "443" && url.protocol === "https:") {
    if (!urls.has(url.toString())) {
      urls.add(url.toString());
      console.warn(
        `WARNING: known issue with \`fetch()\` requests to custom HTTPS ports in published Workers:
 - ${url.toString()} - the custom port will be ignored when the Worker is published using the \`wrangler deploy\` command.
`
      );
    }
  }
}
__name(checkURL, "checkURL");
globalThis.fetch = new Proxy(globalThis.fetch, {
  apply(target, thisArg, argArray) {
    const [request, init] = argArray;
    checkURL(request, init);
    return Reflect.apply(target, thisArg, argArray);
  }
});

// .wrangler/tmp/bundle-1Y08yM/strip-cf-connecting-ip-header.js
function stripCfConnectingIPHeader(input, init) {
  const request = new Request(input, init);
  request.headers.delete("CF-Connecting-IP");
  return request;
}
__name(stripCfConnectingIPHeader, "stripCfConnectingIPHeader");
globalThis.fetch = new Proxy(globalThis.fetch, {
  apply(target, thisArg, argArray) {
    return Reflect.apply(target, thisArg, [
      stripCfConnectingIPHeader.apply(null, argArray)
    ]);
  }
});

// src/index.js
function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-App-Version, X-Device-Id, X-Member-Token",
    "Access-Control-Max-Age": "86400"
  };
}
__name(corsHeaders, "corsHeaders");
function jsonResponse(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(),
      ...extraHeaders
    }
  });
}
__name(jsonResponse, "jsonResponse");
function semverCompare(a, b) {
  const pa = (a || "0.0.0").split(".").map(Number);
  const pb = (b || "0.0.0").split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) < (pb[i] || 0))
      return -1;
    if ((pa[i] || 0) > (pb[i] || 0))
      return 1;
  }
  return 0;
}
__name(semverCompare, "semverCompare");
async function fetchUpstream(env, path, cacheTtl) {
  const url = `${env.GITHUB_RAW}${path}`;
  try {
    const cache = caches.default;
    if (cache) {
      const cacheKey = new Request(url);
      const cached = await cache.match(cacheKey);
      if (cached)
        return cached;
    }
  } catch {
  }
  const response = await fetch(url, {
    headers: { "User-Agent": "MagGoogo-Gateway/1.0" }
  });
  try {
    const cache = caches.default;
    if (response.ok && cache) {
      const ttl = parseInt(cacheTtl) || 300;
      const toCache = new Response(response.clone().body, response);
      toCache.headers.set("Cache-Control", `public, max-age=${ttl}`);
      cache.put(new Request(url), toCache);
    }
  } catch {
  }
  return response;
}
__name(fetchUpstream, "fetchUpstream");
function parseRequestMeta(request) {
  return {
    appVersion: request.headers.get("X-App-Version") || "",
    deviceId: request.headers.get("X-Device-Id") || "",
    memberToken: request.headers.get("X-Member-Token") || "",
    country: request.headers.get("CF-IPCountry") || "",
    ip: request.headers.get("CF-Connecting-IP") || ""
  };
}
__name(parseRequestMeta, "parseRequestMeta");
async function handleHealth() {
  return jsonResponse({
    service: "MagGoogo Gateway",
    status: "ok",
    timestamp: (/* @__PURE__ */ new Date()).toISOString()
  });
}
__name(handleHealth, "handleHealth");
async function handleConfig(request, env) {
  const upstream = await fetchUpstream(env, "/config.json", env.CACHE_TTL);
  if (!upstream.ok) {
    return jsonResponse({ error: "config_unavailable" }, 502);
  }
  const body = await upstream.clone().text();
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": `public, max-age=${env.CACHE_TTL || 300}`,
      ...corsHeaders()
    }
  });
}
__name(handleConfig, "handleConfig");
async function handleSources(request, env) {
  const meta = parseRequestMeta(request);
  let minVersion = "1.0.0";
  try {
    const configResp = await fetchUpstream(env, "/config.json", env.CACHE_TTL);
    if (configResp.ok) {
      const config = await configResp.clone().json();
      minVersion = config.min_version || "1.0.0";
    }
  } catch {
  }
  if (meta.appVersion && semverCompare(meta.appVersion, minVersion) < 0) {
    return jsonResponse({
      error: "update_required",
      min_version: minVersion,
      message: `\u8BF7\u66F4\u65B0App\u5230 ${minVersion} \u4EE5\u4E0A\u7248\u672C`
    }, 403);
  }
  const sourceFile = "/sources.enc.json";
  const upstream = await fetchUpstream(env, sourceFile, env.CACHE_TTL);
  if (!upstream.ok) {
    return jsonResponse({ error: "sources_unavailable" }, 502);
  }
  const body = await upstream.clone().text();
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": `public, max-age=${env.CACHE_TTL || 300}`,
      ...corsHeaders()
    }
  });
}
__name(handleSources, "handleSources");
async function handleCheck(request, env) {
  const meta = parseRequestMeta(request);
  let config = {};
  try {
    const configResp = await fetchUpstream(env, "/config.json", env.CACHE_TTL);
    if (configResp.ok)
      config = await configResp.json();
  } catch {
  }
  const minVersion = config.min_version || "1.0.0";
  const latestVersion = config.latest_version || "1.0.0";
  const forceUpdate = meta.appVersion ? semverCompare(meta.appVersion, minVersion) < 0 : false;
  const updateAvailable = meta.appVersion ? semverCompare(meta.appVersion, latestVersion) < 0 : false;
  const membership = {
    tier: "free",
    expires_at: null,
    valid: true
  };
  return jsonResponse({
    app_version: meta.appVersion,
    force_update: forceUpdate,
    update_available: updateAvailable,
    min_version: minVersion,
    latest_version: latestVersion,
    announcement: config.announcement || "",
    download: config.download || {},
    membership,
    country: meta.country
  });
}
__name(handleCheck, "handleCheck");
async function handleFeedbackPost(request, env) {
  const body = await request.text();
  if (body.length > 2048) {
    return jsonResponse({ error: "feedback_too_long", max: 2048 }, 400);
  }
  let data;
  try {
    data = JSON.parse(body);
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }
  const text = (data.text || "").trim();
  if (!text || text.length > 1e3) {
    return jsonResponse({ error: text ? "feedback_too_long" : "empty_feedback" }, 400);
  }
  const meta = parseRequestMeta(request);
  if (env.FEEDBACK) {
    const rateKey = `rl_${meta.ip}`;
    const last = await env.FEEDBACK.get(rateKey);
    if (last) {
      return jsonResponse({ error: "rate_limited", retry_after: 60 }, 429);
    }
    await env.FEEDBACK.put(rateKey, "1", { expirationTtl: 60 });
  }
  const id = `fb_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const entry = {
    id,
    text,
    appVersion: meta.appVersion,
    country: meta.country,
    platform: data.platform || "",
    createdAt: (/* @__PURE__ */ new Date()).toISOString()
  };
  if (env.FEEDBACK) {
    await env.FEEDBACK.put(id, JSON.stringify(entry), { expirationTtl: 86400 * 90 });
  }
  return jsonResponse({ ok: true, id });
}
__name(handleFeedbackPost, "handleFeedbackPost");
async function handleFeedbackList(request, env) {
  const url = new URL(request.url);
  const secret = url.searchParams.get("secret") || request.headers.get("X-Admin-Secret") || "";
  const adminSecret = env.ADMIN_SECRET || "maggoogo-admin-2026";
  if (secret !== adminSecret) {
    return jsonResponse({ error: "unauthorized" }, 401);
  }
  if (!env.FEEDBACK) {
    return jsonResponse({ error: "kv_not_configured" }, 500);
  }
  const list = await env.FEEDBACK.list({ prefix: "fb_", limit: 100 });
  const items = [];
  for (const key of list.keys) {
    const val = await env.FEEDBACK.get(key.name);
    if (val)
      items.push(JSON.parse(val));
  }
  items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  return jsonResponse({ count: items.length, items });
}
__name(handleFeedbackList, "handleFeedbackList");
var src_default = {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      switch (path) {
        case "/":
          return handleHealth();
        case "/config.json":
          return await handleConfig(request, env);
        case "/sources.enc.json":
          return await handleSources(request, env);
        case "/api/check":
          return await handleCheck(request, env);
        case "/api/feedback":
          if (request.method === "POST")
            return await handleFeedbackPost(request, env);
          if (request.method === "GET")
            return await handleFeedbackList(request, env);
          return jsonResponse({ error: "method_not_allowed" }, 405);
        default:
          return jsonResponse({ error: "not_found" }, 404);
      }
    } catch (err) {
      console.error("[Gateway Error]", err.stack || err.message || err);
      return jsonResponse({
        error: "internal_error",
        message: err.message || "Unknown error"
      }, 500);
    }
  }
};

// node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-1Y08yM/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = src_default;

// node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-1Y08yM/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof __Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
__name(__Facade_ScheduledController__, "__Facade_ScheduledController__");
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = (request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    };
    #dispatcher = (type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    };
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
