import React, { memo } from 'react';
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import type { Colors } from '../core/ThemeContext';
import { getVisibleMovieRatings } from '../core/movieRatings';
import type { MovieFeedItem } from '../core/resourceFeedProtocol';

interface MovieTagRowProps {
  item: Pick<
    MovieFeedItem,
    'imdb_rating' | 'douban_rating' | 'rotten_tomatoes_rating' | 'bangumi_rating'
  >;
  colors: Colors;
  qualityTags?: string[];
  compact?: boolean;
  centered?: boolean;
  ratingVariant?: 'chips' | 'detail';
  style?: StyleProp<ViewStyle>;
}

export const MovieTagRow = memo(function MovieTagRow({
  item,
  colors,
  qualityTags = [],
  compact = false,
  centered = false,
  ratingVariant = 'chips',
  style,
}: MovieTagRowProps) {
  const ratings = getVisibleMovieRatings(item);
  const tags = qualityTags.filter(Boolean);
  if (ratings.length === 0 && tags.length === 0) return null;

  return (
    <View style={[styles.container, compact && styles.containerCompact, style]}>
      {ratings.length > 0 && (
        <View
          style={[
            styles.row,
            ratingVariant === 'detail' && styles.ratingGrid,
            centered && styles.rowCentered,
          ]}
        >
          {ratings.map((rating) => {
            const backgroundColor = rating.tier === 'high'
              ? '#fee2e2'
              : rating.tier === 'featured'
                ? '#fff7ed'
                : colors.chipBg;
            const color = rating.tier === 'high'
              ? '#dc2626'
              : rating.tier === 'featured'
                ? '#d97706'
                : colors.textSecondary;
            const borderColor = rating.isPrimary ? color : 'transparent';
            const detail = ratingVariant === 'detail';
            return (
              <View
                key={rating.key}
                style={[
                  styles.rating,
                  compact && styles.ratingCompact,
                  detail && styles.ratingDetail,
                  { backgroundColor, borderColor },
                ]}
              >
                {detail ? (
                  <>
                    <Text style={[styles.ratingSource, { color }]}>{rating.source}</Text>
                    <Text
                      style={[
                        styles.ratingValue,
                        rating.tier === 'featured' && styles.featured,
                        rating.tier === 'high' && styles.high,
                        { color },
                      ]}
                    >
                      {rating.displayValue}
                    </Text>
                  </>
                ) : (
                  <Text
                    style={[
                      styles.ratingText,
                      compact && styles.ratingTextCompact,
                      rating.tier === 'featured' && styles.featured,
                      rating.tier === 'high' && styles.high,
                      { color },
                    ]}
                  >
                    {rating.source} {rating.displayValue}
                  </Text>
                )}
              </View>
            );
          })}
        </View>
      )}

      {tags.length > 0 && (
        <View style={[styles.row, styles.tagRow, centered && styles.rowCentered]}>
          {tags.map((tag) => (
            <View
              key={`quality:${tag}`}
              style={[styles.tag, compact && styles.tagCompact, { backgroundColor: colors.tagBg }]}
            >
              <Text style={[styles.tagText, compact && styles.tagTextCompact, { color: colors.tagText }]}>
                {tag}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  container: { marginTop: 9 },
  containerCompact: { marginTop: 7 },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  rowCentered: { justifyContent: 'center' },
  ratingGrid: {
    alignItems: 'stretch',
    marginHorizontal: -3,
  },
  rating: {
    borderRadius: 7,
    borderWidth: 1,
    paddingHorizontal: 7,
    paddingVertical: 4,
    marginRight: 5,
    marginBottom: 5,
  },
  ratingCompact: {
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 3,
    marginRight: 4,
    marginBottom: 4,
  },
  ratingDetail: {
    flexBasis: '46%',
    flexGrow: 1,
    minHeight: 58,
    justifyContent: 'center',
    paddingHorizontal: 12,
    paddingVertical: 9,
    marginHorizontal: 3,
    marginBottom: 6,
  },
  ratingText: { fontSize: 10, fontWeight: '700' },
  ratingTextCompact: { fontSize: 9 },
  ratingSource: { fontSize: 11, fontWeight: '700', marginBottom: 2 },
  ratingValue: { fontSize: 18, fontWeight: '800' },
  tagRow: { marginTop: 1 },
  tag: {
    borderRadius: 7,
    paddingHorizontal: 7,
    paddingVertical: 4,
    marginRight: 5,
    marginBottom: 5,
  },
  tagCompact: {
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 3,
    marginRight: 4,
    marginBottom: 4,
  },
  tagText: { fontSize: 10, fontWeight: '700' },
  tagTextCompact: { fontSize: 9 },
  featured: { fontWeight: '800' },
  high: { fontWeight: '900' },
});
