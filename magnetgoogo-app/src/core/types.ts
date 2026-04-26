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

export type Kind = 'video' | 'audio' | 'archive' | 'image' | 'document' | 'software' | 'other';

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
  video:    { iconName: 'play-circle-outline',    tileColors: ['#ffeef0', '#ffd6dc'], iconColor: '#e85d75' },
  audio:    { iconName: 'musical-notes-outline',  tileColors: ['#fff3e0', '#ffe0b2'], iconColor: '#f57c00' },
  archive:  { iconName: 'file-tray-stacked-outline', tileColors: ['#e3f2fd', '#bbdefb'], iconColor: '#1e88e5' },
  image:    { iconName: 'image-outline',          tileColors: ['#f3e5f5', '#e1bee7'], iconColor: '#8e24aa' },
  document: { iconName: 'document-text-outline',  tileColors: ['#fff8e1', '#ffecb3'], iconColor: '#ffa000' },
  software: { iconName: 'cube-outline',           tileColors: ['#e8f5e9', '#c8e6c9'], iconColor: '#43a047' },
  other:    { iconName: 'help-circle-outline',    tileColors: ['#f5f5f5', '#e0e0e0'], iconColor: '#757575' },
};

/** Detect file format kind from title (by file extension or format hints).
 *  If multiple files, the largest is typically named in the title. */
export function guessKind(title: string): Kind {
  const t = title.toLowerCase();

  // ── Video formats ──
  if (/\.(mp4|mkv|avi|rmvb|wmv|flv|mov|ts|m4v|webm|mpg|mpeg|vob|m2ts)\b/.test(t)) return 'video';
  if (/1080p|720p|2160p|4k|bluray|blu-ray|web-?dl|remux|x264|x265|hevc|hdtv|bdrip|brrip|dvdrip/.test(t)) return 'video';

  // ── Audio formats ──
  if (/\.(mp3|flac|ape|wav|aac|ogg|wma|m4a|opus|alac|dsd|dsf)\b/.test(t)) return 'audio';
  if (/专辑|album|\bflac\b|\bape\b|\bmp3\b|无损/.test(t)) return 'audio';

  // ── Archive formats ──
  if (/\.(zip|rar|7z|tar|gz|bz2|xz|iso|img|bin|cue)\b/.test(t)) return 'archive';

  // ── Image formats ──
  if (/\.(jpg|jpeg|png|gif|bmp|webp|tiff?|psd|raw|svg|heic)\b/.test(t)) return 'image';
  if (/写真|画集|图集|photoset|imageset/.test(t)) return 'image';

  // ── Document formats ──
  if (/\.(pdf|epub|mobi|azw3?|txt|doc|docx|rtf|srt|ass|ssa|djvu|chm)\b/.test(t)) return 'document';
  if (/电子书|小说|字幕|subtitle/.test(t)) return 'document';

  // ── Software / App ──
  if (/\.(exe|dmg|apk|msi|deb|rpm|appimage)\b/.test(t)) return 'software';
  if (/软件|crack|keygen|portable|安装包/.test(t)) return 'software';

  // ── Fallback heuristics (no extension found) ──
  // Video is the most common torrent type, so if we see video-related keywords...
  if (/s\d{2}e\d{2}|第.+[季集]|连续剧|美剧|韩剧|日剧|电影|movie|film/.test(t)) return 'video';
  if (/动[漫画]|anime|ova|oad/.test(t)) return 'video';
  if (/[a-z]{2,6}-?\d{3,5}/.test(t)) return 'video'; // JAV codes are video
  if (/游戏|game|switch|ps[345]|xbox/.test(t)) return 'archive'; // games are usually archives

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
      video: t.kindVideo, audio: t.kindAudio, archive: t.kindArchive,
      image: t.kindImage, document: t.kindDocument, software: t.kindSoftware, other: t.kindOther,
    };
    return map[kind];
  }
  const fallback: Record<Kind, string> = {
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
