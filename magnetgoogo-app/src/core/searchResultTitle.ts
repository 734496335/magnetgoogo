const UNKNOWN_TITLE_RE = /^(?:unknown(?:\s+title)?|untitled|no\s+title|未知标题|无标题)$/i;
const PURE_HEX_HASH_RE = /^[a-f0-9]{32,64}$/i;
const PURE_BASE32_HASH_RE = /^[a-z2-7]{32}$/i;
const HASH_ONLY_LABEL_RE = /^(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*(?:[a-f0-9]{8,64}|[a-z2-7]{16,32})(?:\.{3}|…)?$/i;
const BTIH_URI_RE = /^(?:magnet:\?\S*|urn:btih:[a-z0-9]+|btih:[a-z0-9]+)/i;
const LEADING_FULL_HASH_RE = /^(?:hash|btih|info[-_\s]?hash)?\s*[:：=]?\s*(?:[a-f0-9]{32,64}|[a-z2-7]{32})(?:\.{3}|…)?\s*(?:[-–—_|:：]+|\s{2,})\s*(.+)$/i;
const LEADING_TRUNCATED_HASH_RE = /^(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*[a-f0-9]{8,31}(?:\.{3}|…)+\s*(?:[-–—_|:：]+\s*)?(.+)?$/i;

function decodeBasicEntities(value: string): string {
  return value
    .replace(/&nbsp;|&#160;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>');
}

export function normalizeResultTitleText(raw: string): string {
  return decodeBasicEntities(String(raw || ''))
    .replace(/<[^>]*>/g, ' ')
    .replace(/[\u0000-\u001f\u007f]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^["'`\s]+|["'`\s]+$/g, '')
    .trim();
}

function extractDisplayNameFromMagnet(magnet: string): string {
  try {
    const match = String(magnet || '').match(/[?&]dn=([^&]+)/i);
    if (!match) return '';
    return normalizeResultTitleText(decodeURIComponent(match[1].replace(/\+/g, ' ')));
  } catch {
    return '';
  }
}

function stripLeadingHash(raw: string): string {
  const normalized = normalizeResultTitleText(raw);
  const full = normalized.match(LEADING_FULL_HASH_RE);
  if (full?.[1]) return normalizeResultTitleText(full[1]);
  const truncated = normalized.match(LEADING_TRUNCATED_HASH_RE);
  if (truncated?.[1]) return normalizeResultTitleText(truncated[1]);
  return normalized;
}

export function isHashPlaceholderTitle(title: string, magnet = ''): boolean {
  const normalized = normalizeResultTitleText(title);
  if (!normalized || UNKNOWN_TITLE_RE.test(normalized)) return true;
  if (
    PURE_HEX_HASH_RE.test(normalized)
    || PURE_BASE32_HASH_RE.test(normalized)
    || HASH_ONLY_LABEL_RE.test(normalized)
    || BTIH_URI_RE.test(normalized)
  ) {
    return true;
  }

  const infoHash = String(magnet || '').match(/btih:([a-f0-9]{40}|[a-z2-7]{32})/i)?.[1]?.toLowerCase() || '';
  if (infoHash) {
    const compact = normalized
      .replace(/^(?:hash|btih|info[-_\s]?hash)\s*[:：=]?\s*/i, '')
      .replace(/(?:\.{3}|…)$/, '')
      .replace(/[^a-z0-9]/gi, '')
      .toLowerCase();
    if (compact.length >= 8 && infoHash.startsWith(compact)) return true;
  }
  return false;
}

/**
 * Return a user-facing title or null when the source supplied only an info hash.
 * Existing meaningful titles win; otherwise the magnet `dn` parameter is used.
 */
export function recoverResultTitle(rawTitle: string, magnet: string): string | null {
  const stripped = stripLeadingHash(rawTitle);
  if (!isHashPlaceholderTitle(stripped, magnet)) return stripped;

  const displayName = stripLeadingHash(extractDisplayNameFromMagnet(magnet));
  if (!isHashPlaceholderTitle(displayName, magnet)) return displayName;
  return null;
}
