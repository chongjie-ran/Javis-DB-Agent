#!/usr/bin/env python3
"""
MySQL 性能压测脚本
基准测试并发性能和延迟分析
"""
import os
import sys
import time
import pymysql
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Tuple

# MySQL 性能测试配置
PERF_MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3308,
    "user": "root",
    "password": "perf123",
    "database": "zcloud_perf",
    "charset": "utf8mb4",
}

# 压测配置
BENCHMARK_CONFIG = {
    "warmup_rounds": 3,
    "test_rounds": 10,
    "concurrency_levels": [1, 5, 10, 20, 50],
    "query_timeout": 30,
}


class MySQLBenchmark:
    """MySQL 性能基准测试"""
    
    def __init__(self, config: dict):
        self.config = config
        self.results = []
    
    def get_connection(self):
        """获取数据库连接"""
        return pymysql.connect(**self.config)
    
    def create_test_tables(self):
        """创建压测表"""
        print("\n创建压测表...")
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        tables = [
            """CREATE TABLE IF NOT EXISTS benchmark_users (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_username (username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            """CREATE TABLE IF NOT EXISTS benchmark_orders (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_no VARCHAR(32) NOT NULL UNIQUE,
                user_id BIGINT,
                amount DECIMAL(10, 2),
                status VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_status (status),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            """CREATE TABLE IF NOT EXISTS benchmark_results (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                test_name VARCHAR(100),
                concurrency INT,
                total_requests INT,
                success_count INT,
                error_count INT,
                avg_latency_ms FLOAT,
                p50_latency_ms FLOAT,
                p95_latency_ms FLOAT,
                p99_latency_ms FLOAT,
                min_latency_ms FLOAT,
                max_latency_ms FLOAT,
                throughput_qps FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        ]
        
        for sql in tables:
            cursor.execute(sql)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("  ✅ 压测表创建完成")
    
    def prepare_test_data(self, user_count=1000, order_count=10000):
        """准备测试数据"""
        print(f"\n准备测试数据 (用户: {user_count}, 订单: {order_count})...")
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 检查是否已有数据
        cursor.execute("SELECT COUNT(*) FROM benchmark_users")
        existing_users = cursor.fetchone()[0]
        
        if existing_users < user_count:
            # 生成用户数据
            users = [(f"user{i:06d}", f"user{i}@example.com") for i in range(existing_users, user_count)]
            cursor.executemany(
                "INSERT IGNORE INTO benchmark_users (username, email) VALUES (%s, %s)",
                users
            )
            conn.commit()
            print(f"  ✅ 用户数据: {user_count} 行")
        
        # 检查订单数量
        cursor.execute("SELECT COUNT(*) FROM benchmark_orders")
        existing_orders = cursor.fetchone()[0]
        
        if existing_orders < order_count:
            # 生成订单数据
            statuses = ["pending", "processing", "shipped", "completed", "cancelled"]
            orders = [
                (
                    f"ORD{i:010d}",
                    i % user_count + 1,
                    round(100 + (i % 1000) * 10.5, 2),
                    statuses[i % len(statuses)]
                )
                for i in range(existing_orders, order_count)
            ]
            cursor.executemany(
                "INSERT IGNORE INTO benchmark_orders (order_no, user_id, amount, status) VALUES (%s, %s, %s, %s)",
                orders
            )
            conn.commit()
            print(f"  ✅ 订单数据: {order_count} 行")
        
        cursor.close()
        conn.close()
    
    def run_single_query(self, query: str, params: tuple = None) -> Tuple[bool, float]:
        """运行单个查询，返回 (成功, 延迟ms)"""
        start_time = time.time()
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            cursor.fetchall()
            cursor.close()
            conn.close()
            return True, (time.time() - start_time) * 1000
        except Exception as e:
            return False, (time.time() - start_time) * 1000
    
    def run_query_batch(self, query: str, count: int, params: tuple = None) -> List[float]:
        """批量运行查询，返回延迟列表"""
        latencies = []
        for _ in range(count):
            success, latency = self.run_single_query(query, params)
            if success:
                latencies.append(latency)
        return latencies
    
    def benchmark_select(self, concurrency: int, rounds: int) -> Dict:
        """测试 SELECT 查询性能"""
        queries = [
            ("全表扫描", "SELECT * FROM benchmark_orders LIMIT 100"),
            ("索引查询-单行", "SELECT * FROM benchmark_users WHERE id = %s", (500,)),
            ("索引查询-范围", "SELECT * FROM benchmark_orders WHERE user_id BETWEEN %s AND %s", (100, 200)),
            ("聚合查询", "SELECT status, COUNT(*) FROM benchmark_orders GROUP BY status"),
            ("JOIN查询", """
                SELECT u.username, COUNT(o.id) as order_count, SUM(o.amount) as total_amount
                FROM benchmark_users u
                LEFT JOIN benchmark_orders o ON u.id = o.user_id
                GROUP BY u.id
                LIMIT 100
            """),
        ]
        
        results = {}
        for name, query, *params in queries:
            param_tuple = params[0] if params else None
            all_latencies = []
            
            for round_num in range(rounds):
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    futures = [
                        executor.submit(self.run_single_query, query, param_tuple)
                        for _ in range(concurrency * 5)
                    ]
                    for future in as_completed(futures):
                        success, latency = future.result()
                        if success:
                            all_latencies.append(latency)
            
            if all_latencies:
                all_latencies.sort()
                results[name] = {
                    "count": len(all_latencies),
                    "avg": statistics.mean(all_latencies),
                    "p50": all_latencies[len(all_latencies) // 2],
                    "p95": all_latencies[int(len(all_latencies) * 0.95)],
                    "p99": all_latencies[int(len(all_latencies) * 0.99)],
                    "min": min(all_latencies),
                    "max": max(all_latencies),
                }
        
        return results
    
    def benchmark_insert(self, concurrency: int, rounds: int) -> Dict:
        """测试 INSERT 性能"""
        all_latencies = []
        
        for round_num in range(rounds):
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(
                        self.run_single_query,
                        "INSERT INTO benchmark_orders (order_no, user_id, amount, status) VALUES (%s, %s, %s, %s)",
                        (f"PERF{int(time.time()*1000)}{i}", i % 1000 + 1, 99.99, "pending")
                    )
                    for i in range(concurrency * 3)
                ]
                for future in as_completed(futures):
                    success, latency = future.result()
                    if success:
                        all_latencies.append(latency)
        
        if all_latencies:
            all_latencies.sort()
            return {
                "count": len(all_latencies),
                "avg": statistics.mean(all_latencies),
                "p50": all_latencies[len(all_latencies) // 2],
                "p95": all_latencies[int(len(all_latencies) * 0.95)],
                "p99": all_latencies[int(len(all_latencies) * 0.99)],
                "min": min(all_latencies),
                "max": max(all_latencies),
            }
        return {}
    
    def benchmark_update(self, concurrency: int, rounds: int) -> Dict:
        """测试 UPDATE 性能"""
        all_latencies = []
        
        # 先获取一些存在的ID
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM benchmark_orders LIMIT 100")
        ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        if not ids:
            return {}
        
        for round_num in range(rounds):
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(
                        self.run_single_query,
                        "UPDATE benchmark_orders SET status = %s WHERE id = %s",
                        ("completed", ids[i % len(ids)])
                    )
                    for i in range(concurrency * 3)
                ]
                for future in as_completed(futures):
                    success, latency = future.result()
                    if success:
                        all_latencies.append(latency)
        
        if all_latencies:
            all_latencies.sort()
            return {
                "count": len(all_latencies),
                "avg": statistics.mean(all_latencies),
                "p50": all_latencies[len(all_latencies) // 2],
                "p95": all_latencies[int(len(all_latencies) * 0.95)],
                "p99": all_latencies[int(len(all_latencies) * 0.99)],
                "min": min(all_latencies),
                "max": max(all_latencies),
            }
        return {}
    
    def run_benchmark(self, concurrency: int, rounds: int) -> Dict:
        """运行完整基准测试"""
        print(f"\n{'='*60}")
        print(f"并发级别: {concurrency}, 轮次: {rounds}")
        print(f"{'='*60}")
        
        result = {
            "concurrency": concurrency,
            "timestamp": datetime.now().isoformat(),
        }
        
        # SELECT 测试
        print("\n  [SELECT 测试]")
        select_results = self.benchmark_select(concurrency, rounds)
        for name, metrics in select_results.items():
            print(f"    {name}: avg={metrics['avg']:.2f}ms, p95={metrics['p95']:.2f}ms")
            result[f"select_{name.replace(' ', '_').lower()}_avg"] = metrics["avg"]
            result[f"select_{name.replace(' ', '_').lower()}_p95"] = metrics["p95"]
        
        # INSERT 测试
        print("\n  [INSERT 测试]")
        insert_result = self.benchmark_insert(concurrency, rounds)
        if insert_result:
            print(f"    avg={insert_result['avg']:.2f}ms, p95={insert_result['p95']:.2f}ms, max={insert_result['max']:.2f}ms")
            result["insert_avg"] = insert_result["avg"]
            result["insert_p95"] = insert_result["p95"]
        
        # UPDATE 测试
        print("\n  [UPDATE 测试]")
        update_result = self.benchmark_update(concurrency, rounds)
        if update_result:
            print(f"    avg={update_result['avg']:.2f}ms, p95={update_result['p95']:.2f}ms, max={update_result['max']:.2f}ms")
            result["update_avg"] = update_result["avg"]
            result["update_p95"] = update_result["p95"]
        
        return result
    
    def save_results(self, results: List[Dict]):
        """保存测试结果"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        for r in results:
            cursor.execute("""
                INSERT INTO benchmark_results 
                (test_name, concurrency, total_requests, success_count, error_count,
                 avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms,
                 min_latency_ms, max_latency_ms, throughput_qps)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                r.get("test_name", "mysql_benchmark"),
                r.get("concurrency", 1),
                r.get("total_requests", 0),
                r.get("success_count", 0),
                r.get("error_count", 0),
                r.get("avg_latency_ms", 0),
                r.get("p50_latency_ms", 0),
                r.get("p95_latency_ms", 0),
                r.get("p99_latency_ms", 0),
                r.get("min_latency_ms", 0),
                r.get("max_latency_ms", 0),
                r.get("throughput_qps", 0),
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def print_summary(self, results: List[Dict]):
        """打印测试汇总"""
        print("\n" + "="*80)
        print("性能压测汇总报告")
        print("="*80)
        
        print(f"\n{'并发数':<10} {'SELECT-avg':<12} {'SELECT-p95':<12} {'INSERT-avg':<12} {'UPDATE-avg':<12}")
        print("-" * 60)
        
        for r in results:
            select_avg = r.get("select_全表扫描_avg", 0)
            select_p95 = r.get("select_全表扫描_p95", 0)
            insert_avg = r.get("insert_avg", 0)
            update_avg = r.get("update_avg", 0)
            
            print(f"{r['concurrency']:<10} {select_avg:<12.2f} {select_p95:<12.2f} {insert_avg:<12.2f} {update_avg:<12.2f}")
        
        print("\n延迟分析:")
        if results:
            # 找出最佳并发点
            best_throughput = max(results, key=lambda x: 1/x.get("select_全表扫描_avg", 999999))
            best_latency = min(results, key=lambda x: x.get("select_全表扫描_avg", 999999))
            
            print(f"  最佳吞吐量并发点: {best_throughput['concurrency']} (SELECT avg: {best_throughput.get('select_全表扫描_avg', 0):.2f}ms)")
            print(f"  最低延迟并发点: {best_latency['concurrency']} (SELECT avg: {best_latency.get('select_全表扫描_avg', 0):.2f}ms)")


def main():
    print("\n" + "="*80)
    print("MySQL 性能压测")
    print("="*80)
    
    benchmark = MySQLBenchmark(PERF_MYSQL_CONFIG)
    
    # 创建测试表
    benchmark.create_test_tables()
    
    # 准备测试数据
    benchmark.prepare_test_data(user_count=1000, order_count=10000)
    
    # 运行不同并发级别的测试
    all_results = []
    for concurrency in BENCHMARK_CONFIG["concurrency_levels"]:
        result = benchmark.run_benchmark(
            concurrency=concurrency,
            rounds=BENCHMARK_CONFIG["test_rounds"]
        )
        all_results.append(result)
    
    # 打印汇总
    benchmark.print_summary(all_results)
    
    # 保存结果
    benchmark.save_results(all_results)
    
    print("\n✅ 性能压测完成")
    
    return all_results


if __name__ == "__main__":
    results = main()
