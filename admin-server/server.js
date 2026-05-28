const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const { execSync, exec } = require('child_process');

const app = express();
const PORT = 3800;

app.use(cors());
app.use(express.json());

// ── Paths ──
const ROOT = path.resolve(__dirname, '..');
const SOURCES_JSON = path.join(ROOT, 'sources.json');
const MG_DATA = path.join(ROOT, 'mg-data');
const CONFIG_JSON = path.join(MG_DATA, 'config.json');
const MAGGOOGO_SOURCES = path.join(ROOT, 'maggoogo-sources');
const CONFIG_JSON_ALT = path.join(MAGGOOGO_SOURCES, 'config.json');
const ENC_FILE = path.join(MG_DATA, 'sources.enc.json');
const APK_DIR = path.join(ROOT, 'magnetgoogo-app', 'android', 'app', 'build', 'outputs', 'apk', 'release');
const ENCRYPT_SCRIPT = path.join(ROOT, 'encrypt_sources.py');
const DASHBOARD_HTML = path.join(ROOT, 'admin_templates', 'dashboard.html');
const HEALTH_REPORT = path.join(ROOT, 'magnet', '_health_report_full.json');
const AI_BATCH_DIR = path.join(ROOT, 'magnet');

// CF Gateway for feedback proxy
const CF_GATEWAY = 'https://api.naoshiquan.com';
const ADMIN_SECRET = 'maggoogo-admin-2026';

// ── Analytics cache (incremental) ──
const CACHE_DIR = path.join(__dirname, 'cache');
const BATCHES_CACHE_FILE = path.join(CACHE_DIR, 'batches.json');   // raw batches (local accumulation)
const ANALYTICS_CACHE_FILE = path.join(CACHE_DIR, 'analytics.json'); // processed analytics
const META_CACHE_FILE = path.join(CACHE_DIR, 'meta.json');          // { lastFetchedAt }
const CACHE_INTERVAL_MS = 20 * 60 * 1000; // 20 minutes
const MAX_DAYS = 30;                       // rolling window
let analyticsCache = null;   // in-memory processed analytics
let localBatches = [];       // in-memory raw batches
let cacheFetchingNow = false; // prevent concurrent fetches

// ── Chinese geo name mapping (Cloudflare returns pinyin for CN) ──
const CN_CITY_MAP = {
  'Shanghai': '上海', 'Beijing': '北京', 'Guangzhou': '广州', 'Shenzhen': '深圳',
  'Chengdu': '成都', 'Hangzhou': '杭州', 'Wuhan': '武汉', 'Nanjing': '南京',
  'Chongqing': '重庆', 'Tianjin': '天津', 'Suzhou': '苏州', 'Xiamen': '厦门',
  'Changsha': '长沙', 'Zhengzhou': '郑州', 'Dongguan': '东莞', 'Foshan': '佛山',
  'Kunming': '昆明', 'Hefei': '合肥', 'Jinan': '济南', 'Fuzhou': '福州',
  'Qingdao': '青岛', 'Dalian': '大连', 'Ningbo': '宁波', 'Wenzhou': '温州',
  'Shenyang': '沈阳', 'Harbin': '哈尔滨', 'Changchun': '长春', 'Shijiazhuang': '石家庄',
  'Taiyuan': '太原', 'Nanning': '南宁', 'Guiyang': '贵阳', 'Urumqi': '乌鲁木齐',
  'Lanzhou': '兰州', 'Haikou': '海口', 'Yinchuan': '银川', 'Xining': '西宁',
  'Lhasa': '拉萨', 'Hohhot': '呼和浩特', 'Nanchang': '南昌', 'Wuxi': '无锡',
  'Zhuhai': '珠海', 'Zhongshan': '中山', 'Huizhou': '惠州', 'Jiangmen': '江门',
  'Yuncheng': '运城', 'Luoyang': '洛阳', 'Xuzhou': '徐州', 'Yantai': '烟台',
  'Weifang': '潍坊', 'Zibo': '淄博', 'Linyi': '临沂', 'Tangshan': '唐山',
  'Baoding': '保定', 'Huzhou': '湖州', 'Shaoxing': '绍兴', 'Jinhua': '金华',
  'Taizhou': '台州', 'Yangzhou': '扬州', 'Yancheng': '盐城', 'Nantong': '南通',
  'Zhenjiang': '镇江', 'Lianyungang': '连云港', 'Quanzhou': '泉州', 'Zhangzhou': '漳州',
  'Putian': '莆田', 'Sanming': '三明', 'Guilin': '桂林', 'Liuzhou': '柳州',
  'Mianyang': '绵阳', 'Deyang': '德阳', 'Leshan': '乐山', 'Yibin': '宜宾',
  'Zunyi': '遵义', 'Dali': '大理', 'Lijiang': '丽江', 'Lishui': '丽水',
  'Macau': '澳门', 'Hong Kong': '香港', 'Taipei': '台北', 'Kaohsiung': '高雄',
  'Taichung': '台中', 'Tainan': '台南',
};
const CN_REGION_MAP = {
  'Shanghai': '上海', 'Beijing': '北京', 'Tianjin': '天津', 'Chongqing': '重庆',
  'Guangdong': '广东', 'Zhejiang': '浙江', 'Jiangsu': '江苏', 'Shandong': '山东',
  'Henan': '河南', 'Sichuan': '四川', 'Hubei': '湖北', 'Hunan': '湖南',
  'Fujian': '福建', 'Anhui': '安徽', 'Hebei': '河北', 'Liaoning': '辽宁',
  'Shaanxi': '陕西', 'Jiangxi': '江西', 'Guangxi': '广西', 'Yunnan': '云南',
  'Guizhou': '贵州', 'Shanxi': '山西', 'Inner Mongolia': '内蒙古', 'Heilongjiang': '黑龙江',
  'Jilin': '吉林', 'Xinjiang': '新疆', 'Gansu': '甘肃', 'Hainan': '海南',
  'Ningxia': '宁夏', 'Qinghai': '青海', 'Tibet': '西藏', 'Macau': '澳门',
  'Hong Kong': '香港', 'Taiwan': '台湾', 'Hebei': '河北',
};
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
function localizeCN(city, region, country) {
  if (['CN', 'MO', 'HK', 'TW'].includes(country)) {
    return {
      city: CN_CITY_MAP[city] || city,
      region: CN_REGION_MAP[region] || region,
    };
  }
  return { city, region };
}

// ── Serve dashboard ──
app.get('/', (req, res) => {
  res.sendFile(DASHBOARD_HTML);
});

// ── API: Overview ──
app.get('/api/overview', (req, res) => {
  try {
    // Sources stats
    const sourcesRaw = JSON.parse(fs.readFileSync(SOURCES_JSON, 'utf-8'));
    let rules = [];
    if (sourcesRaw.rulesets) {
      for (const rs of sourcesRaw.rulesets) {
        if (rs.rules) rules.push(...rs.rules);
      }
    } else if (Array.isArray(sourcesRaw)) {
      rules = sourcesRaw;
    }

    const green = rules.filter(r => r.health?.status === 'green').length;
    const yellow = rules.filter(r => r.health?.status === 'yellow').length;
    const gray = rules.filter(r => r.health?.status === 'gray').length;

    // Config
    const config = fs.existsSync(CONFIG_JSON)
      ? JSON.parse(fs.readFileSync(CONFIG_JSON, 'utf-8'))
      : {};

    // APK info
    const apkPath = path.join(APK_DIR, 'app-release.apk');
    let apk = { exists: false };
    if (fs.existsSync(apkPath)) {
      const stat = fs.statSync(apkPath);
      apk = { exists: true, size_mb: (stat.size / 1024 / 1024).toFixed(1), modified: stat.mtime.toISOString() };
    }

    // Encrypted file info
    let encrypted = { exists: false };
    if (fs.existsSync(ENC_FILE)) {
      const stat = fs.statSync(ENC_FILE);
      encrypted = { exists: true, size_kb: (stat.size / 1024).toFixed(1), modified: stat.mtime.toISOString() };
    }

    res.json({
      sources: { total: rules.length, green, yellow, gray },
      config,
      apk,
      encrypted,
      github_repo: '734496335/magnetgoogo',
      jsdelivr_base: 'https://cdn.jsdelivr.net/gh/734496335/mg-data@main',
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── API: Sources details ──
app.get('/api/sources/details', (req, res) => {
  try {
    const sourcesRaw = JSON.parse(fs.readFileSync(SOURCES_JSON, 'utf-8'));
    const generatedAt = sourcesRaw.generated_at || '';
    let allRaw = [];
    if (sourcesRaw.rulesets) {
      for (const rs of sourcesRaw.rulesets) {
        if (rs.rules) allRaw.push(...rs.rules);
      }
    }

    // ── Per-rule enriched data ──
    const rules = allRaw.map(r => {
      const origin = r.site?.origin || '';
      let domain = '';
      try { domain = new URL(origin).hostname; } catch {}
      return {
        id: r.id,
        site_name: r.site?.name || r.id,
        brand: r.site?.brand || '',
        base_url: origin,
        domain,
        countries: (r.site?.countries || []).join(', '),
        status: r.health?.status || 'gray',
        status_detail: r.health?.status_detail || '',
        fail_streak: r.health?.fail_streak || 0,
        last_checked: r.health?.last_checked_at || '',
        magnets_found: r.health?.magnets_found || 0,
        sample_title: r.health?.sample_title || '',
        quality_score: r.quality?.score || 0,
        tags: (r.quality?.tags || []).join(', '),
        requires_waf: r.search?.requires_waf_bypass || false,
        requires_browser: r.search?.requires_browser || false,
        supports_detail: r.capabilities?.supports_detail || false,
        search_template: r.search?.request_template || '',
        has_referer: !!r.search?.referer,
        // v0.3.5+ capability tags (added by HealerV2 + brand_rediscovery + onboard_candidate)
        parse_strategy: r.capabilities?.parse_strategy || 'list_page',
        brand_family: r.capabilities?.brand_family || '',
        onboarded_version: r._onboarded?.version || '',
        onboarded_at: r._onboarded?.at || '',
      };
    });

    // ── Aggregate stats ──
    const total = rules.length;
    const green = rules.filter(r => r.status === 'green').length;
    const yellow = rules.filter(r => r.status === 'yellow').length;
    const gray = rules.filter(r => r.status === 'gray').length;

    // Unique brands (non-empty)
    const brandSet = new Set(rules.filter(r => r.brand).map(r => r.brand));
    const noBrandCount = rules.filter(r => !r.brand).length;

    // Deduplicated sources: group by brand (if has brand) or by origin
    const deduped = new Set();
    for (const r of rules) {
      deduped.add(r.brand || r.base_url);
    }

    // Brand breakdown: { brand, total, green, yellow, gray, domains[] }
    const brandMap = {};
    for (const r of rules) {
      const key = r.brand || r.site_name || r.base_url;
      if (!brandMap[key]) brandMap[key] = { brand: key, total: 0, green: 0, yellow: 0, gray: 0, domains: [] };
      brandMap[key].total++;
      brandMap[key][r.status]++;
      if (!brandMap[key].domains.includes(r.domain)) brandMap[key].domains.push(r.domain);
    }
    const brandStats = Object.values(brandMap)
      .sort((a, b) => b.total - a.total)
      .map(b => ({ ...b, domains: b.domains.length }));

    // status_detail breakdown
    const detailMap = {};
    for (const r of rules) {
      const d = r.status_detail || 'unknown';
      detailMap[d] = (detailMap[d] || 0) + 1;
    }
    const detailStats = Object.entries(detailMap)
      .sort((a, b) => b[1] - a[1])
      .map(([detail, count]) => ({ detail, count }));

    // WAF/Browser stats
    const wafCount = rules.filter(r => r.requires_waf).length;
    const browserCount = rules.filter(r => r.requires_browser).length;
    const detailFollowCount = rules.filter(r => r.supports_detail).length;

    // ── parse_strategy breakdown (v0.3.5+) ──
    const parseStrategyMap = {};
    for (const r of rules) {
      const k = r.parse_strategy || 'list_page';
      if (!parseStrategyMap[k]) parseStrategyMap[k] = { strategy: k, total: 0, green: 0, yellow: 0, gray: 0 };
      parseStrategyMap[k].total++;
      parseStrategyMap[k][r.status]++;
    }
    const parseStrategyStats = Object.values(parseStrategyMap)
      .sort((a, b) => b.total - a.total);

    // ── brand_family breakdown (v0.3.6+) ──
    const brandFamilyMap = {};
    for (const r of rules) {
      if (!r.brand_family) continue;
      const k = r.brand_family;
      if (!brandFamilyMap[k]) brandFamilyMap[k] = { family: k, total: 0, green: 0, yellow: 0, gray: 0, members: [] };
      brandFamilyMap[k].total++;
      brandFamilyMap[k][r.status]++;
      brandFamilyMap[k].members.push(r.site_name);
    }
    const brandFamilyStats = Object.values(brandFamilyMap)
      .sort((a, b) => b.total - a.total)
      .map(f => ({ ...f, members: f.members.slice(0, 10) }));

    // ── onboarded sources (v0.3.7+) ──
    const onboardedRules = rules
      .filter(r => r.onboarded_version)
      .map(r => ({
        site_name: r.site_name,
        version: r.onboarded_version,
        at: r.onboarded_at,
        status: r.status,
        parse_strategy: r.parse_strategy,
        brand_family: r.brand_family,
        magnets_found: r.magnets_found,
      }));

    // ── Brand registry (from sources.json) ──
    const brandRegistry = Array.isArray(sourcesRaw.brand_registry) ? sourcesRaw.brand_registry : [];

    // ── Discovery metadata ──
    const disc = sourcesRaw.discovery_metadata || {};
    const releasePages = Array.isArray(disc.release_pages) ? disc.release_pages : [];
    const navSites = Array.isArray(disc.navigation_sites) ? disc.navigation_sites : [];
    const tools = Array.isArray(disc.tools) ? disc.tools : [];

    // ── Green unique sources (brand-level view) ──
    const greenRules = rules.filter(r => r.status === 'green');
    const greenBrandMap = {};
    for (const r of greenRules) {
      const key = r.brand || r.site_name;
      if (!greenBrandMap[key]) greenBrandMap[key] = { brand: key, domains: [], count: 0, sample_domain: '' };
      greenBrandMap[key].count++;
      if (!greenBrandMap[key].domains.includes(r.domain)) greenBrandMap[key].domains.push(r.domain);
      if (!greenBrandMap[key].sample_domain) greenBrandMap[key].sample_domain = r.domain;
    }
    const greenBrands = Object.values(greenBrandMap)
      .sort((a, b) => b.count - a.count)
      .map(b => ({ ...b, domains: b.domains.length, domain_list: b.domains.slice(0, 5) }));

    res.json({
      rules,
      total,
      generated_at: generatedAt,
      stats: {
        total, green, yellow, gray,
        unique_brands: brandSet.size,
        no_brand_count: noBrandCount,
        deduplicated_sources: deduped.size,
        waf_count: wafCount,
        browser_count: browserCount,
        detail_follow_count: detailFollowCount,
        green_unique_brands: Object.keys(greenBrandMap).length,
      },
      brandStats,
      detailStats,
      parseStrategyStats,
      brandFamilyStats,
      onboardedRules,
      greenBrands,
      brandRegistry,
      discovery: {
        release_pages: releasePages,
        navigation_sites: navSites,
        tools,
        last_updated: disc.last_updated || '',
      },
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── API: Save config ──
app.post('/api/config', (req, res) => {
  try {
    const body = req.body;
    const config = {
      latest_version: body.latest_version || '0.1.0',
      min_version: body.min_version || '0.1.0',
      download: body.download || {},
      announcement: body.announcement || '',
      source_expiry_hours: body.source_expiry_hours || 72,
      source_schema_version: body.source_schema_version || 1,
      updated_at: new Date().toISOString(),
    };

    // Write to both config locations
    const configStr = JSON.stringify(config, null, 2);
    fs.writeFileSync(CONFIG_JSON, configStr, 'utf-8');
    if (fs.existsSync(path.dirname(CONFIG_JSON_ALT))) {
      fs.writeFileSync(CONFIG_JSON_ALT, configStr, 'utf-8');
    }

    res.json({ ok: true, message: '配置已保存' });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── API: Encrypt sources ──
app.post('/api/encrypt', (req, res) => {
  try {
    const output = execSync(`python "${ENCRYPT_SCRIPT}"`, {
      cwd: ROOT,
      encoding: 'utf-8',
      timeout: 30000,
    });
    res.json({ ok: true, message: '加密完成', output });
  } catch (e) {
    res.status(500).json({ ok: false, message: '加密失败', output: e.stderr || e.message });
  }
});

// ── API: Push config to GitHub (mg-data) ──
app.post('/api/push-config', (req, res) => {
  try {
    execSync('git add -A', { cwd: MG_DATA, encoding: 'utf-8' });

    // Check if there are changes
    const diff = execSync('git diff --cached --quiet', { cwd: MG_DATA, encoding: 'utf-8', stdio: 'pipe' }).catch(() => null);
    try {
      execSync('git diff --cached --quiet', { cwd: MG_DATA });
      res.json({ ok: true, message: '没有变更需要推送' });
      return;
    } catch {
      // Has changes, proceed
    }

    execSync('git commit -m "Update config"', { cwd: MG_DATA, encoding: 'utf-8' });
    execSync('git push', { cwd: MG_DATA, encoding: 'utf-8', timeout: 60000 });
    res.json({ ok: true, message: '已推送到 GitHub' });
  } catch (e) {
    res.status(500).json({ ok: false, message: e.stderr || e.message });
  }
});

// ── API: One-click publish (encrypt + push) ──
app.post('/api/publish', (req, res) => {
  try {
    // Step 1: Encrypt
    const encOutput = execSync(`python "${ENCRYPT_SCRIPT}"`, {
      cwd: ROOT,
      encoding: 'utf-8',
      timeout: 30000,
    });

    // Step 2: Git push mg-data
    execSync('git add -A', { cwd: MG_DATA, encoding: 'utf-8' });
    try {
      execSync('git diff --cached --quiet', { cwd: MG_DATA });
      res.json({ ok: true, message: '加密完成，无变更需要推送' });
      return;
    } catch {
      // Has changes
    }
    execSync('git commit -m "Publish encrypted sources"', { cwd: MG_DATA, encoding: 'utf-8' });
    execSync('git push', { cwd: MG_DATA, encoding: 'utf-8', timeout: 60000 });

    res.json({ ok: true, message: '发布完成：加密 + 推送成功' });
  } catch (e) {
    res.status(500).json({ ok: false, message: e.stderr || e.message });
  }
});

// ── API: Health diagnostics ──
// Reads the latest full health_check report (magnet/_health_report_full.json)
// + the latest AI bootstrap batch result (magnet/_ai_batch_*.json) and returns
// a single payload the dashboard can render without re-running anything.
//
// Three sections in the response:
//   - suspect_dead: sources that returned 0 magnets via plain requests on
//     every bait but page was non-trivial — likely anti-bot or hijacked
//   - collapsed_families: green→gray transitions clustered by name family
//     (e.g. clm50/51/.../59 dying together = 磁力猫 family migration)
//   - ai_batch: latest AI-bootstrap reverification result if present
app.get('/api/health/diagnostics', (req, res) => {
  try {
    if (!fs.existsSync(HEALTH_REPORT)) {
      return res.json({ ok: false, message: 'No health report yet — run python magnet/health_check.py --report magnet/_health_report_full.json' });
    }
    const stat = fs.statSync(HEALTH_REPORT);
    const report = JSON.parse(fs.readFileSync(HEALTH_REPORT, 'utf-8'));

    // Collect suspect_dead + green→gray
    const suspectDead = [];
    const collapsed = [];
    const counts = { green: 0, yellow: 0, gray: 0, skip: 0 };
    for (const [name, r] of Object.entries(report)) {
      const ns = r.new_status || 'skip';
      counts[ns] = (counts[ns] || 0) + 1;
      const err = r.error || '';
      if (err.includes('suspect_dead_search')) {
        suspectDead.push({
          name,
          old_status: r.old_status || '',
          new_status: ns,
          detail: r.detail || '',
          magnets: r.magnets || 0,
          latency_ms: r.latency || 0,
          error_summary: err.slice(0, 180),
        });
      }
      if (r.old_status === 'green' && ns === 'gray') {
        collapsed.push({
          name,
          detail: r.detail || '',
          latency_ms: r.latency || 0,
          error_summary: (err || '').slice(0, 100),
        });
      }
    }

    // Cluster collapsed by name family (strip "(suffix)" + match common stems)
    const families = {};
    for (const c of collapsed) {
      let key = c.name;
      const m1 = key.match(/^([^(（]+)[（(]/);
      if (m1) key = m1[1].trim();
      // numeric stem: clm52 → clm, sobt19 → sobt, clb13 → clb
      const m2 = key.match(/^([a-z]+?)(?:\d+)?(?:\.[a-z]+)?$/i);
      if (m2 && /\d/.test(key)) key = m2[1];
      families[key] = families[key] || { stem: key, count: 0, members: [], details: {} };
      families[key].count++;
      families[key].members.push(c.name);
      families[key].details[c.detail] = (families[key].details[c.detail] || 0) + 1;
    }
    const familyList = Object.values(families)
      .filter(f => f.count >= 2)
      .sort((a, b) => b.count - a.count);

    // Find latest AI batch result, if any
    let aiBatch = null;
    try {
      const files = fs.readdirSync(AI_BATCH_DIR)
        .filter(f => f.startsWith('_ai_batch_') && f.endsWith('.json'))
        .sort()
        .reverse();
      if (files.length) {
        const latest = path.join(AI_BATCH_DIR, files[0]);
        const raw = JSON.parse(fs.readFileSync(latest, 'utf-8'));
        aiBatch = {
          file: files[0],
          timestamp: raw.timestamp,
          llm: raw.llm,
          results: (raw.results || []).map(r => ({
            name: r.name,
            confidence: r.confidence ?? null,
            magnets_found: r.magnets_found ?? 0,
            list_items: r.list_items ?? 0,
            regex_magnets: r.regex_magnets_on_page ?? 0,
            elapsed_s: r.elapsed ?? null,
            error: r.error || null,
            sample_title: (r.samples && r.samples[0] && r.samples[0].title) || null,
          })),
        };
      }
    } catch (e) {
      aiBatch = { error: e.message };
    }

    res.json({
      ok: true,
      report_mtime: stat.mtime.toISOString(),
      counts,
      suspect_dead: suspectDead,
      collapsed_families: familyList,
      collapsed_total: collapsed.length,
      ai_batch: aiBatch,
    });
  } catch (e) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// ── API: Proxy feedback to CF Gateway ──
app.get('/api/feedback', async (req, res) => {
  try {
    const resp = await fetch(`${CF_GATEWAY}/api/feedback?secret=${ADMIN_SECRET}`);
    const data = await resp.json();
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: e.message, items: [] });
  }
});

app.delete('/api/feedback/:id', async (req, res) => {
  try {
    const resp = await fetch(`${CF_GATEWAY}/api/feedback/${req.params.id}`, {
      method: 'DELETE',
      headers: { 'X-Admin-Secret': ADMIN_SECRET },
    });
    const data = await resp.json();
    res.json(data);
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── API: Events/Analytics (proxy from CF Gateway) ──
app.get('/api/events', async (req, res) => {
  try {
    const raw = req.query.raw === '1' ? '&raw=1' : '';
    const resp = await fetch(`${CF_GATEWAY}/api/events?secret=${ADMIN_SECRET}${raw}`);
    const data = await resp.json();
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: e.message, summary: { batches: 0, devices: 0, totalEvents: 0, eventCounts: {} } });
  }
});

// ── Analytics: process raw batches into aggregated views ──
function processAnalyticsBatches(data) {
    if (!data.batches || data.batches.length === 0) {
      return {
        summary: data.summary || { batches: 0, devices: 0, totalEvents: 0, eventCounts: {} },
        hourly: [], daily: [], topQueries: [], sourcePerf: [],
        versionDist: {}, countryDist: {}, deviceTimeline: [], recentEvents: [],
      };
    }

    const hourlyMap = {};
    const dailyMap = {};
    const queryMap = {};
    const srcOkMap = {};
    const srcFailMap = {};
    const srcMsMap = {};
    const versionMap = {};
    const deviceCountrySet = {};
    const deviceCitySet = {};
    const dailyGeo = {};
    const deviceMap = {};
    const deviceFirstDay = {};
    const deviceActiveDays = {};
    const recentEvents = [];
    const searchDetails = [];

    for (const batch of data.batches) {
      const appV = batch.app_v || 'unknown';
      const country = batch.country || 'unknown';
      const rawCity = batch.city || '';
      const rawRegion = batch.region || '';
      const { city, region } = localizeCN(rawCity, rawRegion, country);
      const did = batch.did || '';
      versionMap[appV] = (versionMap[appV] || 0) + 1;
      if (did) {
        if (!deviceCountrySet[country]) deviceCountrySet[country] = new Set();
        deviceCountrySet[country].add(did);
        if (city) {
          if (!deviceCitySet[city]) deviceCitySet[city] = new Set();
          deviceCitySet[city].add(did);
        }
        const batchDay = (batch.receivedAt || '').slice(0, 10);
        if (batchDay) {
          if (!dailyGeo[batchDay]) dailyGeo[batchDay] = { country: {}, city: {} };
          if (!dailyGeo[batchDay].country[country]) dailyGeo[batchDay].country[country] = new Set();
          dailyGeo[batchDay].country[country].add(did);
          if (city) {
            if (!dailyGeo[batchDay].city[city]) dailyGeo[batchDay].city[city] = new Set();
            dailyGeo[batchDay].city[city].add(did);
          }
        }
      }

      if (did) {
        if (!deviceMap[did]) {
          deviceMap[did] = { lastSeen: '', city: '', region: '', country: '', appV: '', os: '', searches: 0, copies: 0, opens: 0, starts: 0, events: 0, batches: 0 };
        }
        const dm = deviceMap[did];
        const receivedAt = batch.receivedAt || '';
        if (receivedAt > dm.lastSeen) {
          dm.lastSeen = receivedAt;
          dm.city = city || dm.city;
          dm.region = region || dm.region;
          dm.country = country || dm.country;
          dm.appV = appV || dm.appV;
          dm.os = (batch.os || '') + (batch.os_v ? ' ' + batch.os_v : '') || dm.os;
        }
        dm.batches++;
      }

      for (const ev of (batch.events || [])) {
        const ts = ev.ts || 0;
        const d = new Date(ts);
        const hourKey = d.toISOString().slice(0, 13);
        const dayKey = d.toISOString().slice(0, 10);

        hourlyMap[hourKey] = hourlyMap[hourKey] || {};
        hourlyMap[hourKey][ev.e] = (hourlyMap[hourKey][ev.e] || 0) + 1;

        dailyMap[dayKey] = dailyMap[dayKey] || {};
        dailyMap[dayKey][ev.e] = (dailyMap[dayKey][ev.e] || 0) + 1;
        dailyMap[dayKey]._devices = dailyMap[dayKey]._devices || new Set();
        dailyMap[dayKey]._devices.add(did);
        dailyMap[dayKey]._newDevices = dailyMap[dayKey]._newDevices || new Set();

        if (did) {
          if (!deviceFirstDay[did] || dayKey < deviceFirstDay[did]) deviceFirstDay[did] = dayKey;
          if (!deviceActiveDays[did]) deviceActiveDays[did] = new Set();
          deviceActiveDays[did].add(dayKey);
          const dm = deviceMap[did];
          dm.events++;
          if (ev.e === 'search') dm.searches++;
          if (ev.e === 'copy_magnet') dm.copies++;
          if (ev.e === 'open_magnet') dm.opens++;
          if (ev.e === 'app_start') dm.starts++;
        }

        if (ev.e === 'search' && ev.q) {
          queryMap[ev.q] = (queryMap[ev.q] || 0) + 1;
          if (searchDetails.length < 500) {
            searchDetails.push({ q: ev.q, n: ev.n || 0, ts: ev.ts || 0, did: did ? did.slice(-8) : '?', city, country, appV });
          }
        }
        if (ev.e === 'src_ok' && ev.src) {
          srcOkMap[ev.src] = (srcOkMap[ev.src] || 0) + 1;
          if (ev.ms) { srcMsMap[ev.src] = srcMsMap[ev.src] || []; srcMsMap[ev.src].push(ev.ms); }
        }
        if (ev.e === 'src_fail' && ev.src) {
          srcFailMap[ev.src] = (srcFailMap[ev.src] || 0) + 1;
        }

        if (recentEvents.length < 100) {
          recentEvents.push({ e: ev.e, ts: ev.ts, did: did?.slice(-6) || '?', appV, country, city, ...ev });
        }
      }
    }

    for (const [did, firstDay] of Object.entries(deviceFirstDay)) {
      if (dailyMap[firstDay] && dailyMap[firstDay]._newDevices) {
        dailyMap[firstDay]._newDevices.add(did);
      }
    }

    const topQueries = Object.entries(queryMap).sort((a, b) => b[1] - a[1]).slice(0, 30).map(([q, n]) => ({ q, n }));

    const allSrcs = new Set([...Object.keys(srcOkMap), ...Object.keys(srcFailMap)]);
    const sourcePerf = [...allSrcs].map(src => {
      const ok = srcOkMap[src] || 0;
      const fail = srcFailMap[src] || 0;
      const total = ok + fail;
      const msArr = srcMsMap[src] || [];
      const avgMs = msArr.length > 0 ? Math.round(msArr.reduce((a, b) => a + b, 0) / msArr.length) : 0;
      return { src, ok, fail, total, rate: total > 0 ? Math.round(ok / total * 100) : 0, avgMs };
    }).sort((a, b) => b.total - a.total).slice(0, 40);

    const daily = Object.entries(dailyMap).sort((a, b) => a[0].localeCompare(b[0])).map(([day, counts]) => ({
      day,
      devices: counts._devices ? counts._devices.size : 0,
      newDevices: counts._newDevices ? counts._newDevices.size : 0,
      events: Object.entries(counts).filter(([k]) => !k.startsWith('_')).reduce((s, [, v]) => s + v, 0),
      searches: counts.search || 0, copies: counts.copy_magnet || 0,
      opens: counts.open_magnet || 0, starts: counts.app_start || 0,
    }));

    const hourly = Object.entries(hourlyMap).sort((a, b) => a[0].localeCompare(b[0])).slice(-72).map(([hour, counts]) => ({
      hour, total: Object.values(counts).reduce((s, v) => s + v, 0), ...counts,
    }));

    const devices = Object.entries(deviceMap).sort((a, b) => b[1].lastSeen.localeCompare(a[1].lastSeen)).slice(0, 200).map(([did, d]) => ({
      did: did.slice(-8), lastSeen: d.lastSeen, city: d.city, region: d.region, country: d.country,
      appV: d.appV, os: d.os, searches: d.searches, copies: d.copies, opens: d.opens,
      starts: d.starts, events: d.events, batches: d.batches,
    }));

    const countryMap = {};
    for (const [c, s] of Object.entries(deviceCountrySet)) countryMap[countryName(c)] = s.size;
    const cityDist = Object.entries(deviceCitySet).sort((a, b) => b[1].size - a[1].size).slice(0, 50).map(([city, s]) => ({ city, n: s.size }));

    const todayKey = new Date().toISOString().slice(0, 10);
    const todayGeo = dailyGeo[todayKey] || { country: {}, city: {} };
    const todayCountryDist = {};
    for (const [c, s] of Object.entries(todayGeo.country)) todayCountryDist[countryName(c)] = s.size;
    const todayCityDist = Object.entries(todayGeo.city).sort((a, b) => b[1].size - a[1].size).slice(0, 50).map(([city, s]) => ({ city, n: s.size }));

    const yesterdayKey = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const yesterdayGeo = dailyGeo[yesterdayKey] || { country: {}, city: {} };
    const yesterdayCountryDist = {};
    for (const [c, s] of Object.entries(yesterdayGeo.country)) yesterdayCountryDist[countryName(c)] = s.size;
    const yesterdayCityDist = Object.entries(yesterdayGeo.city).sort((a, b) => b[1].size - a[1].size).slice(0, 50).map(([city, s]) => ({ city, n: s.size }));

    const dailyGeoDist = Object.entries(dailyGeo).sort((a, b) => a[0].localeCompare(b[0])).slice(-30).map(([day, g]) => ({
      day,
      countries: Object.fromEntries(Object.entries(g.country).map(([c, s]) => [countryName(c), s.size])),
      cities: Object.fromEntries(Object.entries(g.city).map(([c, s]) => [c, s.size])),
    }));

    recentEvents.sort((a, b) => (b.ts || 0) - (a.ts || 0));

    // ── Cohort retention matrix ──────────────────────────────────────
    // Rows = cohort by install day (deviceFirstDay), latest 30 days only.
    // Cols = D0/D1/D3/D7/D14/D30 — % of cohort that returned that many
    // days after install. Excludes today's cohort from later columns when
    // not enough calendar days have elapsed (shown as null in JSON).
    const RETENTION_DAYS = [0, 1, 3, 7, 14, 30];
    const cohortMap = {};
    for (const [did, firstDay] of Object.entries(deviceFirstDay)) {
      if (!cohortMap[firstDay]) cohortMap[firstDay] = [];
      cohortMap[firstDay].push(did);
    }
    const todayMs = Date.now();
    const ONE_DAY = 86400000;
    const cohortDays = Object.keys(cohortMap).sort().slice(-30);
    const cohortRetention = cohortDays.map(cohortDay => {
      const dids = cohortMap[cohortDay];
      const cohortMs = new Date(cohortDay + 'T00:00:00Z').getTime();
      const elapsedDays = Math.floor((todayMs - cohortMs) / ONE_DAY);
      const retention = {};
      for (const offset of RETENTION_DAYS) {
        if (offset > elapsedDays) {
          retention[offset] = null;
          continue;
        }
        const targetDay = new Date(cohortMs + offset * ONE_DAY).toISOString().slice(0, 10);
        let returned = 0;
        for (const did of dids) {
          if (deviceActiveDays[did] && deviceActiveDays[did].has(targetDay)) returned++;
        }
        retention[offset] = {
          n: returned,
          pct: dids.length > 0 ? Math.round(returned / dids.length * 1000) / 10 : 0,
        };
      }
      return { cohort: cohortDay, size: dids.length, retention };
    });

    return {
      summary: data.summary, hourly, daily, topQueries, sourcePerf,
      versionDist: versionMap, countryDist: countryMap, cityDist,
      todayCountryDist, todayCityDist, yesterdayCountryDist, yesterdayCityDist,
      dailyGeoDist, devices, cohortRetention,
      searchDetails: searchDetails.sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 500),
      recentEvents: recentEvents.slice(0, 50),
    };
}

// ── Analytics cache: incremental fetch from R2, accumulate locally ──

function ensureCacheDir() {
  if (!fs.existsSync(CACHE_DIR)) fs.mkdirSync(CACHE_DIR, { recursive: true });
}

function loadMeta() {
  try {
    if (fs.existsSync(META_CACHE_FILE)) return JSON.parse(fs.readFileSync(META_CACHE_FILE, 'utf-8'));
  } catch (e) {}
  return { lastFetchedAt: null };
}

function saveMeta(meta) {
  ensureCacheDir();
  fs.writeFileSync(META_CACHE_FILE, JSON.stringify(meta), 'utf-8');
}

// Load local batches + processed analytics on startup
function loadCacheFromFile() {
  try {
    if (fs.existsSync(BATCHES_CACHE_FILE)) {
      localBatches = JSON.parse(fs.readFileSync(BATCHES_CACHE_FILE, 'utf-8'));
      console.log(`[cache] Loaded ${localBatches.length} batches from file`);
    }
    if (fs.existsSync(ANALYTICS_CACHE_FILE)) {
      analyticsCache = JSON.parse(fs.readFileSync(ANALYTICS_CACHE_FILE, 'utf-8'));
      console.log(`[cache] Loaded analytics — cached at ${analyticsCache._cachedAt || 'unknown'}`);
    }
  } catch (e) {
    console.error('[cache] Failed to load file cache:', e.message);
  }
}

// Rebuild processed analytics from local raw batches
function rebuildAnalytics(fetchMs, fetchDays, newCount, trimmedCount) {
  const eventCounts = {};
  let totalEvents = 0;
  for (const b of localBatches) {
    for (const ev of (b.events || [])) {
      eventCounts[ev.e] = (eventCounts[ev.e] || 0) + 1;
      totalEvents++;
    }
  }
  const devSet = new Set(localBatches.map(b => b.did).filter(Boolean));
  const data = {
    summary: { batches: localBatches.length, devices: devSet.size, totalEvents, eventCounts },
    batches: localBatches,
  };
  const result = processAnalyticsBatches(data);
  result._cachedAt = new Date().toISOString();
  result._fetchMs = fetchMs;
  result._fetchDays = fetchDays;
  result._newBatches = newCount;
  result._trimmed = trimmedCount;
  result._totalLocalBatches = localBatches.length;
  return result;
}

async function refreshAnalyticsCache() {
  if (cacheFetchingNow) {
    console.log('[cache] Skipping — fetch already in progress');
    return analyticsCache;
  }
  cacheFetchingNow = true;
  const t0 = Date.now();
  try {
    // Calculate minimal fetch window
    const meta = loadMeta();
    let fetchDays = 1;
    if (meta.lastFetchedAt) {
      const hoursSince = (Date.now() - new Date(meta.lastFetchedAt).getTime()) / 3600000;
      fetchDays = Math.max(1, Math.ceil(hoursSince / 24) + 1); // +1 overlap for safety
    } else if (localBatches.length === 0) {
      fetchDays = 14; // cold start: backfill KV+R2 data (may take ~2min, one-time only)
    }
    fetchDays = Math.min(fetchDays, MAX_DAYS);

    // Build existing ID set for dedup
    const existingIds = new Set(localBatches.map(b => b.id || `${b.did}_${b.receivedAt}`));

    console.log(`[cache] Fetching ${fetchDays} day(s) from CF Gateway (local: ${localBatches.length} batches)...`);
    const resp = await fetch(`${CF_GATEWAY}/api/events?secret=${ADMIN_SECRET}&raw=1&days=${fetchDays}`);
    const result = await resp.json();

    // Merge new batches
    let newCount = 0;
    for (const batch of (result.batches || [])) {
      const key = batch.id || `${batch.did}_${batch.receivedAt}`;
      if (!existingIds.has(key)) {
        localBatches.push(batch);
        existingIds.add(key);
        newCount++;
      }
    }

    // Trim older than 30 days
    const cutoff = new Date(Date.now() - MAX_DAYS * 86400000).toISOString();
    const before = localBatches.length;
    localBatches = localBatches.filter(b => (b.receivedAt || '') >= cutoff);
    const trimmedCount = before - localBatches.length;

    // Rebuild analytics
    const fetchMs = Date.now() - t0;
    analyticsCache = rebuildAnalytics(fetchMs, fetchDays, newCount, trimmedCount);

    // Persist to file
    ensureCacheDir();
    fs.writeFileSync(BATCHES_CACHE_FILE, JSON.stringify(localBatches), 'utf-8');
    fs.writeFileSync(ANALYTICS_CACHE_FILE, JSON.stringify(analyticsCache), 'utf-8');
    saveMeta({ lastFetchedAt: new Date().toISOString() });

    console.log(`[cache] Done in ${fetchMs}ms — fetched ${fetchDays}d, +${newCount} new, -${trimmedCount} expired, total ${localBatches.length} batches`);
    return analyticsCache;
  } catch (e) {
    console.error('[cache] Fetch failed:', e.message);
    return analyticsCache;
  } finally {
    cacheFetchingNow = false;
  }
}

// ── API: Events analytics — returns cached data (instant) ──
app.get('/api/events/analytics', async (req, res) => {
  try {
    if (analyticsCache) {
      const ageMs = Date.now() - new Date(analyticsCache._cachedAt || 0).getTime();
      res.json({
        ...analyticsCache,
        _cacheAge: Math.round(ageMs / 1000),
        _cacheAgeMin: Math.round(ageMs / 60000),
        _cached: true,
      });
    } else {
      // No cache yet — do a live fetch (first time only)
      const result = await refreshAnalyticsCache();
      if (result) {
        res.json({ ...result, _cacheAge: 0, _cacheAgeMin: 0, _cached: false });
      } else {
        res.status(503).json({ error: 'Analytics data not available yet, please retry' });
      }
    }
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── API: Force refresh analytics cache ──
app.post('/api/events/refresh', async (req, res) => {
  try {
    const result = await refreshAnalyticsCache();
    if (result) {
      res.json({
        ...result,
        _cacheAge: 0,
        _cacheAgeMin: 0,
        _cached: false,
        _refreshed: true,
      });
    } else {
      res.status(503).json({ error: 'Refresh failed, no data returned' });
    }
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── API: Health check trigger ──
app.post('/api/health-check', (req, res) => {
  const script = path.join(ROOT, 'scripts', 'health_check.py');
  if (!fs.existsSync(script)) {
    return res.status(404).json({ ok: false, message: 'health_check.py not found' });
  }

  // Run async, respond immediately
  res.json({ ok: true, message: '巡检已启动，请稍后刷新查看结果' });

  exec(`python "${script}"`, { cwd: ROOT, timeout: 300000 }, (err, stdout, stderr) => {
    if (err) console.error('[health-check] Error:', stderr || err.message);
    else console.log('[health-check] Done:', stdout.slice(0, 200));
  });
});

// ── Start ──
loadCacheFromFile();
app.listen(PORT, () => {
  console.log(`\n  🔧 MagGoogo Admin Server`);
  console.log(`  ➜ http://localhost:${PORT}`);
  console.log(`  📊 Analytics cache: ${analyticsCache ? 'loaded from file' : 'empty, will fetch on first request'}`);
  console.log(`  ⏱  Auto-refresh: every ${CACHE_INTERVAL_MS / 60000} minutes\n`);

  // Background refresh every 20 minutes
  setInterval(() => {
    console.log('[cache] Scheduled refresh starting...');
    refreshAnalyticsCache();
  }, CACHE_INTERVAL_MS);

  // First background fetch 10 seconds after startup
  setTimeout(() => refreshAnalyticsCache(), 10000);
});
