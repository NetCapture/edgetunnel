ALTER TABLE monitor_events ADD COLUMN node_ip TEXT NOT NULL DEFAULT '';
ALTER TABLE monitor_events ADD COLUMN node_port INTEGER NOT NULL DEFAULT 0;
ALTER TABLE monitor_events ADD COLUMN node_group TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_monitor_node_ts
ON monitor_events(node_ip, node_port, ts);
