CREATE INDEX IF NOT EXISTS idx_monitor_ts_node
ON monitor_events(ts, node_ip, node_port);
