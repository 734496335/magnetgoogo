(() => {
  'use strict';

  if (window.__mgGrowthAttributionLoaded) return;
  window.__mgGrowthAttributionLoaded = true;

  const script = document.currentScript;
  const explicitPage = String(script?.dataset?.growthPage || '').trim();
  const page = explicitPage || window.location.pathname || '/';
  const locale = document.documentElement.lang || 'unknown';

  const CAMPAIGN_SOURCE_ALLOWLIST = new Map([
    ['chatgpt.com', 'chatgpt'], ['chatgpt', 'chatgpt'],
    ['perplexity', 'perplexity'], ['copilot', 'copilot'], ['gemini', 'gemini'], ['claude', 'claude'],
    ['naoshiquan', 'naoshiquan'], ['github', 'github'], ['reddit', 'reddit'], ['zhihu', 'zhihu'],
    ['v2ex', 'v2ex'], ['coolapk', 'coolapk'], ['52pojie', '52pojie'], ['bilibili', 'bilibili'],
    ['telegram', 'telegram'], ['producthunt', 'producthunt'], ['uptodown', 'uptodown'], ['alternativeto', 'alternativeto'], ['x', 'x'], ['twitter', 'x'], ['youtube', 'youtube'],
  ]);

  function campaignSource(search) {
    let value = '';
    try {
      value = String(new URLSearchParams(String(search || '')).get('utm_source') || '').trim().toLowerCase();
    } catch {
      return '';
    }
    return CAMPAIGN_SOURCE_ALLOWLIST.get(value) || '';
  }

  function acquisitionSource(referrer, search) {
    // Some AI-search products intentionally append a source marker while the
    // browser may omit Referer. Collapse only a small allowlist to a category;
    // never send the raw URL, query string or campaign value to analytics.
    const campaign = campaignSource(search);
    if (campaign) return campaign;

    const raw = String(referrer || '').trim();
    if (!raw) return 'direct';

    let host;
    try {
      host = new URL(raw).hostname.toLowerCase().replace(/^www\./, '');
    } catch {
      return 'unknown';
    }

    const ownHost = window.location.hostname.toLowerCase().replace(/^www\./, '');
    if (host === ownHost) return 'internal';
    if (host === 'chatgpt.com' || host.endsWith('.chatgpt.com') || host === 'chat.openai.com') return 'chatgpt';
    if (host === 'perplexity.ai' || host.endsWith('.perplexity.ai')) return 'perplexity';
    if (host === 'copilot.microsoft.com' || host.endsWith('.copilot.microsoft.com') || host === 'copilot.microsoft365.com') return 'copilot';
    if (host === 'gemini.google.com') return 'gemini';
    if (host === 'claude.ai' || host.endsWith('.claude.ai')) return 'claude';
    if (host === 'naoshiquan.com' || host.endsWith('.naoshiquan.com')) return 'naoshiquan';
    if (host === 'github.com' || host.endsWith('.github.com')) return 'github';
    if (host === 'reddit.com' || host.endsWith('.reddit.com')) return 'reddit';
    if (host === 'zhihu.com' || host.endsWith('.zhihu.com')) return 'zhihu';
    if (host === 'v2ex.com' || host.endsWith('.v2ex.com')) return 'v2ex';
    if (host === 'coolapk.com' || host.endsWith('.coolapk.com')) return 'coolapk';
    if (host === '52pojie.cn' || host.endsWith('.52pojie.cn')) return '52pojie';
    if (host === 'bilibili.com' || host.endsWith('.bilibili.com') || host === 'b23.tv') return 'bilibili';
    if (host === 't.me' || host === 'telegram.me' || host.endsWith('.telegram.me')) return 'telegram';
    if (host === 'producthunt.com' || host.endsWith('.producthunt.com')) return 'producthunt';
    if (host === 'uptodown.com' || host.endsWith('.uptodown.com')) return 'uptodown';
    if (host === 'alternativeto.net' || host.endsWith('.alternativeto.net')) return 'alternativeto';
    if (host === 'x.com' || host.endsWith('.x.com') || host === 'twitter.com' || host.endsWith('.twitter.com')) return 'x';
    if (host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtu.be') return 'youtube';
    if (host === 'baidu.com' || host.endsWith('.baidu.com')) return 'baidu';
    if (host === 'bing.com' || host.endsWith('.bing.com')) return 'bing';
    if (host === 'sogou.com' || host.endsWith('.sogou.com')) return 'sogou';
    if (host === 'so.com' || host.endsWith('.so.com')) return '360';
    if (host === 'sm.cn' || host.endsWith('.sm.cn')) return 'shenma';
    if (host === 'google.com' || host.startsWith('google.') || host.includes('.google.')) return 'google';
    if (host === 'duckduckgo.com' || host.endsWith('.duckduckgo.com')) return 'duckduckgo';
    if (host === 'search.brave.com' || host.endsWith('.search.brave.com')) return 'brave';
    if (host === 'ecosia.org' || host.endsWith('.ecosia.org')) return 'ecosia';
    if (host === 'yahoo.com' || host.startsWith('search.yahoo.') || host.includes('.yahoo.')) return 'yahoo';
    if (host === 'yandex.com' || host === 'yandex.ru' || host.startsWith('yandex.') || host.includes('.yandex.')) return 'yandex';
    return 'referral';
  }

  const source = acquisitionSource(document.referrer, window.location.search);
  const SESSION_SOURCE_KEY = 'mg_acq_source_v1';

  function conversionSource(currentSource) {
    let existing = '';
    try { existing = String(window.sessionStorage?.getItem(SESSION_SOURCE_KEY) || '').trim().toLowerCase(); } catch { /* storage unavailable */ }
    const existingAllowed = [...CAMPAIGN_SOURCE_ALLOWLIST.values(), 'direct', 'google', 'baidu', 'bing', 'sogou', '360', 'shenma', 'yahoo', 'yandex', 'duckduckgo', 'brave', 'ecosia', 'referral', 'unknown'].includes(existing)
      ? existing
      : '';
    let chosen = currentSource;
    if (currentSource === 'internal' && existingAllowed) chosen = existingAllowed;
    try {
      if (currentSource !== 'internal' || !existingAllowed) window.sessionStorage?.setItem(SESSION_SOURCE_KEY, chosen);
    } catch { /* storage unavailable */ }
    return chosen || 'unknown';
  }

  const clickSource = conversionSource(source);

  function tagDownloadLink(link) {
    if (!link?.href) return;
    let target;
    try { target = new URL(link.href, window.location.href); } catch { return; }
    if (target.hostname !== 'api.naoshiquan.com' || target.pathname !== '/go/download') return;
    target.searchParams.set('source', clickSource);
    link.href = target.toString();
  }

  function trackBackupDownload(link) {
    const mirror = String(link?.dataset?.backupDownload || '').trim().toLowerCase();
    if (!['github', 'lanzou'].includes(mirror)) return;
    const tracker = new URL('https://api.naoshiquan.com/go/download');
    tracker.searchParams.set('page', page);
    tracker.searchParams.set('locale', locale);
    tracker.searchParams.set('placement', `backup_${mirror}`);
    tracker.searchParams.set('source', clickSource);
    fetch(tracker.toString(), {
      method: 'GET',
      redirect: 'manual',
      keepalive: true,
      credentials: 'omit',
      referrerPolicy: 'strict-origin-when-cross-origin',
    }).catch(() => {});
  }

  document.querySelectorAll('a[href*="api.naoshiquan.com/go/download"]').forEach(tagDownloadLink);
  document.addEventListener('click', (event) => {
    const link = event.target?.closest?.('a[href]');
    if (!link) return;
    tagDownloadLink(link);
    trackBackupDownload(link);
  }, { capture: true, passive: true });

  let sent = false;

  function send() {
    if (sent || document.visibilityState !== 'visible') return;
    sent = true;
    window.__mgGrowthLandingViewSent = true;
    fetch('https://api.naoshiquan.com/api/growth/view', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, locale, source }),
      keepalive: true,
      credentials: 'omit',
      referrerPolicy: 'strict-origin-when-cross-origin',
    }).catch(() => {});
  }

  const timer = window.setTimeout(send, 1500);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !sent) {
      window.clearTimeout(timer);
      window.setTimeout(send, 800);
    }
  }, { passive: true });
})();
