import React from 'react';
import { Modal, View, Text, TouchableOpacity, Linking, StyleSheet } from 'react-native';
import type { ConfigCheckResult } from '../core/configChecker';

interface Props {
  result: ConfigCheckResult;
  visible: boolean;
}

export default function ForceUpdateModal({ result, visible }: Props) {
  const openDownload = () => {
    const url = result.downloadUrl;
    if (url) Linking.openURL(url).catch(() => {});
  };

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

          <TouchableOpacity style={s.primaryBtn} onPress={openDownload} activeOpacity={0.7}>
            <Text style={s.primaryBtnText}>前往下载</Text>
          </TouchableOpacity>

          {result.mirrors.length > 0 && (
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
});
