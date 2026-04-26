import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  Alert,
  Animated,
  Easing,
  Linking,
  Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Clipboard from 'expo-clipboard';
import { useSources } from '../src/core/SourceContext';
import { useLang } from '../src/core/LangContext';
import {
  SearchResult,
  ResultCardModel,
  toResultCardModel,
} from '../src/core/types';
import { searchSource } from '../src/core/searchEngine';
import { deduplicateResults } from '../src/core/dedup';
import { addHistory } from '../src/core/searchHistory';
import { addFavorite, removeFavorite, getFavorites, type FavoriteItem } from '../src/core/favorites';
import { VerifyManager, type VerifyRequest } from '../src/core/VerifyManager';
import VerifyWebView from '../src/components/VerifyWebView';
import FeedbackFAB from '../src/components/FeedbackFAB';
import { useTheme } from '../src/core/ThemeContext';

// ── Bouncing dots component ─────────────────────────────────────────
function BouncingDots() {
  const d1 = useRef(new Animated.Value(0)).current;
  const d2 = useRef(new Animated.Value(0)).current;
  const d3 = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const bounce = (v: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(v, { toValue: -6, duration: 250, easing: Easing.out(Easing.quad), useNativeDriver: true }),
          Animated.timing(v, { toValue: 0, duration: 250, easing: Easing.in(Easing.quad), useNativeDriver: true }),
        ]),
      );
    bounce(d1, 0).start();
    bounce(d2, 150).start();
    bounce(d3, 300).start();
  }, [d1, d2, d3]);

  const dot = (v: Animated.Value) => (
    <Animated.Text style={[s.dotText, { transform: [{ translateY: v }] }]}>.</Animated.Text>
  );
  const s = StyleSheet.create({ dotText: { fontSize: 18, fontWeight: '800', color: '#4285F4', lineHeight: 18 } });
  return <View style={{ flexDirection: 'row' }}>{dot(d1)}{dot(d2)}{dot(d3)}</View>;
}

// ── Animated card wrapper ───────────────────────────────────────────
function AnimatedCard({ index, children }: { index: number; children: React.ReactNode }) {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(24)).current;

  useEffect(() => {
    const delay = Math.min(index * 60, 500);
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 350, delay, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: 0, duration: 350, delay, easing: Easing.out(Easing.quad), useNativeDriver: true }),
    ]).start();
  }, [index, opacity, translateY]);

  return <Animated.View style={{ opacity, transform: [{ translateY }] }}>{children}</Animated.View>;
}

// ── Sort types ──────────────────────────────────────────────────────
type SortKey = 'relevance' | 'size' | 'date';
type SortDir = 'desc' | 'asc';
const RELEVANCE_THRESHOLD = 30;
type ListItem = ResultCardModel | { _divider: true; id: string };

function parseSizeBytes(label: string): number {
  if (!label) return 0;
  const m = label.match(/([\d.]+)\s*(TB|GB|MB|KB|B)/i);
  if (!m) return 0;
  const v = parseFloat(m[1]);
  const u = m[2].toUpperCase();
  const map: Record<string, number> = { B: 1, KB: 1024, MB: 1048576, GB: 1073741824, TB: 1099511627776 };
  return v * (map[u] || 0);
}

function parseDate(label: string): number {
  if (!label) return 0;
  const d = new Date(label);
  return isNaN(d.getTime()) ? 0 : d.getTime();
}

// ── Main Screen ─────────────────────────────────────────────────────
export default function SearchScreen() {
  const { q } = useLocalSearchParams<{ q: string }>();
  const [query, setQuery] = useState(q || '');
  const [results, setResults] = useState<ResultCardModel[]>([]);
  const [searching, setSearching] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [sourceCount, setSourceCount] = useState(0);
  const [doneCount, setDoneCount] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>('relevance');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [favSet, setFavSet] = useState<Set<string>>(new Set());
  const { sources } = useSources();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { t } = useLang();
  const { colors } = useTheme();
  const resultAccum = useRef<SearchResult[]>([]);

  useEffect(() => {
    getFavorites().then((favs) => setFavSet(new Set(favs.map((f) => f.magnet))));
  }, []);

  // ── Legado-style verification: register listener for challenge events ──
  const [verifyRequest, setVerifyRequest] = useState<VerifyRequest | null>(null);
  useEffect(() => {
    VerifyManager.setListener((req) => setVerifyRequest(req));
    return () => VerifyManager.setListener(null);
  }, []);

  const doSearch = useCallback(
    async (term: string) => {
      if (!term.trim() || sources.length === 0) return;
      addHistory(term.trim());
      setSearching(true);
      setResults([]);
      setSortKey('relevance');
      setSortDir('desc');
      resultAccum.current = [];
      setDoneCount(0);

      // Sort: non-verification sources first, verification sources last
      const allSources = [...sources].sort((a, b) => {
        const aV = (a as any).search?.requires_browser ? 1 : VerifyManager.isVerifyOrigin((a as any).site?.origin) ? 1 : 0;
        const bV = (b as any).search?.requires_browser ? 1 : VerifyManager.isVerifyOrigin((b as any).site?.origin) ? 1 : 0;
        return aV - bV;
      });
      setSourceCount(allSources.length);

      // Concurrency-limited pool: run up to 8 source searches at a time (locally on device)
      const CONCURRENCY = 8;
      let cursor = 0;
      const runNext = async (): Promise<void> => {
        while (cursor < allSources.length) {
          const idx = cursor++;
          const rule = allSources[idx];
          try {
            const items = await searchSource(rule as any, term);
            if (items.length > 0) {
              // Map engine ResultItem → app SearchResult
              const mapped: SearchResult[] = items.map((r) => ({
                title: r.title,
                magnet: r.magnet,
                size: r.size,
                date: r.date,
                source: r.source,
                site_name: r.site_name,
              }));
              resultAccum.current.push(...mapped);
              const deduped = deduplicateResults(resultAccum.current);
              const models = deduped.map((r, i) => toResultCardModel(r, i, term, t));
              setResults(models);
            }
          } catch {
            // skip failed source
          } finally {
            setDoneCount((c) => c + 1);
          }
        }
      };
      await Promise.allSettled(
        Array.from({ length: Math.min(CONCURRENCY, allSources.length) }, () => runNext()),
      );

      setSearching(false);
    },
    [sources],
  );

  useEffect(() => {
    if (q) doSearch(q);
  }, [q, doSearch]);

  // ── Sorting + relevance divider ─────────────────────────────────────────
  const sortedResults = React.useMemo((): ListItem[] => {
    const arr = [...results];
    if (sortKey === 'relevance') {
      arr.sort((a, b) => b.relevance - a.relevance);
      // Inject divider between high and low relevance
      const dividerIdx = arr.findIndex((r) => r.relevance < RELEVANCE_THRESHOLD);
      if (dividerIdx > 0 && dividerIdx < arr.length) {
        const out: ListItem[] = arr.slice(0, dividerIdx);
        out.push({ _divider: true, id: '__relevance_divider__' });
        out.push(...arr.slice(dividerIdx));
        return out;
      }
      return arr;
    }
    arr.sort((a, b) => {
      let va: number, vb: number;
      if (sortKey === 'size') {
        va = parseSizeBytes(a.sizeLabel);
        vb = parseSizeBytes(b.sizeLabel);
      } else {
        va = parseDate(a.dateLabel);
        vb = parseDate(b.dateLabel);
      }
      return sortDir === 'desc' ? vb - va : va - vb;
    });
    return arr;
  }, [results, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (key === 'relevance') {
      setSortKey('relevance');
      setSortDir('desc');
      return;
    }
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  // ── Handlers ────────────────────────────────────────────────────
  const handleCopy = async (model: ResultCardModel) => {
    try {
      await Clipboard.setStringAsync(model.magnet);
      setCopiedId(model.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      Alert.alert(t.copyFailed);
    }
  };

  const handleOpen = (magnet: string) => {
    Linking.openURL(magnet).catch(() =>
      Alert.alert(t.cannotOpen, t.cannotOpenMsg),
    );
  };

  const handleToggleFav = async (item: ResultCardModel) => {
    const isFav = favSet.has(item.magnet);
    if (isFav) {
      await removeFavorite(item.magnet);
    } else {
      await addFavorite({
        id: item.id,
        title: item.title,
        magnet: item.magnet,
        size: item.sizeLabel,
        sourceName: item.sourceName,
      });
    }
    const updated = await getFavorites();
    setFavSet(new Set(updated.map((f) => f.magnet)));
  };

  // ── Card / divider renderer ─────────────────────────────────────────────────
  const renderListItem = ({ item, index }: { item: ListItem; index: number }) => {
    if ('_divider' in item) {
      return (
        <View style={styles.relevanceDivider}>
          <View style={styles.relevanceLine} />
          <Text style={styles.relevanceLabel}>{t.lowRelevanceHint}</Text>
          <View style={styles.relevanceLine} />
        </View>
      );
    }
    const theme = item.theme;
    const copied = copiedId === item.id;
    const hasMagnet = !!item.magnet && item.magnet.startsWith('magnet:');
    const isFav = favSet.has(item.magnet);

    return (
      <AnimatedCard index={index}>
        <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow }]}>
          <View style={styles.cardRow}>
            <LinearGradient
              colors={theme.tileColors as [string, string]}
              style={styles.iconTile}
            >
              <Ionicons name={theme.iconName as any} size={22} color={theme.iconColor} />
            </LinearGradient>
            <View style={styles.cardContent}>
              <View style={styles.titleRow}>
                <Text style={[styles.cardTitle, { flex: 1, color: colors.text }]} numberOfLines={2}>{item.title}</Text>
                <TouchableOpacity onPress={() => handleToggleFav(item)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Ionicons name={isFav ? 'star' : 'star-outline'} size={18} color={isFav ? '#f59e0b' : '#d0d5dd'} />
                </TouchableOpacity>
              </View>
              <View style={styles.cardMetaRow}>
                <Text style={[styles.cardMeta, { color: colors.textTertiary }]}>
                  {item.kindLabel}
                  {item.sizeLabel ? ` | ${item.sizeLabel}` : ''}
                  {item.fileCountLabel ? ` | ${item.fileCountLabel}` : ''}
                  {item.dateLabel ? ` | ${item.dateLabel}` : ''}
                </Text>
              </View>
            </View>
          </View>

          {/* Tags + Buttons row */}
          <View style={styles.tagsRow}>
            {item.tags.map((tag) => (
              <View key={tag} style={[styles.tagPill, { backgroundColor: colors.tagBg }]}>
                <Text style={[styles.tagText, { color: colors.tagText }]}>{tag}</Text>
              </View>
            ))}

            <View style={styles.btnGroup}>
              {hasMagnet && (
                <>
                  <TouchableOpacity onPress={() => handleCopy(item)} activeOpacity={0.8}>
                    <LinearGradient colors={['#4e8aff', '#2c63f4']} style={styles.actionBtn}>
                      <Ionicons name="copy-outline" size={13} color="#fff" />
                      <Text style={styles.actionBtnText}>{copied ? t.copied : t.copyMagnet}</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleOpen(item.magnet)} activeOpacity={0.8}>
                    <LinearGradient colors={['#ff8a4c', '#f06529']} style={styles.actionBtn}>
                      <Ionicons name="open-outline" size={13} color="#fff" />
                      <Text style={styles.actionBtnText}>{t.openMagnet}</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                </>
              )}
            </View>
          </View>
        </View>
      </AnimatedCard>
    );
  };

  // ── Sort bar helper ─────────────────────────────────────────────
  const SortChip = ({ label, k }: { label: string; k: SortKey }) => {
    const active = sortKey === k;
    const arrow =
      k === 'relevance' ? null : active ? (sortDir === 'desc' ? '↓' : '↑') : null;
    return (
      <TouchableOpacity
        style={[styles.sortChip, { backgroundColor: colors.chipBg }, active && { backgroundColor: colors.chipActiveBg }]}
        onPress={() => toggleSort(k)}
      >
        <Text style={[styles.sortChipText, active && styles.sortChipTextActive]}>
          {label}{arrow ? ` ${arrow}` : ''}
        </Text>
      </TouchableOpacity>
    );
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Image
          source={require('../assets/logo2.png')}
          style={styles.topLogo}
          resizeMode="contain"
        />
        <View style={[styles.topSearch, { backgroundColor: colors.inputBg }]}>
          <Ionicons name="search" size={16} color={colors.textTertiary} />
          <TextInput
            style={[styles.topInput, { color: colors.text }]}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => doSearch(query)}
            returnKeyType="search"
            placeholder={t.searchPlaceholder}
            placeholderTextColor={colors.textTertiary}
            maxLength={100}
          />
          {query.length > 0 && (
            <TouchableOpacity onPress={() => setQuery('')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="close-circle" size={18} color="#c0c6d0" />
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Status */}
      <View style={styles.statusRow}>
        {searching ? (
          <View style={styles.statusInner}>
            <Text style={styles.statusText}>
              {t.searchingStatus(sourceCount, results.length)}
            </Text>
            <BouncingDots />
          </View>
        ) : results.length > 0 ? (
          <Text style={styles.statusText}>
            {t.searchDoneStatus(sourceCount, results.length)}
          </Text>
        ) : sources.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="cloud-download-outline" size={48} color="#ccc" />
            <Text style={styles.emptyText}>{t.noSourcesHint}</Text>
            <TouchableOpacity onPress={() => router.push('/settings')}>
              <Text style={styles.emptyLink}>{t.goToSettings}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>

      {/* Sort bar */}
      {results.length > 0 && (
        <View style={styles.sortBar}>
          <SortChip label={t.sortRelevance} k="relevance" />
          <SortChip label={t.sortSize} k="size" />
          <SortChip label={t.sortDate} k="date" />
        </View>
      )}

      {/* Results */}
      <FlatList<ListItem>
        data={sortedResults}
        renderItem={renderListItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
      />

      <FeedbackFAB />

      {/* Legado-style WebView verification modal */}
      <VerifyWebView
        request={verifyRequest}
        onDismiss={() => setVerifyRequest(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fffdfb' },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 0,
    gap: 0,
  },
  topLogo: {
    width: 80,
    height: 80,
    borderRadius: 8,
  },
  topSearch: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.85)',
    paddingHorizontal: 14,
    gap: 8,
    shadowColor: '#b4aa9b',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 4,
  },
  topInput: {
    flex: 1,
    fontSize: 15,
    fontWeight: '500',
    color: '#5d6578',
  },
  statusRow: {
    paddingHorizontal: 20,
    paddingTop: 0,
    paddingBottom: 8,
  },
  statusInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  statusText: {
    fontSize: 13,
    color: '#4285F4',
    fontWeight: '600',
  },
  sortBar: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 8,
  },
  sortChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f4f2ef',
  },
  sortChipActive: {
    backgroundColor: '#4285F4',
  },
  sortChipText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#9aa3b4',
  },
  sortChipTextActive: {
    color: '#fff',
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 24,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#e4dfd6',
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.3,
    shadowRadius: 32,
    elevation: 4,
  },
  cardRow: {
    flexDirection: 'row',
    gap: 12,
  },
  iconTile: {
    width: 44,
    height: 44,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardContent: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#262b35',
    lineHeight: 19,
    marginBottom: 4,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  cardMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  cardMeta: {
    fontSize: 12,
    color: '#9aa3b4',
    fontWeight: '500',
    flexShrink: 1,
  },
  tagsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
    gap: 6,
    flexWrap: 'wrap',
  },
  tagPill: {
    backgroundColor: '#f0f4ff',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  tagText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#4285F4',
  },
  btnGroup: {
    flexDirection: 'row',
    marginLeft: 'auto',
    gap: 6,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 28,
    paddingHorizontal: 10,
    borderRadius: 10,
    gap: 4,
  },
  actionBtnText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#fff',
  },
  emptyState: {
    alignItems: 'center',
    paddingTop: 80,
    gap: 12,
  },
  emptyText: {
    fontSize: 15,
    color: '#9aa3b4',
  },
  emptyLink: {
    fontSize: 14,
    color: '#4285F4',
    fontWeight: '600',
  },
  relevanceDivider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 12,
    gap: 10,
  },
  relevanceLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: '#e0dcd6',
  },
  relevanceLabel: {
    fontSize: 11,
    color: '#b0b8c8',
    fontWeight: '500',
  },
});
