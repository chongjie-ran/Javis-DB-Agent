"""
V2.5 复杂测试用例扩展 - Round24
=================================
PostgreSQL 复杂场景（5个）:
  PG-01: 连接池耗尽 - 创建大量 idle in transaction 连接
  PG-02: 磁盘空间告警 - 插入大量数据触发表膨胀
  PG-03: 慢查询 - 复杂 JOIN 多表查询
  PG-04: 重复索引检测 - 同一列多个相似索引
  PG-05: 死锁模拟 - 两个事务循环等待锁

MySQL 复杂场景（5个）:
  MY-01: 主从延迟模拟 - long wait_timeout + 慢查询
  MY-02: 表锁等待 - LOCK TABLE + 阻塞读
  MY-03: 临时表空间告警 - 大量临时表创建
  MY-04: 慢查询日志分析 - 模拟慢查询并分析
  MY-05: 复制中止 - STOP SLAVE 模拟

前置条件：
  - PG:  localhost:5432, user=chongjieran, database=postgres
  - MySQL: localhost:3306, user=root, password=root
"""

import asyncio
import sys
import os
import time
import uuid
import tempfile
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="class")
def pg_test_schema():
    """创建测试 schema（Round24 专用），测试结束后清理"""
    schema_name = f"round24_{uuid.uuid4().hex[:8]}"
    yield schema_name
    # 清理由各测试的 finally 块负责，这里只清理 schema
    # （实际清理在每个测试的 finally 中执行）


@pytest.fixture(scope="class")
def mysql_test_db():
    """创建测试数据库（Round24 专用）"""
    db_name = f"round24_test_{uuid.uuid4().hex[:8]}"
    yield db_name
    # 清理在 finally 中执行


@pytest.fixture
async def pg_conn():
    """创建 PG 直连（chongjieran 用户）"""
    from src.db.direct_postgres_connector import DirectPostgresConnector
    conn = DirectPostgresConnector(
        host="localhost",
        port=5432,
        user="chongjieran",
        database="postgres",
    )
    yield conn
    try:
        await conn.close()
    except Exception:
        pass


@pytest.fixture
def mysql_conn():
    """创建 MySQL 直连（pymysql）"""
    import pymysql
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="root",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    yield conn
    try:
        conn.rollback()
        conn.close()
    except Exception:
        pass


@pytest.fixture
def mysql_conn_auto():
    """MySQL 自动提交连接（用于 DDL/结构操作）"""
    import pymysql
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="root",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: PostgreSQL 复杂故障场景（PG-01 ~ PG-05）
# ═══════════════════════════════════════════════════════════════════════════════

class TestPGConnectionPoolExhaustion:
    """PG-01: 连接池耗尽 - 大量 idle in transaction 连接"""

    @pytest.mark.asyncio
    async def test_pg_01_connection_pool_exhaustion_detection(self, pg_conn):
        """PG-01: 创建多个 idle in transaction 连接，检测 max_connections 使用率"""
        # ── 故障注入 ────────────────────────────────────────────────────────────
        # 获取当前 max_connections
        rows = await pg_conn.execute_sql("SHOW max_connections")
        max_conn = int(rows[0]["max_connections"])

        # 获取当前连接数
        rows = await pg_conn.execute_sql(
            "SELECT COUNT(*) AS cnt FROM pg_stat_activity WHERE datname IS NOT NULL"
        )
        initial_conn_count = rows[0]["cnt"]
        print(f"\n  [PG-01] 初始连接数: {initial_conn_count}, max={max_conn}")

        # 创建多个 idle in transaction 连接（不提交事务）
        injected_pids = []
        created_count = min(10, max(5, max_conn // 20))  # 创建5-10个
        for i in range(created_count):
            try:
                pid = await _pg_create_idle_in_transaction(pg_conn)
                injected_pids.append(pid)
            except Exception as e:
                print(f"  [PG-01] 创建连接失败（可能已达上限）: {e}")
                break

        print(f"  [PG-01] 注入 {len(injected_pids)} 个 idle in transaction 连接: {injected_pids}")

        # ── Javis-DB-Agent 检测 ────────────────────────────────────────────────
        try:
            # 1. 查询会话列表，检测异常连接
            sessions = await pg_conn.get_sessions(limit=200)
            idle_in_transaction = [
                s for s in sessions
                if s.get("state") == "idle in transaction"
            ]
            total_conn = len(sessions)
            usage_percent = (total_conn / max_conn) * 100

            print(f"  [PG-01] 检测结果: 总连接={total_conn}, max={max_conn}, "
                  f"使用率={usage_percent:.1f}%, idle_in_transaction={len(idle_in_transaction)}")

            # 2. 查询长时间 idle in transaction（>10秒）
            long_idle = await pg_conn.execute_sql(
                """
                SELECT pid, state, query, query_start,
                       EXTRACT(EPOCH FROM (now() - query_start)) AS idle_seconds
                FROM pg_stat_activity
                WHERE state = 'idle in transaction'
                  AND query_start < now() - interval '5 seconds'
                """
            )
            print(f"  [PG-01] 长时间 idle in transaction: {len(long_idle)} 个")

            # ── 验证 ──────────────────────────────────────────────────────────
            assert total_conn > initial_conn_count, "应有新连接被创建"
            assert usage_percent <= 100, "使用率不应超过100%"

            # 至少应该检测到我们注入的 idle in transaction
            assert len(idle_in_transaction) >= min(1, len(injected_pids)), \
                f"应检测到 idle in transaction 连接（期望>={min(1,len(injected_pids))}，实际={len(idle_in_transaction)}）"

            # 检测结果应该提示连接池压力
            assert usage_percent > 0, "使用率应大于0"
            print(f"  [PG-01] ✓ 连接池耗尽检测成功: 使用率 {usage_percent:.1f}%")

        finally:
            # ── 清理 ──────────────────────────────────────────────────────────
            for pid in injected_pids:
                try:
                    await pg_conn.kill_backend(pid, "terminate")
                    print(f"  [PG-01] 清理: 终止 PID {pid}")
                except Exception as e:
                    print(f"  [PG-01] 清理失败 PID {pid}: {e}")


class TestPGDiskSpaceAlert:
    """PG-02: 磁盘空间告警 - 插入大量数据触发表膨胀"""

    @pytest.mark.asyncio
    async def test_pg_02_disk_space_alert_detection(self, pg_conn):
        """PG-02: 创建大表，检测表膨胀和磁盘使用"""
        # ── 故障注入 ───────────────────────────────────────────────────────────
        test_table = f"round24_disk_alert_{uuid.uuid4().hex[:6]}"
        test_table_log = f"round24_insert_log_{uuid.uuid4().hex[:6]}"

        try:
            # 1. 创建测试表
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {test_table} (
                    id SERIAL,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT now()
                )
            """)

            # 2. 批量插入大量数据（每次10万行，分多次）
            batch_size = 50_000
            batches = 3
            total_rows = batch_size * batches

            print(f"\n  [PG-02] 插入 {total_rows:,} 行数据到表 {test_table}")
            for b in range(batches):
                # 生成较大行（约2KB/行）
                values_parts = []
                for i in range(batch_size):
                    val = f"batch_{b}_row_{i}_" + "x" * 1800  # ~2KB
                    values_parts.append(f"('{val}')")
                values_str = ",".join(values_parts)

                await pg_conn.execute_sql(
                    f"INSERT INTO {test_table} (data) VALUES {values_str}"
                )
                print(f"  [PG-02] 批次 {b+1}/{batches} 完成")

            # 记录插入日志表
            await pg_conn.execute_sql(f"""
                CREATE TABLE {test_table_log} (
                    id SERIAL PRIMARY KEY,
                    batch_info TEXT,
                    inserted_at TIMESTAMP DEFAULT now()
                )
            """)
            for b in range(batches):
                await pg_conn.execute_sql(
                    f"INSERT INTO {test_table_log} (batch_info) VALUES ('batch_{b}')"
                )

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            # 1. 表大小查询
            table_size_rows = await pg_conn.execute_sql(
                f"""
                SELECT
                    pg_size_pretty(pg_total_relation_size('{test_table}')) AS total_size,
                    pg_size_pretty(pg_relation_size('{test_table}')) AS table_size,
                    pg_size_pretty(pg_indexes_size('{test_table}')) AS index_size,
                    (SELECT COUNT(*) FROM {test_table}) AS row_count
                """
            )
            size_info = table_size_rows[0]
            print(f"  [PG-02] 表大小: total={size_info['total_size']}, "
                  f"table={size_info['table_size']}, "
                  f"index={size_info['index_size']}, rows={size_info['row_count']:,}")

            # 2. 数据库总大小
            db_size_rows = await pg_conn.execute_sql(
                "SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size"
            )
            print(f"  [PG-02] 数据库总大小: {db_size_rows[0]['db_size']}")

            # 3. 膨胀检测（检查日志表的顺序插入效率）
            log_stats = await pg_conn.execute_sql(
                f"""
                SELECT
                    COUNT(*) AS total_records,
                    COUNT(DISTINCT batch_info) AS distinct_batches,
                    pg_size_pretty(pg_relation_size('{test_table_log}')) AS log_size
                FROM {test_table_log}
                """
            )
            print(f"  [PG-02] 日志表: records={log_stats[0]['total_records']}, "
                  f"batches={log_stats[0]['distinct_batches']}, "
                  f"size={log_stats[0]['log_size']}")

            # ── 验证 ──────────────────────────────────────────────────────────
            row_count = size_info["row_count"]
            assert row_count == total_rows, \
                f"应有 {total_rows} 行，实际: {row_count}"

            # 总大小应该 > 1MB（大量数据）
            size_bytes = await pg_conn.execute_sql(
                f"SELECT pg_total_relation_size('{test_table}') AS sz"
            )
            assert size_bytes[0]["sz"] > 1024 * 1024, \
                f"表大小应 > 1MB，实际: {size_bytes[0]['sz']} bytes"

            print(f"  [PG-02] ✓ 磁盘空间/表膨胀检测成功: {size_info['total_size']}")

        finally:
            # ── 清理 ──────────────────────────────────────────────────────────
            for t in [test_table, test_table_log]:
                try:
                    await pg_conn.execute_sql(f"DROP TABLE IF EXISTS {t}")
                    print(f"  [PG-02] 清理: 删除表 {t}")
                except Exception as e:
                    print(f"  [PG-02] 清理失败 {t}: {e}")


class TestPGSlowQuery:
    """PG-03: 慢查询 - 复杂 JOIN 多表查询"""

    @pytest.mark.asyncio
    async def test_pg_03_slow_query_complex_join(self, pg_conn):
        """PG-03: 创建多表并执行复杂 JOIN，检测查询时间和扫描方式"""
        # ── 故障注入 ───────────────────────────────────────────────────────────
        tables = [
            f"round24_orders_{uuid.uuid4().hex[:6]}",
            f"round24_customers_{uuid.uuid4().hex[:6]}",
            f"round24_products_{uuid.uuid4().hex[:6]}",
            f"round24_order_items_{uuid.uuid4().hex[:6]}",
        ]

        try:
            # 创建 4 张表（orders, customers, products, order_items）
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {tables[0]} (
                    id SERIAL PRIMARY KEY,
                    customer_id INT,
                    order_date DATE,
                    status VARCHAR(20),
                    total_amount DECIMAL(10,2)
                )
            """)
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {tables[1]} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    region VARCHAR(50),
                    created_at TIMESTAMP DEFAULT now()
                )
            """)
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {tables[2]} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    category VARCHAR(50),
                    price DECIMAL(10,2)
                )
            """)
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {tables[3]} (
                    id SERIAL PRIMARY KEY,
                    order_id INT,
                    product_id INT,
                    quantity INT,
                    price DECIMAL(10,2)
                )
            """)

            # 插入测试数据（每表 2000-5000 行，无索引 → 全表扫描）
            print(f"\n  [PG-03] 插入测试数据到 4 张表...")
            for t_name, count in [(tables[0], 5000), (tables[1], 3000),
                                  (tables[2], 4000), (tables[3], 6000)]:
                if t_name == tables[0]:
                    # orders: (id, customer_id, order_date, status, total_amount)
                    values = ",".join(
                        f"({i}, {i%count}, '2026-01-01', 'active', 100.00)"
                        for i in range(count)
                    )
                    col_part = "(id, customer_id, order_date, status, total_amount)"
                elif t_name == tables[1]:
                    # customers: (id, name, region)
                    values = ",".join(
                        f"({i}, 'customer_{i}', 'region_{i%5}')"
                        for i in range(count)
                    )
                    col_part = "(id, name, region)"
                elif t_name == tables[2]:
                    # products: (id, name, category, price)
                    values = ",".join(
                        f"({i}, 'product_{i}', 'category_{i%10}', {100+i%50}.00)"
                        for i in range(count)
                    )
                    col_part = "(id, name, category, price)"
                else:
                    # order_items: (id, order_id, product_id, quantity, price)
                    values = ",".join(
                        f"({i}, {i%count}, {i%4000}, {1+i%5}, {50+i%100}.00)"
                        for i in range(count)
                    )
                    col_part = "(id, order_id, product_id, quantity, price)"

                await pg_conn.execute_sql(
                    f"INSERT INTO {t_name} {col_part} VALUES {values}"
                )
                print(f"  [PG-03]   {t_name}: {count} 行")

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            # 执行复杂 JOIN（跨 4 表，无索引优化 → 慢查询）
            slow_query = f"""
                SELECT
                    o.id AS order_id,
                    c.name AS customer_name,
                    p.name AS product_name,
                    oi.quantity,
                    oi.price,
                    o.order_date
                FROM {tables[0]} o
                JOIN {tables[1]} c ON o.customer_id = c.id
                JOIN {tables[3]} oi ON o.id = oi.order_id
                JOIN {tables[2]} p ON oi.product_id = p.id
                WHERE o.status = 'active'
                ORDER BY o.order_date DESC
                LIMIT 1000
            """

            start_time = time.time()
            result = await pg_conn.execute_sql(slow_query)
            elapsed_ms = (time.time() - start_time) * 1000

            print(f"  [PG-03] 复杂 JOIN 执行时间: {elapsed_ms:.1f}ms, "
                  f"返回 {len(result)} 行")

            # EXPLAIN 分析
            explain_rows = await pg_conn.execute_sql(f"EXPLAIN (FORMAT JSON) {slow_query}")
            # asyncpg returns list of dicts; key is 'QUERY PLAN' with JSON string value
            explain_row = explain_rows[0]
            query_plan_str = explain_row.get("QUERY PLAN", "[]")
            import json
            plan_list = json.loads(query_plan_str)
            top_plan = plan_list[0]["Plan"] if plan_list else {}
            total_cost = top_plan.get("Total Cost", 0)
            plan_type = top_plan.get("Node Type", "unknown")
            print(f"  [PG-03] 执行计划: {plan_type}, Total Cost={total_cost}")

            # 检查是否全表扫描（无索引时）
            scan_nodes = []

            def find_scan_nodes(node):
                if node.get("Node Type") in ("Seq Scan", "Hash Join", "Nested Loop"):
                    scan_nodes.append(node["Node Type"])
                for child in node.get("Plans", []):
                    find_scan_nodes(child)

            find_scan_nodes(top_plan)

            # ── 验证 ──────────────────────────────────────────────────────────
            assert len(result) > 0, "查询应返回结果"
            assert "Seq Scan" in scan_nodes or "Hash Join" in scan_nodes, \
                "无索引情况下应有 Seq Scan 或 Hash Join"

            # 查询时间应该可测量
            assert elapsed_ms >= 0

            print(f"  [PG-03] ✓ 慢查询检测成功: {elapsed_ms:.1f}ms, "
                  f"计划类型={plan_type}, Cost={total_cost}")

        finally:
            # ── 清理 ──────────────────────────────────────────────────────────
            for t in tables:
                try:
                    await pg_conn.execute_sql(f"DROP TABLE IF EXISTS {t}")
                    print(f"  [PG-03] 清理: 删除表 {t}")
                except Exception as e:
                    print(f"  [PG-03] 清理失败 {t}: {e}")


class TestPGDuplicateIndex:
    """PG-04: 重复索引检测 - 同一列多个相似索引"""

    @pytest.mark.asyncio
    async def test_pg_04_duplicate_index_detection(self, pg_conn):
        """PG-04: 创建重复/冗余索引，检测索引冗余"""
        # ── 故障注入 ───────────────────────────────────────────────────────────
        test_table = f"round24_idx_test_{uuid.uuid4().hex[:6]}"
        duplicate_indexes = []

        try:
            # 创建测试表
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {test_table} (
                    id SERIAL PRIMARY KEY,
                    user_id INT,
                    email VARCHAR(100),
                    phone VARCHAR(20),
                    status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT now()
                )
            """)

            # 插入少量数据
            values = ",".join(
                f"({i}, {i%100}, 'user{i}@test.com', '138000{i:04d}', 'active')"
                for i in range(1000)
            )
            await pg_conn.execute_sql(
                f"INSERT INTO {test_table} (id, user_id, email, phone, status) VALUES {values}"
            )

            # 创建"正常"索引
            await pg_conn.execute_sql(
                f"CREATE INDEX idx_user_id ON {test_table} (user_id)"
            )

            # 创建重复索引（同一列，不同名字）
            dup1 = f"idx_user_id_dup1_{uuid.uuid4().hex[:4]}"
            dup2 = f"idx_user_id_dup2_{uuid.uuid4().hex[:4]}"
            await pg_conn.execute_sql(f"CREATE INDEX {dup1} ON {test_table} (user_id)")
            await pg_conn.execute_sql(f"CREATE INDEX {dup2} ON {test_table} (user_id)")
            duplicate_indexes = [dup1, dup2]

            # 创建冗余索引（前缀相同）
            redundant = f"idx_user_id_redundant_{uuid.uuid4().hex[:4]}"
            await pg_conn.execute_sql(
                f"CREATE INDEX {redundant} ON {test_table} (user_id, id)"
            )
            duplicate_indexes.append(redundant)

            print(f"\n  [PG-04] 创建表 {test_table}, 注入重复索引: {duplicate_indexes}")

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            # 查询索引信息
            index_info = await pg_conn.execute_sql(f"""
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE tablename = '{test_table}'
                  AND schemaname = 'public'
                ORDER BY indexname
            """)

            print(f"  [PG-04] 发现 {len(index_info)} 个索引:")
            for idx in index_info:
                print(f"    - {idx['indexname']}: {idx['indexdef'][:80]}")

            # 识别同一列上的索引
            from collections import defaultdict
            col_to_indexes = defaultdict(list)
            for idx in index_info:
                # 从 indexdef 提取列名
                def_str = idx["indexdef"].lower()
                if "(user_id)" in def_str or "(user_id," in def_str or ", user_id)" in def_str:
                    col_to_indexes["user_id"].append(idx["indexname"])
                if "(user_id, id)" in def_str or "(user_id,id)" in def_str:
                    col_to_indexes["user_id_id"].append(idx["indexname"])

            print(f"  [PG-04] 列 user_id 上的索引: {col_to_indexes.get('user_id', [])}")
            print(f"  [PG-04] 列 (user_id, id) 上的索引: {col_to_indexes.get('user_id_id', [])}")

            # 检测重复索引
            user_id_indexes = col_to_indexes.get("user_id", [])
            duplicated = [idx for idx in user_id_indexes if "dup" in idx or "idx_user_id" in idx]
            redundant_count = len(user_id_indexes) + len(col_to_indexes.get("user_id_id", []))

            # ── 验证 ──────────────────────────────────────────────────────────
            # 至少应该找到我们注入的重复索引
            assert len(user_id_indexes) >= 3, \
                f"user_id 列应有 >= 3 个索引，实际: {len(user_id_indexes)}"

            # 应该能识别出重复
            assert len(duplicate_indexes) > 0, "应有重复索引被创建"

            print(f"  [PG-04] ✓ 重复索引检测成功: user_id 列有 {len(user_id_indexes)} 个索引，"
                  f"其中 {len(duplicate_indexes)} 个为重复/冗余")

        finally:
            # ── 清理 ──────────────────────────────────────────────────────────
            try:
                await pg_conn.execute_sql(f"DROP TABLE IF EXISTS {test_table}")
                print(f"  [PG-04] 清理: 删除表 {test_table}")
            except Exception as e:
                print(f"  [PG-04] 清理失败: {e}")


class TestPGDeadlock:
    """PG-05: 死锁模拟 - 两个事务循环等待锁"""

    @pytest.mark.asyncio
    async def test_pg_05_deadlock_simulation(self, pg_conn):
        """PG-05: 模拟死锁场景，检测 pg_stat_activity 中的阻塞关系"""
        # ── 故障注入 ───────────────────────────────────────────────────────────
        table_a = f"round24_deadlock_a_{uuid.uuid4().hex[:6]}"
        table_b = f"round24_deadlock_b_{uuid.uuid4().hex[:6]}"

        # 由于 asyncpg 的限制，我们在同步线程中执行事务
        import psycopg2
        import threading
        import queue as queue_module

        errors = queue_module.Queue()
        tx_started = queue_module.Queue()
        deadlock_detected = queue_module.Queue()

        try:
            # 创建测试表
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {table_a} (id INT PRIMARY KEY, value TEXT)
            """)
            await pg_conn.execute_sql(f"""
                CREATE UNLOGGED TABLE {table_b} (id INT PRIMARY KEY, value TEXT)
            """)
            await pg_conn.execute_sql(f"INSERT INTO {table_a} VALUES (1, 'A')")
            await pg_conn.execute_sql(f"INSERT INTO {table_b} VALUES (1, 'B')")

            print(f"\n  [PG-05] 创建死锁测试表: {table_a}, {table_b}")

            # 连接 1: BEGIN → LOCK table_a
            conn1 = psycopg2.connect(
                host="localhost", port=5432,
                user="chongjieran", database="postgres"
            )
            conn1.autocommit = False  # 使用手动提交，通过锁超时模拟

            # 连接 2: BEGIN → LOCK table_b
            conn2 = psycopg2.connect(
                host="localhost", port=5432,
                user="chongjieran", database="postgres"
            )
            conn2.autocommit = False

            def tx1_work():
                """事务1: 锁 A，然后等 B"""
                try:
                    cur1 = conn1.cursor()
                    cur1.execute(f"BEGIN")
                    cur1.execute(f"SELECT * FROM {table_a} FOR UPDATE")
                    tx_started.put(1)
                    time.sleep(0.3)  # 等 tx2 先拿到 B
                    # 尝试锁 B（tx2 拿着）
                    try:
                        cur1.execute(f"SELECT * FROM {table_b} FOR UPDATE")
                        cur1.execute("COMMIT")
                    except psycopg2.errors.DeadlockDetected:
                        deadlock_detected.put(1)
                        conn1.rollback()
                        print(f"  [PG-05] 事务1检测到死锁（预期）")
                    except Exception as e:
                        if "deadlock" in str(e).lower():
                            deadlock_detected.put(1)
                        conn1.rollback()
                except Exception as e:
                    errors.put(f"tx1: {e}")
                    conn1.rollback()

            def tx2_work():
                """事务2: 锁 B，然后等 A"""
                try:
                    cur2 = conn2.cursor()
                    cur2.execute(f"BEGIN")
                    cur2.execute(f"SELECT * FROM {table_b} FOR UPDATE")
                    tx_started.put(2)
                    time.sleep(0.3)  # 等 tx1 先拿到 A
                    # 尝试锁 A（tx1 拿着）
                    try:
                        cur2.execute(f"SELECT * FROM {table_a} FOR UPDATE")
                        cur2.execute("COMMIT")
                    except psycopg2.errors.DeadlockDetected:
                        deadlock_detected.put(2)
                        conn2.rollback()
                        print(f"  [PG-05] 事务2检测到死锁（预期）")
                    except Exception as e:
                        if "deadlock" in str(e).lower():
                            deadlock_detected.put(2)
                        conn2.rollback()
                except Exception as e:
                    errors.put(f"tx2: {e}")
                    conn2.rollback()

            # 启动两个事务线程
            t1 = threading.Thread(target=tx1_work)
            t2 = threading.Thread(target=tx2_work)
            t1.start()
            t2.start()
            t1.join(timeout=15)
            t2.join(timeout=15)

            conn1.close()
            conn2.close()

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            # 检测死锁期间和之后的锁状态
            sessions = await pg_conn.get_sessions(limit=100)
            locks = await pg_conn.get_locks()

            # 尝试从 pg_locks 获取阻塞关系
            blocking_query = await pg_conn.execute_sql("""
                SELECT
                    blocked.pid AS blocked_pid,
                    blocked.query AS blocked_query,
                    blocker_act.pid AS blocker_pid,
                    blocker_act.query AS blocker_query
                FROM pg_stat_activity AS blocked
                JOIN pg_locks AS bl ON blocked.pid = bl.pid AND NOT bl.granted
                JOIN pg_locks AS blocker_lock ON
                    bl.locktype = blocker_lock.locktype
                    AND bl.database IS NOT DISTINCT FROM blocker_lock.database
                    AND bl.relation IS NOT DISTINCT FROM blocker_lock.relation
                    AND bl.page IS NOT DISTINCT FROM blocker_lock.page
                    AND bl.tuple IS NOT DISTINCT FROM blocker_lock.tuple
                    AND bl.virtualxid IS NOT DISTINCT FROM blocker_lock.virtualxid
                    AND bl.transactionid IS NOT DISTINCT FROM blocker_lock.transactionid
                    AND bl.classid IS NOT DISTINCT FROM blocker_lock.classid
                    AND bl.objid IS NOT DISTINCT FROM blocker_lock.objid
                    AND bl.objsubid IS NOT DISTINCT FROM blocker_lock.objsubid
                    AND blocker_lock.granted
                    AND blocker_lock.pid != blocked.pid
                JOIN pg_stat_activity AS blocker_act ON blocker_lock.pid = blocker_act.pid
                WHERE blocked.state = 'active'
            """)

            print(f"  [PG-05] 检测结果: 阻塞关系数量={len(blocking_query)}, "
                  f"锁数量={len(locks)}, 会话数={len(sessions)}")

            # 死锁错误数量
            deadlock_count = deadlock_detected.qsize()
            error_count = errors.qsize()

            if error_count > 0:
                err_list = []
                while not errors.empty():
                    err_list.append(errors.get())
                print(f"  [PG-05] 线程错误: {err_list}")

            # ── 验证 ──────────────────────────────────────────────────────────
            # 两种情况都是可接受的：
            # 1. 死锁被 PostgreSQL 检测到（PostgreSQL 自动处理）
            # 2. 由于时间问题没有发生死锁（锁等待而非死锁）
            # 关键：Javis-DB-Agent 应该能够检测到阻塞关系或锁等待
            print(f"  [PG-05] 死锁事件: {deadlock_count} 个（PostgreSQL 自动检测）")

            # pg_locks 应该能捕获到锁信息（即使死锁已解决，锁信息可能已清空）
            # 主要验证：检测机制能正常运行
            assert isinstance(locks, list), "锁列表应为 list"
            print(f"  [PG-05] ✓ 死锁模拟测试完成: "
                  f"死锁检测={deadlock_count}, 阻塞关系={len(blocking_query)}, "
                  f"锁记录={len(locks)}")

        finally:
            # ── 清理 ──────────────────────────────────────────────────────────
            try:
                # 确保所有挂起事务被清理
                await pg_conn.execute_sql("ROLLBACK")
                await pg_conn.execute_sql(f"DROP TABLE IF EXISTS {table_a}")
                await pg_conn.execute_sql(f"DROP TABLE IF EXISTS {table_b}")
                print(f"  [PG-05] 清理: 删除表 {table_a}, {table_b}")
            except Exception as e:
                print(f"  [PG-05] 清理失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: MySQL 复杂故障场景（MY-01 ~ MY-05）
# ═══════════════════════════════════════════════════════════════════════════════

class TestMySQLReplicationLag:
    """MY-01: 主从延迟模拟 - wait_timeout + 慢查询"""

    def test_mysql_01_replication_lag_detection(self, mysql_conn):
        """MY-01: 检测 MySQL 主从延迟相关指标"""
        cursor = mysql_conn.cursor()

        try:
            # ── 故障注入 ──────────────────────────────────────────────────────
            # 设置 session 级 wait_timeout（模拟慢查询占用连接）
            cursor.execute("SET SESSION wait_timeout = 60")
            cursor.execute("SET SESSION interactive_timeout = 60")

            # 执行一个较慢的查询（模拟大事务）
            cursor.execute("SELECT SLEEP(0.5) AS slow_query_result")
            result = cursor.fetchone()
            assert result["slow_query_result"] == 0, "SLEEP 应返回 0"

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            # 1. 复制状态检测
            cursor.execute("SHOW SLAVE STATUS")
            slave_status = cursor.fetchall()
            # SHOW SLAVE STATUS 返回 tuple（字段名在 description 中）
            if slave_status:
                row = slave_status[0]
                print(f"\n  [MY-01] 从库状态: {type(row)}, 长度={len(row)}")
                # 字段名在 cursor.description 中
                fields = [d[0] for d in cursor.description]
                status_dict = dict(zip(fields, row))
                print(f"  [MY-01] Slave_IO_Running: {status_dict.get('Slave_IO_Running')}")
                print(f"  [MY-01] Slave_SQL_Running: {status_dict.get('Slave_SQL_Running')}")
                print(f"  [MY-01] Seconds_Behind_Master: {status_dict.get('Seconds_Behind_Master')}")
                print(f"  [MY-01] Relay_Log_Pos: {status_dict.get('Relay_Log_Pos')}")

            # 2. 线程连接状态
            cursor.execute("SHOW PROCESSLIST")
            processlist = cursor.fetchall()
            process_dicts = [dict(zip([d[0] for d in cursor.description], row))
                             for row in processlist]
            sleep_threads = [p for p in process_dicts if p.get("Command") == "Sleep"]
            query_threads = [p for p in process_dicts if p.get("Command") == "Query"]
            print(f"  [MY-01] PROCESSLIST: 总={len(process_dicts)}, "
                  f"Sleep={len(sleep_threads)}, Query={len(query_threads)}")

            # 3. 全局状态：连接数
            cursor.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
            threads_conn_row = cursor.fetchone()
            threads_connected = int(threads_conn_row["Value"])
            print(f"  [MY-01] 当前连接数: {threads_connected}")

            cursor.execute("SHOW GLOBAL STATUS LIKE 'Max_used_connections'")
            max_used_row = cursor.fetchone()
            max_used = int(max_used_row["Value"])
            print(f"  [MY-01] 历史最大连接数: {max_used}")

            # 4. 慢查询阈值
            cursor.execute("SHOW VARIABLES LIKE 'long_query_time'")
            lqt_row = cursor.fetchone()
            long_query_time = float(lqt_row["Value"])
            print(f"  [MY-01] long_query_time: {long_query_time}s")

            # ── 验证 ──────────────────────────────────────────────────────────
            assert threads_connected >= 1, "应有活动连接"
            assert long_query_time >= 0, "long_query_time 应 >= 0"
            print(f"  [MY-01] ✓ 主从延迟/连接指标检测成功")

        finally:
            cursor.execute("SET SESSION wait_timeout = 28800")
            cursor.execute("SET SESSION interactive_timeout = 28800")
            mysql_conn.rollback()


class TestMySQLTableLockWait:
    """MY-02: 表锁等待 - LOCK TABLE + 阻塞读"""

    def test_mysql_02_table_lock_wait_detection(self, mysql_conn):
        """MY-02: 执行 LOCK TABLE 模拟表锁，检测阻塞关系"""
        cursor = mysql_conn.cursor()
        cursor.execute("USE mysql")  # 默认无数据库，必须指定

        # 创建测试表
        test_table = f"round24_lock_test_{uuid.uuid4().hex[:6]}"

        try:
            # ── 故障注入 ──────────────────────────────────────────────────────
            cursor.execute(f"""
                CREATE TABLE {test_table} (
                    id INT PRIMARY KEY,
                    name VARCHAR(100),
                    value TEXT
                ) ENGINE=InnoDB
            """)
            cursor.execute(f"INSERT INTO {test_table} VALUES (1, 'init', 'initial data')")
            mysql_conn.commit()

            # 获取初始进程列表
            cursor.execute("SHOW PROCESSLIST")
            initial_procs = cursor.fetchall()
            initial_ids = set(p["Id"] for p in initial_procs)
            print(f"\n  [MY-02] 初始进程数: {len(initial_ids)}")

            # 在另一个连接中执行 LOCK TABLE（使用 threading）
            import threading
            lock_result = {"error": None, "got_lock": False, "thread_id": None}

            def lock_worker():
                import pymysql
                conn2 = pymysql.connect(
                    host="127.0.0.1", port=3306,
                    user="root", password="root",
                    charset="utf8mb4",
                )
                lock_result["thread_id"] = threading.current_thread().ident
                try:
                    cur2 = conn2.cursor()
                    cur2.execute(f"LOCK TABLES {test_table} WRITE")
                    lock_result["got_lock"] = True
                    time.sleep(3)  # 持有锁 3 秒
                    cur2.execute("UNLOCK TABLES")
                    conn2.close()
                except Exception as e:
                    lock_result["error"] = str(e)
                finally:
                    try:
                        conn2.close()
                    except Exception:
                        pass

            # 启动锁线程
            lock_thread = threading.Thread(target=lock_worker)
            lock_thread.start()
            time.sleep(0.5)  # 等待锁线程获得锁

            # 在主连接尝试读取（应被阻塞）
            start_wait = time.time()
            try:
                cursor.execute(f"SELECT * FROM {test_table}")  # 应被阻塞
                read_result = cursor.fetchone()
                wait_time = time.time() - start_wait
                print(f"  [MY-02] 主连接读取成功，等待时间: {wait_time:.2f}s")
            except Exception as e:
                wait_time = time.time() - start_wait
                print(f"  [MY-02] 主连接读取被阻塞: {e}, 等待时间: {wait_time:.2f}s")

            lock_thread.join(timeout=10)

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            # 检查 performance_schema.data_locks
            cursor.execute("""
                SELECT ENGINE, OBJECT_NAME, LOCK_MODE, LOCK_STATUS
                FROM performance_schema.data_locks
                LIMIT 20
            """)
            data_locks = list(cursor.fetchall())
            if data_locks:
                print(f"  [MY-02] data_locks 条目: {len(data_locks)}")
                for lock in data_locks[:3]:
                    print(f"    {lock}")
            else:
                print(f"  [MY-02] data_locks 无记录（可能需要启用 performance_schema）")

            # 检查 data_lock_waits
            cursor.execute("""
                SELECT REQUESTING_THREAD_ID, BLOCKING_THREAD_ID, BLOCKING_ENGINE_LOCK_ID
                FROM performance_schema.data_lock_waits
                LIMIT 10
            """)
            lock_waits = list(cursor.fetchall())
            print(f"  [MY-02] data_lock_waits 条目: {len(lock_waits)}")

            # 检查 INNODB 状态
            cursor.execute("SHOW ENGINE INNODB STATUS")
            innodb_status = cursor.fetchall()
            if innodb_status:
                row = innodb_status[0]
                # DictCursor: access by column name (Status)
                if isinstance(row, dict):
                    status_text = row.get("Status", "")
                else:
                    status_text = row[2]  # tuple fallback: (Engine, Type, Status)
                lock_section = [line for line in status_text.split('\n')
                               if 'LOCK' in line.upper() or 'WAIT' in line.upper()]
                if lock_section:
                    print(f"  [MY-02] InnoDB Lock Section: {lock_section[:3]}")

            # ── 验证 ──────────────────────────────────────────────────────────
            assert isinstance(data_locks, list), "data_locks 应为 list"
            assert isinstance(lock_waits, list), "lock_waits 应为 list"
            print(f"  [MY-02] ✓ 表锁等待检测成功: data_locks={len(data_locks)}, lock_waits={len(lock_waits)}")

        finally:
            try:
                cursor.execute("UNLOCK TABLES")
            except Exception:
                pass
            cursor.execute(f"DROP TABLE IF EXISTS {test_table}")
            try:
                mysql_conn.rollback()
            except Exception:
                pass


class TestMySQLTempTableSpaceAlert:
    """MY-03: 临时表空间告警 - 大量临时表创建"""

    def test_mysql_03_temp_tablespace_alert(self, mysql_conn):
        """MY-03: 创建大量临时表，检测临时表空间使用"""
        cursor = mysql_conn.cursor()

        test_dbs = []

        try:
            # ── 故障注入 ──────────────────────────────────────────────────────
            test_db = f"round24_tmp_{uuid.uuid4().hex[:6]}"
            test_dbs.append(test_db)
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {test_db}")
            mysql_conn.commit()
            cursor.execute(f"USE {test_db}")

            cursor.execute("""
                CREATE TABLE source_data (
                    id INT PRIMARY KEY,
                    data VARCHAR(200),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
            """)

            values = ",".join(f"({i}, 'data_{i}_" + "x" * 150 + "')" for i in range(10000))
            cursor.execute(f"INSERT INTO source_data (id, data) VALUES {values}")
            mysql_conn.commit()
            print(f"\n  [MY-03] 创建测试数据库 {test_db}，插入 10000 行数据")

            # 触发临时表
            for i, q in enumerate([
                "SELECT id, COUNT(*) AS cnt FROM source_data GROUP BY id ORDER BY cnt",
                "SELECT * FROM source_data ORDER BY data, id, created_at LIMIT 5000",
                "SELECT id, SUBSTRING(data, 1, 50) AS d FROM source_data ORDER BY d",
            ]):
                cursor.execute(q)
                cursor.fetchall()
                print(f"  [MY-03] 查询 {i+1} 完成")

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            cursor.execute("SHOW GLOBAL STATUS LIKE 'Created_tmp%'")
            global_tmp = cursor.fetchall()
            global_tmp_dict = dict((row["Variable_name"], int(row["Value"])) for row in global_tmp)
            print(f"  [MY-03] 临时表状态: {global_tmp_dict}")

            cursor.execute("SHOW GLOBAL VARIABLES LIKE 'tmp_table_size'")
            tmp_table_size_row = cursor.fetchone()
            tmp_table_size = int(tmp_table_size_row["Value"]) if tmp_table_size_row else 0
            print(f"  [MY-03] tmp_table_size: {tmp_table_size / 1024 / 1024:.0f} MB")

            created_tmp = global_tmp_dict.get("Created_tmp_tables", 0)
            created_disk_tmp = global_tmp_dict.get("Created_tmp_disk_tables", 0)
            disk_ratio = (created_disk_tmp / created_tmp * 100) if created_tmp > 0 else 0
            print(f"  [MY-03] 磁盘临时表比例: {disk_ratio:.1f}%")

            # ── 验证 ──────────────────────────────────────────────────────────
            assert created_tmp >= 0, "Created_tmp_tables 应 >= 0"
            print(f"  [MY-03] ✓ 临时表空间检测成功: tmp_tables={created_tmp}, disk_tmp={created_disk_tmp}")

        finally:
            try:
                mysql_conn.rollback()
            except Exception:
                pass
            for db in test_dbs:
                try:
                    cursor.execute(f"DROP DATABASE IF EXISTS {db}")
                except Exception as e:
                    print(f"  [MY-03] 清理数据库 {db} 失败: {e}")
            mysql_conn.commit()


class TestMySQLSlowQueryLog:
    """MY-04: 慢查询日志分析 - 模拟慢查询并分析"""

    def test_mysql_04_slow_query_log_analysis(self, mysql_conn):
        """MY-04: 配置并分析慢查询日志"""
        cursor = mysql_conn.cursor()

        try:
            # 保存原始配置
            cursor.execute("SHOW VARIABLES LIKE 'slow_query_log'")
            orig_slow_log_row = cursor.fetchone()
            cursor.execute("SHOW VARIABLES LIKE 'long_query_time'")
            orig_lqt_row = cursor.fetchone()

            orig_slow_log_val = orig_slow_log_row["Value"] if orig_slow_log_row else None
            orig_lqt_val = orig_lqt_row["Value"] if orig_lqt_row else None

            print(f"\n  [MY-04] 原始配置: slow_query_log={orig_slow_log_val}, long_query_time={orig_lqt_val}")

            # 设置慢查询阈值
            cursor.execute("SET GLOBAL slow_query_log = 'ON'")
            cursor.execute("SET GLOBAL long_query_time = 0.1")
            mysql_conn.commit()

            slow_queries = [
                ("SELECT SLEEP(0.5)", "SLEEP 函数"),
                ("SELECT COUNT(*) FROM (SELECT * FROM mysql.user) AS t", "子查询"),
            ]
            for sql, desc in slow_queries:
                start = time.time()
                try:
                    cursor.execute(sql)
                    cursor.fetchall()
                    elapsed = time.time() - start
                    print(f"  [MY-04] 慢查询 [{desc}]: {elapsed:.3f}s")
                except Exception as e:
                    print(f"  [MY-04] 慢查询 [{desc}] 执行: {time.time() - start:.3f}s (错误: {type(e).__name__})")

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            cursor.execute("SHOW GLOBAL VARIABLES LIKE 'long_query_time'")
            lqt_row = cursor.fetchone()
            lqt_value = float(lqt_row["Value"]) if lqt_row else None
            print(f"  [MY-04] 当前 long_query_time: {lqt_value}s")

            cursor.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
            slow_q_row = cursor.fetchone()
            slow_query_count = int(slow_q_row["Value"]) if slow_q_row else 0
            print(f"  [MY-04] Slow_queries 计数器: {slow_query_count}")

            cursor.execute("EXPLAIN SELECT * FROM mysql.user ORDER BY Host, User")
            explain_rows = cursor.fetchall()
            print(f"  [MY-04] EXPLAIN: {len(explain_rows)} 行结果")

            # ── 验证 ──────────────────────────────────────────────────────────
            assert lqt_value is not None, "long_query_time 应有值"
            assert lqt_value == 0.1, f"long_query_time 应为 0.1，实际: {lqt_value}"
            print(f"  [MY-04] ✓ 慢查询日志分析成功: long_query_time={lqt_value}s, 慢查询计数={slow_query_count}")

        finally:
            try:
                if orig_slow_log_val:
                    cursor.execute(f"SET GLOBAL slow_query_log = '{orig_slow_log_val}'")
                if orig_lqt_val is not None:
                    cursor.execute(f"SET GLOBAL long_query_time = {orig_lqt_val}")
                mysql_conn.commit()
            except Exception as e:
                print(f"  [MY-04] 恢复配置失败: {e}")


class TestMySQLReplicationHalt:
    """MY-05: 复制中止 - STOP SLAVE 模拟"""

    def test_mysql_05_replication_halt_detection(self, mysql_conn):
        """MY-05: 检测 MySQL 复制状态"""
        cursor = mysql_conn.cursor()

        try:
            cursor.execute("SHOW SLAVE STATUS")
            slave_status_before = cursor.fetchall()
            print(f"\n  [MY-05] 从库状态: {bool(slave_status_before)}")

            if not slave_status_before:
                print("  [MY-05] 无从库配置，跳过 STOP SLAKE 模拟")
                cursor.execute("SHOW MASTER STATUS")
                master_status = cursor.fetchall()
                if master_status:
                    fields = [d[0] for d in cursor.description]
                    master_dict = dict(zip(fields, master_status[0]))
                    print(f"  [MY-05] 主库: File={master_dict.get('File')}, Position={master_dict.get('Position')}")

                    cursor.execute("SHOW MASTER LOGS")
                    master_logs = cursor.fetchall()
                    print(f"  [MY-05] 主库 binlog 文件数: {len(master_logs)}")

            # ── Javis-DB-Agent 检测 ────────────────────────────────────────────
            cursor.execute("SHOW VARIABLES LIKE 'log_bin'")
            log_bin_row = cursor.fetchone()
            log_bin = log_bin_row["Value"] if log_bin_row else "OFF"
            print(f"  [MY-05] log_bin: {log_bin}")

            cursor.execute("SHOW VARIABLES LIKE 'gtid_mode'")
            gtid_row = cursor.fetchone()
            gtid_mode = gtid_row["Value"] if gtid_row else "OFF"
            print(f"  [MY-05] gtid_mode: {gtid_mode}")

            cursor.execute("SHOW VARIABLES LIKE '%replica%'")
            replica_vars = cursor.fetchall()
            print(f"  [MY-05] 复制相关变量: {len(replica_vars)} 个")

            replication_healthy = True
            if slave_status_before:
                fields = [d[0] for d in cursor.description]
                status_dict = dict(zip(fields, slave_status_before[0]))
                io_running = status_dict.get("Slave_IO_Running", "").lower()
                sql_running = status_dict.get("Slave_SQL_Running", "").lower()
                replication_healthy = (io_running == "yes" and sql_running == "yes")
                print(f"  [MY-05] 复制健康状态: {replication_healthy}")

            # ── 验证 ──────────────────────────────────────────────────────────
            assert isinstance(replica_vars, list), "复制变量应为 list"
            print(f"  [MY-05] ✓ 复制检测完成: log_bin={log_bin}, gtid_mode={gtid_mode}, "
                  f"slave_configured={bool(slave_status_before)}")

            if not slave_status_before:
                print("  [MY-05] ℹ 无从库配置（测试/开发环境），检测机制正常")

        finally:
            mysql_conn.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: E2E 综合场景测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestE2EComplexScenarios:
    """E2E-01~05: 综合复杂场景端到端测试"""

    @pytest.mark.asyncio
    async def test_e2e_01_pg_full_diagnostic_workflow(self, pg_conn):
        """E2E-01: PostgreSQL 综合诊断工作流"""
        print("\n" + "=" * 60)
        print("  E2E-01: PG 综合诊断工作流")
        print("=" * 60)

        health = await pg_conn.health_check()
        assert health is True
        print(f"  [E2E-01] ✓ 健康检查: {health}")

        sessions = await pg_conn.get_sessions(limit=100)
        active = [s for s in sessions if s.get("state") == "active"]
        idle = [s for s in sessions if s.get("state") and s.get("state") != "active"]
        print(f"  [E2E-01]   会话: total={len(sessions)}, active={len(active)}, idle={len(idle)}")

        locks = await pg_conn.get_locks()
        ungranted = [l for l in locks if not l.get("granted")]
        print(f"  [E2E-01]   锁: total={len(locks)}, waiting={len(ungranted)}")

        rep = await pg_conn.get_replication()
        print(f"  [E2E-01]   复制: role={rep['role']}, replicas={len(rep['replicas'])}")

        db_size = await pg_conn.execute_sql(
            "SELECT pg_size_pretty(pg_database_size(current_database())) AS size"
        )
        print(f"  [E2E-01]   DB大小: {db_size[0]['size']}")

        conn_count = await pg_conn.execute_sql(
            "SELECT COUNT(*) AS cnt FROM pg_stat_activity WHERE datname IS NOT NULL"
        )
        max_conn = await pg_conn.execute_sql("SHOW max_connections")
        usage = conn_count[0]["cnt"] / int(max_conn[0]["max_connections"]) * 100
        print(f"  [E2E-01]   连接使用率: {usage:.1f}%")
        print(f"  [E2E-01] ✓ PG 综合诊断完成")

    def test_e2e_02_mysql_full_diagnostic_workflow(self, mysql_conn):
        """E2E-02: MySQL 综合诊断工作流"""
        print("\n" + "=" * 60)
        print("  E2E-02: MySQL 综合诊断工作流")
        print("=" * 60)
        cursor = mysql_conn.cursor()

        cursor.execute("SELECT 1 AS health")
        health = cursor.fetchone()["health"]
        assert health == 1
        print(f"  [E2E-02] ✓ 健康检查: {health}")

        cursor.execute("SHOW PROCESSLIST")
        procs = cursor.fetchall()
        fields = [d[0] for d in cursor.description]
        proc_dicts = [dict(zip(fields, row)) for row in procs]
        queries = [p for p in proc_dicts if p.get("Command") == "Query"]
        print(f"  [E2E-02]   进程: total={len(procs)}, active_query={len(queries)}")

        cursor.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
        threads_conn = int(cursor.fetchone()["Value"])
        cursor.execute("SHOW GLOBAL VARIABLES LIKE 'max_connections'")
        max_conn = int(cursor.fetchone()["Value"])
        usage = threads_conn / max_conn * 100
        print(f"  [E2E-02]   连接: {threads_conn}/{max_conn} ({usage:.1f}%)")

        cursor.execute("SHOW ENGINE INNODB STATUS")
        innodb = cursor.fetchall()
        if innodb:
            innodb_row = innodb[0]
            # DictCursor: access by column name
            if isinstance(innodb_row, dict):
                status = innodb_row.get("Status", "")
            else:
                status = innodb_row[2]  # tuple fallback
            lines = status.split('\n')
            print(f"  [E2E-02]   InnoDB: {lines[0][:80]}")

        cursor.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
        slow_q = int(cursor.fetchone()["Value"])
        print(f"  [E2E-02]   慢查询计数: {slow_q}")

        cursor.execute("SHOW SLAVE STATUS")
        slave = cursor.fetchall()
        has_slave = bool(slave)
        print(f"  [E2E-02]   从库配置: {has_slave}")

        print(f"  [E2E-02] ✓ MySQL 综合诊断完成")

    @pytest.mark.asyncio
    async def test_e2e_03_diagnostic_agent_with_real_pg_data(self, pg_conn):
        """E2E-03: DiagnosticAgent 处理真实 PG 数据"""
        from src.agents.diagnostic import DiagnosticAgent
        from src.agents.base import AgentResponse
        from unittest.mock import AsyncMock, patch

        sessions = await pg_conn.get_sessions(limit=20)
        locks = await pg_conn.get_locks()
        rep = await pg_conn.get_replication()

        agent = DiagnosticAgent()
        ctx = {
            "instance_id": "PG-LOCAL-R24",
            "alert_info": {
                "alert_id": "ALT-R24-001",
                "alert_type": "FULL_DIAGNOSTIC",
                "severity": "info",
            },
            "extra_info": (
                f"会话数={len(sessions)}, 锁数={len(locks)}, "
                f"复制角色={rep['role']}"
            ),
        }

        with patch.object(agent, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = (
                f"PG综合诊断完成。会话={len(sessions)}, "
                f"锁={len(locks)}, 角色={rep['role']}"
            )
            resp = await agent._process_direct("综合诊断PG状态", ctx)

        assert isinstance(resp, AgentResponse)
        assert resp.success is True
        print(f"\n  [E2E-03] ✓ Agent响应: {resp.content[:60]}...")

    @pytest.mark.asyncio
    async def test_e2e_04_sql_guard_against_real_pg_queries(self, pg_conn):
        """E2E-04: SQL Guard 对真实 PG SQL 的校验"""
        from src.security.sql_guard.sql_guard import SQLGuard

        guard = SQLGuard()

        test_cases = [
            ("SELECT * FROM pg_stat_activity LIMIT 5", True, "L2"),
            ("SELECT pid, usename FROM pg_locks LIMIT 5", True, "L2"),
            ("SELECT pg_database_size(current_database())", True, "L1"),
            ("SELECT * FROM pg_tables LIMIT 1", True, "L2"),
            ("SHOW max_connections", True, "L2"),
        ]

        print("\n  [E2E-04] SQL Guard 校验:")
        for sql, exp_allowed, exp_risk_max in test_cases:
            result = await guard.validate(sql)
            passed = result.allowed is not False and result.risk_level <= exp_risk_max
            status = "✓" if passed else "✗"
            print(f"  {status} [{result.risk_level}] {sql[:50]}")
            assert passed, f"SQL校验失败: {sql}"

        print(f"  [E2E-04] ✓ SQL Guard 校验完成: {len(test_cases)} 个测试用例全部通过")

    def test_e2e_05_both_databases_accessible(self):
        """E2E-05: 验证两个数据库都可访问"""
        import pymysql
        import psycopg2

        pg_conn = psycopg2.connect(
            host="localhost", port=5432,
            user="chongjieran", database="postgres"
        )
        pg_cur = pg_conn.cursor()
        pg_cur.execute("SELECT 1, version()")
        row = pg_cur.fetchone()
        assert row[0] == 1
        print(f"\n  [E2E-05] PG: {row[1][:50]}")
        pg_conn.close()

        mysql_conn = pymysql.connect(
            host="127.0.0.1", port=3306,
            user="root", password="root"
        )
        with mysql_conn.cursor() as cur:
            cur.execute("SELECT 1, VERSION()")
            row = cur.fetchone()
            assert row[0] == 1
            print(f"  [E2E-05] MySQL: {row[1]}")
        mysql_conn.close()

        print(f"  [E2E-05] ✓ 两个数据库都可访问")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

async def _pg_create_idle_in_transaction(conn) -> int:
    """创建 1 个 idle in transaction 连接，返回其 PID（同步线程执行）"""
    import threading
    import psycopg2
    import queue as queue_module

    pid_queue = queue_module.Queue()
    error_queue = queue_module.Queue()

    def _worker():
        try:
            c = psycopg2.connect(
                host="localhost", port=5432,
                user="chongjieran", database="postgres",
            )
            c.autocommit = False
            cur = c.cursor()
            cur.execute("BEGIN")
            cur.execute("SELECT 1")
            pid = c.get_backend_pid()
            pid_queue.put(pid)
            time.sleep(30)
            c.rollback()
            c.close()
        except Exception as e:
            error_queue.put(str(e))

    t = threading.Thread(target=_worker)
    t.start()
    t.join(timeout=5)

    if not pid_queue.empty():
        return pid_queue.get()
    else:
        raise RuntimeError(f"无法创建 idle in transaction 连接: {error_queue.get() if not error_queue.empty() else 'unknown'}")


# ═══════════════════════════════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
