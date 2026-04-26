import React, { useState, useEffect, useRef, useCallback } from 'react';
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
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../src/core/LangContext';
import { useTheme } from '../src/core/ThemeContext';
import { getHistory, addHistory, removeHistory, clearHistory, type HistoryItem } from '../src/core/searchHistory';
import { getFavorites, removeFavorite, type FavoriteItem } from '../src/core/favorites';
import * as Clipboard from 'expo-clipboard';
import FeedbackFAB from '../src/components/FeedbackFAB';

const SCREEN_W = Dimensions.get('window').width;
const BTN_W = SCREEN_W * 0.78;

// ── Flowing gradient button ─────────────────────────────────────────
// 5-color cycle repeated identically → scrolling one BTN_W returns to same visual
const GRADIENT_COLORS = [
  '#4facfe', '#a855f7', '#ff6b9d', '#ffa751', '#7bf48c',
  '#4facfe', '#a855f7', '#ff6b9d', '#ffa751', '#7bf48c',
  '#4facfe',
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
      <View style={styles.btnOuter}>
        {/* Scrolling gradient strip (2x width) */}
        <Animated.View style={[styles.gradientStrip, { transform: [{ translateX }] }]}>
          <LinearGradient
            colors={GRADIENT_COLORS}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={{ width: BTN_W * 2, height: 54 }}
          />
        </Animated.View>
        {/* Glass highlight on top half */}
        <View style={styles.glassBorder} />
        {/* Label */}
        <View style={styles.btnContentRow}>
          <Text style={styles.btnText}>{label}</Text>
          <Ionicons name="arrow-forward" size={20} color="#fff" />
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
  const { lang, t } = useLang();
  const { colors } = useTheme();
  const hideToast = useCallback(() => setToast(''), []);

  const loadFavorites = useCallback(() => {
    getFavorites().then(setFavorites);
  }, []);

  useEffect(() => {
    getHistory().then(setHistory);
    loadFavorites();
  }, [loadFavorites]);

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

      {/* Push content to ~40% vertical position (visual center, slightly above true center) */}
      <View style={{ flex: 3 }} />

      {/* Brand block: logo + slogan as a tight unit */}
      <Image
        source={require('../assets/logo.png')}
        style={styles.logo}
        resizeMode="contain"
      />
      <Text style={[styles.subtitle, { color: colors.textTertiary }]}>{t.slogan}</Text>

      {/* Interaction block: search + button */}
      <View style={[styles.searchField, { backgroundColor: colors.inputBg, shadowColor: colors.shadow }]}>
        <Ionicons name="search" size={20} color="#858da0" style={{ marginRight: 12 }} />
        <TextInput
          style={[styles.searchInput, { color: colors.text }]}
          placeholder={t.searchPlaceholder}
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

      {/* Favorites (only if non-empty) */}
      {favorites.length > 0 && (
        <View style={styles.historyWrap}>
          <View style={styles.historyHeader}>
            <Text style={[styles.historyTitle, { color: colors.textTertiary }]}>
              <Ionicons name="star" size={13} color="#f59e0b" />{' '}{t.favoritesTitle}
            </Text>
            <TouchableOpacity onPress={() => router.push('/favorites')}>
              <Text style={styles.historyClear}>{lang === 'zh' ? '全部' : 'All'}</Text>
            </TouchableOpacity>
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.historyScroll}
          >
            {favorites.slice(0, 10).map((fav) => (
              <TouchableOpacity
                key={fav.magnet}
                style={[styles.favChip, { backgroundColor: colors.chipBg }]}
                onPress={() => {
                  Clipboard.setStringAsync(fav.magnet);
                  setToast(t.copied);
                }}
                onLongPress={() => {
                  removeFavorite(fav.magnet).then(loadFavorites);
                }}
              >
                <Text style={[styles.favChipTitle, { color: colors.text }]} numberOfLines={1}>{fav.title}</Text>
                <Text style={[styles.favChipMeta, { color: colors.textTertiary }]} numberOfLines={1}>{fav.size}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}

      <View style={{ flex: 5 }} />

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
  logo: {
    width: 240,
    height: 68,
    marginBottom: 10,
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
    marginBottom: 16,
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
  btnOuter: {
    width: BTN_W,
    height: 54,
    borderRadius: 27,
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#a855f7',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
    elevation: 8,
  },
  gradientStrip: {
    position: 'absolute',
    top: 0,
    left: 0,
    height: 54,
    width: BTN_W * 2,
  },
  glassBorder: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '48%',
    borderTopLeftRadius: 27,
    borderTopRightRadius: 27,
    backgroundColor: 'rgba(255,255,255,0.20)',
  },
  btnContentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  btnText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
    letterSpacing: 0.3,
    textShadowColor: 'rgba(0,0,0,0.18)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
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
  favChip: {
    backgroundColor: '#f4f2ef',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 8,
    maxWidth: 200,
  },
  favChipTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#262b35',
  },
  favChipMeta: {
    fontSize: 11,
    fontWeight: '400',
    color: '#9aa3b4',
    marginTop: 2,
  },
});
