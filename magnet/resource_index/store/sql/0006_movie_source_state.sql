-- resource_index schema version 0006

CREATE TABLE IF NOT EXISTS movie_external_resources (
    resource_id TEXT PRIMARY KEY,
    movie_id TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('download', 'player')),
    provider TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    display_title TEXT NOT NULL,
    quality_tags_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(movie_id, resource_url),
    FOREIGN KEY(movie_id) REFERENCES movie_items(movie_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_movie_external_resources_movie
    ON movie_external_resources(movie_id, resource_type, provider);

CREATE TABLE IF NOT EXISTS movie_source_state (
    source_id TEXT PRIMARY KEY,
    last_attempt_at TEXT,
    last_completed_at TEXT,
    last_snapshot_hash TEXT,
    daily_budget_date TEXT NOT NULL,
    daily_reserved_requests INTEGER NOT NULL DEFAULT 0 CHECK (daily_reserved_requests >= 0),
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    updated_at TEXT NOT NULL
);
