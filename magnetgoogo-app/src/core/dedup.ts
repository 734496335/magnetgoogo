/**
 * Result deduplication — merges identical torrents from multiple sources.
 *
 * Strategy:
 *   1. Extract info hash (btih) from magnet URI — globally unique torrent ID
 *   2. Group results by info hash
 *   3. Merge: keep richest metadata, aggregate source names
 *   4. Multi-source hits rank higher (more trustworthy)
 */

import type { SearchResult } from './types';

/** Extract the 40-hex info hash from a magnet URI. Returns lowercase or null. */
export function extractInfoHash(magnet: string): string | null {
  if (!magnet) return null;
  // urn:btih: followed by 40 hex chars or 32 base32 chars
  const hex = magnet.match(/btih:([0-9a-f]{40})/i);
  if (hex) return hex[1].toLowerCase();
  // Base32 encoded (32 chars)
  const b32 = magnet.match(/btih:([a-z2-7]{32})/i);
  if (b32) return base32ToHex(b32[1]).toLowerCase();
  return null;
}

/** Convert base32 to hex string. */
function base32ToHex(b32: string): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const c of b32.toUpperCase()) {
    const val = alphabet.indexOf(c);
    if (val === -1) return '';
    bits += val.toString(2).padStart(5, '0');
  }
  let hex = '';
  for (let i = 0; i + 4 <= bits.length; i += 4) {
    hex += parseInt(bits.slice(i, i + 4), 2).toString(16);
  }
  return hex;
}

export interface DedupedResult extends SearchResult {
  /** Number of sources that returned this exact torrent */
  sourceCount: number;
  /** Names of all sources that found this torrent */
  sourceNames: string[];
  /** Best seeders value across all duplicates */
  bestSeeders: number;
}

/** Deduplicate search results by info hash. */
export function deduplicateResults(results: SearchResult[]): DedupedResult[] {
  const hashMap = new Map<string, DedupedResult>();
  const noHash: DedupedResult[] = []; // results without parseable hash

  for (const r of results) {
    const hash = extractInfoHash(r.magnet);

    if (!hash) {
      noHash.push({
        ...r,
        sourceCount: 1,
        sourceNames: [r.site_name || r.source || ''],
        bestSeeders: r.seeders || 0,
      });
      continue;
    }

    const existing = hashMap.get(hash);
    if (!existing) {
      hashMap.set(hash, {
        ...r,
        sourceCount: 1,
        sourceNames: [r.site_name || r.source || ''],
        bestSeeders: r.seeders || 0,
      });
    } else {
      // Merge: keep richer metadata
      existing.sourceCount++;
      const srcName = r.site_name || r.source || '';
      if (srcName && !existing.sourceNames.includes(srcName)) {
        existing.sourceNames.push(srcName);
      }
      // Keep longer title (usually more descriptive)
      if (r.title.length > existing.title.length) {
        existing.title = r.title;
      }
      // Keep non-empty size
      if (!existing.size && r.size) existing.size = r.size;
      // Keep better seeders
      if ((r.seeders || 0) > existing.bestSeeders) {
        existing.bestSeeders = r.seeders || 0;
        existing.seeders = r.seeders;
      }
      // Keep non-empty date
      if (!existing.date && r.date) existing.date = r.date;
    }
  }

  // Multi-source hits first, then by seeders
  const deduped = [...hashMap.values()];
  deduped.sort((a, b) => {
    if (b.sourceCount !== a.sourceCount) return b.sourceCount - a.sourceCount;
    return b.bestSeeders - a.bestSeeders;
  });

  return [...deduped, ...noHash];
}
