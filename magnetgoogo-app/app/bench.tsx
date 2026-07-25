import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system';
import { useSources } from '../src/core/SourceContext';
import { useTheme } from '../src/core/ThemeContext';
import { useLang } from '../src/core/LangContext';
import {
  runBenchTest,
  exportBenchReport,
  type BenchConfig,
  type BenchSourceResult,
  type BenchSession,
} from '../src/core/sourceBenchRunner';

// ── Status icon/color map ────────────────────────────────────────────
const STATUS_META: Record<string, { icon: string; color: string }> = {
  pending:       { icon: '○', color: '#9ca3af' },
  running:       { icon: '⟳', color: '#60a5fa' },
  ok:            { icon: '✅', color: '#22c55e' },
  partial:       { icon: '🟡', color: '#eab308' },
  empty:         { icon: '⭕', color: '#f59e0b' },
  error:         { icon: '❌', color: '#ef4444' },
  timeout:       { icon: '⏱', color: '#f97316' },
  skipped_webview:{ icon: '🌐', color: '#a78bfa' },
  hallucinating: { icon: '👻', color: '#ec4899' },
  pending_new_build: { icon: '📦', color: '#f59e0b' },
};

// ── Handler badge color map ──────────────────────────────────────────
const HANDLER_COLORS: Record<string, string> = {
  ssbc: '#7c3aed',
  thatcdn: '#7c3aed',
  lulutang: '#7c3aed',
  btsow: '#2563eb',
  snowfl: '#2563eb',
  yts: '#2563eb',
  wuji: '#2563eb',
};
const TEMPLATE_HANDLER_COLOR = '#6b7280';

function handlerBadgeColor(handler: string): string {
  return HANDLER_COLORS[handler] || TEMPLATE_HANDLER_COLOR;
}

// ── New handler names (tier indicator) ────────────────────────────────
const NEW_HANDLERS = new Set(['ssbc', 'thatcdn', 'lulutang', 'btsow', 'snowfl', 'yts', 'wuji']);

// ── Sort order for source status ─────────────────────────────────────
const STATUS_SORT_ORDER: Record<string, number> = {
  ok: 1,
  partial: 2,
  empty: 3,
  error: 4,
  timeout: 4,
  hallucinating: 5,
  skipped_webview: 5,
  pending_new_build: 6,
  pending: 7,
  running: 0,
};

// ── Filter tab type ──────────────────────────────────────────────────
type FilterTab = 'all' | 'ok' | 'error' | 'new' | 'hallucinating';

// ── FlatList item type ───────────────────────────────────────────────
type ListItem =
  | { _type: 'separator'; id: string; label: string }
  | { _type: 'source'; id: string; result: BenchSourceResult; isNew: boolean };

// ── Default config ───────────────────────────────────────────────────
const DEFAULT_CONFIG: BenchConfig = {
  query1: 'Inception',
  query2: '盗梦空间',
  onlyNewHandlers: true,
  onlyGreen: true,
  concurrency: 3,
  timeoutMs: 30000,
};

export default function BenchScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { lang } = useLang();
  const { sources } = useSources();

  // Guard: dev-only
  if (!__DEV__) {
    return (
      <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
        <Text style={{ color: colors.text, textAlign: 'center', marginTop: 60, fontSize: 15 }}>
          Dev only
        </Text>
      </View>
    );
  }

  // ── State ──────────────────────────────────────────────────────────
  const [config, setConfig] = useState<BenchConfig>({ ...DEFAULT_CONFIG });
  const [configOpen, setConfigOpen] = useState(false);
  const [session, setSession] = useState<BenchSession | null>(null);
  const [results, setResults] = useState<BenchSourceResult[]>([]);
  const [running, setRunning] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterTab, setFilterTab] = useState<FilterTab>('all');
  const abortRef = useRef({ aborted: false });

  // ── Derived counts ─────────────────────────────────────────────────
  const totalCount = results.length;
  const doneCount = results.filter(r => r.status !== 'pending' && r.status !== 'running').length;
  const okCount = results.filter(r => r.status === 'ok').length;
  const emptyCount = results.filter(r => r.status === 'empty').length;
  const errorCount = results.filter(r => r.status === 'error' || r.status === 'timeout').length;
  const magnetCount = results.reduce((sum, r) => sum + (r.q1ResultCount || 0), 0);

  // ── Sort: new handlers first, then ok by q1ResultCount desc, then empty, then error/timeout, then skipped ──
  const sortedResults = useMemo(() => {
    const arr = [...results];
    arr.sort((a, b) => {
      const aIsNew = NEW_HANDLERS.has(a.handler || '');
      const bIsNew = NEW_HANDLERS.has(b.handler || '');
      if (aIsNew !== bIsNew) return aIsNew ? -1 : 1;

      const aOrder = STATUS_SORT_ORDER[a.status] ?? 9;
      const bOrder = STATUS_SORT_ORDER[b.status] ?? 9;
      if (aOrder !== bOrder) return aOrder - bOrder;

      // Within 'ok' status, sort by q1ResultCount desc
      if (a.status === 'ok' && b.status === 'ok') {
        return (b.q1ResultCount || 0) - (a.q1ResultCount || 0);
      }
      return 0;
    });
    return arr;
  }, [results]);

  // ── Filtered by tab ────────────────────────────────────────────────
  const filteredResults = useMemo(() => {
    switch (filterTab) {
      case 'ok':
        return sortedResults.filter(r => r.status === 'ok');
      case 'error':
        return sortedResults.filter(r => r.status === 'error' || r.status === 'timeout' || r.status === 'empty');
      case 'new':
        return sortedResults.filter(r => NEW_HANDLERS.has(r.handler || ''));
      case 'hallucinating':
        return sortedResults.filter(r => r.status === 'hallucinating');
      default:
        return sortedResults;
    }
  }, [sortedResults, filterTab]);

  // ── Build FlatList data: group new handlers at top with separator ──
  const listData = useMemo((): ListItem[] => {
    const newHandlerResults = filteredResults.filter(r => NEW_HANDLERS.has(r.handler || ''));
    const otherResults = filteredResults.filter(r => !NEW_HANDLERS.has(r.handler || ''));
    const items: ListItem[] = [];

    if (newHandlerResults.length > 0) {
      items.push({
        _type: 'separator',
        id: 'sep_new',
        label: lang === 'zh'
          ? `--- 新 Handler 源 (${newHandlerResults.length}个) ---`
          : `--- New Handler Sources (${newHandlerResults.length}) ---`,
      });
      for (const r of newHandlerResults) {
        items.push({ _type: 'source', id: r.ruleId, result: r, isNew: true });
      }
    }

    if (otherResults.length > 0) {
      items.push({
        _type: 'separator',
        id: 'sep_other',
        label: lang === 'zh'
          ? `--- 其他源 (${otherResults.length}个) ---`
          : `--- Other Sources (${otherResults.length}) ---`,
      });
      for (const r of otherResults) {
        items.push({ _type: 'source', id: r.ruleId, result: r, isNew: false });
      }
    }

    return items;
  }, [filteredResults, lang]);

  // ── Run bench ──────────────────────────────────────────────────────
  const handleStart = useCallback(async () => {
    if (running) return;
    setRunning(true);
    setResults([]);
    setSession(null);
    abortRef.current = { aborted: false };

    try {
      const allRules = sources as any[];
      const onProgress = (sess: BenchSession) => {
        setResults([...sess.sources]);
      };

      const finalSession = await runBenchTest(allRules, config, onProgress, abortRef.current);
      setResults([...finalSession.sources]);
    } catch (err: any) {
      Alert.alert('Bench Error', err?.message || 'Unknown error');
    } finally {
      setRunning(false);
    }
  }, [running, sources, config]);

  // ── Retest failed ──────────────────────────────────────────────────
  const handleRetestFailed = useCallback(async () => {
    if (running) return;
    const failedSources = results.filter(r =>
      r.status === 'error' || r.status === 'timeout' || r.status === 'empty',
    );
    if (failedSources.length === 0) {
      Alert.alert('', lang === 'zh' ? '没有失败的源需要重测' : 'No failed sources to retest');
      return;
    }

    setRunning(true);
    abortRef.current = { aborted: false };

    try {
      const allRules = sources as any[];
      const failedIds = new Set(failedSources.map(f => f.ruleId));
      const failedRules = allRules.filter(r => failedIds.has(r.id || r.site?.name));

      const existingMap = new Map(results.map(r => [r.ruleId, r]));

      const onProgress = (sess: BenchSession) => {
        for (const p of sess.sources) {
          if (failedIds.has(p.ruleId)) {
            existingMap.set(p.ruleId, p);
          }
        }
        setResults(Array.from(existingMap.values()));
      };

      const finalSession = await runBenchTest(failedRules, config, onProgress, abortRef.current);
      for (const r of finalSession.sources) {
        existingMap.set(r.ruleId, r);
      }
      setResults(Array.from(existingMap.values()));
    } catch (err: any) {
      Alert.alert('Bench Error', err?.message || 'Unknown error');
    } finally {
      setRunning(false);
    }
  }, [running, sources, config, results, lang]);

  // ── Copy report JSON ───────────────────────────────────────────────
  const handleCopyReport = useCallback(async () => {
    if (!session && results.length === 0) {
      Alert.alert('', lang === 'zh' ? '暂无报告数据' : 'No report data yet');
      return;
    }
    try {
      const json = exportBenchReport({
        config,
        sources: results,
        running: false,
        startedAt: Date.now(),
        completedCount: results.length,
        aborted: false,
      });
      await Clipboard.setStringAsync(json);

      // Also try to save to file
      try {
        const File = require('expo-file-system/next').File;
        const Paths = require('expo-file-system/next').Paths;
        const f = new File(Paths.document, 'bench-report.json');
        f.write(json);
        Alert.alert(
          lang === 'zh' ? '已复制' : 'Copied',
          lang === 'zh'
            ? '报告 JSON 已复制到剪贴板\n文件: bench-report.json'
            : 'Report JSON copied to clipboard\nFile: bench-report.json',
        );
      } catch {
        Alert.alert(
          lang === 'zh' ? '已复制' : 'Copied',
          lang === 'zh'
            ? `报告 JSON 已复制到剪贴板 (${(json.length / 1024).toFixed(0)}KB)`
            : `Report JSON copied to clipboard (${(json.length / 1024).toFixed(0)}KB)`,
        );
      }
    } catch {
      Alert.alert('Error', lang === 'zh' ? '复制失败' : 'Copy failed');
    }
  }, [session, results, lang]);

  // ── Stop bench ─────────────────────────────────────────────────────
  const handleStop = useCallback(() => {
    abortRef.current.aborted = true;
    setRunning(false);
  }, []);

  // ── Filter tab definitions ─────────────────────────────────────────
  const filterTabs: { key: FilterTab; label: string }[] = useMemo(() => [
    { key: 'all', label: lang === 'zh' ? '全部' : 'All' },
    { key: 'ok', label: '✅' + (lang === 'zh' ? '有结果' : ' OK') },
    { key: 'error', label: '❌' + (lang === 'zh' ? '失败' : ' Failed') },
    { key: 'new', label: '🆕' + (lang === 'zh' ? '新handler' : ' New') },
    { key: 'hallucinating', label: '👻' + (lang === 'zh' ? '幻觉' : ' Halluc.') },
  ], [lang]);

  // ── KeyExtractor ───────────────────────────────────────────────────
  const keyExtractor = useCallback((item: ListItem) => item.id, []);

  // ── Toggle expand ──────────────────────────────────────────────────
  const toggleExpand = useCallback((id: string) => {
    setExpandedId(prev => (prev === id ? null : id));
  }, []);

  // ── Render item ────────────────────────────────────────────────────
  const renderItem = useCallback(({ item }: { item: ListItem }) => {
    if (item._type === 'separator') {
      return (
        <View style={styles.separatorContainer}>
          <View style={[styles.separatorLine, { backgroundColor: colors.border }]} />
          <Text style={[styles.separatorLabel, { color: colors.textSecondary }]}>{item.label}</Text>
          <View style={[styles.separatorLine, { backgroundColor: colors.border }]} />
        </View>
      );
    }

    const r = item.result;
    const isExpanded = expandedId === r.ruleId;
    const meta = STATUS_META[r.status] || STATUS_META.pending;
    const badgeColor = handlerBadgeColor(r.handler || '');
    const durationLabel = r.q1DurationMs != null ? `${(r.q1DurationMs / 1000).toFixed(1)}s` : '--';
    const countLabel = r.status === 'ok' ? `${r.q1ResultCount || 0}+${r.q2ResultCount || 0}` : '';

    return (
      <View>
        <TouchableOpacity
          activeOpacity={0.7}
          onPress={() => toggleExpand(r.ruleId)}
          style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
        >
          {/* Collapsed row */}
          <View style={styles.cardRow}>
            <Text style={[styles.statusIcon, { color: meta.color }]}>{meta.icon}</Text>
            <Text style={[styles.sourceName, { color: colors.text }]} numberOfLines={1}>
              {r.name}
            </Text>
            {r.handler ? (
              <View style={[styles.handlerBadge, { backgroundColor: badgeColor + '22' }]}>
                <Text style={[styles.handlerBadgeText, { color: badgeColor }]}>{r.handler}</Text>
              </View>
            ) : null}
            {item.isNew && (
              <View style={styles.newBadge}>
                <Text style={styles.newBadgeText}>NEW</Text>
              </View>
            )}
            {countLabel ? (
              <Text style={[styles.countLabel, { color: colors.textSecondary }]}>{countLabel}</Text>
            ) : null}
            <Text style={[styles.timeLabel, { color: colors.textSecondary }]}>{durationLabel}</Text>
            <Ionicons
              name={isExpanded ? 'chevron-up' : 'chevron-down'}
              size={14}
              color={colors.textSecondary}
            />
          </View>
        </TouchableOpacity>

        {/* Expanded detail */}
        {isExpanded && (
          <View style={[styles.expandedCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            {/* Q1 titles */}
            {r.q1SampleTitles && r.q1SampleTitles.length > 0 && (
              <View style={styles.detailSection}>
                <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>
                  Q1 "{config.query1}" ({r.q1ResultCount || 0}):
                </Text>
                {r.q1SampleTitles.slice(0, 5).map((t, i) => (
                  <Text key={i} style={[styles.detailText, { color: colors.text }]} numberOfLines={1}>
                    {t}
                  </Text>
                ))}
              </View>
            )}

            {/* Q2 info */}
            {r.q2ResultCount > 0 && (
              <View style={styles.detailSection}>
                <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>
                  Q2 "{config.query2}": {r.q2ResultCount} 条  幻觉率: {Math.round(r.hashOverlapRatio * 100)}%
                </Text>
              </View>
            )}

            {/* Hashes */}
            {r.q1Hashes && r.q1Hashes.length > 0 && (
              <View style={styles.detailSection}>
                <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>Hashes:</Text>
                {r.q1Hashes.slice(0, 3).map((h, i) => (
                  <Text key={i} style={[styles.detailMono, { color: colors.textSecondary }]} numberOfLines={1}>
                    {h}
                  </Text>
                ))}
              </View>
            )}

            {/* URL */}
            {r.builtUrl ? (
              <View style={styles.detailSection}>
                <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>URL:</Text>
                <Text style={[styles.detailMono, { color: colors.textTertiary || colors.textSecondary }]} numberOfLines={2}>
                  {r.builtUrl}
                </Text>
              </View>
            ) : null}

            {/* Overlap ratio */}
            {r.hashOverlapRatio != null && (
              <View style={styles.detailSection}>
                <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>
                  {lang === 'zh' ? '重叠率' : 'Overlap'}: {(r.hashOverlapRatio * 100).toFixed(0)}%
                </Text>
              </View>
            )}

            {/* Error info */}
            {(r.status === 'error' || r.status === 'timeout') && r.q1Error ? (
              <View style={styles.detailSection}>
                <Text style={[styles.detailText, { color: '#ef4444' }]} numberOfLines={3}>
                  {r.q1Error}
                </Text>
              </View>
            ) : null}
          </View>
        )}
      </View>
    );
  }, [expandedId, colors, config.query1, config.query2, lang, toggleExpand]);

  // ── Filter tab component ───────────────────────────────────────────
  const FilterChip = useCallback(({ tab }: { tab: { key: FilterTab; label: string } }) => {
    const active = filterTab === tab.key;
    return (
      <TouchableOpacity
        style={[
          styles.filterChip,
          { backgroundColor: colors.chipBg },
          active && { backgroundColor: '#4285F4' },
        ]}
        onPress={() => setFilterTab(tab.key)}
      >
        <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>
          {tab.label}
        </Text>
      </TouchableOpacity>
    );
  }, [filterTab, colors.chipBg]);

  // ── Main render ────────────────────────────────────────────────────
  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.text} />
          <Text style={[styles.backText, { color: colors.text }]}>
            {lang === 'zh' ? '返回' : 'Back'}
          </Text>
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>
          {lang === 'zh' ? '源压测台' : 'Source Bench'}
        </Text>
        <TouchableOpacity
          onPress={running ? handleStop : handleStart}
          style={[styles.startBtn, running && { backgroundColor: '#ef4444' }]}
          disabled={sources.length === 0}
        >
          <Ionicons name={running ? 'stop' : 'play'} size={14} color="#fff" />
          <Text style={styles.startBtnText}>
            {running ? (lang === 'zh' ? '停止' : 'Stop') : (lang === 'zh' ? '开始' : 'Start')}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Config (collapsible) */}
      <TouchableOpacity
        onPress={() => setConfigOpen(v => !v)}
        style={[styles.configToggle, { borderColor: colors.border }]}
      >
        <Ionicons name={configOpen ? 'chevron-down' : 'chevron-forward'} size={14} color={colors.textSecondary} />
        <Text style={[styles.configToggleText, { color: colors.textSecondary }]}>
          {lang === 'zh' ? '测试配置' : 'Test Config'}
        </Text>
      </TouchableOpacity>

      {configOpen && (
        <View style={[styles.configPanel, { backgroundColor: colors.card, borderColor: colors.border }]}>
          {/* Query 1 */}
          <View style={styles.configRow}>
            <Text style={[styles.configLabel, { color: colors.textSecondary }]}>Query1:</Text>
            <TextInput
              style={[styles.configInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.bg }]}
              value={config.query1}
              onChangeText={t => setConfig(c => ({ ...c, query1: t }))}
              placeholder="Query 1"
              placeholderTextColor={colors.textSecondary}
            />
          </View>

          {/* Query 2 */}
          <View style={styles.configRow}>
            <Text style={[styles.configLabel, { color: colors.textSecondary }]}>Query2:</Text>
            <TextInput
              style={[styles.configInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.bg }]}
              value={config.query2}
              onChangeText={t => setConfig(c => ({ ...c, query2: t }))}
              placeholder="Query 2"
              placeholderTextColor={colors.textSecondary}
            />
          </View>

          {/* Toggles */}
          <View style={styles.configToggleRow}>
            <TouchableOpacity
              style={styles.checkboxRow}
              onPress={() => setConfig(c => ({ ...c, onlyNewHandlers: !c.onlyNewHandlers }))}
            >
              <Ionicons
                name={config.onlyNewHandlers ? 'checkbox' : 'square-outline'}
                size={18}
                color={config.onlyNewHandlers ? '#4285F4' : colors.textSecondary}
              />
              <Text style={[styles.checkboxLabel, { color: colors.text }]}>
                {lang === 'zh' ? '仅新handler' : 'New handlers only'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.checkboxRow}
              onPress={() => setConfig(c => ({ ...c, onlyGreen: !c.onlyGreen }))}
            >
              <Ionicons
                name={config.onlyGreen ? 'checkbox' : 'square-outline'}
                size={18}
                color={config.onlyGreen ? '#4285F4' : colors.textSecondary}
              />
              <Text style={[styles.checkboxLabel, { color: colors.text }]}>
                {lang === 'zh' ? '仅Green' : 'Green only'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Concurrency */}
          <View style={styles.configRow}>
            <Text style={[styles.configLabel, { color: colors.textSecondary }]}>
              {lang === 'zh' ? '并发' : 'Concurrency'}:
            </Text>
            <View style={styles.concurrencyRow}>
              {[1, 3, 5].map(n => (
                <TouchableOpacity
                  key={n}
                  style={[
                    styles.concurrencyBtn,
                    { borderColor: colors.border },
                    config.concurrency === n && { backgroundColor: '#4285F4', borderColor: '#4285F4' },
                  ]}
                  onPress={() => setConfig(c => ({ ...c, concurrency: n as 1 | 3 | 5 }))}
                >
                  <Text style={[
                    styles.concurrencyBtnText,
                    { color: colors.text },
                    config.concurrency === n && { color: '#fff' },
                  ]}>
                    {n}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* Progress bar (fixed during search) */}
      {totalCount > 0 && (
        <View style={[styles.progressContainer, { borderBottomColor: colors.border }]}>
          <View style={styles.progressBarOuter}>
            <View
              style={[
                styles.progressBarInner,
                { width: `${totalCount > 0 ? (doneCount / totalCount) * 100 : 0}%` },
              ]}
            />
          </View>
          <Text style={[styles.progressText, { color: colors.textSecondary }]}>
            {doneCount}/{totalCount}
            {'  '}✅{okCount}{'  '}⭕{emptyCount}{'  '}❌{errorCount}{'  '}🧲{magnetCount}
          </Text>
        </View>
      )}

      {/* Filter tabs */}
      {totalCount > 0 && (
        <View style={styles.filterBar}>
          {filterTabs.map(tab => (
            <FilterChip key={tab.key} tab={tab} />
          ))}
        </View>
      )}

      {/* Source list */}
      {totalCount === 0 && !running ? (
        <View style={styles.emptyState}>
          <Ionicons name="speedometer-outline" size={48} color={colors.textSecondary} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            {lang === 'zh' ? '点击"开始"运行源压测' : 'Tap Start to run source bench test'}
          </Text>
        </View>
      ) : totalCount === 0 && running ? (
        <View style={styles.emptyState}>
          <ActivityIndicator size="large" color="#4285F4" />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            {lang === 'zh' ? '正在初始化...' : 'Initializing...'}
          </Text>
        </View>
      ) : (
        <FlatList<ListItem>
          data={listData}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: insets.bottom + 80 }}
          showsVerticalScrollIndicator={false}
          removeClippedSubviews={true}
          maxToRenderPerBatch={10}
          windowSize={8}
          initialNumToRender={10}
          updateCellsBatchingPeriod={100}
        />
      )}

      {/* Bottom actions */}
      {totalCount > 0 && !running && (
        <View style={[styles.bottomBar, { backgroundColor: colors.bg, borderTopColor: colors.border }]}>
          <TouchableOpacity
            style={[styles.bottomBtn, { borderColor: colors.border, backgroundColor: colors.card }]}
            onPress={handleCopyReport}
          >
            <Ionicons name="clipboard-outline" size={16} color={colors.text} />
            <Text style={[styles.bottomBtnText, { color: colors.text }]}>
              {lang === 'zh' ? '复制报告JSON' : 'Copy Report JSON'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.bottomBtn, { borderColor: colors.border, backgroundColor: colors.card }]}
            onPress={handleRetestFailed}
          >
            <Ionicons name="refresh-outline" size={16} color={colors.text} />
            <Text style={[styles.bottomBtnText, { color: colors.text }]}>
              {lang === 'zh' ? '重测失败' : 'Retest Failed'}
            </Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

// ── Styles ───────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 4,
    marginRight: 8,
  },
  backText: {
    fontSize: 15,
    marginLeft: 2,
  },
  headerTitle: {
    flex: 1,
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  sourceName: {
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 8,
  },
  startBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#22c55e',
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 16,
    gap: 4,
  },
  startBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
  },

  // Config
  configToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 6,
  },
  configToggleText: {
    fontSize: 13,
    fontWeight: '600',
  },
  configPanel: {
    marginHorizontal: 12,
    marginTop: 4,
    marginBottom: 8,
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    gap: 10,
  },
  configRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  configLabel: {
    fontSize: 13,
    fontWeight: '600',
    width: 80,
  },
  configInput: {
    flex: 1,
    height: 34,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    fontSize: 13,
  },
  configToggleRow: {
    flexDirection: 'row',
    gap: 20,
  },
  checkboxRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  checkboxLabel: {
    fontSize: 13,
  },
  concurrencyRow: {
    flexDirection: 'row',
    gap: 8,
  },
  concurrencyBtn: {
    width: 36,
    height: 30,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  concurrencyBtnText: {
    fontSize: 14,
    fontWeight: '700',
  },

  // Progress
  progressContainer: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  progressBarOuter: {
    height: 4,
    borderRadius: 2,
    backgroundColor: '#e5e7eb',
    overflow: 'hidden',
    marginBottom: 4,
  },
  progressBarInner: {
    height: '100%',
    borderRadius: 2,
    backgroundColor: '#4285F4',
  },
  progressText: {
    fontSize: 12,
    fontWeight: '600',
  },

  // Filter
  filterBar: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
    flexWrap: 'wrap',
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 14,
  },
  filterChipText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#9aa3b4',
  },
  filterChipTextActive: {
    color: '#fff',
  },

  // Empty
  emptyState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  emptyText: {
    fontSize: 14,
  },

  // Cards
  card: {
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 6,
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusIcon: {
    fontSize: 14,
    fontWeight: '700',
    width: 20,
    textAlign: 'center',
  },
  handlerBadge: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 6,
  },
  handlerBadgeText: {
    fontSize: 9,
    fontWeight: '700',
  },
  newBadge: {
    backgroundColor: '#ec4899',
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
  },
  newBadgeText: {
    fontSize: 8,
    fontWeight: '800',
    color: '#fff',
  },
  countLabel: {
    fontSize: 11,
    fontWeight: '600',
  },
  timeLabel: {
    fontSize: 11,
    width: 40,
    textAlign: 'right',
  },

  // Expanded
  expandedCard: {
    marginHorizontal: 4,
    marginTop: -2,
    marginBottom: 6,
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  detailSection: {
    marginBottom: 6,
  },
  detailLabel: {
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 2,
  },
  detailText: {
    fontSize: 11,
    lineHeight: 16,
  },
  detailMono: {
    fontSize: 10,
    fontFamily: 'monospace',
  },

  // Separator
  separatorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 4,
    gap: 8,
  },
  separatorLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
  },
  separatorLabel: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },

  // Bottom bar
  bottomBar: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    gap: 10,
    paddingBottom: 20,
  },
  bottomBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
    gap: 6,
  },
  bottomBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
});
