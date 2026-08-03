/** Canonical BitTorrent v1 info-hash authority. */

const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

function base32ToHex(value: string): string | null {
  let bits = '';
  for (const character of value.toUpperCase()) {
    const index = BASE32_ALPHABET.indexOf(character);
    if (index < 0) return null;
    bits += index.toString(2).padStart(5, '0');
  }
  let hex = '';
  for (let offset = 0; offset + 4 <= bits.length; offset += 4) {
    hex += Number.parseInt(bits.slice(offset, offset + 4), 2).toString(16);
  }
  return /^[0-9a-f]{40}$/.test(hex) ? hex : null;
}

/** Return a canonical 40-character lowercase hex btih, or null. */
export function extractInfoHash(magnet: string): string | null {
  if (!magnet) return null;
  const hex = magnet.match(/(?:urn:)?btih:([0-9a-f]{40})(?=$|[^0-9a-f])/i);
  if (hex) return hex[1].toLowerCase();
  const base32 = magnet.match(/(?:urn:)?btih:([a-z2-7]{32})(?=$|[^a-z2-7])/i);
  return base32 ? base32ToHex(base32[1]) : null;
}
