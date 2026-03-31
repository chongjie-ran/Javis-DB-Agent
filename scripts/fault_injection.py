#!/usr/bin/env python3
"""
Javis-DB-Agent 故障注入脚本
V2.5 - 故障注入与检测验证

用法:
    python3 fault_injection.py [--cleanup]

故障类型:
1. 锁等待 - 在 users 表上持有行锁不提交
2. 大数据量 - orders 表填充50000+条记录
3. 索引缺失 - no_index_test 表无二级索引
4. 慢SQL - 全表扫描查询

数据库连接:
- PostgreSQL: /tmp (socket), user=chongjieran, database=javis_test_db
- MySQL: 127.0.0.1:3306, user=root, password=root, socket=/tmp/mysql.sock
"""

import argparse
import sys
import time
import threading
import signal

# PostgreSQL
import psycopg2
# MySQL
import pymysql


class FaultInjector:
    """故障注入器"""
    
    def __init__(self):
        self.pg_conn = None
        self.mysql_conn = None
        self.lock_threads = []
        
    def connect_postgres(self):
        """连接 PostgreSQL"""
        self.pg_conn = psycopg2.connect(
            host='/tmp',
            user='chongjieran',
            database='javis_test_db'
        )
        self.pg_conn.autocommit = False
        print("[PG] Connected to PostgreSQL")
        return self.pg_conn
    
    def connect_mysql(self):
        """连接 MySQL"""
        self.mysql_conn = pymysql.connect(
            host='127.0.0.1',
            port=3306,
            user='root',
            password='root',
            unix_socket='/tmp/mysql.sock'
        )
        print("[MySQL] Connected to MySQL")
        return self.mysql_conn
    
    def inject_lock_wait_pg(self):
        """注入 PostgreSQL 锁等待故障"""
        print("\n[PG] Injecting lock wait fault...")
        
        cur = self.pg_conn.cursor()
        
        # 确保用户存在
        cur.execute("""
            INSERT INTO users (id, name, email) 
            VALUES (9999, 'lock_test_user', 'lock@test.com')
            ON CONFLICT (id) DO UPDATE SET name='lock_test_user'
        """)
        self.pg_conn.commit()
        
        # 开始事务并持有锁
        cur.execute("BEGIN")
        cur.execute("UPDATE users SET name='LOCKED_BY_PG' WHERE id=9999")
        
        print("[PG] Lock acquired on users.id=9999 (transaction open)")
        print("[PG] WARNING: Connection must remain open to hold lock")
        
        return True
    
    def inject_lock_wait_mysql(self):
        """注入 MySQL 锁等待故障"""
        print("\n[MySQL] Injecting lock wait fault...")
        
        cur = self.mysql_conn.cursor()
        cur.execute("USE javis_test_db")
        
        # 确保用户存在
        cur.execute("""
            INSERT INTO users (id, name, email) 
            VALUES (9999, 'lock_test_user', 'lock@test.com')
            ON DUPLICATE KEY UPDATE name='lock_test_user'
        """)
        self.mysql_conn.commit()
        
        # 开始事务并持有锁
        cur.execute("BEGIN")
        cur.execute("UPDATE users SET name='LOCKED_BY_MYSQL' WHERE id=9999")
        
        print("[MySQL] Lock acquired on users.id=9999 (transaction open)")
        print("[MySQL] WARNING: Connection must remain open to hold lock")
        
        return True
    
    def inject_large_dataset_pg(self):
        """注入 PostgreSQL 大数据量故障"""
        print("\n[PG] Injecting large dataset fault...")
        
        cur = self.pg_conn.cursor()
        
        # 检查现有数据量
        cur.execute("SELECT COUNT(*) FROM orders")
        count = cur.fetchone()[0]
        
        if count < 50000:
            # 插入50000条记录
            cur.execute("""
                INSERT INTO orders (user_id, status, total_amount)
                SELECT 
                    (random()*1000)::int,
                    CASE (random()*3)::int 
                        WHEN 0 THEN 'pending'
                        WHEN 1 THEN 'completed'
                        WHEN 2 THEN 'cancelled'
                        ELSE 'pending'
                    END,
                    (random()*10000)::numeric(10,2)
                FROM generate_series(1, 50000)
            """)
            self.pg_conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM orders")
        total = cur.fetchone()[0]
        print(f"[PG] Orders table: {total} rows")
        return True
    
    def inject_large_dataset_mysql(self):
        """注入 MySQL 大数据量故障"""
        print("\n[MySQL] Injecting large dataset fault...")
        
        cur = self.mysql_conn.cursor()
        cur.execute("USE javis_test_db")
        
        # 检查现有数据量
        cur.execute("SELECT COUNT(*) FROM orders")
        count = cur.fetchone()[0]
        
        if count < 50000:
            # 分块插入50000条记录
            values = []
            for i in range(1, 50001):
                values.append(f"({i}, {i % 100}, {i * 1.5})")
            
            for chunk_start in range(0, len(values), 5000):
                chunk = values[chunk_start:chunk_start+5000]
                cur.execute(f"INSERT INTO orders (product_id, quantity, price) VALUES {','.join(chunk)}")
                self.mysql_conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM orders")
        total = cur.fetchone()[0]
        print(f"[MySQL] Orders table: {total} rows")
        return True
    
    def inject_no_index_pg(self):
        """注入 PostgreSQL 索引缺失故障"""
        print("\n[PG] Injecting missing index fault...")
        
        cur = self.pg_conn.cursor()
        
        # 创建无索引表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS no_index_test (
                id SERIAL PRIMARY KEY,
                data TEXT,
                search_key VARCHAR(100)
            )
        """)
        self.pg_conn.commit()
        
        # 插入数据
        cur.execute("SELECT COUNT(*) FROM no_index_test")
        count = cur.fetchone()[0]
        
        if count < 10000:
            cur.execute("""
                INSERT INTO no_index_test (data, search_key)
                SELECT 'data'||i, 'key_'||((i % 1000)::text)
                FROM generate_series(1, 10000) AS i
            """)
            self.pg_conn.commit()
        
        # 验证无二级索引
        cur.execute("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'no_index_test' AND indexname != 'no_index_test_pkey'
        """)
        indexes = cur.fetchall()
        print(f"[PG] no_index_test: {10000} rows, secondary indexes: {len(indexes)}")
        return True
    
    def inject_no_index_mysql(self):
        """注入 MySQL 索引缺失故障"""
        print("\n[MySQL] Injecting missing index fault...")
        
        cur = self.mysql_conn.cursor()
        cur.execute("USE javis_test_db")
        
        # 创建无索引表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS no_index_test (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data TEXT,
                search_key VARCHAR(100)
            )
        """)
        self.mysql_conn.commit()
        
        # 插入数据
        cur.execute("SELECT COUNT(*) FROM no_index_test")
        count = cur.fetchone()[0]
        
        if count < 10000:
            values = []
            for i in range(1, 10001):
                values.append(f"('data{i}', 'key_{(i % 1000)}')")
            
            for chunk_start in range(0, len(values), 2000):
                chunk = values[chunk_start:chunk_start+2000]
                cur.execute(f"INSERT INTO no_index_test (data, search_key) VALUES {','.join(chunk)}")
                self.mysql_conn.commit()
        
        print(f"[MySQL] no_index_test: 10000 rows, only PRIMARY KEY index")
        return True
    
    def inject_all(self):
        """注入所有故障"""
        print("=" * 60)
        print("Javis-DB-Agent 故障注入")
        print("=" * 60)
        
        # 连接数据库
        self.connect_postgres()
        self.connect_mysql()
        
        # 注入各项故障
        self.inject_lock_wait_pg()
        self.inject_lock_wait_mysql()
        self.inject_large_dataset_pg()
        self.inject_large_dataset_mysql()
        self.inject_no_index_pg()
        self.inject_no_index_mysql()
        
        print("\n" + "=" * 60)
        print("故障注入完成")
        print("=" * 60)
        print("注入的故障:")
        print("  1. [PG+MySQL] 锁等待 - users.id=9999 事务未提交")
        print("  2. [PG+MySQL] 大数据量 - orders 表 50000+ 条记录")
        print("  3. [PG+MySQL] 索引缺失 - no_index_test 表无二级索引")
        print("\n保持连接打开以维持锁故障...")
        
        # 保持连接
        print("\n按 Ctrl+C 清理并退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n清理中...")
            self.cleanup()
    
    def cleanup(self):
        """清理故障"""
        print("\n[Cleanup] Closing connections...")
        if self.pg_conn:
            try:
                self.pg_conn.rollback()
                self.pg_conn.close()
                print("[PG] Connection closed")
            except:
                pass
        if self.mysql_conn:
            try:
                self.mysql_conn.rollback()
                self.mysql_conn.close()
                print("[MySQL] Connection closed")
            except:
                pass
        print("[Cleanup] Done")


def main():
    parser = argparse.ArgumentParser(description='Javis-DB-Agent 故障注入脚本')
    parser.add_argument('--cleanup', action='store_true', help='仅清理，不注入')
    args = parser.parse_args()
    
    injector = FaultInjector()
    
    if args.cleanup:
        injector.cleanup()
    else:
        injector.inject_all()


if __name__ == "__main__":
    main()
