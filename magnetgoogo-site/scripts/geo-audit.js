const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');

const SITE = path.resolve(__dirname, '..');
const trackerPath = path.join(SITE, 'js', 'growth-attribution.js');
const trackerSource = fs.readFileSync(trackerPath, 'utf8');
const robots = fs.readFileSync(path.join(SITE, 'robots.txt'), 'utf8');
const home = fs.readFileSync(path.join(SITE, 'index.html'), 'utf8').replace(/^\uFEFF/, '');
const about = fs.readFileSync(path.join(SITE, 'about.html'), 'utf8').replace(/^\uFEFF/, '');
const sitemap = fs.readFileSync(path.join(SITE, 'sitemap.xml'), 'utf8');

function runTracker({ referrer = '', search = '', hostname = 'magnetgoogo.com', pathname = '/about', growthPage = 'about', downloadHref = '', backupDownload = '' }) {
  const requests = [];
  const storage = new Map();
  const clickHandlers = [];
  const links = downloadHref ? [{ href: downloadHref }] : [];
  const backupLink = backupDownload ? {
    href: backupDownload === 'github' ? 'https://github.com/734496335/magnetgoogo/releases/latest' : 'https://wwbdy.lanzn.com/irjy846y787c',
    dataset: { backupDownload },
  } : null;
  const href = `https://${hostname}${pathname}${search}`;
  const window = {
    location: { hostname, pathname, search, href },
    sessionStorage: {
      getItem(key) { return storage.has(key) ? storage.get(key) : null; },
      setItem(key, value) { storage.set(key, String(value)); },
    },
    setTimeout(fn) { fn(); return 1; },
    clearTimeout() {},
  };
  const document = {
    currentScript: { dataset: { growthPage } },
    documentElement: { lang: 'zh-CN' },
    referrer,
    visibilityState: 'visible',
    querySelectorAll() { return links; },
    addEventListener(type, handler) { if (type === 'click') clickHandlers.push(handler); },
  };
  const context = {
    window,
    document,
    URL,
    URLSearchParams,
    fetch(url, options = {}) {
      requests.push({ url, options, body: options.body ? JSON.parse(options.body) : null });
      return Promise.resolve({ ok: true });
    },
    console,
  };
  vm.runInNewContext(trackerSource, context, { filename: trackerPath });
  if (backupLink) {
    for (const handler of clickHandlers) handler({ target: { closest() { return backupLink; } } });
  }
  assert.equal(requests.length, backupLink ? 2 : 1, `unexpected growth request count for ${referrer || search || 'direct'}`);
  requests[0].taggedDownloadHref = links[0]?.href || '';
  requests[0].allRequests = requests;
  return requests[0];
}

const cases = [
  { referrer: 'https://chatgpt.com/c/abc', expected: 'chatgpt' },
  { referrer: 'https://chat.openai.com/c/abc', expected: 'chatgpt' },
  { referrer: 'https://www.perplexity.ai/search/test', expected: 'perplexity' },
  { referrer: 'https://copilot.microsoft.com/', expected: 'copilot' },
  { referrer: 'https://gemini.google.com/app/abc', expected: 'gemini' },
  { referrer: 'https://claude.ai/new', expected: 'claude' },
  { referrer: 'https://naoshiquan.com/blog/cili-search-tools-2026', expected: 'naoshiquan' },
  { referrer: 'https://github.com/734496335/magnetgoogo', expected: 'github' },
  { referrer: 'https://www.reddit.com/r/androidapps/', expected: 'reddit' },
  { referrer: 'https://www.zhihu.com/question/1', expected: 'zhihu' },
  { referrer: 'https://www.v2ex.com/t/1', expected: 'v2ex' },
  { referrer: 'https://www.bilibili.com/video/BV1', expected: 'bilibili' },
  { referrer: 'https://magnet-googo.en.uptodown.com/android', expected: 'uptodown' },
  { referrer: 'https://alternativeto.net/software/magnet-googo/', expected: 'alternativeto' },
  { referrer: 'https://www.google.com/search?q=test', expected: 'google' },
  { referrer: 'https://example.com/post', expected: 'referral' },
  { referrer: '', expected: 'direct' },
];
for (const testCase of cases) {
  const req = runTracker(testCase);
  assert.equal(req.body.source, testCase.expected, `source mismatch for ${testCase.referrer}`);
  assert.deepEqual(Object.keys(req.body).sort(), ['locale', 'page', 'source']);
}

const campaignCases = [
  ['chatgpt.com', 'chatgpt'],
  ['reddit', 'reddit'],
  ['twitter', 'x'],
  ['naoshiquan', 'naoshiquan'],
  ['github', 'github'],
  ['uptodown', 'uptodown'],
  ['alternativeto', 'alternativeto'],
];
for (const [utmSource, expected] of campaignCases) {
  const req = runTracker({
    referrer: '',
    search: `?utm_source=${encodeURIComponent(utmSource)}&utm_medium=referral&secret_should_not_leave_browser=1`,
  });
  assert.equal(req.body.source, expected, `campaign source mismatch for ${utmSource}`);
  assert.equal(JSON.stringify(req.body).includes('secret_should_not_leave_browser'), false);
  assert.equal(JSON.stringify(req.body).includes('utm_medium'), false);
  assert.deepEqual(Object.keys(req.body).sort(), ['locale', 'page', 'source']);
}
const untrustedCampaign = runTracker({ referrer: '', search: '?utm_source=totally-untrusted-source&secret=1' });
assert.equal(untrustedCampaign.body.source, 'direct', 'unknown campaign values must not escape the finite allowlist');

const taggedDownload = runTracker({
  referrer: 'https://naoshiquan.com/blog/cili-search-tools-2026',
  search: '?utm_medium=referral&secret_should_not_leave_browser=1',
  downloadHref: 'https://api.naoshiquan.com/go/download?page=home&locale=zh-CN&placement=hero',
});
assert.match(taggedDownload.taggedDownloadHref, /[?&]source=naoshiquan(?:&|$)/, 'download CTA must carry only the finite session acquisition category');
assert.equal(taggedDownload.taggedDownloadHref.includes('secret_should_not_leave_browser'), false, 'raw query must never be copied into download CTA');

for (const mirror of ['github', 'lanzou']) {
  const backup = runTracker({
    pathname: '/',
    growthPage: 'home',
    referrer: 'https://www.baidu.com/s?wd=magnet',
    backupDownload: mirror,
  });
  const trackingRequest = backup.allRequests[1];
  const trackingUrl = new URL(trackingRequest.url);
  assert.equal(trackingUrl.hostname, 'api.naoshiquan.com');
  assert.equal(trackingUrl.pathname, '/go/download');
  assert.equal(trackingUrl.searchParams.get('page'), 'home');
  assert.equal(trackingUrl.searchParams.get('placement'), `backup_${mirror}`);
  assert.equal(trackingUrl.searchParams.get('source'), 'baidu');
  assert.equal(trackingRequest.options.redirect, 'manual', 'backup tracking must never follow the primary APK redirect');
  assert.equal(trackingRequest.options.keepalive, true);
}

for (const agent of ['OAI-SearchBot', 'PerplexityBot']) {
  assert.match(robots, new RegExp(`User-agent:\\s*${agent}[\\s\\S]*?Allow:\\s*/`), `${agent} must be explicitly allowed`);
}
assert.match(robots, /User-agent:\s*\*[\s\S]*?Allow:\s*\//, 'general crawler allow rule missing');

function structuredGraphs(html, label) {
  const blocks = [...html.matchAll(/<script\s+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)];
  assert.ok(blocks.length > 0, `${label}: JSON-LD missing`);
  return blocks.map((match) => JSON.parse(match[1]));
}

function graphNodes(documents) {
  return documents.flatMap((doc) => Array.isArray(doc['@graph']) ? doc['@graph'] : [doc]);
}

for (const [label, html] of [['home', home], ['about', about]]) {
  const nodes = graphNodes(structuredGraphs(html, label));
  const organization = nodes.find((node) => node['@id'] === 'https://magnetgoogo.com/#organization');
  const software = nodes.find((node) => node['@id'] === 'https://magnetgoogo.com/#software');
  assert.ok(organization, `${label}: stable organization entity missing`);
  assert.ok(software, `${label}: stable software entity missing`);
  assert.equal(organization.name, 'Magnet Googo', `${label}: canonical organization name drift`);
  assert.ok(Array.isArray(organization.sameAs) && organization.sameAs.includes('https://github.com/734496335/magnetgoogo'), `${label}: GitHub sameAs missing`);
  assert.match(String(software.description || ''), /Android/i, `${label}: software description must state platform`);
  assert.match(String(software.description || ''), /不托管|does not host/i, `${label}: hosting boundary must be explicit`);
}

for (const href of ['/methodology/', '/status/', '/reports/', 'https://github.com/734496335/magnetgoogo']) {
  assert.ok(about.includes(href), `about reference source missing: ${href}`);
}
assert.ok(sitemap.includes('<loc>https://magnetgoogo.com/</loc>'), 'homepage missing from sitemap');
assert.ok(sitemap.includes('<loc>https://magnetgoogo.com/about</loc>'), 'about entity page missing from sitemap');

const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].length;
console.log(JSON.stringify({
  status: 'PASS',
  ai_referral_sources: ['chatgpt', 'perplexity', 'copilot', 'gemini', 'claude'],
  actionable_referral_sources: ['naoshiquan', 'github', 'reddit', 'zhihu', 'v2ex', 'coolapk', '52pojie', 'bilibili', 'telegram', 'producthunt', 'uptodown', 'alternativeto', 'x', 'youtube'],
  finite_campaign_utm_sources: campaignCases.map(([source, mapped]) => `${source}->${mapped}`),
  raw_query_not_transmitted: true,
  explicit_ai_search_crawlers: ['OAI-SearchBot', 'PerplexityBot'],
  stable_entity_ids: true,
  same_as_github: true,
  evidence_links_on_about: true,
  sitemap_urls: sitemapUrls,
}, null, 2));
