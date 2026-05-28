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
  Platform,
  Vibration,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Clipboard from 'expo-clipboard';
import { useSources } from '../src/core/SourceContext';
import { useLang } from '../src/core/LangContext';
import { isBlockedContent } from '../src/core/complianceConfig';
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
import { trackSearch, trackCopy, trackOpen, trackSourceResult } from '../src/core/analytics';
import { startReport, type ReportBuilder, type ResultItemLog } from '../src/core/searchDebugLogger';
import { computeRelevance } from '../src/core/types';
import { BrandTracker } from '../src/core/brandDedup';

// ── Search throttle (5s cooldown) ──────────────────────────────────────
const SEARCH_COOLDOWN_MS = 3000;
let _lastSearchTime = 0;

// ── Module-level search session (survives component unmount) ────────────
// When the user navigates away, the search promises keep running and
// updating this cache.  When the component re-mounts, it restores
// state from here instead of re-searching.
interface _Session {
  query: string;
  rawResults: SearchResult[];
  searching: boolean;
  sourceCount: number;
  doneCount: number;
  abortRef: { current: boolean };
  // Mounted component's setState callbacks — null when unmounted
  _notify: (() => void) | null;
}
let _session: _Session | null = null;

// ── Skeleton card component ─────────────────────────────────────────
function SkeletonCard({ cardBg, shimmerBg, tileBg }: { cardBg: string; shimmerBg: string; tileBg: string }) {
  const opacity = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ]),
    ).start();
  }, [opacity]);
  const bar = (w: number | `${number}%`, h: number, mt = 0) => (
    <Animated.View style={{ width: w, height: h, borderRadius: h / 2, backgroundColor: shimmerBg, opacity, marginTop: mt }} />
  );
  return (
    <View style={{ backgroundColor: cardBg, borderRadius: 24, padding: 16, marginBottom: 12, marginHorizontal: 16 }}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Animated.View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: tileBg, opacity }} />
        <View style={{ flex: 1 }}>
          {bar('90%' as `${number}%`, 14)}
          {bar('60%' as `${number}%`, 14, 6)}
          {bar('40%' as `${number}%`, 12, 8)}
        </View>
      </View>
      <View style={{ flexDirection: 'row', gap: 6, marginTop: 12 }}>
        {bar(52, 22)}
        {bar(44, 22)}
        {bar(36, 22)}
      </View>
    </View>
  );
}

function SkeletonList({ cardBg, shimmerBg, tileBg }: { cardBg: string; shimmerBg: string; tileBg: string }) {
  return (
    <View style={{ paddingTop: 8 }}>
      {[0, 1, 2, 3].map((i) => (
        <SkeletonCard key={i} cardBg={cardBg} shimmerBg={shimmerBg} tileBg={tileBg} />
      ))}
    </View>
  );
}

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
const MAX_ANIMATED_CARDS = 8;
function AnimatedCard({ index, children }: { index: number; children: React.ReactNode }) {
  // Only animate first N cards; rest render instantly to reduce overhead
  if (index >= MAX_ANIMATED_CARDS) return <View>{children}</View>;

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
  const { lang, t } = useLang();
  const { colors } = useTheme();

  // ── Sync with module-level session on mount / unmount ──
  const syncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncFromSession = useCallback(() => {
    if (!_session) return;
    const models = deduplicateResults(_session.rawResults)
      .map((r, i) => toResultCardModel(r, i, _session!.query, t));
    setResults(models);
    setSearching(_session.searching);
    setSourceCount(_session.sourceCount);
    setDoneCount(_session.doneCount);
    setQuery(_session.query);
  }, [t]);

  // Debounced version: batch rapid _notify calls (every source completion)
  const debouncedSync = useCallback(() => {
    if (syncTimerRef.current) return;           // already scheduled
    syncTimerRef.current = setTimeout(() => {
      syncTimerRef.current = null;
      syncFromSession();
    }, 300);
  }, [syncFromSession]);

  useEffect(() => {
    // Subscribe: session calls this when async results arrive
    if (_session) _session._notify = debouncedSync;
    return () => {
      // Unsubscribe on unmount — search keeps running in background
      if (_session) _session._notify = null;
      if (syncTimerRef.current) { clearTimeout(syncTimerRef.current); syncTimerRef.current = null; }
    };
  }, [debouncedSync]);

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

      // Search throttle: 5s cooldown
      const now = Date.now();
      const elapsed = now - _lastSearchTime;
      if (elapsed < SEARCH_COOLDOWN_MS) {
        const wait = Math.ceil((SEARCH_COOLDOWN_MS - elapsed) / 1000);
        Alert.alert('', lang === 'zh' ? `搜索太频繁，请${wait}秒后再试` : `Please wait ${wait}s before searching again`);
        return;
      }
      _lastSearchTime = now;

      addHistory(term.trim());

      // Abort any previous session
      if (_session) _session.abortRef.current = true;

      // Create new session
      const session: _Session = {
        query: term,
        rawResults: [],
        searching: true,
        sourceCount: 0,
        doneCount: 0,
        abortRef: { current: false },
        _notify: debouncedSync,
      };
      _session = session;

      setSearching(true);
      setResults([]);
      setSortKey('relevance');
      setSortDir('desc');
      setDoneCount(0);

      // 3-tier scheduling: direct(fast) → detail/custom(medium) → browser(slow)
      const getSpeedTier = (s: any): number => {
        if (s.search?.requires_browser) return 2;
        if (VerifyManager.isVerifyOrigin(s.site?.origin)) return 2;
        if (s.capabilities?.supports_detail) return 1;
        if (s.search?.requires_csrf) return 1;
        const h = s.search?.handler || '';
        if (h && h !== 'std') return 1;
        return 0;
      };
      const sortedSources = [...sources].sort((a, b) => {
        const aTier = getSpeedTier(a);
        const bTier = getSpeedTier(b);
        if (aTier !== bTier) return aTier - bTier;
        const aScore = (a as any).quality?.score ?? 50;
        const bScore = (b as any).quality?.score ?? 50;
        return bScore - aScore;
      });
      const allSources = sortedSources;
      session.sourceCount = allSources.length;
      setSourceCount(allSources.length);

      // ── Brand-level dedup: runtime tracker ──
      const brandTracker = new BrandTracker();

      // ── Debug report ──
      const debugReport = startReport(term, allSources.length);

      const CONCURRENCY = 15;
      let cursor = 0;
      const runNext = async (): Promise<void> => {
        while (cursor < allSources.length && !session.abortRef.current) {
          const idx = cursor++;
          const rule = allSources[idx];
          const srcName = (rule as any).site?.name || 'unknown';
          const srcOrigin = (rule as any).site?.origin || '';
          const srcQuality = (rule as any).quality?.score ?? 0;
          const srcWaf = !!(rule as any).search?.requires_waf_bypass;
          const srcBrowser = !!(rule as any).search?.requires_browser;
          // Runtime brand dedup: skip if this brand already has enough successes
          if (brandTracker.shouldSkip(rule)) {
            debugReport.recordSource(srcName, srcOrigin, 'skipped', 0, 0, {
              requiresWaf: srcWaf, requiresBrowser: srcBrowser, qualityScore: srcQuality,
            });
            session.doneCount++;
            session._notify?.();
            continue;
          }
          const srcHost = srcOrigin ? (() => { try { return new URL(srcOrigin).hostname; } catch { return srcName; } })() : srcName;
          const t0 = Date.now();
          try {
            const items = await searchSource(rule as any, term);
            const elapsed = Date.now() - t0;
            trackSourceResult(srcHost, items.length > 0, items.length, elapsed);
            // Record to debug report — full per-item breakdown
            const itemLogs: ResultItemLog[] = items.map(r => ({
              title: r.title,
              hash: (r.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 16),
              size: r.size || '',
              relevance: computeRelevance(r.title, term),
            }));
            debugReport.recordSource(
              srcName, srcOrigin,
              items.length > 0 ? 'ok' : 'empty',
              items.length, elapsed,
              {
                sampleTitles: items.slice(0, 3).map(r => r.title),
                sampleHashes: items.slice(0, 3).map(r => (r.magnet.match(/btih:([a-fA-F0-9]+)/i)?.[1] || '').slice(0, 12)),
                items: itemLogs,
                requiresWaf: srcWaf,
                requiresBrowser: srcBrowser,
                qualityScore: srcQuality,
              },
            );
            if (items.length > 0) brandTracker.recordSuccess(rule);
            if (items.length > 0 && !session.abortRef.current) {
              const mapped: SearchResult[] = items
                .filter((r) => !isBlockedContent(r.title))
                .map((r) => ({
                  title: r.title,
                  magnet: r.magnet,
                  size: r.size,
                  date: r.date,
                  source: r.source,
                  site_name: r.site_name,
                }));
              session.rawResults.push(...mapped);
              session._notify?.();
            }
          } catch (err: any) {
            const elapsed = Date.now() - t0;
            const msg = err?.message || 'unknown';
            const isBlacklisted = msg === '__blacklisted__';
            trackSourceResult(srcHost, false, 0, elapsed, msg);
            debugReport.recordSource(
              srcName, srcOrigin,
              isBlacklisted ? 'skipped' : elapsed > 9000 ? 'timeout' : 'error',
              0, elapsed,
              {
                error: isBlacklisted ? 'blacklisted (session)' : msg,
                requiresWaf: srcWaf,
                requiresBrowser: srcBrowser,
                qualityScore: srcQuality,
              },
            );
          } finally {
            brandTracker.recordDone(rule);
            session.doneCount++;
            session._notify?.();
          }
        }
      };
      await Promise.allSettled(
        Array.from({ length: Math.min(CONCURRENCY, allSources.length) }, () => runNext()),
      );

      session.searching = false;
      trackSearch(term, session.rawResults.length);
      debugReport.finish();
      session._notify?.();
    },
    [sources, syncFromSession],
  );

  // ── On mount: restore existing session or start new search ──
  useEffect(() => {
    if (!q) return;
    if (_session && _session.query === q) {
      // Same query — restore from session (search may still be running)
      syncFromSession();
    } else {
      // New query — start fresh search
      doSearch(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

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
    const cmp = (a: ResultCardModel, b: ResultCardModel) => {
      let va: number, vb: number;
      if (sortKey === 'size') {
        va = parseSizeBytes(a.sizeLabel);
        vb = parseSizeBytes(b.sizeLabel);
      } else {
        va = parseDate(a.dateLabel);
        vb = parseDate(b.dateLabel);
      }
      return sortDir === 'desc' ? vb - va : va - vb;
    };
    // Split into high/low relevance, sort each group independently
    const high = arr.filter(r => r.relevance >= RELEVANCE_THRESHOLD);
    const low = arr.filter(r => r.relevance < RELEVANCE_THRESHOLD);
    high.sort(cmp);
    low.sort(cmp);
    if (high.length > 0 && low.length > 0) {
      const out: ListItem[] = [...high];
      out.push({ _divider: true, id: '__relevance_divider__' });
      out.push(...low);
      return out;
    }
    return [...high, ...low];
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
      trackCopy();
      Vibration.vibrate(Platform.OS === 'android' ? 30 : 10);
      setCopiedId(model.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      Alert.alert(t.copyFailed);
    }
  };

  const handleOpen = (magnet: string) => {
    trackOpen();
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
          <View style={styles.relevancePill}>
            <Text style={styles.relevanceLabel}>{t.lowRelevanceHint}</Text>
          </View>
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
        <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow, borderColor: colors.border }]}>
          <View style={styles.cardRow}>
            <LinearGradient
              colors={theme.tileColors as [string, string]}
              style={styles.iconTile}
            >
              <Ionicons name={theme.iconName as any} size={22} color={theme.iconColor} />
            </LinearGradient>
            <View style={styles.cardContent}>
              <View style={styles.titleRow}>
                <Text style={[styles.cardTitle, { flex: 1, color: colors.text }]} numberOfLines={3} ellipsizeMode="tail">{item.title}</Text>
              </View>
              <View style={styles.cardMetaRow}>
                <Text style={[styles.cardMeta, { color: colors.textTertiary }]}>
                  {item.kindLabel}
                  {item.sizeLabel ? ` · ${item.sizeLabel}` : ''}
                  {item.fileCountLabel ? ` · ${item.fileCountLabel}` : ''}
                  {item.dateLabel ? ` · ${item.dateLabel}` : ''}
                </Text>
              </View>
            </View>
          </View>

          {/* Tags row */}
          {item.tags.length > 0 && (
            <View style={styles.tagsRow}>
              {item.tags.map((tag) => (
                <View key={tag} style={[styles.tagPill, { backgroundColor: colors.tagBg }]}>
                  <Text style={[styles.tagText, { color: colors.tagText }]}>{tag}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Action buttons row */}
          {hasMagnet && (
            <View style={styles.btnRow}>
              <TouchableOpacity
                onPress={() => handleToggleFav(item)}
                activeOpacity={0.8}
                style={[styles.favBtn, { borderColor: isFav ? '#6366f1' : colors.border, backgroundColor: colors.card }]}
              >
                <Ionicons name={isFav ? 'bookmark' : 'bookmark-outline'} size={14} color={isFav ? '#6366f1' : colors.textTertiary} />
              </TouchableOpacity>
              <View style={{ flex: 1 }} />
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
            </View>
          )}
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
        <View style={[styles.topSearch, { backgroundColor: colors.inputBg, shadowColor: colors.shadow }]}>
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
            <TouchableOpacity
              style={[styles.cancelBtn, { backgroundColor: colors.chipBg }]}
              onPress={() => { if (_session) _session.abortRef.current = true; setSearching(false); }}
            >
              <Text style={[styles.cancelBtnText, { color: colors.textSecondary }]}>{lang === 'zh' ? '停止' : 'Stop'}</Text>
            </TouchableOpacity>
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
        ) : q ? (
          <View style={styles.emptyState}>
            <Text style={{ fontSize: 48 }}>🔍</Text>
            <Text style={styles.emptyText}>{t.noResultsHint}</Text>
            <Text style={[styles.emptySubtext, { color: colors.textTertiary }]}>{t.noResultsSuggestion}</Text>
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
      {searching && results.length === 0 ? (
        <SkeletonList cardBg={colors.card} shimmerBg={colors.border} tileBg={colors.chipBg} />
      ) : (
        <FlatList<ListItem>
          data={sortedResults}
          renderItem={renderListItem}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 40 }}
          showsVerticalScrollIndicator={false}
          refreshing={false}
          onRefresh={() => doSearch(query)}
          removeClippedSubviews={true}
          maxToRenderPerBatch={8}
          windowSize={7}
          initialNumToRender={6}
          updateCellsBatchingPeriod={100}
        />
      )}

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
    borderWidth: 1,
    borderColor: 'transparent',
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
    fontSize: 13,
    fontWeight: '600',
    color: '#262b35',
    lineHeight: 18,
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
  btnRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 10,
    gap: 6,
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
  emptySubtext: {
    fontSize: 13,
    color: '#b0b8c8',
    marginTop: -4,
  },
  emptyLink: {
    fontSize: 14,
    color: '#4285F4',
    fontWeight: '600',
  },
  relevanceDivider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 16,
    paddingHorizontal: 4,
    gap: 10,
  },
  relevanceLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#e8a84c',
    opacity: 0.4,
  },
  favBtn: {
    width: 30,
    height: 26,
    borderRadius: 6,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  relevancePill: {
    backgroundColor: '#FFF3E0',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#FFCC80',
  },
  relevanceLabel: {
    fontSize: 12,
    color: '#E65100',
    fontWeight: '600',
  },
  cancelBtn: {
    marginLeft: 12,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
    backgroundColor: '#f4f2ef',
  },
  cancelBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#9aa3b4',
  },
});
