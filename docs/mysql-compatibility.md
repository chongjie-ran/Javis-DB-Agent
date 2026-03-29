# MySQL 兼容性测试文档

> 版本：v1.0 | 日期：2026-03-28 | 状态：进行中

---

## 一、概述

本文档描述 Javis-DB-Agent 的 MySQL 数据库兼容性测试方案。

### 1.1 测试目标

- 验证系统对 MySQL 数据库的诊断能力
- 测试 MySQL 特有的性能视图（information_schema, performance_schema）
- 确保 SQL 语法兼容性
- 创建 MySQL 测试环境

### 1.2 与 PostgreSQL 测试对比

| 功能 | PostgreSQL | MySQL |
|------|------------|-------|
| 会话查询 | pg_stat_activity | information_schema.PROCESSLIST + performance_schema.threads |
| 锁等待 | pg_locks | performance_schema.data_locks + information_schema.INNODB_LOCKS |
| 慢SQL | pg_stat_statements | performance_schema.events_statements_history |
| 索引统计 | pg_stat_user_indexes | information_schema.STATISTICS |
| 表统计 | pg_stat_user_tables | information_schema.TABLES |

---

## 二、MySQL 测试环境

### 2.1 Docker 容器方式（推荐）

```bash
# 启动 MySQL 8.0 容器
docker run -d \
  --name javis-db-mysql-test \
  -e MYSQL_ROOT_PASSWORD=test123 \
  -e MYSQL_DATABASE=zcloud_test_mysql \
  -e MYSQL_USER=javis-db \
  -e MYSQL_PASSWORD=zcloud123 \
  -p 3307:3306 \
  mysql:8.0 \
  --default-authentication-plugin=mysql_native_password \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

# 等待启动
sleep 30

# 验证连接
mysql -h 127.0.0.1 -P 3307 -u root -ptest123 -e "SELECT VERSION();"
```

### 2.2 连接信息

| 项目 | 值 |
|------|-----|
| Host | 127.0.0.1 |
| Port | 3307 |
| Root 用户 | root |
| Root 密码 | test123 |
| 测试数据库 | zcloud_test_mysql |
| 测试用户 | javis-db |
| 测试用户密码 | zcloud123 |

---

## 三、MySQL 特有查询

### 3.1 实例状态查询

```sql
-- MySQL 版本和状态
SELECT @@version, @@version_comment, @@uptime;

-- 当前连接数
SELECT 
  COUNT(*) AS total_connections,
  SUM(IF(command='Sleep', 1, 0)) AS idle_connections,
  SUM(IF(command!='Sleep', 1, 0)) AS active_connections
FROM information_schema.processlist;

-- 变量配置
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'query_cache_type';
```

### 3.2 会话管理

```sql
-- 所有会话（MySQL 8.0+ 使用 performance_schema）
SELECT 
  p.id AS thread_id,
  p.user,
  p.host,
  p.db,
  p.command,
  p.time,
  p.state,
  p.info
FROM information_schema.processlist p
WHERE p.user != 'system user'
ORDER BY p.time DESC;

-- 性能模式线程（更详细）
SELECT 
  thread_id,
  processlist_id,
  processlist_user,
  processlist_host,
  processlist_db,
  processlist_command,
  processlist_state,
  processlist_time
FROM performance_schema.threads
WHERE type = 'FOREGROUND'
  AND processlist_user IS NOT NULL
ORDER BY processlist_time DESC;
```

### 3.3 锁等待分析

```sql
-- InnoDB 锁等待
SELECT 
  r.trx_id AS waiting_trx_id,
  r.trx_mysql_thread_id AS waiting_thread,
  r.trx_query AS waiting_query,
  b.trx_id AS blocking_trx_id,
  b.trx_mysql_thread_id AS blocking_thread,
  b.trx_query AS blocking_query,
  b.trx_started AS blocking_started,
  b.trx_rows_locked AS blocking_rows_locked,
  b.trx_tables_locked AS blocking_tables_locked,
  b.trx_state AS blocking_state
FROM information_schema.INNODB_LOCK_WAITS w
JOIN information_schema.INNODB_TRX b ON w.blocking_trx_id = b.trx_id
JOIN information_schema.INNODB_TRX r ON w.requesting_trx_id = r.trx_id;

-- 性能模式锁（MySQL 8.0+）
SELECT 
  dl.lock_id,
  dl.lock_mode,
  dl.lock_type,
  dl.lock_status,
  dl.lock_table,
  dl.lock_index,
  dl.lock_space,
  dl.lock_page,
  dl.lock_rec,
  dl.lock_data,
  dt.processlist_id AS thread_id,
  dt.processlist_user,
  dt.processlist_host,
  dt.processlist_command,
  dt.processlist_state
FROM performance_schema.data_locks dl
JOIN performance_schema.data_lock_waits dlw 
  ON dl.lock_id = dlw.blocking_lock_id
JOIN performance_schema.threads t 
  ON dl.thread_id = t.thread_id
JOIN performance_schema.events_statements_current esc 
  ON t.thread_id = esc.thread_id
JOIN performance_schema.processlist_by_thread pt 
  ON t.processlist_id = pt.processlist_id;
```

### 3.4 慢SQL查询

```sql
-- 启用慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;
SET GLOBAL slow_query_log_file = '/var/lib/mysql/slow.log';

-- 读取慢查询（需要配置 slow_query_log_file）
-- 使用 performance_schema（MySQL 8.0+）
SELECT 
  dig.digest,
  dig.digest_text,
  SUM(dig.count_star) AS total_executions,
  ROUND(SUM(dig.sum_timer_wait)/1000000000000, 2) AS total_time_sec,
  ROUND(AVG(dig.avg_timer_wait)/1000000000, 2) AS avg_time_ms,
  SUM(dig.sum_rows_affected) AS rows_affected,
  SUM(dig.sum_rows_examined) AS rows_examined,
  SUM(dig.sum_rows_sent) AS rows_sent
FROM performance_schema.events_statements_summary_by_digest dig
WHERE dig.digest_text IS NOT NULL
  AND dig.sum_timer_wait > 0
ORDER BY dig.sum_timer_wait DESC
LIMIT 20;
```

### 3.5 告警链诊断

```sql
-- CPU/内存告警相关查询
SELECT 
  variable_name,
  variable_value
FROM performance_schema.global_status
WHERE variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Aborted_connects'
);

-- InnoDB 缓冲池
SELECT 
  pool.allocated AS total_bytes,
  pool.data AS data_bytes,
  pool.dirty AS dirty_bytes,
  pool.old_pages,
  pool.young_pages
FROM (
  SELECT 
    SUM(allocated) AS allocated,
    SUM(data) AS data,
    SUM(dirty) AS dirty,
    SUM(old_pages) AS old_pages,
    SUM(young_pages) AS young_pages
  FROM information_schema.INNODB_BUFFER_PAGE
  WHERE table_name IS NOT NULL
) pool;

-- 连接数告警
SELECT 
  @@max_connections AS max_conn,
  (SELECT COUNT(*) FROM information_schema.processlist) AS current_conn,
  ROUND((SELECT COUNT(*) FROM information_schema.processlist) / @@max_connections * 100, 2) AS conn_pct;
```

---

## 四、测试用例

### 4.1 MySQL 实例状态查询

```python
def test_mysql_instance_status():
    """测试 MySQL 实例状态查询"""
    # 验证版本
    result = query("SELECT @@version, @@uptime;")
    assert result['version'].startswith('8.0')
    
    # 验证连接数
    result = query("""
        SELECT COUNT(*) AS conn_count 
        FROM information_schema.processlist
    """)
    assert result['conn_count'] >= 0
```

### 4.2 MySQL 会话管理

```python
def test_mysql_sessions():
    """测试 MySQL 会话查询"""
    result = query("""
        SELECT id, user, host, command, time, state
        FROM information_schema.processlist
        WHERE user != 'system user'
        ORDER BY time DESC
    """)
    assert len(result['rows']) >= 0
```

### 4.3 MySQL 锁等待分析

```python
def test_mysql_lock_waits():
    """测试 MySQL 锁等待分析"""
    result = query("""
        SELECT 
          r.trx_id AS waiting_trx,
          b.trx_id AS blocking_trx,
          b.trx_state
        FROM information_schema.INNODB_LOCK_WAITS w
        JOIN information_schema.INNODB_TRX b ON w.blocking_trx_id = b.trx_id
        JOIN information_schema.INNODB_TRX r ON w.requesting_trx_id = r.trx_id
    """)
    # 验证锁等待数据
    assert 'waiting_trx' in result['rows'][0] if result['rows'] else True
```

### 4.4 MySQL 慢SQL查询

```python
def test_mysql_slow_sql():
    """测试 MySQL 慢SQL查询"""
    result = query("""
        SELECT 
          digest_text,
          count_star,
          avg_timer_wait
        FROM performance_schema.events_statements_summary_by_digest
        WHERE digest_text IS NOT NULL
        ORDER BY sum_timer_wait DESC
        LIMIT 10
    """)
    assert len(result['rows']) >= 0
```

---

## 五、SQL 语法差异

### 5.1 关键差异

| 特性 | PostgreSQL | MySQL |
|------|------------|-------|
| 分页 | `LIMIT 10 OFFSET 20` | `LIMIT 20, 10` 或 `LIMIT 10 OFFSET 20` |
| 字符串拼接 | `\|\|` 或 `CONCAT()` | `CONCAT()` |
| 布尔值 | `TRUE/FALSE` | `1/0` |
| UUID | UUID类型 + uuid_generate_v4() | VARCHAR(36) + UUID() |
| 日期函数 | `NOW() - INTERVAL '1' DAY` | `DATE_SUB(NOW(), INTERVAL 1 DAY)` |
| 注释 | `--` 或 `/* */` | `--` 或 `/* */` |
| 大小写 | 不敏感 | 取决于存储引擎 |

### 5.2 适配示例

```python
# PostgreSQL
SELECT * FROM users ORDER BY created_at DESC LIMIT 10 OFFSET 20;

# MySQL 适配
SELECT * FROM users ORDER BY created_at DESC LIMIT 20, 10;
```

```python
# PostgreSQL
SELECT COUNT(*) FROM users WHERE active = TRUE;

# MySQL 适配
SELECT COUNT(*) FROM users WHERE active = 1;
```

```python
# PostgreSQL
SELECT * FROM logs WHERE created_at > NOW() - INTERVAL '1 hour';

# MySQL 适配
SELECT * FROM logs WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR);
```

---

## 六、测试结果

### 6.1 待测试项目

- [ ] MySQL 8.0 Docker 容器启动
- [ ] 数据库连接认证
- [ ] 实例状态查询
- [ ] 会话列表查询
- [ ] 锁等待分析
- [ ] 慢SQL查询
- [ ] 告警链诊断

---

*最后更新：2026-03-28*
