-- Canonical device aliases make the operational DAU a server-verifiable device
-- identity metric instead of a raw legacy installation-id count. Only strong
-- schema-v2 android_id_hash aliases are populated by the Worker/backfill.
CREATE TABLE IF NOT EXISTS ops_device_aliases (
  alias_key TEXT PRIMARY KEY,
  canonical_key TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT '',
  last_seen_ts INTEGER NOT NULL DEFAULT 0,
  conflict INTEGER NOT NULL DEFAULT 0 CHECK (conflict IN (0, 1))
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_ops_device_aliases_canonical
ON ops_device_aliases(canonical_key, conflict);

-- This exact view is diagnostic/repair authority. The public Worker uses the
-- same canonical grouping with a bounded day filter for predictable read cost.
CREATE VIEW IF NOT EXISTS ops_device_days_exact AS
SELECT
  d.day AS day,
  COALESCE(a.canonical_key, d.device_key) AS device_key,
  MIN(d.first_event_ts) AS first_event_ts,
  CASE
    WHEN MAX(CASE WHEN d.country='CN' THEN 1 ELSE 0 END)=1 THEN 'CN'
    ELSE MAX(CASE WHEN d.country<>'' THEN d.country ELSE '' END)
  END AS country,
  MAX(d.searched) AS searched,
  MAX(d.got_result) AS got_result,
  MAX(d.action) AS action
FROM ops_device_days d
LEFT JOIN ops_device_aliases a
  ON a.alias_key=d.device_key AND a.conflict=0
GROUP BY d.day, COALESCE(a.canonical_key, d.device_key);

PRAGMA optimize;
