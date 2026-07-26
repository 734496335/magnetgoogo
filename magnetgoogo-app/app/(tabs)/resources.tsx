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
import { LinearGradient } from 'expo-linear-gradient';
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
  type MediaKind,
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
  const coverUri = movieCoverUri(item);
  const showPlaceholder = failed || !coverUri;
  return (
    <View style={[style, styles.posterShell, { backgroundColor: colors.chipBg }]}>
      {showPlaceholder ? (
        <LinearGradient
          colors={[colors.tagBg, colors.chipBg]}
          style={styles.posterFallback}
        >
          <Ionicons
            name={item.content_kind === 'series' ? 'tv-outline' : 'film-outline'}
            size={30}
            color={colors.textTertiary}
          />
          <Text style={[styles.posterFallbackText, { color: colors.textSecondary }]} numberOfLines={2}>
            {item.title}
          </Text>
        </LinearGradient>
      ) : (
        <Image
          source={{ uri: coverUri }}
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
  onOpen: (item: MovieFeedItem) => void;
}

const RecommendedCard = memo(function RecommendedCard({
  item,
  colors,
  recommendation,
  onOpen,
}: RecommendedCardProps) {
  const open = useCallback(() => onOpen(item), [item, onOpen]);
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

interface MediaRowProps {
  item: MovieFeedItem;
  colors: Colors;
  minutesLabel: (value: number) => string;
  resourceLabel: (value: number) => string;
  onOpen: (item: MovieFeedItem) => void;
}

const MediaRow = memo(function MediaRow({
  item,
  colors,
  minutesLabel,
  resourceLabel,
  onOpen,
}: MediaRowProps) {
  const open = useCallback(() => onOpen(item), [item, onOpen]);
  const status = item.content_kind === 'series'
    ? item.update_status || item.episode_label
    : item.duration_minutes
      ? minutesLabel(item.duration_minutes)
      : null;
  const metadata = [
    item.year,
    item.genres.slice(0, 2).join(' · '),
    status,
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
  const [activeKind, setActiveKind] = useState<MediaKind>('movie');
  const [feeds, setFeeds] = useState<Partial<Record<MediaKind, MovieFeed>>>({});
  const [loadingKind, setLoadingKind] = useState<MediaKind | null>('movie');
  const [refreshingKind, setRefreshingKind] = useState<MediaKind | null>(null);
  const [failedKinds, setFailedKinds] = useState<Partial<Record<MediaKind, boolean>>>({});

  const feed = feeds[activeKind] ?? null;
  const loading = loadingKind === activeKind;
  const refreshing = refreshingKind === activeKind;
  const failed = failedKinds[activeKind] === true;

  const load = useCallback(async (kind: MediaKind, forceRefresh: boolean) => {
    if (forceRefresh) setRefreshingKind(kind);
    else setLoadingKind(kind);
    setFailedKinds((current) => ({ ...current, [kind]: false }));
    try {
      const loaded = await loadResourceFeed(kind, forceRefresh);
      setFeeds((current) => ({ ...current, [kind]: loaded.feed }));
    } catch (error) {
      console.warn('[ResourcesScreen]', {
        stage: 'load_media_feed',
        error_code: 'MEDIA_FEED_LOAD_FAILED',
        content_kind: kind,
        error: error instanceof Error ? error.message : String(error),
      });
      setFailedKinds((current) => ({ ...current, [kind]: true }));
    } finally {
      setLoadingKind((current) => current === kind ? null : current);
      setRefreshingKind((current) => current === kind ? null : current);
    }
  }, []);

  useEffect(() => {
    if (!feeds[activeKind] && loadingKind !== activeKind) {
      void load(activeKind, false);
    }
  }, [activeKind, feeds, load, loadingKind]);

  useEffect(() => {
    void load('movie', false);
  }, [load]);

  const switchKind = useCallback((kind: MediaKind) => {
    setActiveKind(kind);
  }, []);

  const openMedia = useCallback((item: MovieFeedItem) => {
    router.push({
      pathname: '/movie/[movieId]',
      params: { movieId: item.movie_id, kind: item.content_kind },
    });
  }, [router]);

  const recommended = useMemo(
    () => activeKind === 'movie' ? feed?.items.filter((item) => item.recommended) ?? [] : [],
    [activeKind, feed?.items],
  );
  const recent = useMemo(
    () => feed?.items.filter((item) => activeKind === 'series' || !item.recommended) ?? [],
    [activeKind, feed?.items],
  );
  const renderRecommended = useCallback((item: MovieFeedItem) => (
    <RecommendedCard
      key={resourceFeedItemKey(item)}
      item={item}
      colors={colors}
      recommendation={copy.recommendation}
      onOpen={openMedia}
    />
  ), [colors, copy.recommendation, openMedia]);

  const renderItem = useCallback(({ item }: { item: MovieFeedItem }) => (
    <MediaRow
      item={item}
      colors={colors}
      minutesLabel={copy.minutes}
      resourceLabel={copy.resourceCount}
      onOpen={openMedia}
    />
  ), [colors, copy.minutes, copy.resourceCount, openMedia]);

  const listHeader = useMemo(() => (
    <View>
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
  ), [colors.text, copy.latestTitle, copy.recommendedTitle, recommended, renderRecommended]);

  const segment = (
    <View style={[styles.segment, { backgroundColor: colors.chipBg }]}>
      {(['movie', 'series'] as const).map((kind) => {
        const active = activeKind === kind;
        return (
          <TouchableOpacity
            key={kind}
            style={[styles.segmentButton, active && { backgroundColor: colors.accent }]}
            activeOpacity={0.8}
            onPress={() => switchKind(kind)}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={kind === 'movie' ? copy.mediaMovies : copy.mediaSeries}
          >
            <Text style={[styles.segmentText, { color: active ? '#fff' : colors.textSecondary }]}>
              {kind === 'movie' ? copy.mediaMovies : copy.mediaSeries}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <View style={styles.pageHeader}>
        <Text style={[styles.pageTitle, { color: colors.text }]}>{copy.title}</Text>
        {segment}
      </View>

      {loading && !feed ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.accent} />
          <Text style={[styles.loadingText, { color: colors.textSecondary }]}>{copy.loading}</Text>
        </View>
      ) : (failed || !feed) && !refreshing ? (
        <View style={styles.center}>
          <View style={[styles.emptyIcon, { backgroundColor: colors.chipBg }]}>
            <Ionicons
              name={activeKind === 'series' ? 'tv-outline' : 'film-outline'}
              size={34}
              color={colors.textTertiary}
            />
          </View>
          <Text style={[styles.emptyTitle, { color: colors.text }]}>{copy.emptyTitle}</Text>
          <Text style={[styles.emptyBody, { color: colors.textTertiary }]}>{copy.emptyBody}</Text>
          <TouchableOpacity
            style={[styles.retryButton, { backgroundColor: colors.accent }]}
            onPress={() => void load(activeKind, true)}
          >
            <Text style={styles.retryText}>{copy.retry}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          key={activeKind}
          data={recent}
          renderItem={renderItem}
          keyExtractor={resourceFeedItemKey}
          ListHeaderComponent={listHeader}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          refreshControl={(
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => void load(activeKind, true)}
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
      )}
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
  segment: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    marginTop: 16,
    borderRadius: 999,
    padding: 3,
  },
  segmentButton: {
    minWidth: 82,
    height: 34,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
  },
  segmentText: { fontSize: 13, fontWeight: '800' },
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
  posterFallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  posterFallbackText: { marginTop: 8, fontSize: 10, lineHeight: 14, fontWeight: '700', textAlign: 'center' },
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
  retryButton: { marginTop: 20, borderRadius: 999, paddingHorizontal: 24, paddingVertical: 11 },
  retryText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
