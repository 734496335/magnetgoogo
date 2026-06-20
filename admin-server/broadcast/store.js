const Database = require('better-sqlite3');
const path = require('path');
const crypto = require('crypto');
const { canonicalPlatform, resolveAccount, loadConfig: loadConfigFromCfg } = require('./config');

// P2-10: Support BROADCAST_DB_PATH env var for test isolation
const dbPath = process.env.BROADCAST_DB_PATH || path.resolve(__dirname, '..', 'broadcast.db');
const db = new Database(dbPath);

db.pragma('journal_mode = WAL');
db.pragma('busy_timeout = 5000');

db.exec(`
  CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY,
    platform TEXT,
    kind TEXT,
    title TEXT,
    body TEXT,
    vars_json TEXT,
    status TEXT DEFAULT 'draft',
    created_at TEXT,
    approved_at TEXT
  );
  CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT,
    platform TEXT,
    account TEXT,
    template_id INTEGER,
    payload_json TEXT,
    scheduled_at TEXT,
    status TEXT DEFAULT 'queued',
    result_json TEXT,
    created_at TEXT,
    updated_at TEXT
  );
  CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    job_id INTEGER,
    platform TEXT,
    account TEXT,
    action TEXT,
    content_hash TEXT,
    status TEXT,
    detail TEXT,
    ts TEXT
  );
  CREATE TABLE IF NOT EXISTS discovered_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    post_url TEXT NOT NULL UNIQUE,
    post_title TEXT,
    post_excerpt TEXT,
    search_query TEXT,
    relevance_score REAL DEFAULT 0,
    status TEXT DEFAULT 'new',
    reply_job_id INTEGER,
    discovered_at TEXT DEFAULT (datetime('now')),
    replied_at TEXT
  );
  CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'draft',
    source_type TEXT,
    source_id TEXT,
    template_id INTEGER,
    total_items INTEGER DEFAULT 0,
    done_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    payload_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT,
    started_at TEXT,
    completed_at TEXT
  );
`);

/** Add a column to an existing table; silently ignore "duplicate column" errors. */
function safeAddColumn(table, colDef) {
  try {
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${colDef}`);
  } catch (err) {
    if (!/duplicate column/i.test(err.message)) throw err;
  }
}

// -- backward-compatible migrations -----------------------------------------
// AUDIT-04: Use user_version pragma as idempotent migration marker
const currentVersion = db.pragma('user_version', { simple: true });

// Migration v1: jobs columns for retry/defer/task tracking
if (currentVersion < 1) {
  safeAddColumn('jobs', 'retry_count INTEGER DEFAULT 0');
  safeAddColumn('jobs', 'tier_used TEXT');
  safeAddColumn('jobs', 'last_error TEXT');
  safeAddColumn('jobs', 'task_id INTEGER');
  safeAddColumn('jobs', 'defer_count INTEGER DEFAULT 0');

  db.pragma('user_version = 1');
  console.log('[store] Migration v1 applied: jobs retry/defer/task columns');
}

// Migration v2: discovered_posts columns for generation retry tracking
if (currentVersion < 2) {
  safeAddColumn('discovered_posts', 'last_attempt_at TEXT');
  safeAddColumn('discovered_posts', 'generation_retry_count INTEGER DEFAULT 0');

  // Index for fast lookup by reply_job_id (used in task approve/reject)
  db.exec('CREATE INDEX IF NOT EXISTS idx_discovered_posts_reply_job_id ON discovered_posts(reply_job_id)');

  db.pragma('user_version = 2');
  console.log('[store] Migration v2 applied: discovered_posts retry columns + index');
}

// Startup self-heal: even if user_version >= 2, ensure FR-10 columns exist.
// Guards against intermediate versions that bumped user_version without adding these columns.
{
  const cols = db.pragma('table_info(discovered_posts)').map(c => c.name);
  const missing = [];
  if (!cols.includes('last_attempt_at')) {
    safeAddColumn('discovered_posts', 'last_attempt_at TEXT');
    missing.push('last_attempt_at');
  }
  if (!cols.includes('generation_retry_count')) {
    safeAddColumn('discovered_posts', 'generation_retry_count INTEGER DEFAULT 0');
    missing.push('generation_retry_count');
  }
  if (missing.length > 0) {
    console.warn(`[store] Self-heal: added missing discovered_posts columns: ${missing.join(', ')}`);
  }
}

// FR-01/FR-09: One-time migration — canonicalize platform + resolve 'default' accounts in active jobs
(function migrateIdentityNormalization() {
  try {
    // Idempotency guard: skip if already run
    db.exec('CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)');
    const row = db.prepare('SELECT value FROM _meta WHERE key = ?').get('fr01_fr09_migration_done');
    if (row) return;

    const cfg = loadConfigFromCfg();

    // Migrate active jobs: canonicalize platform + resolve account
    const activeJobs = db.prepare("SELECT id, platform, account FROM jobs WHERE (account = 'default' OR platform IN ('twitter','testplatform')) AND status IN ('queued','running','awaiting_approval')").all();
    let migrated = 0;
    const updateJobStmt = db.prepare('UPDATE jobs SET platform = ?, account = ? WHERE id = ?');
    for (const job of activeJobs) {
      const canonPlatform = canonicalPlatform(job.platform);
      const resolvedAccount = resolveAccount(canonPlatform, job.account === 'default' ? null : job.account, cfg);
      if (resolvedAccount !== job.account || canonPlatform !== job.platform) {
        updateJobStmt.run(canonPlatform, resolvedAccount, job.id);
        migrated++;
      }
    }
    if (migrated > 0) {
      console.log(`[store] FR-01/FR-09 migration: canonicalized ${migrated} active jobs`);
    }

    // Migrate logs: canonicalize platform names
    const logMigrations = Object.entries(require('./config').PLATFORM_ALIASES || {});
    let logsMigrated = 0;
    for (const [from, to] of logMigrations) {
      const info = db.prepare('UPDATE logs SET platform = ? WHERE platform = ?').run(to, from);
      logsMigrated += info.changes;
    }
    if (logsMigrated > 0) {
      console.log(`[store] FR-09 migration: canonicalized ${logsMigrated} log rows`);
    }

    // Migrate logs: resolve stale 'default' account to current config profile
    // Without this, countActionsToday/lastActionTs use the resolved account name
    // but historical log entries still have 'default', bypassing daily rate limits.
    const platforms = new Set();
    const platformAcctMap = new Map(); // platform -> resolved account
    for (const row of db.prepare('SELECT DISTINCT platform FROM logs WHERE account = ?').all('default')) {
      platforms.add(row.platform);
    }
    for (const plat of platforms) {
      const canonPlatform = canonicalPlatform(plat);
      const resolvedAccount = resolveAccount(canonPlatform, null, cfg);
      platformAcctMap.set(plat, resolvedAccount);
    }
    let logAcctMigrated = 0;
    for (const [plat, acct] of platformAcctMap) {
      const info = db.prepare("UPDATE logs SET account = ? WHERE platform = ? AND account = 'default'").run(acct, plat);
      logAcctMigrated += info.changes;
    }
    if (logAcctMigrated > 0) {
      console.log(`[store] FR-09 migration: resolved ${logAcctMigrated} log rows from 'default' account`);
    }

    // Migrate discovered_posts: canonicalize platform names
    let postsMigrated = 0;
    for (const [from, to] of logMigrations) {
      const info = db.prepare('UPDATE discovered_posts SET platform = ? WHERE platform = ?').run(to, from);
      postsMigrated += info.changes;
    }
    if (postsMigrated > 0) {
      console.log(`[store] FR-09 migration: canonicalized ${postsMigrated} discovered_posts rows`);
    }

    // Mark migration as done (using _meta, not user_version — schema migrations own user_version)
    db.prepare('INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)').run('fr01_fr09_migration_done', new Date().toISOString());
    console.log('[store] FR-01/FR-09 migration complete — marked as done');
  } catch (err) {
    console.error('[store] FR-01/FR-09 migration error (non-fatal):', err.message);
  }
})();

const now = () => new Date().toISOString();
const toJson = (v) => (v == null ? null : typeof v === 'string' ? v : JSON.stringify(v));

const stmt = {
  insertTpl: db.prepare(
    'INSERT INTO templates (platform,kind,title,body,vars_json,created_at) VALUES (?,?,?,?,?,?)'
  ),
  getTpl: db.prepare('SELECT * FROM templates WHERE id=?'),
  setTplStatus: db.prepare('UPDATE templates SET status=? WHERE id=?'),
  setTplApproved: db.prepare('UPDATE templates SET status=?,approved_at=? WHERE id=?'),
  insertJob: db.prepare(
    'INSERT INTO jobs (campaign_id,platform,account,template_id,payload_json,scheduled_at,status,task_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)'
  ),
  getJob: db.prepare('SELECT * FROM jobs WHERE id=?'),
  insertLog: db.prepare(
    'INSERT INTO logs (job_id,platform,account,action,content_hash,status,detail,ts) VALUES (?,?,?,?,?,?,?,?)'
  ),
  countToday: db.prepare(
    "SELECT COUNT(*) AS cnt FROM logs WHERE platform=? AND account=? AND status='done' AND ts>=? AND ts<?"
  ),
  lastTs: db.prepare(
    "SELECT ts FROM logs WHERE platform=? AND account=? AND status='done' ORDER BY ts DESC LIMIT 1"
  ),
};

function todayRange() {
  const d = new Date();
  return [
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).toISOString(),
    new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1).toISOString(),
  ];
}

/* templates */
function createTemplate(t) {
  const ts = now();
  const info = stmt.insertTpl.run(t.platform, t.kind, t.title || null, t.body || null, toJson(t.vars_json), ts);
  return { id: Number(info.lastInsertRowid), platform: t.platform, kind: t.kind, title: t.title || null, body: t.body || null, vars_json: toJson(t.vars_json), status: 'draft', created_at: ts, approved_at: null };
}

function listTemplates(filter = {}) {
  let sql = 'SELECT * FROM templates';
  const conds = [];
  const params = [];
  if (filter.platform) { conds.push('platform=?'); params.push(filter.platform); }
  if (filter.status) { conds.push('status=?'); params.push(filter.status); }
  if (conds.length) sql += ' WHERE ' + conds.join(' AND ');
  return db.prepare(sql + ' ORDER BY id DESC').all(...params);
}

function getTemplate(id) {
  return stmt.getTpl.get(id) || null;
}

function setTemplateStatus(id, status) {
  if (status === 'approved') {
    stmt.setTplApproved.run(status, now(), id);
  } else {
    stmt.setTplStatus.run(status, id);
  }
}

/* jobs */
function createJob(j) {
  // Max queue size check
  const queuedCount = db.prepare("SELECT COUNT(*) AS cnt FROM jobs WHERE status IN ('queued','awaiting_approval','running')").get();
  if (queuedCount && queuedCount.cnt >= MAX_QUEUE_SIZE) {
    throw new Error(`Queue size limit reached (${MAX_QUEUE_SIZE}). Cannot create more jobs.`);
  }

  // FR-09: Canonicalize platform for internal bookkeeping (locks, rate limits, DB)
  const platform = canonicalPlatform(j.platform);

  // FR-01: Resolve account — never store 'default', use real profile from config
  const cfg = loadConfigFromCfg();
  const account = resolveAccount(platform, j.account, cfg);

  const ts = now();
  const status = j.status || 'queued';
  const info = stmt.insertJob.run(
    j.campaign_id || null, platform, account,
    j.template_id || null, toJson(j.payload_json), j.scheduled_at || null,
    status, j.task_id || null, ts, ts
  );
  // FR-06: Return DB-consistent row (payload_json stays a string)
  return getJob(Number(info.lastInsertRowid));
}

function listJobs(filter = {}) {
  let sql = 'SELECT * FROM jobs';
  const conds = [];
  const params = [];
  if (filter.status) { conds.push('status=?'); params.push(filter.status); }
  if (filter.platform) { conds.push('platform=?'); params.push(canonicalPlatform(filter.platform)); }
  if (filter.campaign_id) { conds.push('campaign_id=?'); params.push(filter.campaign_id); }
  if (conds.length) sql += ' WHERE ' + conds.join(' AND ');
  return db.prepare(sql + ' ORDER BY id DESC').all(...params);
}

function getJob(id) {
  return stmt.getJob.get(id) || null;
}

function updateJob(id, patch) {
  const cols = ['campaign_id','platform','account','template_id','payload_json','scheduled_at','status','result_json','retry_count','tier_used','last_error','defer_count'];
  const sets = [];
  const params = [];
  for (const c of cols) {
    if (patch[c] !== undefined) {
      sets.push(c + '=?');
      params.push(c.endsWith('_json') ? toJson(patch[c]) : patch[c]);
    }
  }
  if (!sets.length) return;
  sets.push('updated_at=?');
  params.push(now());
  params.push(id);
  db.prepare('UPDATE jobs SET ' + sets.join(',') + ' WHERE id=?').run(...params);
}

/* logs */
function addLog(l) {
  const ts = l.ts || now();
  const info = stmt.insertLog.run(
    l.job_id || null, l.platform, l.account || null, l.action,
    l.content_hash || null, l.status, l.detail || null, ts
  );
  return { id: Number(info.lastInsertRowid), ts, ...l };
}

function listLogs(filter = {}) {
  let sql = 'SELECT * FROM logs';
  const conds = [];
  const params = [];
  if (filter.platform) { conds.push('platform=?'); params.push(canonicalPlatform(filter.platform)); }
  if (filter.account) { conds.push('account=?'); params.push(filter.account); }
  if (filter.job_id != null) { conds.push('job_id=?'); params.push(filter.job_id); }
  if (filter.status) { conds.push('status=?'); params.push(filter.status); }
  if (conds.length) sql += ' WHERE ' + conds.join(' AND ');
  return db.prepare(sql + ' ORDER BY id DESC').all(...params);
}

/* rate helpers */
function countActionsToday(platform, account) {
  const [start, end] = todayRange();
  const row = stmt.countToday.get(platform, account, start, end);
  return row ? row.cnt : 0;
}

function lastActionTs(platform, account) {
  const row = stmt.lastTs.get(platform, account);
  return row ? row.ts : null;
}

function hashContent(str) {
  return crypto.createHash('sha1').update(str).digest('hex');
}

/** Reset jobs stuck in 'running' from a previous crash. */
function resetRunningJobs() {
  const info = db.prepare("UPDATE jobs SET status='queued' WHERE status='running'").run();
  if (info.changes > 0) {
    console.log(`[store] Recovered ${info.changes} stuck 'running' jobs back to 'queued'`);
  }
}

function jobStatusCounts() {
  const rows = db.prepare('SELECT status, COUNT(*) AS cnt FROM jobs GROUP BY status').all();
  const m = {};
  for (const r of rows) m[r.status] = r.cnt;
  return m;
}

function hasRunningJob(platform, account) {
  // FR-09: Canonicalize platform so 'x' and 'twitter' share the same lock
  const canonPlatform = canonicalPlatform(platform);
  const row = db.prepare("SELECT COUNT(*) AS cnt FROM jobs WHERE platform=? AND account=? AND status='running'").get(canonPlatform, account || 'default');
  return row ? row.cnt > 0 : false;
}

// Discovery CRUD
function upsertDiscoveredPost(post) {
  // post: { platform, post_url, post_title, post_excerpt, search_query, relevance_score, status }
  // Uses INSERT OR IGNORE + UPDATE pattern
  const existing = db.prepare('SELECT id FROM discovered_posts WHERE post_url = ?').get(post.post_url);
  if (existing) return existing.id;
  const info = db.prepare(
    'INSERT INTO discovered_posts (platform, post_url, post_title, post_excerpt, search_query, relevance_score, status) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(post.platform, post.post_url, post.post_title || '', post.post_excerpt || '', post.search_query || '', post.relevance_score || 0, post.status || 'new');
  return info.lastInsertRowid;
}

function listDiscoveredPosts(filters = {}) {
  let sql = 'SELECT * FROM discovered_posts WHERE 1=1';
  const params = [];
  if (filters.platform) { sql += ' AND platform = ?'; params.push(filters.platform); }
  if (filters.status) { sql += ' AND status = ?'; params.push(filters.status); }
  sql += ' ORDER BY discovered_at DESC';
  if (filters.limit) { sql += ' LIMIT ?'; params.push(filters.limit); }
  return db.prepare(sql).all(...params);
}

function updateDiscoveredPost(id, updates) {
  const allowed = ['status', 'reply_job_id', 'replied_at', 'relevance_score', 'last_attempt_at', 'generation_retry_count'];
  const sets = [];
  const vals = [];
  for (const [k, v] of Object.entries(updates)) {
    if (allowed.includes(k)) { sets.push(`${k} = ?`); vals.push(v); }
  }
  if (sets.length === 0) return;
  vals.push(id);
  db.prepare(`UPDATE discovered_posts SET ${sets.join(', ')} WHERE id = ?`).run(...vals);
}

function getDiscoveredByUrl(url) {
  return db.prepare('SELECT * FROM discovered_posts WHERE post_url = ?').get(url);
}

function getDiscoveredByReplyJobId(jobId) {
  return db.prepare('SELECT * FROM discovered_posts WHERE reply_job_id = ?').get(jobId);
}

/**
 * Map a job status to the corresponding discovered_post status.
 * Keeps discovery post status in sync with the job lifecycle.
 * Shared by discovery.js and index.js to avoid circular imports.
 */
function discoveredStatusForJobStatus(jobStatus) {
  switch (jobStatus) {
    case 'awaiting_approval': return 'pending_approval';
    case 'queued':            return 'queued';
    case 'running':           return 'queued';
    case 'done':              return 'replied';
    case 'failed':            return 'error';
    case 'rejected':          return 'rejected';
    default:                  return 'queued';
  }
}

const MAX_QUEUE_SIZE = 500;

/* tasks */
function createTask(t) {
  const info = db.prepare(
    "INSERT INTO tasks (name, platform, description, status, source_type, source_id, template_id, total_items, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))"
  ).run(t.name, t.platform, t.description || '', t.status || 'draft', t.source_type || null, t.source_id || null, t.template_id || null, t.total_items || 0, t.payload_json || null);
  return info.lastInsertRowid;
}

function listTasks(filters = {}) {
  let sql = 'SELECT * FROM tasks WHERE 1=1';
  const params = [];
  if (filters.status) { sql += ' AND status = ?'; params.push(filters.status); }
  if (filters.platform) { sql += ' AND platform = ?'; params.push(filters.platform); }
  if (filters.source_type) { sql += ' AND source_type = ?'; params.push(filters.source_type); }
  sql += ' ORDER BY id DESC';
  return db.prepare(sql).all(...params);
}

function getTask(id) {
  return db.prepare('SELECT * FROM tasks WHERE id = ?').get(id);
}

function updateTask(id, updates) {
  const allowed = ['name','description','status','total_items','done_items','failed_items','started_at','completed_at','updated_at'];
  const sets = ["updated_at = datetime('now')"];
  const vals = [];
  for (const [k, v] of Object.entries(updates)) {
    if (allowed.includes(k)) { sets.push(`${k} = ?`); vals.push(v); }
  }
  vals.push(id);
  db.prepare(`UPDATE tasks SET ${sets.join(', ')} WHERE id = ?`).run(...vals);
}

function deleteTask(id) {
  db.prepare('DELETE FROM jobs WHERE task_id = ?').run(id);
  db.prepare('DELETE FROM tasks WHERE id = ?').run(id);
}

function getTaskJobs(taskId) {
  return db.prepare('SELECT * FROM jobs WHERE task_id = ? ORDER BY id').all(taskId);
}

function refreshTaskCounts(taskId) {
  // PFC-01: Count ALL job statuses for proper task state derivation
  const row = db.prepare(
    `SELECT COUNT(*) as total,
      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
      SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
      SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected,
      SUM(CASE WHEN status='awaiting_approval' THEN 1 ELSE 0 END) as awaiting,
      SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) as queued,
      SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) as running,
      SUM(CASE WHEN status='paused' THEN 1 ELSE 0 END) as paused,
      SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) as skipped,
      SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled
    FROM jobs WHERE task_id = ?`
  ).get(taskId);

  if (!row || row.total === 0) return;

  // Update counts — rejected counts toward failed_items
  const failedPlusRejected = (row.failed || 0) + (row.rejected || 0);
  updateTask(taskId, {
    total_items: row.total,
    done_items: row.done || 0,
    failed_items: failedPlusRejected,
  });

  // Do not overwrite cancelled tasks
  const task = getTask(taskId);
  if (task && task.status === 'cancelled') return;

  // Derive task status from job states (priority: active > paused > terminal)
  const terminalCount = (row.done || 0) + (row.failed || 0) + (row.rejected || 0) + (row.skipped || 0) + (row.cancelled || 0);
  const allTerminal = terminalCount >= row.total;

  let newStatus = null;
  if (allTerminal) {
    // All jobs finished
    if (failedPlusRejected >= row.total) {
      newStatus = 'failed';
    } else {
      newStatus = 'done';
    }
  } else if ((row.running || 0) > 0) {
    newStatus = 'running';
  } else if ((row.awaiting || 0) > 0) {
    newStatus = 'awaiting_approval';
  } else if ((row.queued || 0) > 0) {
    newStatus = 'queued';
  } else if ((row.paused || 0) > 0) {
    newStatus = 'paused';
  }

  if (newStatus) {
    const patch = { status: newStatus };
    if (allTerminal && !task.completed_at) {
      patch.completed_at = new Date().toISOString();
    }
    updateTask(taskId, patch);
  }
}

module.exports = {
  createTemplate, listTemplates, getTemplate, setTemplateStatus,
  createJob, listJobs, getJob, updateJob,
  addLog, listLogs,
  countActionsToday, lastActionTs, hashContent,
  jobStatusCounts, resetRunningJobs, hasRunningJob,
  upsertDiscoveredPost, listDiscoveredPosts, updateDiscoveredPost, getDiscoveredByUrl, getDiscoveredByReplyJobId,
  discoveredStatusForJobStatus,
  createTask, listTasks, getTask, updateTask, deleteTask, getTaskJobs, refreshTaskCounts,
  cleanupTestRows(platform) {
    db.prepare('DELETE FROM templates WHERE platform = ?').run(platform);
    db.prepare('DELETE FROM jobs WHERE platform = ?').run(platform);
    db.prepare('DELETE FROM logs WHERE platform = ?').run(platform);
  },
};
