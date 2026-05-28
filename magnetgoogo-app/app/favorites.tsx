import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Clipboard from 'expo-clipboard';
import { LinearGradient } from 'expo-linear-gradient';
import { useLang } from '../src/core/LangContext';
import { useTheme } from '../src/core/ThemeContext';
import { getFavorites, removeFavorite, type FavoriteItem } from '../src/core/favorites';
import { guessKind, KIND_THEMES } from '../src/core/types';

export default function FavoritesScreen() {
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { t } = useLang();
  const { colors } = useTheme();

  const load = useCallback(async () => {
    setItems(await getFavorites());
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCopy = async (item: FavoriteItem) => {
    try {
      await Clipboard.setStringAsync(item.magnet);
      setCopiedId(item.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      Alert.alert(t.copyFailed);
    }
  };

  const handleOpen = (magnet: string) => {
    Linking.openURL(magnet).catch(() => Alert.alert(t.cannotOpen, t.cannotOpenMsg));
  };

  const handleRemove = async (magnet: string) => {
    await removeFavorite(magnet);
    await load();
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>{t.favoritesTitle}</Text>
        <View style={{ width: 26 }} />
      </View>

      {items.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="bookmark-outline" size={48} color="#e0e0e0" />
          <Text style={styles.emptyText}>{t.noFavorites}</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.magnet}
          contentContainerStyle={{ padding: 16 }}
          renderItem={({ item }) => {
            const copied = copiedId === item.id;
            return (
              <View style={[styles.card, { backgroundColor: colors.card, shadowColor: colors.shadow, borderColor: colors.border }]}>
                <View style={styles.cardRow}>
                  <LinearGradient
                    colors={(() => { const k = guessKind(item.title); return KIND_THEMES[k].tileColors; })() as [string, string]}
                    style={styles.iconTile}
                  >
                    <Ionicons name={(() => { const k = guessKind(item.title); return KIND_THEMES[k].iconName; })() as any} size={22} color={(() => { const k = guessKind(item.title); return KIND_THEMES[k].iconColor; })()} />
                  </LinearGradient>
                  <View style={{ flex: 1 }}>
                    <View style={styles.titleRow}>
                      <Text style={[styles.title, { color: colors.text }]} numberOfLines={2}>{item.title}</Text>
                      <TouchableOpacity onPress={() => handleRemove(item.magnet)}>
                        <Ionicons name="bookmark" size={18} color="#6366f1" />
                      </TouchableOpacity>
                    </View>
                    <Text style={[styles.meta, { color: colors.textTertiary }]}>
                      {item.size ? `${item.size} · ` : ''}{item.sourceName}
                    </Text>
                  </View>
                </View>
                <View style={styles.btnRow}>
                  <TouchableOpacity style={styles.btn} onPress={() => handleCopy(item)}>
                    <Ionicons name="copy-outline" size={14} color="#4e8aff" />
                    <Text style={styles.btnText}>{copied ? t.copied : t.copyMagnet}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.btn} onPress={() => handleOpen(item.magnet)}>
                    <Ionicons name="open-outline" size={14} color="#f06529" />
                    <Text style={[styles.btnText, { color: '#f06529' }]}>{t.openMagnet}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          }}
        />
      )}
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
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#262b35' },
  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  emptyText: { fontSize: 15, color: '#c0c6d0' },
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: 'transparent',
    shadowColor: '#e4dfd6',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.2,
    shadowRadius: 16,
    elevation: 3,
  },
  cardRow: { flexDirection: 'row', gap: 12 },
  iconTile: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  title: { flex: 1, fontSize: 14, fontWeight: '600', color: '#262b35', lineHeight: 19 },
  meta: { fontSize: 12, color: '#9aa3b4', marginTop: 4, marginBottom: 8 },
  btnRow: { flexDirection: 'row', gap: 12 },
  btn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  btnText: { fontSize: 12, fontWeight: '600', color: '#4e8aff' },
});
