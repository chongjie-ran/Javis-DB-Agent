"""
V2.0 Round 3 验证测试
执行Agent: 真显
验证目标: BUG-001修复 + 直连PostgreSQL适配器 + postgres_tools直连 + pg_kill_session工具

运行方式:
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/v2.0/test_round3_verification.py -v --tb=short
    python3 -m pytest tests/v2.0/real_pg/ -v --tb=short
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
import asyncio
import yaml
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Optional

# =============================================================================
# BUG-001: YAML SOP Loader 字段映射测试
# =============================================================================

class TestBug001SOPFieldMapping:
    """BUG-001修复验证: SOP/Step字段ID映射"""

    @pytest.fixture
    def loader(self):
        from src.security.execution.yaml_sop_loader import YAMLSOPLoader
        sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "sop_yaml")
        return YAMLSOPLoader(sop_dir=sop_dir)

    def test_bug001_sop_id_mapping(self, loader):
        """
        test_bug001_sop_id_mapping: 验证sop_id正确映射到id
        修复前: SOP加载后sop["id"]可能为空，依赖name做sanitize
        修复后: sop["id"] = sop.get("sop_id") or sop.get("id") or sanitize(name)
        """
        sops = loader.load_all()
        assert len(sops) >= 1, "至少应加载1个SOP"

        for sop_id, sop in sops.items():
            # sop["id"] 不应为空
            assert "id" in sop, f"SOP缺少id字段: {sop_id}"
            assert sop["id"], f"SOP id字段为空: {sop_id}"

            # 验证id来源于sop_id（优先）
            raw_sop = loader.load_one(sop_id)
            if raw_sop and "sop_id" in raw_sop:
                assert sop["id"] == raw_sop["sop_id"], \
                    f"SOP id应来自sop_id字段: 期望{raw_sop['sop_id']}, 实际{sop['id']}"

        print(f"\n✅ BUG-001 sop_id映射验证通过: {len(sops)}个SOP的id字段正确")
        print(f"   示例: {list(sops.keys())[:3]}")

    def test_bug001_step_id_mapping(self, loader):
        """
        test_bug001_step_id_mapping: 验证step_id正确映射到step id
        修复前: step["id"]可能为空
        修复后: step["id"] = step.get("step_id") or step.get("id") or f"step_{i}"
        """
        sops = loader.load_all()
        assert len(sops) >= 1, "至少应加载1个SOP"

        for sop_id, sop in sops.items():
            steps = sop.get("steps", [])
            assert len(steps) > 0, f"SOP {sop_id}应有steps"

            for i, step in enumerate(steps):
                # step["id"] 不应为空
                assert "id" in step, f"Step缺少id字段: SOP={sop_id}, Step={i}"
                assert step["id"], f"Step id字段为空: SOP={sop_id}, Step={i}"

                # 验证id来源于step_id（优先）
                if "step_id" in step:
                    assert step["id"] == step["step_id"], \
                        f"Step id应来自step_id字段: 期望{step['step_id']}, 实际{step['id']}"
                elif "id" in step:
                    # 如果原始有id字段，应保留
                    pass
                else:
                    # 兜底: step_{i}
                    assert step["id"] == f"step_{i}", \
                        f"Step id兜底应为step_{{i}}: 期望step_{i}, 实际{step['id']}"

        print(f"\n✅ BUG-001 step_id映射验证通过")
        for sop_id, sop in sops.items():
            print(f"   {sop_id}: {[s['id'] for s in sop.get('steps', [])]}")

    def test_bug001_step_field_normalization(self, loader):
        """test_bug001_step_field_normalization: 验证step其他字段规范化"""
        sops = loader.load_all()

        for sop_id, sop in sops.items():
            for step in sop.get("steps", []):
                # risk_level 应为整数
                assert "risk_level" in step, f"step缺少risk_level: {sop_id}"
                assert isinstance(step["risk_level"], int), \
                    f"risk_level应为int: {type(step['risk_level'])}"

                # timeout_seconds 应有默认值
                assert "timeout_seconds" in step, f"step缺少timeout_seconds: {sop_id}"
                assert step["timeout_seconds"] > 0, f"timeout_seconds应>0: {step['timeout_seconds']}"

                # description/name 兼容
                assert "description" in step or "name" in step, \
                    f"step缺少description和name: {sop_id}"

        print(f"\n✅ BUG-001 step字段规范化验证通过")


# =============================================================================
# DirectPostgresConnector 测试
# =============================================================================

class TestDirectPostgresConnector:
    """直连PostgreSQL适配器测试"""

    @pytest.fixture
    def pg_config(self):
        """从TestConfig获取PG配置"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
        # 直接使用环境变量或默认值
        return {
            "host": os.environ.get("TEST_PG_HOST", "localhost"),
            "port": int(os.environ.get("TEST_PG_PORT", "5432")),
            "user": os.environ.get("TEST_PG_USER", "javis_test"),
            "password": os.environ.get("TEST_PG_PASSWORD", "javis_test123"),
            "database": os.environ.get("TEST_PG_DATABASE", "postgres"),
        }

    def test_direct_connector_env_config(self, pg_config):
        """
        test_direct_connector_env_config: 验证环境变量配置
        验证从环境变量创建DirectPostgresConnector
        """
        from src.db.direct_postgres_connector import get_default_postgres_connector

        # 设置环境变量
        os.environ["JAVIS_PG_HOST"] = pg_config["host"]
        os.environ["JAVIS_PG_PORT"] = str(pg_config["port"])
        os.environ["JAVIS_PG_USER"] = pg_config["user"]
        os.environ["JAVIS_PG_PASSWORD"] = pg_config["password"]
        os.environ["JAVIS_PG_DATABASE"] = pg_config["database"]

        connector = get_default_postgres_connector()

        assert connector.config["host"] == pg_config["host"]
        assert connector.config["port"] == pg_config["port"]
        assert connector.config["user"] == pg_config["user"]
        assert connector.config["password"] == pg_config["password"]
        assert connector.config["database"] == pg_config["database"]

        print(f"\n✅ DirectPostgresConnector环境变量配置正确")
        print(f"   {pg_config['host']}:{pg_config['port']}/{pg_config['database']}")

    @pytest.mark.asyncio
    async def test_direct_connector_sessions(self, pg_config):
        """
        test_direct_connector_sessions: 验证直连connector查询sessions
        """
        from src.db.direct_postgres_connector import DirectPostgresConnector

        connector = DirectPostgresConnector(
            host=pg_config["host"],
            port=pg_config["port"],
            user=pg_config["user"],
            password=pg_config["password"],
            database=pg_config["database"],
        )

        try:
            sessions = await connector.get_sessions(limit=10)
            assert isinstance(sessions, list), f"sessions应为list: {type(sessions)}"
            # sessions 可能为空（正常情况），但应为list
            print(f"\n✅ DirectPostgresConnector.get_sessions() 调用成功")
            print(f"   返回 {len(sessions)} 个会话")

            # 验证会话字段
            if sessions:
                s = sessions[0]
                assert "pid" in s, "会话应有pid字段"
                assert "username" in s, "会话应有username字段"
                print(f"   示例: pid={s.get('pid')}, user={s.get('username')}")
        finally:
            await connector.close()

    @pytest.mark.asyncio
    async def test_direct_connector_locks(self, pg_config):
        """
        test_direct_connector_locks: 验证直连connector查询locks
        """
        from src.db.direct_postgres_connector import DirectPostgresConnector

        connector = DirectPostgresConnector(
            host=pg_config["host"],
            port=pg_config["port"],
            user=pg_config["user"],
            password=pg_config["password"],
            database=pg_config["database"],
        )

        try:
            locks = await connector.get_locks()
            assert isinstance(locks, list), f"locks应为list: {type(locks)}"
            print(f"\n✅ DirectPostgresConnector.get_locks() 调用成功")
            print(f"   返回 {len(locks)} 个锁信息")
        finally:
            await connector.close()

    @pytest.mark.asyncio
    async def test_direct_connector_execute_sql(self, pg_config):
        """
        test_direct_connector_execute_sql: 验证直连connector执行SQL
        """
        from src.db.direct_postgres_connector import DirectPostgresConnector

        connector = DirectPostgresConnector(
            host=pg_config["host"],
            port=pg_config["port"],
            user=pg_config["user"],
            password=pg_config["password"],
            database=pg_config["database"],
        )

        try:
            # 执行简单查询
            result = await connector.execute_sql("SELECT 1 AS num, current_database() AS db")
            assert isinstance(result, list), f"result应为list: {type(result)}"
            assert len(result) > 0, "应有返回结果"
            assert result[0]["num"] == 1, f"SELECT 1应返回1: {result[0]}"
            print(f"\n✅ DirectPostgresConnector.execute_sql() 调用成功")
            print(f"   查询结果: {result[0]}")
        finally:
            await connector.close()

    @pytest.mark.asyncio
    async def test_direct_connector_health_check(self, pg_config):
        """
        test_direct_connector_health_check: 验证健康检查
        """
        from src.db.direct_postgres_connector import DirectPostgresConnector

        connector = DirectPostgresConnector(
            host=pg_config["host"],
            port=pg_config["port"],
            user=pg_config["user"],
            password=pg_config["password"],
            database=pg_config["database"],
        )

        try:
            health = await connector.health_check()
            assert health is True, "健康检查应返回True"
            print(f"\n✅ DirectPostgresConnector.health_check() 返回True")
        finally:
            await connector.close()

    @pytest.mark.asyncio
    async def test_direct_connector_kill_backend(self, pg_config):
        """
        test_direct_connector_kill_backend: 验证kill_backend方法存在
        注意: 不实际kill会话，只验证方法存在和参数校验
        """
        from src.db.direct_postgres_connector import DirectPostgresConnector

        connector = DirectPostgresConnector(
            host=pg_config["host"],
            port=pg_config["port"],
            user=pg_config["user"],
            password=pg_config["password"],
            database=pg_config["database"],
        )

        try:
            # 验证方法存在
            assert hasattr(connector, "kill_backend"), "应有kill_backend方法"
            assert callable(connector.kill_backend), "kill_backend应为可调用"

            # 获取当前后端PID（当前连接本身的PID），使用新会话执行查询
            async def get_current_pid():
                pool = await connector._get_pool()
                async with pool.acquire() as conn:
                    return await conn.fetchval("SELECT pg_backend_pid()")

            current_pid = await get_current_pid()
            assert current_pid is not None, "应能获取当前backend PID"

            # 验证kill_backend调用成功（发送SIGTERM到自己的后台进程会失败，但方法签名正确）
            # 用一个无害的方式测试：cancel类型（SIGINT）同样无害
            result = await connector.kill_backend(current_pid, "cancel")
            assert isinstance(result, dict), f"kill_backend应返回dict: {type(result)}"
            assert "pid" in result, "返回应包含pid"
            assert result["pid"] == current_pid, f"返回的PID应一致: {result['pid']}"
            print(f"\n✅ DirectPostgresConnector.kill_backend() 定义正确")
            print(f"   PID={current_pid}, kill_type={result.get('kill_type')}")
        finally:
            await connector.close()


# =============================================================================
# PostgreSQL Tools 直连模式测试
# =============================================================================

class TestPostgresToolsDirectMode:
    """postgres_tools直连模式测试"""

    @pytest.fixture
    def pg_config(self):
        return {
            "host": os.environ.get("TEST_PG_HOST", "localhost"),
            "port": int(os.environ.get("TEST_PG_PORT", "5432")),
            "user": os.environ.get("TEST_PG_USER", "javis_test"),
            "password": os.environ.get("TEST_PG_PASSWORD", "javis_test123"),
            "database": os.environ.get("TEST_PG_DATABASE", "postgres"),
        }

    @pytest.fixture
    def db_connector(self, pg_config):
        from src.db.direct_postgres_connector import DirectPostgresConnector
        return DirectPostgresConnector(
            host=pg_config["host"],
            port=pg_config["port"],
            user=pg_config["user"],
            password=pg_config["password"],
            database=pg_config["database"],
        )

    @pytest.mark.asyncio
    async def test_pg_session_tool_real(self, db_connector):
        """
        test_pg_session_tool_real: 验证PGSessionAnalysisTool直连PG
        """
        from src.tools.postgres_tools import PGSessionAnalysisTool

        tool = PGSessionAnalysisTool()
        context = {
            "instance_id": "INS-TEST-001",
            "db_connector": db_connector,
        }
        params = {
            "instance_id": "INS-TEST-001",
            "state_filter": "",
            "limit": 10,
        }

        result = await tool.execute(params, context)

        assert result.success is True, f"PGSessionAnalysisTool执行失败: {result.error}"
        assert "sessions" in result.data, f"结果应包含sessions: {result.data.keys()}"
        assert isinstance(result.data["sessions"], list), "sessions应为list"
        print(f"\n✅ PGSessionAnalysisTool直连PG成功")
        print(f"   会话数: {result.data['total']}, 活跃: {result.data.get('active_count', 0)}")

    @pytest.mark.asyncio
    async def test_pg_lock_tool_real(self, db_connector):
        """
        test_pg_lock_tool_real: 验证PGLockAnalysisTool直连PG
        """
        from src.tools.postgres_tools import PGLockAnalysisTool

        tool = PGLockAnalysisTool()
        context = {
            "instance_id": "INS-TEST-001",
            "db_connector": db_connector,
        }
        params = {
            "instance_id": "INS-TEST-001",
            "include_graph": False,
        }

        result = await tool.execute(params, context)

        assert result.success is True, f"PGLockAnalysisTool执行失败: {result.error}"
        assert "locks" in result.data, f"结果应包含locks: {result.data.keys()}"
        assert isinstance(result.data["locks"], list), "locks应为list"
        print(f"\n✅ PGLockAnalysisTool直连PG成功")
        print(f"   锁数量: {result.data['total']}")

    @pytest.mark.asyncio
    async def test_pg_replication_tool_real(self, db_connector):
        """
        test_pg_replication_tool_real: 验证PGReplicationStatusTool直连PG
        """
        from src.tools.postgres_tools import PGReplicationStatusTool

        tool = PGReplicationStatusTool()
        context = {
            "instance_id": "INS-TEST-001",
            "db_connector": db_connector,
        }
        params = {
            "instance_id": "INS-TEST-001",
        }

        result = await tool.execute(params, context)

        assert result.success is True, f"PGReplicationStatusTool执行失败: {result.error}"
        assert "role" in result.data, f"结果应包含role: {result.data.keys()}"
        print(f"\n✅ PGReplicationStatusTool直连PG成功")
        print(f"   角色: {result.data['role']}, 复制启用: {result.data.get('replication_enabled', False)}")

    @pytest.mark.asyncio
    async def test_pg_bloat_tool_real(self, db_connector):
        """
        test_pg_bloat_tool_real: 验证PGBloatAnalysisTool执行真实SQL
        """
        from src.tools.postgres_tools import PGBloatAnalysisTool

        tool = PGBloatAnalysisTool()
        context = {
            "instance_id": "INS-TEST-001",
            "db_connector": db_connector,
        }
        params = {
            "instance_id": "INS-TEST-001",
            "min_bloat_percent": 0.0,  # 0.0 以查看所有表
            "schema": "",
        }

        result = await tool.execute(params, context)

        assert result.success is True, f"PGBloatAnalysisTool执行失败: {result.error}"
        assert "tables" in result.data, f"结果应包含tables: {result.data.keys()}"
        print(f"\n✅ PGBloatAnalysisTool直连PG成功")
        print(f"   膨胀表数量: {result.data['total']}")

    @pytest.mark.asyncio
    async def test_pg_index_tool_real(self, db_connector):
        """
        test_pg_index_tool_real: 验证PGIndexAnalysisTool执行真实SQL
        """
        from src.tools.postgres_tools import PGIndexAnalysisTool

        tool = PGIndexAnalysisTool()
        context = {
            "instance_id": "INS-TEST-001",
            "db_connector": db_connector,
        }
        params = {
            "instance_id": "INS-TEST-001",
            "table": "",
        }

        result = await tool.execute(params, context)

        assert result.success is True, f"PGIndexAnalysisTool执行失败: {result.error}"
        assert "indexes" in result.data, f"结果应包含indexes: {result.data.keys()}"
        print(f"\n✅ PGIndexAnalysisTool直连PG成功")
        print(f"   索引数量: {result.data['total']}, 总大小: {result.data.get('total_size_mb', 0)} MB")


# =============================================================================
# PGKillSessionTool 测试
# =============================================================================

class TestPGKillSessionTool:
    """PGKillSessionTool工具验证"""

    def test_pg_kill_session_tool_definition(self):
        """
        test_pg_kill_session_tool: 验证PGKillSessionTool定义正确
        - L4_MEDIUM 风险等级
        - 调用pg_terminate_backend或pg_cancel_backend
        - 参数校验正确
        """
        from src.tools.postgres_tools import PGKillSessionTool
        from src.tools.base import RiskLevel

        tool = PGKillSessionTool()

        # 验证定义
        assert tool.definition is not None, "应有ToolDefinition"
        assert tool.definition.name == "pg_kill_session", f"工具名应为pg_kill_session: {tool.definition.name}"
        assert tool.definition.risk_level == RiskLevel.L4_MEDIUM, \
            f"风险等级应为L4_MEDIUM: {tool.definition.risk_level}"

        # 验证参数
        param_names = [p.name for p in tool.definition.params]
        assert "instance_id" in param_names, "应有instance_id参数"
        assert "pid" in param_names, "应有pid参数"
        assert "kill_type" in param_names, "应有kill_type参数"

        # 验证pid参数类型为int
        pid_param = next(p for p in tool.definition.params if p.name == "pid")
        assert pid_param.type == "int", f"pid参数类型应为int: {pid_param.type}"

        # 验证kill_type参数有默认值
        kill_type_param = next(p for p in tool.definition.params if p.name == "kill_type")
        assert kill_type_param.default == "terminate", \
            f"kill_type默认值应为terminate: {kill_type_param.default}"

        print(f"\n✅ PGKillSessionTool定义正确")
        print(f"   风险等级: L4_MEDIUM")
        print(f"   参数: {param_names}")
        print(f"   示例: {tool.definition.example}")

    @pytest.mark.asyncio
    async def test_pg_kill_session_invalid_kill_type(self):
        """
        test_pg_kill_session_invalid_kill_type: 验证kill_type参数校验
        """
        from src.tools.postgres_tools import PGKillSessionTool

        tool = PGKillSessionTool()
        context = {"db_connector": None}
        params = {
            "instance_id": "INS-TEST-001",
            "pid": 12345,
            "kill_type": "invalid_type",
        }

        result = await tool.execute(params, context)

        assert result.success is False, "无效kill_type应返回失败"
        assert "Invalid kill_type" in result.error, f"应包含Invalid kill_type错误: {result.error}"
        print(f"\n✅ PGKillSessionTool参数校验正确: {result.error}")

    @pytest.mark.asyncio
    async def test_pg_kill_session_no_connector(self):
        """
        test_pg_kill_session_no_connector: 验证无db_connector时正确报错
        """
        from src.tools.postgres_tools import PGKillSessionTool

        tool = PGKillSessionTool()
        context = {"db_connector": None}
        params = {
            "instance_id": "INS-TEST-001",
            "pid": 12345,
            "kill_type": "terminate",
        }

        result = await tool.execute(params, context)

        assert result.success is False, "无db_connector应返回失败"
        assert "No db_connector" in result.error, f"应包含No db_connector错误: {result.error}"
        print(f"\n✅ PGKillSessionTool无connector时报错正确: {result.error}")

    @pytest.mark.asyncio
    async def test_pg_kill_session_valid_params(self, db_connector=None):
        """
        test_pg_kill_session_valid_params: 验证有效参数下的行为
        注意: 不实际kill会话，只验证方法调用
        """
        from src.tools.postgres_tools import PGKillSessionTool

        # 创建mock connector with kill_backend
        mock_connector = MagicMock()
        mock_connector.kill_backend = AsyncMock(return_value={"pid": 99999, "kill_type": "terminate", "result": True})

        tool = PGKillSessionTool()
        context = {"db_connector": mock_connector}
        params = {
            "instance_id": "INS-TEST-001",
            "pid": 99999,
            "kill_type": "terminate",
        }

        result = await tool.execute(params, context)

        assert result.success is True, f"有效参数应返回成功: {result.error}"
        assert result.data["killed"] == 99999, f"应返回killed的PID: {result.data}"
        mock_connector.kill_backend.assert_called_once_with(99999, "terminate")
        print(f"\n✅ PGKillSessionTool有效参数验证通过")


# =============================================================================
# 工具注册测试
# =============================================================================

class TestPostgresToolsRegistration:
    """PostgreSQL工具注册测试"""

    def test_register_postgres_tools(self):
        """
        test_register_postgres_tools: 验证工具注册函数存在且返回正确数量
        """
        from src.tools.postgres_tools import register_postgres_tools

        # Mock registry
        mock_registry = MagicMock()
        mock_registry.register = MagicMock()

        tools = register_postgres_tools(mock_registry)

        assert isinstance(tools, list), "应返回工具列表"
        assert len(tools) == 6, f"应注册6个PG工具，实际{len(tools)}个: {[t.definition.name for t in tools]}"

        # 验证所有工具都已注册
        tool_names = [t.definition.name for t in tools]
        expected = ["pg_session_analysis", "pg_lock_analysis", "pg_replication_status",
                    "pg_bloat_analysis", "pg_index_analysis", "pg_kill_session"]
        assert set(tool_names) == set(expected), f"工具名不匹配: {tool_names}"

        print(f"\n✅ PostgreSQL工具注册正确: {tool_names}")


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
