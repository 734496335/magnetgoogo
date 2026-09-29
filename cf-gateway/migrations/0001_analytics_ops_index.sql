PRAGMA foreign_keys = ON;

-- Compact, rebuildable operational index. R2 remains the immutable source of
-- truth. Rollups are maintained explicitly by the Worker instead of SQLite
-- triggers so Wrangler/D1 migrations stay portable and replay semantics remain
-- visible in application code.
CREATE TABLE IF NOT EXISTS ops_daily (
  day TEXT PRIMARY KEY,
  active_devices INTEGER NOT NULL DEFAULT 0,
  search_devices INTEGER NOT NULL DEFAULT 0,
  result_devices INTEGER NOT NULL DEFAULT 0,
  action_devices INTEGER NOT NULL DEFAULT 0,
  physical_installs INTEGER NOT NULL DEFAULT 0,
  sessions INTEGER NOT NULL DEFAULT 0,
  searches_submitted INTEGER NOT NULL DEFAULT 0,
  searches_completed INTEGER NOT NULL DEFAULT 0,
  searches_with_results INTEGER NOT NULL DEFAULT 0,
  zero_result_searches INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ops_device_days (
  day TEXT NOT NULL,
  device_key TEXT NOT NULL,
  first_event_ts INTEGER NOT NULL,
  app_v TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  searched INTEGER NOT NULL DEFAULT 0 CHECK (searched IN (0, 1)),
  got_result INTEGER NOT NULL DEFAULT 0 CHECK (got_result IN (0, 1)),
  action INTEGER NOT NULL DEFAULT 0 CHECK (action IN (0, 1)),
  PRIMARY KEY (day, device_key)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ops_install_days (
  install_day TEXT NOT NULL,
  install_key TEXT NOT NULL,
  installation_ts INTEGER NOT NULL,
  first_open_ts INTEGER NOT NULL,
  app_v TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (install_day, install_key)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ops_session_days (
  day TEXT NOT NULL,
  session_id TEXT NOT NULL,
  device_key TEXT NOT NULL DEFAULT '',
  first_event_ts INTEGER NOT NULL,
  app_v TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (day, session_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ops_searches (
  search_id TEXT PRIMARY KEY,
  device_key TEXT NOT NULL DEFAULT '',
  submitted_day TEXT,
  submitted_ts INTEGER,
  completed_day TEXT,
  completed_ts INTEGER,
  result_count INTEGER,
  ttfr_ms INTEGER,
  action INTEGER NOT NULL DEFAULT 0 CHECK (action IN (0, 1)),
  app_v TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT ''
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_ops_searches_submitted_day ON ops_searches(submitted_day);
CREATE INDEX IF NOT EXISTS idx_ops_searches_completed_day ON ops_searches(completed_day);

CREATE TABLE IF NOT EXISTS ops_index_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
) WITHOUT ROWID;
