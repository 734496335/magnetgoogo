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

const SPOTLIGHT_WIDTH = 158;
const SPOTLIGHT_COVER_HEIGHT = 224;
const ROW_COVER_WIDTH = 86;
const ROW_COVER_HEIGHT = 122;

type MediaChannel = 'movie' | 'series' | 'us' | 'korea' | 'japan' | 'china' | 'uk';

const CHANNELS: MediaChannel[] = ['movie', 'series', 'us', 'korea', 'japan', 'china', 'uk'];

function channelKind(channel: MediaChannel): MediaKind {
  return channel === 'movie' ? 'movie' : 'series';
}

function isCompletedSeries(item: MovieFeedItem): boolean {
  const status = `${item.update_status ?? ''} ${item.episode_label ?? ''}`.trim();
  return /全集|完结|(?:^|\s)全$|季全$/.test(status);
}

function matchesChannel(item: MovieFeedItem, channel: MediaChannel): boolean {
  if (channel === 'movie') return item.content_kind === 'movie';
  if (item.content_kind !== 'series') return false;
  if (channel === 'series') return true;
  const countries = new Set(item.countries);
  if (channel === 'us') return countries.has('美国');
  if (channel === 'korea') return countries.has('韩国');
  if (channel === 'japan') return countries.has('日本');
  if (channel === 'uk') return countries.has('英国');
  return ['中国', '大陆', '香港', '台湾'].some((country) => countries.has(country));
}

interface PosterProps {
  item: MovieFeedItem;
  style: object;
  colors: Colors;
  overlayLabel?: string | null;
}

const MediaPoster = memo(function MediaPoster({ item, style, colors, overlayLabel }: PosterProps) {
  const [failed, setFailed] = useState(false);
  const coverUri = movieCoverUri(item);
  return (
    <View style={[style, styles.posterShell, { backgroundColor: colors.chipBg }]}>
      <LinearGradient colors={[colors.tagBg, colors.chipBg]} style={styles.posterFallback}>
        <Ionicons
          name={item.content_kind === 'series' ? 'tv-outline' : 'film-outline'}
          size={30}
          color={colors.textTertiary}
        />
        <Text style={[styles.posterFallbackText, { color: colors.textSecondary }]} numberOfLines={2}>
          {item.title}
        </Text>
      </LinearGradient>
      {!!coverUri && !failed && (
        <Image
          source={{ uri: coverUri, cache: 'force-cache' }}
          style={styles.posterImage}
          resizeMode="cover"
          fadeDuration={160}
          progressiveRenderingEnabled
          onError={() => setFailed(true)}
        />
      )}
      {!!overlayLabel && (
        <View style={styles.updateOverlay}>
          <Text style={styles.updateOverlayText} numberOfLines={1}>{overlayLabel}</Text>
        </View>
      )}
    </View>
  );
});

interface SpotlightCardProps {
  item: MovieFeedItem;
  colors: Colors;
  badgeText: string;
  onOpen: (item: MovieFeedItem) => void;
}

const SpotlightCard = memo(function SpotlightCard({ item, colors, badgeText, onOpen }: SpotlightCardProps) {
  const open = useCallback(() => onOpen(item), [item, onOpen]);
  const hasProminentScore = getMovieScoreTier(item) !== null;
  return (
    <TouchableOpacity
      style={styles.spotlightCard}
      activeOpacity={0.86}
      onPress={open}
      accessibilityRole="button"
      accessibilityLabel={item.title}
    >
      <View style={styles.spotlightPosterWrap}>
        <MediaPoster
          item={item}
          colors={colors}
          overlayLabel={item.content_kind === 'series' ? item.update_status || item.episode_label : null}
          style={{ width: SPOTLIGHT_WIDTH, height: SPOTLIGHT_COVER_HEIGHT }}
        />
        {item.content_kind === 'movie' && (
          <View style={styles.recommendBadge}>
            <Text style={styles.recommendBadgeText}>{badgeText}</Text>
          </View>
        )}
      </View>
      <Text
        style={[styles.spotlightTitle, { color: hasProminentScore ? '#dc2626' : colors.text }]}
        numberOfLines={2}
      >
        {item.title}
      </Text>
      <Text style={[styles.spotlightMeta, { color: colors.textTertiary }]} numberOfLines={1}>
        {[item.year, item.countries[0], item.genres[0]].filter(Boolean).join(' · ')}
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
    item.countries[0],
    item.genres.slice(0, 2).join(' · '),
    status,
  ].filter(Boolean).join(' · ');
  const visibleTags = item.quality_tags.slice(0, 3);
  const magnetCount = item.resources.filter((resource) => resource.resource_type === 'magnet').length;
  const hasProminentScore = getMovieScoreTier(item) !== null;
  return (
    <TouchableOpacity
      style={[styles.mediaRow, { borderBottomColor: colors.border }]}
      activeOpacity={0.72}
      onPress={open}
      accessibilityRole="button"
      accessibilityLabel={item.title}
    >
      <MediaPoster
        item={item}
        colors={colors}
        overlayLabel={item.content_kind === 'series' ? status : null}
        style={{ width: ROW_COVER_WIDTH, height: ROW_COVER_HEIGHT }}
      />
      <View style={styles.mediaInfo}>
        <Text
          style={[styles.mediaTitle, { color: hasProminentScore ? '#dc2626' : colors.text }]}
          numberOfLines={2}
        >
          {item.title}
        </Text>
        {!!metadata && (
          <Text style={[styles.mediaMeta, { color: colors.textTertiary }]} numberOfLines={2}>
            {metadata}
          </Text>
        )}
        <MovieTagRow item={item} colors={colors} qualityTags={visibleTags} />
        <View style={styles.rowFooter}>
          <Ionicons name="link-outline" size={12} color={colors.textTertiary} />
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
  const [activeChannel, setActiveChannel] = useState<MediaChannel>('movie');
  const [feeds, setFeeds] = useState<Partial<Record<MediaKind, MovieFeed>>>({});
  const [loadingKind, setLoadingKind] = useState<MediaKind | null>('movie');
  const [refreshingKind, setRefreshingKind] = useState<MediaKind | null>(null);
  const [failedKinds, setFailedKinds] = useState<Partial<Record<MediaKind, boolean>>>({});

  const activeKind = channelKind(activeChannel);
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
    void load('movie', false);
  }, [load]);

  useEffect(() => {
    if (!feeds[activeKind] && loadingKind !== activeKind) {
      void load(activeKind, false);
    }
  }, [activeKind, feeds, load, loadingKind]);

  const openMedia = useCallback((item: MovieFeedItem) => {
    router.push({
      pathname: '/movie/[movieId]',
      params: { movieId: item.movie_id, kind: item.content_kind },
    });
  }, [router]);

  const filteredItems = useMemo(
    () => feed?.items.filter((item) => matchesChannel(item, activeChannel)) ?? [],
    [activeChannel, feed?.items],
  );

  const spotlight = useMemo(() => {
    if (activeKind === 'movie') return filteredItems.filter((item) => item.recommended);
    return filteredItems.filter((item) => !isCompletedSeries(item)).slice(0, 10);
  }, [activeKind, filteredItems]);

  const spotlightIds = useMemo(
    () => new Set(spotlight.map((item) => item.movie_id)),
    [spotlight],
  );

  const recent = useMemo(() => {
    if (activeKind === 'movie') return filteredItems.filter((item) => !item.recommended);
    const withoutSpotlight = filteredItems.filter((item) => !spotlightIds.has(item.movie_id));
    return withoutSpotlight.length > 0 ? withoutSpotlight : filteredItems;
  }, [activeKind, filteredItems, spotlightIds]);

  const renderSpotlight = useCallback((item: MovieFeedItem) => (
    <SpotlightCard
      key={resourceFeedItemKey(item)}
      item={item}
      colors={colors}
      badgeText={copy.recommendation}
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

  const channelLabel = useCallback((channel: MediaChannel) => {
    if (channel === 'movie') return copy.mediaMovies;
    if (channel === 'series') return copy.mediaSeries;
    if (channel === 'us') return copy.mediaUsSeries;
    if (channel === 'korea') return copy.mediaKoreanSeries;
    if (channel === 'japan') return copy.mediaJapaneseSeries;
    if (channel === 'china') return copy.mediaChineseSeries;
    return copy.mediaUkSeries;
  }, [copy]);

  const channelBar = (
    <View style={[styles.channelShell, { borderBottomColor: colors.border, backgroundColor: colors.bg }]}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.channelContent}
      >
        {CHANNELS.map((channel) => {
          const active = activeChannel === channel;
          return (
            <TouchableOpacity
              key={channel}
              style={[
                styles.channelButton,
                active && {
                  backgroundColor: colors.card,
                  borderColor: colors.accent,
                  shadowColor: colors.shadow,
                },
              ]}
              activeOpacity={0.82}
              onPress={() => setActiveChannel(channel)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={channelLabel(channel)}
            >
              <Text
                style={[
                  styles.channelText,
                  { color: active ? colors.text : colors.textTertiary },
                  active && styles.channelTextActive,
                ]}
              >
                {channelLabel(channel)}
              </Text>
              <View style={[styles.channelIndicator, active && { backgroundColor: colors.accent }]} />
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );

  const listHeader = useMemo(() => (
    <View>
      {spotlight.length > 0 && (
        <View style={styles.spotlightSection}>
          <View style={styles.sectionHeadingRow}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>
              {activeKind === 'movie' ? copy.recommendedTitle : copy.seriesUpdatingTitle}
            </Text>
            {activeKind === 'series' && (
              <Text style={[styles.sectionHint, { color: colors.textTertiary }]}>{copy.offlineUpdated}</Text>
            )}
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.spotlightContent}
          >
            {spotlight.map(renderSpotlight)}
          </ScrollView>
        </View>
      )}

      <Text style={[styles.sectionTitle, styles.latestTitle, { color: colors.text }]}>
        {activeKind === 'movie' ? copy.latestTitle : copy.seriesLatestTitle}
      </Text>
    </View>
  ), [
    activeKind,
    colors.text,
    colors.textTertiary,
    copy.latestTitle,
    copy.offlineUpdated,
    copy.recommendedTitle,
    copy.seriesLatestTitle,
    copy.seriesUpdatingTitle,
    renderSpotlight,
    spotlight,
  ]);

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      {channelBar}

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
      ) : filteredItems.length === 0 ? (
        <View style={styles.center}>
          <View style={[styles.emptyIcon, { backgroundColor: colors.chipBg }]}>
            <Ionicons name="tv-outline" size={34} color={colors.textTertiary} />
          </View>
          <Text style={[styles.emptyTitle, { color: colors.text }]}>{copy.channelEmptyTitle}</Text>
          <Text style={[styles.emptyBody, { color: colors.textTertiary }]}>{copy.channelEmptyBody}</Text>
        </View>
      ) : (
        <FlatList
          key={activeChannel}
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
  channelShell: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingTop: 10,
    paddingBottom: 12,
  },
  channelContent: { paddingHorizontal: 16, paddingRight: 8 },
  channelButton: {
    minWidth: 88,
    height: 54,
    marginRight: 10,
    paddingHorizontal: 18,
    borderRadius: 17,
    borderWidth: 1.2,
    borderColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  channelText: { fontSize: 17, fontWeight: '700', letterSpacing: -0.2 },
  channelTextActive: { fontSize: 20, fontWeight: '900' },
  channelIndicator: { width: 24, height: 3, marginTop: 6, borderRadius: 999, backgroundColor: 'transparent' },
  spotlightSection: { marginTop: 22, marginBottom: 26 },
  sectionHeadingRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  sectionTitle: {
    paddingHorizontal: 20,
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: -0.3,
  },
  sectionHint: { paddingRight: 20, fontSize: 11, fontWeight: '600' },
  latestTitle: { marginTop: 20, marginBottom: 4 },
  spotlightContent: { paddingHorizontal: 20, paddingTop: 13, paddingRight: 8 },
  spotlightCard: { width: SPOTLIGHT_WIDTH, marginRight: 13 },
  spotlightPosterWrap: { position: 'relative' },
  posterShell: { borderRadius: 14, overflow: 'hidden' },
  posterImage: { ...StyleSheet.absoluteFillObject, width: '100%', height: '100%' },
  posterFallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  posterFallbackText: { marginTop: 8, fontSize: 10, lineHeight: 14, fontWeight: '700', textAlign: 'center' },
  updateOverlay: {
    position: 'absolute',
    right: 6,
    bottom: 6,
    maxWidth: '84%',
    borderRadius: 7,
    paddingHorizontal: 7,
    paddingVertical: 4,
    backgroundColor: 'rgba(0,0,0,0.72)',
  },
  updateOverlayText: { color: '#fff', fontSize: 10, fontWeight: '800' },
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
  spotlightTitle: { marginTop: 9, fontSize: 14, lineHeight: 19, fontWeight: '700' },
  spotlightMeta: { marginTop: 4, fontSize: 11 },
  mediaRow: {
    minHeight: 146,
    marginHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
  },
  mediaInfo: { flex: 1, alignSelf: 'stretch', marginLeft: 13, paddingVertical: 2 },
  mediaTitle: { fontSize: 16, lineHeight: 22, fontWeight: '700' },
  mediaMeta: { marginTop: 6, fontSize: 11, lineHeight: 16 },
  rowFooter: { marginTop: 'auto', flexDirection: 'row', alignItems: 'center', gap: 4 },
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
