ALTER TABLE monitor_events ADD COLUMN request_count INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS monitor_archive_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_check_ts INTEGER NOT NULL DEFAULT 0,
    last_archive_ts INTEGER NOT NULL DEFAULT 0,
    last_archive_file TEXT NOT NULL DEFAULT '',
    archived_rows INTEGER NOT NULL DEFAULT 0,
    archived_bytes INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO monitor_archive_state (id) VALUES (1);
