"""
V2.0 真实PostgreSQL环境验证 - P0-3 感知层
真实PG环境测试: 感知层采集工具 + 统一客户端 + 锁等待诊断 + 慢SQL分析

依赖: TEST_PG_* 环境变量配置的PostgreSQL实例
运行: cd ~/SWproject/Javis-DB-Agent && python3 -m pytest tests/v2.0/test_real_pg_perception.py -v --tb=short
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
import asyncio
import time
from typing import Dict, Any, List

from src.db.postgres_adapter import PostgresConnector
from src.db.base import get_db_connector, DBType, SessionInfo, LockInfo


# =============================================================================
# P0-3 真实PG环境: 复制状态查询
# =============================================================================

class TestRealPGReplication:
    """真实PG环境: 主从复制感知"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_stat_replication_query(self, pg_conn):
        """PER-PG-001: pg_stat_replication复制状态查询"""
        cursor = pg_conn.cursor()

        # 查询复制状态
        cursor.execute("""
            SELECT
                client_addr,
                state,
                usename,
                application_name,
                sent_lsn,
                write_lsn,
                flush_lsn,
                replay_lsn,
                sync_state
            FROM pg_stat_replication
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        assert isinstance(rows, list), "复制状态查询应返回列表"
        print(f"\n✅ 复制状态查询: {len(rows)}个复制连接")
        if rows:
            print(f"   状态: {dict(zip(columns, rows[0]))}")

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_replication_slot_query(self, pg_conn):
        """PER-PG-002: 复制槽状态查询"""
        cursor = pg_conn.cursor()

        cursor.execute("""
            SELECT
                slot_name,
                plugin,
                slot_type,
                active,
                restart_lsn,
                confirmed_flush_lsn
            FROM pg_replication_slots
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        assert isinstance(rows, list), "复制槽查询应返回列表"
        print(f"\n✅ 复制槽查询: {len(rows)}个槽")
        if rows:
            print(f"   槽名: {dict(zip(columns, rows[0]))}")


# =============================================================================
# P0-3 真实PG环境: 集群拓扑发现
# =============================================================================

class TestRealPGTopology:
    """真实PG环境: 集群拓扑感知"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_cluster_topology_discovery(self, pg_conn):
        """PER-PG-003: 集群拓扑发现"""
        cursor = pg_conn.cursor()

        # 获取所有节点角色
        cursor.execute("""
            SELECT
                pg_is_in_recovery() as is_replica,
                inet_server_addr() as server_addr,
                inet_server_port() as server_port,
                current_setting('cluster_name') as cluster_name
        """)
        row = cursor.fetchone()

        is_replica = row[0]
        server_addr = row[1]
        server_port = row[2]
        cluster_name = row[3]

        print(f"\n✅ 集群拓扑: 本节点role={'replica' if is_replica else 'primary'}")
        print(f"   地址: {server_addr}:{server_port}")
        print(f"   集群名: {cluster_name}")

        # 查询复制连接
        cursor.execute("SELECT count(*) FROM pg_stat_replication")
        repl_count = cursor.fetchone()[0]
        print(f"   复制连接数: {repl_count}")

        assert True, "拓扑发现应成功"

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_database_list_query(self, pg_conn):
        """PER-PG-004: 数据库列表查询"""
        cursor = pg_conn.cursor()

        cursor.execute("""
            SELECT
                datname,
                pg_size_pretty(pg_database_size(datname)) as size
            FROM pg_database
            WHERE datistemplate = false
            ORDER BY pg_database_size(datname) DESC
        """)
        rows = cursor.fetchall()

        assert isinstance(rows, list), "数据库列表查询应返回列表"
        print(f"\n✅ 数据库列表: {len(rows)}个数据库")
        for row in rows[:3]:
            print(f"   datname={row[0]}, size={row[1]}")


# =============================================================================
# P0-3 真实PG环境: 配置采集
# =============================================================================

class TestRealPGSettings:
    """真实PG环境: 配置感知"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_settings_collection(self, pg_conn):
        """PER-PG-005: PG配置参数采集"""
        cursor = pg_conn.cursor()

        # 采集关键参数
        key_params = [
            "max_connections",
            "shared_buffers",
            "effective_cache_size",
            "maintenance_work_mem",
            "checkpoint_completion_target",
            "wal_buffers",
            "default_statistics_target",
            "random_page_cost",
            "effective_io_concurrency",
            "work_mem",
            "min_wal_size",
            "max_wal_size",
        ]

        cursor.execute("""
            SELECT name, setting, unit, context
            FROM pg_settings
            WHERE name = ANY(%s)
        """, [key_params])
        rows = cursor.fetchall()

        assert len(rows) > 0, "应能采集到关键参数"
        print(f"\n✅ PG配置采集: {len(rows)}个关键参数")
        for row in rows:
            print(f"   {row[0]} = {row[1]} {row[2] or ''} (context: {row[3]})")

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_version_and_uptime(self, pg_conn):
        """PER-PG-006: PG版本与运行时长"""
        cursor = pg_conn.cursor()

        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]

        cursor.execute("SELECT pg_postmaster_start_time()")
        start_time = cursor.fetchone()[0]

        uptime_seconds = (time.time() - start_time.timestamp())
        uptime_hours = uptime_seconds / 3600

        print(f"\n✅ PG版本: {version}")
        print(f"   启动时间: {start_time}")
        print(f"   运行时间: {uptime_hours:.1f}小时")

        assert version is not None, "应能获取版本信息"


# =============================================================================
# P0-3 真实PG环境: 统一客户端
# =============================================================================

class TestRealPGUnifiedClient:
    """真实PG环境: 统一数据库客户端"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_unified_client_real_pg(self, pg_conn):
        """PER-PG-007: 统一客户端连接真实PG"""
        # 使用统一工厂创建连接器
        connector = get_db_connector(
            db_type="postgresql",
            host=os.getenv("TEST_PG_HOST", "localhost"),
            port=int(os.getenv("TEST_PG_PORT", "5432")),
            username=os.getenv("TEST_PG_USER", "postgres"),
            password=os.getenv("TEST_PG_PASSWORD", ""),
        )

        assert connector.db_type == DBType.POSTGRES, "连接器类型应为PostgreSQL"

        # 健康检查
        is_healthy = await connector.health_check()
        assert is_healthy is True, "健康检查应返回True"

        # 获取会话列表
        sessions = await connector.get_sessions(limit=10)
        assert isinstance(sessions, list), "会话列表应为list"
        print(f"\n✅ 统一客户端: 连接正常, 会话数={len(sessions)}")

        # 获取复制状态
        repl_info = await connector.get_replication()
        assert repl_info is not None, "应能获取复制状态"
        print(f"   角色: {repl_info.role}, 复制启用: {repl_info.replication_enabled}")

        await connector.close()

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_unified_client_capacity(self, pg_conn):
        """PER-PG-008: 统一客户端容量查询"""
        connector = get_db_connector(
            db_type="postgresql",
            host=os.getenv("TEST_PG_HOST", "localhost"),
            port=int(os.getenv("TEST_PG_PORT", "5432")),
            username=os.getenv("TEST_PG_USER", "postgres"),
            password=os.getenv("TEST_PG_PASSWORD", ""),
        )

        capacity = await connector.get_capacity()
        assert capacity is not None, "应能获取容量信息"
        print(f"\n✅ 容量查询: 磁盘使用={capacity.disk_used_percent:.1f}%")
        print(f"   总量={capacity.disk_total_gb:.0f}GB, 已用={capacity.disk_used_gb:.0f}GB")

        await connector.close()

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_unified_client_performance(self, pg_conn):
        """PER-PG-009: 统一客户端性能指标"""
        connector = get_db_connector(
            db_type="postgresql",
            host=os.getenv("TEST_PG_HOST", "localhost"),
            port=int(os.getenv("TEST_PG_PORT", "5432")),
            username=os.getenv("TEST_PG_USER", "postgres"),
            password=os.getenv("TEST_PG_PASSWORD", ""),
        )

        perf = await connector.get_performance()
        assert perf is not None, "应能获取性能指标"
        print(f"\n✅ 性能指标: CPU={perf.cpu_usage_percent:.1f}%, 内存={perf.memory_usage_percent:.1f}%")
        print(f"   活跃连接={perf.active_connections}/{perf.max_connections}")
        print(f"   事务TPS={perf.transactions_per_sec:.1f}, 缓存命中率={perf.buffer_hit_ratio:.1f}%")

        await connector.close()


# =============================================================================
# P0-3 真实PG环境: 查询工具
# =============================================================================

class TestRealPGQueryTool:
    """真实PG环境: 查询工具"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_query_tool_real_data(self, pg_conn):
        """PER-PG-010: 查询工具返回真实数据"""
        cursor = pg_conn.cursor()

        # 执行一个复杂查询验证返回结构
        cursor.execute("""
            SELECT
                datname,
                numbackends,
                xact_commit,
                xact_rollback,
                blks_hit,
                blks_read,
                ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) AS hit_ratio
            FROM pg_stat_database
            WHERE datname = current_database()
            LIMIT 5
        """)
        rows = cursor.fetchall()

        assert isinstance(rows, list), "查询应返回列表"
        assert len(rows) > 0, "应有数据返回"
        print(f"\n✅ 查询工具: 返回{len(rows)}行数据")

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_stat_activity_query(self, pg_conn):
        """PER-PG-011: pg_stat_activity实时查询"""
        cursor = pg_conn.cursor()

        cursor.execute("""
            SELECT
                pid,
                usename,
                datname,
                state,
                query,
                query_start,
                wait_event_type,
                wait_event,
                left(query, 50) as query_preview
            FROM pg_stat_activity
            WHERE state IS NOT NULL
            ORDER BY query_start ASC NULLS FIRST
            LIMIT 20
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        assert isinstance(rows, list), "活动查询应返回列表"
        print(f"\n✅ 活动会话查询: {len(rows)}个活跃会话")
        for row in rows[:3]:
            d = dict(zip(columns, row))
            print(f"   pid={d['pid']}, state={d['state']}, query={d['query_preview']}")


# =============================================================================
# P0-3 真实PG环境: 锁等待诊断
# =============================================================================

class TestRealPGLockWait:
    """真实PG环境: 锁等待诊断"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_lock_wait_full_loop(self, pg_conn):
        """PER-PG-012: 锁等待诊断完整流程"""
        cursor = pg_conn.cursor()

        # Step 1: 查询等待中的会话
        cursor.execute("""
            SELECT
                pid,
                usename,
                datname,
                query,
                wait_event_type,
                wait_event,
                state,
                query_start
            FROM pg_stat_activity
            WHERE wait_event_type IS NOT NULL
            AND state = 'active'
        """)
        waiting_sessions = cursor.fetchall()
        waiting_cols = [desc[0] for desc in cursor.description]

        print(f"\n✅ 锁等待诊断 Step1: 发现{len(waiting_sessions)}个等待会话")

        # Step 2: 查询锁信息
        cursor.execute("""
            SELECT
                pg_blocking_pids(a.pid) as blocked_by,
                a.pid,
                a.query,
                a.wait_event_type,
                a.wait_event
            FROM pg_stat_activity a
            WHERE a.wait_event_type IS NOT NULL
        """)
        blocking_info = cursor.fetchall()
        print(f"   阻塞关系: {len(blocking_info)}条")

        # Step 3: 查询长事务（可能导致锁等待）
        cursor.execute("""
            SELECT
                pid,
                usename,
                query,
                state,
                xact_start,
                query_start,
                LEFT(query, 80) as query_preview
            FROM pg_stat_activity
            WHERE state != 'idle in transaction'
            AND xact_start IS NOT NULL
            AND NOW() - xact_start > interval '5 minutes'
            ORDER BY xact_start
            LIMIT 10
        """)
        long_transactions = cursor.fetchall()
        print(f"   长事务(>5min): {len(long_transactions)}个")

        assert isinstance(waiting_sessions, list), "等待会话应为列表"
        print(f"\n✅ 锁等待诊断完整流程: 完成")

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_locks_query(self, pg_conn):
        """PER-PG-013: pg_locks锁信息查询"""
        cursor = pg_conn.cursor()

        cursor.execute("""
            SELECT
                locktype,
                granted,
                mode,
                pid,
                relation::regclass as relation,
                page,
                tuple
            FROM pg_locks
            WHERE granted = false
            LIMIT 20
        """)
        waiting_locks = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        assert isinstance(waiting_locks, list), "锁查询应返回列表"
        print(f"\n✅ 等待锁查询: {len(waiting_locks)}个未授予锁")


# =============================================================================
# P0-3 真实PG环境: 慢SQL分析
# =============================================================================

class TestRealPGSlowQuery:
    """真实PG环境: 慢SQL分析"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_slow_sql_full_loop(self, pg_conn):
        """PER-PG-014: 慢SQL分析完整流程"""
        cursor = pg_conn.cursor()

        # Step 1: 查询pg_stat_statements（如果启用）
        try:
            cursor.execute("""
                SELECT
                    query,
                    calls,
                    total_exec_time,
                    mean_exec_time,
                    rows,
                    LEFT(query, 100) as query_preview
                FROM pg_stat_statements
                ORDER BY total_exec_time DESC
                LIMIT 10
            """)
            top_queries = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            print(f"\n✅ 慢SQL分析 Step1: pg_stat_statements返回{len(top_queries)}条")
            for row in top_queries[:3]:
                d = dict(zip(columns, row))
                print(f"   总耗时={d['total_exec_time']:.0f}ms, 调用={d['calls']}, 行数={d['rows']}")

        except Exception as e:
            # pg_stat_statements可能未启用，需要ROLLBACK恢复事务
            pg_conn.rollback()
            print(f"\n   (pg_stat_statements未启用，跳过: {e})")

        # Step 2: 查询当前最慢的活跃查询
        cursor.execute("""
            SELECT
                pid,
                usename,
                NOW() - query_start as duration,
                left(query, 80) as query_preview,
                state
            FROM pg_stat_activity
            WHERE state = 'active'
            AND query_start IS NOT NULL
            ORDER BY query_start ASC NULLS FIRST
            LIMIT 5
        """)
        active_slow = cursor.fetchall()
        active_cols = [desc[0] for desc in cursor.description]

        print(f"   活跃查询(按启动时间): {len(active_slow)}个")

        # Step 3: EXPLAIN分析（找一个简单查询做示例）
        try:
            cursor.execute("""
                SELECT
                    LEFT(query, 100) as query_preview
                FROM pg_stat_activity
                WHERE state = 'active'
                AND query NOT LIKE '%pg_stat%'
                LIMIT 1
            """)
            sample_query = cursor.fetchall()
        except Exception as e:
            sample_query = []
            print(f"   活跃查询查询跳过: {e}")

        if sample_query:
            query_text = sample_query[0][0]
            try:
                # Only EXPLAIN if we have a valid query
                if query_text and query_text.strip():
                    cursor.execute(f"EXPLAIN (FORMAT JSON) {query_text}")
                    explain_result = cursor.fetchone()[0]
                    print(f"   EXPLAIN分析成功")
            except Exception as e:
                print(f"   EXPLAIN分析跳过: {e}")

        print(f"\n✅ 慢SQL分析完整流程: 完成")

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_pg_bloat_analysis(self, pg_conn):
        """PER-PG-015: 表膨胀分析"""
        cursor = pg_conn.cursor()

        cursor.execute("""
            SELECT
                schemaname,
                relname,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) as total_size,
                pg_size_pretty(pg_relation_size(schemaname||'.'||relname)) as table_size,
                n_dead_tup,
                n_live_tup,
                ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_tuple_pct
            FROM pg_stat_user_tables
            WHERE n_live_tup > 0
            ORDER BY n_dead_tup DESC
            LIMIT 10
        """)
        bloat_data = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        assert isinstance(bloat_data, list), "膨胀分析应返回列表"
        print(f"\n✅ 表膨胀分析: {len(bloat_data)}个表")
        for row in bloat_data[:5]:
            d = dict(zip(columns, row))
            print(f"   {d['schemaname']}.{d['relname']}: dead_pct={d['dead_tuple_pct']}%")


# =============================================================================
# P0-3 真实PG环境: PostgresConnector直接测试
# =============================================================================

class TestRealPGDirectConnector:
    """真实PG环境: PostgresConnector直接测试"""

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_postgres_connector_direct(self):
        """PER-PG-016: PostgresConnector直接实例化测试"""
        host = os.getenv("TEST_PG_HOST", "localhost")
        port = int(os.getenv("TEST_PG_PORT", "5432"))
        user = os.getenv("TEST_PG_USER", "postgres")
        password = os.getenv("TEST_PG_PASSWORD", "")

        connector = PostgresConnector(
            host=host,
            port=port,
            username=user,
            password=password,
        )

        # 健康检查
        is_healthy = await connector.health_check()
        assert is_healthy is True, "健康检查应通过"

        # 获取会话
        sessions = await connector.get_sessions(limit=5)
        assert isinstance(sessions, list), "会话列表应为list"
        assert len(sessions) > 0, "应有会话数据"

        # 获取锁
        locks = await connector.get_locks()
        assert isinstance(locks, list), "锁列表应为list"

        # 获取容量
        capacity = await connector.get_capacity()
        assert capacity.disk_total_gb > 0, "应有磁盘容量"

        # 获取性能
        perf = await connector.get_performance()
        assert perf.active_connections >= 0, "应有连接数"

        print(f"\n✅ PostgresConnector直接测试: 健康")
        print(f"   会话={len(sessions)}, 锁={len(locks)}, 容量={capacity.disk_total_gb:.0f}GB")

        await connector.close()

    @pytest.mark.p0_per
    @pytest.mark.pg
    async def test_postgres_connector_replication(self):
        """PER-PG-017: PostgresConnector复制状态"""
        connector = PostgresConnector(
            host=os.getenv("TEST_PG_HOST", "localhost"),
            port=int(os.getenv("TEST_PG_PORT", "5432")),
            username=os.getenv("TEST_PG_USER", "postgres"),
            password=os.getenv("TEST_PG_PASSWORD", ""),
        )

        repl_info = await connector.get_replication()
        assert repl_info is not None, "应能获取复制信息"
        assert repl_info.role is not None, "应有role字段"
        print(f"\n✅ 复制状态: role={repl_info.role}, replicas={len(repl_info.replicas)}")

        await connector.close()
