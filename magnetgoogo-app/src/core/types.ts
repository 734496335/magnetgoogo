/** Shared types for the MagnetGoogo RN app. */
import type { Translations } from './i18n';

export interface SearchResult {
  title: string;
  magnet: string;
  size?: string;
  date?: string;
  fileCount?: number;
  source?: string;
  score?: number;
  seeders?: number;
  leechers?: number;
  site_name?: string;
}

// ── Two-tier Kind system ──
// Tier 1 — Content type: detected from title keywords (what it IS)
// Tier 2 — Format type:  detected from file extension (what format it's in)
export type Kind =
  // Tier 1: content types
  | 'movie' | 'tv_us' | 'tv_jp' | 'tv_kr' | 'tv_cn' | 'tv'
  | 'anime' | 'variety' | 'documentary'
  | 'music' | 'game' | 'ebook' | 'manga'
  // Tier 2: format fallback types
  | 'video' | 'audio' | 'archive' | 'image' | 'document' | 'software' | 'other';

export interface ResultCardModel {
  id: string;
  title: string;
  magnet: string;
  kind: Kind;
  kindLabel: string;
  sizeLabel: string;
  dateLabel: string;
  fileCountLabel: string;
  tags: string[];
  theme: KindTheme;
  relevance: number;
  sourceName: string;
  sourceCount: number;
  sourceNames: string[];
}

export interface KindTheme {
  iconName: string; // Ionicons name
  tileColors: [string, string]; // gradient start/end
  iconColor: string;
}

export const KIND_THEMES: Record<Kind, KindTheme> = {
  // ── Tier 1: content types ──
  movie:       { iconName: 'film-outline',             tileColors: ['#ffeef0', '#ffd6dc'], iconColor: '#e85d75' },
  tv_us:       { iconName: 'tv-outline',               tileColors: ['#e3f2fd', '#bbdefb'], iconColor: '#1565c0' },
  tv_jp:       { iconName: 'tv-outline',               tileColors: ['#fce4ec', '#f8bbd0'], iconColor: '#c62828' },
  tv_kr:       { iconName: 'tv-outline',               tileColors: ['#f3e5f5', '#e1bee7'], iconColor: '#7b1fa2' },
  tv_cn:       { iconName: 'tv-outline',               tileColors: ['#ffebee', '#ffcdd2'], iconColor: '#d32f2f' },
  tv:          { iconName: 'tv-outline',               tileColors: ['#e0f2f1', '#b2dfdb'], iconColor: '#00796b' },
  anime:       { iconName: 'color-palette-outline',    tileColors: ['#fce4ec', '#f8bbd0'], iconColor: '#d81b60' },
  variety:     { iconName: 'mic-outline',              tileColors: ['#fff3e0', '#ffe0b2'], iconColor: '#ef6c00' },
  documentary: { iconName: 'earth-outline',            tileColors: ['#e8eaf6', '#c5cae9'], iconColor: '#283593' },
  music:       { iconName: 'musical-notes-outline',    tileColors: ['#fff3e0', '#ffe0b2'], iconColor: '#f57c00' },
  game:        { iconName: 'game-controller-outline',  tileColors: ['#e8f5e9', '#c8e6c9'], iconColor: '#2e7d32' },
  ebook:       { iconName: 'book-outline',             tileColors: ['#fff8e1', '#ffecb3'], iconColor: '#ff8f00' },
  manga:       { iconName: 'library-outline',          tileColors: ['#fce4ec', '#f8bbd0'], iconColor: '#ad1457' },
  // ── Tier 2: format fallback types ──
  video:       { iconName: 'play-circle-outline',      tileColors: ['#ffeef0', '#ffd6dc'], iconColor: '#e85d75' },
  audio:       { iconName: 'musical-notes-outline',    tileColors: ['#fff3e0', '#ffe0b2'], iconColor: '#f57c00' },
  archive:     { iconName: 'file-tray-stacked-outline', tileColors: ['#e3f2fd', '#bbdefb'], iconColor: '#1e88e5' },
  image:       { iconName: 'image-outline',            tileColors: ['#f3e5f5', '#e1bee7'], iconColor: '#8e24aa' },
  document:    { iconName: 'document-text-outline',    tileColors: ['#fff8e1', '#ffecb3'], iconColor: '#ffa000' },
  software:    { iconName: 'cube-outline',             tileColors: ['#e8f5e9', '#c8e6c9'], iconColor: '#43a047' },
  other:       { iconName: 'help-circle-outline',      tileColors: ['#f5f5f5', '#e0e0e0'], iconColor: '#757575' },
};

/**
 * Two-tier kind detection:
 *   Tier 1 — Content type from title keywords (电影/美剧/动漫/漫画/…)
 *   Tier 2 — File format from extension (.mp4/.mkv/.rmvb/…)
 */
export function guessKind(title: string): Kind {
  const t = title.toLowerCase();

  // ═══════════════════════════════════════════════════════════════════
  // TIER 1: Content-based detection (what the resource IS)
  // ═══════════════════════════════════════════════════════════════════

  // ── Anime / 动漫 ── (check before TV, many anime have S/E patterns)
  if (/动[漫画]片?|anime|ova|oad|番剧|新番|旧番/.test(t)) return 'anime';
  if (/\[.*(?:字幕[组組队隊]|fansub|sub)\]|fansu[bp]/i.test(t)) return 'anime';
  if (/\b(?:mikan|nyaa|acg\.rip|dmhy|bangumi|animetime)\b/i.test(t)) return 'anime';
  if (/\[\d{2,3}(?:v\d)?\]|\[\d{2,3}-\d{2,3}\]/.test(t) && /[\u4e00-\u9fff]|[\u3040-\u309f\u30a0-\u30ff]/.test(t)) return 'anime';

  // ── Manga / 漫画 ──
  if (/漫画|manga|comic|同人志|同人誌|doujin|コミック|まんが/.test(t)) return 'manga';
  if (/\.(cbr|cbz)\b/.test(t)) return 'manga';

  // ── eBook / 电子书 ──
  if (/电子书|小说|ebook|kindle|文库|轻小说|light\s*novel/.test(t)) return 'ebook';
  if (/\.(epub|mobi|azw3?|fb2)\b/.test(t)) return 'ebook';

  // ── Music / 音乐 ──
  if (/专辑|album|discography|无损|lossless|hi-?res|演唱会|concert|live\s*(?:tour|album)/i.test(t)) return 'music';

  // ── Game / 游戏 ──
  // "游戏" alone is ambiguous (鱿鱼游戏=TV, 权力的游戏=TV), require stronger context
  if (/\bgame\b|switch|ps[345]|xbox|nintendo|steam|gog\b|fitgirl|repack/i.test(t)) return 'game';
  if (/游戏/.test(t) && !/鱿鱼游戏|权力.*游戏|饥饿游戏|致命游戏|游戏人生|模仿游戏|电影|电视|剧/.test(t)) return 'game';

  // ── TV sub-types (specific regions) ──
  if (/美剧|american\s*(?:tv|drama|series)/i.test(t)) return 'tv_us';
  if (/日剧|日本电视|japanese\s*(?:tv|drama)|jdrama/i.test(t)) return 'tv_jp';
  if (/韩剧|韩国电视|korean\s*(?:tv|drama)|kdrama/i.test(t)) return 'tv_kr';
  if (/国产剧|大陆剧|内地剧|国产电视|华语剧/.test(t)) return 'tv_cn';

  // ── Variety / 综艺 ──
  if (/综艺|variety|真人秀|reality\s*show|脱口秀|talk\s*show/i.test(t)) return 'variety';

  // ── Documentary / 纪录片 ──
  if (/纪录片|纪实|documentary|bbc.{0,10}(?:纪录|记录)|national\s*geographic/i.test(t)) return 'documentary';

  // ── Generic TV (S01E01, 第X季/集) ──
  if (/s\d{2}e\d{2}/i.test(t)) return 'tv';
  if (/第.{1,4}[季部]|season\s*\d/i.test(t)) return 'tv';
  if (/连续剧|电视剧|剧集|tvshow|tv\s*series/i.test(t)) return 'tv';
  if (/第.{1,4}集|episode\s*\d|ep\.?\s*\d/i.test(t)) return 'tv';

  // ── Movie / 电影 ──
  if (/电影|movie|film/i.test(t)) return 'movie';
  if (/[a-z]{2,6}-?\d{3,5}/.test(t)) return 'movie'; // JAV codes
  // Year + quality hints without S/E → likely a movie
  if (/(19|20)\d{2}.{0,20}(1080p|720p|2160p|4k|bluray|blu-?ray|remux|web-?dl)/i.test(t)
    && !/s\d{2}e\d{2}/i.test(t) && !/第.{1,4}[季集部]/i.test(t)) return 'movie';

  // ═══════════════════════════════════════════════════════════════════
  // TIER 2: Format-based detection (from file extension / encoding hints)
  // ═══════════════════════════════════════════════════════════════════

  // ── Video formats ──
  if (/\.(mp4|mkv|avi|rmvb|rm|wmv|flv|mov|ts|m4v|webm|mpg|mpeg|vob|m2ts|mts|divx|3gp|3g2|f4v|ogv|asf|tp|trp)\b/.test(t)) return 'video';
  if (/1080p|720p|2160p|4k|bluray|blu-ray|web-?dl|remux|x264|x265|hevc|hdtv|bdrip|brrip|dvdrip|hdrip|webrip|cam-?rip/.test(t)) return 'video';

  // ── Audio formats ──
  if (/\.(mp3|flac|ape|wav|aac|ogg|wma|m4a|opus|alac|dsd|dsf|dff|tak|tta|aiff?|ac3|dts|mka|pcm|cue)\b/.test(t)) return 'audio';

  // ── Archive formats ──
  if (/\.(zip|rar|7z|tar|gz|bz2|xz|zst|lz|lzma|cab|iso|img|bin|nrg|mdf|mds|udf)\b/.test(t)) return 'archive';

  // ── Image formats ──
  if (/\.(jpg|jpeg|png|gif|bmp|webp|tiff?|psd|raw|svg|heic|heif|avif|ico|cr2|nef|arw|dng|jxl)\b/.test(t)) return 'image';
  if (/写真|画集|图集|photoset|imageset|壁纸|wallpaper/.test(t)) return 'image';

  // ── Document formats ──
  if (/\.(pdf|txt|doc|docx|rtf|srt|ass|ssa|djvu|chm|xls|xlsx|ppt|pptx|csv|odt|ods|odp)\b/.test(t)) return 'document';
  if (/字幕|subtitle/.test(t)) return 'document';

  // ── Software / App ──
  if (/\.(exe|dmg|apk|msi|deb|rpm|appimage|pkg|ipa|xapk|snap|flatpak)\b/.test(t)) return 'software';
  if (/软件|crack|keygen|portable|安装包|patch|activat/.test(t)) return 'software';

  return 'other';
}

/** Extract tag-like tokens from the title. */
export function extractTags(title: string): string[] {
  const tags: string[] = [];
  const patterns: [RegExp, string][] = [
    [/4k|2160p/i, '4K'],
    [/1080p/i, '1080P'],
    [/720p/i, '720P'],
    [/bluray|blu-ray/i, 'BluRay'],
    [/web-?dl/i, 'WEB-DL'],
    [/remux/i, 'REMUX'],
    [/hdr/i, 'HDR'],
    [/dolby|atmos|dts/i, 'DTS'],
    [/hevc|x265|h\.?265/i, 'HEVC'],
    [/中[文字]|国[语粤]|简体|繁体/i, '中文'],
  ];
  for (const [re, label] of patterns) {
    if (re.test(title) && !tags.includes(label)) tags.push(label);
  }
  return tags.slice(0, 4);
}

/** Format bytes to human-readable. */
export function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let idx = 0;
  let val = bytes;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx++;
  }
  return `${val.toFixed(val >= 100 ? 0 : 1)} ${units[idx]}`;
}

/** Parse size string — extract only the valid size portion (e.g. "14.61 GB"). */
export function parseSizeLabel(sizeStr?: string): string {
  if (!sizeStr) return '';
  // Extract the first valid size pattern, ignoring surrounding junk/newlines
  const m = sizeStr.match(/(\d+\.?\d*)\s*(TB|GB|MB|KB|TiB|GiB|MiB|KiB|bytes?)\b/i);
  return m ? m[0] : '';
}

function kindLabelText(kind: Kind, t?: Translations): string {
  if (t) {
    const map: Record<Kind, string> = {
      // Tier 1
      movie: t.kindMovie, tv_us: t.kindTvUs, tv_jp: t.kindTvJp,
      tv_kr: t.kindTvKr, tv_cn: t.kindTvCn, tv: t.kindTv,
      anime: t.kindAnime, variety: t.kindVariety, documentary: t.kindDocumentary,
      music: t.kindMusic, game: t.kindGame, ebook: t.kindEbook, manga: t.kindManga,
      // Tier 2
      video: t.kindVideo, audio: t.kindAudio, archive: t.kindArchive,
      image: t.kindImage, document: t.kindDocument, software: t.kindSoftware, other: t.kindOther,
    };
    return map[kind];
  }
  const fallback: Record<Kind, string> = {
    // Tier 1
    movie: '电影', tv_us: '美剧', tv_jp: '日剧', tv_kr: '韩剧',
    tv_cn: '国产剧', tv: '剧集', anime: '动漫', variety: '综艺',
    documentary: '纪录片', music: '音乐', game: '游戏', ebook: '电子书', manga: '漫画',
    // Tier 2
    video: '视频', audio: '音频', archive: '压缩包',
    image: '图片', document: '文档', software: '程序', other: '其他',
  };
  return fallback[kind];
}

/** Compute relevance score: how well does the title match the query? */
export function computeRelevance(title: string, query: string): number {
  if (!query || !title) return 0;
  const tl = title.toLowerCase();
  const ql = query.toLowerCase().trim();
  // exact match
  if (tl.includes(ql)) return 100;
  // keyword match
  const kws = ql.split(/[\s_\-+]+/).filter(w => w.length >= 1);
  if (kws.length === 0) return 0;
  let matched = 0;
  for (const kw of kws) {
    if (tl.includes(kw)) matched++;
  }
  const ratio = matched / kws.length;
  // Penalty: very short/generic titles
  const lenPenalty = title.length < 8 ? -30 : 0;
  return Math.round(ratio * 80) + lenPenalty;
}

/** Validate and clean a date string. Extract only the first valid date. */
function cleanDateLabel(raw?: string): string {
  if (!raw) return '';
  // Flatten newlines to spaces
  const s = raw.replace(/[\r\n]+/g, ' ').trim();
  // Reject pure numbers (seeders/leechers/fileCount leaking in)
  if (/^\d{1,4}$/.test(s)) return '';
  // Reject time-only (HH:MM or HH:MM:SS)
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) return '';
  // Extract first YYYY-MM-DD or M/D/YYYY pattern
  const isoDate = s.match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
  if (isoDate) return isoDate[1];
  const usDate = s.match(/(\d{1,2}[-/]\d{1,2}[-/]\d{4})/);
  if (usDate) return usDate[1];
  // English month name
  const enDate = s.match(/((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4})/i);
  if (enDate) return enDate[1];
  return '';
}

/** Build a ResultCardModel from a raw SearchResult. */
export function toResultCardModel(r: SearchResult, index: number, query?: string, t?: Translations): ResultCardModel {
  const kind = guessKind(r.title);
  const dateLabel = cleanDateLabel(r.date);
  const fmtFileCount = t ? t.fileCount : (n: number) => `文件数 ${n}`;

  // Detect if date field was actually a file count (pure small number)
  let fileCountLabel = r.fileCount ? fmtFileCount(r.fileCount) : '';
  if (!fileCountLabel && r.date && /^\d{1,4}$/.test(r.date.trim())) {
    const n = parseInt(r.date.trim(), 10);
    if (n > 0 && n < 10000) fileCountLabel = fmtFileCount(n);
  }

  const dr = r as any;
  return {
    id: `${index}-${r.magnet.slice(-8)}`,
    title: r.title,
    magnet: r.magnet,
    kind,
    kindLabel: kindLabelText(kind, t),
    sizeLabel: parseSizeLabel(r.size),
    dateLabel,
    fileCountLabel,
    tags: extractTags(r.title),
    theme: KIND_THEMES[kind],
    relevance: computeRelevance(r.title, query || ''),
    sourceName: r.site_name || r.source || '',
    sourceCount: dr.sourceCount || 1,
    sourceNames: dr.sourceNames || [r.site_name || r.source || ''],
  };
}
