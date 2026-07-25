-- resource_index schema version 0004

CREATE TABLE IF NOT EXISTS movie_items (
    movie_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    detail_url TEXT NOT NULL,
    listing_title TEXT NOT NULL,
    title TEXT NOT NULL,
    original_title TEXT,
    year INTEGER,
    update_date TEXT,
    release_date TEXT,
    duration_minutes INTEGER,
    countries_json TEXT NOT NULL DEFAULT '[]',
    genres_json TEXT NOT NULL DEFAULT '[]',
    languages_json TEXT NOT NULL DEFAULT '[]',
    directors_json TEXT NOT NULL DEFAULT '[]',
    actors_json TEXT NOT NULL DEFAULT '[]',
    imdb_id TEXT,
    douban_rating REAL,
    douban_rating_text TEXT,
    douban_url TEXT,
    cover_source_url TEXT,
    synopsis TEXT,
    recommended INTEGER NOT NULL DEFAULT 0 CHECK (recommended IN (0, 1)),
    highlight_labels_json TEXT NOT NULL DEFAULT '[]',
    quality_tags_json TEXT NOT NULL DEFAULT '[]',
    parser_version TEXT NOT NULL,
    raw_document_hash TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, source_item_key),
    UNIQUE(source_id, detail_url)
);

CREATE TABLE IF NOT EXISTS movie_resources (
    resource_id TEXT PRIMARY KEY,
    movie_id TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type IN ('magnet', 'cloud')),
    provider TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    info_hash TEXT,
    display_title TEXT NOT NULL,
    extraction_code TEXT,
    quality_tags_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(movie_id, resource_url),
    FOREIGN KEY(movie_id) REFERENCES movie_items(movie_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_movie_items_source_update
    ON movie_items(source_id, update_date DESC, detail_url);
CREATE INDEX IF NOT EXISTS idx_movie_items_recommended
    ON movie_items(source_id, recommended, update_date DESC);
CREATE INDEX IF NOT EXISTS idx_movie_resources_movie
    ON movie_resources(movie_id, resource_type, provider);
