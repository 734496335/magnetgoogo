import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSources } from '../src/core/SourceContext';
import { useLang } from '../src/core/LangContext';
import { useTheme, type ThemeMode } from '../src/core/ThemeContext';
import type { Lang } from '../src/core/i18n';
import { getCrashLogs, clearCrashLogs, formatCrashReport } from '../src/core/crashReporter';

export default function SettingsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { meta, syncing, error, refresh } = useSources();
  const { lang, t, setLang } = useLang();
  const { mode, colors, setMode } = useTheme();

  const handleSync = async () => {
    await refresh();
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>{t.settings}</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Section 1: Source Sync */}
        <Text style={[styles.sectionTitle, { color: colors.textTertiary }]}>{t.sectionSources}</Text>
        <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow }]}>
          <TouchableOpacity
            style={styles.syncRow}
            onPress={handleSync}
            disabled={syncing}
            activeOpacity={0.7}
          >
            <Ionicons
              name="cloud-download-outline"
              size={20}
              color="#4285F4"
            />
            <View style={styles.rowContent}>
              <Text style={[styles.rowLabel, { color: colors.text }]}>{t.syncSources}</Text>
              {meta ? (
                <>
                  <Text style={styles.metaText}>
                    {t.syncSuccess(meta.count)}
                  </Text>
                  <Text style={styles.metaTime}>
                    {t.lastSync}: {new Date(meta.updatedAt).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </Text>
                </>
              ) : (
                <Text style={styles.metaText}>
                  {t.notSynced}
                </Text>
              )}
            </View>
            {syncing ? (
              <ActivityIndicator size="small" color="#4285F4" />
            ) : (
              <Ionicons name="chevron-forward" size={18} color="#ccc" />
            )}
          </TouchableOpacity>

          {error && (
            <>
              <View style={styles.divider} />
              <View style={styles.row}>
                <Ionicons name="alert-circle-outline" size={20} color="#EA4335" />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            </>
          )}
        </View>

        {/* Section 2: Theme */}
        <Text style={[styles.sectionTitle, { color: colors.textTertiary }]}>{t.sectionTheme}</Text>
        <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow }]}>
          <View style={styles.langRow}>
            {(['system', 'light', 'dark'] as ThemeMode[]).map((m) => {
              const label = m === 'system' ? (lang === 'zh' ? '跟随系统' : 'System') : m === 'light' ? (lang === 'zh' ? '浅色' : 'Light') : (lang === 'zh' ? '深色' : 'Dark');
              const icon = m === 'system' ? 'phone-portrait-outline' : m === 'light' ? 'sunny-outline' : 'moon-outline';
              return (
                <TouchableOpacity
                  key={m}
                  style={[styles.langOption, { backgroundColor: colors.chipBg }, mode === m && styles.langOptionActive]}
                  onPress={() => setMode(m)}
                  activeOpacity={0.7}
                >
                  <Ionicons name={icon as any} size={15} color={mode === m ? '#4285F4' : colors.textTertiary} />
                  <Text style={[styles.langText, { color: colors.textTertiary }, mode === m && styles.langTextActive]}>
                    {label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Section 3: Language */}
        <Text style={[styles.sectionTitle, { color: colors.textTertiary }]}>{t.sectionLanguage}</Text>
        <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow }]}>
          <View style={styles.langRow}>
            {(['zh', 'en'] as Lang[]).map((l) => (
              <TouchableOpacity
                key={l}
                style={[styles.langOption, lang === l && styles.langOptionActive]}
                onPress={() => setLang(l)}
                activeOpacity={0.7}
              >
                <Text style={[styles.langText, lang === l && styles.langTextActive]}>
                  {l === 'zh' ? t.langZh : t.langEn}
                </Text>
                {lang === l && (
                  <Ionicons name="checkmark-circle" size={18} color="#4285F4" />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Section 4: About */}
        <Text style={[styles.sectionTitle, { color: colors.textTertiary }]}>{t.sectionAbout}</Text>
        <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow }]}>
          <View style={styles.aboutRow}>
            <Image
              source={require('../assets/logo.png')}
              style={styles.aboutLogo}
              resizeMode="contain"
            />
            <Text style={styles.aboutVersion}>{t.version} 0.1.0</Text>
          </View>
          <View style={styles.divider} />
          <TouchableOpacity
            style={styles.syncRow}
            activeOpacity={0.7}
            onPress={async () => {
              const logs = await getCrashLogs();
              if (logs.length === 0) {
                Alert.alert(lang === 'zh' ? '无崩溃日志' : 'No Crash Logs', lang === 'zh' ? '应用运行正常，未捕获到错误' : 'App is running normally, no errors captured.');
                return;
              }
              const report = formatCrashReport(logs);
              Alert.alert(
                lang === 'zh' ? `发现 ${logs.length} 条崩溃日志` : `${logs.length} crash log(s) found`,
                lang === 'zh' ? '是否清空崩溃日志？' : 'Clear crash logs?',
                [
                  { text: lang === 'zh' ? '取消' : 'Cancel', style: 'cancel' },
                  { text: lang === 'zh' ? '清空日志' : 'Clear', onPress: () => clearCrashLogs(), style: 'destructive' },
                ],
              );
            }}
          >
            <Ionicons name="bug-outline" size={20} color="#EA4335" />
            <View style={styles.rowContent}>
              <Text style={[styles.rowLabel, { color: colors.text }]}>{lang === 'zh' ? '崩溃日志' : 'Crash Logs'}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color="#ccc" />
          </TouchableOpacity>
          <View style={styles.divider} />
          <TouchableOpacity
            style={styles.syncRow}
            onPress={() => router.push('/privacy')}
            activeOpacity={0.7}
          >
            <Ionicons name="shield-checkmark-outline" size={20} color="#6B7280" />
            <View style={styles.rowContent}>
              <Text style={[styles.rowLabel, { color: colors.text }]}>{t.privacyTitle}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color="#ccc" />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fffdfb' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#262b35',
  },
  content: {
    paddingHorizontal: 16,
    paddingBottom: 60,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#9aa3b4',
    marginTop: 24,
    marginBottom: 8,
    marginLeft: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#e4dfd6',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.2,
    shadowRadius: 20,
    elevation: 3,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 16,
    gap: 12,
  },
  syncRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    gap: 12,
  },
  rowContent: {
    flex: 1,
  },
  rowLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: '#262b35',
    marginBottom: 2,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: '#f0ede8',
    marginLeft: 48,
  },
  metaText: {
    fontSize: 12,
    color: '#9aa3b4',
    marginTop: 2,
  },
  metaTime: {
    fontSize: 11,
    color: '#b0b8c8',
    marginTop: 1,
  },
  errorText: {
    flex: 1,
    fontSize: 13,
    color: '#EA4335',
  },
  aboutRow: {
    alignItems: 'center',
    paddingVertical: 20,
    paddingHorizontal: 16,
    gap: 8,
  },
  aboutLogo: {
    width: 120,
    height: 36,
  },
  aboutVersion: {
    fontSize: 12,
    color: '#9aa3b4',
    textAlign: 'center',
  },
  langRow: {
    flexDirection: 'row',
    padding: 8,
    gap: 8,
  },
  langOption: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: '#f8f6f3',
  },
  langOptionActive: {
    backgroundColor: '#e8f0fe',
    borderWidth: 1.5,
    borderColor: '#4285F4',
  },
  langText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#9aa3b4',
  },
  langTextActive: {
    color: '#4285F4',
  },
});
