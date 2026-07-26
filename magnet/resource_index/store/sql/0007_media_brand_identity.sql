-- resource_index schema version 0007

ALTER TABLE movie_items ADD COLUMN content_kind TEXT NOT NULL DEFAULT 'movie'
    CHECK (content_kind IN ('movie', 'series', 'anime', 'variety', 'documentary'));
ALTER TABLE movie_items ADD COLUMN series_title TEXT;
ALTER TABLE movie_items ADD COLUMN season_number INTEGER CHECK (season_number IS NULL OR season_number > 0);
ALTER TABLE movie_items ADD COLUMN episode_number INTEGER CHECK (episode_number IS NULL OR episode_number > 0);
ALTER TABLE movie_items ADD COLUMN episode_label TEXT;
ALTER TABLE movie_items ADD COLUMN update_status TEXT;
ALTER TABLE movie_items ADD COLUMN brand_id TEXT;
ALTER TABLE movie_items ADD COLUMN endpoint_origin TEXT;

ALTER TABLE latest_crawl_items ADD COLUMN source_item_key TEXT;

CREATE INDEX IF NOT EXISTS idx_movie_items_kind_update
    ON movie_items(content_kind, update_date DESC, source_id);
CREATE INDEX IF NOT EXISTS idx_movie_items_brand
    ON movie_items(brand_id, content_kind, update_date DESC);
CREATE INDEX IF NOT EXISTS idx_movie_items_series
    ON movie_items(series_title, season_number, episode_number);
CREATE INDEX IF NOT EXISTS idx_latest_crawl_items_source_key
    ON latest_crawl_items(job_id, source_item_key);
