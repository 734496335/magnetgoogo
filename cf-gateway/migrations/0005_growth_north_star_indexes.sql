-- Growth north-star queries stay on compact D1 identities, never raw R2 objects.
-- device_key/day supports first-observed and D7 satisfied-return lookups.
CREATE INDEX IF NOT EXISTS idx_ops_device_days_device_day_action
ON ops_device_days(device_key, day, action);

-- Search-satisfaction analysis is keyed by submit day while distinguishing
-- fully exhausted searches from searches where the user already acted early.
CREATE INDEX IF NOT EXISTS idx_ops_searches_submitted_action_completed
ON ops_searches(submitted_day, action, completed_ts);

PRAGMA optimize;
