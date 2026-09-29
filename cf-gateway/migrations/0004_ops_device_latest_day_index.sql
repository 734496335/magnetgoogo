-- Version distribution uses the UTC+8 operational-day window. Store/index the
-- latest observed operational day so repeat batches on the same day can be true
-- no-op writes while the 31-day query remains index-bounded.
ALTER TABLE ops_device_latest ADD COLUMN last_seen_day TEXT NOT NULL DEFAULT '';
UPDATE ops_device_latest
SET last_seen_day = strftime('%Y-%m-%d', (last_seen_ts / 1000) + (8 * 3600), 'unixepoch')
WHERE last_seen_day = '';
CREATE INDEX IF NOT EXISTS idx_ops_device_latest_last_seen_day
ON ops_device_latest(last_seen_day);
