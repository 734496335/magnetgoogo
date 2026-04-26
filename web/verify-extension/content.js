/**
 * Content script — runs on every page after load.
 *
 * 1. Asks background to read ALL cookies (incl. HttpOnly cf_clearance)
 * 2. If search page has detail links but no magnet links, fetches detail
 *    pages using browser's cookies and injects magnet links into DOM
 * 3. Submits cookies + enriched page HTML to /api/verify
 *
 * HTML extraction mirrors Legado's saveVerificationResult():
 * the server can parse search results directly from the HTML
 * without needing cf_clearance for a separate fetch.
 */
(function() {
  if (!location.origin.startsWith('http')) return;
  // Skip localhost / extension pages
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return;

  const API = 'http://localhost:3000/api/verify';

  // Wait for page to fully settle (CF may redirect after Turnstile)
  setTimeout(async () => {
    // Phase 1: Enrich page — fetch detail pages for magnet links if needed
    await enrichMagnets();

    // Phase 2: Ask background for HttpOnly cookies and submit
    try {
      chrome.runtime.sendMessage(
        { type: 'READ_COOKIES', hostname: location.hostname, origin: location.origin },
        (bgResp) => {
          submitPayload(bgResp?.cookies || document.cookie);
        }
      );
    } catch {
      submitPayload(document.cookie);
    }
  }, 3000);

  /**
   * If the page has result items with detail links but NO magnet links,
   * fetch each detail page (browser has CF cookies) and inject magnets.
   * This works for BT4G-style sites where magnets are on detail pages only.
   */
  async function enrichMagnets() {
    // Check if page already has magnet links
    if (document.querySelector('a[href^="magnet:"]')) return;

    // Find detail links (common patterns: /magnet/xxx, /torrent/xxx, /detail/xxx)
    const detailLinks = document.querySelectorAll(
      'a[href*="/magnet/"], a[href*="/torrent/"], a[href*="/detail/"]'
    );
    if (detailLinks.length === 0) return;

    console.log(`[MagnetGoogo] Found ${detailLinks.length} detail links, fetching magnets...`);

    // Limit to first 20 detail pages
    const links = Array.from(detailLinks).slice(0, 20);
    const results = await Promise.allSettled(
      links.map(async (a) => {
        try {
          const url = a.href;
          const resp = await fetch(url, { credentials: 'include' });
          if (!resp.ok) return null;
          const html = await resp.text();
          // Extract magnet link — try multiple patterns:
          // 1. Direct magnet URI: magnet:?xt=urn:btih:HASH
          // 2. URL-encoded: magnet:%3Fxt=urn:btih:HASH (BT4G keepshare links)
          // 3. Hash from downloadtorrentfile.com/hash/HASH
          let magnetUri = null;
          const m1 = html.match(/magnet:\?xt=urn:btih:[^"'\s<]+/);
          if (m1) {
            magnetUri = m1[0];
          } else {
            const m2 = html.match(/magnet:%3Fxt=urn:btih:([a-fA-F0-9]{40})/);
            if (m2) {
              magnetUri = 'magnet:?xt=urn:btih:' + m2[1];
            } else {
              const m3 = html.match(/downloadtorrentfile\.com\/hash\/([a-fA-F0-9]{40})/);
              if (m3) {
                magnetUri = 'magnet:?xt=urn:btih:' + m3[1];
              }
            }
          }
          if (magnetUri) {
            // Inject magnet link into the DOM next to the detail link
            const magnetA = document.createElement('a');
            magnetA.href = magnetUri;
            magnetA.className = 'injected-magnet';
            magnetA.style.display = 'none';
            a.parentElement.appendChild(magnetA);
            console.log(`[MagnetGoogo] ✓ Magnet found for: ${a.title || a.textContent.trim().slice(0, 40)}`);
            return magnetUri;
          }
        } catch {}
        return null;
      })
    );

    const found = results.filter(r => r.status === 'fulfilled' && r.value).length;
    console.log(`[MagnetGoogo] Enriched ${found}/${links.length} results with magnet links`);
  }

  function submitPayload(cookies) {
    const html = document.documentElement.outerHTML;
    const payload = {
      origin: location.origin,
      url: location.href,
      cookies: cookies || document.cookie,
      html: html,
    };
    fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    .then(r => r.json())
    .then(d => {
      if (d.ok) console.log('[MagnetGoogo] ✓ Submitted cookies + HTML (' + Math.round(html.length/1024) + 'KB)');
    })
    .catch(() => {});
  }
})();
