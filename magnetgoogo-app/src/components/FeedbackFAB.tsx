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
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLang } from '../core/LangContext';
import { useTheme } from '../core/ThemeContext';
import { getAppVersion } from '../core/configChecker';

const FEEDBACK_API = 'https://maggoogo-gateway.734496335lp.workers.dev/api/feedback';

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

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Close modal immediately — fire and forget
    setText('');
    setVisible(false);
    showToast(isZh ? '反馈提交中…' : 'Submitting…');

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
          showToast(isZh ? '✓ 已收到反馈，感谢！' : '✓ Feedback received, thanks!');
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
      <TouchableOpacity
        style={styles.fab}
        activeOpacity={0.85}
        onPress={() => setVisible(true)}
      >
        <Ionicons name="chatbubble-ellipses-outline" size={16} color="#fff" />
        <Text style={styles.fabLabel}>{t.feedbackBtn}</Text>
      </TouchableOpacity>

      <Modal visible={visible} transparent animationType="slide" onRequestClose={() => setVisible(false)}>
        <KeyboardAvoidingView style={styles.overlay} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={[styles.sheet, { backgroundColor: colors.card }]}>
            <View style={styles.sheetHeader}>
              <Text style={[styles.sheetTitle, { color: colors.text }]}>{isZh ? '意见反馈' : 'Feedback'}</Text>
              <TouchableOpacity onPress={() => setVisible(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Ionicons name="close" size={22} color={colors.textTertiary} />
              </TouchableOpacity>
            </View>
            <Text style={[styles.sheetHint, { color: colors.textTertiary }]}>
              {isZh ? '匿名提交，无需登录。Bug、建议、吐槽都欢迎。' : 'Anonymous. No login required. Bugs, suggestions, anything.'}
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
  fab: {
    position: 'absolute',
    right: 16,
    bottom: 24,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(66,133,244,0.9)',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    shadowColor: '#4285F4',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  fabLabel: {
    fontSize: 12,
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
