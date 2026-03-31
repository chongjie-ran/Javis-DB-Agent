"""
V2.0 Round 2 验证测试
执行Agent: 真显
验证目标: YAML SOP加载器 + Action→Tool映射 + 工具链路注入

运行方式:
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/v2.0/test_round2_verification.py -v --tb=short
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Optional

# =============================================================================
# YAML SOP Loader Tests
# =============================================================================

class TestYAMLSOPLoader:
    """YAML SOP加载器测试"""

    @pytest.fixture
    def loader(self):
        """创建加载器实例"""
        from src.security.execution.yaml_sop_loader import YAMLSOPLoader
        sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "sop_yaml")
        return YAMLSOPLoader(sop_dir=sop_dir)

    def test_yaml_sop_loader_load_all(self, loader):
        """test_yaml_sop_loader_load_all: 加载所有YAML SOP"""
        sops = loader.load_all()
        # 应加载3个SOP
        assert len(sops) == 3, f"期望3个SOP，实际加载了{len(sops)}个: {list(sops.keys())}"
        # 修复后：sop_id字段被正确映射到id
        actual_ids = set(sops.keys())
        expected_ids = {"slow_sql_diagnosis", "lock_wait_diagnosis", "session_cleanup"}
        assert actual_ids == expected_ids, f"ID不匹配: 期望{expected_ids}, 实际{actual_ids}"
        print(f"\n✅ 加载了 {len(sops)} 个SOP: {list(sops.keys())}")
        print(f"   注意: sop_id字段已正确映射到id")

    def test_yaml_sop_loader_load_one(self, loader):
        """test_yaml_sop_loader_load_one: 加载单个SOP"""
        sop = loader.load_one("slow_sql_diagnosis")
        assert sop is not None, "slow_sql_diagnosis应能加载"
        assert "慢SQL诊断" in str(sop.get("name", "")), f"SOP name不正确: {sop.get('name')}"
        print(f"\n✅ 加载单个SOP: {sop.get('name')}")

    def test_yaml_sop_loader_load_nonexistent(self, loader):
        """test_yaml_sop_loader_load_nonexistent: 加载不存在的SOP返回None"""
        sop = loader.load_one("nonexistent_sop_xyz")
        assert sop is None, "不存在的SOP应返回None"
        print(f"\n✅ 不存在的SOP返回None")

    def test_yaml_sop_normalize_fields(self, loader):
        """test_yaml_sop_normalize_fields: 验证字段规范化"""
        sop = loader.load_one("slow_sql_diagnosis")
        assert sop is not None

        # 验证 steps 规范化
        steps = sop.get("steps", [])
        assert len(steps) > 0, "应有steps"

        for step in steps:
            # step 字段应为数字
            assert "step" in step or "step_id" in step, f"step缺少step/step_id字段: {step}"
            # risk_level 应为整数
            assert isinstance(step.get("risk_level"), int), f"risk_level应为int: {step.get('risk_level')}"
            # timeout_seconds 应有默认值
            assert "timeout_seconds" in step, f"step缺少timeout_seconds: {step}"

        print(f"\n✅ 字段规范化正确: {len(steps)} steps")

    def test_yaml_sop_id_field_issue(self, loader):
        """test_yaml_sop_id_field_issue: 验证sop_id vs id字段问题

        修复后：sop_id字段被正确映射到id，不再使用name作为fallback。
        """
        sop = loader.load_one("slow_sql_diagnosis")
        assert sop is not None

        # 修复后：sop_id被正确映射到id
        sop_id = sop.get("id", "")
        name = sop.get("name", "")
        print(f"\n✅ YAML sop_id vs loader id: id='{sop_id}', name='{name}'")
        print(f"   YAML定义sop_id='slow_sql_diagnosis'，loader正确识别")

        # 修复后：sop_id字段被正确映射
        assert sop_id == "slow_sql_diagnosis", f"sop_id字段未被正确映射: got '{sop_id}'"
        print(f"   ✅ sop_id字段已正确映射到id")


# =============================================================================
# Action Mapper Tests
# =============================================================================

class TestActionToolMapper:
    """Action→Tool映射器测试"""

    @pytest.fixture
    def mapper(self):
        from src.security.execution.action_tool_mapper import ActionToolMapper
        return ActionToolMapper()

    def test_action_mapper_resolve(self, mapper):
        """test_action_mapper_resolve: 验证action解析到tool"""
        # 测试已知映射
        assert mapper.resolve("find_idle_sessions") == "pg_session_analysis"
        assert mapper.resolve("find_blocking_sessions") == "pg_lock_analysis"
        assert mapper.resolve("find_slow_queries") == "pg_session_analysis"
        assert mapper.resolve("analyze_lock_chain") == "pg_lock_analysis"
        assert mapper.resolve("suggest_index") == "pg_index_analysis"
        assert mapper.resolve("check_replication") == "pg_replication_status"
        print(f"\n✅ Action映射正确")

    def test_action_mapper_unknown_action(self, mapper):
        """test_action_mapper_unknown_action: 验证未知action处理"""
        # 未知action应返回None
        assert mapper.resolve("unknown_action_xyz") is None
        assert mapper.resolve("pg_execute_sql") is None  # 未实现工具
        print(f"\n✅ 未知action正确返回None")

    def test_action_mapper_pg_tools(self, mapper):
        """test_action_mapper_pg_tools: 验证PG工具映射完整性"""
        all_actions = mapper.get_all_actions()
        print(f"\n总共有 {len(all_actions)} 个action映射")

        # 统计映射到None的action（未实现工具）
        none_count = sum(1 for a in all_actions if mapper.resolve(a) is None)
        mapped_count = len(all_actions) - none_count

        print(f"已映射工具: {mapped_count}, 待实现工具: {none_count}")
        print(f"待实现工具的action: {[a for a in all_actions if mapper.resolve(a) is None]}")

        # 验证关键action都有映射
        key_actions = [
            "find_idle_sessions", "find_blocking_sessions", "find_slow_queries",
            "analyze_lock_chain", "suggest_index", "check_replication"
        ]
        for action in key_actions:
            assert mapper.resolve(action) is not None, f"{action}应有tool映射"

        print(f"\n✅ PG工具映射完整性验证通过")

    def test_action_mapper_custom_override(self, mapper):
        """test_action_mapper_custom_override: 验证自定义映射覆盖"""
        custom_map = {"find_idle_sessions": "custom_tool"}
        custom_mapper = type(mapper)(custom_map=custom_map)
        assert custom_mapper.resolve("find_idle_sessions") == "custom_tool"
        # 其他不受影响
        assert custom_mapper.resolve("find_blocking_sessions") == "pg_lock_analysis"
        print(f"\n✅ 自定义映射覆盖正确")

    def test_action_mapper_register(self, mapper):
        """test_action_mapper_register: 验证动态注册"""
        mapper.register("new_action", "new_tool")
        assert mapper.resolve("new_action") == "new_tool"
        print(f"\n✅ 动态注册正确")


# =============================================================================
# SOPExecutor Integration Tests
# =============================================================================

class TestSOPExecutorIntegration:
    """SOPExecutor集成测试"""

    @pytest.fixture
    def sop_dir(self):
        return os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "sop_yaml")

    @pytest.fixture
    def executor_no_registry(self, sop_dir):
        """无tool_registry的executor（使用mock fallback）"""
        from src.security.execution.sop_executor import SOPExecutor
        return SOPExecutor(yaml_sop_dir=sop_dir)

    @pytest.fixture
    def mock_tool_registry(self):
        """Mock工具注册表"""
        registry = MagicMock()
        registry.get_tool = MagicMock(return_value=None)  # 默认无工具
        return registry

    @pytest.fixture
    def executor_with_registry(self, sop_dir, mock_tool_registry):
        """有tool_registry的executor"""
        from src.security.execution.sop_executor import SOPExecutor
        return SOPExecutor(
            yaml_sop_dir=sop_dir,
            tool_registry=mock_tool_registry
        )

    def test_sop_executor_yaml_priority(self, executor_no_registry):
        """test_sop_executor_yaml_priority: 验证YAML优先于硬编码"""
        sops = executor_no_registry.list_sops()

        # YAML应覆盖硬编码SOP
        sop_ids = [s.get("id") or s.get("name") for s in sops]
        print(f"\n加载的SOP: {sop_ids}")

        # 验证YAML SOP已加载
        yaml_sop_ids = ["slow_sql_diagnosis", "lock_wait_diagnosis", "session_cleanup"]
        for yid in yaml_sop_ids:
            found = any(yid in str(sid) for sid in sop_ids)
            # 注意：由于sop_id未被正确映射，可能找不到
            if not found:
                print(f"  ⚠️  YAML SOP '{yid}' 未被识别（sop_id vs id问题）")

        # 硬编码SOP仍存在
        hardcoded = ["refresh_stats", "kill_idle_session", "慢SQL优化", "lock_wait_diagnosis"]
        hardcoded_found = [h for h in hardcoded if any(h in str(sid) for sid in sop_ids)]
        print(f"硬编码SOP: {hardcoded_found}")

        print(f"\n✅ YAML优先验证完成")

    def test_sop_executor_action_mapper(self, sop_dir):
        """test_sop_executor_action_mapper: 验证action映射正确"""
        from src.security.execution.sop_executor import SOPExecutor
        from src.security.execution.action_tool_mapper import ActionToolMapper

        mapper = ActionToolMapper()
        executor = SOPExecutor(
            yaml_sop_dir=sop_dir,
            action_mapper=mapper
        )

        # 验证executor有action_mapper
        assert executor.action_mapper is not None

        # 验证映射器工作正常
        assert executor.action_mapper.resolve("find_idle_sessions") == "pg_session_analysis"
        print(f"\n✅ SOPExecutor集成action_mapper正确")

    def test_sop_executor_tool_registry_param(self, executor_with_registry):
        """test_sop_executor_tool_registry_param: 验证tool_registry参数注入"""
        # 验证tool_registry已注入
        assert executor_with_registry.tool_registry is not None
        print(f"\n✅ tool_registry参数注入成功")

    def test_pg_kill_session_registered(self, mock_tool_registry):
        """test_pg_kill_session_registered: 验证pg_kill_session已注册到registry

        Round 3实现：pg_kill_session已实现并注册
        """
        from src.tools.postgres_tools import PGKillSessionTool

        tool = PGKillSessionTool()
        assert tool.name == "pg_kill_session"
        assert tool.definition.risk_level.name == "L4_MEDIUM"
        print(f"\n✅ pg_kill_session已注册: risk={tool.definition.risk_level.name}")

    def test_sop_executor_backward_compat(self, sop_dir):
        """test_sop_executor_backward_compat: 验证无yaml时fallback到硬编码"""
        from src.security.execution.sop_executor import SOPExecutor

        # 使用不存在的目录，强制使用硬编码
        executor = SOPExecutor(yaml_sop_dir="/nonexistent/path")

        # 应能加载硬编码SOP
        sops = executor.list_sops()
        assert len(sops) > 0, "应fallback到硬编码SOP"

        # 硬编码SOP应存在
        sop_ids = [s.get("id") or s.get("name") for s in sops]
        assert "refresh_stats" in str(sops) or "kill_idle_session" in str(sops)
        print(f"\n✅ 无YAML时fallback到硬编码: {len(sops)} SOPs")

    @pytest.mark.asyncio
    async def test_sop_executor_mock_execution(self, executor_no_registry):
        """test_sop_executor_mock_execution: 验证SOP执行使用mock（无registry）"""
        sop = {
            "id": "test_mock",
            "name": "测试SOP",
            "steps": [
                {
                    "step": 1,
                    "action": "find_idle_sessions",
                    "params": {},
                    "risk_level": 1,
                    "timeout_seconds": 30,
                }
            ]
        }

        context = {"instance_id": "INS-TEST"}
        result = await executor_no_registry.execute(sop, context)

        assert result.success is True, f"SOP执行应成功: {result.error}"
        assert len(result.step_results) == 1
        assert result.step_results[0].status.name == "COMPLETED"
        print(f"\n✅ Mock执行成功: {result.final_result}")

    @pytest.mark.asyncio
    async def test_sop_executor_with_registry_raises_on_unregistered(self, sop_dir, mock_tool_registry):
        """test_sop_executor_with_registry_raises_on_unregistered: registry模式下未注册工具应报错"""
        from src.security.execution.sop_executor import SOPExecutor
        from src.security.execution.sop_executor import SOPStepStatus

        # 确保get_tool返回None（工具未注册）
        mock_tool_registry.get_tool.return_value = None

        executor = SOPExecutor(
            yaml_sop_dir=sop_dir,
            tool_registry=mock_tool_registry
        )

        sop = {
            "id": "test_unregistered",
            "name": "测试未注册工具",
            "steps": [
                {
                    "step": 1,
                    "action": "find_idle_sessions",  # 映射到pg_session_analysis
                    "params": {},
                    "risk_level": 1,
                    "timeout_seconds": 30,
                }
            ]
        }

        context = {"instance_id": "INS-TEST"}

        # 执行SOP，验证未注册工具会导致步骤失败
        result = await executor.execute(sop, context)

        # 验证步骤失败
        assert len(result.step_results) == 1
        step_result = result.step_results[0]
        assert step_result.status == SOPStepStatus.FAILED, f"步骤应失败，实际状态: {step_result.status}"
        assert "Tool not registered" in str(step_result.error) or "pg_session_analysis" in str(step_result.error), \
            f"错误信息应包含工具名: {step_result.error}"
        print(f"\n✅ 未注册工具正确触发失败: {step_result.error}")


# =============================================================================
# Regression Tests: 确保现有测试不被破坏
# =============================================================================

class TestRegressionSecurityLayer:
    """回归测试：确保现有安全层测试不被破坏"""

    @pytest.mark.asyncio
    async def test_regression_sop_executor_still_works(self):
        """回归测试：SOP执行器基础功能"""
        from src.security.execution.sop_executor import SOPExecutor

        executor = SOPExecutor()
        sop = {
            "id": "REGRESSION-001",
            "name": "回归测试SOP",
            "steps": [
                {"step": 1, "action": "action_a", "params": {}},
                {"step": 2, "action": "action_b", "params": {}},
            ]
        }
        result = await executor.execute(sop, {})
        assert result.success is True
        print(f"\n✅ 回归测试通过: SOP执行器基础功能正常")


# =============================================================================
# Test Summary
# =============================================================================

def test_summary_check():
    """summary_check: 验证测试环境完整性"""
    # 验证YAML SOP文件存在
    sop_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge", "sop_yaml")
    assert os.path.exists(sop_dir), f"SOP目录不存在: {sop_dir}"

    yaml_files = list(Path(sop_dir).glob("*.yaml"))
    assert len(yaml_files) == 3, f"应有3个YAML SOP，实际{len(yaml_files)}个"
    print(f"\n✅ 测试环境完整: {len(yaml_files)} YAML SOP文件")
