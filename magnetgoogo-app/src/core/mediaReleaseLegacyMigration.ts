import { Buffer } from 'buffer';
import CryptoJS from 'crypto-js';
import * as SecureStore from 'expo-secure-store';
import { Directory, File, Paths } from 'expo-file-system';
import type { MediaKind, MovieFeed, MovieFeedItem } from './resourceFeedProtocol';

const LEGACY_CACHE_KEY_NAME = 'mg_media_cache_key_v1';
const LEGACY_CACHE_VERSION = 1;
const LEGACY_CACHE_DIR = new Directory(Paths.document, 'media-release-cache');
const LEGACY_PRIMARY_NAME = 'media.cache.enc.json';
const LEGACY_BACKUP_NAME = 'media.cache.backup.enc.json';
const SHA256_RE = /^[0-9a-f]{64}$/;

export interface LegacyMediaCacheState {
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

interface LegacyEncryptedCacheEnvelope {
  version: 1;
  iv: string;
  ciphertext: string;
  mac: string;
}

function legacyFile(name: string): File {
  return new File(LEGACY_CACHE_DIR, name);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function wordArrayFromBytes(bytes: Uint8Array): CryptoJS.lib.WordArray {
  const words: number[] = [];
  for (let index = 0; index < bytes.length; index += 1) {
    words[index >>> 2] = (words[index >>> 2] || 0) | (bytes[index] << (24 - (index % 4) * 8));
  }
  return CryptoJS.lib.WordArray.create(words, bytes.length);
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

function validateLegacyState(value: unknown): LegacyMediaCacheState {
  if (!isRecord(value) || value.schema_version !== 'media-app-cache/1') {
    throw new Error('LEGACY_MEDIA_CACHE_STATE_INVALID');
  }
  if (
    typeof value.saved_at !== 'string'
    || !value.saved_at
    || typeof value.release_id !== 'string'
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
    throw new Error('LEGACY_MEDIA_CACHE_STATE_INVALID');
  }
  return value as unknown as LegacyMediaCacheState;
}

async function legacyKeyBytes(): Promise<Uint8Array> {
  const stored = await SecureStore.getItemAsync(LEGACY_CACHE_KEY_NAME);
  if (!stored) throw new Error('LEGACY_MEDIA_CACHE_KEY_MISSING');
  const parsed = Uint8Array.from(Buffer.from(stored, 'base64'));
  if (parsed.length !== 64) throw new Error('LEGACY_MEDIA_CACHE_KEY_INVALID');
  return parsed;
}

async function decryptLegacyState(text: string): Promise<LegacyMediaCacheState> {
  const envelope = JSON.parse(text) as Partial<LegacyEncryptedCacheEnvelope>;
  if (
    envelope.version !== LEGACY_CACHE_VERSION
    || typeof envelope.iv !== 'string'
    || typeof envelope.ciphertext !== 'string'
    || typeof envelope.mac !== 'string'
  ) {
    throw new Error('LEGACY_MEDIA_CACHE_ENVELOPE_INVALID');
  }
  const keys = splitKeys(await legacyKeyBytes());
  const signed = `${LEGACY_CACHE_VERSION}.${envelope.iv}.${envelope.ciphertext}`;
  const expectedMac = CryptoJS.HmacSHA256(signed, keys.mac).toString(CryptoJS.enc.Hex);
  if (!constantTimeHexEqual(expectedMac, envelope.mac)) {
    throw new Error('LEGACY_MEDIA_CACHE_MAC_INVALID');
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
  if (!plaintext) throw new Error('LEGACY_MEDIA_CACHE_DECRYPT_EMPTY');
  return validateLegacyState(JSON.parse(plaintext));
}

export function legacyMediaCacheExists(): boolean {
  return legacyFile(LEGACY_PRIMARY_NAME).exists || legacyFile(LEGACY_BACKUP_NAME).exists;
}

export async function readLegacyMediaCache(): Promise<LegacyMediaCacheState | null> {
  for (const name of [LEGACY_PRIMARY_NAME, LEGACY_BACKUP_NAME]) {
    const file = legacyFile(name);
    if (!file.exists) continue;
    try {
      return await decryptLegacyState(await file.text());
    } catch (error) {
      console.warn('[MediaReleaseCacheMigration]', {
        stage: 'read_legacy_cache',
        error_code: 'LEGACY_MEDIA_CACHE_READ_FAILED',
        file: name,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return null;
}

export async function deleteLegacyMediaCache(): Promise<void> {
  for (const name of [LEGACY_PRIMARY_NAME, LEGACY_BACKUP_NAME]) {
    const file = legacyFile(name);
    if (file.exists) file.delete();
  }
  try {
    await SecureStore.deleteItemAsync(LEGACY_CACHE_KEY_NAME);
  } catch (error) {
    console.warn('[MediaReleaseCacheMigration]', {
      stage: 'delete_legacy_key',
      error_code: 'LEGACY_MEDIA_CACHE_KEY_DELETE_FAILED',
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
