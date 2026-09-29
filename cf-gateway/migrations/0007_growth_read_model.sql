-- Compact, rebuildable website-growth read model.
-- R2 remains the immutable raw fact source; this table exists only so Admin
-- reads stay O(days × dimensions) instead of O(raw growth objects).
CREATE TABLE IF NOT EXISTS growth_daily_dims (
  day TEXT NOT NULL,
  event_type TEXT NOT NULL,
  page TEXT NOT NULL DEFAULT '',
  locale TEXT NOT NULL DEFAULT '',
  placement TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  requested_version TEXT NOT NULL DEFAULT '',
  target_version TEXT NOT NULL DEFAULT '',
  event_count INTEGER NOT NULL DEFAULT 0,
  first_ts INTEGER NOT NULL,
  last_ts INTEGER NOT NULL,
  PRIMARY KEY (
    day,
    event_type,
    page,
    locale,
    placement,
    country,
    requested_version,
    target_version
  )
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_growth_daily_dims_day_type
ON growth_daily_dims(day, event_type);

CREATE INDEX IF NOT EXISTS idx_growth_daily_dims_page_day
ON growth_daily_dims(page, day);

PRAGMA optimize;
