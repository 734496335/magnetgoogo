const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;
const DASHBOARD_PASSWORD = process.env.DASH_PASS || 'Maggoogo2026';
const CF_GATEWAY = 'https://api.naoshiquan.com';
const ADMIN_SECRET = 'maggoogo-admin-2026';

// ── In-memory cache (refresh from CF every 3 min) ──
let cache = { data: null, ts: 0 };
const CACHE_TTL = 3 * 60 * 1000;

app.use(express.json());

// ── Minimal cookie parser ──
app.use((req, res, next) => {
  req.cookies = {};
  (req.headers.cookie || '').split(';').forEach(c => {
    const [k, v] = c.trim().split('=');
    if (k && v) req.cookies[k] = decodeURIComponent(v);
  });
  next();
});

function authCheck(req, res, next) {
  const token = req.cookies?.auth || req.query.token;
  if (token === DASHBOARD_PASSWORD) return next();
  res.status(401).json({ error: 'unauthorized' });
}

// ── Login ──
app.post('/api/auth', (req, res) => {
  if ((req.body?.password) === DASHBOARD_PASSWORD) {
    res.setHeader('Set-Cookie', `auth=${DASHBOARD_PASSWORD}; HttpOnly; Max-Age=${30*86400}; Path=/`);
    return res.json({ ok: true });
  }
  res.status(401).json({ ok: false });
});

// ── Fetch from CF Gateway + cache ──
async function fetchCFAnalytics() {
  const now = Date.now();
  if (cache.data && (now - cache.ts) < CACHE_TTL) return cache.data;

  console.log('[CF] Fetching analytics from CF Gateway...');
  const resp = await fetch(`${CF_GATEWAY}/api/events?secret=${ADMIN_SECRET}&raw=1`);
  const raw = await resp.json();
  cache.data = raw;
  cache.ts = now;
  console.log(`[CF] Got ${raw.batches?.length || 0} batches`);
  return raw;
}

// ── Analytics API (proxy + process) ──
app.get('/api/analytics', authCheck, async (req, res) => {
  try {
    const raw = await fetchCFAnalytics();
    const result = processAnalytics(raw.batches || [], raw.summary || {});
    res.json(result);
  } catch (e) {
    console.error('[analytics]', e.message);
    res.status(500).json({ error: e.message });
  }
});

// ── Chinese city names ──
const CN = {
  'Shanghai':'上海','Beijing':'北京','Guangzhou':'广州','Shenzhen':'深圳',
  'Chengdu':'成都','Hangzhou':'杭州','Wuhan':'武汉','Nanjing':'南京',
  'Chongqing':'重庆','Tianjin':'天津','Suzhou':'苏州','Xiamen':'厦门',
  'Changsha':'长沙','Zhengzhou':'郑州','Dongguan':'东莞','Foshan':'佛山',
  'Kunming':'昆明','Hefei':'合肥','Jinan':'济南','Fuzhou':'福州',
  'Qingdao':'青岛','Dalian':'大连','Ningbo':'宁波','Wenzhou':'温州',
  'Shenyang':'沈阳','Harbin':'哈尔滨','Changchun':'长春','Shijiazhuang':'石家庄',
  'Taiyuan':'太原','Nanning':'南宁','Guiyang':'贵阳','Nanchang':'南昌','Wuxi':'无锡',
  'Macau':'澳门','Hong Kong':'香港','Taipei':'台北',
};
// ── Country code → Chinese name ──
const COUNTRY_CN = {
  'CN':'中国','US':'美国','JP':'日本','KR':'韩国','GB':'英国','DE':'德国',
  'FR':'法国','CA':'加拿大','AU':'澳大利亚','SG':'新加坡','MY':'马来西亚',
  'TH':'泰国','VN':'越南','ID':'印度尼西亚','PH':'菲律宾','IN':'印度',
  'RU':'俄罗斯','BR':'巴西','TW':'台湾','HK':'香港','MO':'澳门',
  'NL':'荷兰','IT':'意大利','ES':'西班牙','SE':'瑞典','NO':'挪威',
  'FI':'芬兰','DK':'丹麦','PL':'波兰','CH':'瑞士','AT':'奥地利',
  'NZ':'新西兰','IE':'爱尔兰','PT':'葡萄牙','CZ':'捷克','RO':'罗马尼亚',
  'UA':'乌克兰','TR':'土耳其','MX':'墨西哥','AR':'阿根廷','CL':'智利',
  'CO':'哥伦比亚','PE':'秘鲁','ZA':'南非','EG':'埃及','SA':'沙特阿拉伯',
  'AE':'阿联酋','IL':'以色列','PK':'巴基斯坦','BD':'孟加拉','MM':'缅甸',
  'KH':'柬埔寨','LA':'老挝','NP':'尼泊尔','LK':'斯里兰卡',
};
function countryName(code) { return COUNTRY_CN[code] || code; }
function loc(city, country) {
  return ['CN','MO','HK','TW'].includes(country) ? (CN[city] || city) : city;
}

function processAnalytics(batches, cfSummary) {
  const dailyMap = {}, queryMap = {}, srcOkMap = {}, srcFailMap = {}, srcMsMap = {};
  const versionMap = {}, deviceCountrySet = {}, deviceCitySet = {};
  const deviceMap = {}, deviceFirstDay = {}, recentEvents = [];

  for (const batch of batches) {
    const appV = batch.app_v || '?';
    const country = batch.country || '?';
    const city = loc(batch.city || '', country);
    const did = batch.did || '';
    versionMap[appV] = (versionMap[appV] || 0) + 1;

    if (did) {
      if (!deviceCountrySet[country]) deviceCountrySet[country] = new Set();
      deviceCountrySet[country].add(did);
      if (city) { if (!deviceCitySet[city]) deviceCitySet[city] = new Set(); deviceCitySet[city].add(did); }
      if (!deviceMap[did]) deviceMap[did] = { lastSeen:'', city:'', country:'', appV:'', searches:0, copies:0, opens:0, starts:0, events:0 };
      const dm = deviceMap[did];
      const ts = batch.receivedAt || '';
      if (ts > dm.lastSeen) { dm.lastSeen = ts; dm.city = city; dm.country = country; dm.appV = appV; }
    }

    for (const ev of (batch.events || [])) {
      const d = new Date(ev.ts || 0);
      const dayKey = d.toISOString().slice(0, 10);
      if (!dailyMap[dayKey]) dailyMap[dayKey] = { _devs: new Set(), _new: new Set() };
      const dm = dailyMap[dayKey];
      dm[ev.e] = (dm[ev.e] || 0) + 1;
      if (did) {
        dm._devs.add(did);
        if (!deviceFirstDay[did] || dayKey < deviceFirstDay[did]) deviceFirstDay[did] = dayKey;
        const dv = deviceMap[did]; dv.events++;
        if (ev.e === 'search') dv.searches++;
        if (ev.e === 'copy_magnet') dv.copies++;
        if (ev.e === 'open_magnet') dv.opens++;
        if (ev.e === 'app_start') dv.starts++;
      }
      if (ev.e === 'search' && ev.q) queryMap[ev.q] = (queryMap[ev.q] || 0) + 1;
      if (ev.e === 'src_ok' && ev.src) { srcOkMap[ev.src] = (srcOkMap[ev.src] || 0) + 1; if (ev.ms) { srcMsMap[ev.src] = srcMsMap[ev.src] || []; srcMsMap[ev.src].push(ev.ms); } }
      if (ev.e === 'src_fail' && ev.src) srcFailMap[ev.src] = (srcFailMap[ev.src] || 0) + 1;
      if (recentEvents.length < 80) recentEvents.push({ e: ev.e, ts: ev.ts, did: did?.slice(-6), city, country, ...ev });
    }
  }

  for (const [did, fd] of Object.entries(deviceFirstDay)) { if (dailyMap[fd]) dailyMap[fd]._new.add(did); }

  const daily = Object.entries(dailyMap).sort((a,b) => a[0].localeCompare(b[0])).map(([day, c]) => ({
    day, devices: c._devs.size, newDevices: c._new.size,
    searches: c.search || 0, copies: c.copy_magnet || 0, opens: c.open_magnet || 0, starts: c.app_start || 0,
    events: Object.entries(c).filter(([k]) => !k.startsWith('_')).reduce((s,[,v]) => s + (typeof v === 'number' ? v : 0), 0),
  }));

  const topQueries = Object.entries(queryMap).sort((a,b) => b[1] - a[1]).slice(0, 30).map(([q,n]) => ({q,n}));
  const allSrcs = new Set([...Object.keys(srcOkMap), ...Object.keys(srcFailMap)]);
  const sourcePerf = [...allSrcs].map(src => {
    const ok = srcOkMap[src]||0, fail = srcFailMap[src]||0, total = ok+fail;
    const ms = srcMsMap[src]||[];
    return { src, ok, fail, total, rate: total>0 ? Math.round(ok/total*100) : 0, avgMs: ms.length ? Math.round(ms.reduce((a,b)=>a+b,0)/ms.length) : 0 };
  }).sort((a,b) => b.total - a.total).slice(0, 40);

  const countryDist = {}; for (const [c,s] of Object.entries(deviceCountrySet)) countryDist[countryName(c)] = s.size;
  const cityDist = Object.entries(deviceCitySet).sort((a,b) => b[1].size - a[1].size).slice(0, 30).map(([city,s]) => ({city, n: s.size}));
  const todayKey = new Date().toISOString().slice(0, 10);
  const todayData = dailyMap[todayKey];

  const devices = Object.entries(deviceMap).sort((a,b) => b[1].lastSeen.localeCompare(a[1].lastSeen)).slice(0, 100).map(([did,d]) => ({ did: did.slice(-8), ...d }));
  recentEvents.sort((a,b) => (b.ts||0) - (a.ts||0));

  return {
    summary: {
      totalDevices: Object.keys(deviceMap).length,
      totalEvents: batches.reduce((s,b) => s + (b.events?.length||0), 0),
      totalSearches: Object.values(queryMap).reduce((s,v) => s+v, 0),
      totalBatches: batches.length,
      todayDevices: todayData ? todayData._devs.size : 0,
      todaySearches: todayData ? (todayData.search||0) : 0,
    },
    daily, topQueries, sourcePerf, versionDist: versionMap, countryDist, cityDist, devices,
    recentEvents: recentEvents.slice(0, 50),
  };
}

// ── Serve Dashboard ──
app.get('/', (req, res) => {
  if (req.cookies?.auth === DASHBOARD_PASSWORD) return res.sendFile(path.join(__dirname, 'public', 'index.html'));
  res.sendFile(path.join(__dirname, 'public', 'login.html'));
});
app.use('/assets', express.static(path.join(__dirname, 'public')));

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n  📊 MagGoogo Analytics Dashboard`);
  console.log(`  ➜ http://0.0.0.0:${PORT}`);
  console.log(`  � Data source: ${CF_GATEWAY}`);
  console.log(`  ⏱  Cache TTL: ${CACHE_TTL/1000}s\n`);
});
