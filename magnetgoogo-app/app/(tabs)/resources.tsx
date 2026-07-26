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
  type GestureResponderEvent,
  type StyleProp,
  type TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../../src/core/LangContext';
import { useTheme, type Colors } from '../../src/core/ThemeContext';
import { MovieTagRow } from '../../src/components/MovieTagRow';
import { getMovieScoreTier } from '../../src/core/movieRatings';
import { seriesStatusForDisplay } from '../../src/core/mediaResourceTitle';
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
const TITLE_COPY_TOAST_MS = 2000;

type MediaChannel = 'movie' | 'us' | 'uk' | 'china' | 'korea' | 'japan';

interface CopyableMediaTitleProps {
  title: string;
  onCopied: () => void;
  style: StyleProp<TextStyle>;
  numberOfLines?: number;
}

const CopyableMediaTitle = memo(function CopyableMediaTitle({
  title,
  onCopied,
  style,
  numberOfLines,
}: CopyableMediaTitleProps) {
  const copyTitle = useCallback(async (event: GestureResponderEvent) => {
    event.stopPropagation();
    try {
      await Clipboard.setStringAsync(title);
      onCopied();
    } catch (error) {
      console.warn('[ResourcesScreen]', {
        stage: 'copy_media_title',
        error_code: 'MEDIA_TITLE_COPY_FAILED',
        title,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }, [onCopied, title]);

  return (
    <TouchableOpacity
      activeOpacity={0.62}
      onPress={(event) => void copyTitle(event)}
      accessibilityRole="button"
      accessibilityLabel={title}
    >
      <Text style={style} numberOfLines={numberOfLines}>
        {title}
      </Text>
    </TouchableOpacity>
  );
});

const CHANNELS: MediaChannel[] = ['movie', 'us', 'uk', 'china', 'korea', 'japan'];

function channelKind(channel: MediaChannel): MediaKind {
  return channel === 'movie' ? 'movie' : 'series';
}

function isCompletedSeries(item: MovieFeedItem): boolean {
  const status = `${item.update_status ?? ''} ${item.episode_label ?? ''}`.trim();
  return /全集|完结|(?:^|\s)全$|季全$/.test(status);
}

function rawSeriesStatus(item: MovieFeedItem): string | null {
  return seriesStatusForDisplay(
    item.title,
    item.season_number,
    item.update_status || item.episode_label,
  );
}

function latestEpisodeNumber(raw: string): number | null {
  const values: number[] = [];
  for (const match of raw.matchAll(/(?:更新\s*(?:至|到)?\s*第?|第|无字第)\s*0*(\d+)\s*集?/g)) {
    const value = Number(match[1]);
    if (Number.isFinite(value) && value > 0) values.push(value);
  }
  return values.length > 0 ? Math.max(...values) : null;
}

function prominentUpdateLabel(item: MovieFeedItem): string | null {
  const raw = rawSeriesStatus(item);
  if (!raw) return null;
  if (/全集|完结|季全|全\s*\d+\s*集/.test(raw)) return '已完结';
  const episode = latestEpisodeNumber(raw);
  if (episode !== null) return `更新至${episode}集`;
  return raw;
}

function listUpdateLabel(item: MovieFeedItem): string | null {
  const raw = rawSeriesStatus(item);
  if (!raw) return null;
  if (/全集|完结|季全|全\s*\d+\s*集/.test(raw)) return raw;
  const episode = latestEpisodeNumber(raw);
  if (episode === null) return raw.replace(/^更新\s*(?:至|到)?\s*/, '').trim() || null;
  const season = raw.match(/第[一二三四五六七八九十百0-9-]+季/)?.[0];
  return season ? `${season} · 更新至第${episode}集` : `更新至第${episode}集`;
}

function normalizeGenreLabel(value: string): string {
  const htmlTail = value.includes('>') ? value.split('>').at(-1) ?? value : value;
  return htmlTail
    .replace(/^[\s:：·|/]+/, '')
    .replace(/\s+片$/, '片')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizedGenres(item: MovieFeedItem): string[] {
  return [...new Set(item.genres.map(normalizeGenreLabel).filter(Boolean))];
}

function normalizeCountryLabel(value: string): string {
  return value.replace(/^[\s:：·|/]+/, '').replace(/\s+/g, ' ').trim();
}

function normalizedCountries(item: MovieFeedItem): string[] {
  return [...new Set(item.countries.map(normalizeCountryLabel).filter(Boolean))];
}

function matchesChannel(item: MovieFeedItem, channel: MediaChannel): boolean {
  if (channel === 'movie') return item.content_kind === 'movie';
  if (item.content_kind !== 'series') return false;
  const countries = new Set(normalizedCountries(item));
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
        <LinearGradient colors={['#ff7a3d', '#ef3f24']} style={styles.updateOverlay}>
          <Text style={styles.updateOverlayText} numberOfLines={1}>{overlayLabel}</Text>
        </LinearGradient>
      )}
    </View>
  );
});

interface SpotlightCardProps {
  item: MovieFeedItem;
  colors: Colors;
  badgeText: string;
  onTitleCopied: () => void;
  onOpen: (item: MovieFeedItem) => void;
}

const SpotlightCard = memo(function SpotlightCard({ item, colors, badgeText, onTitleCopied, onOpen }: SpotlightCardProps) {
  const open = useCallback(() => onOpen(item), [item, onOpen]);
  const hasProminentScore = getMovieScoreTier(item) !== null;
  return (
    <View style={styles.spotlightCard}>
      <TouchableOpacity
        activeOpacity={0.86}
        onPress={open}
        accessibilityRole="button"
        accessibilityLabel={item.title}
      >
        <View style={styles.spotlightPosterWrap}>
          <MediaPoster
            item={item}
            colors={colors}
            overlayLabel={item.content_kind === 'series' ? prominentUpdateLabel(item) : null}
            style={{ width: SPOTLIGHT_WIDTH, height: SPOTLIGHT_COVER_HEIGHT }}
          />
          {item.content_kind === 'movie' && (
            <View style={styles.recommendBadge}>
              <Text style={styles.recommendBadgeText}>{badgeText}</Text>
            </View>
          )}
        </View>
      </TouchableOpacity>
      <CopyableMediaTitle
        title={item.title}
        onCopied={onTitleCopied}
        style={[styles.spotlightTitle, { color: hasProminentScore ? '#dc2626' : colors.text }]}
        numberOfLines={2}
      />
      <TouchableOpacity
        activeOpacity={0.7}
        onPress={open}
        accessibilityRole="button"
        accessibilityLabel={item.title}
      >
        <Text style={[styles.spotlightMeta, { color: colors.textTertiary }]} numberOfLines={1}>
          {[item.year, normalizedCountries(item)[0], normalizedGenres(item)[0]].filter(Boolean).join(' · ')}
        </Text>
        <MovieTagRow
          item={item}
          colors={colors}
          qualityTags={item.quality_tags.slice(0, 2)}
          compact
        />
      </TouchableOpacity>
    </View>
  );
});

interface MediaRowProps {
  item: MovieFeedItem;
  colors: Colors;
  minutesLabel: (value: number) => string;
  resourceLabel: (value: number) => string;
  onTitleCopied: () => void;
  onOpen: (item: MovieFeedItem) => void;
}

const MediaRow = memo(function MediaRow({
  item,
  colors,
  minutesLabel,
  resourceLabel,
  onTitleCopied,
  onOpen,
}: MediaRowProps) {
  const open = useCallback(() => onOpen(item), [item, onOpen]);
  const seriesStatus = item.content_kind === 'series' ? listUpdateLabel(item) : null;
  const duration = item.content_kind === 'movie' && item.duration_minutes
    ? minutesLabel(item.duration_minutes)
    : null;
  const metadata = [
    item.year,
    normalizedCountries(item)[0],
    normalizedGenres(item).slice(0, 2).join(' · '),
    duration,
  ].filter(Boolean).join(' · ');
  const visibleTags = item.quality_tags.slice(0, 3);
  const magnetCount = item.resources.filter((resource) => resource.resource_type === 'magnet').length;
  const hasProminentScore = getMovieScoreTier(item) !== null;
  return (
    <View style={[styles.mediaRow, { borderBottomColor: colors.border }]}>
      <TouchableOpacity
        activeOpacity={0.76}
        onPress={open}
        accessibilityRole="button"
        accessibilityLabel={item.title}
      >
        <MediaPoster
          item={item}
          colors={colors}
          style={{ width: ROW_COVER_WIDTH, height: ROW_COVER_HEIGHT }}
        />
      </TouchableOpacity>
      <View style={styles.mediaInfo}>
        <CopyableMediaTitle
          title={item.title}
          onCopied={onTitleCopied}
          style={[styles.mediaTitle, { color: hasProminentScore ? '#dc2626' : colors.text }]}
          numberOfLines={2}
        />
        <TouchableOpacity
          style={styles.mediaDetailTouch}
          activeOpacity={0.7}
          onPress={open}
          accessibilityRole="button"
          accessibilityLabel={item.title}
        >
          {!!metadata && (
            <Text style={[styles.mediaMeta, { color: colors.textTertiary }]} numberOfLines={2}>
              {metadata}
            </Text>
          )}
          <MovieTagRow item={item} colors={colors} qualityTags={visibleTags} />
          <View style={styles.rowFooter}>
            {!!seriesStatus && (
              <Text style={[styles.mediaStatus, { color: colors.text }]} numberOfLines={1}>
                {seriesStatus}
              </Text>
            )}
            <Text style={[styles.resourceText, { color: colors.textTertiary }]}>
              {resourceLabel(magnetCount)}
            </Text>
          </View>
        </TouchableOpacity>
      </View>
      <TouchableOpacity
        style={styles.mediaChevronTouch}
        activeOpacity={0.7}
        onPress={open}
        accessibilityRole="button"
        accessibilityLabel={item.title}
      >
        <Ionicons name="chevron-forward" size={18} color={colors.textTertiary} />
      </TouchableOpacity>
    </View>
  );
});

export default function ResourcesScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { lang } = useLang();
  const { colors } = useTheme();
  const copy = getResourceCopy(lang);
  const [activeChannel, setActiveChannel] = useState<MediaChannel>('movie');
  const [activeGenre, setActiveGenre] = useState<string | null>(null);
  const [feeds, setFeeds] = useState<Partial<Record<MediaKind, MovieFeed>>>({});
  const [loadingKind, setLoadingKind] = useState<MediaKind | null>('movie');
  const [refreshingKind, setRefreshingKind] = useState<MediaKind | null>(null);
  const [failedKinds, setFailedKinds] = useState<Partial<Record<MediaKind, boolean>>>({});
  const [titleCopyToastNonce, setTitleCopyToastNonce] = useState(0);

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

  useEffect(() => {
    setActiveGenre(null);
  }, [activeChannel]);

  useEffect(() => {
    if (titleCopyToastNonce === 0) return undefined;
    const timer = setTimeout(() => setTitleCopyToastNonce(0), TITLE_COPY_TOAST_MS);
    return () => clearTimeout(timer);
  }, [titleCopyToastNonce]);

  const showTitleCopiedToast = useCallback(() => {
    setTitleCopyToastNonce((current) => current + 1);
  }, []);

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

  const genreOptions = useMemo(() => {
    const counts = new Map<string, number>();
    recent.forEach((item) => {
      item.genres.forEach((genre) => {
        const normalized = normalizeGenreLabel(genre);
        if (!normalized) return;
        counts.set(normalized, (counts.get(normalized) ?? 0) + 1);
      });
    });
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], 'zh-CN'))
      .map(([genre]) => genre);
  }, [recent]);

  const visibleRecent = useMemo(
    () => activeGenre
      ? recent.filter((item) => normalizedGenres(item).includes(activeGenre))
      : recent,
    [activeGenre, recent],
  );

  const renderSpotlight = useCallback((item: MovieFeedItem) => (
    <SpotlightCard
      key={resourceFeedItemKey(item)}
      item={item}
      colors={colors}
      badgeText={copy.recommendation}
      onTitleCopied={showTitleCopiedToast}
      onOpen={openMedia}
    />
  ), [colors, copy.recommendation, openMedia, showTitleCopiedToast]);

  const renderItem = useCallback(({ item }: { item: MovieFeedItem }) => (
    <MediaRow
      item={item}
      colors={colors}
      minutesLabel={copy.minutes}
      resourceLabel={copy.resourceCount}
      onTitleCopied={showTitleCopiedToast}
      onOpen={openMedia}
    />
  ), [colors, copy.minutes, copy.resourceCount, openMedia, showTitleCopiedToast]);

  const channelLabel = useCallback((channel: MediaChannel) => {
    if (channel === 'movie') return copy.mediaMovies;
    if (channel === 'us') return copy.mediaUsSeries;
    if (channel === 'korea') return copy.mediaKoreanSeries;
    if (channel === 'japan') return copy.mediaJapaneseSeries;
    if (channel === 'china') return copy.mediaChineseSeries;
    return copy.mediaUkSeries;
  }, [copy]);

  const channelBar = (
    <View style={[styles.channelShell, { backgroundColor: colors.bg }]}>
      <View style={[styles.channelViewport, { backgroundColor: colors.card, borderColor: colors.border }]}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.channelContent}
        >
          {CHANNELS.map((channel, index) => {
            const active = activeChannel === channel;
            return (
              <React.Fragment key={channel}>
                <TouchableOpacity
                  style={styles.channelButton}
                  activeOpacity={0.82}
                  onPress={() => setActiveChannel(channel)}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={channelLabel(channel)}
                >
                  {active ? (
                    <LinearGradient
                      colors={['#3867f5', '#2753d7']}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 1 }}
                      style={styles.channelSegment}
                    >
                      <Text style={[styles.channelText, styles.channelTextActive]}>
                        {channelLabel(channel)}
                      </Text>
                      <View style={styles.channelActiveMark} />
                    </LinearGradient>
                  ) : (
                    <View style={styles.channelSegment}>
                      <Text style={[styles.channelText, { color: colors.textSecondary }]}>
                        {channelLabel(channel)}
                      </Text>
                    </View>
                  )}
                </TouchableOpacity>
                {index < CHANNELS.length - 1 && (
                  <View style={[styles.channelDivider, { backgroundColor: colors.border }]} />
                )}
              </React.Fragment>
            );
          })}
        </ScrollView>
      </View>
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

      {genreOptions.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.genreContent}
        >
          {[null, ...genreOptions].map((genre) => {
            const active = activeGenre === genre;
            return (
              <TouchableOpacity
                key={genre ?? 'all'}
                style={[
                  styles.genreChip,
                  {
                    backgroundColor: active ? colors.accent : colors.chipBg,
                    borderColor: active ? colors.accent : colors.border,
                  },
                ]}
                activeOpacity={0.8}
                onPress={() => setActiveGenre(genre)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
              >
                <Text style={[styles.genreText, { color: active ? '#fff' : colors.textSecondary }]}>
                  {genre ?? copy.genreAll}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      )}
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
    activeGenre,
    colors.accent,
    colors.border,
    colors.chipBg,
    colors.textSecondary,
    copy.genreAll,
    genreOptions,
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
          data={visibleRecent}
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

      {titleCopyToastNonce > 0 && (
        <View
          pointerEvents="none"
          style={[styles.copyToastLayer, { bottom: Math.max(insets.bottom, 8) + 76 }]}
        >
          <View style={styles.copyToast}>
            <Ionicons name="checkmark-circle" size={16} color="#fff" />
            <Text style={styles.copyToastText}>{copy.copiedAction}</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  copyToastLayer: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 40,
  },
  copyToast: {
    minHeight: 38,
    borderRadius: 999,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: 'rgba(17,24,39,0.94)',
  },
  copyToastText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 36,
  },
  loadingText: { marginTop: 14, fontSize: 14 },
  listContent: { paddingBottom: 24 },
  channelShell: {
    paddingTop: 10,
    paddingBottom: 8,
  },
  channelViewport: {
    marginHorizontal: 14,
    height: 62,
    borderRadius: 20,
    borderWidth: 1,
    overflow: 'hidden',
  },
  channelContent: { paddingHorizontal: 5, paddingVertical: 5, alignItems: 'center' },
  channelButton: {
    minWidth: 78,
    height: 52,
  },
  channelSegment: {
    flex: 1,
    borderRadius: 16,
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  channelDivider: { width: StyleSheet.hairlineWidth, height: 24, opacity: 0.72 },
  channelText: { fontSize: 16, fontWeight: '800', letterSpacing: -0.25 },
  channelTextActive: { color: '#fff', fontSize: 18, fontWeight: '900' },
  channelActiveMark: {
    position: 'absolute',
    bottom: 6,
    width: 18,
    height: 3,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.92)',
  },
  spotlightSection: { marginTop: 14, marginBottom: 10 },
  sectionHeadingRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  sectionTitle: {
    paddingHorizontal: 20,
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: -0.3,
  },
  sectionHint: { paddingRight: 20, fontSize: 11, fontWeight: '600' },
  latestTitle: { marginTop: 0, marginBottom: 0 },
  spotlightContent: { paddingHorizontal: 20, paddingTop: 10, paddingRight: 8 },
  genreContent: { paddingHorizontal: 20, paddingTop: 10, paddingBottom: 3, paddingRight: 8 },
  genreChip: {
    height: 34,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 16,
    marginRight: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  genreText: { fontSize: 13, fontWeight: '800' },
  spotlightCard: { width: SPOTLIGHT_WIDTH, marginRight: 13 },
  spotlightPosterWrap: { position: 'relative' },
  posterShell: { borderRadius: 14, overflow: 'hidden' },
  posterImage: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    width: '100%',
    height: '100%',
  },
  posterFallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  posterFallbackText: { marginTop: 8, fontSize: 10, lineHeight: 14, fontWeight: '700', textAlign: 'center' },
  updateOverlay: {
    position: 'absolute',
    left: 8,
    bottom: 8,
    minHeight: 32,
    maxWidth: '88%',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.38)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  updateOverlayText: { color: '#fff', fontSize: 13, lineHeight: 18, fontWeight: '900' },
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
  mediaDetailTouch: { flex: 1 },
  mediaChevronTouch: {
    width: 34,
    alignSelf: 'stretch',
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  mediaMeta: { marginTop: 6, fontSize: 11, lineHeight: 16 },
  mediaStatus: { flex: 1, fontSize: 13, lineHeight: 18, fontWeight: '400' },
  rowFooter: {
    marginTop: 'auto',
    minHeight: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  resourceText: { flexShrink: 0, fontSize: 10, fontWeight: '500' },
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
