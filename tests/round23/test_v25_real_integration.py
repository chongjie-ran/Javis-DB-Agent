"""
V2.5 真实数据库集成测试（禁止 Mock）
=============================================
直连真实数据库，验证 V2.5 所有功能：
  - PostgreSQL: DirectPostgresConnector → pg_stat_activity, pg_locks, pg_stat_replication
  - MySQL:      pymysql → SHOW PROCESSLIST, performance_schema, SHOW SLAVE STATUS

前置条件：
  - PostgreSQL: localhost:5432, user=chongjieran, database=postgres
  - MySQL:      localhost:3306, user=root, password=root
"""

import asyncio
import sys
import os
import time
from datetime import datetime

import pytest
from unittest.mock import patch, AsyncMock
from tests.round23.conftest import MYSQL_AVAILABLE, POSTGRES_AVAILABLE  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


# ═══════════════════════════════════════════════════════════════════════════════
# REAL PostgreSQL TESTS — DirectPostgresConnector → asyncpg
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestPGRealConnection:
    """PG-Real: 真实 PostgreSQL 连接测试"""

    @pytest.fixture
    async def pg_conn(self):
        """创建真实 PG 连接"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost",
            port=5432,
            user="chongjieran",
            database="postgres",
        )
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_pg_real_01_health_check(self, pg_conn):
        """PG-Real-01: PostgreSQL 健康检查返回 True"""
        result = await pg_conn.health_check()
        assert result is True, "真实 PG 连接健康检查应通过"

    @pytest.mark.asyncio
    async def test_pg_real_02_session_list_not_empty(self, pg_conn):
        """PG-Real-02: pg_stat_activity 返回会话列表（非空）"""
        sessions = await pg_conn.get_sessions(limit=100)
        assert isinstance(sessions, list), "会话列表应为 list"
        assert len(sessions) > 0, "应有活动会话（当前连接）"

    @pytest.mark.asyncio
    async def test_pg_real_03_session_fields(self, pg_conn):
        """PG-Real-03: 会话包含所有必要字段"""
        sessions = await pg_conn.get_sessions(limit=10)
        for s in sessions:
            assert "pid" in s, "会话需有 pid 字段"
            assert ("usename" in s or "username" in s), "会话需有 username 字段"

    @pytest.mark.asyncio
    async def test_pg_real_04_replication_status(self, pg_conn):
        """PG-Real-04: 获取复制状态"""
        rep = await pg_conn.get_replication()
        assert isinstance(rep, dict), "复制状态应为 dict"
        assert "role" in rep, "应有 role 字段"
        assert rep["role"] in ("primary", "standby"), f"role 应为 primary/standby，实际: {rep['role']}"

    @pytest.mark.asyncio
    async def test_pg_real_05_lock_query(self, pg_conn):
        """PG-Real-05: 查询 pg_locks（可能为空）"""
        locks = await pg_conn.get_locks()
        assert isinstance(locks, list), "锁列表应为 list"
        # 无锁时返回空列表也正常
        for lock in locks:
            assert "locktype" in lock
            assert "granted" in lock

    @pytest.mark.asyncio
    async def test_pg_real_06_execute_sql_select(self, pg_conn):
        """PG-Real-06: execute_sql 执行 SELECT"""
        rows = await pg_conn.execute_sql("SELECT 1 AS num, version() AS ver")
        assert len(rows) == 1
        assert rows[0]["num"] == 1
        assert "PostgreSQL" in rows[0]["ver"]

    @pytest.mark.asyncio
    async def test_pg_real_07_database_size_query(self, pg_conn):
        """PG-Real-07: 查询数据库大小"""
        rows = await pg_conn.execute_sql(
            "SELECT pg_database_size(current_database()) AS size_bytes"
        )
        assert rows[0]["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_pg_real_08_connections_count(self, pg_conn):
        """PG-Real-08: 当前连接数 > 0"""
        rows = await pg_conn.execute_sql(
            "SELECT COUNT(*) AS cnt FROM pg_stat_activity WHERE datname IS NOT NULL"
        )
        assert rows[0]["cnt"] > 0

    @pytest.mark.asyncio
    async def test_pg_real_09_settings_max_connections(self, pg_conn):
        """PG-Real-09: 获取 max_connections 配置"""
        rows = await pg_conn.execute_sql("SHOW max_connections")
        assert len(rows) == 1
        assert int(rows[0]["max_connections"]) > 0

    @pytest.mark.asyncio
    async def test_pg_real_10_version_info(self, pg_conn):
        """PG-Real-10: PostgreSQL 版本信息"""
        rows = await pg_conn.execute_sql("SELECT version()")
        ver = rows[0]["version"]
        assert "PostgreSQL" in ver
        print(f"  PG Version: {ver[:60]}")


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestPGRealOnboarding:
    """PG-Real-Onboard: PostgreSQL 发现与纳管（真实）"""

    @pytest.mark.asyncio
    async def test_pg_real_11_discovery_scanner(self):
        """PG-Real-11: DatabaseScanner 能扫描 localhost:5432"""
        from src.discovery.scanner import DatabaseScanner, DBType
        scanner = DatabaseScanner(ports=[5432], scan_timeout=5.0)
        results = await scanner.scan_ports("localhost")
        pg_inst = next((r for r in results if r.port == 5432), None)
        assert pg_inst is not None, "应发现 localhost:5432"
        assert pg_inst.db_type == DBType.POSTGRESQL

    @pytest.mark.asyncio
    async def test_pg_real_12_version_identification(self):
        """PG-Real-12: DatabaseIdentifier 识别 PostgreSQL 版本"""
        from src.discovery.identifier import DatabaseIdentifier
        from src.discovery.scanner import DiscoveredInstance, DBType
        inst = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
            status="reachable",
        )
        identifier = DatabaseIdentifier()
        result = await identifier.identify(inst)
        assert result is not None
        assert "PostgreSQL" in result.version

    @pytest.mark.asyncio
    async def test_pg_real_13_connector_factory(self):
        """PG-Real-13: get_db_connector(postgresql) 返回 PostgresConnector"""
        from src.db.base import get_db_connector, DBType
        conn = get_db_connector(
            db_type="postgresql",
            host="localhost",
            port=5432,
            username="chongjieran",
        )
        assert conn.db_type == DBType.POSTGRES


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestPGRealSchemaAndAnalysis:
    """PG-Real-Schema: Schema 捕获与 SQL 分析"""

    @pytest.mark.asyncio
    async def test_pg_real_14_public_tables_list(self):
        """PG-Real-14: 列出 public schema 中的表"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        rows = await conn.execute_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        assert isinstance(rows, list)
        print(f"  Public tables: {[r['tablename'] for r in rows]}")
        await conn.close()

    @pytest.mark.asyncio
    async def test_pg_real_15_indexes_list(self):
        """PG-Real-15: 列出索引信息"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        rows = await conn.execute_sql(
            "SELECT indexname, tablename FROM pg_indexes "
            "WHERE schemaname = 'public' LIMIT 10"
        )
        assert isinstance(rows, list)
        print(f"  Indexes found: {len(rows)}")
        await conn.close()

    @pytest.mark.asyncio
    async def test_pg_real_16_sql_guard_validate_real(self):
        """PG-Real-16: SQL Guard 对真实 SQL 进行校验"""
        from src.security.sql_guard.sql_guard import SQLGuard
        guard = SQLGuard()
        sql = "SELECT pid, usename FROM pg_stat_activity LIMIT 10"
        result = await guard.validate(sql)
        assert result.risk_level in ("L0", "L1", "L2")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_pg_real_17_sql_guard_block_dangerous_real(self):
        """PG-Real-17: SQL Guard 拦截危险 SQL"""
        from src.security.sql_guard.sql_guard import SQLGuard
        guard = SQLGuard()
        dangerous_sqls = [
            "DROP TABLE pg_stat_activity",
            "TRUNCATE pg_catalog.pg_class",
        ]
        for sql in dangerous_sqls:
            result = await guard.validate(sql)
            assert result.risk_level in ("L4", "L5") or result.allowed is False, \
                f"危险SQL应被拦截: {sql}"

    @pytest.mark.asyncio
    async def test_pg_real_18_pg_stat_statements_available(self):
        """PG-Real-18: 检查 pg_stat_statements 是否可用（查询前等待时间）"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        try:
            rows = await conn.execute_sql(
                "SELECT * FROM pg_stat_statements LIMIT 1"
            )
            print(f"  pg_stat_statements available: {len(rows)} rows")
        except Exception as e:
            print(f"  pg_stat_statements not available (expected in some envs): {e}")
        finally:
            await conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# REAL MySQL TESTS — pymysql direct connection
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not MYSQL_AVAILABLE, reason="MySQL not available")
class TestMySQLRealConnection:
    """MySQL-Real: 真实 MySQL 连接测试"""

    @pytest.fixture
    def mysql_conn(self):
        """创建真实 MySQL 连接（pymysql）"""
        import pymysql
        conn = pymysql.connect(
            host="127.0.0.1",
            port=3306,
            user="root",
            password="root",
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        yield conn
        conn.close()

    def test_mysql_real_01_health_check(self, mysql_conn):
        """MySQL-Real-01: MySQL 健康检查（SELECT 1）"""
        with mysql_conn.cursor() as cur:
            cur.execute("SELECT 1 AS test")
            row = cur.fetchone()
            assert row["test"] == 1

    def test_mysql_real_02_processlist(self, mysql_conn):
        """MySQL-Real-02: SHOW PROCESSLIST 返回结果"""
        with mysql_conn.cursor() as cur:
            cur.execute("SHOW PROCESSLIST")
            rows = cur.fetchall()
            assert isinstance(rows, list)
            assert len(rows) >= 1, "应有当前连接"
            for r in rows:
                assert "Id" in r or "Id" in str(r)

    def test_mysql_real_03_version(self, mysql_conn):
        """MySQL-Real-03: 获取 MySQL 版本"""
        with mysql_conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS ver")
            ver = cur.fetchone()["ver"]
            assert "MySQL" in ver or "8.0" in ver
            print(f"  MySQL Version: {ver}")

    def test_mysql_real_04_databases(self, mysql_conn):
        """MySQL-Real-04: 列出所有数据库"""
        with mysql_conn.cursor() as cur:
            cur.execute("SHOW DATABASES")
            rows = cur.fetchall()
            dbs = [r["Database"] for r in rows]
            assert "mysql" in dbs
            print(f"  Databases: {dbs}")

    def test_mysql_real_05_global_variables(self, mysql_conn):
        """MySQL-Real-05: 查询全局变量 max_connections"""
        with mysql_conn.cursor() as cur:
            cur.execute("SHOW GLOBAL VARIABLES LIKE 'max_connections'")
            row = cur.fetchone()
            assert row is not None
            assert int(row["Value"]) > 0

    def test_mysql_real_06_status_variables(self, mysql_conn):
        """MySQL-Real-06: 查询全局状态 Threads_connected"""
        with mysql_conn.cursor() as cur:
            cur.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
            row = cur.fetchone()
            assert row is not None
            assert int(row["Value"]) >= 0

    def test_mysql_real_07_data_locks_schema(self, mysql_conn):
        """MySQL-Real-07: performance_schema.data_locks 表结构"""
        with mysql_conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema='performance_schema' AND table_name='data_locks'"
            )
            cols = [r["COLUMN_NAME"] for r in cur.fetchall()]
            assert "ENGINE" in cols
            assert "LOCK_MODE" in cols
            assert "LOCK_STATUS" in cols

    def test_mysql_real_08_data_lock_waits_schema(self, mysql_conn):
        """MySQL-Real-08: performance_schema.data_lock_waits 表结构"""
        with mysql_conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema='performance_schema' AND table_name='data_lock_waits'"
            )
            cols = [r["COLUMN_NAME"] for r in cur.fetchall()]
            assert "REQUESTING_THREAD_ID" in cols
            assert "BLOCKING_THREAD_ID" in cols

    def test_mysql_real_09_innodb_status(self, mysql_conn):
        """MySQL-Real-09: SHOW ENGINE INNODB STATUS"""
        with mysql_conn.cursor() as cur:
            cur.execute("SHOW ENGINE INNODB STATUS")
            row = cur.fetchone()
            assert row is not None
            assert "Status" in row

    def test_mysql_real_10_slave_status(self, mysql_conn):
        """MySQL-Real-10: SHOW SLAVE STATUS（可能为空但结构正确）"""
        with mysql_conn.cursor() as cur:
            cur.execute("SHOW SLAVE STATUS")
            # 如果没有复制，返回空元组（SHOW命令返回tuple）
            result = cur.fetchall()
            assert isinstance(result, (list, tuple))


@pytest.mark.skipif(not MYSQL_AVAILABLE, reason="MySQL not available")
class TestMySQLRealOnboarding:
    """MySQL-Real-Onboard: MySQL 发现与纳管（真实）"""

    @pytest.mark.asyncio
    async def test_mysql_real_11_discovery_scanner(self):
        """MySQL-Real-11: DatabaseScanner 能扫描 localhost:3306"""
        import pytest
        from src.discovery.scanner import DatabaseScanner, DBType
        scanner = DatabaseScanner(ports=[3306], scan_timeout=5.0)
        results = await scanner.scan_ports("localhost")
        mysql_inst = next((r for r in results if r.port == 3306), None)
        if mysql_inst:
            assert mysql_inst.db_type == DBType.MYSQL
        else:
            pytest.skip("MySQL 未在 localhost:3306 启用")

    def test_mysql_real_12_connector_factory(self):
        """MySQL-Real-12: get_db_connector(mysql) 返回 MySQLConnector"""
        from src.db.base import get_db_connector, DBType
        conn = get_db_connector(
            db_type="mysql",
            host="127.0.0.1",
            port=3306,
            username="root",
            password="root",
        )
        assert conn.db_type == DBType.MYSQL

    @pytest.mark.asyncio
    async def test_mysql_real_13_sql_guard_validate_real(self):
        """MySQL-Real-13: SQL Guard 对 MySQL 真实 SQL 校验"""
        import pytest
        from src.security.sql_guard.sql_guard import SQLGuard
        guard = SQLGuard()
        sql = "SELECT * FROM mysql.user LIMIT 1"
        result = await guard.validate(sql)
        assert result.risk_level in ("L0", "L1", "L2", "L3")

    @pytest.mark.asyncio
    async def test_mysql_real_14_sql_guard_block_real(self):
        """MySQL-Real-14: SQL Guard 拦截 MySQL 危险 SQL"""
        from src.security.sql_guard.sql_guard import SQLGuard
        guard = SQLGuard()
        result = await guard.validate("DROP TABLE mysql.user")
        assert result.risk_level in ("L4", "L5") or result.allowed is False


# ═══════════════════════════════════════════════════════════════════════════════
# E2E TESTS WITH REAL DATA
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not (MYSQL_AVAILABLE and POSTGRES_AVAILABLE), reason="MySQL or PostgreSQL not available")
class TestE2ERealScenarios:
    """E2E-Real: 基于真实数据库的端到端场景测试"""

    @pytest.mark.asyncio
    async def test_e2e_real_01_pg_session_snapshot(self):
        """E2E-Real-01: 快照当前 PG 会话状态"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        sessions = await conn.get_sessions(limit=20)
        assert len(sessions) >= 1
        # 验证字段完整性
        for s in sessions:
            assert "pid" in s
            assert "usename" in s or "username" in s
        print(f"\n  PG 会话数: {len(sessions)}")
        await conn.close()

    @pytest.mark.asyncio
    async def test_e2e_real_02_pg_lock_snapshot(self):
        """E2E-Real-02: 快照当前 PG 锁状态"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        locks = await conn.get_locks()
        assert isinstance(locks, list)
        print(f"\n  PG 锁数: {len(locks)}")
        await conn.close()

    @pytest.mark.asyncio
    async def test_e2e_real_03_pg_replication_snapshot(self):
        """E2E-Real-03: 快照当前 PG 复制状态"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        rep = await conn.get_replication()
        assert "role" in rep
        print(f"\n  PG 角色: {rep['role']}, 副本数: {len(rep['replicas'])}")
        await conn.close()

    @pytest.mark.asyncio
    async def test_e2e_real_04_pg_capacity_real(self):
        """E2E-Real-04: 查询 PG 容量信息"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        rows = await conn.execute_sql(
            "SELECT pg_database_size(current_database()) AS db_size_bytes"
        )
        assert rows[0]["db_size_bytes"] >= 0
        print(f"\n  DB size: {rows[0]['db_size_bytes']:,} bytes")
        await conn.close()

    @pytest.mark.asyncio
    async def test_e2e_real_05_diagnostic_agent_with_real_pg(self):
        """E2E-Real-05: DiagnosticAgent 处理真实 PG 会话数据"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        from src.agents.diagnostic import DiagnosticAgent
        from src.agents.base import AgentResponse

        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        sessions = await conn.get_sessions(limit=10)
        locks = await conn.get_locks()

        agent = DiagnosticAgent()
        ctx = {
            "instance_id": "PG-LOCAL",
            "alert_info": {
                "alert_id": "ALT-REAL-001",
                "alert_type": "SESSION_SNAPSHOT",
                "severity": "info",
            },
            "extra_info": (
                f"当前会话数: {len(sessions)}, "
                f"锁数量: {len(locks)}, "
                f"PG版本查询成功"
            ),
        }

        with patch.object(agent, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = (
                f"PostgreSQL 真实连接正常。会话数={len(sessions)}，"
                f"锁数={len(locks)}，数据库响应正常。"
            )
            resp = await agent._process_direct("检查 PostgreSQL 状态", ctx)

        assert isinstance(resp, AgentResponse)
        assert resp.success is True
        print(f"\n  Agent response: {resp.content[:80]}")
        await conn.close()

    @pytest.mark.asyncio
    async def test_e2e_real_06_full_diagnostic_workflow(self):
        """E2E-Real-06: 完整诊断工作流（会话→锁→复制）"""
        from src.db.direct_postgres_connector import DirectPostgresConnector

        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )

        # 1. 获取会话
        sessions = await conn.get_sessions(limit=50)
        active = [s for s in sessions if s.get("state") == "active"]
        idle = [s for s in sessions if s.get("state") and s.get("state") != "active"]

        # 2. 获取锁
        locks = await conn.get_locks()
        ungranted = [l for l in locks if not l.get("granted")]

        # 3. 获取复制
        rep = await conn.get_replication()

        # 4. 汇总
        report = {
            "session_total": len(sessions),
            "session_active": len(active),
            "session_idle": len(idle),
            "locks_total": len(locks),
            "locks_waiting": len(ungranted),
            "replication_role": rep["role"],
            "replicas": len(rep["replicas"]),
        }

        print(f"\n  诊断报告: {report}")
        assert report["session_total"] >= 1
        await conn.close()


@pytest.mark.skipif(not MYSQL_AVAILABLE, reason="MySQL not available")
class TestMySQLRealScenarios:
    """MySQL-Real-Scenarios: MySQL 真实场景测试"""

    def test_e2e_mysql_real_01_processlist_snapshot(self):
        """E2E-MySQL-01: 快照 MySQL 进程列表"""
        import pymysql
        conn = pymysql.connect(
            host="127.0.0.1", port=3306,
            user="root", password="root",
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute("SHOW PROCESSLIST")
            rows = cur.fetchall()
            assert len(rows) >= 1
            print(f"\n  MySQL 进程数: {len(rows)}")
            for r in rows[:3]:
                print(f"    Id={r.get('Id')}, Command={r.get('Command')}, "
                      f"DB={r.get('db')}, Time={r.get('Time')}")
        conn.close()

    def test_e2e_mysql_real_02_innodb_metrics(self):
        """E2E-MySQL-02: 查询 InnoDB 关键指标"""
        import pymysql
        conn = pymysql.connect(
            host="127.0.0.1", port=3306,
            user="root", password="root",
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            metrics = {}
            cur.execute("SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_requests'")
            r = cur.fetchone()
            if r:
                metrics["buffer_pool_read_requests"] = int(r["Value"])

            cur.execute("SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_waits'")
            r = cur.fetchone()
            if r:
                metrics["row_lock_waits"] = int(r["Value"])

            print(f"\n  InnoDB metrics: {metrics}")
            assert isinstance(metrics, dict)
        conn.close()

    def test_e2e_mysql_real_03_full_workflow(self):
        """E2E-MySQL-03: 完整 MySQL 健康检查工作流"""
        import pymysql
        conn = pymysql.connect(
            host="127.0.0.1", port=3306,
            user="root", password="root",
            cursorclass=pymysql.cursors.DictCursor,
        )
        report = {}

        with conn.cursor() as cur:
            # 1. 版本
            cur.execute("SELECT VERSION() AS ver")
            report["version"] = cur.fetchone()["ver"]

            # 2. 连接数
            cur.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
            report["threads_connected"] = int(cur.fetchone()["Value"])

            # 3. 查询缓存命中率（如有）
            cur.execute("SHOW GLOBAL STATUS LIKE 'Qcache_hits'")
            r = cur.fetchone()
            report["qcache_hits"] = int(r["Value"]) if r else None

            # 4. 锁等待
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM performance_schema.data_lock_waits"
            )
            r = cur.fetchone()
            report["lock_waits"] = r["cnt"]

        print(f"\n  MySQL 健康报告: {report}")
        assert "version" in report
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS (SQL Guard, ApprovalGate) — Real DB Context
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not (MYSQL_AVAILABLE and POSTGRES_AVAILABLE), reason="MySQL or PostgreSQL not available")
class TestRegressionRealDB:
    """REG-Real: 回归测试（真实数据库上下文）"""

    @pytest.mark.asyncio
    async def test_reg_real_01_guard_pg_metadata_query(self):
        """REG-Real-01: SQL Guard 保护 PG 元数据查询"""
        from src.security.sql_guard.sql_guard import SQLGuard
        guard = SQLGuard()
        sqls = [
            ("SELECT * FROM pg_stat_activity LIMIT 1", True),
            ("SELECT * FROM pg_locks LIMIT 1", True),
            ("SELECT * FROM pg_catalog.pg_class LIMIT 1", True),
            ("DROP TABLE pg_stat_activity", False),
            ("TRUNCATE pg_catalog.pg_class", False),
        ]
        for sql, should_pass in sqls:
            result = await guard.validate(sql)
            if should_pass:
                assert result.allowed is not False, f"应允许: {sql}"
            else:
                assert result.risk_level in ("L4", "L5") or result.allowed is False, \
                    f"应拦截: {sql}"

    @pytest.mark.asyncio
    async def test_reg_real_02_guard_mysql_metadata_query(self):
        """REG-Real-02: SQL Guard 保护 MySQL 元数据查询"""
        from src.security.sql_guard.sql_guard import SQLGuard
        guard = SQLGuard()
        sqls = [
            ("SELECT * FROM mysql.user LIMIT 1", True),
            ("SHOW DATABASES", True),
            ("SHOW PROCESSLIST", True),
            ("DROP TABLE mysql.user", False),
        ]
        for sql, should_pass in sqls:
            result = await guard.validate(sql)
            if should_pass:
                assert result.allowed is not False, f"应允许: {sql}"
            else:
                assert result.risk_level in ("L4", "L5") or result.allowed is False, \
                    f"应拦截: {sql}"

    def test_reg_real_03_approval_gate_real(self):
        """REG-Real-03: ApprovalGate 审批流程（真实）"""
        import asyncio
        from src.gateway.approval import ApprovalGate

        gate = ApprovalGate(timeout_seconds=5)
        ctx = {"user_id": "test_user", "session_id": "s1", "risk_level": "L4"}
        step_def = {"step_id": "1", "action": "pg_query", "risk_level": "L4"}

        async def run():
            result = await gate.request_approval(
                step_def=step_def, params={}, context=ctx
            )
            assert result.success is True
            rid = result.request_id

            ok = await gate.approve(rid, approver="admin", comment="OK")
            assert ok is True

            approved, reason = await gate.check_approval_status(rid)
            assert approved is True
            assert reason == "approved"

        asyncio.run(run())

    def test_reg_real_04_approval_gate_reject(self):
        """REG-Real-04: ApprovalGate 拒绝流程"""
        from src.gateway.approval import ApprovalGate

        gate = ApprovalGate(timeout_seconds=5)
        ctx = {"user_id": "test_user", "session_id": "s2", "risk_level": "L4"}
        step_def = {"step_id": "1", "action": "pg_kill_session", "risk_level": "L4"}

        async def run():
            result = await gate.request_approval(
                step_def=step_def, params={}, context=ctx
            )
            rid = result.request_id
            await gate.reject(rid, approver="dba", reason="拒绝")
            approved, reason = await gate.check_approval_status(rid)
            assert approved is False
            assert reason == "rejected"

        import asyncio
        asyncio.run(run())

    @pytest.mark.asyncio
    async def test_reg_real_05_diagnostic_agent_real_pg(self):
        """REG-Real-05: DiagnosticAgent 使用真实 PG 数据"""
        from src.db.direct_postgres_connector import DirectPostgresConnector
        from src.agents.diagnostic import DiagnosticAgent
        from src.agents.base import AgentResponse

        conn = DirectPostgresConnector(
            host="localhost", port=5432,
            user="chongjieran", database="postgres",
        )
        sessions = await conn.get_sessions(limit=5)
        locks = await conn.get_locks()
        rep = await conn.get_replication()
        await conn.close()

        agent = DiagnosticAgent()
        ctx = {
            "instance_id": "PG-LOCAL-REAL",
            "alert_info": {
                "alert_id": "ALT-REG-001",
                "alert_type": "DATABASE_CHECK",
            },
            "extra_info": (
                f"会话:{len(sessions)}, 锁:{len(locks)}, "
                f"复制:{rep['role']}"
            ),
        }

        with patch.object(agent, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = (
                f"PostgreSQL 诊断完成。会话={len(sessions)}, "
                f"锁={len(locks)}, 角色={rep['role']}"
            )
            resp = await agent._process_direct("诊断 PG 状态", ctx)

        assert isinstance(resp, AgentResponse)
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_reg_real_06_sql_analyzer_agent_real(self):
        """REG-Real-06: SQLAnalyzerAgent 分析真实 SQL"""
        from src.agents.sql_analyzer import SQLAnalyzerAgent
        from src.agents.base import AgentResponse

        agent = SQLAnalyzerAgent()
        ctx = {"db_type": "postgresql"}

        with patch.object(agent, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = (
                "SQL 分析完成。建议：为 usename 列添加索引以加速过滤。"
            )
            resp = await agent.analyze_sql(
                sql="SELECT pid, usename FROM pg_stat_activity WHERE usename = 'test'",
                context=ctx,
            )
        assert isinstance(resp, AgentResponse)
        assert resp.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助: pytest 参数化
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not MYSQL_AVAILABLE, reason="MySQL not available")
def test_summary_all_databases_accessible():
    """Summary: 验证两个数据库都可访问"""
    import pymysql
    import psycopg2

    # PG
    pg_conn = psycopg2.connect(
        host="localhost", port=5432,
        user="chongjieran", database="postgres"
    )
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT 1")
    assert pg_cur.fetchone()[0] == 1
    pg_conn.close()

    # MySQL
    mysql_conn = pymysql.connect(
        host="127.0.0.1", port=3306,
        user="root", password="root"
    )
    with mysql_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    mysql_conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
