/**
 * VerifyWebView — 3-tier verification WebView.
 *
 * Silent mode (Tier 1):
 *   WebView renders off-screen. If CF JS challenge auto-resolves within
 *   SILENT_TIMEOUT, cookies are extracted silently — user sees nothing.
 *
 * Interactive mode (Tier 2):
 *   If silent doesn't resolve in time, the WebView escalates to a
 *   full-screen overlay so the user can manually complete CAPTCHA/Turnstile.
 *
 * Uses a View (not Modal) so the WebView stays mounted during escalation.
 */
import React, { useRef, useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  VerifyManager,
  type VerifyRequest,
  type VerifyResult,
} from '../core/VerifyManager';
import { getStoredCookies } from '../core/httpClient';

const SILENT_TIMEOUT = 10_000; // 10s before escalating to interactive
const HTTP_403_MAX = 2; // auto-cancel after N consecutive 403s

const INJECTED_BEFORE = `
(function() {
  // Ensure DOM has standard viewport metadata
  var existing = document.querySelectorAll('meta[name="viewport"]');
  for (var i = 0; i < existing.length; i++) existing[i].remove();

  var meta = document.createElement('meta');
  meta.name = 'viewport';
  meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes';
  document.head.appendChild(meta);

  // After DOM ready, scroll the challenge widget into view for easy interaction
  function scrollChallengeIntoView() {
    var selectors = [
      'iframe[src*="challenges.cloudflare"]',
      '.cf-turnstile', '.h-captcha', '.g-recaptcha',
      '[class*="captcha"]', '#challenge-form',
      '#turnstile-wrapper', '.challenge-running',
    ];
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
    }
  }
  // Try scrolling at multiple intervals since challenge may load async
  setTimeout(scrollChallengeIntoView, 1000);
  setTimeout(scrollChallengeIntoView, 2500);
  setTimeout(scrollChallengeIntoView, 5000);
})();
true;
`;

// ── JS injected into WebView (generated per request type) ────────────
function buildInjectedJS(type: string): string {
  const isSPA = type === 'spa_render';
  // SPA: wait at least 5s, check for actual search results
  // Challenge: wait for CF/captcha to resolve, then extract immediately
  const MIN_SPA_WAIT = 5000;
  const SPA_MAX_WAIT = 20000; // 20s max for SPA rendering
  const CHALLENGE_MAX_WAIT = 120000;
  return `
(function() {
  if (window.__VERIFY_INJECTED__) return;
  window.__VERIFY_INJECTED__ = true;

  var CHECK_INTERVAL = 800;
  var IS_SPA = ${isSPA};
  var MAX_WAIT = IS_SPA ? ${SPA_MAX_WAIT} : ${CHALLENGE_MAX_WAIT};
  var MIN_WAIT = IS_SPA ? ${MIN_SPA_WAIT} : 0;
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

  // DOM stability tracking via MutationObserver (CloakBrowser approach)
  var lastMutationTime = Date.now();
  var mutationCount = 0;
  var DOM_STABLE_MS = 1500; // consider stable after 1.5s without mutations
  try {
    var observer = new MutationObserver(function(mutations) {
      lastMutationTime = Date.now();
      mutationCount += mutations.length;
    });
    observer.observe(document.documentElement, {
      childList: true, subtree: true, attributes: false
    });
  } catch(e) {}

  function hasSPAContent() {
    // Instant success: magnet links found
    var links = document.querySelectorAll('a[href*="magnet:"]');
    if (links.length > 0) return true;

    // DOM must be stable (no mutations for DOM_STABLE_MS)
    var sinceLastMutation = Date.now() - lastMutationTime;
    if (sinceLastMutation < DOM_STABLE_MS && mutationCount < 500) return false;

    // After DOM is stable, check for actual content
    var allLinks = document.querySelectorAll('a[href]');
    var body = document.body;
    var text = (body && body.innerText) || '';
    // Substantial content: many links + text, or just a lot of text
    if (allLinks.length > 10 && text.length > 300) return true;
    if (text.length > 1000) return true;
    return false;
  }

  function checkChallenge() {
    if (sent) return;
    var elapsed = Date.now() - startTime;
    if (elapsed > MAX_WAIT) {
      extractAndSend();
      return;
    }

    // Always wait minimum time for SPA
    if (IS_SPA && elapsed < MIN_WAIT) {
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    var hasCF = !!window._cf_chl_opt;
    var hasTurnstile = !!document.querySelector('iframe[src*="challenges.cloudflare"]');
    var hasJSChallenge = document.title === 'Just a moment...' ||
                         !!document.querySelector('#cf-browser-verification');

    if (hasCF || hasTurnstile || hasJSChallenge) {
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    if (document.body && document.body.innerHTML.includes('DDoS-Guard')) {
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    var hasCaptcha = !!document.querySelector('[class*="captcha"], [id*="captcha"], .g-recaptcha, .h-captcha');
    if (hasCaptcha) {
      setTimeout(checkChallenge, CHECK_INTERVAL);
      return;
    }

    // SPA mode: wait for actual rendered content
    if (IS_SPA) {
      if (hasSPAContent()) {
        extractAndSend();
      } else {
        setTimeout(checkChallenge, CHECK_INTERVAL);
      }
      return;
    }

    // Challenge mode: check for basic content
    var body = document.body;
    if (body) {
      var text = body.innerText || '';
      var links = document.querySelectorAll('a[href*="magnet:"]');
      var hasContent = text.length > 200 || links.length > 0;
      if (!hasContent && text.length < 100) {
        if (elapsed < 10000) {
          setTimeout(checkChallenge, CHECK_INTERVAL);
          return;
        }
      }
    }

    extractAndSend();
  }

  setTimeout(checkChallenge, IS_SPA ? 2000 : 1500);
  window.__VERIFY_FORCE_EXTRACT__ = extractAndSend;
})();
true;
`;
}

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
  const [silent, setSilent] = useState(true);
  const escalateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const httpErrorCount = useRef(0);
  const isCloudflareChallenge = useRef(false);
  const requestRef = useRef(request);
  requestRef.current = request;

  const typeLabels: Record<string, string> = {
    cloudflare: '☁️ Cloudflare 验证',
    cloudflare_block: '🛡️ Cloudflare 拦截',
    captcha: '🔑 人机验证',
    ddos_guard: '🛡️ DDoS-Guard 验证',
    spa_render: '⏳ 页面渲染中...',
  };

  // Reset state and start silent timer when a new request arrives
  useEffect(() => {
    if (request) {
      setSilent(true);
      setLoading(true);
      httpErrorCount.current = 0;
      setCurrentUrl(request.url);
      setStatusText(
        request.type === 'spa_render'
          ? '正在渲染页面，请稍候...'
          : '请在下方完成验证，完成后将自动继续搜索'
      );
      console.log(`[VerifyWebView] Starting silent verification for ${request.siteName}`);

      // Start escalation timer
      if (escalateTimer.current) clearTimeout(escalateTimer.current);
      escalateTimer.current = setTimeout(() => {
        if (requestRef.current) {
          console.log(`[VerifyWebView] Silent timeout → escalating to interactive for ${requestRef.current.siteName}`);
          setSilent(false);
        }
      }, SILENT_TIMEOUT);
    }
    return () => {
      if (escalateTimer.current) {
        clearTimeout(escalateTimer.current);
        escalateTimer.current = null;
      }
    };
  }, [request]);

  const handleMessage = useCallback(
    (event: WebViewMessageEvent) => {
      const req = requestRef.current;
      if (!req) return;
      try {
        const data = JSON.parse(event.nativeEvent.data);
        if (data.type === 'cf_probe') {
          console.log(`[VerifyWebView] cf_probe: isCF=${data.isCF} previousIsCF=${isCloudflareChallenge.current}`);
          if (data.isCF) {
            isCloudflareChallenge.current = true;
          } else if (isCloudflareChallenge.current) {
            console.log(`[VerifyWebView] CF challenge resolved automatically via state transition!`);
            isCloudflareChallenge.current = false;
            if (escalateTimer.current) {
              clearTimeout(escalateTimer.current);
              escalateTimer.current = null;
            }
            const wasSilent = silent;
            const result: VerifyResult = {
              success: true,
              cookies: data.cookies || '',
              html: data.html || '',
            };
            VerifyManager.submitResult(req.id, result, req.origin, wasSilent);
            onDismiss();
          }
          return;
        }
        if (data.type === 'verify_result') {
          // Clear escalation timer
          if (escalateTimer.current) {
            clearTimeout(escalateTimer.current);
            escalateTimer.current = null;
          }
          const wasSilent = silent;
          const result: VerifyResult = {
            success: true,
            cookies: data.cookies || '',
            html: data.html || '',
          };
          console.log(`[VerifyWebView] Verification complete for ${req.siteName} (silent=${wasSilent})`);
          VerifyManager.submitResult(req.id, result, req.origin, wasSilent);
          onDismiss();
        }
      } catch {
        // Ignore non-JSON messages
      }
    },
    [silent, onDismiss],
  );

  const handleCancel = useCallback(() => {
    if (escalateTimer.current) {
      clearTimeout(escalateTimer.current);
      escalateTimer.current = null;
    }
    const req = requestRef.current;
    if (req) {
      VerifyManager.cancel(req.id, req.origin);
    }
    onDismiss();
  }, [onDismiss]);

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
    const fatal = code < 0 || /abort|refused|reset|timeout|unreachable|not_resolved/i.test(desc);
    if (fatal) {
      if (escalateTimer.current) {
        clearTimeout(escalateTimer.current);
        escalateTimer.current = null;
      }
      const req = requestRef.current;
      if (req) {
        if (!silent) {
          setStatusText(desc.includes('ABORT') || desc.includes('REFUSED')
            ? '该站点无法访问（可能被网络封锁）'
            : `加载失败: ${desc.slice(0, 60)}`);
        }
        setTimeout(() => {
          VerifyManager.cancel(req.id, req.origin);
          onDismiss();
        }, silent ? 0 : 2000);
      }
    }
  }, [silent, onDismiss]);

  if (!request) return null;

  // Silent mode: render WebView off-screen (invisible to user)
  // Interactive mode: render as full-screen overlay
  return (
    <View
      style={silent ? styles.silentContainer : [styles.interactiveContainer, { paddingTop: insets.top }]}
      pointerEvents={silent ? 'none' : 'auto'}
    >
      {/* Header — only in interactive mode */}
      {!silent && (
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
      )}

      {/* Status bar — only in interactive mode */}
      {!silent && (
        <View style={styles.statusBar}>
          {loading && <ActivityIndicator size="small" color="#4285F4" />}
          <Text style={styles.statusText} numberOfLines={1}>
            {statusText}
          </Text>
        </View>
      )}

      {/* WebView — always mounted */}
      <WebView
        ref={webViewRef}
        source={{
          uri: request.url,
          headers: {
            Cookie: getStoredCookies(request.origin),
          }
        }}
        style={styles.webview}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        thirdPartyCookiesEnabled={true}
        sharedCookiesEnabled={true}
        scalesPageToFit={true}
        setBuiltInZoomControls={true}
        setDisplayZoomControls={false}
        forceDarkOn={false}
        textZoom={100}
        injectedJavaScriptBeforeContentLoaded={INJECTED_BEFORE}
        userAgent="Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        injectedJavaScript={buildInjectedJS(request.type)}
        onMessage={handleMessage}
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => {
          setLoading(false);
          // Evaluate Cloudflare challenge state like legado
          webViewRef.current?.injectJavaScript(`
            (function() {
              // 1. Re-inject viewport fix
              var existing = document.querySelectorAll('meta[name="viewport"]');
              for (var i = 0; i < existing.length; i++) existing[i].remove();
              var meta = document.createElement('meta');
              meta.name = 'viewport';
              meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes';
              document.head.appendChild(meta);

              // 2. Scroll challenge widget into view
              var sels = ['iframe[src*="challenges.cloudflare"]','.cf-turnstile','.h-captcha','.g-recaptcha','[class*="captcha"]','#challenge-form'];
              for (var i = 0; i < sels.length; i++) {
                var el = document.querySelector(sels[i]);
                if (el) { el.scrollIntoView({ behavior:'smooth', block:'center' }); break; }
              }

              // 3. CF challenge transition probe
              var isCF = !!window._cf_chl_opt;
              window.ReactNativeWebView.postMessage(JSON.stringify({
                type: 'cf_probe',
                isCF: isCF,
                url: window.location.href,
                cookies: document.cookie || '',
                html: document.documentElement.outerHTML || ''
              }));
            })(); true;
          `);
        }}
        onNavigationStateChange={(nav) => setCurrentUrl(nav.url)}
        onError={handleWebViewError}
        onHttpError={(syntheticEvent) => {
          const { nativeEvent } = syntheticEvent;
          console.log(`[VerifyWebView] HTTP error: ${nativeEvent.statusCode} ${nativeEvent.url}`);
          if (nativeEvent.statusCode === 403) {
            httpErrorCount.current++;
            if (httpErrorCount.current >= HTTP_403_MAX) {
              console.log(`[VerifyWebView] ${HTTP_403_MAX}+ consecutive 403 → auto-cancelling ${requestRef.current?.siteName}`);
              const req = requestRef.current;
              if (req) {
                if (escalateTimer.current) {
                  clearTimeout(escalateTimer.current);
                  escalateTimer.current = null;
                }
                VerifyManager.cancel(req.id, req.origin);
                onDismiss();
              }
            }
          }
        }}
        onShouldStartLoadWithRequest={() => true}
      />

      {/* URL bar — only in interactive mode */}
      {!silent && (
        <View style={[styles.urlBar, { paddingBottom: insets.bottom + 4 }]}>
          <Text style={styles.urlText} numberOfLines={1}>
            🔒 {currentUrl}
          </Text>
        </View>
      )}
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  silentContainer: {
    position: 'absolute',
    left: -10000,
    top: -10000,
    width: 375,
    height: 812,
    opacity: 0,
  },
  interactiveContainer: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 999,
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
