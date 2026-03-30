-- V1.5 Round 2 - PG测试数据库初始化SQL
-- 用于验证工具连接真实PG环境

-- 创建备份历史表
CREATE TABLE IF NOT EXISTS backup_history (
    id SERIAL PRIMARY KEY,
    db_type VARCHAR(20),
    backup_type VARCHAR(20),
    status VARCHAR(20),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    size_bytes BIGINT
);

-- 创建慢查询日志表
CREATE TABLE IF NOT EXISTS slow_query_log (
    id SERIAL PRIMARY KEY,
    query TEXT,
    execution_time_ms INTEGER,
    calls INTEGER,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- 创建测试业务表（用于模拟真实数据）
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    status VARCHAR(20),
    total_amount DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    category_id INTEGER,
    price DECIMAL(10,2),
    stock INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 插入备份历史测试数据
INSERT INTO backup_history (db_type, backup_type, status, start_time, end_time, size_bytes)
VALUES 
    ('postgresql', 'full', 'success', NOW()-INTERVAL '1 day', NOW()-INTERVAL '23 hours', 1048576000),
    ('postgresql', 'full', 'success', NOW()-INTERVAL '2 days', NOW()-INTERVAL '1 day', 1024000000),
    ('postgresql', 'incremental', 'success', NOW()-INTERVAL '12 hours', NOW()-INTERVAL '11 hours', 104857600),
    ('postgresql', 'full', 'failed', NOW()-INTERVAL '3 days', NOW()-INTERVAL '2 days', 0),
    ('postgresql', 'full', 'success', NOW()-INTERVAL '4 days', NOW()-INTERVAL '3 days', 985600000)
ON CONFLICT DO NOTHING;

-- 插入慢查询测试数据
INSERT INTO slow_query_log (query, execution_time_ms, calls)
VALUES 
    ('SELECT * FROM orders WHERE status = ''pending'' AND created_at > NOW()-INTERVAL ''7 days''', 2500, 150),
    ('SELECT o.*, u.name FROM orders o JOIN users u ON o.user_id = u.id WHERE o.status = ''completed''', 1800, 320),
    ('UPDATE products SET stock = stock - 1 WHERE id = $1', 350, 5000),
    ('SELECT COUNT(*) FROM orders GROUP BY status', 1200, 80),
    ('SELECT * FROM products WHERE category_id = 5 ORDER BY price DESC', 890, 200)
ON CONFLICT DO NOTHING;

-- 插入业务测试数据
INSERT INTO users (name, email) VALUES 
    ('张三', 'zhangsan@test.com'),
    ('李四', 'lisi@test.com'),
    ('王五', 'wangwu@test.com')
ON CONFLICT DO NOTHING;

INSERT INTO products (name, category_id, price, stock) VALUES 
    ('产品A', 1, 99.99, 100),
    ('产品B', 1, 199.99, 50),
    ('产品C', 2, 299.99, 30)
ON CONFLICT DO NOTHING;

INSERT INTO orders (user_id, status, total_amount) VALUES 
    (1, 'completed', 299.97),
    (1, 'pending', 99.99),
    (2, 'completed', 199.99),
    (3, 'cancelled', 99.99)
ON CONFLICT DO NOTHING;

-- 创建统计视图（用于模拟pg_stat_statements功能）
CREATE OR REPLACE VIEW v_top_sql AS
SELECT 
    query,
    calls,
    total_exec_time_ms,
    total_exec_time_ms / NULLIF(calls, 0) as avg_exec_time_ms,
    0 as rows_examined,
    CASE 
        WHEN total_exec_time_ms / NULLIF(calls, 0) > 1000 THEN 'critical'
        WHEN total_exec_time_ms / NULLIF(calls, 0) > 500 THEN 'high'
        WHEN total_exec_time_ms / NULLIF(calls, 0) > 100 THEN 'medium'
        ELSE 'low'
    END as risk_level
FROM slow_query_log
ORDER BY total_exec_time_ms DESC;
