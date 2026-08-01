/** Shared torrent/resource size parsing and formatting.
 *
 * All display labels use binary multipliers because the upstream torrent
 * indexes report KiB-style counts even when their UI labels them as KB/GB.
 */

const RESOURCE_SIZE_PATTERN = /(\d[\d,]*(?:\.\d+)?)\s*(TiB|GiB|MiB|KiB|TB|GB|MB|KB|bytes?|B|太字节|太位元組|吉字节|吉位元組|兆字节|兆位元組|千字节|千位元組|字节|位元組)(?![A-Za-z])/gi;

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
}

function parseMatches(raw?: string): ParsedSize[] {
  if (!raw) return [];
  const matches: ParsedSize[] = [];
  RESOURCE_SIZE_PATTERN.lastIndex = 0;
  for (const match of raw.matchAll(RESOURCE_SIZE_PATTERN)) {
    const value = Number.parseFloat(match[1].replace(/,/g, ''));
    const unit = normalizeUnit(match[2]);
    if (!unit || !Number.isFinite(value) || value <= 0) continue;
    const bytes = value * UNIT_MULTIPLIERS[unit];
    if (!Number.isFinite(bytes) || bytes <= 0) continue;
    matches.push({ label: `${match[1].replace(/,/g, '')} ${unit}`, bytes });
  }
  return matches;
}

/** Extract the largest valid size from a label or a container with multiple sizes. */
export function parseResourceSizeLabel(raw?: string): string {
  const matches = parseMatches(raw);
  if (matches.length === 0) return '';
  return matches.reduce((best, item) => item.bytes > best.bytes ? item : best).label;
}

/** Parse the largest valid size in a string to bytes. */
export function parseResourceSizeBytes(raw?: string): number {
  const matches = parseMatches(raw);
  if (matches.length === 0) return 0;
  return matches.reduce((best, item) => item.bytes > best ? item.bytes : best, 0);
}

/** Format a byte count using binary units and compact precision. */
export function formatResourceSize(bytes?: number): string {
  if (!bytes || !Number.isFinite(bytes) || bytes <= 0) return '';
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

/** SSBC's `size` field is a KiB count, not a byte count. */
export function formatSsbcSize(raw: unknown): string {
  const kib = typeof raw === 'number'
    ? raw
    : Number(String(raw ?? '').replace(/,/g, '').trim());
  if (!Number.isFinite(kib) || kib <= 0) return '';
  return formatResourceSize(kib * 1024);
}
