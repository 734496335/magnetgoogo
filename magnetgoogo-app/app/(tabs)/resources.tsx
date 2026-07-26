import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../../src/core/LangContext';
import { useTheme, type Colors } from '../../src/core/ThemeContext';
import { MovieTagRow } from '../../src/components/MovieTagRow';
import { getMovieScoreTier } from '../../src/core/movieRatings';
import { getResourceCopy } from '../../src/core/resourceCopy';
import { loadResourceFeed, movieCoverUri } from '../../src/core/resourceFeed';
import {
  resourceFeedItemKey,
  type MovieFeed,
  type MovieFeedItem,
} from '../../src/core/resourceFeedProtocol';

const RECOMMENDED_WIDTH = 158;
const RECOMMENDED_COVER_HEIGHT = 224;
const ROW_COVER_WIDTH = 86;
const ROW_COVER_HEIGHT = 122;

interface PosterProps {
  item: MovieFeedItem;
  style: object;
  colors: Colors;
}

const MoviePoster = memo(function MoviePoster({ item, style, colors }: PosterProps) {
  const [failed, setFailed] = useState(false);
  return (
    <View style={[style, styles.posterShell, { backgroundColor: colors.chipBg }]}>
      {failed ? (
        <View style={styles.posterFallback}>
          <Ionicons name="film-outline" size={30} color={colors.textTertiary} />
        </View>
      ) : (
        <Image
          source={{ uri: movieCoverUri(item) }}
          style={styles.posterImage}
          resizeMode="cover"
          fadeDuration={120}
          onError={() => setFailed(true)}
        />
      )}
    </View>
  );
});

interface RecommendedCardProps {
  item: MovieFeedItem;
  colors: Colors;
  recommendation: string;
  onOpen: (movieId: string) => void;
}

const RecommendedCard = memo(function RecommendedCard({
  item,
  colors,
  recommendation,
  onOpen,
}: RecommendedCardProps) {
  const open = useCallback(() => onOpen(item.movie_id), [item.movie_id, onOpen]);
  const hasProminentScore = getMovieScoreTier(item) !== null;
  return (
    <TouchableOpacity
      style={styles.recommendedCard}
      activeOpacity={0.86}
      onPress={open}
      accessibilityRole="button"
      accessibilityLabel={item.title}
    >
      <View style={styles.recommendedPosterWrap}>
        <MoviePoster
          item={item}
          colors={colors}
          style={{ width: RECOMMENDED_WIDTH, height: RECOMMENDED_COVER_HEIGHT }}
        />
        <View style={styles.recommendBadge}>
          <Text style={styles.recommendBadgeText}>{recommendation}</Text>
        </View>
      </View>
      <Text
        style={[styles.recommendedTitle, { color: hasProminentScore ? '#dc2626' : colors.text }]}
        numberOfLines={2}
      >
        {item.title}
      </Text>
      <Text style={[styles.recommendedMeta, { color: colors.textTertiary }]} numberOfLines={1}>
        {[item.year, item.genres.slice(0, 2).join(' · ')].filter(Boolean).join(' · ')}
      </Text>
      <MovieTagRow
        item={item}
        colors={colors}
        qualityTags={item.quality_tags.slice(0, 2)}
        compact
      />
    </TouchableOpacity>
  );
});

interface MovieRowProps {
  item: MovieFeedItem;
  colors: Colors;
  minutesLabel: (value: number) => string;
  resourceLabel: (value: number) => string;
  onOpen: (movieId: string) => void;
}

const MovieRow = memo(function MovieRow({
  item,
  colors,
  minutesLabel,
  resourceLabel,
  onOpen,
}: MovieRowProps) {
  const open = useCallback(() => onOpen(item.movie_id), [item.movie_id, onOpen]);
  const metadata = [
    item.year,
    item.genres.slice(0, 2).join(' · '),
    item.duration_minutes ? minutesLabel(item.duration_minutes) : null,
  ].filter(Boolean).join(' · ');
  const visibleTags = item.quality_tags.slice(0, 3);
  const magnetCount = item.resources.filter((resource) => resource.resource_type === 'magnet').length;
  const hasProminentScore = getMovieScoreTier(item) !== null;
  return (
    <TouchableOpacity
      style={[styles.movieRow, { borderBottomColor: colors.border }]}
      activeOpacity={0.72}
      onPress={open}
      accessibilityRole="button"
      accessibilityLabel={item.title}
    >
      <MoviePoster
        item={item}
        colors={colors}
        style={{ width: ROW_COVER_WIDTH, height: ROW_COVER_HEIGHT }}
      />
      <View style={styles.movieInfo}>
        <Text
          style={[styles.movieTitle, { color: hasProminentScore ? '#dc2626' : colors.text }]}
          numberOfLines={2}
        >
          {item.title}
        </Text>
        {!!metadata && (
          <Text style={[styles.movieMeta, { color: colors.textTertiary }]} numberOfLines={1}>
            {metadata}
          </Text>
        )}
        <MovieTagRow item={item} colors={colors} qualityTags={visibleTags} />
        <View style={styles.rowFooter}>
          <Text style={[styles.resourceText, { color: colors.textTertiary }]}>
            {resourceLabel(magnetCount)}
          </Text>
        </View>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.textTertiary} />
    </TouchableOpacity>
  );
});

export default function ResourcesScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { lang } = useLang();
  const { colors } = useTheme();
  const copy = getResourceCopy(lang);
  const [feed, setFeed] = useState<MovieFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (forceRefresh: boolean) => {
    if (forceRefresh) setRefreshing(true);
    else setLoading(true);
    setFailed(false);
    try {
      const loaded = await loadResourceFeed(forceRefresh);
      setFeed(loaded.feed);
    } catch (error) {
      console.warn('[ResourcesScreen]', {
        stage: 'load_movie_feed',
        error_code: 'MOVIE_FEED_LOAD_FAILED',
        error: error instanceof Error ? error.message : String(error),
      });
      setFailed(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const openMovie = useCallback((movieId: string) => {
    router.push({
      pathname: '/movie/[movieId]',
      params: { movieId },
    });
  }, [router]);

  const recommended = useMemo(
    () => feed?.items.filter((item) => item.recommended) ?? [],
    [feed?.items],
  );
  const recent = useMemo(
    () => feed?.items.filter((item) => !item.recommended) ?? [],
    [feed?.items],
  );
  const renderRecommended = useCallback((item: MovieFeedItem) => (
    <RecommendedCard
      key={item.movie_id}
      item={item}
      colors={colors}
      recommendation={copy.recommendation}
      onOpen={openMovie}
    />
  ), [colors, copy.recommendation, openMovie]);

  const renderItem = useCallback(({ item }: { item: MovieFeedItem }) => (
    <MovieRow
      item={item}
      colors={colors}
      minutesLabel={copy.minutes}
      resourceLabel={copy.resourceCount}
      onOpen={openMovie}
    />
  ), [colors, copy.minutes, copy.resourceCount, openMovie]);

  const header = useMemo(() => (
    <View>
      <View style={styles.pageHeader}>
        <Text style={[styles.pageTitle, { color: colors.text }]}>{copy.title}</Text>
      </View>

      {recommended.length > 0 && (
        <View style={styles.recommendedSection}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>{copy.recommendedTitle}</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.recommendedContent}
          >
            {recommended.map(renderRecommended)}
          </ScrollView>
        </View>
      )}

      <Text style={[styles.sectionTitle, styles.latestTitle, { color: colors.text }]}>
        {copy.latestTitle}
      </Text>
    </View>
  ), [colors, copy, recommended, renderRecommended]);

  if (loading && !feed) {
    return (
      <View style={[styles.center, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
        <ActivityIndicator size="large" color={colors.accent} />
        <Text style={[styles.loadingText, { color: colors.textSecondary }]}>{copy.loading}</Text>
      </View>
    );
  }

  if ((failed || !feed) && !refreshing) {
    return (
      <View style={[styles.center, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
        <View style={[styles.emptyIcon, { backgroundColor: colors.chipBg }]}>
          <Ionicons name="film-outline" size={34} color={colors.textTertiary} />
        </View>
        <Text style={[styles.emptyTitle, { color: colors.text }]}>{copy.emptyTitle}</Text>
        <Text style={[styles.emptyBody, { color: colors.textTertiary }]}>{copy.emptyBody}</Text>
        <TouchableOpacity
          style={[styles.retryButton, { backgroundColor: colors.accent }]}
          onPress={() => void load(true)}
        >
          <Text style={styles.retryText}>{copy.retry}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <FlatList
        data={recent}
        renderItem={renderItem}
        keyExtractor={resourceFeedItemKey}
        ListHeaderComponent={header}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        refreshControl={(
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor={colors.accent}
            colors={[colors.accent]}
          />
        )}
        initialNumToRender={8}
        maxToRenderPerBatch={8}
        updateCellsBatchingPeriod={40}
        windowSize={7}
        removeClippedSubviews
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 36,
  },
  loadingText: { marginTop: 14, fontSize: 14 },
  listContent: { paddingBottom: 28 },
  pageHeader: {
    paddingHorizontal: 20,
    paddingTop: 14,
    paddingBottom: 18,
  },
  pageTitle: { fontSize: 31, fontWeight: '800', letterSpacing: -0.8 },
  recommendedSection: { marginBottom: 24 },
  sectionTitle: {
    paddingHorizontal: 20,
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  latestTitle: { marginBottom: 4 },
  recommendedContent: { paddingHorizontal: 20, paddingTop: 12, paddingRight: 8 },
  recommendedCard: { width: RECOMMENDED_WIDTH, marginRight: 13 },
  recommendedPosterWrap: { position: 'relative' },
  posterShell: { borderRadius: 13, overflow: 'hidden' },
  posterImage: { width: '100%', height: '100%' },
  posterFallback: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  recommendBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    borderRadius: 7,
    paddingHorizontal: 7,
    paddingVertical: 4,
    backgroundColor: '#ef4444',
  },
  recommendBadgeText: { color: '#fff', fontSize: 10, fontWeight: '800' },
  recommendedTitle: { marginTop: 9, fontSize: 14, lineHeight: 19, fontWeight: '700' },
  recommendedMeta: { marginTop: 4, fontSize: 11 },
  movieRow: {
    minHeight: 146,
    marginHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
  },
  movieInfo: { flex: 1, alignSelf: 'stretch', marginLeft: 13, paddingVertical: 2 },
  movieTitle: { fontSize: 16, lineHeight: 22, fontWeight: '700' },
  movieMeta: { marginTop: 6, fontSize: 11 },
  rowFooter: { marginTop: 'auto', flexDirection: 'row', alignItems: 'center' },
  resourceText: { fontSize: 10 },
  emptyIcon: {
    width: 72,
    height: 72,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
  },
  emptyTitle: { fontSize: 18, fontWeight: '800', textAlign: 'center' },
  emptyBody: { marginTop: 8, fontSize: 13, lineHeight: 20, textAlign: 'center' },
  retryButton: { marginTop: 20, borderRadius: 14, paddingHorizontal: 22, paddingVertical: 11 },
  retryText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
