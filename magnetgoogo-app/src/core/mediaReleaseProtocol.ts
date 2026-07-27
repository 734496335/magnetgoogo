import { Buffer } from 'buffer';
import CryptoJS from 'crypto-js';
import nacl from 'tweetnacl';

const MEDIA_PUBLIC_KEY_BASE64 = '94eLTKi0Gz1RIQEssMSHrk1ND5WRjdIWzQqjAhrsCb4=';
const MEDIA_SIGNATURE_KEY_ID = 'media-ed25519-339487293160';
const SHA256_RE = /^[0-9a-f]{64}$/;

export interface MediaObjectRef {
  path: string;
  hash: string;
  size: number;
  count?: number;
  page?: number;
}

export interface MediaCurrentPointer {
  schema_version: 'media-current/1';
  pointer_revision: number;
  release_id: string;
  manifest_path: string;
  manifest_sha256: string;
  published_at: string;
  min_app_version: string;
  signature_key_id: string;
  signature: string;
}

export interface MediaPointerIdentity {
  pointer_revision: number;
  pointer_sha256: string;
  release_id: string;
  manifest_sha256: string;
}

export interface MediaCurrentCandidate extends MediaPointerIdentity {
  endpoint: string;
  pointer: MediaCurrentPointer;
}

export interface MediaManifestChannel {
  featured?: MediaObjectRef;
  updating?: MediaObjectRef;
  latest_pages: MediaObjectRef[];
}

export interface MediaManifest {
  schema_version: 'media-manifest/1';
  release_id: string;
  generated_at: string;
  signature_key_id: string;
  signature: string;
  channels: Record<string, MediaManifestChannel>;
  counts: {
    movie: number;
    series: number;
    resources: number;
    covers: number;
    details: number;
    catalog_objects: number;
  };
}

export interface MediaCatalogCard {
  media_id: string;
  content_kind: 'movie' | 'series';
  title: string;
  original_title?: string | null;
  year?: number | null;
  update_date?: string | null;
  countries: string[];
  genres: string[];
  imdb_rating?: number | null;
  douban_rating?: number | null;
  recommended: boolean;
  highlight_labels: string[];
  quality_tags: string[];
  resource_count: number;
  season_number?: number | null;
  episode_number?: number | null;
  episode_label?: string | null;
  update_status?: string | null;
  cover: MediaObjectRef & { mime_type?: string };
  detail_object: MediaObjectRef;
}

export interface MediaCatalog {
  schema_version: 'media-catalog/1';
  channel: string;
  role: 'featured' | 'updating' | 'latest';
  page: number | null;
  count: number;
  items: MediaCatalogCard[];
}

export interface MediaDetail {
  schema_version: 'media-detail/1';
  media_id: string;
  content_kind: 'movie' | 'series';
  title: string;
  original_title?: string | null;
  year?: number | null;
  release_date?: string | null;
  duration_minutes?: number | null;
  countries: string[];
  genres: string[];
  languages: string[];
  directors: string[];
  actors: string[];
  imdb_id?: string | null;
  imdb_rating?: number | null;
  imdb_rating_text?: string | null;
  douban_rating?: number | null;
  douban_rating_text?: string | null;
  douban_url?: string | null;
  synopsis?: string | null;
  resource_object: MediaObjectRef & { encrypted: boolean };
}

export interface MediaResourceItem {
  resource_type: 'magnet' | 'cloud';
  provider: string;
  url: string;
  info_hash?: string | null;
  display_title: string;
  extraction_code?: string | null;
  quality_tags: string[];
}

export interface MediaResources {
  schema_version: 'media-resources/1';
  media_id: string;
  items: MediaResourceItem[];
}

export class MediaReleaseValidationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'MediaReleaseValidationError';
    this.code = code;
  }
}

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key];
  if (typeof value !== 'string' || !value.trim()) {
    throw new MediaReleaseValidationError('INVALID_STRING', `${context}.${key} must be non-empty string`);
  }
  return value.trim();
}

function nullableString(record: Record<string, unknown>, key: string, context: string): string | null {
  const value = record[key];
  if (value === null || value === undefined || value === '') return null;
  if (typeof value !== 'string') {
    throw new MediaReleaseValidationError('INVALID_NULLABLE_STRING', `${context}.${key} must be string or null`);
  }
  return value.trim() || null;
}

function integer(record: Record<string, unknown>, key: string, context: string, minimum = 0): number {
  const value = record[key];
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new MediaReleaseValidationError('INVALID_INTEGER', `${context}.${key} must be integer >= ${minimum}`);
  }
  return value as number;
}

function nullableInteger(record: Record<string, unknown>, key: string, context: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new MediaReleaseValidationError('INVALID_NULLABLE_INTEGER', `${context}.${key} must be integer or null`);
  }
  return value as number;
}

function nullableNumber(record: Record<string, unknown>, key: string, context: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new MediaReleaseValidationError('INVALID_NULLABLE_NUMBER', `${context}.${key} must be number or null`);
  }
  return value;
}

function stringArray(value: unknown, context: string): string[] {
  if (!Array.isArray(value)) {
    throw new MediaReleaseValidationError('INVALID_STRING_ARRAY', `${context} must be array`);
  }
  return value.map((entry, index) => {
    if (typeof entry !== 'string' || !entry.trim()) {
      throw new MediaReleaseValidationError('INVALID_STRING_ARRAY_ITEM', `${context}[${index}] must be string`);
    }
    return entry.trim();
  });
}

function safePath(value: unknown, context: string): string {
  if (typeof value !== 'string' || !value.startsWith('/v1/') || value.includes('\\')) {
    throw new MediaReleaseValidationError('INVALID_MEDIA_PATH', `${context} must be a /v1/ path`);
  }
  const parts = value.split('/').filter(Boolean);
  if (parts.some((part) => part === '.' || part === '..')) {
    throw new MediaReleaseValidationError('INVALID_MEDIA_PATH', `${context} contains unsafe path component`);
  }
  return `/${parts.join('/')}`;
}

function objectRef(value: unknown, context: string): MediaObjectRef {
  if (!isRecord(value)) {
    throw new MediaReleaseValidationError('INVALID_OBJECT_REF', `${context} must be object`);
  }
  const hash = requiredString(value, 'hash', context).toLowerCase();
  if (!SHA256_RE.test(hash)) {
    throw new MediaReleaseValidationError('INVALID_SHA256', `${context}.hash is invalid`);
  }
  return {
    path: safePath(value.path, `${context}.path`),
    hash,
    size: integer(value, 'size', context),
    count: value.count === undefined ? undefined : integer(value, 'count', context),
    page: value.page === undefined ? undefined : integer(value, 'page', context, 1),
  };
}

function canonicalize(value: JsonValue): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(',')}]`;
  }
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`).join(',')}}`;
}

export function canonicalJson(value: unknown): string {
  return canonicalize(value as JsonValue);
}

function unsignedDocument(document: Record<string, unknown>): Record<string, unknown> {
  const result = { ...document };
  delete result.signature;
  return result;
}

export function verifySignedMediaDocument(document: Record<string, unknown>): void {
  const keyId = requiredString(document, 'signature_key_id', 'document');
  const signature = requiredString(document, 'signature', 'document');
  if (keyId !== MEDIA_SIGNATURE_KEY_ID) {
    throw new MediaReleaseValidationError('SIGNATURE_KEY_MISMATCH', 'media signature key ID is not trusted');
  }
  const message = Buffer.from(canonicalJson(unsignedDocument(document)), 'utf8');
  const signatureBytes = Buffer.from(signature, 'base64');
  const publicKey = Buffer.from(MEDIA_PUBLIC_KEY_BASE64, 'base64');
  if (signatureBytes.length !== nacl.sign.signatureLength || publicKey.length !== nacl.sign.publicKeyLength) {
    throw new MediaReleaseValidationError('INVALID_SIGNATURE_BYTES', 'media signature bytes are invalid');
  }
  if (!nacl.sign.detached.verify(message, signatureBytes, publicKey)) {
    throw new MediaReleaseValidationError('SIGNATURE_INVALID', 'media Ed25519 signature verification failed');
  }
}

function wordArrayFromBytes(bytes: Uint8Array): CryptoJS.lib.WordArray {
  const words: number[] = [];
  for (let index = 0; index < bytes.length; index += 1) {
    words[index >>> 2] = (words[index >>> 2] || 0) | (bytes[index] << (24 - (index % 4) * 8));
  }
  return CryptoJS.lib.WordArray.create(words, bytes.length);
}

export function sha256Hex(bytes: Uint8Array): string {
  return CryptoJS.SHA256(wordArrayFromBytes(bytes)).toString(CryptoJS.enc.Hex);
}

function validatePointerIdentity(identity: MediaPointerIdentity, context: string): void {
  if (!Number.isInteger(identity.pointer_revision) || identity.pointer_revision < 1) {
    throw new MediaReleaseValidationError('MEDIA_POINTER_IDENTITY_INVALID', `${context}.pointer_revision is invalid`);
  }
  if (!SHA256_RE.test(identity.pointer_sha256) || !SHA256_RE.test(identity.manifest_sha256)) {
    throw new MediaReleaseValidationError('MEDIA_POINTER_IDENTITY_INVALID', `${context} hash is invalid`);
  }
  if (!identity.release_id) {
    throw new MediaReleaseValidationError('MEDIA_POINTER_IDENTITY_INVALID', `${context}.release_id is invalid`);
  }
}

export function mediaPointerIdentity(candidate: MediaCurrentCandidate): MediaPointerIdentity {
  const identity: MediaPointerIdentity = {
    pointer_revision: candidate.pointer.pointer_revision,
    pointer_sha256: candidate.pointer_sha256,
    release_id: candidate.pointer.release_id,
    manifest_sha256: candidate.pointer.manifest_sha256,
  };
  validatePointerIdentity(identity, 'candidate');
  return identity;
}

export function assertMediaPointerTransition(
  candidate: MediaPointerIdentity,
  accepted: MediaPointerIdentity | null,
): void {
  validatePointerIdentity(candidate, 'candidate');
  if (!accepted) return;
  validatePointerIdentity(accepted, 'accepted');
  if (candidate.pointer_revision < accepted.pointer_revision) {
    throw new MediaReleaseValidationError(
      'MEDIA_POINTER_ROLLBACK_REJECTED',
      `media pointer revision ${candidate.pointer_revision} is older than accepted revision ${accepted.pointer_revision}`,
    );
  }
  if (candidate.pointer_revision === accepted.pointer_revision) {
    const sameIdentity = candidate.pointer_sha256 === accepted.pointer_sha256
      && candidate.release_id === accepted.release_id
      && candidate.manifest_sha256 === accepted.manifest_sha256;
    if (!sameIdentity) {
      throw new MediaReleaseValidationError(
        'MEDIA_POINTER_SAME_REVISION_CONFLICT',
        `media pointer revision ${candidate.pointer_revision} conflicts with the accepted identity`,
      );
    }
  }
}

export function selectMediaCurrentCandidate(
  candidates: MediaCurrentCandidate[],
  accepted: MediaPointerIdentity | null = null,
): MediaCurrentCandidate {
  if (!candidates.length) {
    throw new MediaReleaseValidationError('MEDIA_CURRENT_UNAVAILABLE', 'no valid media current candidate is available');
  }
  candidates.forEach((candidate, index) => {
    if (!candidate.endpoint) {
      throw new MediaReleaseValidationError('MEDIA_POINTER_IDENTITY_INVALID', `candidate[${index}].endpoint is invalid`);
    }
    validatePointerIdentity(mediaPointerIdentity(candidate), `candidate[${index}]`);
  });
  const highestRevision = Math.max(...candidates.map((candidate) => candidate.pointer.pointer_revision));
  const highest = candidates.filter((candidate) => candidate.pointer.pointer_revision === highestRevision);
  const fingerprints = new Set(highest.map((candidate) => candidate.pointer_sha256));
  if (fingerprints.size !== 1) {
    throw new MediaReleaseValidationError(
      'MEDIA_POINTER_SAME_REVISION_CONFLICT',
      `media endpoints disagree on revision ${highestRevision}`,
    );
  }
  const winner = highest[0];
  assertMediaPointerTransition(mediaPointerIdentity(winner), accepted);
  return winner;
}

export function parseCurrentPointer(value: unknown): MediaCurrentPointer {
  if (!isRecord(value) || value.schema_version !== 'media-current/1') {
    throw new MediaReleaseValidationError('INVALID_CURRENT', 'media current pointer schema mismatch');
  }
  verifySignedMediaDocument(value);
  const manifestHash = requiredString(value, 'manifest_sha256', 'current').toLowerCase();
  if (!SHA256_RE.test(manifestHash)) {
    throw new MediaReleaseValidationError('INVALID_SHA256', 'current.manifest_sha256 is invalid');
  }
  return {
    schema_version: 'media-current/1',
    pointer_revision: integer(value, 'pointer_revision', 'current', 1),
    release_id: requiredString(value, 'release_id', 'current'),
    manifest_path: safePath(value.manifest_path, 'current.manifest_path'),
    manifest_sha256: manifestHash,
    published_at: requiredString(value, 'published_at', 'current'),
    min_app_version: requiredString(value, 'min_app_version', 'current'),
    signature_key_id: requiredString(value, 'signature_key_id', 'current'),
    signature: requiredString(value, 'signature', 'current'),
  };
}

export function parseManifest(value: unknown): MediaManifest {
  if (!isRecord(value) || value.schema_version !== 'media-manifest/1') {
    throw new MediaReleaseValidationError('INVALID_MANIFEST', 'media manifest schema mismatch');
  }
  verifySignedMediaDocument(value);
  if (!isRecord(value.channels) || !isRecord(value.counts)) {
    throw new MediaReleaseValidationError('INVALID_MANIFEST', 'media manifest channels/counts are invalid');
  }
  const channels: Record<string, MediaManifestChannel> = {};
  Object.entries(value.channels).forEach(([name, raw]) => {
    if (!isRecord(raw) || !Array.isArray(raw.latest_pages)) {
      throw new MediaReleaseValidationError('INVALID_CHANNEL', `manifest.channels.${name} is invalid`);
    }
    channels[name] = {
      featured: raw.featured === undefined ? undefined : objectRef(raw.featured, `channels.${name}.featured`),
      updating: raw.updating === undefined ? undefined : objectRef(raw.updating, `channels.${name}.updating`),
      latest_pages: raw.latest_pages.map((item, index) => objectRef(item, `channels.${name}.latest_pages[${index}]`)),
    };
  });
  return {
    schema_version: 'media-manifest/1',
    release_id: requiredString(value, 'release_id', 'manifest'),
    generated_at: requiredString(value, 'generated_at', 'manifest'),
    signature_key_id: requiredString(value, 'signature_key_id', 'manifest'),
    signature: requiredString(value, 'signature', 'manifest'),
    channels,
    counts: {
      movie: integer(value.counts, 'movie', 'counts'),
      series: integer(value.counts, 'series', 'counts'),
      resources: integer(value.counts, 'resources', 'counts'),
      covers: integer(value.counts, 'covers', 'counts'),
      details: integer(value.counts, 'details', 'counts'),
      catalog_objects: integer(value.counts, 'catalog_objects', 'counts'),
    },
  };
}

export function parseCatalog(value: unknown): MediaCatalog {
  if (!isRecord(value) || value.schema_version !== 'media-catalog/1' || !Array.isArray(value.items)) {
    throw new MediaReleaseValidationError('INVALID_CATALOG', 'media catalog schema mismatch');
  }
  const role = requiredString(value, 'role', 'catalog');
  if (role !== 'featured' && role !== 'updating' && role !== 'latest') {
    throw new MediaReleaseValidationError('INVALID_CATALOG_ROLE', 'media catalog role is invalid');
  }
  const items = value.items.map((raw, index): MediaCatalogCard => {
    if (!isRecord(raw)) {
      throw new MediaReleaseValidationError('INVALID_CATALOG_CARD', `catalog.items[${index}] is invalid`);
    }
    const kind = requiredString(raw, 'content_kind', `catalog.items[${index}]`);
    if (kind !== 'movie' && kind !== 'series') {
      throw new MediaReleaseValidationError('INVALID_CONTENT_KIND', `catalog.items[${index}].content_kind is invalid`);
    }
    const cover = objectRef(raw.cover, `catalog.items[${index}].cover`);
    const detail = objectRef(raw.detail_object, `catalog.items[${index}].detail_object`);
    return {
      media_id: requiredString(raw, 'media_id', `catalog.items[${index}]`),
      content_kind: kind,
      title: requiredString(raw, 'title', `catalog.items[${index}]`),
      original_title: nullableString(raw, 'original_title', `catalog.items[${index}]`),
      year: nullableInteger(raw, 'year', `catalog.items[${index}]`),
      update_date: nullableString(raw, 'update_date', `catalog.items[${index}]`),
      countries: stringArray(raw.countries, `catalog.items[${index}].countries`),
      genres: stringArray(raw.genres, `catalog.items[${index}].genres`),
      imdb_rating: nullableNumber(raw, 'imdb_rating', `catalog.items[${index}]`),
      douban_rating: nullableNumber(raw, 'douban_rating', `catalog.items[${index}]`),
      recommended: raw.recommended === true,
      highlight_labels: stringArray(raw.highlight_labels, `catalog.items[${index}].highlight_labels`),
      quality_tags: stringArray(raw.quality_tags, `catalog.items[${index}].quality_tags`),
      resource_count: integer(raw, 'resource_count', `catalog.items[${index}]`),
      season_number: nullableInteger(raw, 'season_number', `catalog.items[${index}]`),
      episode_number: nullableInteger(raw, 'episode_number', `catalog.items[${index}]`),
      episode_label: nullableString(raw, 'episode_label', `catalog.items[${index}]`),
      update_status: nullableString(raw, 'update_status', `catalog.items[${index}]`),
      cover: { ...cover, mime_type: nullableString(raw.cover as Record<string, unknown>, 'mime_type', `catalog.items[${index}].cover`) ?? undefined },
      detail_object: detail,
    };
  });
  const count = integer(value, 'count', 'catalog');
  if (count !== items.length) {
    throw new MediaReleaseValidationError('CATALOG_COUNT_MISMATCH', 'catalog count does not match items');
  }
  return {
    schema_version: 'media-catalog/1',
    channel: requiredString(value, 'channel', 'catalog'),
    role,
    page: nullableInteger(value, 'page', 'catalog'),
    count,
    items,
  };
}

export function parseDetail(value: unknown): MediaDetail {
  if (!isRecord(value) || value.schema_version !== 'media-detail/1') {
    throw new MediaReleaseValidationError('INVALID_DETAIL', 'media detail schema mismatch');
  }
  const kind = requiredString(value, 'content_kind', 'detail');
  if (kind !== 'movie' && kind !== 'series') {
    throw new MediaReleaseValidationError('INVALID_CONTENT_KIND', 'detail.content_kind is invalid');
  }
  const resourceRef = objectRef(value.resource_object, 'detail.resource_object');
  const encrypted = isRecord(value.resource_object) && value.resource_object.encrypted === true;
  return {
    schema_version: 'media-detail/1',
    media_id: requiredString(value, 'media_id', 'detail'),
    content_kind: kind,
    title: requiredString(value, 'title', 'detail'),
    original_title: nullableString(value, 'original_title', 'detail'),
    year: nullableInteger(value, 'year', 'detail'),
    release_date: nullableString(value, 'release_date', 'detail'),
    duration_minutes: nullableInteger(value, 'duration_minutes', 'detail'),
    countries: stringArray(value.countries, 'detail.countries'),
    genres: stringArray(value.genres, 'detail.genres'),
    languages: stringArray(value.languages, 'detail.languages'),
    directors: stringArray(value.directors, 'detail.directors'),
    actors: stringArray(value.actors, 'detail.actors'),
    imdb_id: nullableString(value, 'imdb_id', 'detail'),
    imdb_rating: nullableNumber(value, 'imdb_rating', 'detail'),
    imdb_rating_text: nullableString(value, 'imdb_rating_text', 'detail'),
    douban_rating: nullableNumber(value, 'douban_rating', 'detail'),
    douban_rating_text: nullableString(value, 'douban_rating_text', 'detail'),
    douban_url: nullableString(value, 'douban_url', 'detail'),
    synopsis: nullableString(value, 'synopsis', 'detail'),
    resource_object: { ...resourceRef, encrypted },
  };
}

export function parseResources(value: unknown): MediaResources {
  if (!isRecord(value) || value.schema_version !== 'media-resources/1' || !Array.isArray(value.items)) {
    throw new MediaReleaseValidationError('INVALID_RESOURCES', 'media resources schema mismatch');
  }
  return {
    schema_version: 'media-resources/1',
    media_id: requiredString(value, 'media_id', 'resources'),
    items: value.items.map((raw, index): MediaResourceItem => {
      if (!isRecord(raw)) {
        throw new MediaReleaseValidationError('INVALID_RESOURCE', `resources.items[${index}] is invalid`);
      }
      const type = requiredString(raw, 'resource_type', `resources.items[${index}]`);
      if (type !== 'magnet' && type !== 'cloud') {
        throw new MediaReleaseValidationError('INVALID_RESOURCE_TYPE', `resources.items[${index}].resource_type is invalid`);
      }
      return {
        resource_type: type,
        provider: requiredString(raw, 'provider', `resources.items[${index}]`),
        url: requiredString(raw, 'url', `resources.items[${index}]`),
        info_hash: nullableString(raw, 'info_hash', `resources.items[${index}]`),
        display_title: requiredString(raw, 'display_title', `resources.items[${index}]`),
        extraction_code: nullableString(raw, 'extraction_code', `resources.items[${index}]`),
        quality_tags: stringArray(raw.quality_tags, `resources.items[${index}].quality_tags`),
      };
    }),
  };
}
