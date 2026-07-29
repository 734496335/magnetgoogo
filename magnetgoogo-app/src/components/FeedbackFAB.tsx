/**
 * Floating feedback button — anonymous submission via CF Worker KV.
 * No login, no email, just type and submit.
 *
 * Submit is fire-and-forget: close modal immediately, show toast later.
 */
import React, { useState, useRef } from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  Modal,
  View,
  TextInput,
  Platform,
  KeyboardAvoidingView,
  Animated,
  Easing,
  Share,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLang } from '../core/LangContext';
import { useTheme } from '../core/ThemeContext';
import { getAppVersion } from '../core/configChecker';
import { WEBSITE_URL } from '../core/complianceConfig';
import { buildAppShareMessage } from '../core/appShare';

const FEEDBACK_API = 'https://api.naoshiquan.com/api/feedback';

export default function FeedbackFAB() {
  const { lang, t } = useLang();
  const { colors } = useTheme();
  const [visible, setVisible] = useState(false);
  const [text, setText] = useState('');
  const isZh = lang === 'zh';

  // ── Toast state ──
  const [toastMsg, setToastMsg] = useState('');
  const toastOpacity = useRef(new Animated.Value(0)).current;
  const toastY = useRef(new Animated.Value(30)).current;

  const showToast = (msg: string) => {
    setToastMsg(msg);
    toastOpacity.setValue(0);
    toastY.setValue(30);
    Animated.parallel([
      Animated.timing(toastOpacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      Animated.timing(toastY, { toValue: 0, duration: 200, easing: Easing.out(Easing.quad), useNativeDriver: true }),
    ]).start();
    setTimeout(() => {
      Animated.timing(toastOpacity, { toValue: 0, duration: 300, useNativeDriver: true }).start(() => setToastMsg(''));
    }, 2500);
  };

  const handleShare = async () => {
    try {
      await Share.share(
        {
          title: t.shareDialogTitle,
          message: buildAppShareMessage(t.shareMessage, WEBSITE_URL),
        },
        { dialogTitle: t.shareDialogTitle },
      );
    } catch (error) {
      console.warn('[FeedbackFAB]', {
        stage: 'open_native_share',
        error_code: 'NATIVE_SHARE_FAILED',
        error: error instanceof Error ? error.message : String(error),
      });
      showToast(t.shareFailed);
    }
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Close modal immediately — fire and forget
    setText('');
    setVisible(false);
    showToast(isZh ? '吐槽提交中…' : 'Sending…');

    // Background submit
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15000);
    fetch(FEEDBACK_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-App-Version': getAppVersion(),
      },
      body: JSON.stringify({
        text: trimmed,
        platform: Platform.OS,
        ts: Date.now(),
      }),
      signal: ctrl.signal,
    })
      .then(async (resp) => {
        clearTimeout(timer);
        if (!resp.ok) {
          const body = await resp.text().catch(() => '');
          console.log(`[Feedback] HTTP ${resp.status}: ${body}`);
          showToast(isZh ? '提交失败，稍后再试' : 'Submit failed, try later');
          return;
        }
        const json = await resp.json().catch(() => ({ ok: false }));
        if (json.ok) {
          showToast(isZh ? '✓ 吐槽收到，谢谢！' : '✓ Got it, thanks!');
        } else {
          console.log(`[Feedback] API error:`, json);
          showToast(isZh ? '提交失败' : 'Submit failed');
        }
      })
      .catch((e: any) => {
        clearTimeout(timer);
        console.log(`[Feedback] Network error: ${e.message}`);
        showToast(isZh ? '网络错误，稍后再试' : 'Network error, try later');
      });
  };

  return (
    <>
      <View style={styles.fabRow}>
        <TouchableOpacity
          style={styles.fab}
          activeOpacity={0.85}
          onPress={() => setVisible(true)}
          accessibilityRole="button"
          accessibilityLabel={isZh ? '吐槽' : 'Feedback'}
          testID="home-feedback-button"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={16} color="#fff" />
          <Text style={styles.fabLabel}>{t.feedbackBtn}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.fab}
          activeOpacity={0.85}
          onPress={handleShare}
          accessibilityRole="button"
          accessibilityLabel={t.shareDialogTitle}
          testID="home-share-button"
        >
          <Ionicons name="share-social-outline" size={16} color="#fff" />
          <Text style={styles.fabLabel}>{t.shareBtn}</Text>
        </TouchableOpacity>
      </View>

      <Modal visible={visible} transparent animationType="slide" onRequestClose={() => setVisible(false)}>
        <KeyboardAvoidingView style={styles.overlay} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={[styles.sheet, { backgroundColor: colors.card }]}>
            <View style={styles.sheetHeader}>
              <Text style={[styles.sheetTitle, { color: colors.text }]}>{isZh ? '来吐槽吧' : 'Let it out'}</Text>
              <TouchableOpacity onPress={() => setVisible(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Ionicons name="close" size={22} color={colors.textTertiary} />
              </TouchableOpacity>
            </View>
            <Text style={[styles.sheetHint, { color: colors.textTertiary }]}>
              {isZh ? '匿名提交，无需登录。Bug、建议、吐槽都来吧。' : 'Anonymous. Bugs, complaints, rants — all welcome.'}
            </Text>
            <TextInput
              style={[styles.input, { color: colors.text, backgroundColor: colors.inputBg, borderColor: colors.border || '#e0dcd6' }]}
              placeholder={isZh ? '在这里写下你的反馈...' : 'Write your feedback here...'}
              placeholderTextColor={colors.textTertiary}
              value={text}
              onChangeText={setText}
              multiline
              maxLength={1000}
              autoFocus
            />
            <View style={styles.sheetFooter}>
              <Text style={[styles.charCount, { color: colors.textTertiary }]}>{text.length}/1000</Text>
              <TouchableOpacity
                style={[styles.submitBtn, !text.trim() && styles.submitBtnDisabled]}
                onPress={handleSubmit}
                disabled={!text.trim()}
                activeOpacity={0.8}
              >
                <Text style={styles.submitBtnText}>{isZh ? '提交' : 'Submit'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Lightweight toast */}
      {!!toastMsg && (
        <Animated.View style={[styles.toast, { opacity: toastOpacity, transform: [{ translateY: toastY }] }]} pointerEvents="none">
          <Text style={styles.toastText}>{toastMsg}</Text>
        </Animated.View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  fabRow: {
    position: 'absolute',
    right: 16,
    bottom: 24,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  fab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(66,133,244,0.75)',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
    shadowColor: '#4285F4',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  },
  fabLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#fff',
  },
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  sheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: 36,
  },
  sheetHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  sheetTitle: {
    fontSize: 17,
    fontWeight: '700',
  },
  sheetHint: {
    fontSize: 12,
    marginBottom: 12,
  },
  input: {
    borderWidth: 1,
    borderColor: '#e0dcd6',
    borderRadius: 12,
    padding: 12,
    fontSize: 15,
    minHeight: 120,
    textAlignVertical: 'top',
  },
  sheetFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
  },
  charCount: {
    fontSize: 12,
  },
  submitBtn: {
    backgroundColor: '#4285F4',
    borderRadius: 20,
    paddingHorizontal: 24,
    paddingVertical: 10,
    minWidth: 80,
    alignItems: 'center',
  },
  submitBtnDisabled: {
    opacity: 0.4,
  },
  submitBtnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 14,
  },
  toast: {
    position: 'absolute',
    bottom: 80,
    left: 24,
    right: 24,
    backgroundColor: 'rgba(30,30,30,0.92)',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  toastText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
});
