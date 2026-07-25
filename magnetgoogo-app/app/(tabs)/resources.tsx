import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  FlatList,
  Image,
  RefreshControl,
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
import { addHistory } from '../../src/core/searchHistory';
import { getResourceCopy } from '../../src/core/resourceCopy';
import { loadResourceFeed, type ResourceFeedOrigin } from '../../src/core/resourceFeed';
import {
  resourceFeedItemKey,
  type ResourceFeed,
  type ResourceFeedItem,
} from '../../src/core/resourceFeedProtocol';

const SCREEN_WIDTH = Dimensions.get('window').width;
const PAGE_PADDING = 16;
const CARD_GAP = 12;
const CARD_WIDTH = (SCREEN_WIDTH - PAGE_PADDING * 2 - CARD_GAP) / 2;
const COVER_HEIGHT = Math.round(CARD_WIDTH * 1.38);

interface ResourceCardProps {
  item: ResourceFeedItem;
  colors: Colors;
  minutesLabel: (value: number) => string;
  resourceCountLabel: (value: number) => string;
  searchLabel: string;
  onOpen: (code: string) => void;
}

const ResourceCard = memo(function ResourceCard({
  item,
  colors,
  minutesLabel,
  resourceCountLabel,
  searchLabel,
  onOpen,
}: ResourceCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const handleOpen = useCallback(() => onOpen(item.content_code), [item.content_code, onOpen]);
  const people = item.people.slice(0, 2).map((person) => person.display_name).join(' · ');
  const metadata = [
    item.release_date,
    item.duration_minutes === null ? null : minutesLabel(item.duration_minutes),
  ].filter(Boolean).join(' · ');

  return (
    <TouchableOpacity
      style={[
        styles.card,
        {
          width: CARD_WIDTH,
          backgroundColor: colors.card,
          borderColor: colors.border,
          shadowColor: colors.shadow,
        },
      ]}
      activeOpacity={0.82}
      onPress={handleOpen}
      accessibilityRole="button"
      accessibilityLabel={`${item.content_code} ${searchLabel}`}
    >
      <View style={[styles.coverWrap, { height: COVER_HEIGHT, backgroundColor: colors.chipBg }]}>
        {imageFailed ? (
          <View style={styles.coverFallback}>
            <Ionicons name="image-outline" size={34} color={colors.textTertiary} />
          </View>
        ) : (
          <Image
            source={{ uri: item.cover_source_url }}
            style={styles.cover}
            resizeMode="cover"
            onError={() => setImageFailed(true)}
          />
        )}
        <View style={styles.rankBadge}>
          <Text style={styles.rankText}>#{item.rank}</Text>
        </View>
        <View style={styles.searchBadge}>
          <Ionicons name="search" size={12} color="#fff" />
          <Text style={styles.searchBadgeText}>{searchLabel}</Text>
        </View>
      </View>

      <View style={styles.cardBody}>
        <Text style={[styles.code, { color: colors.accent }]} numberOfLines={1}>
          {item.content_code}
        </Text>
        <Text style={[styles.title, { color: colors.text }]} numberOfLines={2}>
          {item.title}
        </Text>
        {!!people && (
          <Text style={[styles.people, { color: colors.textSecondary }]} numberOfLines={1}>
            {people}
          </Text>
        )}
        {!!metadata && (
          <Text style={[styles.meta, { color: colors.textTertiary }]} numberOfLines={1}>
            {metadata}
          </Text>
        )}
        <View style={styles.cardFooter}>
          <Ionicons name="magnet-outline" size={13} color={colors.textTertiary} />
          <Text style={[styles.resourceCount, { color: colors.textTertiary }]}>
            {resourceCountLabel(item.resource_count)}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );
});

export default function ResourcesScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { lang } = useLang();
  const { colors } = useTheme();
  const copy = getResourceCopy(lang);
  const [feed, setFeed] = useState<ResourceFeed | null>(null);
  const [origin, setOrigin] = useState<ResourceFeedOrigin | null>(null);
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
      setOrigin(loaded.origin);
    } catch (error) {
      console.warn('[ResourcesScreen]', {
        stage: 'load_feed',
        error_code: 'RESOURCE_FEED_LOAD_FAILED',
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

  const handleOpen = useCallback(async (code: string) => {
    try {
      await addHistory(code);
    } catch (error) {
      console.warn('[ResourcesScreen]', {
        stage: 'save_history',
        error_code: 'RESOURCE_HISTORY_SAVE_FAILED',
        query: code,
        error: error instanceof Error ? error.message : String(error),
      });
    }
    router.push({ pathname: '/search', params: { q: code } });
  }, [router]);

  const generatedAt = useMemo(() => {
    if (!feed?.summary.generated_at) return '';
    const date = new Date(feed.summary.generated_at);
    if (Number.isNaN(date.getTime())) return feed.summary.generated_at;
    return date.toLocaleString(lang === 'zh' ? 'zh-CN' : lang, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, [feed?.summary.generated_at, lang]);

  const renderItem = useCallback(({ item }: { item: ResourceFeedItem }) => (
    <ResourceCard
      item={item}
      colors={colors}
      minutesLabel={copy.minutes}
      resourceCountLabel={copy.resourceCount}
      searchLabel={copy.searchAction}
      onOpen={handleOpen}
    />
  ), [colors, copy.minutes, copy.resourceCount, copy.searchAction, handleOpen]);

  const header = useMemo(() => (
    <View style={styles.headerBlock}>
      <View style={styles.titleRow}>
        <View style={styles.titleGroup}>
          <Text style={[styles.pageTitle, { color: colors.text }]}>{copy.title}</Text>
          <Text style={[styles.subtitle, { color: colors.textTertiary }]}>
            {copy.subtitle(feed?.items.length ?? 0)}
          </Text>
        </View>
        {origin && (
          <View style={[styles.originChip, { backgroundColor: colors.tagBg }]}>
            <View style={[styles.originDot, { backgroundColor: origin === 'remote' ? '#22c55e' : '#f59e0b' }]} />
            <Text style={[styles.originText, { color: colors.tagText }]}>
              {origin === 'remote' ? copy.sourceRemote : copy.sourceBundled}
            </Text>
          </View>
        )}
      </View>

      <View style={[styles.hint, { backgroundColor: colors.chipBg }]}>
        <Ionicons name="sparkles-outline" size={17} color={colors.accent} />
        <Text style={[styles.hintText, { color: colors.textSecondary }]}>{copy.tapHint}</Text>
      </View>

      {!!generatedAt && (
        <Text style={[styles.updatedAt, { color: colors.textTertiary }]}>
          {copy.updatedAt} {generatedAt}
        </Text>
      )}
    </View>
  ), [colors, copy, feed?.items.length, generatedAt, origin]);

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
          <Ionicons name="albums-outline" size={34} color={colors.textTertiary} />
        </View>
        <Text style={[styles.emptyTitle, { color: colors.text }]}>{copy.emptyTitle}</Text>
        <Text style={[styles.emptyBody, { color: colors.textTertiary }]}>{copy.emptyBody}</Text>
        <TouchableOpacity style={[styles.retryButton, { backgroundColor: colors.accent }]} onPress={() => void load(true)}>
          <Text style={styles.retryText}>{copy.retry}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <FlatList
        data={feed?.items ?? []}
        renderItem={renderItem}
        keyExtractor={resourceFeedItemKey}
        numColumns={2}
        columnWrapperStyle={styles.row}
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
  listContent: {
    paddingHorizontal: PAGE_PADDING,
    paddingBottom: 24,
  },
  row: {
    justifyContent: 'space-between',
    marginBottom: CARD_GAP,
  },
  headerBlock: {
    paddingTop: 12,
    paddingBottom: 16,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  titleGroup: { flex: 1, paddingRight: 10 },
  pageTitle: { fontSize: 26, fontWeight: '800', letterSpacing: -0.4 },
  subtitle: { marginTop: 5, fontSize: 13 },
  originChip: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  originDot: { width: 6, height: 6, borderRadius: 3, marginRight: 5 },
  originText: { fontSize: 10, fontWeight: '700' },
  hint: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginTop: 14,
  },
  hintText: { flex: 1, marginLeft: 8, fontSize: 12, lineHeight: 18 },
  updatedAt: { marginTop: 9, fontSize: 11 },
  card: {
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 10,
    elevation: 2,
  },
  coverWrap: { width: '100%', position: 'relative', overflow: 'hidden' },
  cover: { width: '100%', height: '100%' },
  coverFallback: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  rankBadge: {
    position: 'absolute',
    top: 8,
    left: 8,
    backgroundColor: 'rgba(17,24,39,0.78)',
    borderRadius: 8,
    paddingHorizontal: 7,
    paddingVertical: 4,
  },
  rankText: { color: '#fff', fontSize: 10, fontWeight: '800' },
  searchBadge: {
    position: 'absolute',
    right: 8,
    bottom: 8,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(66,133,244,0.92)',
    borderRadius: 10,
    paddingHorizontal: 7,
    paddingVertical: 5,
  },
  searchBadgeText: { color: '#fff', fontSize: 10, fontWeight: '700', marginLeft: 3 },
  cardBody: { minHeight: 126, padding: 10 },
  code: { fontSize: 13, fontWeight: '800', letterSpacing: 0.2 },
  title: { marginTop: 5, fontSize: 12, lineHeight: 17, fontWeight: '600' },
  people: { marginTop: 6, fontSize: 10 },
  meta: { marginTop: 4, fontSize: 10 },
  cardFooter: { flexDirection: 'row', alignItems: 'center', marginTop: 'auto', paddingTop: 8 },
  resourceCount: { marginLeft: 4, fontSize: 10, fontWeight: '600' },
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
