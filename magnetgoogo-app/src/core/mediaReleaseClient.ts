import { Buffer } from 'buffer';
import * as Application from 'expo-application';
import { getAppVersion } from './configChecker';
import {
  assertMediaPointerTransition,
  classifyMediaCurrentState,
  mediaPointerIdentity,
  parseCatalog,
  parseCurrentPointer,
  parseDetail,
  parseManifest,
  parseResources,
  selectMediaCurrentCandidate,
  sha256Hex,
  MediaReleaseValidationError,
  type MediaCurrentCandidate,
  type MediaCurrentPointer,
  type MediaManifest,
  type MediaObjectRef,
  type MediaPointerIdentity,
} from './mediaReleaseProtocol';
import {
  cachedMediaCatalog,
  cachedMediaDetail,
  cachedMediaFeed,
  cachedMediaFeedIdentity,
  cachedMediaFeedNeedsConsumerRefresh,
  cachedMediaPointerIdentity,
  saveMediaCatalog,
  saveMediaDetail,
  saveMediaFeeds,
} from './mediaReleaseCache';
import type {
  MediaKind,
  MovieFeed,
  MovieFeedItem,
} from './resourceFeedProtocol';
import {
  mediaFeedItemFromCatalogCard,
  mergeMediaDetailIntoFeedItem,
} from './mediaReleaseMapping';

const MEDIA_ENDPOINTS = [
  'https://media.magnetgoogo.com',
  'https://api.naoshiquan.com/media',
] as const;
const CURRENT_TIMEOUT_MS = 10_000;
const CURRENT_MAX_ATTEMPTS = 2;
const OBJECT_TIMEOUT_MS = 9000;

interface ActiveRelease {
  endpoint: string;
  endpoints: string[];
  pointer: MediaCurrentPointer;
  identity: MediaPointerIdentity;
  manifest: MediaManifest;
}

let activeRelease: ActiveRelease | null = null;
let syncPromise: Promise<ActiveRelease> | null = null;
const detailSyncs = new Map<string, Promise<MovieFeedItem>>();

function detailSyncKey(item: MovieFeedItem): string {
  return [
    item.content_kind,
    item.movie_id,
    item.remote_release_id || 'bundled',
    item.remote_detail_hash || item.remote_detail_path || 'no-detail',
  ].join('|');
}

function logMediaNetworkSuccess(stage: string, context: Record<string, unknown>) {
  if (!Application.applicationId?.endsWith('.debug')) return;
  console.log('[MediaReleaseEvidence]', {
    stage,
    error_code: 'OK',
    ...context,
  });
}

function logMediaNetworkFailure(
  stage: string,
  errorCode: string,
  error: unknown,
  context: Record<string, unknown> = {},
) {
  console.warn('[MediaReleaseClient]', {
    stage,
    error_code: errorCode,
    ...context,
    error: error instanceof Error ? error.message : String(error),
  });
}

function compareSemver(left: string, right: string): number {
  const a = left.split('.').map((value) => Number(value) || 0);
  const b = right.split('.').map((value) => Number(value) || 0);
  for (let index = 0; index < 3; index += 1) {
    if ((a[index] ?? 0) < (b[index] ?? 0)) return -1;
    if ((a[index] ?? 0) > (b[index] ?? 0)) return 1;
  }
  return 0;
}

async function fetchBytes(url: string, timeoutMs: number): Promise<Uint8Array> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | null = null;
  const request = fetch(url, {
    signal: controller.signal,
    headers: { accept: 'application/json, image/*;q=0.8, */*;q=0.5' },
  }).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  });
  const timeout = new Promise<Uint8Array>((_resolve, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(new Error(`REQUEST_TIMEOUT_${timeoutMs}`));
    }, timeoutMs);
  });
  try {
    return await Promise.race([request, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function parseJson(bytes: Uint8Array, context: string): unknown {
  try {
    return JSON.parse(Buffer.from(bytes).toString('utf8'));
  } catch (error) {
    throw new Error(`${context}_INVALID_JSON:${error instanceof Error ? error.message : String(error)}`);
  }
}

function isTransientCurrentError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message === 'Network request failed'
    || message.startsWith('REQUEST_TIMEOUT_')
    || message.startsWith('HTTP_5');
}

async function fetchCurrent(endpoint: string): Promise<MediaCurrentCandidate> {
  let lastError: unknown = null;
  for (let attempt = 1; attempt <= CURRENT_MAX_ATTEMPTS; attempt += 1) {
    try {
      const bytes = await fetchBytes(`${endpoint}/v1/current.json`, CURRENT_TIMEOUT_MS);
      const pointer = parseCurrentPointer(parseJson(bytes, 'CURRENT'));
      if (compareSemver(getAppVersion(), pointer.min_app_version) < 0) {
        throw new Error(`APP_VERSION_TOO_OLD:${pointer.min_app_version}`);
      }
      return {
        endpoint,
        pointer,
        pointer_revision: pointer.pointer_revision,
        pointer_sha256: sha256Hex(bytes),
        release_id: pointer.release_id,
        manifest_sha256: pointer.manifest_sha256,
      };
    } catch (error) {
      lastError = error;
      if (attempt >= CURRENT_MAX_ATTEMPTS || !isTransientCurrentError(error)) throw error;
      logMediaNetworkFailure('fetch_current_retry', 'MEDIA_CURRENT_TRANSIENT_RETRY', error, {
        endpoint,
        attempt,
      });
    }
  }
  throw lastError instanceof Error ? lastError : new Error('MEDIA_CURRENT_UNAVAILABLE');
}

type RemotePointerState = 'same' | 'changed' | 'unavailable';

export interface MediaFeedSyncResult {
  feed: MovieFeed;
  remoteRevalidated: boolean;
  remoteState: RemotePointerState;
}

async function remotePointerState(identity: MediaPointerIdentity): Promise<RemotePointerState> {
  const settled = await Promise.allSettled(MEDIA_ENDPOINTS.map((endpoint) => fetchCurrent(endpoint)));
  settled.forEach((result, index) => {
    if (result.status === 'rejected') {
      logMediaNetworkFailure('check_current', 'MEDIA_CURRENT_CHECK_FAILED', result.reason, {
        endpoint: MEDIA_ENDPOINTS[index],
      });
    }
  });
  const candidates = settled
    .filter((result): result is PromiseFulfilledResult<MediaCurrentCandidate> => result.status === 'fulfilled')
    .map((result) => result.value);
  if (!candidates.length) return 'unavailable';
  try {
    return classifyMediaCurrentState(candidates, identity);
  } catch (error) {
    logMediaNetworkFailure('check_current', 'MEDIA_CURRENT_STATE_CONFLICT', error, {
      candidate_count: candidates.length,
      accepted_revision: identity.pointer_revision,
    });
    return 'changed';
  }
}

function newestAcceptedIdentity(
  memory: MediaPointerIdentity | null,
  disk: MediaPointerIdentity | null,
): MediaPointerIdentity | null {
  if (!memory) return disk;
  if (!disk) return memory;
  if (memory.pointer_revision >= disk.pointer_revision) {
    assertMediaPointerTransition(memory, disk);
    return memory;
  }
  assertMediaPointerTransition(disk, memory);
  return disk;
}

async function fetchReferencedJson<T>(
  endpoints: string[],
  ref: MediaObjectRef,
  parser: (value: unknown) => T,
  stage: string,
): Promise<{ value: T; endpoint: string }> {
  let lastError: unknown = null;
  for (const endpoint of endpoints) {
    try {
      const bytes = await fetchBytes(`${endpoint}${ref.path}`, OBJECT_TIMEOUT_MS);
      if (bytes.byteLength !== ref.size || sha256Hex(bytes) !== ref.hash) {
        throw new Error('OBJECT_HASH_OR_SIZE_MISMATCH');
      }
      return { value: parser(parseJson(bytes, stage)), endpoint };
    } catch (error) {
      lastError = error;
      logMediaNetworkFailure(stage, 'MEDIA_OBJECT_ENDPOINT_FAILED', error, {
        endpoint,
        path: ref.path,
      });
    }
  }
  throw lastError instanceof Error ? lastError : new Error(`${stage}_UNAVAILABLE`);
}

async function fetchCatalogObject(
  endpoints: string[],
  ref: MediaObjectRef,
): Promise<{ value: ReturnType<typeof parseCatalog>; endpoint: string; cacheHit: boolean }> {
  const cached = await cachedMediaCatalog(ref);
  if (cached) {
    return { value: cached, endpoint: endpoints[0], cacheHit: true };
  }

  let lastError: unknown = null;
  for (const endpoint of endpoints) {
    try {
      const bytes = await fetchBytes(`${endpoint}${ref.path}`, OBJECT_TIMEOUT_MS);
      if (bytes.byteLength !== ref.size || sha256Hex(bytes) !== ref.hash) {
        throw new Error('OBJECT_HASH_OR_SIZE_MISMATCH');
      }
      const value = parseCatalog(parseJson(bytes, 'fetch_catalog'));
      await saveMediaCatalog(ref, bytes);
      return { value, endpoint, cacheHit: false };
    } catch (error) {
      lastError = error;
      logMediaNetworkFailure('fetch_catalog', 'MEDIA_OBJECT_ENDPOINT_FAILED', error, {
        endpoint,
        path: ref.path,
      });
    }
  }
  throw lastError instanceof Error ? lastError : new Error('fetch_catalog_UNAVAILABLE');
}

async function resolveActiveRelease(forceRefresh = false): Promise<ActiveRelease> {
  if (!forceRefresh && activeRelease) return activeRelease;
  if (!forceRefresh && syncPromise) return syncPromise;
  const task = (async () => {
    const settled = await Promise.allSettled(MEDIA_ENDPOINTS.map((endpoint) => fetchCurrent(endpoint)));
    settled.forEach((result, index) => {
      if (result.status === 'rejected') {
        logMediaNetworkFailure('fetch_current', 'MEDIA_CURRENT_ENDPOINT_FAILED', result.reason, {
          endpoint: MEDIA_ENDPOINTS[index],
        });
      }
    });
    const candidates = settled
      .filter((result): result is PromiseFulfilledResult<MediaCurrentCandidate> => result.status === 'fulfilled')
      .map((result) => result.value);
    if (!candidates.length) throw new Error('MEDIA_CURRENT_UNAVAILABLE');

    const acceptedIdentity = newestAcceptedIdentity(
      activeRelease?.identity ?? null,
      await cachedMediaPointerIdentity(),
    );
    let winner: MediaCurrentCandidate;
    try {
      winner = selectMediaCurrentCandidate(candidates, acceptedIdentity);
    } catch (error) {
      logMediaNetworkFailure(
        'select_current',
        error instanceof MediaReleaseValidationError ? error.code : 'MEDIA_POINTER_SELECTION_FAILED',
        error,
        {
          candidate_count: candidates.length,
          accepted_revision: acceptedIdentity?.pointer_revision ?? null,
        },
      );
      throw error;
    }
    const matchingEndpoints = candidates
      .filter((candidate) => candidate.pointer_sha256 === winner.pointer_sha256)
      .map((candidate) => candidate.endpoint);
    const endpointOrder = [
      winner.endpoint,
      ...matchingEndpoints.filter((endpoint) => endpoint !== winner.endpoint),
      ...MEDIA_ENDPOINTS.filter((endpoint) => !matchingEndpoints.includes(endpoint)),
    ];
    const manifestRef: MediaObjectRef = {
      path: winner.pointer.manifest_path,
      hash: winner.pointer.manifest_sha256,
      size: -1,
    };
    let manifestBytes: Uint8Array | null = null;
    let manifestEndpoint = winner.endpoint;
    let lastError: unknown = null;
    for (const endpoint of endpointOrder) {
      try {
        const bytes = await fetchBytes(`${endpoint}${manifestRef.path}`, OBJECT_TIMEOUT_MS);
        if (sha256Hex(bytes) !== manifestRef.hash) throw new Error('MANIFEST_HASH_MISMATCH');
        manifestBytes = bytes;
        manifestEndpoint = endpoint;
        break;
      } catch (error) {
        lastError = error;
        logMediaNetworkFailure('fetch_manifest', 'MEDIA_MANIFEST_ENDPOINT_FAILED', error, {
          endpoint,
          path: manifestRef.path,
        });
      }
    }
    if (!manifestBytes) throw lastError instanceof Error ? lastError : new Error('MEDIA_MANIFEST_UNAVAILABLE');
    const manifest = parseManifest(parseJson(manifestBytes, 'MANIFEST'));
    if (manifest.release_id !== winner.pointer.release_id) {
      throw new Error('MANIFEST_RELEASE_ID_MISMATCH');
    }
    const resolved: ActiveRelease = {
      endpoint: manifestEndpoint,
      endpoints: [manifestEndpoint, ...endpointOrder.filter((endpoint) => endpoint !== manifestEndpoint)],
      pointer: winner.pointer,
      identity: mediaPointerIdentity(winner),
      manifest,
    };
    activeRelease = resolved;
    logMediaNetworkSuccess('active_release', {
      release_id: resolved.pointer.release_id,
      pointer_revision: resolved.pointer.pointer_revision,
      pointer_sha256: resolved.identity.pointer_sha256,
      endpoint: resolved.endpoint,
      fallback_endpoint_count: resolved.endpoints.length - 1,
      movie_count: resolved.manifest.counts.movie,
      series_count: resolved.manifest.counts.series,
    });
    return resolved;
  })();
  syncPromise = task;
  try {
    return await task;
  } finally {
    if (syncPromise === task) syncPromise = null;
  }
}

function catalogRefs(manifest: MediaManifest, kind: MediaKind): MediaObjectRef[] {
  const refs: MediaObjectRef[] = [];
  Object.entries(manifest.channels).forEach(([channel, value]) => {
    if (kind === 'movie' && channel !== 'movie') return;
    if (kind === 'series' && !channel.startsWith('series_')) return;
    if (value.featured) refs.push(value.featured);
    if (value.updating) refs.push(value.updating);
    refs.push(...value.latest_pages);
  });
  const seen = new Set<string>();
  return refs.filter((ref) => {
    if (seen.has(ref.hash)) return false;
    seen.add(ref.hash);
    return true;
  });
}

export async function syncMediaFeed(kind: MediaKind): Promise<MediaFeedSyncResult> {
  const [cachedFeed, cachedIdentity, needsConsumerRefresh] = await Promise.all([
    cachedMediaFeed(kind),
    cachedMediaFeedIdentity(kind),
    cachedMediaFeedNeedsConsumerRefresh(kind),
  ]);
  if (cachedFeed && cachedIdentity) {
    const pointerState = await remotePointerState(cachedIdentity);
    if (pointerState === 'unavailable' || (pointerState === 'same' && !needsConsumerRefresh)) {
      logMediaNetworkSuccess(pointerState === 'same' ? 'feed_unchanged' : 'feed_offline_cache', {
        release_id: cachedIdentity.release_id,
        pointer_revision: cachedIdentity.pointer_revision,
        pointer_sha256: cachedIdentity.pointer_sha256,
        content_kind: kind,
        item_count: cachedFeed.items.length,
        incremental_network_bytes: pointerState === 'same' ? 'current_only' : 'unavailable',
      });
      return {
        feed: cachedFeed,
        remoteRevalidated: pointerState === 'same',
        remoteState: pointerState,
      };
    }
    if (pointerState === 'same' && needsConsumerRefresh) {
      logMediaNetworkSuccess('feed_consumer_schema_refresh', {
        release_id: cachedIdentity.release_id,
        pointer_revision: cachedIdentity.pointer_revision,
        pointer_sha256: cachedIdentity.pointer_sha256,
        content_kind: kind,
        previous_feed_schema: 'media-app-feed-cache/2',
        target_feed_schema: 'media-app-feed-cache/3',
      });
    }
  }

  const release = await resolveActiveRelease(true);
  const refs = catalogRefs(release.manifest, kind);
  const catalogs = await Promise.all(refs.map((ref) => fetchCatalogObject(
    release.endpoints,
    ref,
  )));
  const byId = new Map<string, MovieFeedItem>();
  catalogs.forEach(({ value, endpoint }) => {
    value.items.forEach((card) => {
      if (card.content_kind !== kind || byId.has(card.media_id)) return;
      byId.set(card.media_id, mediaFeedItemFromCatalogCard(card, byId.size + 1, endpoint, release.pointer.release_id));
    });
  });
  const items = [...byId.values()].map((item, index) => ({ ...item, rank: index + 1 }));
  const feed: MovieFeed = {
    schema_version: 'media-app-feed/1',
    source_id: 'media-release',
    content_kind: kind,
    generated_at: release.manifest.generated_at,
    snapshot_captured_at: release.pointer.published_at,
    items,
    summary: {
      record_count: items.length,
      target_count: kind === 'movie' ? release.manifest.counts.movie : release.manifest.counts.series,
      recommended_count: items.filter((item) => item.recommended).length,
      resource_count: items.reduce((sum, item) => sum + (item.resource_count_hint ?? 0), 0),
      missing_urls: [],
      snapshot_http_requests: 0,
      detail_http_requests: 0,
      database_movie_count: items.length,
      cover_count: items.length,
      offline_ready: true,
    },
  };
  try {
    await saveMediaFeeds(
      release.identity,
      release.endpoint,
      { [kind]: feed },
    );
  } catch (error) {
    if (activeRelease?.identity.pointer_sha256 === release.identity.pointer_sha256) {
      activeRelease = null;
    }
    logMediaNetworkFailure(
      'persist_feed',
      error instanceof MediaReleaseValidationError ? error.code : 'MEDIA_CACHE_COMMIT_FAILED',
      error,
      {
        release_id: release.pointer.release_id,
        pointer_revision: release.pointer.pointer_revision,
      },
    );
    throw error;
  }
  logMediaNetworkSuccess('feed_synced', {
    release_id: release.pointer.release_id,
    pointer_revision: release.pointer.pointer_revision,
    endpoint: release.endpoint,
    content_kind: kind,
    item_count: items.length,
    resource_count: feed.summary.resource_count,
    catalog_cache_hits: catalogs.filter((catalog) => catalog.cacheHit).length,
    catalog_downloads: catalogs.filter((catalog) => !catalog.cacheHit).length,
  });
  return {
    feed,
    remoteRevalidated: true,
    remoteState: 'changed',
  };
}

function detailEndpointOrder(item: MovieFeedItem): string[] {
  const preferred = item.remote_endpoint && MEDIA_ENDPOINTS.includes(item.remote_endpoint as typeof MEDIA_ENDPOINTS[number])
    ? item.remote_endpoint
    : null;
  return [
    ...(preferred ? [preferred] : []),
    ...MEDIA_ENDPOINTS.filter((endpoint) => endpoint !== preferred),
  ];
}

async function fetchAndCacheRemoteMediaDetail(item: MovieFeedItem): Promise<MovieFeedItem> {
  if (!item.remote_detail_path || !item.remote_detail_hash || item.remote_detail_size === undefined) return item;
  const endpoints = detailEndpointOrder(item);
  const detailResult = await fetchReferencedJson(
    endpoints,
    {
      path: item.remote_detail_path,
      hash: item.remote_detail_hash,
      size: item.remote_detail_size,
    },
    parseDetail,
    'fetch_detail',
  );
  if (detailResult.value.media_id !== item.movie_id || detailResult.value.content_kind !== item.content_kind) {
    throw new Error('MEDIA_DETAIL_IDENTITY_MISMATCH');
  }
  if (detailResult.value.resource_object.encrypted) {
    throw new Error('ENCRYPTED_MEDIA_RESOURCES_UNSUPPORTED');
  }
  const resourceResult = await fetchReferencedJson(
    [detailResult.endpoint, ...endpoints.filter((endpoint) => endpoint !== detailResult.endpoint)],
    detailResult.value.resource_object,
    parseResources,
    'fetch_resources',
  );
  if (resourceResult.value.media_id !== item.movie_id) {
    throw new Error('MEDIA_RESOURCES_IDENTITY_MISMATCH');
  }
  const merged = mergeMediaDetailIntoFeedItem(item, detailResult.value, resourceResult.value, resourceResult.endpoint);
  await saveMediaDetail(merged);
  logMediaNetworkSuccess('detail_synced', {
    release_id: merged.remote_release_id,
    endpoint: merged.remote_endpoint,
    content_kind: merged.content_kind,
    media_id: merged.movie_id,
    resource_count: merged.resources.length,
    manifest_refresh_skipped: true,
  });
  return merged;
}

export async function loadRemoteMediaDetail(item: MovieFeedItem): Promise<MovieFeedItem> {
  const cached = await cachedMediaDetail(item);
  if (cached) {
    logMediaNetworkSuccess('detail_cache_hit', {
      release_id: cached.remote_release_id,
      content_kind: cached.content_kind,
      media_id: cached.movie_id,
      resource_count: cached.resources.length,
      detail_hash: cached.remote_detail_hash,
    });
    return cached;
  }

  const syncKey = detailSyncKey(item);
  const existing = detailSyncs.get(syncKey);
  if (existing) return existing;
  const task = fetchAndCacheRemoteMediaDetail(item).finally(() => {
    if (detailSyncs.get(syncKey) === task) detailSyncs.delete(syncKey);
  });
  detailSyncs.set(syncKey, task);
  return task;
}

export function clearActiveMediaRelease() {
  activeRelease = null;
  syncPromise = null;
}
