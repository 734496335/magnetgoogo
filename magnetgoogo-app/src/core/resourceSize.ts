/** Shared torrent/resource size parsing, formatting and conflict resolution.
 *
 * Display labels use binary multipliers. Individual source adapters remain
 * responsible for declaring the unit of raw numeric API fields.
 */

const RESOURCE_SIZE_PATTERN = /(\d[\d,]*(?:\.\d+)?)\s*(TiB|GiB|MiB|KiB|TB|GB|MB|KB|bytes?|B|太字节|太位元組|吉字节|吉位元組|兆字节|兆位元組|千字节|千位元組|字节|位元組)/gi;
const LABEL_PREFIX_PATTERN = /(?:torrent\s*size|file\s*size|total\s*size|resource\s*size|size|文件大小|檔案大小|种子大小|種子大小|资源大小|資源大小|总大小|總大小|大小|容量)\s*[:：]?\s*$/i;

const UNIT_MULTIPLIERS: Record<string, number> = {
  B: 1,
  KB: 1024,
  MB: 1024 ** 2,
  GB: 1024 ** 3,
  TB: 1024 ** 4,
};

function normalizeUnit(raw: string): keyof typeof UNIT_MULTIPLIERS | null {
  const compact = raw.trim().toUpperCase();
  if (compact === 'B' || compact === 'BYTE' || compact === 'BYTES' || raw === '字节' || raw === '位元組') return 'B';
  if (compact === 'KB' || compact === 'KIB' || raw === '千字节' || raw === '千位元組') return 'KB';
  if (compact === 'MB' || compact === 'MIB' || raw === '兆字节' || raw === '兆位元組') return 'MB';
  if (compact === 'GB' || compact === 'GIB' || raw === '吉字节' || raw === '吉位元組') return 'GB';
  if (compact === 'TB' || compact === 'TIB' || raw === '太字节' || raw === '太位元組') return 'TB';
  return null;
}

interface ParsedSize {
  label: string;
  bytes: number;
  value: number;
  numericText: string;
  unit: keyof typeof UNIT_MULTIPLIERS;
  index: number;
}

function isAsciiAlphaNumeric(value: string): boolean {
  return /[A-Za-z0-9]/.test(value);
}

function parseMatches(raw?: string): ParsedSize[] {
  if (!raw) return [];
  const matches: ParsedSize[] = [];
  RESOURCE_SIZE_PATTERN.lastIndex = 0;
  for (const match of raw.matchAll(RESOURCE_SIZE_PATTERN)) {
    const index = match.index ?? 0;
    const end = index + match[0].length;
    const previous = index > 0 ? raw[index - 1] : '';
    const next = end < raw.length ? raw[end] : '';

    // Reject size-like fragments embedded inside hashes, filenames or text
    // accidentally concatenated by DOM .text(), e.g. `...a7b5308` -> `7 B`
    // and `movie.mp44.32 GB` -> `44.32 GB`.
    if ((previous && isAsciiAlphaNumeric(previous)) || (next && isAsciiAlphaNumeric(next))) continue;

    const numericText = match[1].replace(/,/g, '');
    const value = Number.parseFloat(numericText);
    const unit = normalizeUnit(match[2]);
    if (!unit || !Number.isFinite(value) || value <= 0) continue;
    const bytes = value * UNIT_MULTIPLIERS[unit];
    if (!Number.isFinite(bytes) || bytes < 1024) continue;
    matches.push({ label: `${numericText} ${unit}`, bytes, value, numericText, unit, index });
  }
  return matches;
}

/** Extract the largest valid size from a result row containing total and file sizes. */
export function parseResourceSizeLabel(raw?: string): string {
  const matches = parseMatches(raw);
  if (matches.length === 0) return '';
  return matches.reduce((best, item) => item.bytes > best.bytes ? item : best).label;
}

/** Extract the first valid size while preserving page/selector order. */
export function parseFirstResourceSizeLabel(raw?: string): string {
  return parseMatches(raw)[0]?.label || '';
}

/** Extract the first size explicitly preceded by a size label. */
export function parseLabeledResourceSizeLabel(raw?: string): string {
  if (!raw) return '';
  for (const match of parseMatches(raw)) {
    const prefix = raw.slice(Math.max(0, match.index - 48), match.index);
    if (LABEL_PREFIX_PATTERN.test(prefix)) return match.label;
  }
  return '';
}

/** Parse the largest valid size in a string to bytes. */
export function parseResourceSizeBytes(raw?: string): number {
  const matches = parseMatches(raw);
  if (matches.length === 0) return 0;
  return matches.reduce((best, item) => item.bytes > best ? item.bytes : best, 0);
}

export interface BoundDetailSizeEvidence {
  hint?: string;
  localText?: string;
  selectorTexts?: string[];
  bodyText?: string;
  magnetCount: number;
}

/**
 * Resolve size metadata for one magnet on a detail page. Search-page hints and
 * the magnet's nearest DOM context are bound evidence. Page-wide selectors or
 * body text are only safe when the page exposes exactly one magnet.
 */
export function resolveBoundDetailResourceSize(evidence: BoundDetailSizeEvidence): string {
  const hintSize = parseResourceSizeLabel(evidence.hint);
  if (hintSize) return hintSize;

  const localText = evidence.localText || '';
  const localSize = parseLabeledResourceSizeLabel(localText) || parseFirstResourceSizeLabel(localText);
  if (localSize) return localSize;

  if (evidence.magnetCount !== 1) return '';
  for (const text of evidence.selectorTexts || []) {
    const selectorSize = parseFirstResourceSizeLabel(text);
    if (selectorSize) return selectorSize;
  }
  const bodyText = evidence.bodyText || '';
  return parseLabeledResourceSizeLabel(bodyText) || parseFirstResourceSizeLabel(bodyText);
}

/** Format a byte count using binary units and compact precision. */
export function formatResourceSize(bytes?: number): string {
  if (!bytes || !Number.isFinite(bytes) || bytes < 1024) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const decimals = value >= 100 ? 0 : value >= 10 ? 1 : 2;
  const fixed = value.toFixed(decimals);
  const numeric = fixed.includes('.') ? fixed.replace(/0+$/, '').replace(/\.$/, '') : fixed;
  return `${numeric} ${units[unitIndex]}`;
}

interface SsbcSizeRange {
  minimum: number;
  maximum: number;
}

function ssbcExpectedSizeRange(title: string): SsbcSizeRange | null {
  const normalized = title.toLowerCase();
  const gib = 1024 ** 3;
  const mib = 1024 ** 2;
  if (/\b(?:2160p|4k|uhd)\b/.test(normalized)) return { minimum: 1 * gib, maximum: 300 * gib };
  if (/\b(?:1080[pi]|remux|blu[ ._-]?ray|bdrip|hdrip|webrip|web[ ._-]?dl)\b/.test(normalized)) {
    return { minimum: 100 * mib, maximum: 300 * gib };
  }
  if (/\b720[pi]\b/.test(normalized)) return { minimum: 100 * mib, maximum: 80 * gib };
  if (/\.(?:mkv|mp4|avi|mov|wmv|m2ts|ts)(?:\b|$)/.test(normalized)) {
    return { minimum: 50 * mib, maximum: 300 * gib };
  }
  if (/\.(?:iso|dmg|pkg|exe|msi|apk|zip|rar|7z)(?:\b|$)/.test(normalized)) {
    return { minimum: 1 * mib, maximum: 500 * gib };
  }
  return null;
}

/**
 * SSBC mixes byte counts and KiB counts in the same API response. Resolve only
 * when title-derived plausibility leaves one safe candidate; hide ambiguity.
 */
export function formatSsbcSize(raw: unknown, title = ''): string {
  const numeric = typeof raw === 'number'
    ? raw
    : Number(String(raw ?? '').replace(/,/g, '').trim());
  if (!Number.isFinite(numeric) || numeric <= 0) return '';
  const candidates = [numeric, numeric * 1024];
  const range = ssbcExpectedSizeRange(title);
  if (range) {
    const plausible = candidates.filter((bytes) => bytes >= range.minimum && bytes <= range.maximum);
    return plausible.length === 1 ? formatResourceSize(plausible[0]) : '';
  }
  const genericMinimum = 1024 ** 2;
  const genericMaximum = 64 * 1024 ** 4;
  const plausible = candidates.filter((bytes) => bytes >= genericMinimum && bytes <= genericMaximum);
  if (plausible.length !== 1) return '';
  return formatResourceSize(plausible[0]);
}

export interface ResourceSizeObservation {
  label: string;
  source: string;
}

/** Keep at most one current observation per source while retaining arrival order. */
export function upsertResourceSizeObservation(
  observations: ResourceSizeObservation[] | undefined,
  label: string | undefined,
  source = '',
): ResourceSizeObservation[] {
  const normalized = parseResourceSizeLabel(label);
  const current = [...(observations || [])];
  if (!normalized) return current;
  if (source) {
    const index = current.findIndex((item) => item.source === source);
    if (index >= 0) {
      current[index] = { label: normalized, source };
      return current;
    }
  }
  current.push({ label: normalized, source });
  return current;
}

interface SizeCluster {
  firstIndex: number;
  items: Array<{ parsed: ParsedSize; observation: ResourceSizeObservation; index: number }>;
}

function clusterRepresentative(cluster: SizeCluster) {
  const sorted = [...cluster.items].sort((a, b) => a.parsed.bytes - b.parsed.bytes);
  return sorted[Math.floor((sorted.length - 1) / 2)];
}

function chooseTiedCluster(clusters: SizeCluster[]): SizeCluster {
  if (clusters.length === 1) return clusters[0];
  const byRepresentative = [...clusters].sort(
    (a, b) => clusterRepresentative(a).parsed.bytes - clusterRepresentative(b).parsed.bytes,
  );
  const low = byRepresentative[0];
  const high = byRepresentative[byRepresentative.length - 1];
  const lowParsed = clusterRepresentative(low).parsed;
  const highParsed = clusterRepresentative(high).parsed;
  const ratio = highParsed.bytes / lowParsed.bytes;

  // Typical unit-loss signature: a byte/KiB count exposed as a few bytes versus
  // a real MB/GB value, or a KiB count interpreted as bytes (roughly 1024x).
  if (lowParsed.bytes < 1024 && highParsed.bytes >= 1024 ** 2) return high;
  if (ratio >= 900 && ratio <= 1150) return high;

  // Typical DOM-concatenation signature: a recommendation/title number glued
  // in front of the real size, producing a multi-terabyte outlier.
  if (highParsed.bytes > 8 * 1024 ** 4 && lowParsed.bytes < 500 * 1024 ** 3 && ratio > 16) return low;
  if (
    highParsed.unit === lowParsed.unit
    && highParsed.numericText.endsWith(lowParsed.numericText)
    && ratio > 2
  ) return low;

  return [...clusters].sort((a, b) => a.firstIndex - b.firstIndex)[0];
}

/** Resolve conflicting same-hash sizes by source consensus, not raw maximum. */
export function resolveResourceSizeConsensus(
  observations: ResourceSizeObservation[] | undefined,
): string {
  const valid = (observations || []).map((observation, index) => {
    const parsed = parseMatches(observation.label)[0];
    return parsed ? { parsed, observation, index } : null;
  }).filter((item): item is NonNullable<typeof item> => !!item);
  if (valid.length === 0) return '';

  const clusters: SizeCluster[] = [];
  for (const item of valid) {
    const cluster = clusters.find((candidate) => {
      const representative = clusterRepresentative(candidate).parsed.bytes;
      return Math.max(representative, item.parsed.bytes) / Math.min(representative, item.parsed.bytes) <= 1.15;
    });
    if (cluster) cluster.items.push(item);
    else clusters.push({ firstIndex: item.index, items: [item] });
  }

  const maxVotes = Math.max(...clusters.map((cluster) => cluster.items.length));
  const tied = clusters.filter((cluster) => cluster.items.length === maxVotes);
  return clusterRepresentative(chooseTiedCluster(tied)).parsed.label;
}
