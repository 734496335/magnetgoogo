-- Prospective privacy-safe acquisition funnel read model.
-- Stores only finite acquisition source categories; no raw referrer, UTM, query,
-- user/device identifier, or visitor join is persisted here.
CREATE TABLE IF NOT EXISTS growth_attribution_daily_dims (
  day TEXT NOT NULL,
  event_type TEXT NOT NULL,
  page TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'unknown',
  locale TEXT NOT NULL DEFAULT '',
  placement TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  event_count INTEGER NOT NULL DEFAULT 0,
  first_ts INTEGER NOT NULL,
  last_ts INTEGER NOT NULL,
  PRIMARY KEY (
    day,
    event_type,
    page,
    source,
    locale,
    placement,
    country
  )
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_growth_attribution_day_source_type
ON growth_attribution_daily_dims(day, source, event_type);

CREATE INDEX IF NOT EXISTS idx_growth_attribution_page_day
ON growth_attribution_daily_dims(page, day);

PRAGMA optimize;
