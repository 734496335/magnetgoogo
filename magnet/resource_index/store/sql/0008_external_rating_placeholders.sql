-- resource_index schema version 0008

ALTER TABLE movie_items ADD COLUMN rotten_tomatoes_rating REAL
    CHECK (rotten_tomatoes_rating IS NULL OR (rotten_tomatoes_rating > 0 AND rotten_tomatoes_rating <= 100));
ALTER TABLE movie_items ADD COLUMN rotten_tomatoes_rating_text TEXT;
ALTER TABLE movie_items ADD COLUMN rotten_tomatoes_url TEXT;

ALTER TABLE movie_items ADD COLUMN bangumi_rating REAL
    CHECK (bangumi_rating IS NULL OR (bangumi_rating > 0 AND bangumi_rating <= 10));
ALTER TABLE movie_items ADD COLUMN bangumi_rating_text TEXT;
ALTER TABLE movie_items ADD COLUMN bangumi_subject_id TEXT;
ALTER TABLE movie_items ADD COLUMN bangumi_url TEXT;
