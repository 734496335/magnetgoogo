/**
 * Result deduplication — merges identical torrents from multiple sources.
 *
 * Strategy:
 *   1. Extract info hash (btih) from magnet URI — globally unique torrent ID
 *   2. Group results by info hash
 *   3. Merge: keep richest metadata, aggregate source names
 *   4. Multi-source hits rank higher (more trustworthy)
 */

import {
  resolveResourceSizeConsensus,
  upsertResourceSizeObservation,
} from './resourceSize.ts';
import { parseSizeBytes, type SearchResult } from './types.ts';

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

/** Detect video quality from title keywords. Higher = better. 50 = unknown. */
const QUALITY_PATTERNS: [RegExp, number][] = [
  [/remux/i, 100],
  [/blu[\s.-]?ray|bluray|bdrip|bdremux|brrip/i, 95],
  [/web[\s.-]?dl|webdl|webrip|web[\s.-]?rip/i, 80],
  [/hdrip|hdtv|pdtv/i, 65],
  [/dvdrip|dvd[\s.-]?scr|dvd/i, 50],
  [/hdcam|hdcam|cam[\s.-]?rip|\bcam\b/i, 15],
  [/ts\b|telesync|tc\b|telecine/i, 10],
];

function detectVideoQuality(title: string): number {
  for (const [re, score] of QUALITY_PATTERNS) {
    if (re.test(title)) return score;
  }
  return 50;
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
      const sourceName = r.site_name || r.source || '';
      hashMap.set(hash, {
        ...r,
        sourceCount: 1,
        sourceNames: [sourceName],
        bestSeeders: r.seeders || 0,
        _sizeObservations: upsertResourceSizeObservation(r._sizeObservations, r.size, sourceName),
      });
    } else {
      // Merge: keep richer metadata and count distinct sources only.
      const srcName = r.site_name || r.source || '';
      if (srcName && !existing.sourceNames.includes(srcName)) {
        existing.sourceNames.push(srcName);
        existing.sourceCount = existing.sourceNames.length;
      }
      // Keep longer title (usually more descriptive)
      if (r.title.length > existing.title.length) {
        existing.title = r.title;
      }
      existing._sizeObservations = upsertResourceSizeObservation(
        existing._sizeObservations,
        r.size,
        srcName,
      );
      const consensusSize = resolveResourceSizeConsensus(existing._sizeObservations);
      if (consensusSize) existing.size = consensusSize;
      // Keep better seeders
      if ((r.seeders || 0) > existing.bestSeeders) {
        existing.bestSeeders = r.seeders || 0;
        existing.seeders = r.seeders;
      }
      // Keep non-empty date
      if (!existing.date && r.date) existing.date = r.date;
    }
  }

  // Combined sort: relevance (sourceCount) > size > quality tag > seeders
  const deduped = [...hashMap.values()];
  deduped.sort((a, b) => {
    // Primary: multi-source relevance
    if (b.sourceCount !== a.sourceCount) return b.sourceCount - a.sourceCount;
    // Secondary: file size (larger = higher quality)
    const sizeDiff = parseSizeBytes(b.size || '') - parseSizeBytes(a.size || '');
    if (sizeDiff !== 0) return sizeDiff;
    // Tertiary: video quality tags from title
    const qDiff = detectVideoQuality(b.title) - detectVideoQuality(a.title);
    if (qDiff !== 0) return qDiff;
    // Fallback: seeders
    return b.bestSeeders - a.bestSeeders;
  });

  return [...deduped, ...noHash];
}
