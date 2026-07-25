-- resource_index schema version 0002

ALTER TABLE ingest_runs ADD COLUMN http_requests INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS content_observations (
    content_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    raw_content_code TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_original_title TEXT,
    release_date TEXT,
    duration_minutes INTEGER,
    maker_name TEXT,
    publisher_name TEXT,
    label_name TEXT,
    series_name TEXT,
    cover_source_url TEXT,
    detail_url TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    raw_document_hash TEXT,
    source_priority INTEGER NOT NULL DEFAULT 0,
    metadata_quality INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(content_id, source_id, source_item_key),
    UNIQUE(source_id, source_item_key),
    FOREIGN KEY(content_id) REFERENCES content_items(content_id) ON DELETE CASCADE
);

INSERT OR IGNORE INTO content_observations(
    content_id, source_id, source_item_key, raw_content_code,
    source_title, source_original_title, release_date, duration_minutes,
    maker_name, publisher_name, label_name, series_name, cover_source_url,
    detail_url, parser_version, raw_document_hash, source_priority,
    metadata_quality, first_seen_at, last_seen_at, seen_count
)
SELECT
    content_id, source_id, source_item_key, raw_content_code,
    title, original_title, release_date, duration_minutes,
    maker_name, publisher_name, label_name, series_name, cover_source_url,
    detail_url, parser_version, NULL, 0,
    1
        + CASE WHEN original_title IS NOT NULL AND TRIM(original_title) <> '' THEN 1 ELSE 0 END
        + CASE WHEN release_date IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN duration_minutes IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN maker_name IS NOT NULL AND TRIM(maker_name) <> '' THEN 1 ELSE 0 END
        + CASE WHEN publisher_name IS NOT NULL AND TRIM(publisher_name) <> '' THEN 1 ELSE 0 END
        + CASE WHEN label_name IS NOT NULL AND TRIM(label_name) <> '' THEN 1 ELSE 0 END
        + CASE WHEN series_name IS NOT NULL AND TRIM(series_name) <> '' THEN 1 ELSE 0 END
        + CASE WHEN cover_source_url IS NOT NULL AND TRIM(cover_source_url) <> '' THEN 1 ELSE 0 END,
    first_seen_at, last_seen_at, 1
FROM content_items;

CREATE INDEX IF NOT EXISTS idx_content_observations_content
    ON content_observations(content_id);
CREATE INDEX IF NOT EXISTS idx_content_observations_source
    ON content_observations(source_id, source_item_key);
