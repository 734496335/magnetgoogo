const SHA256_RE = /^[0-9a-f]{64}$/;
const MAX_OBJECT_BYTES = 1024 * 1024;
const MAX_MANIFEST_BYTES = 2 * 1024 * 1024;
const RELEASE_MANIFEST_KEY_RE = /^v1\/releases\/[^/]+\/manifest\.json$/;
const RELEASE_ID_RE = /^\d{8}T\d{6}Z-[0-9a-f]{8}$/;
const MAX_CURRENT_BYTES = 64 * 1024;

export function maxObjectBytesFor(key, objectKind, contentType) {
  const normalizedType = String(contentType || "").split(";", 1)[0].trim().toLowerCase();
  return RELEASE_MANIFEST_KEY_RE.test(key)
    && objectKind === "manifest"
    && normalizedType === "application/json"
    ? MAX_MANIFEST_BYTES
    : MAX_OBJECT_BYTES;
}

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-media-bridge": "1",
    },
  });
}

function hex(bytes) {
  return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function isAuthorized(request, env) {
  const expected = env.UPLOAD_TOKEN;
  const actual = request.headers.get("authorization");
  return typeof expected === "string" && expected.length >= 32 && actual === `Bearer ${expected}`;
}

function parseKey(request, env) {
  const key = new URL(request.url).searchParams.get("key") || "";
  if (!key || key.startsWith("/") || key.includes("\\") || /[\u0000-\u001f]/.test(key)) {
    return { error: "unsafe object key" };
  }
  const parts = key.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    return { error: "unsafe object key" };
  }
  const mode = env.PUBLISH_MODE || "m2-test";
  if (mode === "m2-test") {
    if (!key.startsWith("m2-test/")) {
      return { error: "object key must remain under m2-test/" };
    }
  } else if (mode === "production-data" || mode === "production-auto") {
    const allowed = key.startsWith("v1/objects/")
      || key.startsWith("v1/covers/")
      || key.startsWith("v1/releases/")
      || key.startsWith("staging/pointers/");
    if (!allowed) {
      return { error: "production data key is outside the frozen allowlist" };
    }
  } else {
    return { error: "unsupported publish mode" };
  }
  if (key.endsWith("/v1/current.json") || key === "v1/current.json") {
    return { error: "production current.json is forbidden" };
  }
  return { key };
}

export function validateCurrentCandidate(candidate, existing = null) {
  if (!candidate || candidate.schema_version !== "media-current/1") return "current schema is invalid";
  if (!RELEASE_ID_RE.test(String(candidate.release_id || ""))) return "release_id is invalid";
  if (!Number.isSafeInteger(candidate.pointer_revision) || candidate.pointer_revision < 1) {
    return "pointer_revision is invalid";
  }
  const expectedManifestPath = `/v1/releases/${candidate.release_id}/manifest.json`;
  if (candidate.manifest_path !== expectedManifestPath) return "manifest_path does not match release_id";
  if (!SHA256_RE.test(String(candidate.manifest_sha256 || ""))) return "manifest_sha256 is invalid";
  if (typeof candidate.min_app_version !== "string" || !candidate.min_app_version.trim()) {
    return "min_app_version is invalid";
  }
  if (existing) {
    if (!Number.isSafeInteger(existing.pointer_revision)) return "existing pointer_revision is invalid";
    if (candidate.pointer_revision < existing.pointer_revision) return "pointer revision rollback is forbidden";
    if (candidate.pointer_revision === existing.pointer_revision) {
      const same = candidate.release_id === existing.release_id
        && candidate.manifest_sha256 === existing.manifest_sha256
        && candidate.manifest_path === existing.manifest_path;
      if (!same) return "same revision points to different release bytes";
    }
  }
  return null;
}

async function promoteCurrent(request, env) {
  if ((env.PUBLISH_MODE || "") !== "production-auto") {
    return jsonResponse({ error: "current promotion is disabled" }, 403);
  }
  const expectedHash = (request.headers.get("x-media-sha256") || "").toLowerCase();
  const expectedSize = Number(request.headers.get("x-media-size"));
  if (!SHA256_RE.test(expectedHash) || !Number.isSafeInteger(expectedSize)
      || expectedSize < 2 || expectedSize > MAX_CURRENT_BYTES) {
    return jsonResponse({ error: "invalid current hash or size" }, 400);
  }
  const payload = await request.arrayBuffer();
  if (payload.byteLength !== expectedSize) return jsonResponse({ error: "current body size mismatch" }, 400);
  const actualHash = hex(await crypto.subtle.digest("SHA-256", payload));
  if (actualHash !== expectedHash) return jsonResponse({ error: "current body hash mismatch" }, 400);
  let candidate;
  try {
    candidate = JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return jsonResponse({ error: "current body is not valid JSON" }, 400);
  }
  const existingObject = await env.MEDIA_BUCKET.get("v1/current.json");
  let existing = null;
  if (existingObject) {
    try {
      existing = JSON.parse(await existingObject.text());
    } catch {
      return jsonResponse({ error: "existing current.json is invalid" }, 409);
    }
  }
  const validationError = validateCurrentCandidate(candidate, existing);
  if (validationError) return jsonResponse({ error: validationError }, 409);
  const manifestKey = candidate.manifest_path.replace(/^\//, "");
  const manifest = await env.MEDIA_BUCKET.head(manifestKey);
  if (!manifest || manifest.customMetadata?.sha256 !== candidate.manifest_sha256) {
    return jsonResponse({ error: "candidate manifest is missing or mismatched" }, 409);
  }
  if (existing && candidate.pointer_revision === existing.pointer_revision) {
    return jsonResponse({ promoted: false, reused: true, pointerRevision: candidate.pointer_revision });
  }
  await env.MEDIA_BUCKET.put("v1/current.json", payload, {
    httpMetadata: {
      contentType: "application/json; charset=utf-8",
      cacheControl: "public, max-age=60, must-revalidate",
    },
    customMetadata: {
      sha256: expectedHash,
      releaseId: candidate.release_id,
      objectKind: "current-pointer",
    },
    sha256: expectedHash,
  });
  return jsonResponse({ promoted: true, reused: false, pointerRevision: candidate.pointer_revision }, 201);
}

function objectHeaders(object) {
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("x-media-bridge", "1");
  headers.set("content-length", String(object.size));
  headers.set("etag", object.httpEtag);
  headers.set("x-media-sha256", object.customMetadata?.sha256 || "");
  headers.set("x-media-release-id", object.customMetadata?.releaseId || "");
  headers.set("x-media-object-kind", object.customMetadata?.objectKind || "");
  headers.set("cache-control", headers.get("cache-control") || "no-store");
  return headers;
}

async function putObject(request, env, key) {
  const expectedHash = (request.headers.get("x-media-sha256") || "").toLowerCase();
  const expectedSize = Number(request.headers.get("x-media-size"));
  const releaseId = request.headers.get("x-media-release-id") || "";
  const objectKind = request.headers.get("x-media-object-kind") || "artifact";
  const contentType = request.headers.get("content-type") || "application/octet-stream";
  const maxObjectBytes = maxObjectBytesFor(key, objectKind, contentType);
  if (
    !SHA256_RE.test(expectedHash) ||
    !Number.isSafeInteger(expectedSize) ||
    expectedSize < 0 ||
    expectedSize > maxObjectBytes
  ) {
    return jsonResponse({ error: "invalid expected hash or size" }, 400);
  }
  const payload = await request.arrayBuffer();
  if (payload.byteLength !== expectedSize) {
    return jsonResponse({ error: "request body size mismatch" }, 400);
  }
  const actualHash = hex(await crypto.subtle.digest("SHA-256", payload));
  if (actualHash !== expectedHash) {
    return jsonResponse({ error: "request body hash mismatch" }, 400);
  }

  const existing = await env.MEDIA_BUCKET.head(key);
  if (existing) {
    const same = existing.size === expectedSize && existing.customMetadata?.sha256 === expectedHash;
    if (!same) {
      return jsonResponse({ error: "immutable object conflict" }, 409);
    }
    return jsonResponse({ uploaded: false, reused: true, etag: existing.etag });
  }

  const stored = await env.MEDIA_BUCKET.put(key, payload, {
    onlyIf: { etagDoesNotMatch: "*" },
    httpMetadata: {
      contentType,
      cacheControl: request.headers.get("cache-control") || "no-store",
    },
    customMetadata: { sha256: expectedHash, releaseId, objectKind },
    sha256: expectedHash,
  });
  if (stored) {
    return jsonResponse({ uploaded: true, reused: false, etag: stored.etag }, 201);
  }

  const raced = await env.MEDIA_BUCKET.head(key);
  if (raced && raced.size === expectedSize && raced.customMetadata?.sha256 === expectedHash) {
    return jsonResponse({ uploaded: false, reused: true, etag: raced.etag });
  }
  return jsonResponse({ error: "conditional immutable upload conflict" }, 409);
}

export default {
  async fetch(request, env) {
    if (!isAuthorized(request, env)) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      await env.MEDIA_BUCKET.list({ prefix: "__m2_healthcheck_never__", limit: 1 });
      return jsonResponse({
        status: "ok",
        currentPromotion: (env.PUBLISH_MODE || "") === "production-auto",
        publishMode: env.PUBLISH_MODE || "m2-test",
      });
    }
    if (url.pathname === "/promote" && request.method === "PUT") {
      return promoteCurrent(request, env);
    }
    if (url.pathname === "/current" && (request.method === "GET" || request.method === "HEAD")) {
      const object = request.method === "HEAD"
        ? await env.MEDIA_BUCKET.head("v1/current.json")
        : await env.MEDIA_BUCKET.get("v1/current.json");
      if (!object) {
        return new Response(null, { status: 404, headers: { "x-media-bridge": "1", "cache-control": "no-store" } });
      }
      return request.method === "HEAD"
        ? new Response(null, { status: 200, headers: objectHeaders(object) })
        : new Response(object.body, { status: 200, headers: objectHeaders(object) });
    }
    if (url.pathname !== "/object") {
      return jsonResponse({ error: "not found" }, 404);
    }
    const parsed = parseKey(request, env);
    if (parsed.error) {
      return jsonResponse({ error: parsed.error }, 400);
    }
    const key = parsed.key;
    if (request.method === "PUT") {
      return putObject(request, env, key);
    }
    if (request.method === "HEAD") {
      const object = await env.MEDIA_BUCKET.head(key);
      return object
        ? new Response(null, { status: 200, headers: objectHeaders(object) })
        : new Response(null, { status: 404, headers: { "x-media-bridge": "1", "cache-control": "no-store" } });
    }
    if (request.method === "GET") {
      const object = await env.MEDIA_BUCKET.get(key);
      return object
        ? new Response(object.body, { status: 200, headers: objectHeaders(object) })
        : new Response(null, { status: 404, headers: { "x-media-bridge": "1", "cache-control": "no-store" } });
    }
    return jsonResponse({ error: "method not allowed" }, 405);
  },
};
