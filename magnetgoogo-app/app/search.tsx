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
  AppState,
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
  computeRelevance,
  getResultStableId,
  parseSizeBytes,
} from '../src/core/types';
import { extractInfoHash } from '../src/core/dedup';
import {
  createSearchResultAccumulatorState,
  mergePendingSearchResults,
  rebuildSearchCardModels,
  type SearchResultAccumulatorState,
} from '../src/core/searchResultAccumulator';
import { addHistory } from '../src/core/searchHistory';
import { addFavorite, removeFavorite, getFavorites, type FavoriteItem } from '../src/core/favorites';
import { VerifyManager, type VerifyRequest } from '../src/core/VerifyManager';
import VerifyWebView from '../src/components/VerifyWebView';
import FeedbackFAB from '../src/components/FeedbackFAB';
import { useTheme } from '../src/core/ThemeContext';
import { trackCopy, trackOpen, trackSearchCompleted, trackSearchSubmitted } from '../src/core/analytics';
import { notifySearchCompleted } from '../src/core/searchNotifications';
import { loadSourceStats } from '../src/core/sourceStats';
import { startSearchKeepAlive, stopSearchKeepAlive, handoffSearchToBackground } from '../src/core/searchKeepAlive';
import {
  claimBackgroundSearch,
  clearBackgroundSearchState,
  getBackgroundSearchSnapshot,
  subscribeBackgroundSearch,
} from '../src/core/backgroundSearch';
import {
  BACKGROUND_SEARCH_POLL_INTERVAL_MS,
  BACKGROUND_SEARCH_TASK_TIMEOUT_MS,
  backgroundSnapshotMatches,
  isBackgroundSearchTerminal,
  mergeBackgroundSearchResults,
  type BackgroundSearchSnapshot,
} from '../src/core/backgroundSearchProtocol';
import { runSearchTask } from '../src/core/searchRunner';
import { normalizeSearchTerm } from '../src/core/searchTerm';
import { getSearchProgressStage, HIGH_RELEVANCE_THRESHOLD } from '../src/core/searchQuality';
import { splitSearchingStatus } from '../src/core/i18n';
import { createSearchRunId, normalizeSearchRunId, routeSearchMatchesSession } from '../src/core/searchRoute';

// Search throttle (3s cooldown)
const SEARCH_COOLDOWN_MS = 3000;
let _lastSearchTime = 0;

// Module-level search session (survives component unmount)
// When the user navigates away, the search promises keep running and
// updating this cache.  When the component re-mounts, it restores
// state from here instead of re-searching.
interface _Session extends SearchResultAccumulatorState {
  generation: number;
  query: string;
  routeRunId?: string;
  searchId?: string;
  rawResults: SearchResult[];
  searching: boolean;
  startedAt: number;
  sourceCount: number;
  doneCount: number;
  completedPoolCount: number;
  totalPoolCount: number;
  abortRef: { current: boolean };
  // Mounted component's setState callbacks; null when unmounted.
  _notify: (() => void) | null;
  _keepAliveToken?: number;
}
let _session: _Session | null = null;
let _searchGeneration = 0;

/** Ids that already played enter animation (stable across reorders). */
const _animatedCardIds = new Set<string>();

// Skeleton card component
function SkeletonCard({ cardBg, shimmerBg, tileBg }: { cardBg: string; shimmerBg: string; tileBg: string }) {
  const opacity = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ]),
    );
    anim.start();
    return () => anim.stop();
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

// Bouncing dots component
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
    const a1 = bounce(d1, 0);
    const a2 = bounce(d2, 150);
    const a3 = bounce(d3, 300);
    a1.start();
    a2.start();
    a3.start();
    return () => {
      a1.stop();
      a2.stop();
      a3.stop();
    };
  }, [d1, d2, d3]);

  const dot = (v: Animated.Value) => (
    <Animated.Text style={[s.dotText, { transform: [{ translateY: v }] }]}>.</Animated.Text>
  );
  const s = StyleSheet.create({ dotText: { fontSize: 18, fontWeight: '800', color: '#4285F4', lineHeight: 18 } });
  return <View style={{ flexDirection: 'row', flexShrink: 0 }}>{dot(d1)}{dot(d2)}{dot(d3)}</View>;
}

function SearchingStatus({ text }: { text: string }) {
  const { before, after } = splitSearchingStatus(text);
  return (
    <View style={styles.searchingStatusCopy}>
      <Text style={[styles.statusText, styles.searchingStatusBefore]} numberOfLines={1}>
        {before}
      </Text>
      <BouncingDots />
      {!!after && (
        <Text style={[styles.statusText, styles.searchingStatusAfter]} numberOfLines={1}>
          {after}
        </Text>
      )}
    </View>
  );
}

// Animated card wrapper — animate by stable id once, never by list index (prevents re-fly on re-rank).
const MAX_ANIMATED_CARDS = 8;
function AnimatedCard({
  id,
  index,
  children,
}: {
  id: string;
  index: number;
  children: React.ReactNode;
}) {
  const already = _animatedCardIds.has(id);
  // Only the first MAX ids ever get enter animation; later ids appear static.
  const canEnter = !already && _animatedCardIds.size < MAX_ANIMATED_CARDS;
  const opacity = useRef(new Animated.Value(canEnter ? 0 : 1)).current;
  const translateY = useRef(new Animated.Value(canEnter ? 16 : 0)).current;
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    _animatedCardIds.add(id);
    if (!canEnter) return;
    const delay = Math.min(index * 45, 360);
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 240, delay, useNativeDriver: true }),
      Animated.timing(translateY, {
        toValue: 0,
        duration: 240,
        delay,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }),
    ]).start();
  }, [id, index, canEnter, opacity, translateY]);

  if (!canEnter) return <View>{children}</View>;
  return <Animated.View style={{ opacity, transform: [{ translateY }] }}>{children}</Animated.View>;
}

// Sort types
type SortKey = 'relevance' | 'size' | 'date';
type SortDir = 'desc' | 'asc';
type ListItem = ResultCardModel | { _divider: true; id: string };

function parseDate(label: string): number {
  if (!label) return 0;
  const d = new Date(label);
  return isNaN(d.getTime()) ? 0 : d.getTime();
}

// Main screen
export default function SearchScreen() {
  const { q, benchmark, cold, run } = useLocalSearchParams<{
    q: string;
    benchmark?: string;
    cold?: string;
    run?: string;
  }>();
  const exhaustiveBenchmark = benchmark === '1';
  const coldStartTest = cold === '1';
  const [query, setQuery] = useState(() => normalizeSearchTerm(q));
  const [results, setResults] = useState<ResultCardModel[]>([]);
  const [searching, setSearching] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [, setSourceCount] = useState(0);
  const [, setDoneCount] = useState(0);
  const [completedPoolCount, setCompletedPoolCount] = useState(0);
  const [totalPoolCount, setTotalPoolCount] = useState(0);
  const [progressClock, setProgressClock] = useState(() => Date.now());
  const [sortKey, setSortKey] = useState<SortKey>('relevance');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [favSet, setFavSet] = useState<Set<string>>(new Set());
  const { sources, meta: sourceMeta } = useSources();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { lang, t } = useLang();
  const { colors } = useTheme();

  // Sync with module-level session on mount / unmount.
  const syncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backgroundHandoffRef = useRef<{ query: string; token: number } | null>(null);
  const backgroundPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const backgroundPollStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backgroundPollBusyRef = useRef(false);
  /** While user is scrolling, defer list data updates to avoid jump/jank. */
  const isScrollingRef = useRef(false);
  const pendingListSyncRef = useRef(false);
  const scrollEndTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const rebuildCardModels = useCallback((s: _Session, forceFullSort: boolean) => {
    rebuildSearchCardModels(s, {
      searching: s.searching,
      forceFullSort,
      query: s.query,
      extractInfoHash,
      getStableId: getResultStableId,
      buildCard: (result, index) => toResultCardModel(result, index, s.query, t),
    });
  }, [t]);

  const syncFromSession = useCallback((opts?: { forceList?: boolean }) => {
    if (!_session) return;

    const s = _session;
    let cardCacheInvalidated = false;
    if ((s as any)._cachedLang !== lang) {
      (s as any)._cachedLang = lang;
      s._cardModelCache.clear();
      cardCacheInvalidated = true;
    }
    let listChanged = mergePendingSearchResults(s, s.rawResults, s.query, {
      extractInfoHash,
      getStableId: getResultStableId,
      computeRelevance,
      parseSizeBytes,
    });

    // Full rank only when search finished (or user stopped). Mid-search stays first-seen order.
    const forceFullSort = !s.searching && !s._finalSorted;
    if (listChanged || forceFullSort || cardCacheInvalidated) {
      rebuildCardModels(s, forceFullSort);
      listChanged = true;
    }

    // Progress chips update always (fixed-height status row — no layout thrash)
    setSearching(s.searching);
    setSourceCount(s.sourceCount);
    setDoneCount(s.doneCount);
    setCompletedPoolCount(s.completedPoolCount);
    setTotalPoolCount(s.totalPoolCount);

    // Defer list data while scrolling to keep scroll position stable
    if (listChanged || opts?.forceList) {
      if (isScrollingRef.current && !opts?.forceList) {
        pendingListSyncRef.current = true;
      } else {
        pendingListSyncRef.current = false;
        // New array ref so FlatList sees an update; order is stable while searching
        setResults(s._cardModels.slice());
      }
    }
  }, [t, lang, rebuildCardModels]);

  // Debounced version: batch rapid _notify calls (every source completion)
  // 700ms while searching reduces thrash vs 500ms; still feels live.
  const debouncedSync = useCallback(() => {
    if (syncTimerRef.current) return;
    const delay = _session?.searching ? 700 : 400;
    syncTimerRef.current = setTimeout(() => {
      syncTimerRef.current = null;
      syncFromSession();
    }, delay);
  }, [syncFromSession]);

  const onScrollBeginDrag = useCallback(() => {
    isScrollingRef.current = true;
    if (scrollEndTimerRef.current) {
      clearTimeout(scrollEndTimerRef.current);
      scrollEndTimerRef.current = null;
    }
  }, []);

  const onScrollEnd = useCallback(() => {
    if (scrollEndTimerRef.current) clearTimeout(scrollEndTimerRef.current);
    // Coalesce fling end
    scrollEndTimerRef.current = setTimeout(() => {
      scrollEndTimerRef.current = null;
      isScrollingRef.current = false;
      if (pendingListSyncRef.current) {
        pendingListSyncRef.current = false;
        syncFromSession({ forceList: true });
      }
    }, 120);
  }, [syncFromSession]);

  useEffect(() => {
    // Subscribe: session calls this when async results arrive
    if (_session) _session._notify = debouncedSync;
    return () => {
      // Unsubscribe on unmount; search keeps running in background.
      if (_session) _session._notify = null;
      if (syncTimerRef.current) { clearTimeout(syncTimerRef.current); syncTimerRef.current = null; }
    };
  }, [debouncedSync]);

  useEffect(() => {
    getFavorites().then((favs) => setFavSet(new Set(favs.map((f) => f.magnet))));
  }, []);

  useEffect(() => {
    if (!searching) return undefined;
    setProgressClock(Date.now());
    const timer = setInterval(() => setProgressClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [searching]);

  // Legado-style verification: register listener for challenge events.
  const [verifyRequest, setVerifyRequest] = useState<VerifyRequest | null>(null);
  useEffect(() => {
    VerifyManager.setListener((req) => setVerifyRequest(req));
    return () => VerifyManager.setListener(null);
  }, []);

  const stopBackgroundObservation = useCallback(() => {
    if (backgroundPollRef.current) {
      clearInterval(backgroundPollRef.current);
      backgroundPollRef.current = null;
    }
    if (backgroundPollStopRef.current) {
      clearTimeout(backgroundPollStopRef.current);
      backgroundPollStopRef.current = null;
    }
    backgroundPollBusyRef.current = false;
  }, []);

  const handoffActiveSessionToBackground = useCallback(async (
    session: _Session | null = _session,
  ): Promise<boolean> => {
    if (
      !session ||
      _session !== session ||
      !session.searching ||
      backgroundHandoffRef.current ||
      !session.query.trim()
    ) {
      return false;
    }

    stopBackgroundObservation();
    const token = session._keepAliveToken || 0;
    if (!token) return false;

    backgroundHandoffRef.current = { query: session.query, token };
    const handoffSnapshot: BackgroundSearchSnapshot = {
      query: session.query,
      token,
      searchId: session.searchId,
      updatedAt: new Date().toISOString(),
      startedAt: session.startedAt,
      sourceCount: session.sourceCount || sources.length,
      doneCount: session.doneCount,
      completedPoolCount: session.completedPoolCount,
      totalPoolCount: session.totalPoolCount,
      searching: true,
      completed: false,
      resultCount: session.rawResults.length,
      results: session.rawResults,
    };

    try {
      await claimBackgroundSearch(handoffSnapshot);
      const ok = await handoffSearchToBackground(session.query, token, session.searchId || '');
      if (!ok || backgroundHandoffRef.current?.token !== token) {
        backgroundHandoffRef.current = null;
        await clearBackgroundSearchState(session.query, token);
        return false;
      }
      if (_session === session) session.abortRef.current = true;
      return true;
    } catch (error) {
      console.warn('[Search] background handoff failed', {
        search_id: session.searchId || '',
        rule_id: '',
        stage: 'background_handoff',
        error_code: error instanceof Error ? error.message : String(error),
      });
      if (backgroundHandoffRef.current?.token === token) {
        backgroundHandoffRef.current = null;
      }
      await clearBackgroundSearchState(session.query, token).catch(() => {});
      return false;
    }
  }, [sources.length, stopBackgroundObservation]);

  const applyBackgroundSnapshot = useCallback((snapshot: BackgroundSearchSnapshot): boolean => {
    const expectedQuery = backgroundHandoffRef.current?.query || _session?.query || '';
    const expectedToken = backgroundHandoffRef.current?.token || _session?._keepAliveToken || 0;
    if (!expectedQuery || !expectedToken || !backgroundSnapshotMatches(snapshot, expectedQuery, expectedToken)) {
      return false;
    }

    const terminal = isBackgroundSearchTerminal(snapshot);
    const existing = _session?.query === snapshot.query ? _session : null;
    const mergedResults = mergeBackgroundSearchResults(
      existing?.rawResults || [],
      snapshot.results,
      getResultStableId,
    );

    if (existing && !terminal) {
      existing.rawResults = mergedResults;
      existing.searching = true;
      existing.searchId = snapshot.searchId || existing.searchId;
      existing.startedAt = snapshot.startedAt || existing.startedAt;
      existing.sourceCount = snapshot.sourceCount || existing.sourceCount || sources.length;
      existing.doneCount = snapshot.doneCount;
      existing.completedPoolCount = snapshot.completedPoolCount;
      existing.totalPoolCount = snapshot.totalPoolCount;
      existing._keepAliveToken = snapshot.token || existing._keepAliveToken;
      existing.abortRef.current = true;
      existing._notify = debouncedSync;
    } else {
      _session = {
        generation: existing?.generation || ++_searchGeneration,
        query: snapshot.query,
        routeRunId: existing?.routeRunId || normalizeSearchRunId(run),
        searchId: snapshot.searchId || existing?.searchId,
        rawResults: mergedResults,
        searching: !terminal,
        startedAt: snapshot.startedAt || existing?.startedAt || Date.now(),
        sourceCount: snapshot.sourceCount || existing?.sourceCount || sources.length,
        doneCount: snapshot.doneCount || (terminal ? snapshot.sourceCount : 0),
        completedPoolCount: snapshot.completedPoolCount || existing?.completedPoolCount || 0,
        totalPoolCount: snapshot.totalPoolCount || existing?.totalPoolCount || 0,
        abortRef: { current: true },
        _notify: debouncedSync,
        _keepAliveToken: snapshot.token || existing?._keepAliveToken,
        ...createSearchResultAccumulatorState(),
      };
      _animatedCardIds.clear();
    }

    setQuery(snapshot.query);
    syncFromSession({ forceList: terminal });
    if (terminal) backgroundHandoffRef.current = null;
    return true;
  }, [debouncedSync, run, sources.length, syncFromSession]);

  const pollBackgroundSnapshot = useCallback(async () => {
    if (backgroundPollBusyRef.current) return;
    backgroundPollBusyRef.current = true;
    try {
      const snapshot = await getBackgroundSearchSnapshot();
      if (!snapshot) {
        if (!backgroundHandoffRef.current) stopBackgroundObservation();
        return;
      }
      const applied = applyBackgroundSnapshot(snapshot);
      if (applied && isBackgroundSearchTerminal(snapshot)) {
        stopBackgroundObservation();
        await clearBackgroundSearchState(snapshot.query, snapshot.token);
      }
    } catch (error) {
      console.warn('[Search] background poll failed', {
        search_id: _session?.searchId || '',
        rule_id: '',
        stage: 'background_poll',
        error_code: error instanceof Error ? error.message : String(error),
      });
    } finally {
      backgroundPollBusyRef.current = false;
    }
  }, [applyBackgroundSnapshot, stopBackgroundObservation]);

  const resumeBackgroundObservation = useCallback(() => {
    stopBackgroundObservation();
    void pollBackgroundSnapshot();
    backgroundPollRef.current = setInterval(
      () => void pollBackgroundSnapshot(),
      BACKGROUND_SEARCH_POLL_INTERVAL_MS,
    );
    backgroundPollStopRef.current = setTimeout(
      stopBackgroundObservation,
      BACKGROUND_SEARCH_TASK_TIMEOUT_MS,
    );
  }, [pollBackgroundSnapshot, stopBackgroundObservation]);

  useEffect(() => subscribeBackgroundSearch((snapshot) => {
    if (AppState.currentState !== 'active') return;
    const applied = applyBackgroundSnapshot(snapshot);
    if (applied && isBackgroundSearchTerminal(snapshot)) {
      stopBackgroundObservation();
      void clearBackgroundSearchState(snapshot.query, snapshot.token);
    }
  }), [applyBackgroundSnapshot, stopBackgroundObservation]);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'background') {
        void handoffActiveSessionToBackground();
        return;
      }
      if (next === 'active') resumeBackgroundObservation();
    });

    if (AppState.currentState === 'active') resumeBackgroundObservation();
    return () => {
      sub.remove();
      stopBackgroundObservation();
    };
  }, [handoffActiveSessionToBackground, resumeBackgroundObservation, stopBackgroundObservation]);

  const doSearch = useCallback(
    async (term: string, routeRunId = '') => {
      const normalizedTerm = normalizeSearchTerm(term);
      if (!normalizedTerm || sources.length === 0) return;

      // Search throttle: 3s cooldown.
      const now = Date.now();
      const elapsed = now - _lastSearchTime;
      if (elapsed < SEARCH_COOLDOWN_MS) {
        const wait = Math.ceil((SEARCH_COOLDOWN_MS - elapsed) / 1000);
        Alert.alert('', lang === 'zh' ? `搜索太频繁，请 ${wait} 秒后再试` : `Please wait ${wait}s before searching again`);
        return;
      }
      _lastSearchTime = now;

      // Invalidate any older foreground/headless search before starting a new owner.
      const generation = ++_searchGeneration;
      const previousSession = _session;
      const previousHandoff = backgroundHandoffRef.current;
      const previousToken = previousHandoff?.token || previousSession?._keepAliveToken || 0;
      const previousQuery = previousHandoff?.query || previousSession?.query || '';
      if (previousSession) previousSession.abortRef.current = true;
      backgroundHandoffRef.current = null;
      setQuery(normalizedTerm);

      await Promise.allSettled([
        exhaustiveBenchmark ? Promise.resolve() : addHistory(normalizedTerm),
        loadSourceStats(),
        previousToken && previousQuery
          ? clearBackgroundSearchState(previousQuery, previousToken)
          : Promise.resolve(false),
        previousToken ? stopSearchKeepAlive(previousToken) : Promise.resolve(),
      ]);
      if (generation !== _searchGeneration) return;

      const keepAliveToken = await startSearchKeepAlive(normalizedTerm);
      if (generation !== _searchGeneration) {
        await stopSearchKeepAlive(keepAliveToken).catch(() => {});
        return;
      }

      // Create new session.
      const session: _Session = {
        generation,
        query: normalizedTerm,
        routeRunId: normalizeSearchRunId(routeRunId),
        searchId: undefined,
        rawResults: [],
        searching: true,
        startedAt: Date.now(),
        sourceCount: 0,
        doneCount: 0,
        completedPoolCount: 0,
        totalPoolCount: 0,
        abortRef: { current: false },
        _notify: debouncedSync,
        _keepAliveToken: keepAliveToken,
        ...createSearchResultAccumulatorState(),
      };
      _session = session;
      _animatedCardIds.clear();

      setSearching(true);
      setResults([]);
      setSortKey('relevance');
      setSortDir('desc');
      setDoneCount(0);
      setCompletedPoolCount(0);
      setTotalPoolCount(0);
      setProgressClock(Date.now());

      // The app may have reached background before the async session was created.
      // Do not rely exclusively on a one-shot AppState event in that race.
      if (AppState.currentState !== 'active') {
        const handedOff = await handoffActiveSessionToBackground(session);
        if (handedOff) return;
      }

      try {
        if (!exhaustiveBenchmark) {
          try {
            session.searchId = await trackSearchSubmitted({
              term: normalizedTerm,
              sourceCount: sources.length,
              backgroundCapable: true,
            });
          } catch {
            // Analytics must never block the actual search.
          }
        }

        if (_session !== session || generation !== _searchGeneration) {
          session.abortRef.current = true;
          return;
        }

        const result = await runSearchTask({
          term: normalizedTerm,
          sources,
          shouldAbort: () => session.abortRef.current || generation !== _searchGeneration,
          onItems: (items) => {
            if (_session !== session || generation !== _searchGeneration) return;
            session.rawResults.push(...items);
            session._notify?.();
          },
          onProgress: (done, total, progress) => {
            if (_session !== session || generation !== _searchGeneration) return;
            session.doneCount = done;
            session.sourceCount = total;
            session.completedPoolCount = progress.completedPoolCount;
            session.totalPoolCount = progress.totalPoolCount;
            session._notify?.();
          },
          exhaustive: exhaustiveBenchmark,
          ignoreLocalLearning: coldStartTest,
          sourceMeta,
        });

        if (_session !== session || generation !== _searchGeneration) return;
        const handoffState = backgroundHandoffRef.current as { query: string; token: number } | null;
        const handedOff = handoffState?.token === keepAliveToken;
        if (!handedOff) {
          session.searching = false;
          session.doneCount = result.doneCount;
          session.sourceCount = result.sourceCount;
          session.completedPoolCount = result.completedPoolCount;
          session.totalPoolCount = result.totalPoolCount;
          session._notify?.();
          if (session.searchId) {
            trackSearchCompleted({
              searchId: session.searchId,
              term: normalizedTerm,
              sourceCount: result.sourceCount,
              doneCount: result.doneCount,
              resultCount: session.rawResults.length,
              aborted: result.aborted,
              background: false,
              durationMs: result.analytics.durationMs,
              timeToFirstResultMs: result.analytics.timeToFirstResultMs,
              sourceRollup: result.analytics.sourceRollup,
            }).catch(() => {});
          }
          if (!result.aborted && !exhaustiveBenchmark) {
            notifySearchCompleted({
              query: normalizedTerm,
              resultCount: session.rawResults.length,
              sourceCount: result.sourceCount,
              elapsedMs: result.report.totalDurationMs || Date.now() - session.startedAt,
            }).catch(() => {});
          }
        }
      } catch (error) {
        if (_session === session && generation === _searchGeneration) {
          session.searching = false;
          session.sourceCount = session.sourceCount || sources.length;
          session._notify?.();
          console.warn('[Search] unexpected failure', error);
        }
      } finally {
        const handoffState = backgroundHandoffRef.current as { query: string; token: number } | null;
        const handedOff = handoffState?.token === keepAliveToken;
        if (!handedOff) {
          stopSearchKeepAlive(keepAliveToken).catch(() => {});
        }
      }
    },
    [sources, sourceMeta, lang, debouncedSync, handoffActiveSessionToBackground, exhaustiveBenchmark, coldStartTest],
  );

  // Route launches carry a run id. Re-entering the same history/movie query with
  // a new run id must execute a new live search; remounting the same route run
  // restores the matching session instead of duplicating work.
  useEffect(() => {
    const routeQuery = normalizeSearchTerm(q);
    const routeRunId = normalizeSearchRunId(run);
    if (!routeQuery || sources.length === 0) return;
    if (!routeRunId) {
      router.setParams({ q: routeQuery, run: createSearchRunId() });
      return;
    }
    if (routeSearchMatchesSession(routeQuery, routeRunId, _session?.query, _session?.routeRunId)) {
      setQuery(routeQuery);
      syncFromSession();
    } else {
      void doSearch(routeQuery, routeRunId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, run, benchmark, cold, sources.length]);

  const submitSearch = useCallback((term: string) => {
    const normalizedTerm = normalizeSearchTerm(term);
    if (!normalizedTerm) return;
    router.setParams({ q: normalizedTerm, run: createSearchRunId() });
  }, [router]);

  // Relevance is the default and primary ordering. The session keeps result
  // identity stable, while this render-time sort lets clearly better matches
  // rise as the full content-pool search continues.
  const sortedResults = React.useMemo((): ListItem[] => {
    const arr = [...results];
    if (sortKey === 'relevance') {
      arr.sort((a, b) => b.relevance - a.relevance);
      const dividerIdx = arr.findIndex((r) => r.relevance < HIGH_RELEVANCE_THRESHOLD);
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
        va = a.sizeBytes;
        vb = b.sizeBytes;
      } else {
        va = parseDate(a.dateLabel);
        vb = parseDate(b.dateLabel);
      }
      return sortDir === 'desc' ? vb - va : va - vb;
    };
    const high = arr.filter((r) => r.relevance >= HIGH_RELEVANCE_THRESHOLD);
    const low = arr.filter((r) => r.relevance < HIGH_RELEVANCE_THRESHOLD);
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
      setSortKey(key);
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

  // Handlers.
  const handleCopy = useCallback(async (model: ResultCardModel) => {
    try {
      await Clipboard.setStringAsync(model.magnet);
      trackCopy({ searchId: _session?.searchId, surface: 'search', action: 'single' });
      Vibration.vibrate(Platform.OS === 'android' ? 30 : 10);
      setCopiedId(model.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      Alert.alert(t.copyFailed);
    }
  }, [t]);

  const handleOpen = useCallback((magnet: string) => {
    trackOpen({ searchId: _session?.searchId, surface: 'search', action: 'single' });
    Linking.openURL(magnet).catch(() =>
      Alert.alert(t.cannotOpen, t.cannotOpenMsg),
    );
  }, [t]);

  const handleToggleFav = useCallback(async (item: ResultCardModel) => {
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
  }, [favSet]);

  // Card / divider renderer.
  const renderListItem = useCallback(({ item, index }: { item: ListItem; index: number }) => {
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
      <AnimatedCard id={item.id} index={index}>
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
  }, [copiedId, favSet, colors, handleCopy, handleOpen, handleToggleFav, t]);

  // Sort bar helper.
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

  const progressStage = getSearchProgressStage(
    Math.max(0, progressClock - (_session?.startedAt || progressClock)),
    completedPoolCount,
    totalPoolCount,
  );
  const searchCompleted = totalPoolCount > 0 && completedPoolCount >= totalPoolCount;

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
            onSubmitEditing={() => submitSearch(query)}
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

      {/* Status — fixed minHeight so progress text ticks don't shove the list */}
      <View style={styles.statusRow}>
        {searching ? (
          <View style={styles.statusInner}>
            <SearchingStatus text={t.searchingStatus(progressStage, results.length)} />
            <TouchableOpacity
              style={[styles.cancelBtn, { backgroundColor: colors.chipBg }]}
              onPress={() => {
                if (_session) {
                  _session.abortRef.current = true;
                  _session.searching = false;
                }
                setSearching(false);
                // Rebuild once on stop; list updates still honor scroll deferral.
                syncFromSession();
              }}
            >
              <Text style={[styles.cancelBtnText, { color: colors.textSecondary }]}>{t.stopSearch}</Text>
            </TouchableOpacity>
          </View>
        ) : results.length > 0 && searchCompleted ? (
          <Text style={styles.statusText} numberOfLines={1}>
            {t.searchDoneStatus(results.length)}
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
      <FlatList<ListItem>
        data={sortedResults}
        renderItem={renderListItem}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          searching ? (
            <SkeletonList cardBg={colors.card} shimmerBg={colors.border} tileBg={colors.chipBg} />
          ) : null
        }
        onScrollBeginDrag={onScrollBeginDrag}
        onScrollEndDrag={onScrollEnd}
        onMomentumScrollBegin={onScrollBeginDrag}
        onMomentumScrollEnd={onScrollEnd}
        scrollEventThrottle={32}
        removeClippedSubviews={Platform.OS === 'android'}
        maxToRenderPerBatch={6}
        windowSize={5}
        initialNumToRender={8}
        updateCellsBatchingPeriod={80}
        // Avoid blank flashes when data identity churns mid-search
        maintainVisibleContentPosition={
          Platform.OS === 'ios'
            ? { minIndexForVisible: 0, autoscrollToTopThreshold: 12 }
            : undefined
        }
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
    minHeight: 36,
    justifyContent: 'center',
  },
  statusInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    minHeight: 28,
  },
  statusText: {
    fontSize: 13,
    color: '#4285F4',
    fontWeight: '600',
  },
  searchingStatusCopy: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  searchingStatusBefore: {
    flexShrink: 1,
    minWidth: 0,
  },
  searchingStatusAfter: {
    flexShrink: 0,
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
    marginLeft: 10,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
    backgroundColor: '#f4f2ef',
    flexShrink: 0,
  },
  cancelBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#9aa3b4',
  },
});
