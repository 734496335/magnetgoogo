-- Verified first-party growth lower bound.
-- Only CTA requests whose browser Referer is the production magnetgoogo.com
-- site enter this table. Raw/direct/unverified requests remain in R2 and in
-- growth_daily_dims for audit, but cannot drive CRO/SEO experiments.
CREATE TABLE IF NOT EXISTS growth_first_party_daily_dims (
  day TEXT NOT NULL,
  event_type TEXT NOT NULL,
  source_page TEXT NOT NULL DEFAULT '',
  locale TEXT NOT NULL DEFAULT '',
  placement TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  target_version TEXT NOT NULL DEFAULT '',
  event_count INTEGER NOT NULL DEFAULT 0,
  first_ts INTEGER NOT NULL,
  last_ts INTEGER NOT NULL,
  PRIMARY KEY (
    day,
    event_type,
    source_page,
    locale,
    placement,
    country,
    target_version
  )
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_growth_first_party_day_type
ON growth_first_party_daily_dims(day, event_type);

CREATE INDEX IF NOT EXISTS idx_growth_first_party_page_day
ON growth_first_party_daily_dims(source_page, day);

PRAGMA optimize;
