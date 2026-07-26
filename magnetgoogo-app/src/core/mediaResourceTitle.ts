import type { MovieResource } from './resourceFeedProtocol';

const GENERIC_RESOURCE_TITLE = /^(?:4k|2160p?|1080p?|720p|480p|hd|bd|web-?dl|磁力|magnet)$/i;

function decodeMagnetDisplayName(url: string): string | null {
  const match = url.match(/[?&]dn=([^&]+)/i);
  if (!match?.[1]) return null;
  try {
    return decodeURIComponent(match[1].replace(/\+/g, ' ')).trim() || null;
  } catch {
    return match[1].replace(/\+/g, ' ').trim() || null;
  }
}

function episodeLabelFromName(name: string): string | null {
  const seasonEpisode = name.match(/\bS(\d{1,2})E(\d{1,3})(?:[-_. ]?E?(\d{1,3}))?\b/i);
  if (seasonEpisode) {
    const season = seasonEpisode[1].padStart(2, '0');
    const firstEpisode = seasonEpisode[2].padStart(2, '0');
    const finalEpisode = seasonEpisode[3]?.padStart(2, '0');
    return finalEpisode
      ? `S${season}E${firstEpisode}-E${finalEpisode}`
      : `S${season}E${firstEpisode}`;
  }

  const chineseEpisode = name.match(/第\s*(\d{1,3})(?:\s*[-–至到]\s*(\d{1,3}))?\s*集/);
  if (chineseEpisode) {
    return chineseEpisode[2]
      ? `第${chineseEpisode[1]}-${chineseEpisode[2]}集`
      : `第${chineseEpisode[1]}集`;
  }

  const compactEpisode = name.match(/\bE(?:P)?(\d{1,3})(?:[-_. ]?E?(\d{1,3}))?\b/i);
  if (compactEpisode) {
    return compactEpisode[2]
      ? `E${compactEpisode[1].padStart(2, '0')}-E${compactEpisode[2].padStart(2, '0')}`
      : `E${compactEpisode[1].padStart(2, '0')}`;
  }

  return null;
}

export function resourceDisplayTitle(resource: MovieResource): string {
  const rawTitle = resource.display_title.trim();
  if (!GENERIC_RESOURCE_TITLE.test(rawTitle)) return rawTitle;

  const magnetName = decodeMagnetDisplayName(resource.url);
  if (!magnetName) return rawTitle;

  const episodeLabel = episodeLabelFromName(magnetName);
  if (episodeLabel) return `${episodeLabel} · ${rawTitle}`;

  return magnetName.length <= 96 ? magnetName : rawTitle;
}
