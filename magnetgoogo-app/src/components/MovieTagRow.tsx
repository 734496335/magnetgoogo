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
  style?: StyleProp<ViewStyle>;
}

export const MovieTagRow = memo(function MovieTagRow({
  item,
  colors,
  qualityTags = [],
  compact = false,
  centered = false,
  style,
}: MovieTagRowProps) {
  const ratings = getVisibleMovieRatings(item);
  const tags = qualityTags.filter(Boolean);
  if (ratings.length === 0 && tags.length === 0) return null;

  return (
    <View
      style={[
        styles.row,
        compact && styles.rowCompact,
        centered && styles.rowCentered,
        style,
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
        return (
          <View key={rating.source} style={[styles.tag, compact && styles.tagCompact, { backgroundColor }]}>
            <Text
              style={[
                styles.tagText,
                compact && styles.tagTextCompact,
                rating.tier === 'featured' && styles.featured,
                rating.tier === 'high' && styles.high,
                { color },
              ]}
            >
              {rating.source} {rating.displayValue}
            </Text>
          </View>
        );
      })}

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
  );
});

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginTop: 9,
  },
  rowCompact: { marginTop: 7 },
  rowCentered: { justifyContent: 'center' },
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
