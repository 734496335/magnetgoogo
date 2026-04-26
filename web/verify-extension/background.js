/**
 * MagnetGoogo Cookie Bridge Extension
 *
 * Equivalent of Legado's CookieStore.setCookie() / CookieManager.getCookie().
 *
 * When a page finishes loading, reads all cookies for that domain and
 * submits them to the MagnetGoogo /api/verify endpoint. This allows
 * Turnstile/CAPTCHA cookies to flow back to the search server.
 */

const API_BASE = 'http://localhost:3000';

// ---- Message handler: content script asks us to read cookies ----
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'READ_COOKIES' && msg.hostname) {
    readCookies(msg.hostname)
      .then(cookieStr => {
        // Also submit from background (HttpOnly cookies)
        readAndSubmit(msg.origin, msg.hostname);
        sendResponse({ ok: true, cookies: cookieStr });
      })
      .catch(() => sendResponse({ ok: false }));
    return true; // async response
  }
});

async function readCookies(hostname) {
  const cookies = await chrome.cookies.getAll({ domain: hostname });
  return cookies.map(c => `${c.name}=${c.value}`).join('; ');
}

// NOTE: Don't auto-submit on webNavigation.onCompleted — let content.js
// handle it so we get HTML too. Background only fires on explicit request
// from content.js or on cf_clearance cookie changes.

// ---- Watch for cf_clearance cookie appearing ----
chrome.cookies.onChanged.addListener(async (changeInfo) => {
  if (changeInfo.removed) return;
  const c = changeInfo.cookie;
  if (c.name === 'cf_clearance' || c.name === '__cf_bm') {
    const hostname = c.domain.replace(/^\./, '');
    const origin = `https://${hostname}`;
    console.log(`[CookieBridge] Cookie changed: ${c.name} on ${origin}`);
    await readAndSubmit(origin, hostname);
  }
});

// ---- Core: read ALL cookies (including HttpOnly) and submit ----
async function readAndSubmit(origin, hostname) {
  // chrome.cookies.getAll returns HttpOnly cookies too!
  const cookies = await chrome.cookies.getAll({ domain: hostname });
  if (cookies.length === 0) return;

  const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');
  const hasClearance = cookies.some(c => c.name === 'cf_clearance');
  const httpOnlyCount = cookies.filter(c => c.httpOnly).length;

  console.log(
    `[CookieBridge] ${origin} — ${cookies.length} cookies (${httpOnlyCount} HttpOnly)` +
    (hasClearance ? ' [cf_clearance ✓]' : '')
  );

  const resp = await fetch(`${API_BASE}/api/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin, cookies: cookieStr }),
  });

  if (resp.ok) {
    console.log(`[CookieBridge] ✓ Submitted for ${origin}`);
  } else {
    console.log(`[CookieBridge] ✗ HTTP ${resp.status}`);
  }
}

console.log('[CookieBridge] Extension loaded — monitoring cookies + messages');
