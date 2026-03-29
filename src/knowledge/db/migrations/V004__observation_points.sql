-- ============================================================
-- 观察点元数据表 - Round 20
-- 迁移时间: 2026-03-29
-- 描述: 定义关键指标的"采集方法、表示方法、异常模式"元数据，提升告警可解释性
-- ============================================================

CREATE TABLE IF NOT EXISTS observation_points (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,          -- 资源类型，如 OS.CPU, OS.Memory, DB.Connection
    metric_name TEXT NOT NULL,            -- 指标名称，如 usage_percent, active_count
    collection_method TEXT NOT NULL,      -- 如何采集该指标
    representation TEXT NOT NULL,        -- 如何表示该指标（单位、范围等）
    anomaly_pattern TEXT,                 -- 异常模式描述，如"持续>90%超过5分钟"
    anomaly_condition TEXT,               -- 异常条件表达式，如"avg(5m) > 90"
    unit TEXT,                            -- 单位，如 percent, count, ms
    severity TEXT,                        -- 默认严重程度，如 critical, warning, info
    metadata JSON,                        -- 扩展元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(resource_type, metric_name)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_op_resource_type ON observation_points(resource_type);
CREATE INDEX IF NOT EXISTS idx_op_metric_name ON observation_points(metric_name);
CREATE INDEX IF NOT EXISTS idx_op_severity ON observation_points(severity);

-- 触发器：更新updated_at
CREATE TRIGGER IF NOT EXISTS update_observation_points_timestamp 
AFTER UPDATE ON observation_points
BEGIN
    UPDATE observation_points SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- 观察点元数据示例（从benchmark导入）
-- 这些是常见的系统指标及其元数据定义
-- ============================================================

INSERT OR IGNORE INTO observation_points (id, resource_type, metric_name, collection_method, representation, anomaly_pattern, anomaly_condition, unit, severity, metadata) VALUES

-- OS.CPU 观察点
('bench-op-001', 'OS.CPU', 'usage_percent', '/proc/stat, psutil.cpu_percent()', 'percentage (0-100%)', '持续>90%超过5分钟', 'avg(5m) > 90', 'percent', 'warning', '{"source": "benchmark", "category": "performance"}'),

-- OS.Memory 观察点
('bench-op-002', 'OS.Memory', 'usage_percent', '/proc/meminfo, psutil.virtual_memory()', 'percentage (0-100%)', '持续>85%超过10分钟', 'avg(10m) > 85', 'percent', 'warning', '{"source": "benchmark", "category": "performance"}'),
('bench-op-003', 'OS.Memory', 'available_mb', '/proc/meminfo, psutil.virtual_memory()', 'megabytes', '可用内存<1GB', 'available < 1024', 'MB', 'critical', '{"source": "benchmark", "category": "performance"}'),

-- OS.Disk 观察点
('bench-op-004', 'OS.Disk', 'usage_percent', '/proc/mounts, psutil.disk_usage()', 'percentage (0-100%)', '磁盘使用率>85%', 'usage_percent > 85', 'percent', 'warning', '{"source": "benchmark", "category": "storage"}'),
('bench-op-005', 'OS.Disk', 'io_util', 'iostat, /proc/diskstats', 'percentage (0-100%)', '磁盘IO util持续>80%', 'avg(5m) > 80', 'percent', 'warning', '{"source": "benchmark", "category": "performance"}'),

-- OS.Network 观察点
('bench-op-006', 'OS.Network', 'bandwidth_util', '/proc/net/dev, ifstat', 'percentage (0-100%)', '带宽利用率>90%', 'avg(5m) > 90', 'percent', 'warning', '{"source": "benchmark", "category": "network"}'),
('bench-op-007', 'OS.Network', 'retransmit_rate', '/proc/net/netstat', 'packets per second', '重传率异常升高', 'retransmits > 100', 'pps', 'warning', '{"source": "benchmark", "category": "network"}'),

-- DB.Connection 观察点
('bench-op-008', 'DB.Connection', 'active_count', 'SHOW STATUS / pg_stat_activity', 'count', '连接数>最大连接数80%', 'current > max_connections * 0.8', 'count', 'warning', '{"source": "benchmark", "category": "database"}'),
('bench-op-009', 'DB.Connection', 'idle_count', 'SHOW STATUS / pg_stat_activity', 'count', 'Idle连接过多', 'idle > 50', 'count', 'info', '{"source": "benchmark", "category": "database"}'),
('bench-op-010', 'DB.Connection', 'wait_count', 'SHOW STATUS / pg_stat_activity', 'count', '等待连接过多', 'waiting > 10', 'count', 'warning', '{"source": "benchmark", "category": "database"}'),

-- DB.Query 观察点
('bench-op-011', 'DB.Query', 'slow_query_count', 'SHOW STATUS / pg_stat_statements', 'count per minute', '慢查询数量突增', 'rate(5m) > 10', 'count', 'warning', '{"source": "benchmark", "category": "performance"}'),
('bench-op-012', 'DB.Query', 'avg_duration_ms', 'SHOW STATUS / performance_schema', 'milliseconds', '平均查询时间>1秒', 'avg(5m) > 1000', 'ms', 'warning', '{"source": "benchmark", "category": "performance"}'),
('bench-op-013', 'DB.Query', 'lock_wait_ms', 'SHOW ENGINE INNODB STATUS', 'milliseconds', '锁等待时间过长', 'avg(5m) > 5000', 'ms', 'warning', '{"source": "benchmark", "category": "concurrency"}'),

-- DB.Transaction 观察点
('bench-op-014', 'DB.Transaction', 'active_count', 'SHOW ENGINE INNODB STATUS', 'count', '活跃事务过多', 'active > 100', 'count', 'warning', '{"source": "benchmark", "category": "concurrency"}'),
('bench-op-015', 'DB.Transaction', 'long_transaction_sec', 'information_schema.innodb_trx', 'seconds', '长事务>30分钟', 'max_duration > 1800', 'sec', 'critical', '{"source": "benchmark", "category": "concurrency"}'),

-- DB.Replication 观察点
('bench-op-016', 'DB.Replication', 'lag_bytes', 'SHOW SLAVE STATUS', 'bytes', '复制延迟>10MB', 'lag > 10485760', 'bytes', 'warning', '{"source": "benchmark", "category": "replication"}'),
('bench-op-017', 'DB.Replication', 'lag_sec', 'SHOW SLAVE STATUS', 'seconds', '复制延迟>30秒', 'lag > 30', 'sec', 'warning', '{"source": "benchmark", "category": "replication"}'),
('bench-op-018', 'DB.Replication', 'io_running', 'SHOW SLAVE STATUS', 'Yes/No', 'IO线程停止', 'io_running != "Yes"', 'flag', 'critical', '{"source": "benchmark", "category": "replication"}'),

-- DB.Buffer 观察点
('bench-op-019', 'DB.Buffer', 'hit_ratio', 'SHOW STATUS', 'percentage (0-100%)', 'Buffer命中率<95%', 'hit_ratio < 95', 'percent', 'warning', '{"source": "benchmark", "category": "performance"}'),
('bench-op-020', 'DB.Buffer', 'usage_percent', 'SHOW STATUS', 'percentage (0-100%)', 'Buffer池使用率>90%', 'usage > 90', 'percent', 'warning', '{"source": "benchmark", "category": "performance"}'),

-- App.Service 观察点
('bench-op-021', 'App.Service', 'response_time_ms', ' APM / nginx status', 'milliseconds', '响应时间>P95 > 500ms', 'p95(5m) > 500', 'ms', 'warning', '{"source": "benchmark", "category": "performance"}'),
('bench-op-022', 'App.Service', 'error_rate', 'APM / logs', 'percentage (0-100%)', '错误率>1%', 'error_rate > 1', 'percent', 'warning', '{"source": "benchmark", "category": "error"}'),
('bench-op-023', 'App.Service', 'request_rate', 'APM / nginx status', 'requests per second', '请求量突增/突降', 'rate_change > 50%', 'rps', 'info', '{"source": "benchmark", "category": "throughput"}'),

-- Cache.Service 观察点
('bench-op-024', 'Cache.Service', 'hit_ratio', 'INFO stats', 'percentage (0-100%)', '缓存命中率<80%', 'hit_ratio < 80', 'percent', 'warning', '{"source": "benchmark", "category": "cache"}'),
('bench-op-025', 'Cache.Service', 'evicted_keys', 'INFO stats', 'count per second', '驱逐速率过高', 'evicted > 1000', 'count', 'warning', '{"source": "benchmark", "category": "cache"}'),
('bench-op-026', 'Cache.Service', 'memory_usage_mb', 'INFO memory', 'megabytes', '内存使用超过上限', 'memory > maxmemory', 'MB', 'critical', '{"source": "benchmark", "category": "memory"}'),

-- MQ.Broker 观察点
('bench-op-027', 'MQ.Broker', 'queue_depth', 'QUEUE_STATUS', 'count', '队列积压>10000', 'depth > 10000', 'count', 'warning', '{"source": "benchmark", "category": "middleware"}'),
('bench-op-028', 'MQ.Broker', 'unacked_messages', 'QUEUE_STATUS', 'count', '未确认消息过多', 'unacked > 5000', 'count', 'warning', '{"source": "benchmark", "category": "middleware"}');
