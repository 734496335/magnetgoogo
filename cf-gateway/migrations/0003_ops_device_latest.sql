-- Latest observed App version per anonymous device. This is a compact operational
-- read model for version distribution; raw telemetry remains authoritative in R2.
CREATE TABLE IF NOT EXISTS ops_device_latest (
  device_key TEXT PRIMARY KEY,
  last_seen_ts INTEGER NOT NULL,
  app_v TEXT NOT NULL DEFAULT '',
  version_code TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT ''
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_ops_device_latest_last_seen_ts
  ON ops_device_latest(last_seen_ts);

PRAGMA optimize;
