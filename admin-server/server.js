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

// CF Gateway for feedback proxy
const CF_GATEWAY = 'https://api.naoshiquan.com';
const ADMIN_SECRET = 'maggoogo-admin-2026';

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
      },
      brandStats,
      detailStats,
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

// ── API: Events raw batches with processing ──
app.get('/api/events/analytics', async (req, res) => {
  try {
    const resp = await fetch(`${CF_GATEWAY}/api/events?secret=${ADMIN_SECRET}&raw=1`);
    const data = await resp.json();

    if (!data.batches || data.batches.length === 0) {
      return res.json({
        summary: data.summary || { batches: 0, devices: 0, totalEvents: 0, eventCounts: {} },
        hourly: [],
        daily: [],
        topQueries: [],
        sourcePerf: [],
        versionDist: {},
        countryDist: {},
        deviceTimeline: [],
        recentEvents: [],
      });
    }

    // ── Process raw batches into analytics views ──
    const hourlyMap = {};
    const dailyMap = {};
    const queryMap = {};
    const srcOkMap = {};
    const srcFailMap = {};
    const srcMsMap = {};
    const versionMap = {};
    const countryMap = {};
    const recentEvents = [];

    for (const batch of data.batches) {
      const appV = batch.app_v || 'unknown';
      const country = batch.country || 'unknown';
      versionMap[appV] = (versionMap[appV] || 0) + 1;
      countryMap[country] = (countryMap[country] || 0) + 1;

      for (const ev of (batch.events || [])) {
        const ts = ev.ts || 0;
        const d = new Date(ts);
        const hourKey = d.toISOString().slice(0, 13); // "2026-05-03T18"
        const dayKey = d.toISOString().slice(0, 10);   // "2026-05-03"

        hourlyMap[hourKey] = hourlyMap[hourKey] || {};
        hourlyMap[hourKey][ev.e] = (hourlyMap[hourKey][ev.e] || 0) + 1;

        dailyMap[dayKey] = dailyMap[dayKey] || {};
        dailyMap[dayKey][ev.e] = (dailyMap[dayKey][ev.e] || 0) + 1;
        dailyMap[dayKey]._devices = dailyMap[dayKey]._devices || new Set();
        dailyMap[dayKey]._devices.add(batch.did);

        if (ev.e === 'search' && ev.q) {
          queryMap[ev.q] = (queryMap[ev.q] || 0) + 1;
        }
        if (ev.e === 'src_ok' && ev.src) {
          srcOkMap[ev.src] = (srcOkMap[ev.src] || 0) + 1;
          if (ev.ms) {
            srcMsMap[ev.src] = srcMsMap[ev.src] || [];
            srcMsMap[ev.src].push(ev.ms);
          }
        }
        if (ev.e === 'src_fail' && ev.src) {
          srcFailMap[ev.src] = (srcFailMap[ev.src] || 0) + 1;
        }

        // Keep recent events (last 100)
        if (recentEvents.length < 100) {
          recentEvents.push({
            e: ev.e,
            ts: ev.ts,
            did: batch.did?.slice(-6) || '?',
            appV,
            country,
            ...ev,
          });
        }
      }
    }

    // Sort & format
    const topQueries = Object.entries(queryMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 30)
      .map(([q, n]) => ({ q, n }));

    const allSrcs = new Set([...Object.keys(srcOkMap), ...Object.keys(srcFailMap)]);
    const sourcePerf = [...allSrcs].map(src => {
      const ok = srcOkMap[src] || 0;
      const fail = srcFailMap[src] || 0;
      const total = ok + fail;
      const msArr = srcMsMap[src] || [];
      const avgMs = msArr.length > 0 ? Math.round(msArr.reduce((a, b) => a + b, 0) / msArr.length) : 0;
      return { src, ok, fail, total, rate: total > 0 ? Math.round(ok / total * 100) : 0, avgMs };
    }).sort((a, b) => b.total - a.total).slice(0, 40);

    const daily = Object.entries(dailyMap)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([day, counts]) => ({
        day,
        devices: counts._devices ? counts._devices.size : 0,
        events: Object.entries(counts).filter(([k]) => k !== '_devices').reduce((s, [, v]) => s + v, 0),
        searches: counts.search || 0,
        copies: counts.copy_magnet || 0,
        opens: counts.open_magnet || 0,
        starts: counts.app_start || 0,
      }));

    const hourly = Object.entries(hourlyMap)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-72)
      .map(([hour, counts]) => ({
        hour,
        total: Object.values(counts).reduce((s, v) => s + v, 0),
        ...counts,
      }));

    recentEvents.sort((a, b) => (b.ts || 0) - (a.ts || 0));

    res.json({
      summary: data.summary,
      hourly,
      daily,
      topQueries,
      sourcePerf,
      versionDist: versionMap,
      countryDist: countryMap,
      recentEvents: recentEvents.slice(0, 50),
    });
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
app.listen(PORT, () => {
  console.log(`\n  🔧 MagGoogo Admin Server`);
  console.log(`  ➜ http://localhost:${PORT}\n`);
});
