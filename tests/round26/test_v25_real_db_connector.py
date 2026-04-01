"""
V2.5 Inspector真实DB连接器测试 - Round26
=========================================
测试目标：
  1. InspectorAgent 使用真实数据库连接器
  2. 连接池管理（创建、复用、关闭）
  3. 连接异常处理（连接失败、超时、无效连接）

验收标准：
  - InspectorAgent 能正确获取 db_connector
  - 真实连接时调用工具获取真实数据
  - 连接池复用，避免重复创建
  - 异常情况下有友好错误提示

测试方法：
  - Mock db_connector：验证调用逻辑
  - 真实连接（可选）：端到端验证

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round26/test_v25_real_db_connector.py -v --tb=short
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

# ── 路径设置 ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.inspector import InspectorAgent
from src.db.direct_postgres_connector import DirectPostgresConnector
from src.agents.base import AgentResponse


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def is_meaningful_content(content: str) -> bool:
    """判断内容是否有意义（非空、非占位符、非"未找到"）"""
    if not content or not content.strip():
        return False
    if "未找到" in content or "未找到相关信息" in content:
        return False
    if len(content.strip()) < 10:
        return False
    return True


def make_llm_mock(response: str):
    """创建一个 LLM complete 方法的 AsyncMock，返回指定内容"""
    mock = AsyncMock()
    mock.return_value = response
    return mock


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def inspector_agent():
    """InspectorAgent 实例"""
    return InspectorAgent()


@pytest.fixture
def mock_context():
    """标准上下文（无数据库连接）"""
    return {
        "session_id": "test-session-001",
        "user_id": "test-user",
        "extra_info": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: 连接器获取与识别
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBConnectorRecognition:
    """验证 InspectorAgent 正确识别和获取 db_connector"""

    @pytest.mark.asyncio
    async def test_dbc_01_recognizes_pg_connector(self, inspector_agent, mock_context):
        """DBC-01: InspectorAgent 识别 context.pg_connector"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return [{"pid": 1234, "username": "test", "state": "active", "query": "SELECT 1"}]
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": FakePGConnector()}

        # Mock call_tool 来验证工具被调用
        with patch.object(inspector_agent, "call_tool", new_callable=AsyncMock) as mock_call_tool:
            mock_call_tool.return_value = MagicMock(
                success=True,
                data={"sessions": [], "total": 0}
            )
            response = await inspector_agent._process_direct("数据库健康检查", ctx)

        assert response.success is True
        assert is_meaningful_content(response.content)
        # metadata 中应标记有真实数据
        assert response.metadata.get("has_real_data") is True

    @pytest.mark.asyncio
    async def test_dbc_02_recognizes_db_connector(self, inspector_agent, mock_context):
        """DBC-02: InspectorAgent 识别 context.db_connector"""
        class FakeDBConnector:
            async def get_sessions(self, limit=100):
                return [{"pid": 5678, "username": "app", "state": "idle", "query": "SELECT"}]
            async def get_locks(self):
                return [{"locktype": "relation", "mode": "ShareLock", "pid": 5678}]
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": True, "replicas": []}
            async def close(self):
                pass

        ctx = {**mock_context, "db_connector": FakeDBConnector()}

        with patch.object(inspector_agent, "call_tool", new_callable=AsyncMock) as mock_call_tool:
            mock_call_tool.return_value = MagicMock(
                success=True,
                data={"sessions": [], "total": 0}
            )
            response = await inspector_agent._process_direct("查看会话", ctx)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert response.metadata.get("has_real_data") is True

    @pytest.mark.asyncio
    async def test_dbc_03_prefers_pg_connector_over_db_connector(self, inspector_agent, mock_context):
        """DBC-03: 同时存在时，pg_connector 优先于 db_connector"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return [{"pid": 9999, "username": "pg_user", "state": "active"}]
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        class FakeDBConnector:
            async def get_sessions(self, limit=100):
                return [{"pid": 1111, "username": "db_user", "state": "idle"}]
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "standby", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        ctx = {
            **mock_context,
            "pg_connector": FakePGConnector(),
            "db_connector": FakeDBConnector(),
        }

        call_args = []

        async def mock_call_tool(tool_name, params, ctx):
            call_args.append((tool_name, ctx.get("db_connector")))
            return MagicMock(success=True, data={"sessions": [], "total": 0})

        with patch.object(inspector_agent, "call_tool", side_effect=mock_call_tool):
            response = await inspector_agent._process_direct("健康检查", ctx)

        assert response.success is True
        # db_connector 应该被传入（pg_connector 优先）
        pg_connector_used = any(
            isinstance(args[1], FakePGConnector) if args[1] else False
            for args in call_args
        )
        assert pg_connector_used, "pg_connector should be used as db_connector"

    @pytest.mark.asyncio
    async def test_dbc_04_no_connector_returns_mock_data(self, inspector_agent, mock_context):
        """DBC-04: 无连接器时，InspectorAgent 不崩溃并返回友好内容"""
        response = await inspector_agent._process_direct("数据库健康检查", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content
        # metadata 应标记无真实数据
        assert response.metadata.get("has_real_data") is False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: 真实数据库连接功能
# ═══════════════════════════════════════════════════════════════════════════════

class TestRealDBConnection:
    """验证真实数据库连接功能"""

    @pytest.mark.asyncio
    async def test_rdc_01_calls_pg_session_analysis(self, inspector_agent, mock_context):
        """RDC-01: 真实连接时调用 pg_session_analysis 工具"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return [
                    {"pid": 1234, "username": "test", "state": "active", "query": "SELECT 1"},
                    {"pid": 5678, "username": "app", "state": "idle", "query": "SELECT"},
                ]
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": FakePGConnector()}
        call_args = []

        async def mock_call_tool(tool_name, params, ctx):
            call_args.append(tool_name)
            return MagicMock(success=True, data={"sessions": [], "total": 2})

        with patch.object(inspector_agent, "call_tool", side_effect=mock_call_tool):
            response = await inspector_agent._process_direct("分析会话", ctx)

        assert response.success is True
        assert "pg_session_analysis" in call_args, \
            f"应调用 pg_session_analysis，实际调用: {call_args}"

    @pytest.mark.asyncio
    async def test_rdc_02_calls_pg_lock_analysis(self, inspector_agent, mock_context):
        """RDC-02: 真实连接时调用 pg_lock_analysis 工具"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return []
            async def get_locks(self):
                return [{"locktype": "relation", "mode": "ExclusiveLock", "pid": 1234, "granted": True}]
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": FakePGConnector()}
        call_args = []

        async def mock_call_tool(tool_name, params, ctx):
            call_args.append(tool_name)
            return MagicMock(success=True, data={"locks": [], "total": 1})

        with patch.object(inspector_agent, "call_tool", side_effect=mock_call_tool):
            response = await inspector_agent._process_direct("分析锁", ctx)

        assert response.success is True
        assert "pg_lock_analysis" in call_args, \
            f"应调用 pg_lock_analysis，实际调用: {call_args}"

    @pytest.mark.asyncio
    async def test_rdc_03_calls_pg_replication_status(self, inspector_agent, mock_context):
        """RDC-03: 真实连接时调用 pg_replication_status 工具"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return []
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": True, "replicas": [
                    {"pid": 9999, "client_addr": "192.168.1.100", "state": "streaming"}
                ]}
            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": FakePGConnector()}
        call_args = []

        async def mock_call_tool(tool_name, params, ctx):
            call_args.append(tool_name)
            return MagicMock(success=True, data={"replication": {}})

        with patch.object(inspector_agent, "call_tool", side_effect=mock_call_tool):
            response = await inspector_agent._process_direct("复制状态", ctx)

        assert response.success is True
        assert "pg_replication_status" in call_args, \
            f"应调用 pg_replication_status，实际调用: {call_args}"

    @pytest.mark.asyncio
    async def test_rdc_04_passes_connector_to_call_tool(self, inspector_agent, mock_context):
        """RDC-04: InspectorAgent 将 db_connector 传递给 call_tool"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return [{"pid": 1234, "username": "test", "state": "active"}]
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        fake_connector = FakePGConnector()
        ctx = {**mock_context, "pg_connector": fake_connector}
        received_connector = None

        async def mock_call_tool(tool_name, params, call_ctx):
            nonlocal received_connector
            received_connector = call_ctx.get("db_connector")
            return MagicMock(success=True, data={"sessions": []})

        with patch.object(inspector_agent, "call_tool", side_effect=mock_call_tool):
            await inspector_agent._process_direct("健康检查", ctx)

        assert received_connector is fake_connector, \
            "db_connector should be passed to call_tool context"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: 连接池管理
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionPoolManagement:
    """验证连接池管理功能"""

    @pytest.mark.asyncio
    async def test_cpm_01_direct_postgres_connector_creates_pool(self):
        """CPM-01: DirectPostgresConnector 正确创建连接池"""
        connector = DirectPostgresConnector(
            host="localhost",
            port=5432,
            user="postgres",
            password="",
            database="postgres"
        )

        # 模拟连接池
        mock_pool = MagicMock()
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_pool
            pool = await connector._get_pool()

        assert pool is mock_pool
        assert connector._pool is mock_pool

    @pytest.mark.asyncio
    async def test_cpm_02_connector_reuses_existing_pool(self):
        """CPM-02: 连接池被复用，不会重复创建"""
        connector = DirectPostgresConnector()

        mock_pool = MagicMock()
        call_count = 0

        async def mock_create_pool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=mock_create_pool):
            # 第一次调用
            pool1 = await connector._get_pool()
            # 第二次调用（应该复用）
            pool2 = await connector._get_pool()

        assert call_count == 1, f"连接池只应创建一次，实际: {call_count}次"
        assert pool1 is pool2

    @pytest.mark.asyncio
    async def test_cpm_03_connector_close_closes_pool(self):
        """CPM-03: close() 方法正确关闭连接池"""
        connector = DirectPostgresConnector()

        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        connector._pool = mock_pool

        await connector.close()

        mock_pool.close.assert_called_once()
        assert connector._pool is None

    @pytest.mark.asyncio
    async def test_cpm_04_multiple_connectors_have_separate_pools(self):
        """CPM-04: 多个连接器实例有独立的连接池"""
        connector_a = DirectPostgresConnector(host="localhost", port=5432)
        connector_b = DirectPostgresConnector(host="localhost", port=5432)

        mock_pool_a = MagicMock()
        mock_pool_b = MagicMock()

        pools_created = []

        async def mock_create_pool(*args, **kwargs):
            pools_created.append(MagicMock())

        with patch("asyncpg.create_pool", side_effect=mock_create_pool):
            pool_a = await connector_a._get_pool()
            pool_b = await connector_b._get_pool()

        assert len(pools_created) == 2, "应创建两个独立连接池"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: 连接异常处理
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionExceptionHandling:
    """验证连接异常处理"""

    @pytest.mark.asyncio
    async def test_ceh_01_connection_timeout_handled(self, inspector_agent, mock_context):
        """CEH-01: 连接超时时有友好错误提示"""
        class TimeoutPGConnector:
            async def get_sessions(self, limit=100):
                raise TimeoutError("连接超时")

            async def get_locks(self):
                return []

            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}

            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": TimeoutPGConnector()}

        response = await inspector_agent._process_direct("健康检查", ctx)

        # 不应崩溃，应返回错误信息
        assert response.success is True
        assert is_meaningful_content(response.content)

    @pytest.mark.asyncio
    async def test_ceh_02_invalid_credentials_handled(self, inspector_agent, mock_context):
        """CEH-02: 无效凭据时有友好错误提示"""
        connector = DirectPostgresConnector(
            host="localhost",
            port=5432,
            user="invalid_user",
            password="wrong_password",
            database="postgres"
        )

        async def mock_create_pool(*args, **kwargs):
            raise Exception("password authentication failed")

        with patch("asyncpg.create_pool", side_effect=mock_create_pool):
            with pytest.raises(Exception):
                await connector._get_pool()

    @pytest.mark.asyncio
    async def test_ceh_03_connector_health_check_returns_false_on_error(self):
        """CEH-03: health_check 在连接失败时返回 False"""
        connector = DirectPostgresConnector(
            host="invalid-host",
            port=5432
        )

        async def mock_create_pool(*args, **kwargs):
            raise Exception("无法连接到数据库")

        with patch("asyncpg.create_pool", side_effect=mock_create_pool):
            result = await connector.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_ceh_04_get_sessions_returns_empty_on_error(self):
        """CEH-04: get_sessions 在错误时返回空列表而非崩溃"""
        connector = DirectPostgresConnector()

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = Exception("查询失败")
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        connector._pool = mock_pool

        result = await connector.get_sessions(limit=10)

        assert result == []
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: MySQL 连接器支持
# ═══════════════════════════════════════════════════════════════════════════════

class TestMySQLConnectorSupport:
    """验证 MySQL 连接器支持"""

    @pytest.mark.asyncio
    async def test_mysql_01_inspector_handles_mysql_connector(self, inspector_agent, mock_context):
        """MYSQL-01: InspectorAgent 处理 mysql_connector"""
        class FakeMySQLSession:
            status = "active"
            command = "Query"
            time = 0

        class FakeMySQLConnector:
            async def get_sessions(self, limit=10):
                return [FakeMySQLSession()]

        ctx = {**mock_context, "mysql_connector": FakeMySQLConnector()}

        with patch.object(inspector_agent, "call_tool", new_callable=AsyncMock) as mock_call_tool:
            mock_call_tool.return_value = MagicMock(success=True, data={})
            response = await inspector_agent._process_direct("MySQL健康检查", ctx)

        assert response.success is True
        assert is_meaningful_content(response.content)

    @pytest.mark.asyncio
    async def test_mysql_02_mysql_error_does_not_crash(self, inspector_agent, mock_context):
        """MYSQL-02: MySQL 获取会话失败时不崩溃"""
        class BadMySQLConnector:
            async def get_sessions(self, limit=10):
                raise Exception("MySQL 连接失败")

        ctx = {**mock_context, "mysql_connector": BadMySQLConnector()}

        # 不应崩溃
        response = await inspector_agent._process_direct("MySQL健康检查", ctx)

        assert response.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
