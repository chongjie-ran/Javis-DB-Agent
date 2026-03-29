"""
MySQL 兼容性测试配置
"""
import os
import sys

# MySQL 测试配置
MYSQL_TEST_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "root",
    "password": "test123",
    "database": "zcloud_test_mysql",
    "charset": "utf8mb4",
}

# Docker MySQL 配置
DOCKER_MYSQL_CONFIG = {
    "image": "mysql:8.0",
    "container_name": "zcloud-mysql-test",
    "ports": {"3307": "3306"},
    "environment": {
        "MYSQL_ROOT_PASSWORD": "test123",
        "MYSQL_DATABASE": "zcloud_test_mysql",
        "MYSQL_USER": "zcloud",
        "MYSQL_PASSWORD": "zcloud123",
    },
    "args": [
        "--default-authentication-plugin=mysql_native_password",
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_unicode_ci",
    ],
}

# MySQL 特有 SQL 查询
MYSQL_QUERIES = {
    # 实例状态
    "version": "SELECT @@version, @@version_comment, @@uptime;",
    "connections": """
        SELECT 
            COUNT(*) AS total_connections,
            SUM(IF(command='Sleep', 1, 0)) AS idle_connections,
            SUM(IF(command!='Sleep', 1, 0)) AS active_connections
        FROM information_schema.processlist;
    """,
    "max_connections": "SHOW VARIABLES LIKE 'max_connections';",
    "buffer_pool_size": "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';",
    
    # 会话管理
    "sessions": """
        SELECT 
            p.id AS thread_id,
            p.user,
            p.host,
            p.db,
            p.command,
            p.time,
            p.state,
            LEFT(p.info, 100) AS current_sql
        FROM information_schema.processlist p
        WHERE p.user != 'system user'
        ORDER BY p.time DESC
        LIMIT 50;
    """,
    
    # 锁等待
    "lock_waits": """
        SELECT 
            r.trx_id AS waiting_trx_id,
            r.trx_mysql_thread_id AS waiting_thread,
            r.trx_query AS waiting_query,
            b.trx_id AS blocking_trx_id,
            b.trx_mysql_thread_id AS blocking_thread,
            b.trx_query AS blocking_query,
            b.trx_started AS blocking_started,
            b.trx_rows_locked AS blocking_rows_locked,
            b.trx_state AS blocking_state
        FROM information_schema.INNODB_LOCK_WAITS w
        JOIN information_schema.INNODB_TRX b ON w.blocking_trx_id = b.trx_id
        JOIN information_schema.INNODB_TRX r ON w.requesting_trx_id = r.trx_id;
    """,
    
    # 慢SQL
    "slow_sql": """
        SELECT 
            dig.digest,
            dig.digest_text,
            SUM(dig.count_star) AS total_executions,
            ROUND(SUM(dig.sum_timer_wait)/1000000000000, 2) AS total_time_sec,
            ROUND(AVG(dig.avg_timer_wait)/1000000000, 2) AS avg_time_ms,
            SUM(dig.sum_rows_examined) AS rows_examined,
            SUM(dig.sum_rows_sent) AS rows_sent
        FROM performance_schema.events_statements_summary_by_digest dig
        WHERE dig.digest_text IS NOT NULL
            AND dig.sum_timer_wait > 0
        GROUP BY dig.digest, dig.digest_text
        ORDER BY dig.sum_timer_wait DESC
        LIMIT 20;
    """,
    
    # 表统计
    "table_stats": """
        SELECT 
            table_schema,
            table_name,
            table_rows,
            ROUND(data_length / 1024 / 1024, 2) AS data_mb,
            ROUND(index_length / 1024 / 1024, 2) AS index_mb,
            ROUND((data_length + index_length) / 1024 / 1024, 2) AS total_mb,
            ROUND(data_free / 1024 / 1024, 2) AS free_mb
        FROM information_schema.tables
        WHERE table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
        ORDER BY (data_length + index_length) DESC
        LIMIT 20;
    """,
    
    # 索引统计
    "index_stats": """
        SELECT 
            table_schema,
            table_name,
            index_name,
            NON_UNIQUE,
            seq_in_index,
            column_name,
            collation,
            cardinality
        FROM information_schema.statistics
        WHERE table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
        ORDER BY table_schema, table_name, index_name, seq_in_index;
    """,
}
