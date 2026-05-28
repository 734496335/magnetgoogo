import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang } from '../src/core/LangContext';
import { useTheme } from '../src/core/ThemeContext';

const URLS = {
  primary: 'https://cn.magnetgoogo.com/privacy.html',
  fallback: 'https://magnetgoogo.com/privacy.html',
};

export default function PrivacyScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { t } = useLang();
  const { colors } = useTheme();
  const [url, setUrl] = useState(URLS.primary);
  const [loading, setLoading] = useState(true);
  const [retried, setRetried] = useState(false);

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.bg }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>{t.privacyTitle}</Text>
        <View style={{ width: 26 }} />
      </View>
      {loading && (
        <ActivityIndicator style={styles.loader} size="small" color={colors.text} />
      )}
      <WebView
        source={{ uri: url }}
        style={{ flex: 1 }}
        onLoadEnd={() => setLoading(false)}
        onError={() => {
          if (!retried) {
            setRetried(true);
            setUrl(URLS.fallback);
          }
        }}
        onHttpError={() => {
          if (!retried) {
            setRetried(true);
            setUrl(URLS.fallback);
          }
        }}
      />
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
  loader: { position: 'absolute', top: '50%', alignSelf: 'center', zIndex: 10 },
});
