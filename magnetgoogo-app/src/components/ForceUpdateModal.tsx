import React, { useState, useRef, useCallback } from 'react';
import { Modal, View, Text, TouchableOpacity, Linking, StyleSheet, Platform, Alert } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as IntentLauncher from 'expo-intent-launcher';
import type { ConfigCheckResult } from '../core/configChecker';

interface Props {
  result: ConfigCheckResult;
  visible: boolean;
}

export default function ForceUpdateModal({ result, visible }: Props) {
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const downloadRef = useRef<FileSystem.DownloadResumable | null>(null);

  const installApk = useCallback(async (fileUri: string) => {
    if (Platform.OS !== 'android') {
      if (result.downloadUrl) Linking.openURL(result.downloadUrl).catch(() => {});
      return;
    }
    try {
      const contentUri = await FileSystem.getContentUriAsync(fileUri);
      await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
        data: contentUri,
        flags: 1, // FLAG_GRANT_READ_URI_PERMISSION
        type: 'application/vnd.android.package-archive',
      });
    } catch (e: any) {
      console.log('[Update] Install intent failed:', e.message);
      // Fallback: open in browser
      Linking.openURL(result.downloadUrl).catch(() => {});
    }
  }, [result.downloadUrl]);

  const startDownload = useCallback(async () => {
    if (downloading) return;
    const url = result.downloadUrl;
    if (!url || Platform.OS !== 'android') {
      Linking.openURL(url).catch(() => {});
      return;
    }

    setDownloading(true);
    setProgress(0);
    setStatusText('正在下载…');

    const fileUri = FileSystem.cacheDirectory + 'magnetgoogo-update.apk';

    try {
      // Clean up old file
      const info = await FileSystem.getInfoAsync(fileUri);
      if (info.exists) await FileSystem.deleteAsync(fileUri, { idempotent: true });

      const dl = FileSystem.createDownloadResumable(
        url,
        fileUri,
        {},
        (dp) => {
          if (dp.totalBytesExpectedToWrite > 0) {
            const pct = dp.totalBytesWritten / dp.totalBytesExpectedToWrite;
            setProgress(pct);
            const mb = (dp.totalBytesWritten / 1048576).toFixed(1);
            const totalMb = (dp.totalBytesExpectedToWrite / 1048576).toFixed(1);
            setStatusText(`${mb}MB / ${totalMb}MB`);
          }
        },
      );
      downloadRef.current = dl;

      const result = await dl.downloadAsync();
      if (result?.uri) {
        setStatusText('下载完成，正在安装…');
        setProgress(1);
        await installApk(result.uri);
      }
    } catch (e: any) {
      console.log('[Update] Download failed:', e.message);
      setStatusText('下载失败');
      Alert.alert('下载失败', '请使用浏览器下载安装', [
        { text: '前往下载', onPress: () => Linking.openURL(url).catch(() => {}) },
      ]);
    } finally {
      setDownloading(false);
    }
  }, [result.downloadUrl, downloading, installApk]);

  const openMirror = (url: string) => {
    Linking.openURL(url).catch(() => {});
  };

  return (
    <Modal visible={visible} transparent animationType="fade" statusBarTranslucent>
      <View style={s.overlay}>
        <View style={s.card}>
          <View style={s.iconWrap}>
            <Text style={s.icon}>⬆️</Text>
          </View>
          <Text style={s.title}>需要更新</Text>
          <Text style={s.desc}>
            当前版本过旧，无法继续使用。{'\n'}请更新到最新版本。
          </Text>

          {result.announcement ? (
            <View style={s.announcementBox}>
              <Text style={s.announcementText}>{result.announcement}</Text>
            </View>
          ) : null}

          {downloading ? (
            <View style={s.progressWrap}>
              <View style={s.progressBg}>
                <View style={[s.progressBar, { width: `${Math.round(progress * 100)}%` }]} />
              </View>
              <Text style={s.progressText}>{statusText}</Text>
            </View>
          ) : (
            <TouchableOpacity style={s.primaryBtn} onPress={startDownload} activeOpacity={0.7}>
              <Text style={s.primaryBtnText}>立即更新</Text>
            </TouchableOpacity>
          )}

          {!downloading && result.mirrors.length > 0 && (
            <View style={s.mirrors}>
              <Text style={s.mirrorsLabel}>备用下载：</Text>
              {result.mirrors.map((url, i) => (
                <TouchableOpacity key={i} onPress={() => openMirror(url)}>
                  <Text style={s.mirrorLink}>备用链接 {i + 1}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 24,
    padding: 28,
    width: '100%',
    maxWidth: 340,
    alignItems: 'center',
  },
  iconWrap: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#EEF2FF',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  icon: { fontSize: 28 },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1E293B',
    marginBottom: 8,
  },
  desc: {
    fontSize: 14,
    color: '#64748B',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 20,
  },
  announcementBox: {
    backgroundColor: '#FFF7ED',
    borderRadius: 12,
    padding: 12,
    marginBottom: 20,
    width: '100%',
  },
  announcementText: {
    fontSize: 13,
    color: '#9A3412',
    lineHeight: 18,
  },
  primaryBtn: {
    backgroundColor: '#3B82F6',
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 32,
    width: '100%',
    alignItems: 'center',
  },
  primaryBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  mirrors: {
    marginTop: 16,
    alignItems: 'center',
  },
  mirrorsLabel: {
    fontSize: 12,
    color: '#94A3B8',
    marginBottom: 4,
  },
  mirrorLink: {
    fontSize: 13,
    color: '#3B82F6',
    paddingVertical: 4,
  },
  progressWrap: {
    width: '100%',
    alignItems: 'center',
    marginBottom: 8,
  },
  progressBg: {
    width: '100%',
    height: 8,
    backgroundColor: '#E2E8F0',
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 8,
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#3B82F6',
    borderRadius: 4,
  },
  progressText: {
    fontSize: 13,
    color: '#64748B',
  },
});
