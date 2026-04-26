/**
 * Floating feedback button — anonymous submission via CF Worker KV.
 * No login, no email, just type and submit.
 */
import React, { useState } from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  Modal,
  View,
  TextInput,
  Alert,
  Platform,
  KeyboardAvoidingView,
  ActivityIndicator,
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
  const [sending, setSending] = useState(false);
  const isZh = lang === 'zh';

  const handleSubmit = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSending(true);
    try {
      const resp = await fetch(FEEDBACK_API, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-App-Version': getAppVersion(),
        },
        body: JSON.stringify({
          text: trimmed,
          platform: Platform.OS,
        }),
      });
      const json = await resp.json();
      if (json.ok) {
        Alert.alert(isZh ? '感谢反馈' : 'Thanks!', isZh ? '已收到你的反馈' : 'Your feedback has been submitted.');
        setText('');
        setVisible(false);
      } else {
        Alert.alert(isZh ? '提交失败' : 'Failed', json.error || 'Unknown error');
      }
    } catch (e: any) {
      Alert.alert(isZh ? '网络错误' : 'Network Error', e.message || String(e));
    } finally {
      setSending(false);
    }
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
                disabled={!text.trim() || sending}
                activeOpacity={0.8}
              >
                {sending ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Text style={styles.submitBtnText}>{isZh ? '提交' : 'Submit'}</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
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
});
