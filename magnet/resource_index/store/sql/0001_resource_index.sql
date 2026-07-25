-- resource_index schema version 0001

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_items (
    content_id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,
    content_code TEXT NOT NULL,
    raw_content_code TEXT NOT NULL,
    title TEXT NOT NULL,
    original_title TEXT,
    release_date TEXT,
    duration_minutes INTEGER,
    maker_name TEXT,
    publisher_name TEXT,
    label_name TEXT,
    series_name TEXT,
    cover_source_url TEXT,
    detail_url TEXT NOT NULL,
    adult INTEGER NOT NULL CHECK (adult = 1),
    source_id TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    risk_status TEXT NOT NULL DEFAULT 'manual_review',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(content_type, content_code),
    UNIQUE(source_id, source_item_key)
);

CREATE TABLE IF NOT EXISTS content_aliases (
    content_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(content_id, normalized_alias, alias_type),
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS people (
    person_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    source_profile_url TEXT,
    source_external_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_people (
    content_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    role TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY(content_id, person_id, role),
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES people(person_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    tag_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    source_url TEXT,
    source_external_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_tags (
    content_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    PRIMARY KEY(content_id, tag_id),
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_assets (
    media_id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    stored_url TEXT,
    content_hash TEXT,
    width INTEGER,
    height INTEGER,
    adult INTEGER NOT NULL CHECK (adult = 1),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(content_id, media_type, source_url),
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS resource_releases (
    resource_id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    info_hash TEXT NOT NULL UNIQUE,
    magnet_uri TEXT NOT NULL,
    display_title TEXT NOT NULL,
    size_bytes INTEGER,
    size_display TEXT,
    published_at TEXT,
    has_subtitle INTEGER,
    has_hd INTEGER,
    quality_tags_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS resource_observations (
    observation_id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    content_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    detail_url TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    raw_document_hash TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(resource_id, source_id, source_item_key),
    FOREIGN KEY(resource_id) REFERENCES resource_releases(resource_id) ON DELETE CASCADE,
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    documents_seen INTEGER NOT NULL DEFAULT 0,
    contents_created INTEGER NOT NULL DEFAULT 0,
    contents_updated INTEGER NOT NULL DEFAULT 0,
    resources_created INTEGER NOT NULL DEFAULT 0,
    resources_updated INTEGER NOT NULL DEFAULT 0,
    warnings INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    error_summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ingest_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    stage TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_item_key TEXT,
    error_code TEXT,
    message TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(run_id) REFERENCES ingest_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crawl_checkpoints (
    source_id TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(source_id, stream_id)
);

CREATE INDEX IF NOT EXISTS idx_content_code ON content_items(content_code);
CREATE INDEX IF NOT EXISTS idx_resource_content ON resource_releases(content_id);
CREATE INDEX IF NOT EXISTS idx_obs_content ON resource_observations(content_id);
