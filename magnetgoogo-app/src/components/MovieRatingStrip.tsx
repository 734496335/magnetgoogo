import React, { memo } from 'react';
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import type { Colors } from '../core/ThemeContext';
import { getVisibleMovieRatings } from '../core/movieRatings';
import type { MovieFeedItem } from '../core/resourceFeedProtocol';

interface MovieRatingStripProps {
  item: Pick<MovieFeedItem, 'imdb_rating' | 'douban_rating'>;
  colors: Colors;
  compact?: boolean;
  centered?: boolean;
  style?: StyleProp<ViewStyle>;
}

export const MovieRatingStrip = memo(function MovieRatingStrip({
  item,
  colors,
  compact = false,
  centered = false,
  style,
}: MovieRatingStripProps) {
  const ratings = getVisibleMovieRatings(item);
  if (ratings.length === 0) return null;

  return (
    <View
      style={[
        styles.row,
        compact && styles.rowCompact,
        centered && styles.rowCentered,
        style,
      ]}
    >
      {ratings.map((rating, index) => {
        const color = rating.tier === 'high'
          ? '#dc2626'
          : rating.tier === 'featured'
            ? '#d97706'
            : colors.textSecondary;
        return (
          <View key={rating.source} style={styles.item}>
            {index > 0 && (
              <Text style={[styles.separator, { color: colors.textTertiary }]}>·</Text>
            )}
            <Text
              style={[
                styles.rating,
                compact && styles.ratingCompact,
                rating.tier === 'featured' && styles.featured,
                rating.tier === 'high' && styles.high,
                { color },
              ]}
            >
              {rating.source} {rating.value.toFixed(1)}
            </Text>
          </View>
        );
      })}
    </View>
  );
});

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginTop: 7,
  },
  rowCompact: { marginTop: 6 },
  rowCentered: { justifyContent: 'center' },
  item: { flexDirection: 'row', alignItems: 'baseline', marginBottom: 4 },
  separator: { marginHorizontal: 7, fontSize: 10 },
  rating: { fontSize: 11, fontWeight: '700' },
  ratingCompact: { fontSize: 10 },
  featured: { fontWeight: '800' },
  high: { fontWeight: '900' },
});
