/**
 * Compliance Mode — Google Play compliant build.
 *
 * When COMPLIANCE_MODE = true:
 *   1. Only whitelisted sources are loaded (no adult/piracy-heavy sites)
 *   2. Search results are filtered through NSFW keyword blocklist
 *   3. Home screen shows compliance banner with CTA to website
 *   4. Search placeholder guides users toward legitimate queries
 *
 * TEMPORARILY DEPRECATED (2026-08-11): compliance builds are not part of the
 * production support scope. Production releases must keep COMPLIANCE_MODE=false.
 * Historical code/assets remain only so the mode can be restored deliberately later.
 */

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  BUILD FLAG — flip this for Google Play builds
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
export const COMPLIANCE_MODE = false;

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  WHITELISTED SOURCES (by rule id in sources.json)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
export const COMPLIANT_SOURCE_IDS = new Set([
  '6d6496b2ce94',  // animetosho.org — anime fansubs, clean
  '52fbe59cf95c',  // animetime.cc   — anime, clean
  'uindex_001',    // UIndex         — general DHT, structured data
  'zhihu_cilimo',  // CiliMo/磁力魔  — DHT JSON API
  'zhihu_kd705',   // 磁力口袋/CLKD  — DHT JSON API
]);

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  NSFW / PIRACY KEYWORD BLOCKLIST (applied to result titles)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const BLOCKED_PATTERNS: RegExp[] = [
  // ── Adult content (EN) ──
  /\b(porn|xxx|hentai|18\+|adult[- ]?video|nude|erotic|orgasm|fetish|milf|stepmom|stepsister)\b/i,
  // ── Adult content (CN/JP) ──
  /(成人|色情|无码|有码|中文字幕.*无码|骑兵|步兵|素人|痴女|人妻|巨乳|美乳|av女优|里番|工口|裏|エロ|風俗)/,
  // ── JAV studio codes (common prefixes) ──
  /\b(ABP|ABW|SSNI|SSIS|STARS|IPX|IPZ|PRED|MIDE|MIDV|JUL|JUR|CAWD|FSDSS|DLDSS|ROE|MEYD|SONE|MVSD|JUFE|HMN|WAAA|BLK|DASS|FC2)[- ]?\d{3,5}\b/i,
  // ── Torrent quality tags that indicate piracy ──
  /\b(CAMRip|HDTS|HDRip|BDRip|WEB-?DL|DVDSCR|TS-?Rip|HC[- ]?HDRip)\b/i,
  // ── Gambling / fraud ──
  /(赌博|博彩|棋牌|威尼斯人|澳门|六合彩|彩票|赚钱|兼职日结)/,
];

/**
 * Check if a search result title should be blocked in compliance mode.
 * Returns true if the title matches any blocked pattern.
 */
export function isBlockedContent(title: string): boolean {
  if (!COMPLIANCE_MODE) return false;
  if (!title) return false;
  return BLOCKED_PATTERNS.some(p => p.test(title));
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  WEBSITE URL for the CTA banner
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
export const WEBSITE_URL = 'https://magnetgoogo.com';
