"""
测试数据准备脚本
在真实数据库中创建测试所需的数据
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import asyncio
import time

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from test_runner import TestConfig


async def setup_mysql_test_data(drop_existing: bool = False) -> bool:
    """
    准备MySQL测试数据
    
    Args:
        drop_existing: 是否删除已存在的测试数据
    
    Returns:
        True if setup succeeded
    """
    if not HAS_PYMYSQL:
        print("⚠️  pymysql 未安装，跳过MySQL测试数据准备")
        return False

    if not TestConfig.is_mysql_available():
        print("⚠️  MySQL不可用，跳过测试数据准备")
        return False

    print("📦 准备MySQL测试数据...")

    try:
        conn = TestConfig.get_mysql_conn()
        cursor = conn.cursor()

        db_name = TestConfig.MYSQL_DATABASE

        # 创建测试数据库
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        cursor.execute(f"USE `{db_name}`")

        if drop_existing:
            cursor.execute("DROP TABLE IF EXISTS backup_history")
            cursor.execute("DROP TABLE IF EXISTS slow_query_log")
            cursor.execute("DROP TABLE IF EXISTS test_performance")

        # 创建备份历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                backup_type VARCHAR(20) NOT NULL DEFAULT 'full',
                status VARCHAR(20) NOT NULL DEFAULT 'completed',
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                size_bytes BIGINT DEFAULT 0,
                duration_seconds INT DEFAULT 0,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # 插入备份历史数据
        now = time.time()
        backups = [
            # 成功备份
            ("full", "completed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 86400)), 1024 * 1024 * 500, 3600),
            ("incremental", "completed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 43200)), 1024 * 1024 * 50, 300),
            ("full", "completed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), 1024 * 1024 * 510, 3700),
            # 失败备份
            ("full", "failed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 172800)), 0, 0),
        ]

        for btype, status, start, size, duration in backups:
            cursor.execute(
                "INSERT INTO backup_history (backup_type, status, start_time, size_bytes, duration_seconds) "
                "VALUES (%s, %s, %s, %s, %s)",
                (btype, status, start, size, duration)
            )
        conn.commit()

        # 创建性能测试表（模拟TopSQL数据）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_performance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                query_text TEXT,
                exec_count INT DEFAULT 0,
                total_exec_time_ms BIGINT DEFAULT 0,
                rows_examined BIGINT DEFAULT 0,
                last_exec_time DATETIME,
                risk_level VARCHAR(20) DEFAULT 'low'
            )
        """)

        # 插入TopSQL模拟数据
        slow_queries = [
            ("SELECT * FROM orders WHERE status = 'pending' AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)", 5000, 5000 * 200, 100000, "high"),
            ("SELECT p.*, c.name FROM products p JOIN categories c ON p.cat_id = c.id WHERE p.price > 100", 3000, 3000 * 50, 50000, "medium"),
            ("UPDATE inventory SET stock = stock - 1 WHERE product_id = 123 AND stock > 0", 10000, 10000 * 5, 10000, "low"),
            ("SELECT COUNT(*) FROM logs WHERE level = 'ERROR' AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)", 800, 800 * 300, 200000, "high"),
            ("SELECT user_id, SUM(amount) FROM transactions GROUP BY user_id HAVING SUM(amount) > 10000", 200, 200 * 1000, 500000, "medium"),
        ]

        cursor.execute("DELETE FROM test_performance")
        for sql, count, total_time, rows, risk in slow_queries:
            cursor.execute(
                "INSERT INTO test_performance (query_text, exec_count, total_exec_time_ms, rows_examined, risk_level) "
                "VALUES (%s, %s, %s, %s, %s)",
                (sql, count, total_time, rows, risk)
            )
        conn.commit()

        cursor.close()
        conn.close()

        print(f"  ✅ MySQL测试数据准备完成: {db_name}")
        print(f"     - backup_history: {len(backups)} 条记录")
        print(f"     - test_performance: {len(slow_queries)} 条记录")
        return True

    except Exception as e:
        print(f"  ❌ MySQL测试数据准备失败: {e}")
        return False


async def setup_pg_test_data(drop_existing: bool = False) -> bool:
    """
    准备PostgreSQL测试数据
    
    Args:
        drop_existing: 是否删除已存在的测试数据
    
    Returns:
        True if setup succeeded
    """
    if not HAS_PSYCOPG2:
        print("⚠️  psycopg2 未安装，跳过PG测试数据准备")
        return False

    if not TestConfig.is_pg_available():
        print("⚠️  PostgreSQL不可用，跳过测试数据准备")
        return False

    print("📦 准备PostgreSQL测试数据...")

    try:
        conn = TestConfig.get_pg_conn()
        cursor = conn.cursor()

        db_name = TestConfig.PG_DATABASE

        if drop_existing:
            cursor.execute("DROP TABLE IF EXISTS backup_history CASCADE")
            cursor.execute("DROP TABLE IF EXISTS slow_query_log CASCADE")
            cursor.execute("DROP TABLE IF EXISTS test_performance CASCADE")

        # 创建备份历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_history (
                id SERIAL PRIMARY KEY,
                backup_type VARCHAR(20) NOT NULL DEFAULT 'full',
                status VARCHAR(20) NOT NULL DEFAULT 'completed',
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                size_bytes BIGINT DEFAULT 0,
                duration_seconds INT DEFAULT 0,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # 插入备份历史数据
        now = time.time()
        backups = [
            ("full", "completed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 86400)), 1024 * 1024 * 800, 4200),
            ("incremental", "completed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 43200)), 1024 * 1024 * 80, 400),
            ("full", "completed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), 1024 * 1024 * 810, 4300),
            ("differential", "failed", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 172800)), 0, 0),
        ]

        cursor.execute("DELETE FROM backup_history")
        for btype, status, start, size, duration in backups:
            cursor.execute(
                "INSERT INTO backup_history (backup_type, status, start_time, size_bytes, duration_seconds) "
                "VALUES (%s, %s, %s, %s, %s)",
                (btype, status, start, size, duration)
            )
        conn.commit()

        # 创建性能测试表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_performance (
                id SERIAL PRIMARY KEY,
                query_text TEXT,
                exec_count INT DEFAULT 0,
                total_exec_time_ms BIGINT DEFAULT 0,
                rows_examined BIGINT DEFAULT 0,
                last_exec_time TIMESTAMP,
                risk_level VARCHAR(20) DEFAULT 'low'
            )
        """)

        slow_queries = [
            ("SELECT * FROM orders WHERE status = 'pending' AND created_at < NOW() - INTERVAL '30 days'", 5000, 5000 * 200, 100000, "high"),
            ("SELECT p.*, c.name FROM products p JOIN categories c ON p.cat_id = c.id WHERE p.price > 100", 3000, 3000 * 50, 50000, "medium"),
            ("UPDATE inventory SET stock = stock - 1 WHERE product_id = 123 AND stock > 0", 10000, 10000 * 5, 10000, "low"),
            ("SELECT COUNT(*) FROM logs WHERE level = 'ERROR' AND created_at > NOW() - INTERVAL '7 days'", 800, 800 * 300, 200000, "high"),
            ("SELECT user_id, SUM(amount) FROM transactions GROUP BY user_id HAVING SUM(amount) > 10000", 200, 200 * 1000, 500000, "medium"),
        ]

        cursor.execute("DELETE FROM test_performance")
        for sql, count, total_time, rows, risk in slow_queries:
            cursor.execute(
                "INSERT INTO test_performance (query_text, exec_count, total_exec_time_ms, rows_examined, risk_level) "
                "VALUES (%s, %s, %s, %s, %s)",
                (sql, count, total_time, rows, risk)
            )
        conn.commit()

        cursor.close()
        conn.close()

        print(f"  ✅ PostgreSQL测试数据准备完成: {db_name}")
        print(f"     - backup_history: {len(backups)} 条记录")
        print(f"     - test_performance: {len(slow_queries)} 条记录")
        return True

    except Exception as e:
        print(f"  ❌ PostgreSQL测试数据准备失败: {e}")
        return False


async def setup_all(drop_existing: bool = False):
    """准备所有测试数据"""
    print("=" * 50)
    print("V1.5 测试数据准备")
    print("=" * 50)

    mysql_ok = await setup_mysql_test_data(drop_existing)
    pg_ok = await setup_pg_test_data(drop_existing)

    print("\n" + "=" * 50)
    if mysql_ok or pg_ok:
        print("✅ 测试数据准备完成")
        return True
    else:
        print("❌ 测试数据准备失败")
        return False


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description="V1.5 测试数据准备")
    parser.add_argument("--drop", action="store_true", help="删除已存在的测试数据")
    args = parser.parse_args()

    result = asyncio.run(setup_all(drop_existing=args.drop))
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
