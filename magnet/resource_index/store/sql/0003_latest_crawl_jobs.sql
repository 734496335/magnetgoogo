-- resource_index schema version 0003

CREATE TABLE IF NOT EXISTS latest_crawl_jobs (
    job_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_count INTEGER NOT NULL CHECK (target_count > 0),
    batch_size INTEGER NOT NULL CHECK (batch_size > 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    snapshot_hash TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_path TEXT NOT NULL,
    feed_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'paused', 'success', 'partial', 'failed')),
    snapshot_http_requests INTEGER NOT NULL DEFAULT 0,
    detail_http_requests INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    error_summary_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_id, target_count, snapshot_hash)
);

CREATE TABLE IF NOT EXISTS latest_crawl_items (
    job_id TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank > 0),
    detail_url TEXT NOT NULL,
    content_code TEXT,
    listing_title TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')) DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_run_id TEXT,
    last_error_code TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(job_id, rank),
    UNIQUE(job_id, detail_url),
    FOREIGN KEY(job_id) REFERENCES latest_crawl_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_latest_crawl_jobs_status
    ON latest_crawl_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_latest_crawl_items_status
    ON latest_crawl_items(job_id, status, attempts, rank);
