-- ============================================================
-- 资源依赖关系表 - Round 19
-- 迁移时间: 2026-03-29
-- 描述: 支持告警在资源间的依赖传播，增强根因分析能力
-- ============================================================

-- 资源依赖关系表
CREATE TABLE IF NOT EXISTS resource_dependencies (
    id TEXT PRIMARY KEY,
    source_resource_type TEXT NOT NULL,
    target_resource_type TEXT NOT NULL,
    dependency_type TEXT NOT NULL CHECK (dependency_type IN ('depends_on', 'used_by', 'calls')),
    weight FLOAT DEFAULT 1.0 CHECK (weight >= 0.0 AND weight <= 1.0),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_resource_type, target_resource_type, dependency_type)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_deps_source ON resource_dependencies(source_resource_type);
CREATE INDEX IF NOT EXISTS idx_deps_target ON resource_dependencies(target_resource_type);
CREATE INDEX IF NOT EXISTS idx_deps_type ON resource_dependencies(dependency_type);

-- 触发器：更新updated_at
CREATE TRIGGER IF NOT EXISTS update_resource_dependencies_timestamp 
AFTER UPDATE ON resource_dependencies
BEGIN
    UPDATE resource_dependencies SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- 基准依赖规则（从benchmark导入）
-- 这些是典型的资源依赖关系
-- ============================================================

INSERT OR IGNORE INTO resource_dependencies (id, source_resource_type, target_resource_type, dependency_type, weight, metadata) VALUES
-- OS层依赖
('bench-001', 'OS.CPU', 'DB.Connection', 'depends_on', 0.9, '{"description": "高CPU导致数据库连接池耗尽", "category": "performance"}'),
('bench-002', 'OS.Memory', 'DB.Buffer', 'depends_on', 0.8, '{"description": "内存不足影响数据库缓冲池", "category": "performance"}'),
('bench-003', 'OS.Disk', 'DB.Storage', 'depends_on', 0.85, '{"description": "磁盘性能影响数据库存储", "category": "storage"}'),
('bench-004', 'OS.Network', 'DB.Replication', 'depends_on', 0.75, '{"description": "网络延迟影响数据库复制", "category": "network"}'),
('bench-005', 'OS.CPU', 'App.Service', 'depends_on', 0.8, '{"description": "高CPU影响应用服务响应", "category": "performance"}'),
('bench-006', 'OS.Memory', 'App.Service', 'depends_on', 0.85, '{"description": "内存不足导致应用服务不稳定", "category": "performance"}'),

-- 数据库层依赖
('bench-007', 'DB.Connection', 'DB.Query', 'calls', 0.7, '{"description": "连接用于执行查询", "category": "database"}'),
('bench-008', 'DB.Lock', 'DB.Transaction', 'depends_on', 0.9, '{"description": "锁等待影响事务执行", "category": "concurrency"}'),
('bench-009', 'DB.Transaction', 'DB.Commit', 'depends_on', 0.6, '{"description": "事务最终需要提交", "category": "database"}'),
('bench-010', 'DB.Index', 'DB.Query', 'depends_on', 0.8, '{"description": "索引影响查询性能", "category": "performance"}'),
('bench-011', 'DB.Buffer', 'DB.Query', 'depends_on', 0.75, '{"description": "缓冲池影响查询速度", "category": "performance"}'),
('bench-012', 'DB.Lock', 'DB.Query', 'depends_on', 0.65, '{"description": "锁等待导致查询变慢", "category": "performance"}'),

-- 应用层依赖
('bench-013', 'App.Service', 'DB.Connection', 'depends_on', 0.9, '{"description": "应用服务依赖数据库连接", "category": "application"}'),
('bench-014', 'App.Service', 'Cache.Service', 'depends_on', 0.7, '{"description": "应用服务依赖缓存", "category": "application"}'),
('bench-015', 'App.API', 'App.Service', 'calls', 0.85, '{"description": "API调用服务", "category": "application"}'),
('bench-016', 'App.API', 'DB.Connection', 'depends_on', 0.6, '{"description": "API直接使用数据库连接", "category": "application"}'),

-- 中间件依赖
('bench-017', 'MQ.Broker', 'App.Service', 'used_by', 0.7, '{"description": "消息队列被服务使用", "category": "middleware"}'),
('bench-018', 'Cache.Service', 'DB.Connection', 'used_by', 0.5, '{"description": "缓存服务减少数据库连接压力", "category": "cache"}'),
('bench-019', 'LoadBalancer', 'App.API', 'depends_on', 0.6, '{"description": "负载均衡依赖后端API", "category": "network"}'),

-- 存储层依赖
('bench-020', 'DB.Storage', 'DB.Replication', 'depends_on', 0.8, '{"description": "存储影响复制性能", "category": "storage"}'),
('bench-021', 'DB.Storage', 'DB.Backup', 'depends_on', 0.75, '{"description": "存储影响备份", "category": "backup"}'),
('bench-022', 'OS.Disk', 'DB.Backup', 'depends_on', 0.8, '{"description": "磁盘IO影响备份速度", "category": "backup"}');
