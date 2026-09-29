const DAY_MS = 86400_000;

export function opsDayKey(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return '';
  return new Date(n + 8 * 3600_000).toISOString().slice(0, 10);
}

function cleanKey(value) {
  return String(value ?? '').trim().replace(/\u0000/g, '');
}

function eventTs(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

const MIN_EPOCH_MS = Date.UTC(2000, 0, 1);
function installationTs(value, firstOpenTs) {
  const ts = eventTs(value);
  if (ts === null || ts < MIN_EPOCH_MS || ts > firstOpenTs + 5 * 60_000) return null;
  return ts;
}

function deviceKey(batch) {
  const schemaV = Number(batch?.schema_v || 0);
  if (schemaV >= 2) return cleanKey(batch?.legacy_did || batch?.device_id || batch?.did);
  return cleanKey(batch?.did);
}

function installKey(batch) {
  return cleanKey(batch?.install_id || batch?.did);
}

function strongDeviceAlias(batch) {
  if (Number(batch?.schema_v || 0) < 2 || cleanKey(batch?.device_id_kind) !== 'android_id_hash') return null;
  const aliasKey = cleanKey(batch?.legacy_did || batch?.did);
  const canonicalKey = cleanKey(batch?.device_id);
  if (!aliasKey || !canonicalKey || aliasKey === canonicalKey) return null;
  return { aliasKey, canonicalKey, kind: 'android_id_hash' };
}

export function buildOpsState(batches) {
  const deviceDays = new Map();
  const deviceLatest = new Map();
  const aliases = new Map();
  const installs = new Map();
  const sessions = new Map();
  const searches = new Map();
  let validEvents = 0;

  for (const batch of Array.isArray(batches) ? batches : []) {
    const dev = deviceKey(batch);
    if (!dev) continue;
    const install = installKey(batch);
    const appV = cleanKey(batch?.app_v);
    const versionCode = cleanKey(batch?.version_code);
    const country = cleanKey(batch?.country);
    const events = Array.isArray(batch?.events) ? batch.events : [];
    const receivedParsed = Date.parse(String(batch?.receivedAt || ''));
    let lastSeenTs = Number.isFinite(receivedParsed) && receivedParsed > 0 ? receivedParsed : null;
    if (lastSeenTs === null) {
      for (const ev of events) {
        const ts = eventTs(ev?.ts);
        if (ts !== null) lastSeenTs = Math.max(lastSeenTs || 0, ts);
      }
    }
    if (lastSeenTs !== null) {
      const oldLatest = deviceLatest.get(dev);
      if (!oldLatest || lastSeenTs > oldLatest.lastSeenTs) {
        deviceLatest.set(dev, { deviceKey: dev, lastSeenTs, lastSeenDay: opsDayKey(lastSeenTs), appV, versionCode, country });
      }
      const alias = strongDeviceAlias(batch);
      if (alias) {
        const oldAlias = aliases.get(alias.aliasKey);
        if (!oldAlias) {
          aliases.set(alias.aliasKey, { ...alias, lastSeenTs, conflict: 0 });
        } else if (oldAlias.canonicalKey !== alias.canonicalKey) {
          oldAlias.conflict = 1;
          oldAlias.lastSeenTs = Math.max(oldAlias.lastSeenTs, lastSeenTs);
        } else {
          oldAlias.lastSeenTs = Math.max(oldAlias.lastSeenTs, lastSeenTs);
        }
      }
    }

    for (const ev of events) {
      const ts = eventTs(ev?.ts);
      if (!ts) continue;
      validEvents += 1;
      const day = opsDayKey(ts);
      const ddKey = `${day}\u0000${dev}`;
      const dd = deviceDays.get(ddKey) || {
        day, deviceKey: dev, firstTs: ts, appV, country, searched: 0, gotResult: 0, action: 0,
      };
      dd.firstTs = Math.min(dd.firstTs, ts);
      if (appV) dd.appV = appV;
      if (country) dd.country = country;
      if (ev.e === 'search_submitted') dd.searched = 1;
      if (ev.e === 'search_completed' && Math.max(0, Number(ev.result_count || 0)) > 0) dd.gotResult = 1;
      if (ev.e === 'open_magnet' || ev.e === 'copy_magnet') dd.action = 1;
      deviceDays.set(ddKey, dd);

      const sessionId = cleanKey(ev?.session_id || batch?.session_id);
      if (sessionId) {
        const key = `${day}\u0000${sessionId}`;
        const old = sessions.get(key);
        if (!old || ts < old.firstTs) {
          sessions.set(key, { day, sessionId, deviceKey: dev, firstTs: ts, appV, country });
        }
      }

      if (ev.e === 'first_open' && install) {
        const installTs = installationTs(ev?.installation_time, ts);
        if (installTs !== null) {
          const installDay = opsDayKey(installTs);
          const old = installs.get(install);
          if (!old || installTs < old.installationTs) {
            installs.set(install, {
              installDay, installKey: install, installationTs: installTs, firstOpenTs: ts, appV, country,
            });
          }
        }
      }

      const searchId = cleanKey(ev?.search_id);
      if (searchId) {
        const s = searches.get(searchId) || {
          searchId, deviceKey: dev, submittedDay: null, submittedTs: null,
          completedDay: null, completedTs: null, resultCount: null, ttfrMs: null,
          action: 0, appV, country,
        };
        if (dev) s.deviceKey = dev;
        if (appV) s.appV = appV;
        if (country) s.country = country;
        if (ev.e === 'search_submitted' && (s.submittedTs === null || ts < s.submittedTs)) {
          s.submittedTs = ts;
          s.submittedDay = day;
        }
        if (ev.e === 'search_completed' && (s.completedTs === null || ts >= s.completedTs)) {
          s.completedTs = ts;
          s.completedDay = day;
          s.resultCount = Math.max(0, Number(ev.result_count || 0));
          const ttfr = Number(ev.ttfr_ms);
          s.ttfrMs = Number.isFinite(ttfr) && ttfr >= 0 ? Math.round(ttfr) : null;
        }
        if (ev.e === 'open_magnet' || ev.e === 'copy_magnet') s.action = 1;
        searches.set(searchId, s);
      }
    }
  }

  return { deviceDays, deviceLatest, aliases, installs, sessions, searches, validEvents };
}

export function expectedCanonicalDailyRows(state) {
  const aliasMap = new Map();
  for (const row of state.aliases?.values?.() || []) {
    if (!row.conflict) aliasMap.set(row.aliasKey, row.canonicalKey);
  }
  const canonicalDays = new Map();
  for (const row of state.deviceDays?.values?.() || []) {
    const canonicalKey = aliasMap.get(row.deviceKey) || row.deviceKey;
    const key = `${row.day}\u0000${canonicalKey}`;
    const current = canonicalDays.get(key) || {
      day: row.day,
      deviceKey: canonicalKey,
      searched: 0,
      gotResult: 0,
      action: 0,
    };
    current.searched = Math.max(current.searched, row.searched ? 1 : 0);
    current.gotResult = Math.max(current.gotResult, row.gotResult ? 1 : 0);
    current.action = Math.max(current.action, row.action ? 1 : 0);
    canonicalDays.set(key, current);
  }
  const rows = new Map();
  const rowFor = (day) => {
    if (!rows.has(day)) rows.set(day, { day, active_devices: 0, search_devices: 0, result_devices: 0, action_devices: 0 });
    return rows.get(day);
  };
  for (const row of canonicalDays.values()) {
    const daily = rowFor(row.day);
    daily.active_devices += 1;
    daily.search_devices += row.searched;
    daily.result_devices += row.gotResult;
    daily.action_devices += row.action;
  }
  return [...rows.values()].sort((a, b) => a.day.localeCompare(b.day));
}

export function expectedVersionRows(state, days = 31, nowMs = Date.now()) {
  const minDay = opsDayKey(nowMs - (Math.max(1, Number(days) || 31) - 1) * DAY_MS);
  const groups = new Map();
  for (const row of state.deviceLatest?.values?.() || []) {
    if (!row.lastSeenDay || row.lastSeenDay < minDay) continue;
    const appV = row.appV || 'unknown';
    const versionCode = row.versionCode || '';
    const key = `${appV}\u0000${versionCode}`;
    const current = groups.get(key) || { app_v: appV, version_code: versionCode, devices: 0 };
    current.devices += 1;
    groups.set(key, current);
  }
  return [...groups.values()].sort((a, b) => b.devices - a.devices || a.app_v.localeCompare(b.app_v) || a.version_code.localeCompare(b.version_code));
}

export function expectedDailyRows(state) {
  const rows = new Map();
  const rowFor = (day) => {
    if (!rows.has(day)) {
      rows.set(day, {
        day,
        active_devices: 0,
        search_devices: 0,
        result_devices: 0,
        action_devices: 0,
        physical_installs: 0,
        sessions: 0,
        searches_submitted: 0,
        searches_completed: 0,
        searches_with_results: 0,
        zero_result_searches: 0,
      });
    }
    return rows.get(day);
  };

  for (const r of state.deviceDays.values()) {
    const d = rowFor(r.day);
    d.active_devices += 1;
    d.search_devices += r.searched ? 1 : 0;
    d.result_devices += r.gotResult ? 1 : 0;
    d.action_devices += r.action ? 1 : 0;
  }
  for (const r of state.installs.values()) rowFor(r.installDay).physical_installs += 1;
  for (const r of state.sessions.values()) rowFor(r.day).sessions += 1;
  for (const r of state.searches.values()) {
    if (r.submittedDay && r.submittedTs !== null) rowFor(r.submittedDay).searches_submitted += 1;
    if (r.completedDay && r.completedTs !== null) {
      const d = rowFor(r.completedDay);
      d.searches_completed += 1;
      if (Number(r.resultCount || 0) > 0) d.searches_with_results += 1;
      else d.zero_result_searches += 1;
    }
  }
  return [...rows.values()].sort((a, b) => a.day.localeCompare(b.day));
}

function sqlValue(value) {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'NULL';
    return String(Math.trunc(value));
  }
  return `'${String(value).replace(/'/g, "''")}'`;
}

function valuesSql(rows, columns) {
  return rows.map((row) => `(${columns.map((c) => sqlValue(row[c])).join(',')})`).join(',\n');
}

function chunks(rows, size) {
  const out = [];
  for (let i = 0; i < rows.length; i += size) out.push(rows.slice(i, i + size));
  return out;
}

export function buildBackfillStatements(state, metadata = {}) {
  const statements = [];
  const aliasRows = [...(state.aliases?.values?.() || [])];
  for (const rows of chunks(aliasRows, 100)) {
    statements.push(
      `INSERT INTO ops_device_aliases(alias_key,canonical_key,kind,last_seen_ts,conflict) VALUES\n${valuesSql(rows, ['aliasKey','canonicalKey','kind','lastSeenTs','conflict'])}\n`
      + `ON CONFLICT(alias_key) DO UPDATE SET last_seen_ts=MAX(ops_device_aliases.last_seen_ts,excluded.last_seen_ts),conflict=MAX(ops_device_aliases.conflict,CASE WHEN ops_device_aliases.canonical_key<>excluded.canonical_key THEN 1 ELSE excluded.conflict END),kind=CASE WHEN ops_device_aliases.kind='' THEN excluded.kind ELSE ops_device_aliases.kind END WHERE ops_device_aliases.canonical_key<>excluded.canonical_key OR excluded.conflict>ops_device_aliases.conflict OR (ops_device_aliases.kind='' AND excluded.kind<>'') OR excluded.last_seen_ts>ops_device_aliases.last_seen_ts;`
    );
  }
  const latestRows = [...(state.deviceLatest?.values?.() || [])];
  for (const rows of chunks(latestRows, 100)) {
    statements.push(
      `INSERT INTO ops_device_latest(device_key,last_seen_ts,last_seen_day,app_v,version_code,country) VALUES\n${valuesSql(rows, ['deviceKey','lastSeenTs','lastSeenDay','appV','versionCode','country'])}\n`
      + `ON CONFLICT(device_key) DO UPDATE SET last_seen_ts=excluded.last_seen_ts,last_seen_day=excluded.last_seen_day,app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_device_latest.app_v END,version_code=CASE WHEN excluded.version_code<>'' THEN excluded.version_code ELSE ops_device_latest.version_code END,country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_device_latest.country END WHERE excluded.last_seen_ts>ops_device_latest.last_seen_ts;`
    );
  }

  const deviceRows = [...state.deviceDays.values()];
  for (const rows of chunks(deviceRows, 100)) {
    statements.push(
      `INSERT INTO ops_device_days(day,device_key,first_event_ts,app_v,country,searched,got_result,action) VALUES\n${valuesSql(rows, ['day','deviceKey','firstTs','appV','country','searched','gotResult','action'])}\n`
      + `ON CONFLICT(day,device_key) DO UPDATE SET first_event_ts=MIN(ops_device_days.first_event_ts,excluded.first_event_ts),app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_device_days.app_v END,country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_device_days.country END,searched=MAX(ops_device_days.searched,excluded.searched),got_result=MAX(ops_device_days.got_result,excluded.got_result),action=MAX(ops_device_days.action,excluded.action) WHERE excluded.first_event_ts<ops_device_days.first_event_ts OR (excluded.app_v<>'' AND excluded.app_v<>ops_device_days.app_v) OR (excluded.country<>'' AND excluded.country<>ops_device_days.country) OR excluded.searched>ops_device_days.searched OR excluded.got_result>ops_device_days.got_result OR excluded.action>ops_device_days.action;`
    );
  }

  for (const rows of chunks([...state.installs.values()], 100)) {
    statements.push(
      `INSERT INTO ops_install_days(install_day,install_key,installation_ts,first_open_ts,app_v,country) VALUES\n${valuesSql(rows, ['installDay','installKey','installationTs','firstOpenTs','appV','country'])}\n`
      + `ON CONFLICT(install_key) DO UPDATE SET install_day=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts THEN excluded.install_day ELSE ops_install_days.install_day END,installation_ts=MIN(ops_install_days.installation_ts,excluded.installation_ts),first_open_ts=MIN(ops_install_days.first_open_ts,excluded.first_open_ts),app_v=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts AND excluded.app_v<>'' THEN excluded.app_v ELSE ops_install_days.app_v END,country=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts AND excluded.country<>'' THEN excluded.country ELSE ops_install_days.country END WHERE excluded.installation_ts<ops_install_days.installation_ts OR excluded.first_open_ts<ops_install_days.first_open_ts;`
    );
  }

  for (const rows of chunks([...state.sessions.values()], 100)) {
    statements.push(
      `INSERT INTO ops_session_days(day,session_id,device_key,first_event_ts,app_v,country) VALUES\n${valuesSql(rows, ['day','sessionId','deviceKey','firstTs','appV','country'])}\n`
      + `ON CONFLICT(day,session_id) DO UPDATE SET first_event_ts=MIN(ops_session_days.first_event_ts,excluded.first_event_ts),device_key=CASE WHEN excluded.device_key<>'' THEN excluded.device_key ELSE ops_session_days.device_key END,app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_session_days.app_v END,country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_session_days.country END WHERE excluded.first_event_ts<ops_session_days.first_event_ts OR (excluded.device_key<>'' AND excluded.device_key<>ops_session_days.device_key) OR (excluded.app_v<>'' AND excluded.app_v<>ops_session_days.app_v) OR (excluded.country<>'' AND excluded.country<>ops_session_days.country);`
    );
  }

  for (const rows of chunks([...state.searches.values()], 80)) {
    statements.push(
      `INSERT INTO ops_searches(search_id,device_key,submitted_day,submitted_ts,completed_day,completed_ts,result_count,ttfr_ms,action,app_v,country) VALUES\n${valuesSql(rows, ['searchId','deviceKey','submittedDay','submittedTs','completedDay','completedTs','resultCount','ttfrMs','action','appV','country'])}\n`
      + `ON CONFLICT(search_id) DO UPDATE SET device_key=CASE WHEN excluded.device_key<>'' THEN excluded.device_key ELSE ops_searches.device_key END,submitted_day=CASE WHEN ops_searches.submitted_ts IS NULL OR (excluded.submitted_ts IS NOT NULL AND excluded.submitted_ts<ops_searches.submitted_ts) THEN excluded.submitted_day ELSE ops_searches.submitted_day END,submitted_ts=CASE WHEN ops_searches.submitted_ts IS NULL OR (excluded.submitted_ts IS NOT NULL AND excluded.submitted_ts<ops_searches.submitted_ts) THEN excluded.submitted_ts ELSE ops_searches.submitted_ts END,completed_day=CASE WHEN ops_searches.completed_ts IS NULL OR (excluded.completed_ts IS NOT NULL AND excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.completed_day ELSE ops_searches.completed_day END,completed_ts=CASE WHEN ops_searches.completed_ts IS NULL OR (excluded.completed_ts IS NOT NULL AND excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.completed_ts ELSE ops_searches.completed_ts END,result_count=CASE WHEN excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.result_count ELSE ops_searches.result_count END,ttfr_ms=CASE WHEN excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.ttfr_ms ELSE ops_searches.ttfr_ms END,action=MAX(ops_searches.action,excluded.action),app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_searches.app_v END,country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE ops_searches.country END WHERE (excluded.device_key<>'' AND excluded.device_key<>ops_searches.device_key) OR (excluded.submitted_ts IS NOT NULL AND (ops_searches.submitted_ts IS NULL OR excluded.submitted_ts<ops_searches.submitted_ts)) OR (excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>ops_searches.completed_ts OR (excluded.completed_ts=ops_searches.completed_ts AND (COALESCE(excluded.result_count,-1)<>COALESCE(ops_searches.result_count,-1) OR COALESCE(excluded.ttfr_ms,-1)<>COALESCE(ops_searches.ttfr_ms,-1))))) OR excluded.action>ops_searches.action OR (excluded.app_v<>'' AND excluded.app_v<>ops_searches.app_v) OR (excluded.country<>'' AND excluded.country<>ops_searches.country);`
    );
  }

  statements.push(`INSERT INTO ops_daily(day,active_devices,search_devices,result_devices,action_devices,physical_installs,sessions,searches_submitted,searches_completed,searches_with_results,zero_result_searches)
SELECT d.day,
  (SELECT COUNT(*) FROM ops_device_days_exact x WHERE x.day=d.day),
  (SELECT COUNT(*) FROM ops_device_days_exact x WHERE x.day=d.day AND x.searched=1),
  (SELECT COUNT(*) FROM ops_device_days_exact x WHERE x.day=d.day AND x.got_result=1),
  (SELECT COUNT(*) FROM ops_device_days_exact x WHERE x.day=d.day AND x.action=1),
  (SELECT COUNT(*) FROM ops_install_days x WHERE x.install_day=d.day),
  (SELECT COUNT(*) FROM ops_session_days x WHERE x.day=d.day),
  (SELECT COUNT(*) FROM ops_searches x WHERE x.submitted_day=d.day AND x.submitted_ts IS NOT NULL),
  (SELECT COUNT(*) FROM ops_searches x WHERE x.completed_day=d.day AND x.completed_ts IS NOT NULL),
  (SELECT COUNT(*) FROM ops_searches x WHERE x.completed_day=d.day AND x.completed_ts IS NOT NULL AND COALESCE(x.result_count,0)>0),
  (SELECT COUNT(*) FROM ops_searches x WHERE x.completed_day=d.day AND x.completed_ts IS NOT NULL AND COALESCE(x.result_count,0)=0)
FROM (
  SELECT day FROM ops_device_days
  UNION SELECT install_day AS day FROM ops_install_days
  UNION SELECT day FROM ops_session_days
  UNION SELECT submitted_day AS day FROM ops_searches WHERE submitted_day IS NOT NULL
  UNION SELECT completed_day AS day FROM ops_searches WHERE completed_day IS NOT NULL
) d
WHERE d.day IS NOT NULL
ON CONFLICT(day) DO UPDATE SET active_devices=excluded.active_devices,search_devices=excluded.search_devices,result_devices=excluded.result_devices,action_devices=excluded.action_devices,physical_installs=excluded.physical_installs,sessions=excluded.sessions,searches_submitted=excluded.searches_submitted,searches_completed=excluded.searches_completed,searches_with_results=excluded.searches_with_results,zero_result_searches=excluded.zero_result_searches WHERE ops_daily.active_devices<>excluded.active_devices OR ops_daily.search_devices<>excluded.search_devices OR ops_daily.result_devices<>excluded.result_devices OR ops_daily.action_devices<>excluded.action_devices OR ops_daily.physical_installs<>excluded.physical_installs OR ops_daily.sessions<>excluded.sessions OR ops_daily.searches_submitted<>excluded.searches_submitted OR ops_daily.searches_completed<>excluded.searches_completed OR ops_daily.searches_with_results<>excluded.searches_with_results OR ops_daily.zero_result_searches<>excluded.zero_result_searches;`);

  const meta = JSON.stringify({
    status: 'complete',
    inventoryVerified: true,
    inventoryDays: Number(metadata.inventoryDays || 0),
    sourceCachedAt: String(metadata.sourceCachedAt || ''),
    sourceBatchCount: Number(metadata.sourceBatchCount || 0),
    generatedAt: new Date().toISOString(),
  });
  statements.push(`INSERT INTO ops_index_meta(key,value,updated_at) VALUES('backfill_complete',${sqlValue(meta)},${Date.now()}) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at;`);
  return statements;
}

export function recentRows(rows, days = 31, nowMs = Date.now()) {
  const minDay = opsDayKey(nowMs - (days - 1) * DAY_MS);
  return rows.filter((row) => row.day >= minDay);
}
