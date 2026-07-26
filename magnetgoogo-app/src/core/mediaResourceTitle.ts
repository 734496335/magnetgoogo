import type { MovieResource } from './resourceFeedProtocol';

const GENERIC_RESOURCE_TITLE = /^(?:4k|2160p?|1080p?|720p|480p|hd|bd|web-?dl|磁力|magnet)$/i;
const QUALITY_TOKEN = /\b(?:4k|2160p?|1080p?|720p|480p|hd|bd|web-?dl|webrip|bluray)\b/i;

const CHINESE_NUMBER_DIGITS: Record<string, number> = {
  零: 0,
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
};

export interface ResourceEpisodeIdentity {
  season: number;
  episodeStart: number | null;
  episodeEnd: number | null;
  kind: 'episode' | 'season-pack';
  label: string;
  source: 'title' | 'magnet';
}

function parseChineseNumber(value: string): number | null {
  if (/^\d+$/.test(value)) return Number(value);
  if (value === '十') return 10;
  if (value.includes('十')) {
    const [tensText, onesText] = value.split('十');
    const tens = tensText ? CHINESE_NUMBER_DIGITS[tensText] : 1;
    const ones = onesText ? CHINESE_NUMBER_DIGITS[onesText] : 0;
    if (tens === undefined || ones === undefined) return null;
    return tens * 10 + ones;
  }
  return CHINESE_NUMBER_DIGITS[value] ?? null;
}

function explicitSeasonFromText(value: string): number | null {
  const arabic = value.match(/第\s*(\d{1,2})\s*季/);
  if (arabic) return Number(arabic[1]);
  const chinese = value.match(/第\s*([零一二两三四五六七八九十]+)\s*季/);
  if (chinese) return parseChineseNumber(chinese[1]);
  const english = value.match(/\b(?:Season\s*|S)(\d{1,2})(?:E\d{1,3})?\b/i);
  if (english) return Number(english[1]);
  return null;
}

export function inferSeriesSeason(title: string, seasonNumber: number | null | undefined): number {
  return explicitSeasonFromText(title) ?? seasonNumber ?? 1;
}

export function seriesStatusForDisplay(
  title: string,
  seasonNumber: number | null | undefined,
  rawStatus: string | null | undefined,
): string | null {
  const status = rawStatus?.trim() ?? '';
  if (!status) return null;
  const titleSeason = explicitSeasonFromText(title);
  const statusSeason = explicitSeasonFromText(status);
  if (titleSeason !== null && statusSeason !== null && titleSeason !== statusSeason) return null;
  if (titleSeason === null && seasonNumber && statusSeason !== null && seasonNumber !== statusSeason) return null;
  return status;
}

export function decodeMagnetDisplayName(url: string): string | null {
  const match = url.match(/[?&]dn=([^&]+)/i);
  if (!match?.[1]) return null;
  try {
    return decodeURIComponent(match[1].replace(/\+/g, ' ')).trim() || null;
  } catch {
    return match[1].replace(/\+/g, ' ').trim() || null;
  }
}

function episodeIdentityFromName(name: string, fallbackSeason: number): Omit<ResourceEpisodeIdentity, 'source'> | null {
  const seasonEpisode = name.match(/\bS(\d{1,2})E(\d{1,3})(?:[-_. ]?E?(\d{1,3}))?\b/i);
  if (seasonEpisode) {
    const season = Number(seasonEpisode[1]);
    const episodeStart = Number(seasonEpisode[2]);
    const episodeEnd = Number(seasonEpisode[3] ?? seasonEpisode[2]);
    return {
      season,
      episodeStart,
      episodeEnd,
      kind: 'episode',
      label: episodeEnd > episodeStart
        ? `S${String(season).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}-E${String(episodeEnd).padStart(2, '0')}`
        : `S${String(season).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}`,
    };
  }

  const chineseEpisode = name.match(/第\s*(\d{1,3})(?:\s*[-–至到]\s*(\d{1,3}))?\s*集/);
  if (chineseEpisode) {
    const episodeStart = Number(chineseEpisode[1]);
    const episodeEnd = Number(chineseEpisode[2] ?? chineseEpisode[1]);
    return {
      season: fallbackSeason,
      episodeStart,
      episodeEnd,
      kind: 'episode',
      label: episodeEnd > episodeStart
        ? `S${String(fallbackSeason).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}-E${String(episodeEnd).padStart(2, '0')}`
        : `S${String(fallbackSeason).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}`,
    };
  }

  const compactEpisode = name.match(/\bE(?:P)?(\d{1,3})(?:[-_. ]?E?(\d{1,3}))?\b/i);
  if (compactEpisode) {
    const episodeStart = Number(compactEpisode[1]);
    const episodeEnd = Number(compactEpisode[2] ?? compactEpisode[1]);
    return {
      season: fallbackSeason,
      episodeStart,
      episodeEnd,
      kind: 'episode',
      label: episodeEnd > episodeStart
        ? `S${String(fallbackSeason).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}-E${String(episodeEnd).padStart(2, '0')}`
        : `S${String(fallbackSeason).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}`,
    };
  }

  const leadingEpisode = name.match(/^(\d{1,3})(?:\s*[-–至到]\s*(\d{1,3}))?(?=[._ -]*(?:1080|2160|720|4k|hd|bd|web|$))/i);
  if (leadingEpisode) {
    const episodeStart = Number(leadingEpisode[1]);
    const episodeEnd = Number(leadingEpisode[2] ?? leadingEpisode[1]);
    return {
      season: fallbackSeason,
      episodeStart,
      episodeEnd,
      kind: 'episode',
      label: episodeEnd > episodeStart
        ? `S${String(fallbackSeason).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}-E${String(episodeEnd).padStart(2, '0')}`
        : `S${String(fallbackSeason).padStart(2, '0')}E${String(episodeStart).padStart(2, '0')}`,
    };
  }

  const seasonPack = name.match(/\b(?:S|Season[ ._-]*)(\d{1,2})(?!\s*E\d)/i);
  if (seasonPack && /complete|full|全集|全季|打包|season/i.test(name)) {
    const season = Number(seasonPack[1]);
    return {
      season,
      episodeStart: null,
      episodeEnd: null,
      kind: 'season-pack',
      label: `S${String(season).padStart(2, '0')} 全季`,
    };
  }

  if (/全集|全季|全集打包|整季/.test(name)) {
    return {
      season: fallbackSeason,
      episodeStart: null,
      episodeEnd: null,
      kind: 'season-pack',
      label: `S${String(fallbackSeason).padStart(2, '0')} 全季`,
    };
  }

  return null;
}

export function resourceEpisodeIdentity(
  resource: MovieResource,
  fallbackSeason = 1,
): ResourceEpisodeIdentity | null {
  const rawTitle = resource.display_title.trim();
  const magnetName = decodeMagnetDisplayName(resource.url) ?? '';
  const magnetIdentity = episodeIdentityFromName(magnetName, fallbackSeason);
  const titleIdentity = episodeIdentityFromName(rawTitle, fallbackSeason);

  if (magnetIdentity?.kind === 'episode') return { ...magnetIdentity, source: 'magnet' };
  if (titleIdentity?.kind === 'episode') return { ...titleIdentity, source: 'title' };
  if (magnetIdentity) return { ...magnetIdentity, source: 'magnet' };
  if (titleIdentity) return { ...titleIdentity, source: 'title' };
  return null;
}

function qualityRank(resource: MovieResource): number {
  const text = `${resource.display_title} ${resource.quality_tags.join(' ')}`.toLowerCase();
  if (/4k|2160/.test(text)) return 4;
  if (/1080/.test(text)) return 3;
  if (/720/.test(text)) return 2;
  if (/480/.test(text)) return 1;
  return 0;
}

export function compareMediaResources(
  left: MovieResource,
  right: MovieResource,
  fallbackSeason = 1,
): number {
  const leftIdentity = resourceEpisodeIdentity(left, fallbackSeason);
  const rightIdentity = resourceEpisodeIdentity(right, fallbackSeason);

  if (leftIdentity && !rightIdentity) return -1;
  if (!leftIdentity && rightIdentity) return 1;
  if (leftIdentity && rightIdentity) {
    if (leftIdentity.season !== rightIdentity.season) return leftIdentity.season - rightIdentity.season;
    if (leftIdentity.kind !== rightIdentity.kind) return leftIdentity.kind === 'episode' ? -1 : 1;
    const leftStart = leftIdentity.episodeStart ?? Number.MAX_SAFE_INTEGER;
    const rightStart = rightIdentity.episodeStart ?? Number.MAX_SAFE_INTEGER;
    if (leftStart !== rightStart) return leftStart - rightStart;
    const leftEnd = leftIdentity.episodeEnd ?? Number.MAX_SAFE_INTEGER;
    const rightEnd = rightIdentity.episodeEnd ?? Number.MAX_SAFE_INTEGER;
    if (leftEnd !== rightEnd) return leftEnd - rightEnd;
  }

  const qualityDifference = qualityRank(right) - qualityRank(left);
  if (qualityDifference !== 0) return qualityDifference;
  return resourceDisplayTitle(left, fallbackSeason).localeCompare(
    resourceDisplayTitle(right, fallbackSeason),
    'zh-CN',
    { numeric: true, sensitivity: 'base' },
  );
}

export function sortMediaResources(
  resources: MovieResource[],
  fallbackSeason = 1,
): MovieResource[] {
  return [...resources].sort((left, right) => compareMediaResources(left, right, fallbackSeason));
}

export function uniqueMagnetResources(resources: MovieResource[]): MovieResource[] {
  const seen = new Set<string>();
  return resources.filter((resource) => {
    const key = (resource.info_hash || resource.url).trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function magnetBatchText(resources: MovieResource[]): string {
  return uniqueMagnetResources(resources)
    .map((resource) => resource.url.trim())
    .filter((url) => /^magnet:\?/i.test(url))
    .join('\r\n');
}

function compactQualityLabel(resource: MovieResource, rawTitle: string): string {
  const tags = [...new Set(resource.quality_tags.map((tag) => tag.trim()).filter(Boolean))].slice(0, 3);
  if (tags.length > 0) return tags.join(' · ');
  return rawTitle.match(QUALITY_TOKEN)?.[0] ?? '';
}

export function resourceDisplayTitle(resource: MovieResource, fallbackSeason?: number): string {
  const rawTitle = resource.display_title.trim() || '磁力资源';
  const magnetName = decodeMagnetDisplayName(resource.url);

  if (fallbackSeason !== undefined) {
    const identity = resourceEpisodeIdentity(resource, fallbackSeason);
    if (identity) {
      const quality = compactQualityLabel(resource, rawTitle);
      return quality ? `${identity.label} · ${quality}` : identity.label;
    }
  }

  if (!GENERIC_RESOURCE_TITLE.test(rawTitle)) return rawTitle;
  if (!magnetName) return rawTitle;

  const identity = resourceEpisodeIdentity(resource, fallbackSeason ?? 1);
  if (identity) return `${identity.label} · ${rawTitle}`;
  return magnetName.length <= 96 ? magnetName : rawTitle;
}
