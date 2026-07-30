import React, { useState, useCallback, useMemo } from 'react';
import { Modal, View, Text, TouchableOpacity, Linking, StyleSheet, Platform, Alert } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as IntentLauncher from 'expo-intent-launcher';
import type { ConfigCheckResult } from '../core/configChecker';
import { useLang } from '../core/LangContext';
import { getUpdateCopy } from '../core/updateCopy';
import { downloadApkFromCandidates } from '../core/updateDownload';
import {
  buildDirectDownloadCandidates,
  getBrowserFallbacks,
  getEmergencyBrowserFallbacks,
  getUpdateErrorMessage,
  getUpdateMirrorLabel,
  orderUpdateMirrors,
} from '../core/updateDownloadPolicy';

interface Props {
  result: ConfigCheckResult;
  visible: boolean;
}

export default function ForceUpdateModal({ result, visible }: Props) {
  const { lang } = useLang();
  const copy = getUpdateCopy(lang);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const orderedMirrors = useMemo(() => orderUpdateMirrors(result.mirrors), [result.mirrors]);
  const directCandidates = useMemo(
    () => buildDirectDownloadCandidates(result.downloadUrl, orderedMirrors),
    [result.downloadUrl, orderedMirrors],
  );
  const browserFallbacks = useMemo(
    () => getBrowserFallbacks(result.downloadUrl, orderedMirrors),
    [result.downloadUrl, orderedMirrors],
  );
  const emergencyFallbacks = useMemo(
    () => getEmergencyBrowserFallbacks(orderedMirrors),
    [orderedMirrors],
  );

  const openUrl = useCallback((url: string) => {
    if (!url) return;
    Linking.openURL(url).catch((error: unknown) => {
      console.log('[UpdateDownload]', JSON.stringify({
        rule_id: 'app_update_download',
        stage: 'open_browser_failed',
        error_code: 'linking_open_failed',
        url,
        message: getUpdateErrorMessage(error),
      }));
    });
  }, []);

  const installApk = useCallback(async (fileUri: string) => {
    if (Platform.OS !== 'android') {
      openUrl(browserFallbacks[0] || result.downloadUrl);
      return;
    }
    try {
      const contentUri = await FileSystem.getContentUriAsync(fileUri);
      await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
        data: contentUri,
        flags: 1,
        type: 'application/vnd.android.package-archive',
      });
    } catch (error: unknown) {
      console.log('[UpdateDownload]', JSON.stringify({
        rule_id: 'app_update_install',
        stage: 'launch_installer_failed',
        error_code: 'install_intent_failed',
        message: getUpdateErrorMessage(error),
      }));
      openUrl(browserFallbacks[0] || result.downloadUrl);
    }
  }, [browserFallbacks, openUrl, result.downloadUrl]);

  const startDownload = useCallback(async () => {
    if (downloading) return;
    if (Platform.OS !== 'android' || directCandidates.length === 0) {
      openUrl(browserFallbacks[0] || result.downloadUrl);
      return;
    }

    setDownloading(true);
    setProgress(0);
    setStatusText(copy.downloading);

    const fileUri = FileSystem.cacheDirectory + 'magnetgoogo-update.apk';

    try {
      const downloaded = await downloadApkFromCandidates({
        candidates: directCandidates,
        fileUri,
        onAttempt: (_url, index, total) => {
          setProgress(0);
          setStatusText(total > 1 ? `${copy.downloading} (${index + 1}/${total})` : copy.downloading);
        },
        onProgress: ({ bytesWritten, totalBytes, ratio }) => {
          setProgress(ratio);
          if (totalBytes > 0) {
            const mb = (bytesWritten / 1048576).toFixed(1);
            const totalMb = (totalBytes / 1048576).toFixed(1);
            setStatusText(`${mb}MB / ${totalMb}MB`);
          }
        },
      });
      setStatusText(copy.downloadComplete);
      setProgress(1);
      await installApk(downloaded.uri);
    } catch (error: unknown) {
      console.log('[UpdateDownload]', JSON.stringify({
        rule_id: 'app_update_download',
        stage: 'all_candidates_failed',
        error_code: 'all_download_candidates_failed',
        message: getUpdateErrorMessage(error),
      }));
      setStatusText(copy.downloadFailed);
      const buttons = emergencyFallbacks.map((url, index) => ({
        text: getUpdateMirrorLabel(url, lang, index + 1),
        onPress: () => openUrl(url),
      }));
      if (buttons.length === 0) {
        buttons.push({ text: copy.openDownload, onPress: () => openUrl(result.downloadUrl) });
      }
      Alert.alert(copy.downloadFailed, copy.downloadFailedMessage, buttons);
    } finally {
      setDownloading(false);
    }
  }, [
    browserFallbacks,
    copy,
    directCandidates,
    downloading,
    emergencyFallbacks,
    installApk,
    lang,
    openUrl,
    result.downloadUrl,
  ]);

  const announcement = result.config?.announcement_i18n?.[lang] || result.announcement;

  return (
    <Modal visible={visible} transparent animationType="fade" statusBarTranslucent>
      <View style={s.overlay}>
        <View style={s.card}>
          <View style={s.iconWrap}>
            <Text style={s.icon}>⬆️</Text>
          </View>
          <Text style={s.title}>{copy.forceTitle}</Text>
          <Text style={s.desc}>{copy.forceDescription}</Text>

          {announcement ? (
            <View style={s.announcementBox}>
              <Text style={s.announcementText}>{announcement}</Text>
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
              <Text style={s.primaryBtnText}>{copy.updateNow}</Text>
            </TouchableOpacity>
          )}

          {!downloading && orderedMirrors.length > 0 && (
            <View style={s.mirrors}>
              <Text style={s.mirrorsLabel}>{copy.backupDownload}</Text>
              {orderedMirrors.map((url, i) => (
                <TouchableOpacity key={url} onPress={() => openUrl(url)}>
                  <Text style={s.mirrorLink}>{getUpdateMirrorLabel(url, lang, i + 1)}</Text>
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
