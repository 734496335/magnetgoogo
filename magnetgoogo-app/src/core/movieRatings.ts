import type { MovieFeedItem } from './resourceFeedProtocol';

export const FEATURED_SCORE_THRESHOLD = 6.0;
export const HIGH_SCORE_THRESHOLD = 8.0;
export const FEATURED_PERCENT_THRESHOLD = 60;
export const HIGH_PERCENT_THRESHOLD = 80;

export const MEDIA_LIST_SORT_POLICY = 'release-rank' as const;
export const MEDIA_RECOMMENDATION_POLICY = 'server-recommended' as const;
export const MOVIE_RATING_DISPLAY_ORDER = ['douban', 'imdb', 'rotten_tomatoes', 'bangumi'] as const;
export const MOVIE_PRIMARY_SCORE_PRIORITY = ['douban', 'imdb', 'bangumi', 'rotten_tomatoes'] as const;

export type MovieScoreTier = 'featured' | 'high' | null;
export type MovieRatingKey = typeof MOVIE_RATING_DISPLAY_ORDER[number];
export type MovieRatingSource = '豆瓣' | 'IMDb' | '烂番茄' | 'Bangumi';

type MovieRatingInput = Partial<Pick<
  MovieFeedItem,
  'imdb_rating' | 'douban_rating' | 'rotten_tomatoes_rating' | 'bangumi_rating'
>>;

export interface VisibleMovieRating {
  key: MovieRatingKey;
  source: MovieRatingSource;
  value: number;
  displayValue: string;
  normalizedValue: number;
  tier: Exclude<MovieScoreTier, null> | null;
  isPrimary: boolean;
}

interface RatingDefinition {
  key: MovieRatingKey;
  source: MovieRatingSource;
  value: number | null | undefined;
  scale: 10 | 100;
}

function validRating(value: number | null | undefined, scale: 10 | 100): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= scale
    ? value
    : null;
}

function scoreTier(value: number, scale: 10 | 100): MovieScoreTier {
  const highThreshold = scale === 100 ? HIGH_PERCENT_THRESHOLD : HIGH_SCORE_THRESHOLD;
  const featuredThreshold = scale === 100 ? FEATURED_PERCENT_THRESHOLD : FEATURED_SCORE_THRESHOLD;
  if (value >= highThreshold) return 'high';
  if (value >= featuredThreshold) return 'featured';
  return null;
}

function ratingDefinitions(item: MovieRatingInput): RatingDefinition[] {
  return [
    { key: 'douban', source: '豆瓣', value: item.douban_rating, scale: 10 },
    { key: 'imdb', source: 'IMDb', value: item.imdb_rating, scale: 10 },
    { key: 'rotten_tomatoes', source: '烂番茄', value: item.rotten_tomatoes_rating, scale: 100 },
    { key: 'bangumi', source: 'Bangumi', value: item.bangumi_rating, scale: 10 },
  ];
}

function primaryRatingKey(definitions: RatingDefinition[]): MovieRatingKey | null {
  for (const key of MOVIE_PRIMARY_SCORE_PRIORITY) {
    const definition = definitions.find((item) => item.key === key);
    if (definition && validRating(definition.value, definition.scale) !== null) return key;
  }
  return null;
}

export function getVisibleMovieRatings(item: MovieRatingInput): VisibleMovieRating[] {
  const definitions = ratingDefinitions(item);
  const primaryKey = primaryRatingKey(definitions);
  return definitions.flatMap((definition) => {
    const value = validRating(definition.value, definition.scale);
    if (value === null) return [];
    const isPrimary = definition.key === primaryKey;
    return [{
      key: definition.key,
      source: definition.source,
      value,
      displayValue: definition.scale === 100
        ? `${Number.isInteger(value) ? value : value.toFixed(1)}%`
        : value.toFixed(1),
      normalizedValue: definition.scale === 100 ? value / 10 : value,
      tier: isPrimary ? scoreTier(value, definition.scale) : null,
      isPrimary,
    }];
  });
}

export function getPrimaryMovieRating(item: MovieRatingInput): VisibleMovieRating | null {
  return getVisibleMovieRatings(item).find((rating) => rating.isPrimary) ?? null;
}

export function getMovieScoreTier(item: MovieRatingInput): MovieScoreTier {
  return getPrimaryMovieRating(item)?.tier ?? null;
}

export function compareMediaFeedRank(
  left: Pick<MovieFeedItem, 'rank' | 'movie_id'>,
  right: Pick<MovieFeedItem, 'rank' | 'movie_id'>,
): number {
  return left.rank - right.rank || left.movie_id.localeCompare(right.movie_id);
}

export function isServerRecommendedMovie(item: Pick<MovieFeedItem, 'recommended'>): boolean {
  return item.recommended === true;
}
