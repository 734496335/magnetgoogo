import type { MovieFeedItem } from './resourceFeedProtocol';

export const FEATURED_SCORE_THRESHOLD = 6.0;
export const HIGH_SCORE_THRESHOLD = 8.0;
export const ROTTEN_TOMATOES_FEATURED_THRESHOLD = 60;
export const ROTTEN_TOMATOES_HIGH_THRESHOLD = 80;

export type MovieScoreTier = 'featured' | 'high' | null;
export type MovieRatingSource = 'IMDb' | '豆瓣' | '烂番茄' | 'Bangumi';

export type MovieRatingFields = Pick<
  MovieFeedItem,
  'imdb_rating' | 'douban_rating' | 'rotten_tomatoes_rating' | 'bangumi_rating'
>;

export interface VisibleMovieRating {
  source: MovieRatingSource;
  value: number;
  displayValue: string;
  tier: Exclude<MovieScoreTier, null> | null;
}

function validRating(value: number | null, maximum: number): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= maximum
    ? value
    : null;
}

function tierFor(value: number, featured: number, high: number): VisibleMovieRating['tier'] {
  if (value >= high) return 'high';
  if (value >= featured) return 'featured';
  return null;
}

export function getVisibleMovieRatings(item: MovieRatingFields): VisibleMovieRating[] {
  const douban = validRating(item.douban_rating, 10);
  const imdb = validRating(item.imdb_rating, 10);
  const rottenTomatoes = validRating(item.rotten_tomatoes_rating, 100);
  const bangumi = validRating(item.bangumi_rating, 10);
  const ratings: VisibleMovieRating[] = [];

  if (douban !== null) {
    ratings.push({
      source: '豆瓣',
      value: douban,
      displayValue: douban.toFixed(1),
      tier: tierFor(douban, FEATURED_SCORE_THRESHOLD, HIGH_SCORE_THRESHOLD),
    });
  }
  if (imdb !== null) {
    ratings.push({
      source: 'IMDb',
      value: imdb,
      displayValue: imdb.toFixed(1),
      tier: tierFor(imdb, FEATURED_SCORE_THRESHOLD, HIGH_SCORE_THRESHOLD),
    });
  }
  if (rottenTomatoes !== null) {
    ratings.push({
      source: '烂番茄',
      value: rottenTomatoes,
      displayValue: `${Math.round(rottenTomatoes)}%`,
      tier: tierFor(
        rottenTomatoes,
        ROTTEN_TOMATOES_FEATURED_THRESHOLD,
        ROTTEN_TOMATOES_HIGH_THRESHOLD,
      ),
    });
  }
  if (bangumi !== null) {
    ratings.push({
      source: 'Bangumi',
      value: bangumi,
      displayValue: bangumi.toFixed(1),
      tier: tierFor(bangumi, FEATURED_SCORE_THRESHOLD, HIGH_SCORE_THRESHOLD),
    });
  }
  return ratings;
}

export function getMovieScoreTier(item: MovieRatingFields): MovieScoreTier {
  const ratings = getVisibleMovieRatings(item);
  if (ratings.some((rating) => rating.tier === 'high')) return 'high';
  if (ratings.some((rating) => rating.tier === 'featured')) return 'featured';
  return null;
}
