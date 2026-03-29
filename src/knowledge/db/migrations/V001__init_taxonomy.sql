-- V001__init_taxonomy.sql
-- Taxonomy data model: Entity-Resource-ObservationPoint three-layer classification system
-- This migration creates the foundational taxonomy tables for resource classification

BEGIN;

-- =============================================================================
-- Entity Types Table
-- Represents top-level entities like Operating Systems, Databases, Applications
-- =============================================================================
CREATE TABLE IF NOT EXISTS entity_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('os', 'database', 'application', 'network', 'storage', 'security', 'middleware')),
    description TEXT,
    parent_id TEXT REFERENCES entity_types(id) ON DELETE SET NULL,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for parent lookups (for hierarchy queries)
CREATE INDEX IF NOT EXISTS idx_entity_types_parent_id ON entity_types(parent_id);
CREATE INDEX IF NOT EXISTS idx_entity_types_category ON entity_types(category);

-- =============================================================================
-- Resource Types Table
-- Represents resources belonging to entities (CPU, Memory, Sessions, etc.)
-- =============================================================================
CREATE TABLE IF NOT EXISTS resource_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type_id TEXT NOT NULL REFERENCES entity_types(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('hardware', 'software', 'data', 'network', 'memory', 'compute', 'storage', 'service', 'process')),
    description TEXT,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for entity lookups
CREATE INDEX IF NOT EXISTS idx_resource_types_entity_type_id ON resource_types(entity_type_id);
CREATE INDEX IF NOT EXISTS idx_resource_types_category ON resource_types(category);

-- =============================================================================
-- Observation Point Types Table
-- Represents observable metrics/points for resources (load, performance, errors)
-- =============================================================================
CREATE TABLE IF NOT EXISTS observation_point_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    resource_type_id TEXT NOT NULL REFERENCES resource_types(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('load', 'performance', 'error', 'security', 'config', 'health', 'availability', 'throughput', 'latency')),
    unit TEXT,
    description TEXT,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for resource lookups
CREATE INDEX IF NOT EXISTS idx_obs_point_types_resource_type_id ON observation_point_types(resource_type_id);
CREATE INDEX IF NOT EXISTS idx_obs_point_types_category ON observation_point_types(category);

-- =============================================================================
-- Initial Seed Data (from benchmark taxonomy)
-- Entity-Resource-ObservationPoint hierarchy for Linux OS
-- =============================================================================

-- OS Entities
INSERT INTO entity_types (id, name, category, description, parent_id) VALUES
    ('os', 'Operating System', 'os', '操作系统基础分类', NULL),
    ('os.linux', 'Linux', 'os', 'Linux操作系统', 'os'),
    ('os.windows', 'Windows', 'os', 'Windows操作系统', 'os'),
    ('db', 'Database', 'database', '数据库基础分类', NULL),
    ('db.postgresql', 'PostgreSQL', 'database', 'PostgreSQL数据库', 'db'),
    ('db.mysql', 'MySQL', 'database', 'MySQL数据库', 'db'),
    ('db.opengauss', 'OpenGauss', 'database', 'OpenGauss数据库', 'db'),
    ('app', 'Application', 'application', '应用程序基础分类', NULL),
    ('app.web', 'Web Application', 'application', 'Web应用程序', 'app'),
    ('app.api', 'API Service', 'application', 'API服务', 'app')
ON CONFLICT (id) DO NOTHING;

-- OS Linux Resources
INSERT INTO resource_types (id, name, entity_type_id, category, description) VALUES
    -- Hardware resources
    ('os.linux.cpu', 'CPU', 'os.linux', 'compute', 'CPU计算资源'),
    ('os.linux.memory', 'Memory', 'os.linux', 'memory', '物理内存资源'),
    ('os.linux.disk', 'Disk I/O', 'os.linux', 'storage', '磁盘存储I/O资源'),
    ('os.linux.network', 'Network I/O', 'os.linux', 'network', '网络I/O资源'),
    ('os.linux.filesystem', 'Filesystem', 'os.linux', 'storage', '文件系统资源'),
    -- Software resources
    ('os.linux.process', 'Process', 'os.linux', 'process', '进程资源'),
    ('os.linux.file', 'File', 'os.linux', 'storage', '文件资源'),
    ('os.linux.service', 'Service', 'os.linux', 'service', '系统服务资源')
ON CONFLICT (id) DO NOTHING;

-- OS Windows Resources
INSERT INTO resource_types (id, name, entity_type_id, category, description) VALUES
    ('os.windows.cpu', 'CPU', 'os.windows', 'compute', 'CPU计算资源'),
    ('os.windows.memory', 'Memory', 'os.windows', 'memory', '物理内存资源'),
    ('os.windows.disk', 'Disk I/O', 'os.windows', 'storage', '磁盘存储I/O资源'),
    ('os.windows.network', 'Network I/O', 'os.windows', 'network', '网络I/O资源'),
    ('os.windows.service', 'Service', 'os.windows', 'service', 'Windows服务资源')
ON CONFLICT (id) DO NOTHING;

-- PostgreSQL Resources
INSERT INTO resource_types (id, name, entity_type_id, category, description) VALUES
    -- Data object resources
    ('db.postgresql.session', 'Session', 'db.postgresql', 'service', '数据库会话资源'),
    ('db.postgresql.transaction', 'Transaction', 'db.postgresql', 'service', '事务资源'),
    ('db.postgresql.connection', 'Connection', 'db.postgresql', 'service', '数据库连接资源'),
    ('db.postgresql.buffer', 'Buffer', 'db.postgresql', 'memory', '缓冲池资源'),
    ('db.postgresql.lock', 'Lock', 'db.postgresql', 'service', '锁资源'),
    ('db.postgresql.wal', 'WAL', 'db.postgresql', 'storage', '预写日志资源'),
    ('db.postgresql.table', 'Table', 'db.postgresql', 'data', '表资源'),
    ('db.postgresql.index', 'Index', 'db.postgresql', 'data', '索引资源'),
    ('db.postgresql.query', 'Query', 'db.postgresql', 'compute', '查询资源')
ON CONFLICT (id) DO NOTHING;

-- MySQL Resources
INSERT INTO resource_types (id, name, entity_type_id, category, description) VALUES
    ('db.mysql.session', 'Session', 'db.mysql', 'service', '数据库会话资源'),
    ('db.mysql.connection', 'Connection', 'db.mysql', 'service', '数据库连接资源'),
    ('db.mysql.buffer', 'Buffer', 'db.mysql', 'memory', '缓冲池资源'),
    ('db.mysql.table', 'Table', 'db.mysql', 'data', '表资源'),
    ('db.mysql.query', 'Query', 'db.mysql', 'compute', '查询资源')
ON CONFLICT (id) DO NOTHING;

-- Linux CPU Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('os.linux.cpu.utilization', 'CPU Utilization', 'os.linux.cpu', 'performance', 'percent', 'CPU利用率'),
    ('os.linux.cpu.load_avg', 'Load Average', 'os.linux.cpu', 'load', 'load', '系统负载均值'),
    ('os.linux.cpu.iowait', 'I/O Wait', 'os.linux.cpu', 'performance', 'percent', 'I/O等待占用'),
    ('os.linux.cpu.context_switch', 'Context Switches', 'os.linux.cpu', 'performance', 'count/s', '上下文切换次数'),
    ('os.linux.cpu.interrupt', 'Interrupts', 'os.linux.cpu', 'performance', 'count/s', '中断次数'),
    ('os.linux.cpu.softirq', 'SoftIRQ', 'os.linux.cpu', 'performance', 'count/s', '软中断次数')
ON CONFLICT (id) DO NOTHING;

-- Linux Memory Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('os.linux.memory.used', 'Memory Used', 'os.linux.memory', 'performance', 'percent', '内存使用率'),
    ('os.linux.memory.available', 'Memory Available', 'os.linux.memory', 'health', 'bytes', '可用内存'),
    ('os.linux.memory.swap', 'Swap Usage', 'os.linux.memory', 'performance', 'percent', 'Swap使用率'),
    ('os.linux.memory.cached', 'Cached Memory', 'os.linux.memory', 'performance', 'bytes', '缓存内存'),
    ('os.linux.memory.buffers', 'Buffers', 'os.linux.memory', 'performance', 'bytes', '缓冲区内存')
ON CONFLICT (id) DO NOTHING;

-- Linux Disk I/O Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('os.linux.disk.read_iops', 'Read IOPS', 'os.linux.disk', 'throughput', 'ops/s', '磁盘读IOPS'),
    ('os.linux.disk.write_iops', 'Write IOPS', 'os.linux.disk', 'throughput', 'ops/s', '磁盘写IOPS'),
    ('os.linux.disk.read_throughput', 'Read Throughput', 'os.linux.disk', 'throughput', 'bytes/s', '磁盘读吞吐量'),
    ('os.linux.disk.write_throughput', 'Write Throughput', 'os.linux.disk', 'throughput', 'bytes/s', '磁盘写吞吐量'),
    ('os.linux.disk.utilization', 'Disk Utilization', 'os.linux.disk', 'performance', 'percent', '磁盘利用率'),
    ('os.linux.disk.latency', 'Disk Latency', 'os.linux.disk', 'latency', 'ms', '磁盘延迟'),
    ('os.linux.disk.queue_depth', 'Queue Depth', 'os.linux.disk', 'performance', 'depth', 'I/O队列深度')
ON CONFLICT (id) DO NOTHING;

-- Linux Network I/O Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('os.linux.network.rx_bytes', 'RX Bytes', 'os.linux.network', 'throughput', 'bytes/s', '网络接收字节'),
    ('os.linux.network.tx_bytes', 'TX Bytes', 'os.linux.network', 'throughput', 'bytes/s', '网络发送字节'),
    ('os.linux.network.rx_packets', 'RX Packets', 'os.linux.network', 'throughput', 'packets/s', '网络接收包数'),
    ('os.linux.network.tx_packets', 'TX Packets', 'os.linux.network', 'throughput', 'packets/s', '网络发送包数'),
    ('os.linux.network.errors', 'Network Errors', 'os.linux.network', 'error', 'count/s', '网络错误数'),
    ('os.linux.network.dropped', 'Dropped Packets', 'os.linux.network', 'error', 'count/s', '丢包数')
ON CONFLICT (id) DO NOTHING;

-- Linux Process Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('os.linux.process.count', 'Process Count', 'os.linux.process', 'load', 'count', '进程数量'),
    ('os.linux.process.thread_count', 'Thread Count', 'os.linux.process', 'load', 'count', '线程数量'),
    ('os.linux.process.zombie_count', 'Zombie Count', 'os.linux.process', 'error', 'count', '僵尸进程数'),
    ('os.linux.process.file_descriptors', 'File Descriptors', 'os.linux.process', 'performance', 'count', '打开文件描述符')
ON CONFLICT (id) DO NOTHING;

-- PostgreSQL Session Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('db.postgresql.session.active', 'Active Sessions', 'db.postgresql.session', 'load', 'count', '活跃会话数'),
    ('db.postgresql.session.idle', 'Idle Sessions', 'db.postgresql.session', 'performance', 'count', '空闲会话数'),
    ('db.postgresql.session.waiting', 'Waiting Sessions', 'db.postgresql.session', 'error', 'count', '等待中会话'),
    ('db.postgresql.session.long_running', 'Long Running Queries', 'db.postgresql.session', 'error', 'count', '长时间运行查询')
ON CONFLICT (id) DO NOTHING;

-- PostgreSQL Connection Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('db.postgresql.connection.used', 'Connections Used', 'db.postgresql.connection', 'load', 'count', '已用连接数'),
    ('db.postgresql.connection.available', 'Connections Available', 'db.postgresql.connection', 'availability', 'count', '可用连接数'),
    ('db.postgresql.connection.utilization', 'Connection Utilization', 'db.postgresql.connection', 'performance', 'percent', '连接利用率')
ON CONFLICT (id) DO NOTHING;

-- PostgreSQL Buffer Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('db.postgresql.buffer.hit_ratio', 'Buffer Hit Ratio', 'db.postgresql.buffer', 'performance', 'percent', '缓冲区命中率'),
    ('db.postgresql.buffer.usage', 'Buffer Usage', 'db.postgresql.buffer', 'load', 'percent', '缓冲区使用率'),
    ('db.postgresql.buffer.dirty', 'Dirty Buffers', 'db.postgresql.buffer', 'performance', 'percent', '脏缓冲区比例')
ON CONFLICT (id) DO NOTHING;

-- PostgreSQL Lock Observation Points
INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description) VALUES
    ('db.postgresql.lock.waiting', 'Waiting Locks', 'db.postgresql.lock', 'error', 'count', '等待中的锁'),
    ('db.postgresql.lock.deadlock', 'Deadlocks', 'db.postgresql.lock', 'error', 'count', '死锁数量'),
    ('db.postgresql.lock.conflict', 'Lock Conflicts', 'db.postgresql.lock', 'error', 'count/s', '锁冲突次数')
ON CONFLICT (id) DO NOTHING;

COMMIT;
