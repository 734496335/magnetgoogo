import { Buffer } from 'buffer';
import { Directory, File, Paths } from 'expo-file-system';
import {
  assertMediaPointerTransition,
  parseCatalog,
  sha256Hex,
  type MediaCatalog,
  type MediaObjectRef,
  type MediaPointerIdentity,
} from './mediaReleaseProtocol';
import {
  parseResourceFeed,
  parseResourceFeedItem,
  type MediaKind,
  type MovieFeed,
  type MovieFeedItem,
} from './resourceFeedProtocol';
import {
  deleteLegacyMediaCache,
  legacyMediaCacheExists,
  readLegacyMediaCache,
  type LegacyMediaCacheState,
} from './mediaReleaseLegacyMigration';

const CACHE_ROOT = new Directory(Paths.document, 'media-release-cache-v2');
const FEED_DIR = new Directory(CACHE_ROOT, 'feeds');
const CATALOG_DIR = new Directory(CACHE_ROOT, 'catalogs');
const DETAIL_DIR = new Directory(CACHE_ROOT, 'details');
const INDEX_NAME = 'index.json';
const MIGRATION_MARKER_NAME = 'legacy-migration-complete.json';
const SHA256_RE = /^[0-9a-f]{64}$/;

export interface MediaCacheIndex {
  schema_version: 'media-app-cache-index/2';
  updated_at: string;
  endpoint: string;
  identity: MediaPointerIdentity;
}

interface MediaFeedCacheEnvelope {
  schema_version: 'media-app-feed-cache/2';
  saved_at: string;
  endpoint: string;
  identity: MediaPointerIdentity;
  feed: MovieFeed;
}

interface MediaCatalogCacheEnvelope {
  schema_version: 'media-app-catalog-cache/2';
  saved_at: string;
  hash: string;
  size: number;
  payload_base64: string;
}

interface MediaDetailCacheEnvelope {
  schema_version: 'media-app-detail-cache/2';
  saved_at: string;
  media_id: string;
  content_kind: MediaKind;
  detail_hash: string;
  item: MovieFeedItem;
}

interface MigrationMarker {
  schema_version: 'media-app-cache-migration/1';
  completed_at: string;
  migrated: boolean;
}

let memoryIndex: MediaCacheIndex | null | undefined;
const memoryFeeds: Partial<Record<MediaKind, MovieFeed | null>> = {};
const memoryFeedIdentities: Partial<Record<MediaKind, MediaPointerIdentity | null>> = {};
const loadedFeedKinds = new Set<MediaKind>();
const memoryCatalogs = new Map<string, MediaCatalog>();
const missingCatalogs = new Set<string>();
const memoryDetails = new Map<string, MovieFeedItem>();
const missingDetails = new Set<string>();
let migrationPromise: Promise<void> | null = null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function logCacheFailure(stage: string, errorCode: string, error: unknown, context: Record<string, unknown> = {}) {
  console.warn('[MediaReleaseCache]', {
    stage,
    error_code: errorCode,
    ...context,
    error: error instanceof Error ? error.message : String(error),
  });
}

function ensureDirectories(): void {
  if (!CACHE_ROOT.exists) CACHE_ROOT.create();
  if (!FEED_DIR.exists) FEED_DIR.create();
  if (!CATALOG_DIR.exists) CATALOG_DIR.create();
  if (!DETAIL_DIR.exists) DETAIL_DIR.create();
}

function deleteIfExists(file: File): void {
  if (file.exists) file.delete();
}

function jsonShardExists(directory: Directory, name: string): boolean {
  return new File(directory, name).exists || new File(directory, `.${name}.backup`).exists;
}

function deleteJsonShard(directory: Directory, name: string): void {
  deleteIfExists(new File(directory, name));
  deleteIfExists(new File(directory, `.${name}.backup`));
}

function migrationMarkerFile(): File {
  return new File(CACHE_ROOT, MIGRATION_MARKER_NAME);
}

function mediaIdCacheKey(mediaId: string): string {
  return sha256Hex(Uint8Array.from(Buffer.from(mediaId, 'utf8')));
}

async function writeTextAtomically(
  directory: Directory,
  name: string,
  text: string,
  validate: (writtenText: string) => void,
): Promise<void> {
  ensureDirectories();
  const backupName = `.${name}.backup`;
  const temporaryName = `.${name}.${Date.now()}.tmp`;
  const targetFile = () => new File(directory, name);
  const backupFile = () => new File(directory, backupName);
  const temporaryFile = () => new File(directory, temporaryName);
  let targetMoved = false;
  let temporaryMoved = false;
  try {
    deleteIfExists(temporaryFile());
    temporaryFile().create();
    temporaryFile().write(text);
    validate(await temporaryFile().text());

    deleteIfExists(backupFile());
    if (targetFile().exists) {
      targetFile().move(backupFile());
      targetMoved = true;
    }
    temporaryFile().move(targetFile());
    temporaryMoved = true;
    validate(await targetFile().text());
    deleteIfExists(backupFile());
  } catch (error) {
    if (temporaryMoved) deleteIfExists(targetFile());
    if (targetMoved && backupFile().exists) backupFile().move(targetFile());
    throw error;
  } finally {
    if (!temporaryMoved) deleteIfExists(temporaryFile());
    if (targetFile().exists) deleteIfExists(backupFile());
  }
}

async function writeJsonAtomically(
  directory: Directory,
  name: string,
  value: unknown,
): Promise<void> {
  await writeTextAtomically(directory, name, JSON.stringify(value), (text) => {
    JSON.parse(text);
  });
}

async function readJsonResilient(directory: Directory, name: string): Promise<unknown> {
  const target = new File(directory, name);
  const backup = new File(directory, `.${name}.backup`);
  if (target.exists) {
    try {
      return JSON.parse(await target.text());
    } catch (error) {
      if (!backup.exists) throw error;
      deleteIfExists(target);
    }
  }
  if (!backup.exists) throw new Error('MEDIA_CACHE_FILE_MISSING');
  const recovered = JSON.parse(await backup.text());
  backup.move(target);
  return recovered;
}

function validateIdentity(value: unknown, context: string): MediaPointerIdentity {
  if (!isRecord(value)) throw new Error(`${context}_IDENTITY_INVALID`);
  const identity: MediaPointerIdentity = {
    pointer_revision: value.pointer_revision as number,
    pointer_sha256: value.pointer_sha256 as string,
    release_id: value.release_id as string,
    manifest_sha256: value.manifest_sha256 as string,
  };
  assertMediaPointerTransition(identity, null);
  return identity;
}

function validateIndex(value: unknown): MediaCacheIndex {
  if (!isRecord(value) || value.schema_version !== 'media-app-cache-index/2') {
    throw new Error('MEDIA_CACHE_INDEX_INVALID');
  }
  if (
    typeof value.updated_at !== 'string'
    || typeof value.endpoint !== 'string'
    || !value.endpoint.startsWith('https://')
  ) {
    throw new Error('MEDIA_CACHE_INDEX_INVALID');
  }
  return {
    schema_version: 'media-app-cache-index/2',
    updated_at: value.updated_at,
    endpoint: value.endpoint,
    identity: validateIdentity(value.identity, 'MEDIA_CACHE_INDEX'),
  };
}

function validateFeedEnvelope(value: unknown, expectedKind: MediaKind): MediaFeedCacheEnvelope {
  if (!isRecord(value) || value.schema_version !== 'media-app-feed-cache/2') {
    throw new Error('MEDIA_FEED_CACHE_ENVELOPE_INVALID');
  }
  if (
    typeof value.saved_at !== 'string'
    || typeof value.endpoint !== 'string'
    || !value.endpoint.startsWith('https://')
  ) {
    throw new Error('MEDIA_FEED_CACHE_ENVELOPE_INVALID');
  }
  const feed = parseResourceFeed(value.feed, {
    requireOfflineCover: false,
    allowResourceCountHints: true,
  });
  if (feed.content_kind !== expectedKind) throw new Error('MEDIA_FEED_CACHE_KIND_MISMATCH');
  return {
    schema_version: 'media-app-feed-cache/2',
    saved_at: value.saved_at,
    endpoint: value.endpoint,
    identity: validateIdentity(value.identity, 'MEDIA_FEED_CACHE'),
    feed,
  };
}

function validateCatalogEnvelope(
  value: unknown,
  expectedRef: MediaObjectRef,
): { envelope: MediaCatalogCacheEnvelope; catalog: MediaCatalog } {
  if (!isRecord(value) || value.schema_version !== 'media-app-catalog-cache/2') {
    throw new Error('MEDIA_CATALOG_CACHE_ENVELOPE_INVALID');
  }
  if (
    typeof value.saved_at !== 'string'
    || typeof value.hash !== 'string'
    || value.hash !== expectedRef.hash
    || typeof value.size !== 'number'
    || value.size !== expectedRef.size
    || typeof value.payload_base64 !== 'string'
  ) {
    throw new Error('MEDIA_CATALOG_CACHE_ENVELOPE_INVALID');
  }
  const bytes = Uint8Array.from(Buffer.from(value.payload_base64, 'base64'));
  if (bytes.byteLength !== expectedRef.size || sha256Hex(bytes) !== expectedRef.hash) {
    throw new Error('MEDIA_CATALOG_CACHE_HASH_OR_SIZE_MISMATCH');
  }
  const catalog = parseCatalog(JSON.parse(Buffer.from(bytes).toString('utf8')));
  return {
    envelope: {
      schema_version: 'media-app-catalog-cache/2',
      saved_at: value.saved_at,
      hash: value.hash,
      size: value.size,
      payload_base64: value.payload_base64,
    },
    catalog,
  };
}

function validateDetailEnvelope(value: unknown, expectedMediaId: string): MediaDetailCacheEnvelope {
  if (!isRecord(value) || value.schema_version !== 'media-app-detail-cache/2') {
    throw new Error('MEDIA_DETAIL_CACHE_ENVELOPE_INVALID');
  }
  if (
    typeof value.saved_at !== 'string'
    || typeof value.media_id !== 'string'
    || value.media_id !== expectedMediaId
    || (value.content_kind !== 'movie' && value.content_kind !== 'series')
    || typeof value.detail_hash !== 'string'
    || !SHA256_RE.test(value.detail_hash)
  ) {
    throw new Error('MEDIA_DETAIL_CACHE_ENVELOPE_INVALID');
  }
  const contentKind = value.content_kind as MediaKind;
  const item = parseResourceFeedItem(value.item, contentKind, false);
  if (
    item.movie_id !== expectedMediaId
    || item.remote_detail_hash !== value.detail_hash
    || item.resources.length === 0
  ) {
    throw new Error('MEDIA_DETAIL_CACHE_IDENTITY_MISMATCH');
  }
  return {
    schema_version: 'media-app-detail-cache/2',
    saved_at: value.saved_at,
    media_id: expectedMediaId,
    content_kind: contentKind,
    detail_hash: value.detail_hash,
    item,
  };
}

function identityFromLegacy(state: LegacyMediaCacheState): MediaPointerIdentity {
  return {
    pointer_revision: state.pointer_revision,
    pointer_sha256: state.pointer_sha256,
    release_id: state.release_id,
    manifest_sha256: state.manifest_sha256,
  };
}

async function writeIndex(index: MediaCacheIndex): Promise<void> {
  await writeJsonAtomically(CACHE_ROOT, INDEX_NAME, index);
  memoryIndex = index;
}

async function writeFeedEnvelope(kind: MediaKind, envelope: MediaFeedCacheEnvelope): Promise<void> {
  await writeJsonAtomically(FEED_DIR, `${kind}.json`, envelope);
  memoryFeeds[kind] = envelope.feed;
  memoryFeedIdentities[kind] = envelope.identity;
  loadedFeedKinds.add(kind);
}

async function writeDetailEnvelope(envelope: MediaDetailCacheEnvelope): Promise<void> {
  const name = `${mediaIdCacheKey(envelope.media_id)}.json`;
  await writeJsonAtomically(DETAIL_DIR, name, envelope);
  memoryDetails.set(envelope.media_id, envelope.item);
  missingDetails.delete(envelope.media_id);
}

async function migrateLegacyCache(): Promise<void> {
  ensureDirectories();
  const marker = migrationMarkerFile();
  if (marker.exists) return;

  let migrated = false;
  if (legacyMediaCacheExists()) {
    const legacy = await readLegacyMediaCache();
    if (legacy) {
      const identity = identityFromLegacy(legacy);
      assertMediaPointerTransition(identity, null);
      const index: MediaCacheIndex = {
        schema_version: 'media-app-cache-index/2',
        updated_at: new Date().toISOString(),
        endpoint: legacy.endpoint,
        identity,
      };
      for (const kind of ['movie', 'series'] as const) {
        const rawFeed = legacy.feeds[kind];
        if (!rawFeed) continue;
        try {
          const feed = parseResourceFeed(rawFeed, {
            requireOfflineCover: false,
            allowResourceCountHints: true,
          });
          await writeFeedEnvelope(kind, {
            schema_version: 'media-app-feed-cache/2',
            saved_at: legacy.saved_at,
            endpoint: legacy.endpoint,
            identity,
            feed,
          });
        } catch (error) {
          logCacheFailure('migrate_legacy_feed', 'LEGACY_MEDIA_FEED_MIGRATION_FAILED', error, {
            content_kind: kind,
          });
        }
      }
      for (const [mediaId, rawItem] of Object.entries(legacy.details)) {
        try {
          const item = parseResourceFeedItem(rawItem, rawItem.content_kind, false);
          if (!item.remote_detail_hash || !SHA256_RE.test(item.remote_detail_hash) || item.resources.length === 0) {
            continue;
          }
          await writeDetailEnvelope({
            schema_version: 'media-app-detail-cache/2',
            saved_at: legacy.saved_at,
            media_id: mediaId,
            content_kind: item.content_kind,
            detail_hash: item.remote_detail_hash,
            item,
          });
        } catch (error) {
          logCacheFailure('migrate_legacy_detail', 'LEGACY_MEDIA_DETAIL_MIGRATION_FAILED', error, {
            media_id: mediaId,
          });
        }
      }
      await writeIndex(index);
      migrated = true;
    }
    await deleteLegacyMediaCache();
  }

  const migrationMarker: MigrationMarker = {
    schema_version: 'media-app-cache-migration/1',
    completed_at: new Date().toISOString(),
    migrated,
  };
  await writeJsonAtomically(CACHE_ROOT, MIGRATION_MARKER_NAME, migrationMarker);
}

async function ensureMigrated(): Promise<void> {
  if (!migrationPromise) {
    migrationPromise = migrateLegacyCache().catch((error) => {
      migrationPromise = null;
      logCacheFailure('migrate_legacy_cache', 'LEGACY_MEDIA_CACHE_MIGRATION_FAILED', error);
      throw error;
    });
  }
  return migrationPromise;
}

async function loadIndex(): Promise<MediaCacheIndex | null> {
  await ensureMigrated();
  if (memoryIndex !== undefined) return memoryIndex;
  if (!jsonShardExists(CACHE_ROOT, INDEX_NAME)) {
    memoryIndex = null;
    return null;
  }
  try {
    memoryIndex = validateIndex(await readJsonResilient(CACHE_ROOT, INDEX_NAME));
    return memoryIndex;
  } catch (error) {
    logCacheFailure('load_index', 'MEDIA_CACHE_INDEX_READ_FAILED', error);
    deleteJsonShard(CACHE_ROOT, INDEX_NAME);
    memoryIndex = null;
    return null;
  }
}

export async function cachedMediaPointerIdentity(): Promise<MediaPointerIdentity | null> {
  const index = await loadIndex();
  return index?.identity ?? null;
}

export async function saveMediaFeeds(
  identity: MediaPointerIdentity,
  endpoint: string,
  feeds: Partial<Record<MediaKind, MovieFeed>>,
): Promise<void> {
  await ensureMigrated();
  const existing = await loadIndex();
  assertMediaPointerTransition(identity, existing?.identity ?? null);

  for (const kind of ['movie', 'series'] as const) {
    const rawFeed = feeds[kind];
    if (!rawFeed) continue;
    const feed = parseResourceFeed(rawFeed, {
      requireOfflineCover: false,
      allowResourceCountHints: true,
    });
    if (feed.content_kind !== kind) throw new Error('MEDIA_FEED_CACHE_KIND_MISMATCH');
    await writeFeedEnvelope(kind, {
      schema_version: 'media-app-feed-cache/2',
      saved_at: new Date().toISOString(),
      endpoint,
      identity,
      feed,
    });
  }

  await writeIndex({
    schema_version: 'media-app-cache-index/2',
    updated_at: new Date().toISOString(),
    endpoint,
    identity,
  });
}

export async function cachedMediaFeed(kind: MediaKind): Promise<MovieFeed | null> {
  await ensureMigrated();
  if (loadedFeedKinds.has(kind)) return memoryFeeds[kind] ?? null;
  const name = `${kind}.json`;
  loadedFeedKinds.add(kind);
  if (!jsonShardExists(FEED_DIR, name)) {
    memoryFeeds[kind] = null;
    memoryFeedIdentities[kind] = null;
    return null;
  }
  try {
    const envelope = validateFeedEnvelope(await readJsonResilient(FEED_DIR, name), kind);
    memoryFeeds[kind] = envelope.feed;
    memoryFeedIdentities[kind] = envelope.identity;
    return envelope.feed;
  } catch (error) {
    logCacheFailure('load_feed', 'MEDIA_FEED_CACHE_READ_FAILED', error, {
      content_kind: kind,
    });
    deleteJsonShard(FEED_DIR, name);
    memoryFeeds[kind] = null;
    memoryFeedIdentities[kind] = null;
    return null;
  }
}

export async function cachedMediaFeedIdentity(kind: MediaKind): Promise<MediaPointerIdentity | null> {
  await cachedMediaFeed(kind);
  return memoryFeedIdentities[kind] ?? null;
}

export async function cachedMediaCatalog(ref: MediaObjectRef): Promise<MediaCatalog | null> {
  await ensureMigrated();
  const inMemory = memoryCatalogs.get(ref.hash);
  if (inMemory) return inMemory;
  if (missingCatalogs.has(ref.hash)) return null;

  const name = `${ref.hash}.json`;
  if (!jsonShardExists(CATALOG_DIR, name)) {
    missingCatalogs.add(ref.hash);
    return null;
  }
  try {
    const { catalog } = validateCatalogEnvelope(
      await readJsonResilient(CATALOG_DIR, name),
      ref,
    );
    memoryCatalogs.set(ref.hash, catalog);
    return catalog;
  } catch (error) {
    logCacheFailure('load_catalog', 'MEDIA_CATALOG_CACHE_READ_FAILED', error, {
      hash: ref.hash,
      path: ref.path,
    });
    deleteJsonShard(CATALOG_DIR, name);
    missingCatalogs.add(ref.hash);
    return null;
  }
}

export async function saveMediaCatalog(ref: MediaObjectRef, bytes: Uint8Array): Promise<void> {
  await ensureMigrated();
  if (bytes.byteLength !== ref.size || sha256Hex(bytes) !== ref.hash) {
    throw new Error('MEDIA_CATALOG_CACHE_HASH_OR_SIZE_MISMATCH');
  }
  const catalog = parseCatalog(JSON.parse(Buffer.from(bytes).toString('utf8')));
  try {
    await writeJsonAtomically(CATALOG_DIR, `${ref.hash}.json`, {
      schema_version: 'media-app-catalog-cache/2',
      saved_at: new Date().toISOString(),
      hash: ref.hash,
      size: ref.size,
      payload_base64: Buffer.from(bytes).toString('base64'),
    } satisfies MediaCatalogCacheEnvelope);
    memoryCatalogs.set(ref.hash, catalog);
    missingCatalogs.delete(ref.hash);
  } catch (error) {
    logCacheFailure('save_catalog', 'MEDIA_CATALOG_CACHE_SAVE_FAILED', error, {
      hash: ref.hash,
      path: ref.path,
    });
  }
}

function mergeCachedDetail(
  currentItem: MovieFeedItem,
  cachedItem: MovieFeedItem,
): MovieFeedItem {
  return {
    ...currentItem,
    ...cachedItem,
    rank: currentItem.rank,
    recommended: currentItem.recommended,
    highlight_labels: currentItem.highlight_labels,
    quality_tags: currentItem.quality_tags,
    resource_count_hint: cachedItem.resources.length,
    remote_cover_url: currentItem.remote_cover_url ?? cachedItem.remote_cover_url,
    remote_endpoint: currentItem.remote_endpoint ?? cachedItem.remote_endpoint,
    remote_release_id: currentItem.remote_release_id ?? cachedItem.remote_release_id,
    remote_detail_path: currentItem.remote_detail_path ?? cachedItem.remote_detail_path,
    remote_detail_hash: currentItem.remote_detail_hash ?? cachedItem.remote_detail_hash,
    remote_detail_size: currentItem.remote_detail_size ?? cachedItem.remote_detail_size,
  };
}

export async function cachedMediaDetail(currentItem: MovieFeedItem): Promise<MovieFeedItem | null> {
  await ensureMigrated();
  if (!currentItem.remote_detail_hash || !SHA256_RE.test(currentItem.remote_detail_hash)) return null;

  const inMemory = memoryDetails.get(currentItem.movie_id);
  if (inMemory) {
    return inMemory.remote_detail_hash === currentItem.remote_detail_hash
      ? mergeCachedDetail(currentItem, inMemory)
      : null;
  }
  if (missingDetails.has(currentItem.movie_id)) return null;

  const name = `${mediaIdCacheKey(currentItem.movie_id)}.json`;
  if (!jsonShardExists(DETAIL_DIR, name)) {
    missingDetails.add(currentItem.movie_id);
    return null;
  }
  try {
    const envelope = validateDetailEnvelope(
      await readJsonResilient(DETAIL_DIR, name),
      currentItem.movie_id,
    );
    memoryDetails.set(currentItem.movie_id, envelope.item);
    if (envelope.detail_hash !== currentItem.remote_detail_hash) return null;
    return mergeCachedDetail(currentItem, envelope.item);
  } catch (error) {
    logCacheFailure('load_detail', 'MEDIA_DETAIL_CACHE_READ_FAILED', error, {
      media_id: currentItem.movie_id,
      content_kind: currentItem.content_kind,
    });
    deleteJsonShard(DETAIL_DIR, name);
    missingDetails.add(currentItem.movie_id);
    return null;
  }
}

export async function saveMediaDetail(item: MovieFeedItem): Promise<void> {
  await ensureMigrated();
  if (!item.remote_detail_hash || !SHA256_RE.test(item.remote_detail_hash) || item.resources.length === 0) {
    return;
  }
  try {
    const validated = parseResourceFeedItem(item, item.content_kind, false);
    await writeDetailEnvelope({
      schema_version: 'media-app-detail-cache/2',
      saved_at: new Date().toISOString(),
      media_id: validated.movie_id,
      content_kind: validated.content_kind,
      detail_hash: item.remote_detail_hash,
      item: validated,
    });
  } catch (error) {
    logCacheFailure('save_detail', 'MEDIA_DETAIL_CACHE_SAVE_FAILED', error, {
      media_id: item.movie_id,
      content_kind: item.content_kind,
    });
  }
}

export function clearMediaCacheMemory() {
  memoryIndex = undefined;
  delete memoryFeeds.movie;
  delete memoryFeeds.series;
  delete memoryFeedIdentities.movie;
  delete memoryFeedIdentities.series;
  loadedFeedKinds.clear();
  memoryCatalogs.clear();
  missingCatalogs.clear();
  memoryDetails.clear();
  missingDetails.clear();
}
