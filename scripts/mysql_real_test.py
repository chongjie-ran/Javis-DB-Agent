#!/usr/bin/env python3
"""
MySQL 真实环境验证脚本
用于测试 Javis-DB-Agent Agent 与真实 MySQL 的连接
"""
import os
import sys
import time
import pymysql
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# MySQL 连接配置
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "root",
    "password": "test123",
    "database": "zcloud_test_mysql",
    "charset": "utf8mb4",
}

PERF_MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3308,
    "user": "root",
    "password": "perf123",
    "database": "zcloud_perf",
    "charset": "utf8mb4",
}


def test_connection(config, name="MySQL"):
    """测试 MySQL 连接"""
    print(f"\n{'='*60}")
    print(f"测试 {name} 连接")
    print(f"{'='*60}")
    print(f"主机: {config['host']}:{config['port']}")
    print(f"用户: {config['user']}")
    print(f"数据库: {config['database']}")
    
    try:
        start_time = time.time()
        conn = pymysql.connect(**config)
        elapsed = time.time() - start_time
        
        print(f"✅ 连接成功! 耗时: {elapsed*1000:.2f}ms")
        
        # 获取版本信息
        cursor = conn.cursor()
        cursor.execute("SELECT @@version, @@version_comment")
        version_info = cursor.fetchone()
        print(f"✅ MySQL 版本: {version_info[0]}")
        print(f"   {version_info[1]}")
        
        cursor.close()
        conn.close()
        return True, elapsed
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False, 0


def test_basic_queries(config, name="MySQL"):
    """测试基本查询"""
    print(f"\n{'='*60}")
    print(f"测试 {name} 基本查询")
    print(f"{'='*60}")
    
    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        
        queries = {
            "版本查询": "SELECT @@version",
            "当前数据库": "SELECT DATABASE()",
            "当前用户": "SELECT USER()",
            "连接数": "SELECT COUNT(*) FROM information_schema.processlist",
            "最大连接数": "SHOW VARIABLES LIKE 'max_connections'",
            "缓冲池大小": "SHOW VARIABLES LIKE 'innodb_buffer_pool_size'",
            "数据库列表": "SHOW DATABASES",
        }
        
        results = {}
        for query_name, query in queries.items():
            try:
                start_time = time.time()
                cursor.execute(query)
                result = cursor.fetchone()
                elapsed = time.time() - start_time
                results[query_name] = {"success": True, "result": result, "time_ms": elapsed * 1000}
                print(f"  ✅ {query_name}: {result} ({elapsed*1000:.2f}ms)")
            except Exception as e:
                results[query_name] = {"success": False, "error": str(e)}
                print(f"  ❌ {query_name}: {e}")
        
        cursor.close()
        conn.close()
        return results
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return {}


def create_test_schema(config, name="MySQL"):
    """创建测试 schema 和表"""
    print(f"\n{'='*60}")
    print(f"创建 {name} 测试数据")
    print(f"{'='*60}")
    
    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        
        # 创建测试表
        tables = [
            # 订单表
            """CREATE TABLE IF NOT EXISTS orders (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_no VARCHAR(32) NOT NULL UNIQUE,
                user_id BIGINT NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_status (status),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            # 用户表
            """CREATE TABLE IF NOT EXISTS users (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100),
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_username (username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            # 产品表
            """CREATE TABLE IF NOT EXISTS products (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                category VARCHAR(50),
                price DECIMAL(10, 2) NOT NULL,
                stock INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_category (category)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            # 订单明细表
            """CREATE TABLE IF NOT EXISTS order_items (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_id BIGINT NOT NULL,
                product_id BIGINT NOT NULL,
                quantity INT NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                INDEX idx_order_id (order_id),
                INDEX idx_product_id (product_id),
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            # 慢查询模拟表
            """CREATE TABLE IF NOT EXISTS slow_query_log (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                query_text TEXT,
                execution_time_ms INT,
                rows_examined BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_execution_time (execution_time_ms)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        ]
        
        for i, sql in enumerate(tables):
            table_name = ["orders", "users", "products", "order_items", "slow_query_log"][i]
            try:
                cursor.execute(sql)
                print(f"  ✅ 创建表: {table_name}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"  ℹ️  表已存在: {table_name}")
                else:
                    print(f"  ❌ 创建表 {table_name} 失败: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ 创建测试数据失败: {e}")
        return False


def insert_test_data(config, name="MySQL"):
    """插入测试数据"""
    print(f"\n{'='*60}")
    print(f"插入 {name} 测试数据")
    print(f"{'='*60}")
    
    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        
        # 插入用户数据
        users = [
            ("user001", "alice@example.com"),
            ("user002", "bob@example.com"),
            ("user003", "charlie@example.com"),
            ("user004", "david@example.com"),
            ("user005", "eve@example.com"),
        ]
        
        cursor.executemany(
            "INSERT IGNORE INTO users (username, email) VALUES (%s, %s)",
            users
        )
        print(f"  ✅ 插入用户数据: {cursor.rowcount} 行")
        
        # 插入产品数据
        products = [
            ("iPhone 15", "electronics", 6999.00, 100),
            ("MacBook Pro", "electronics", 12999.00, 50),
            ("AirPods Pro", "electronics", 1499.00, 200),
            ("iPad Air", "electronics", 3999.00, 80),
            ("Apple Watch", "electronics", 2499.00, 150),
        ]
        
        cursor.executemany(
            "INSERT IGNORE INTO products (name, category, price, stock) VALUES (%s, %s, %s, %s)",
            products
        )
        print(f"  ✅ 插入产品数据: {cursor.rowcount} 行")
        
        # 插入订单数据
        orders = [
            ("ORD2026032901", 1, 6999.00, "completed"),
            ("ORD2026032902", 2, 12999.00, "completed"),
            ("ORD2026032903", 3, 2998.00, "pending"),
            ("ORD2026032904", 1, 1499.00, "shipped"),
            ("ORD2026032905", 4, 3999.00, "pending"),
        ]
        
        cursor.executemany(
            "INSERT IGNORE INTO orders (order_no, user_id, amount, status) VALUES (%s, %s, %s, %s)",
            orders
        )
        print(f"  ✅ 插入订单数据: {cursor.rowcount} 行")
        
        # 插入一些慢查询日志
        slow_logs = [
            ("SELECT * FROM orders o JOIN users u ON o.user_id = u.id WHERE o.status = 'pending'", 1523, 50000),
            ("SELECT COUNT(*) FROM order_items GROUP BY order_id", 892, 15000),
            ("SELECT * FROM products WHERE category = 'electronics' ORDER BY price DESC", 456, 500),
        ]
        
        cursor.executemany(
            "INSERT INTO slow_query_log (query_text, execution_time_ms, rows_examined) VALUES (%s, %s, %s)",
            slow_logs
        )
        print(f"  ✅ 插入慢查询日志: {cursor.rowcount} 行")
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ 插入测试数据失败: {e}")
        return False


def verify_data(config, name="MySQL"):
    """验证数据"""
    print(f"\n{'='*60}")
    print(f"验证 {name} 数据")
    print(f"{'='*60}")
    
    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        
        tables = ["users", "products", "orders", "order_items", "slow_query_log"]
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  📊 {table}: {count} 行")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ 验证数据失败: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("Javis-DB-Agent MySQL 真实环境验证")
    print("="*60)
    
    # 测试主测试库连接
    success1, time1 = test_connection(MYSQL_CONFIG, "MySQL-Test")
    
    if success1:
        test_basic_queries(MYSQL_CONFIG, "MySQL-Test")
        create_test_schema(MYSQL_CONFIG, "MySQL-Test")
        insert_test_data(MYSQL_CONFIG, "MySQL-Test")
        verify_data(MYSQL_CONFIG, "MySQL-Test")
    
    # 测试性能测试库连接
    success2, time2 = test_connection(PERF_MYSQL_CONFIG, "MySQL-Perf")
    
    if success2:
        test_basic_queries(PERF_MYSQL_CONFIG, "MySQL-Perf")
        create_test_schema(PERF_MYSQL_CONFIG, "MySQL-Perf")
    
    # 总结
    print("\n" + "="*60)
    print("验证结果汇总")
    print("="*60)
    print(f"MySQL-Test: {'✅ 成功' if success1 else '❌ 失败'}")
    print(f"MySQL-Perf: {'✅ 成功' if success2 else '❌ 失败'}")
    
    return success1 and success2


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
