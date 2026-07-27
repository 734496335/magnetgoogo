import { Buffer } from 'buffer';
import CryptoJS from 'crypto-js';
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { Directory, File, Paths } from 'expo-file-system';
import {
  assertMediaPointerTransition,
  type MediaPointerIdentity,
} from './mediaReleaseProtocol';
import type { MediaKind, MovieFeed, MovieFeedItem } from './resourceFeedProtocol';

const CACHE_KEY_NAME = 'mg_media_cache_key_v1';
const CACHE_VERSION = 1;
const CACHE_EXPIRY_MS = 72 * 60 * 60 * 1000;
const CACHE_DIR = new Directory(Paths.document, 'media-release-cache');
const CACHE_PRIMARY_NAME = 'media.cache.enc.json';
const CACHE_BACKUP_NAME = 'media.cache.backup.enc.json';
const SHA256_RE = /^[0-9a-f]{64}$/;

export interface MediaCacheState {
  schema_version: 'media-app-cache/1';
  saved_at: string;
  release_id: string;
  pointer_revision: number;
  pointer_sha256: string;
  manifest_sha256: string;
  endpoint: string;
  feeds: Partial<Record<MediaKind, MovieFeed>>;
  details: Record<string, MovieFeedItem>;
}

interface EncryptedCacheEnvelope {
  version: 1;
  iv: string;
  ciphertext: string;
  mac: string;
}

let memoryState: MediaCacheState | null = null;

function cacheFile(name: string): File {
  return new File(CACHE_DIR, name);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function logCacheFailure(stage: string, errorCode: string, error: unknown) {
  console.warn('[MediaReleaseCache]', {
    stage,
    error_code: errorCode,
    error: error instanceof Error ? error.message : String(error),
  });
}

function wordArrayFromBytes(bytes: Uint8Array): CryptoJS.lib.WordArray {
  const words: number[] = [];
  for (let index = 0; index < bytes.length; index += 1) {
    words[index >>> 2] = (words[index >>> 2] || 0) | (bytes[index] << (24 - (index % 4) * 8));
  }
  return CryptoJS.lib.WordArray.create(words, bytes.length);
}

async function cacheKeyBytes(): Promise<Uint8Array> {
  const stored = await SecureStore.getItemAsync(CACHE_KEY_NAME);
  if (stored) {
    const parsed = Uint8Array.from(Buffer.from(stored, 'base64'));
    if (parsed.length === 64) return parsed;
  }
  const generated = await Crypto.getRandomBytesAsync(64);
  await SecureStore.setItemAsync(CACHE_KEY_NAME, Buffer.from(generated).toString('base64'));
  return generated;
}

function splitKeys(bytes: Uint8Array): { aes: CryptoJS.lib.WordArray; mac: CryptoJS.lib.WordArray } {
  return {
    aes: wordArrayFromBytes(bytes.slice(0, 32)),
    mac: wordArrayFromBytes(bytes.slice(32, 64)),
  };
}

function constantTimeHexEqual(left: string, right: string): boolean {
  if (left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) {
    mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return mismatch === 0;
}

function stateIdentity(state: MediaCacheState): MediaPointerIdentity {
  return {
    pointer_revision: state.pointer_revision,
    pointer_sha256: state.pointer_sha256,
    release_id: state.release_id,
    manifest_sha256: state.manifest_sha256,
  };
}

function validateState(value: unknown): MediaCacheState {
  if (!isRecord(value) || value.schema_version !== 'media-app-cache/1') {
    throw new Error('MEDIA_CACHE_STATE_INVALID');
  }
  const savedAt = typeof value.saved_at === 'string' ? new Date(value.saved_at).getTime() : Number.NaN;
  if (!Number.isFinite(savedAt) || Date.now() - savedAt > CACHE_EXPIRY_MS || savedAt - Date.now() > 5 * 60 * 1000) {
    throw new Error('MEDIA_CACHE_EXPIRED');
  }
  if (
    typeof value.release_id !== 'string'
    || !value.release_id
    || !Number.isInteger(value.pointer_revision)
    || (value.pointer_revision as number) < 1
    || typeof value.pointer_sha256 !== 'string'
    || !SHA256_RE.test(value.pointer_sha256)
    || typeof value.manifest_sha256 !== 'string'
    || !SHA256_RE.test(value.manifest_sha256)
    || typeof value.endpoint !== 'string'
    || !value.endpoint.startsWith('https://')
    || !isRecord(value.feeds)
    || !isRecord(value.details)
  ) {
    throw new Error('MEDIA_CACHE_STATE_INVALID');
  }
  return value as unknown as MediaCacheState;
}

async function encryptState(state: MediaCacheState): Promise<string> {
  validateState(state);
  const keys = splitKeys(await cacheKeyBytes());
  const ivBytes = await Crypto.getRandomBytesAsync(16);
  const iv = wordArrayFromBytes(ivBytes);
  const ciphertext = CryptoJS.AES.encrypt(JSON.stringify(state), keys.aes, {
    iv,
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7,
  }).ciphertext.toString(CryptoJS.enc.Base64);
  const ivText = Buffer.from(ivBytes).toString('base64');
  const signed = `${CACHE_VERSION}.${ivText}.${ciphertext}`;
  const mac = CryptoJS.HmacSHA256(signed, keys.mac).toString(CryptoJS.enc.Hex);
  return JSON.stringify({ version: CACHE_VERSION, iv: ivText, ciphertext, mac } satisfies EncryptedCacheEnvelope);
}

async function decryptState(text: string): Promise<MediaCacheState> {
  const envelope = JSON.parse(text) as Partial<EncryptedCacheEnvelope>;
  if (
    envelope.version !== CACHE_VERSION
    || typeof envelope.iv !== 'string'
    || typeof envelope.ciphertext !== 'string'
    || typeof envelope.mac !== 'string'
  ) {
    throw new Error('MEDIA_CACHE_ENVELOPE_INVALID');
  }
  const keys = splitKeys(await cacheKeyBytes());
  const signed = `${CACHE_VERSION}.${envelope.iv}.${envelope.ciphertext}`;
  const expectedMac = CryptoJS.HmacSHA256(signed, keys.mac).toString(CryptoJS.enc.Hex);
  if (!constantTimeHexEqual(expectedMac, envelope.mac)) {
    throw new Error('MEDIA_CACHE_MAC_INVALID');
  }
  const plaintext = CryptoJS.AES.decrypt(
    { ciphertext: CryptoJS.enc.Base64.parse(envelope.ciphertext) } as CryptoJS.lib.CipherParams,
    keys.aes,
    {
      iv: wordArrayFromBytes(Uint8Array.from(Buffer.from(envelope.iv, 'base64'))),
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    },
  ).toString(CryptoJS.enc.Utf8);
  if (!plaintext) throw new Error('MEDIA_CACHE_DECRYPT_EMPTY');
  return validateState(JSON.parse(plaintext));
}

function deleteIfExists(file: File): void {
  if (file.exists) file.delete();
}

async function restoreBackupToPrimary(backupState: MediaCacheState): Promise<void> {
  if (!CACHE_DIR.exists) CACHE_DIR.create();
  const primary = cacheFile(CACHE_PRIMARY_NAME);
  const backup = cacheFile(CACHE_BACKUP_NAME);
  if (!backup.exists) throw new Error('MEDIA_CACHE_BACKUP_MISSING');
  const temporary = cacheFile(`.media-cache-restore-${Date.now()}.tmp`);
  let temporaryMoved = false;
  try {
    deleteIfExists(temporary);
    new File(backup.uri).copy(temporary);
    const restored = await decryptState(await temporary.text());
    assertMediaPointerTransition(stateIdentity(restored), stateIdentity(backupState));
    deleteIfExists(primary);
    temporary.move(primary);
    temporaryMoved = true;
    await decryptState(await primary.text());
  } finally {
    if (!temporaryMoved) deleteIfExists(temporary);
  }
}

async function writeState(state: MediaCacheState): Promise<void> {
  if (!CACHE_DIR.exists) CACHE_DIR.create();
  const payload = await encryptState(state);
  const primary = cacheFile(CACHE_PRIMARY_NAME);
  const backup = cacheFile(CACHE_BACKUP_NAME);
  const temporary = cacheFile(`.media-cache-${Date.now()}.tmp`);
  let primaryMoved = false;
  let newPrimaryInstalled = false;
  let temporaryMoved = false;
  try {
    deleteIfExists(temporary);
    temporary.create();
    temporary.write(payload);
    const prepared = await decryptState(await temporary.text());
    assertMediaPointerTransition(stateIdentity(prepared), stateIdentity(state));

    deleteIfExists(backup);
    if (primary.exists) {
      new File(primary.uri).move(backup);
      primaryMoved = true;
    }
    temporary.move(primary);
    temporaryMoved = true;
    newPrimaryInstalled = true;
    const committed = await decryptState(await primary.text());
    assertMediaPointerTransition(stateIdentity(committed), stateIdentity(state));
    memoryState = committed;
  } catch (error) {
    try {
      if (newPrimaryInstalled && primary.exists) primary.delete();
      if (primaryMoved && backup.exists) {
        const backupState = await decryptState(await backup.text());
        await restoreBackupToPrimary(backupState);
        memoryState = backupState;
      }
    } catch (restoreError) {
      logCacheFailure('restore_after_write_failure', 'MEDIA_CACHE_RESTORE_FAILED', restoreError);
    }
    throw error;
  } finally {
    if (!temporaryMoved) deleteIfExists(temporary);
  }
}

async function readValidFile(file: File): Promise<MediaCacheState> {
  if (!file.exists) throw new Error('MEDIA_CACHE_FILE_MISSING');
  return decryptState(await file.text());
}

export async function loadMediaCache(): Promise<MediaCacheState | null> {
  if (memoryState) {
    try {
      memoryState = validateState(memoryState);
      return memoryState;
    } catch (error) {
      logCacheFailure('memory_cache_validation', 'MEDIA_CACHE_MEMORY_INVALID', error);
      memoryState = null;
    }
  }
  const primary = cacheFile(CACHE_PRIMARY_NAME);
  const backup = cacheFile(CACHE_BACKUP_NAME);
  try {
    memoryState = await readValidFile(primary);
    return memoryState;
  } catch (primaryError) {
    if (primary.exists) {
      logCacheFailure('load_primary', 'MEDIA_CACHE_PRIMARY_FAILED', primaryError);
    }
  }
  try {
    const recovered = await readValidFile(backup);
    await restoreBackupToPrimary(recovered);
    memoryState = recovered;
    return recovered;
  } catch (backupError) {
    if (backup.exists) {
      logCacheFailure('load_backup', 'MEDIA_CACHE_BACKUP_FAILED', backupError);
    }
  }
  try {
    deleteIfExists(primary);
    deleteIfExists(backup);
  } catch (deleteError) {
    logCacheFailure('delete_invalid_cache', 'MEDIA_CACHE_DELETE_FAILED', deleteError);
  }
  return null;
}

export async function cachedMediaPointerIdentity(): Promise<MediaPointerIdentity | null> {
  const state = await loadMediaCache();
  return state ? stateIdentity(state) : null;
}

export async function saveMediaFeeds(
  identity: MediaPointerIdentity,
  endpoint: string,
  feeds: Partial<Record<MediaKind, MovieFeed>>,
): Promise<void> {
  const existing = await loadMediaCache();
  const existingIdentity = existing ? stateIdentity(existing) : null;
  assertMediaPointerTransition(identity, existingIdentity);
  const samePointer = existingIdentity?.pointer_revision === identity.pointer_revision
    && existingIdentity.pointer_sha256 === identity.pointer_sha256;
  const state: MediaCacheState = {
    schema_version: 'media-app-cache/1',
    saved_at: new Date().toISOString(),
    release_id: identity.release_id,
    pointer_revision: identity.pointer_revision,
    pointer_sha256: identity.pointer_sha256,
    manifest_sha256: identity.manifest_sha256,
    endpoint,
    feeds: { ...(samePointer ? existing?.feeds : {}), ...feeds },
    details: samePointer ? existing?.details ?? {} : {},
  };
  await writeState(state);
}

export async function saveMediaDetail(item: MovieFeedItem): Promise<void> {
  const existing = await loadMediaCache();
  if (!existing || item.remote_release_id !== existing.release_id) return;
  try {
    await writeState({
      ...existing,
      saved_at: new Date().toISOString(),
      details: { ...existing.details, [item.movie_id]: item },
    });
  } catch (error) {
    logCacheFailure('save_detail', 'MEDIA_DETAIL_CACHE_SAVE_FAILED', error);
  }
}

export async function cachedMediaFeed(kind: MediaKind): Promise<MovieFeed | null> {
  const state = await loadMediaCache();
  return state?.feeds[kind] ?? null;
}

export async function cachedMediaDetail(mediaId: string): Promise<MovieFeedItem | null> {
  const state = await loadMediaCache();
  return state?.details[mediaId] ?? null;
}

export function clearMediaCacheMemory() {
  memoryState = null;
}
