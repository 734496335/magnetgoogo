#!/usr/bin/env node
/**
 * Encrypt sources.json for secure distribution.
 *
 * Usage:
 *   node scripts/encrypt-sources.mjs [path/to/sources.json] [output]
 *
 * Defaults:
 *   input:  ../../sources.json
 *   output: ../../sources.enc.json
 */
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import CryptoJS from 'crypto-js';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Same key fragments as crypto.ts — MUST stay in sync ──
const _F = [
  { f: 'a837c14b9e5d0a23', m: 'e556a52dfa3b6e45' },
  { f: '3c19574f28410a1c', m: '5e7b332e48256e3a' },
  { f: '672f0b115c39462b', m: '354a6f723a5f204d' },
  { f: '1c0b5e47193a5818', m: '6e6e3a26796c3c3e' },
];

function _xorHex(a, b) {
  let r = '';
  for (let i = 0; i < a.length; i += 2) {
    r += (parseInt(a.substring(i, i + 2), 16) ^ parseInt(b.substring(i, i + 2), 16))
      .toString(16).padStart(2, '0');
  }
  return r;
}

function assembleKey() {
  return _F.map(({ f, m }) => _xorHex(f, m)).join('');
}

// ── Main ──
const inputPath = resolve(__dirname, process.argv[2] || '../../sources.json');
const outputPath = resolve(__dirname, process.argv[3] || '../../sources.enc.json');

console.log(`📖 Reading: ${inputPath}`);
const raw = readFileSync(inputPath, 'utf8');

const key = CryptoJS.enc.Hex.parse(assembleKey());
const iv = CryptoJS.lib.WordArray.random(16);

const encrypted = CryptoJS.AES.encrypt(raw, key, {
  iv,
  mode: CryptoJS.mode.CBC,
  padding: CryptoJS.pad.Pkcs7,
});

const ct = encrypted.toString();
const sig = CryptoJS.HmacSHA256(ct, key).toString();

const payload = JSON.stringify({ iv: iv.toString(), ct, sig });
writeFileSync(outputPath, payload, 'utf8');

const origKB = Math.round(raw.length / 1024);
const encKB = Math.round(payload.length / 1024);
console.log(`🔒 Encrypted: ${outputPath}`);
console.log(`   Original: ${origKB} KB → Encrypted: ${encKB} KB`);
console.log('✅ Done. Serve sources.enc.json instead of sources.json');
