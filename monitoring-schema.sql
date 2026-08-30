CREATE TABLE IF NOT EXISTS monitor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    minute INTEGER NOT NULL,
    user_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    method TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 1,
    status INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    bytes_up INTEGER NOT NULL DEFAULT 0,
    bytes_down INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    country TEXT NOT NULL DEFAULT 'N/A',
    colo TEXT NOT NULL DEFAULT 'N/A',
    node_ip TEXT NOT NULL DEFAULT '',
    node_port INTEGER NOT NULL DEFAULT 0,
    node_group TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_monitor_node_ts
ON monitor_events(node_ip, node_port, ts);

CREATE INDEX IF NOT EXISTS idx_monitor_ts_node
ON monitor_events(ts, node_ip, node_port);

CREATE TABLE IF NOT EXISTS monitor_archive_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_check_ts INTEGER NOT NULL DEFAULT 0,
    last_archive_ts INTEGER NOT NULL DEFAULT 0,
    last_archive_file TEXT NOT NULL DEFAULT '',
    archived_rows INTEGER NOT NULL DEFAULT 0,
    archived_bytes INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO monitor_archive_state (id) VALUES (1);
