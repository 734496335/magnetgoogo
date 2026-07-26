import type { MovieFeedItem } from './resourceFeedProtocol';

export const FEATURED_SCORE_THRESHOLD = 6.0;
export const HIGH_SCORE_THRESHOLD = 8.0;

export type MovieScoreTier = 'featured' | 'high' | null;

export interface VisibleMovieRating {
  source: 'IMDb' | '豆瓣';
  value: number;
  tier: Exclude<MovieScoreTier, null> | null;
}

function validRating(value: number | null): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= 10
    ? value
    : null;
}

export function getVisibleMovieRatings(
  item: Pick<MovieFeedItem, 'imdb_rating' | 'douban_rating'>,
): VisibleMovieRating[] {
  const imdb = validRating(item.imdb_rating);
  const douban = validRating(item.douban_rating);
  const ratings: VisibleMovieRating[] = [];
  const tierFor = (value: number): VisibleMovieRating['tier'] => {
    if (value >= HIGH_SCORE_THRESHOLD) return 'high';
    if (value >= FEATURED_SCORE_THRESHOLD) return 'featured';
    return null;
  };
  if (douban !== null) ratings.push({ source: '豆瓣', value: douban, tier: tierFor(douban) });
  if (imdb !== null) ratings.push({ source: 'IMDb', value: imdb, tier: tierFor(imdb) });
  return ratings;
}

export function getMovieScoreTier(
  item: Pick<MovieFeedItem, 'imdb_rating' | 'douban_rating'>,
): MovieScoreTier {
  const ratings = getVisibleMovieRatings(item);
  if (ratings.some((rating) => rating.tier === 'high')) return 'high';
  if (ratings.some((rating) => rating.tier === 'featured')) return 'featured';
  return null;
}
