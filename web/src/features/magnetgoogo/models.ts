import type { LucideIcon } from 'lucide-react';
import { Film, MonitorPlay, Sparkles, Tv2 } from 'lucide-react';
import { MagnetResult } from '@/core/types';

export type SiteStatus = 'searching' | 'done' | 'error';
export type ResourceKind = 'movie' | 'series' | 'anime' | 'document' | 'other';

export interface ResultCardModel {
  id: string;
  title: string;
  kind: ResourceKind;
  kindLabel: string;
  sizeLabel: string;
  fileCountLabel: string;
  tags: string[];
  magnet: string;
  theme: {
    icon: LucideIcon;
    tileClassName: string;
    iconClassName: string;
    pillClassNames: string[];
  };
}

export function kindLabelText(kind: ResourceKind): string {
  switch (kind) {
    case 'movie': return '电影';
    case 'series': return '剧集';
    case 'anime': return '动漫';
    case 'document': return '文档';
    default: return '资源';
  }
}

export function pillClassForTag(tag: string): string {
  const upper = tag.toUpperCase();
  if (/中文|双语|字幕/.test(tag)) return 'bg-[#eefaf0] text-[#28ae62]';
  if (upper === 'HDR') return 'bg-[#fff8e9] text-[#ffad17]';
  if (upper === 'HEVC') return 'bg-[#f4efff] text-[#8659ff]';
  if (upper === 'REMUX') return 'bg-[#eefaf0] text-[#28ae62]';
  return 'bg-[#edf4ff] text-[#2f6eff]';
}

export function parseSize(input: string): number {
  if (!input) return 0;
  const match = input.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB|B)/i);
  if (!match) return 0;
  const value = Number.parseFloat(match[1]);
  const unit = match[2].toUpperCase().replace('IB', 'B');
  if (unit === 'TB') return value * 1e12;
  if (unit === 'GB') return value * 1e9;
  if (unit === 'MB') return value * 1e6;
  if (unit === 'KB') return value * 1e3;
  return value;
}

export function formatSize(input: string): string {
  if (!input) return '';
  const match = input.match(/([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB|B)/i);
  if (!match) return input;
  const value = Number.parseFloat(match[1]);
  const unit = match[2].toUpperCase().replace('IB', 'B');
  const digits = value >= 10 ? 0 : 1;
  return `${value.toFixed(digits)} ${unit}`;
}

export function guessKind(title: string): ResourceKind {
  const lower = title.toLowerCase();
  if (/anime|动画|動漫|番剧|ova/i.test(lower)) return 'anime';
  if (/s\d{1,2}e\d{1,2}|season|episode|第.?季|全集|完结/i.test(lower)) return 'series';
  if (/pdf|epub|mobi|document|ebook/i.test(lower)) return 'document';
  if (/2160p|1080p|720p|bluray|web-?dl|webrip|remux|hdr|dv|电影|movie/i.test(lower)) return 'movie';
  return 'other';
}

export function extractTags(title: string): string[] {
  const lower = title.toLowerCase();
  const tags: string[] = [];

  if (/4k|2160p|uhd/.test(lower)) tags.push('4K');
  else if (/1080p/.test(lower)) tags.push('1080P');
  else if (/720p/.test(lower)) tags.push('720P');

  if (/web-?dl|webdl|webrip/.test(lower)) tags.push('WEB-DL');
  else if (/remux/.test(lower)) tags.push('REMUX');
  else if (/blu-?ray|bluray|bdrip|bdmv/.test(lower)) tags.push('BluRay');

  if (/hdr/.test(lower)) tags.push('HDR');
  if (/hevc|x265/.test(lower)) tags.push('HEVC');
  if (/中字|中文字幕|chs|cht|sub|subtitle/.test(lower)) tags.push('中文字幕');
  if (/双语/.test(lower)) tags.push('双语字幕');

  return tags.slice(0, 4);
}

function fallbackTags(kind: ResourceKind, size: string): string[] {
  const bytes = parseSize(size);
  if (kind === 'series') {
    return bytes >= 12e9 ? ['4K', 'WEB-DL', 'HDR'] : ['1080P', 'WEB-DL'];
  }
  if (kind === 'movie') {
    return bytes >= 18e9 ? ['4K', 'BluRay', 'HDR'] : ['1080P', 'BluRay'];
  }
  if (kind === 'anime') {
    return ['1080P', 'WEB-DL'];
  }
  return bytes >= 8e9 ? ['1080P', 'WEB-DL'] : ['WEB-DL'];
}

export function themeForKind(kind: ResourceKind) {
  if (kind === 'movie') {
    return {
      icon: Film,
      tileClassName: 'from-[#fff1f3] via-[#fff7f0] to-[#fffaf6]',
      iconClassName: 'text-[#ff6a4d]',
      pillClassNames: [
        'bg-[#fff2ef] text-[#ff6a4d]',
        'bg-[#edf4ff] text-[#2f6eff]',
        'bg-[#fff8e9] text-[#ffad17]',
        'bg-[#eefaf0] text-[#28ae62]',
      ],
    };
  }
  if (kind === 'series') {
    return {
      icon: Tv2,
      tileClassName: 'from-[#effbf1] via-[#f8fff8] to-[#f9fffb]',
      iconClassName: 'text-[#26c26b]',
      pillClassNames: [
        'bg-[#eefaf0] text-[#28ae62]',
        'bg-[#edf4ff] text-[#2f6eff]',
        'bg-[#eefaf0] text-[#28ae62]',
        'bg-[#f4efff] text-[#8659ff]',
      ],
    };
  }
  if (kind === 'anime') {
    return {
      icon: Sparkles,
      tileClassName: 'from-[#f6efff] via-[#fdf7ff] to-[#fffafe]',
      iconClassName: 'text-[#a35bff]',
      pillClassNames: [
        'bg-[#f3ecff] text-[#9658ff]',
        'bg-[#edf4ff] text-[#2f6eff]',
        'bg-[#eefaf0] text-[#28ae62]',
        'bg-[#fff2ef] text-[#ff6a4d]',
      ],
    };
  }
  return {
    icon: MonitorPlay,
    tileClassName: 'from-[#fff7ea] via-[#fffdf6] to-[#fffcf4]',
    iconClassName: 'text-[#ff9f0a]',
    pillClassNames: [
      'bg-[#fff8e9] text-[#ffad17]',
      'bg-[#edf4ff] text-[#2f6eff]',
      'bg-[#eefaf0] text-[#28ae62]',
      'bg-[#f4efff] text-[#8659ff]',
    ],
  };
}

export function dedupeResults(existing: MagnetResult[], incoming: MagnetResult[]) {
  const seen = new Set(
    existing.map((item) => {
      const match = item.magnet.match(/btih:([a-fA-F0-9]+)/i);
      return match ? match[1].toLowerCase() : item.magnet;
    }),
  );

  const next = [...existing];
  for (const item of incoming) {
    const match = item.magnet.match(/btih:([a-fA-F0-9]+)/i);
    const key = match ? match[1].toLowerCase() : item.magnet;
    if (seen.has(key)) continue;
    seen.add(key);
    next.push(item);
  }
  return next;
}

export function sortResults(results: MagnetResult[]) {
  return [...results].sort((a, b) => {
    const relevanceA = a.relevance ?? 0;
    const relevanceB = b.relevance ?? 0;
    if (relevanceA !== relevanceB) return relevanceB - relevanceA;
    const sizeA = parseSize(a.size);
    const sizeB = parseSize(b.size);
    if (sizeA !== sizeB) return sizeB - sizeA;
    return (b.seeders ?? 0) - (a.seeders ?? 0);
  });
}

export function toResultCardModel(result: MagnetResult): ResultCardModel {
  const kind = guessKind(result.title);
  const formattedSize = formatSize(result.size);
  const detectedTags = extractTags(result.title);

  return {
    id: result.magnet,
    title: result.title,
    kind,
    sizeLabel: formattedSize || '',
    kindLabel: kindLabelText(kind),
    fileCountLabel:
      typeof result.file_count === 'number' && result.file_count > 0 ? `文件数 ${result.file_count}` : '',
    tags: detectedTags.length > 0 ? detectedTags : fallbackTags(kind, result.size),
    magnet: result.magnet,
    theme: themeForKind(kind),
  };
}
