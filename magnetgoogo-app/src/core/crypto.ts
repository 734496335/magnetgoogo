/**
 * Source payload encryption / decryption.
 *
 * Defence-in-depth:
 *   1. AES-256-CBC encrypts sources.json server-side before transmission.
 *   2. The encryption key is NOT stored as a single string — it is split
 *      into 4 fragments XOR'd with per-fragment masks, then reassembled
 *      at runtime.  A static analysis of the binary will not find a
 *      plaintext key.
 *   3. An HMAC-SHA256 signature accompanies every payload so the app can
 *      reject tampered / forged data.
 *
 * This is NOT unbreakable (a determined reverse-engineer with a debugger
 * can still extract the key from memory).  But it raises the bar far
 * above "open the APK and read sources.json".
 */

import CryptoJS from 'crypto-js';
import pako from 'pako';

// ── Key fragments ────────────────────────────────────────────────────
// The real 32-byte key is split into 4 hex fragments, each XOR'd with
// a mask.  To change the key, run the `generateKeyFragments` helper at
// the bottom of this file in Node.js, then paste the output here.
//
// Key: random 256-bit, split into 4 XOR-masked fragments.
// Regenerate with _gen_key.py — never commit the raw key.

const _F = [
  { f: '8e16f5d77f2cbe1d', m: '879013eacc3c0e66' },
  { f: 'd3ece411ab179a96', m: '2c3f0b24625b15fb' },
  { f: '04f8509f59e484d6', m: '95ae4517844b1c0d' },
  { f: '7242f48883974ebb', m: '0de88d8f93fc7a65' },
];

function _xorHex(a: string, b: string): string {
  let r = '';
  for (let i = 0; i < a.length; i += 2) {
    r += (parseInt(a.substring(i, i + 2), 16) ^ parseInt(b.substring(i, i + 2), 16))
      .toString(16).padStart(2, '0');
  }
  return r;
}

function _assembleKey(): string {
  return _F.map(({ f, m }) => _xorHex(f, m)).join('');
}

// ── Public API ───────────────────────────────────────────────────────

/**
 * Decrypt an encrypted sources payload.
 *
 * Expected input format (JSON string):
 *   { "iv": "<hex>", "ct": "<base64>", "sig": "<hex>" }
 *
 * Returns the decrypted JSON string, or throws on failure.
 */
export function decryptSources(encryptedPayload: string): string {
  const key = CryptoJS.enc.Hex.parse(_assembleKey());
  const { iv, ct, sig } = JSON.parse(encryptedPayload);

  // Verify HMAC-SHA256 signature
  const expectedSig = CryptoJS.HmacSHA256(ct, key).toString();
  if (sig !== expectedSig) {
    throw new Error('Source signature verification failed — data may be tampered');
  }

  // Decrypt AES-256-CBC
  const decrypted = CryptoJS.AES.decrypt(ct, key, {
    iv: CryptoJS.enc.Hex.parse(iv),
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7,
  });

  // Check if payload is gzip-compressed
  const isGzipped = JSON.parse(encryptedPayload).gz === true;
  if (isGzipped) {
    // Convert WordArray to Uint8Array, then gunzip
    const words = decrypted.words;
    const sigBytes = decrypted.sigBytes;
    const bytes = new Uint8Array(sigBytes);
    for (let i = 0; i < sigBytes; i++) {
      bytes[i] = (words[i >>> 2] >>> (24 - (i % 4) * 8)) & 0xff;
    }
    try {
      const decompressed = pako.inflate(bytes, { to: 'string' });
      if (!decompressed) {
        throw new Error('Decompression returned empty result');
      }
      return decompressed;
    } catch (e: any) {
      throw new Error(`Decompression failed: ${e.message}`);
    }
  }

  const plaintext = decrypted.toString(CryptoJS.enc.Utf8);
  if (!plaintext) {
    throw new Error('Decryption failed — invalid key or corrupted data');
  }
  return plaintext;
}

/**
 * Encrypt sources (used by the server-side script, exported for tooling).
 * In production this runs on the server, NOT in the app.
 */
export function encryptSources(jsonString: string): string {
  const key = CryptoJS.enc.Hex.parse(_assembleKey());
  const iv = CryptoJS.lib.WordArray.random(16);

  const encrypted = CryptoJS.AES.encrypt(jsonString, key, {
    iv,
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7,
  });

  const ct = encrypted.toString(); // base64
  const sig = CryptoJS.HmacSHA256(ct, key).toString();

  return JSON.stringify({
    iv: iv.toString(),
    ct,
    sig,
  });
}
