import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useFocusEffect } from 'expo-router';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Image,
  Animated,
  Easing,
  Dimensions,
  ScrollView,
  InteractionManager,
  Linking,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../src/core/LangContext';
import { useTheme } from '../src/core/ThemeContext';
import { getHistory, addHistory, removeHistory, clearHistory, type HistoryItem } from '../src/core/searchHistory';
import { getFavorites, type FavoriteItem } from '../src/core/favorites';
import FeedbackFAB from '../src/components/FeedbackFAB';
import { COMPLIANCE_MODE, WEBSITE_URL } from '../src/core/complianceConfig';
import { getLatestReport, printReport } from '../src/core/searchDebugLogger';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');
const BTN_W = SCREEN_W * 0.78;

// ── Glass gradient button (CSS GlassButton faithful port) ────────────
// Colors matched to CSS: #4ea1ff → #b855ff → #ff6289 → #ffbc55 → #6dedad
const GRADIENT_COLORS = [
  '#4ea1ff', '#b855ff', '#ff6289', '#ffbc55', '#6dedad',
  '#4ea1ff', '#b855ff', '#ff6289', '#ffbc55', '#6dedad',
  '#4ea1ff',
] as const;

function FlowingGradientButton({
  onPress,
  label,
}: {
  onPress: () => void;
  label: string;
}) {
  const flow = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.timing(flow, {
        toValue: 1,
        duration: 3000,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    ).start();
  }, [flow]);

  const translateX = flow.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -BTN_W],
  });

  return (
    <TouchableOpacity
      style={styles.btnWrap}
      onPress={onPress}
      activeOpacity={0.85}
    >
      {/* Outer Glow (模拟弥散的彩色投影) */}
      <View style={styles.btnShadowWrapper}>
        <View style={styles.btnOuter}>

          {/* Layer 1: 底层绚丽滚动渐变 (100%纯净，不加任何模糊) */}
          <Animated.View style={[styles.gradientStrip, { transform: [{ translateX }] }]}>
            <LinearGradient
              colors={GRADIENT_COLORS}
              start={{ x: 0, y: 0.5 }}
              end={{ x: 1, y: 0.5 }}
              style={{ width: BTN_W * 2, height: 54 }}
            />
          </Animated.View>

          {/* Layer 2: 顶部高光 (模拟玻璃顶部的强反射光，制造“鼓起”的错觉) */}
          <LinearGradient
            colors={['rgba(255,255,255,0.8)', 'rgba(255,255,255,0)']}
            start={{ x: 0.5, y: 0 }}
            end={{ x: 0.5, y: 0.45 }}
            style={StyleSheet.absoluteFill}
          />

          {/* Layer 3: 底部边缘反光与内阴影 (增加底部的立体厚度) */}
          <LinearGradient
            colors={['rgba(0,0,0,0)', 'rgba(0,0,0,0.08)', 'rgba(255,255,255,0.5)']}
            locations={[0.5, 0.85, 1]}
            start={{ x: 0.5, y: 0 }}
            end={{ x: 0.5, y: 1 }}
            style={StyleSheet.absoluteFill}
          />

          {/* Layer 4: 高对比度白边 (模拟玻璃切割边缘) */}
          <View style={styles.glassBorderFrame} />

          {/* Layer 5: 内容层 */}
          <View style={styles.btnContentRow}>
            <Text style={styles.btnText}>{label}</Text>
            <Ionicons name="arrow-forward" size={20} color="#fff" />
          </View>

        </View>
      </View>
    </TouchableOpacity>
  );
}

// ── Top Toast ───────────────────────────────────────────────────────
function TopToast({ message, visible, onHide }: { message: string; visible: boolean; onHide: () => void }) {
  const translateY = useRef(new Animated.Value(-80)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(translateY, { toValue: 0, useNativeDriver: true, tension: 80, friction: 10 }),
        Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      ]).start();
      const timer = setTimeout(() => {
        Animated.parallel([
          Animated.timing(translateY, { toValue: -80, duration: 250, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0, duration: 250, useNativeDriver: true }),
        ]).start(() => onHide());
      }, 2500);
      return () => clearTimeout(timer);
    }
  }, [visible, translateY, opacity, onHide]);

  if (!visible) return null;
  return (
    <Animated.View style={[styles.toastWrap, { transform: [{ translateY }], opacity }]}>
      <View style={styles.toastInner}>
        <Ionicons name="alert-circle-outline" size={18} color="#f59e0b" />
        <Text style={styles.toastText}>{message}</Text>
      </View>
    </Animated.View>
  );
}

// ── Main Screen ─────────────────────────────────────────────────────
export default function HomeScreen() {
  const [query, setQuery] = useState('');
  const [toast, setToast] = useState('');
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { t } = useLang();
  const { colors } = useTheme();
  const hideToast = useCallback(() => setToast(''), []);

  const loadFavorites = useCallback(() => {
    getFavorites().then(setFavorites);
  }, []);

  useEffect(() => {
    getHistory().then(setHistory);
    loadFavorites();
    // Print latest debug report directly to console.log on startup
    const r = getLatestReport();
    if (r) {
      console.log("\n[PULLED REPORT] Print Latest Search Debug Report:");
      printReport(r);
    }
  }, [loadFavorites]);

  // Refresh favorites + history every time the screen regains focus
  // (e.g. returning from search where user may have added favorites)
  // Defer reads until after the navigation animation finishes to avoid jank
  useFocusEffect(
    useCallback(() => {
      const task = InteractionManager.runAfterInteractions(() => {
        loadFavorites();
        getHistory().then(setHistory);
        const r = getLatestReport();
        if (r) {
          console.log("\n[PULLED REPORT FOCUS] Print Latest Search Debug Report:");
          printReport(r);
        }
      });
      return () => task.cancel();
    }, [loadFavorites]),
  );

  const handleSearch = async () => {
    if (!query.trim()) {
      setToast(t.emptyQueryToast);
      return;
    }
    await addHistory(query.trim());
    setHistory(await getHistory());
    router.push({ pathname: '/search', params: { q: query.trim() } });
  };

  const handleHistoryTap = async (q: string) => {
    setQuery(q);
    await addHistory(q);
    setHistory(await getHistory());
    router.push({ pathname: '/search', params: { q } });
  };

  const handleRemoveHistory = async (q: string) => {
    await removeHistory(q);
    setHistory(await getHistory());
  };

  const handleClearHistory = async () => {
    await clearHistory();
    setHistory([]);
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Toast */}
      <TopToast message={toast} visible={!!toast} onHide={hideToast} />

      {/* Settings top-right */}
      <View style={styles.topRow}>
        <View style={{ flex: 1 }} />
        <TouchableOpacity
          style={styles.settingsBtn}
          onPress={() => router.push('/settings')}
        >
          <Ionicons name="settings-outline" size={22} color={colors.textTertiary} />
        </TouchableOpacity>
      </View>

      {/* Push content to ~28% vertical position */}
      <View style={{ height: SCREEN_H * 0.22 }} />

      {/* Brand block: magnet icon + text logo + slogan */}
      <View style={styles.brandRow}>
        <Image
          source={require('../assets/icon.png')}
          style={styles.magnetIcon}
          resizeMode="contain"
        />
        <Image
          source={require('../assets/logo.png')}
          style={styles.logo}
          resizeMode="contain"
        />
      </View>
      <Text style={[styles.subtitle, { color: colors.textTertiary }]}>
        {t.sloganPrefix}
        <Text style={{ color: colors.accent, fontWeight: '600' }}>{t.sloganBrand}</Text>
      </Text>

      {/* Interaction block: search + button */}
      <View style={[styles.searchField, { backgroundColor: colors.inputBg, shadowColor: colors.shadow, borderColor: colors.border }]}>
        <Ionicons name="search" size={20} color="#858da0" style={{ marginRight: 12 }} />
        <TextInput
          style={[styles.searchInput, { color: colors.text }]}
          placeholder={COMPLIANCE_MODE ? t.complianceSearchPlaceholder : t.searchPlaceholder}
          placeholderTextColor={colors.textTertiary}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
          maxLength={100}
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => setQuery('')}>
            <Ionicons name="close-circle" size={20} color="#c0c6d0" />
          </TouchableOpacity>
        )}
      </View>

      <FlowingGradientButton onPress={handleSearch} label={t.searchButton} />

      {/* Compliance banner */}
      {COMPLIANCE_MODE && (
        <TouchableOpacity
          style={styles.complianceBanner}
          onPress={() => Linking.openURL(WEBSITE_URL)}
          activeOpacity={0.8}
        >
          <LinearGradient
            colors={['#f0fdf4', '#ecfdf5', '#f0fdf4']}
            style={styles.complianceBannerBg}
          >
            <View style={styles.complianceBadge}>
              <Ionicons name="shield-checkmark" size={18} color="#fff" />
            </View>
            <Text style={styles.complianceLine1}>
              {t.complianceBannerLine1}
            </Text>
            <View style={styles.complianceLinkRow}>
              <Text style={styles.complianceLinkText}>{t.complianceBannerLink}</Text>
              <Ionicons name="chevron-forward" size={14} color="#6366f1" />
            </View>
          </LinearGradient>
        </TouchableOpacity>
      )}

      {/* Search history */}
      {history.length > 0 && (
        <View style={styles.historyWrap}>
          <View style={styles.historyHeader}>
            <Text style={[styles.historyTitle, { color: colors.textTertiary }]}>{t.historyTitle || '搜索历史'}</Text>
            <TouchableOpacity onPress={handleClearHistory}>
              <Text style={styles.historyClear}>{t.historyClear || '清空'}</Text>
            </TouchableOpacity>
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.historyScroll}
          >
            {history.slice(0, 20).map((h) => (
              <TouchableOpacity
                key={h.query}
                style={[styles.historyChip, { backgroundColor: colors.chipBg }]}
                onPress={() => handleHistoryTap(h.query)}
                onLongPress={() => handleRemoveHistory(h.query)}
              >
                <Text style={[styles.historyChipText, { color: colors.textSecondary }]} numberOfLines={1}>{h.query}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}

      {/* Favorites entry (only if non-empty) */}
      {favorites.length > 0 && (
        <TouchableOpacity
          style={[styles.favEntry, { backgroundColor: colors.chipBg }]}
          onPress={() => router.push('/favorites')}
          activeOpacity={0.7}
        >
          <Ionicons name="bookmark" size={16} color="#6366f1" />
          <Text style={[styles.favEntryText, { color: colors.text }]}>{t.favoritesTitle}</Text>
          <Text style={[styles.favEntryCount, { color: colors.textTertiary }]}>{favorites.length}</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.textTertiary} />
        </TouchableOpacity>
      )}

      <View style={{ flex: 1 }} />

      <FeedbackFAB />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fffdfb',
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  topRow: {
    flexDirection: 'row',
    width: '100%',
    paddingVertical: 4,
  },
  settingsBtn: {
    padding: 8,
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  magnetIcon: {
    width: 68,
    height: 68,
    marginRight: 0,
  },
  logo: {
    width: 220,
    height: 60,
  },
  subtitle: {
    fontSize: 14,
    color: '#9aa3b4',
    letterSpacing: 0,
    marginBottom: 32,
  },
  searchField: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '100%',
    height: 54,
    borderRadius: 27,
    backgroundColor: 'rgba(255,255,255,0.85)',
    paddingHorizontal: 20,
    marginBottom: 28,
    borderWidth: 1,
    borderColor: '#e0dcd6',
    shadowColor: '#b4aa9b',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.15,
    shadowRadius: 20,
    elevation: 5,
  },
  searchInput: {
    flex: 1,
    fontSize: 16,
    fontWeight: '500',
    color: '#5d6578',
  },
  btnWrap: {
    width: BTN_W,
    marginBottom: 0,
    alignItems: 'center',
  },
  btnShadowWrapper: {
    width: BTN_W,
    height: 54,
    borderRadius: 27,
    shadowColor: '#ff6289',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.45,
    shadowRadius: 20,
    elevation: 10,
    backgroundColor: '#fff',
  },
  btnOuter: {
    width: '100%',
    height: '100%',
    borderRadius: 27,
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
  },
  gradientStrip: {
    position: 'absolute',
    top: 0,
    left: 0,
    height: 54,
    width: BTN_W * 2,
  },
  glassBorderFrame: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 27,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.75)',
  },
  btnContentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    zIndex: 10,
  },
  btnText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#fff',
    letterSpacing: 0.5,
    textShadowColor: 'rgba(0,0,0,0.15)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  toastWrap: {
    position: 'absolute',
    top: 50,
    left: 24,
    right: 24,
    zIndex: 999,
    alignItems: 'center',
  },
  toastInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#fffbeb',
    borderWidth: 1,
    borderColor: '#fde68a',
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 18,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 6,
  },
  toastText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#92400e',
  },
  historyWrap: {
    width: '100%',
    marginTop: 20,
  },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  historyTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#9aa3b4',
  },
  historyClear: {
    fontSize: 12,
    color: '#c0c6d0',
  },
  historyScroll: {
    gap: 8,
  },
  historyChip: {
    backgroundColor: '#f4f2ef',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 7,
    maxWidth: 160,
  },
  historyChipText: {
    fontSize: 13,
    fontWeight: '500',
    color: '#5d6578',
  },
  favEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '100%',
    marginTop: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 14,
    gap: 8,
  },
  favEntryText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
  },
  favEntryCount: {
    fontSize: 13,
    fontWeight: '500',
  },
  complianceBanner: {
    width: '100%',
    marginTop: 22,
    borderRadius: 18,
    borderWidth: 1.5,
    borderColor: '#86efac',
    overflow: 'hidden',
    shadowColor: '#10b981',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.18,
    shadowRadius: 12,
    elevation: 6,
  },
  complianceBannerBg: {
    paddingVertical: 16,
    paddingHorizontal: 18,
    alignItems: 'center',
    gap: 8,
  },
  complianceBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#10b981',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 2,
  },
  complianceLine1: {
    fontSize: 15,
    fontWeight: '700',
    color: '#065f46',
    textAlign: 'center',
    lineHeight: 22,
  },
  complianceLinkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    marginTop: 2,
    backgroundColor: 'rgba(99,102,241,0.1)',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  complianceLinkText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#6366f1',
  },
});
