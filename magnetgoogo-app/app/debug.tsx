import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../src/core/ThemeContext';
import * as Clipboard from 'expo-clipboard';
import {
  getReports,
  clearReports,
  subscribe,
  exportReportsJson,
  type SearchReport,
  type SourceResult,
  type ResultItemLog,
} from '../src/core/searchDebugLogger';

export default function DebugScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [reports, setReports] = useState<SearchReport[]>(getReports());
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    return subscribe(() => setReports([...getReports()]));
  }, []);

  const handleClear = () => {
    Alert.alert('清除搜索报告', '确定清除所有报告？', [
      { text: '取消', style: 'cancel' },
      { text: '清除', style: 'destructive', onPress: () => clearReports() },
    ]);
  };

  const handleExport = async () => {
    const json = exportReportsJson();
    await Clipboard.setStringAsync(json);
    Alert.alert('已复制', `${reports.length} 条报告 JSON 已复制到剪贴板 (${(json.length / 1024).toFixed(0)}KB)`);
  };

  const statusIcon = (s: string) => {
    if (s === 'ok') return '✓';
    if (s === 'empty') return '○';
    if (s === 'timeout') return '⏱';
    return '✗';
  };
  const statusColor = (s: string) => {
    if (s === 'ok') return '#22c55e';
    if (s === 'empty') return '#f59e0b';
    if (s === 'timeout') return '#f97316';
    return '#ef4444';
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.title, { color: colors.text }]}>搜索调试报告</Text>
        <TouchableOpacity onPress={handleExport} style={styles.clearBtn}>
          <Ionicons name="copy-outline" size={18} color="#3b82f6" />
        </TouchableOpacity>
        <TouchableOpacity onPress={handleClear} style={styles.clearBtn}>
          <Ionicons name="trash-outline" size={18} color="#ef4444" />
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: insets.bottom + 20 }}>
        {reports.length === 0 && (
          <Text style={[styles.empty, { color: colors.textSecondary }]}>暂无搜索报告，执行一次搜索后会自动记录</Text>
        )}

        {reports.map((r) => (
          <TouchableOpacity
            key={r.id}
            activeOpacity={0.7}
            onPress={() => setExpanded(expanded === r.id ? null : r.id)}
            style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
          >
            {/* Summary row */}
            <View style={styles.cardHeader}>
              <Text style={[styles.query, { color: colors.text }]} numberOfLines={1}>
                "{r.query}"
              </Text>
              <Text style={[styles.statusBadge, r.completed ? styles.badgeComplete : styles.badgePartial]}>
                {r.completed ? '完成' : `${r.completedSources}/${r.totalSources}`}
              </Text>
              <Text style={[styles.time, { color: colors.textSecondary }]}>
                {new Date(r.startedAt).toLocaleTimeString('zh-CN', { hour12: false })}
              </Text>
            </View>

            {/* Stats row */}
            <View style={styles.statsRow}>
              <Stat label="总源" value={r.totalSources} color={colors.textSecondary} />
              <Stat label="可访问" value={r.accessibleCount} color="#3b82f6" />
              <Stat label="有结果" value={r.resultCount} color="#22c55e" />
              <Stat label="空" value={r.emptyCount} color="#f59e0b" />
              <Stat label="失败" value={r.errorCount} color="#ef4444" />
              <Stat label="磁力" value={r.totalMagnets} color="#8b5cf6" />
              <Stat label="耗时" value={`${(r.totalDurationMs / 1000).toFixed(1)}s`} color={colors.textSecondary} />
            </View>

            {/* Quick summary */}
            <View style={styles.quickRow}>
              <Text style={[styles.quickText, { color: colors.textSecondary }]}>
                最快: {r.fastestSource} · 最多: {r.mostResultsSource}
              </Text>
            </View>

            {/* Expanded: per-source details */}
            {expanded === r.id && (
              <View style={styles.detailSection}>
                <View style={styles.detailDivider} />
                {r.sourceResults.map((sr, i) => (
                  <SourceRow key={i} sr={sr} statusIcon={statusIcon} statusColor={statusColor} colors={colors} />
                ))}
              </View>
            )}

            <View style={styles.expandHint}>
              <Ionicons
                name={expanded === r.id ? 'chevron-up' : 'chevron-down'}
                size={14}
                color={colors.textSecondary}
              />
            </View>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={[styles.statLabel, { color }]}>{label}</Text>
    </View>
  );
}

function SourceRow({
  sr,
  statusIcon,
  statusColor,
  colors,
}: {
  sr: SourceResult;
  statusIcon: (s: string) => string;
  statusColor: (s: string) => string;
  colors: any;
}) {
  return (
    <View>
      <View style={styles.sourceRow}>
        <Text style={[styles.sourceIcon, { color: statusColor(sr.status) }]}>{statusIcon(sr.status)}</Text>
        <View style={styles.sourceInfo}>
          <View style={styles.sourceNameRow}>
            <Text style={[styles.sourceName, { color: colors.text }]} numberOfLines={1}>
              {sr.name}
            </Text>
            <Text style={[styles.srcCount, { color: colors.textSecondary }]}>
              {sr.resultCount > 0 ? `${sr.resultCount}条` : ''}
            </Text>
            <Text style={[styles.srcTime, { color: colors.textSecondary }]}>
              {(sr.durationMs / 1000).toFixed(1)}s
            </Text>
            <View style={styles.badges}>
              {sr.requiresWaf && <Text style={styles.badgeW}>W</Text>}
              {sr.requiresBrowser && <Text style={styles.badgeB}>B</Text>}
            </View>
          </View>
          {sr.status !== 'ok' && sr.status !== 'empty' && (
            <Text style={[styles.sourceDetail, { color: '#ef4444' }]} numberOfLines={1}>
              {sr.status}{sr.error ? ` · ${sr.error.slice(0, 80)}` : ''}
            </Text>
          )}
        </View>
      </View>
      {sr.items?.length > 0 && (
        <View style={styles.itemList}>
          {sr.items.map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <Text style={[
                styles.itemScore,
                { color: item.relevance >= 80 ? '#22c55e' : item.relevance >= 30 ? '#f59e0b' : '#ef4444' },
              ]}>
                {item.relevance}
              </Text>
              <View style={styles.itemBody}>
                <Text style={[styles.itemTitle, { color: colors.text }]} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={[styles.itemMeta, { color: colors.textSecondary }]} numberOfLines={1}>
                  {item.size ? item.size + ' · ' : ''}{item.hash}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  backBtn: { padding: 4, marginRight: 8 },
  title: { flex: 1, fontSize: 18, fontWeight: '700' },
  clearBtn: { padding: 6 },
  scroll: { flex: 1, paddingHorizontal: 12 },
  empty: { textAlign: 'center', marginTop: 60, fontSize: 14 },
  card: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    marginBottom: 10,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  query: { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 4 },
  statusBadge: {
    fontSize: 9,
    fontWeight: '700',
    paddingHorizontal: 5,
    paddingVertical: 1.5,
    borderRadius: 4,
    overflow: 'hidden',
    marginRight: 6,
  },
  badgeComplete: { color: '#15803d', backgroundColor: '#dcfce7' },
  badgePartial: { color: '#b45309', backgroundColor: '#fef3c7' },
  time: { fontSize: 11 },
  statsRow: {
    flexDirection: 'row',
    marginTop: 8,
    gap: 2,
  },
  stat: { alignItems: 'center', flex: 1 },
  statValue: { fontSize: 14, fontWeight: '700' },
  statLabel: { fontSize: 9, marginTop: 1 },
  quickRow: { marginTop: 6 },
  quickText: { fontSize: 11 },
  detailSection: { marginTop: 4 },
  detailDivider: { height: 1, backgroundColor: '#e2e8f0', marginVertical: 8 },
  sourceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 3,
  },
  sourceIcon: { width: 16, fontSize: 12, fontWeight: '700', marginTop: 2 },
  sourceInfo: { flex: 1 },
  sourceNameRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  sourceName: { fontSize: 12, fontWeight: '600' },
  badges: { flexDirection: 'row', gap: 2 },
  badgeW: {
    fontSize: 8,
    fontWeight: '700',
    color: '#d97706',
    backgroundColor: '#fef3c7',
    paddingHorizontal: 3,
    paddingVertical: 1,
    borderRadius: 3,
    overflow: 'hidden',
  },
  badgeB: {
    fontSize: 8,
    fontWeight: '700',
    color: '#0891b2',
    backgroundColor: '#e0f2fe',
    paddingHorizontal: 3,
    paddingVertical: 1,
    borderRadius: 3,
    overflow: 'hidden',
  },
  srcCount: { fontSize: 10, marginLeft: 4 },
  srcTime: { fontSize: 10, marginLeft: 4 },
  sourceDetail: { fontSize: 10, marginTop: 1 },
  itemList: { marginLeft: 16, marginTop: 2, marginBottom: 4 },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e2e8f0',
  },
  itemScore: {
    width: 26,
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'right',
    marginRight: 6,
    marginTop: 1,
  },
  itemBody: { flex: 1 },
  itemTitle: { fontSize: 11 },
  itemMeta: { fontSize: 9, marginTop: 1 },
  expandHint: { alignItems: 'center', marginTop: 4 },
});
