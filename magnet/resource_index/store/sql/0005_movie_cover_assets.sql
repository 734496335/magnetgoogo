-- resource_index schema version 0005

CREATE TABLE IF NOT EXISTS movie_cover_assets (
    movie_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    image_blob BLOB NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(movie_id) REFERENCES movie_items(movie_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_movie_cover_hash
    ON movie_cover_assets(content_hash);
