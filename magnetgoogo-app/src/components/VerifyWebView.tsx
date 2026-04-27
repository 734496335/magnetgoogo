/**
 * VerifyWebView — Modal WebView for solving challenges.
 *
 * Equivalent to Legado's WebViewActivity:
 *   - Loads the challenge URL in a real WebView (system browser engine)
 *   - User sees and interacts with CF Turnstile / CAPTCHA / etc.
 *   - After challenge solved, injectedJS extracts:
 *     a) All cookies via document.cookie
 *     b) Rendered page HTML via document.documentElement.outerHTML
 *   - Sends result back via VerifyManager.submitResult()
 *
 * For SPA rendering:
 *   - Loads the search URL, waits for JS to render
 *   - Extracts the rendered HTML for cheerio parsing
 *
 * CF detection (same as Legado):
 *   - Checks window._cf_chl_opt to detect active Cloudflare challenge
 *   - When challenge disappears, extraction is triggered
 */
import React, { useRef, useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Modal,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  VerifyManager,
  type VerifyRequest,
  type VerifyResult,
} from '../core/VerifyManager';

// ── JS injected into WebView ──────────────────────────────────────────
// Runs after every page load. Polls for challenge completion.
const INJECTED_JS = `
(function() {
  // Already injected?
  if (window.__VERIFY_INJECTED__) return;
  window.__VERIFY_INJECTED__ = true;

  var CHECK_INTERVAL = 800;
  var MAX_WAIT = 120000;
  var startTime = Date.now();
  var sent = false;

  function extractAndSend() {
    if (sent) return;
    sent = true;
    var cookies = document.cookie || '';
    var html = document.documentElement.outerHTML || '';
    window.ReactNativeWebView.postMessage(JSON.stringify({
      type: 'verify_result',
      cookies: cookies,
      html: html,
      url: window.location.href,
      title: document.title
    }));
  }

  function checkChallenge() {
    if (sent) return;
    if (Date.now() - startTime > MAX_WAIT) {
      extractAndSend();
      return;
    }

    // CF challenge detection (same as Legado: !!window._cf_chl_opt)
    var hasCF = !!window._cf_chl_opt;
    var hasTurnstile = !!document.querySelector('iframe[src*="challenges.cloudflare"]');
    var hasJSChallenge = document.title === 'Just a moment...' ||
                         !!document.querySelector('#cf-browser-verification');

    if (hasCF || hasTurnstile || hasJSChallenge) {
      // Challenge still active — keep waiting
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    // DDoS-Guard check
    if (document.body && document.body.innerHTML.includes('DDoS-Guard')) {
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    // CAPTCHA check (user must solve manually)
    var hasCaptcha = !!document.querySelector('[class*="captcha"], [id*="captcha"], .g-recaptcha, .h-captcha');
    if (hasCaptcha) {
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    // SPA rendering check: wait for meaningful content
    var body = document.body;
    if (body) {
      var text = body.innerText || '';
      var links = document.querySelectorAll('a[href*="magnet:"]');
      var hasContent = text.length > 200 || links.length > 0;
      // For SPA: if body is mostly empty scripts, wait
      if (!hasContent && text.length < 100) {
        if (Date.now() - startTime < 10000) {
          setTimeout(checkChallenge, CHECK_INTERVAL);
          return;
        }
      }
    }

    // No active challenge detected — extract
    extractAndSend();
  }

  // Start polling after a short delay (let page init)
  setTimeout(checkChallenge, 1500);

  // Also listen for manual "done" button press
  window.__VERIFY_FORCE_EXTRACT__ = extractAndSend;
})();
true;
`;

// ── Component ─────────────────────────────────────────────────────────

interface Props {
  request: VerifyRequest | null;
  onDismiss: () => void;
}

export default function VerifyWebView({ request, onDismiss }: Props) {
  const insets = useSafeAreaInsets();
  const webViewRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [currentUrl, setCurrentUrl] = useState('');
  const [statusText, setStatusText] = useState('');

  // Type-specific labels
  const typeLabels: Record<string, string> = {
    cloudflare: '☁️ Cloudflare 验证',
    cloudflare_block: '🛡️ Cloudflare 拦截',
    captcha: '🔑 人机验证',
    ddos_guard: '🛡️ DDoS-Guard 验证',
    spa_render: '⏳ 页面渲染中...',
  };

  useEffect(() => {
    if (request) {
      setLoading(true);
      setCurrentUrl(request.url);
      setStatusText(
        request.type === 'spa_render'
          ? '正在渲染页面，请稍候...'
          : '请在下方完成验证，完成后将自动继续搜索'
      );
    }
  }, [request]);

  const handleMessage = useCallback(
    (event: WebViewMessageEvent) => {
      if (!request) return;
      try {
        const data = JSON.parse(event.nativeEvent.data);
        if (data.type === 'verify_result') {
          const result: VerifyResult = {
            success: true,
            cookies: data.cookies || '',
            html: data.html || '',
          };
          VerifyManager.submitResult(request.id, result, request.origin);
          onDismiss();
        }
      } catch {
        // Ignore non-JSON messages
      }
    },
    [request, onDismiss],
  );

  const handleCancel = useCallback(() => {
    if (request) {
      VerifyManager.cancel(request.id);
    }
    onDismiss();
  }, [request, onDismiss]);

  const handleForceExtract = useCallback(() => {
    webViewRef.current?.injectJavaScript(
      'if(window.__VERIFY_FORCE_EXTRACT__) window.__VERIFY_FORCE_EXTRACT__(); true;'
    );
  }, []);

  const handleWebViewError = useCallback((syntheticEvent: any) => {
    const { nativeEvent } = syntheticEvent;
    const code = nativeEvent?.code ?? nativeEvent?.errorCode ?? 0;
    const desc = nativeEvent?.description || nativeEvent?.error || '';
    console.log(`[VerifyWebView] Load error: code=${code} desc=${desc}`);
    // Network-level failures (GFW block, DNS, timeout) — auto-dismiss
    // Error codes: -6 = ERR_CONNECTION_ABORTED, -2 = ERR_NAME_NOT_RESOLVED,
    // -7 = ERR_TIMED_OUT, -8 = ERR_CONNECTION_TIMED_OUT, -109 = ERR_ADDRESS_UNREACHABLE
    const fatal = code < 0 || /abort|refused|reset|timeout|unreachable|not_resolved/i.test(desc);
    if (fatal && request) {
      setStatusText(desc.includes('ABORT') || desc.includes('REFUSED')
        ? '该站点无法访问（可能被网络封锁）'
        : `加载失败: ${desc.slice(0, 60)}`);
      // Auto-cancel after 2s so user sees the message
      setTimeout(() => {
        if (request) {
          VerifyManager.cancel(request.id);
          onDismiss();
        }
      }, 2000);
    }
  }, [request, onDismiss]);

  if (!request) return null;

  return (
    <Modal
      visible={!!request}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={handleCancel}
    >
      <View style={[styles.container, { paddingTop: insets.top }]}>
        {/* Header bar */}
        <View style={styles.header}>
          <TouchableOpacity onPress={handleCancel} style={styles.headerBtn}>
            <Text style={styles.cancelText}>✕ 取消</Text>
          </TouchableOpacity>

          <View style={styles.headerCenter}>
            <Text style={styles.siteLabel} numberOfLines={1}>
              {request.siteName}
            </Text>
            <Text style={styles.typeLabel}>
              {typeLabels[request.type] || '验证'}
            </Text>
          </View>

          <TouchableOpacity onPress={handleForceExtract} style={styles.headerBtn}>
            <Text style={styles.doneText}>完成 ✓</Text>
          </TouchableOpacity>
        </View>

        {/* Status bar */}
        <View style={styles.statusBar}>
          {loading && <ActivityIndicator size="small" color="#4285F4" />}
          <Text style={styles.statusText} numberOfLines={1}>
            {statusText}
          </Text>
        </View>

        {/* WebView */}
        <WebView
          ref={webViewRef}
          source={{ uri: request.url }}
          style={styles.webview}
          javaScriptEnabled={true}
          domStorageEnabled={true}
          thirdPartyCookiesEnabled={true}
          sharedCookiesEnabled={true}
          userAgent="Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
          injectedJavaScript={INJECTED_JS}
          onMessage={handleMessage}
          onLoadStart={() => setLoading(true)}
          onLoadEnd={() => setLoading(false)}
          onNavigationStateChange={(nav) => {
            setCurrentUrl(nav.url);
          }}
          onError={handleWebViewError}
          onHttpError={(syntheticEvent) => {
            const { nativeEvent } = syntheticEvent;
            console.log(`[VerifyWebView] HTTP error: ${nativeEvent.statusCode} ${nativeEvent.url}`);
          }}
          // Important: allow all navigation (challenge may redirect)
          onShouldStartLoadWithRequest={() => true}
        />

        {/* URL indicator */}
        <View style={[styles.urlBar, { paddingBottom: insets.bottom + 4 }]}>
          <Text style={styles.urlText} numberOfLines={1}>
            🔒 {currentUrl}
          </Text>
        </View>
      </View>
    </Modal>
  );
}

// ── Styles ────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e0e0e0',
    backgroundColor: '#f8f8f8',
  },
  headerBtn: {
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
    marginHorizontal: 8,
  },
  siteLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: '#333',
  },
  typeLabel: {
    fontSize: 12,
    color: '#888',
    marginTop: 1,
  },
  cancelText: {
    fontSize: 14,
    color: '#999',
    fontWeight: '600',
  },
  doneText: {
    fontSize: 14,
    color: '#4285F4',
    fontWeight: '700',
  },
  statusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 6,
    backgroundColor: '#FFF8E1',
    gap: 8,
  },
  statusText: {
    fontSize: 12,
    color: '#6d4c00',
    flex: 1,
  },
  webview: {
    flex: 1,
  },
  urlBar: {
    paddingHorizontal: 16,
    paddingTop: 6,
    backgroundColor: '#f8f8f8',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#e0e0e0',
  },
  urlText: {
    fontSize: 11,
    color: '#aaa',
  },
});
