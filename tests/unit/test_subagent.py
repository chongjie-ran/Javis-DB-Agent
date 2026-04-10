"""
Phase 6 测试：Subagent双模式
验证 ExploreSpec、ExecuteSpec、SubagentFactory 和 SubagentModeHook
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.subagent.subagent_spec import SubagentMode, SubagentSpec
from src.subagent.explore_spec import ExploreSpec
from src.subagent.execute_spec import ExecuteSpec
from src.subagent.plan_spec import PlanSpec
from src.subagent.subagent_factory import SubagentFactory
from src.subagent.helpers import quick_explore, quick_execute


class TestSubagentMode:
    """SubagentMode枚举测试"""

    def test_explore_mode_value(self):
        assert SubagentMode.EXPLORE.value == "explore"

    def test_execute_mode_value(self):
        assert SubagentMode.EXECUTE.value == "execute"


class TestExploreSpec:
    """ExploreSpec测试"""

    def test_default_values(self):
        spec = ExploreSpec(task="find config files")
        assert spec.task == "find config files"
        assert spec.timeout == 300  # 5分钟
        assert spec.max_cost == 30000
        assert spec.mode == SubagentMode.EXPLORE

    def test_custom_timeout(self):
        spec = ExploreSpec(task="explore", timeout=180)
        assert spec.timeout == 180

    def test_get_instructions_contains_explore(self):
        spec = ExploreSpec(task="find all JSON files")
        instructions = spec.get_instructions()
        assert "探索模式" in instructions
        assert "find all JSON files" in instructions
        assert "只读" in instructions

    def test_validate_result_valid(self):
        spec = ExploreSpec(task="test")
        assert spec.validate_result("some result") is True
        assert spec.validate_result(["item1", "item2"]) is True

    def test_validate_result_invalid(self):
        spec = ExploreSpec(task="test")
        assert spec.validate_result(None) is False
        assert spec.validate_result("") is False


class TestExecuteSpec:
    """ExecuteSpec测试"""

    def test_default_values(self):
        spec = ExecuteSpec(task="update config")
        assert spec.task == "update config"
        assert spec.timeout == 3600  # 60分钟
        assert spec.max_cost == 100000
        assert spec.mode == SubagentMode.EXECUTE

    def test_with_target_files(self):
        spec = ExecuteSpec(
            task="fix auth bug",
            target_files=["src/auth/login.py", "src/auth/session.py"],
            expected_outcome="token refresh works",
            verification_method="pytest tests/auth/",
        )
        assert spec.target_files == ["src/auth/login.py", "src/auth/session.py"]
        assert spec.expected_outcome == "token refresh works"
        assert spec.verification_method == "pytest tests/auth/"

    def test_get_instructions_contains_execute(self):
        spec = ExecuteSpec(task="update config", target_files=["config.yaml"])
        instructions = spec.get_instructions()
        assert "执行模式" in instructions
        assert "update config" in instructions
        assert "config.yaml" in instructions

    def test_validate_result_with_expected_outcome(self):
        spec = ExecuteSpec(task="fix", expected_outcome="test passed")
        assert spec.validate_result("test passed - all good") is True
        assert spec.validate_result("something else") is False

    def test_validate_result_without_expected_outcome(self):
        spec = ExecuteSpec(task="fix")
        assert spec.validate_result("any result") is True


class TestSubagentFactory:
    """SubagentFactory测试"""

    def test_create_explore_config(self):
        spec = ExploreSpec(task="find files", timeout=300)
        config = SubagentFactory.create(spec)
        
        assert config["runtime"] == "subagent"
        assert config["mode"] == "run"
        assert config["runTimeoutSeconds"] == 300
        assert "探索模式" in config["task"]
        assert isinstance(config["tools"]["allow"], list)  # now from ToolRegistry
        assert config["tools"]["deny"] == ["Bash", "Write", "Edit", "Notebook"]
        assert config["memory"] is False
        assert config["is_subagent"] is True
        assert config["subagent_mode"] == "explore"

    def test_create_execute_config(self):
        spec = ExecuteSpec(task="update", timeout=3600)
        config = SubagentFactory.create(spec)
        
        assert config["runtime"] == "subagent"
        assert config["mode"] == "run"
        assert config["runTimeoutSeconds"] == 3600
        assert "执行模式" in config["task"]
        assert isinstance(config["tools"]["allow"], list)  # now from ToolRegistry
        assert config["tools"]["deny"] == []
        assert config["memory"] is True
        assert config["is_subagent"] is True
        assert config["subagent_mode"] == "execute"

    def test_explore_restricts_write_tools(self):
        spec = ExploreSpec(task="read only")
        config = SubagentFactory.create(spec)
        assert "Write" in config["tools"]["deny"]
        assert "Edit" in config["tools"]["deny"]
        assert "Notebook" in config["tools"]["deny"]

    def test_execute_allows_write_tools(self):
        spec = ExecuteSpec(task="modify")
        config = SubagentFactory.create(spec)
        assert "Write" in config["tools"]["allow"]
        assert config["tools"]["deny"] == []


class TestQuickHelpers:
    """快速启动辅助函数测试"""

    def test_quick_explore(self):
        spec = quick_explore("find all .py files")
        assert isinstance(spec, ExploreSpec)
        assert spec.task == "find all .py files"
        assert spec.mode == SubagentMode.EXPLORE
        assert spec.timeout == 300

    def test_quick_execute_minimal(self):
        spec = quick_execute(task="update config")
        assert isinstance(spec, ExecuteSpec)
        assert spec.task == "update config"
        assert spec.mode == SubagentMode.EXECUTE

    def test_quick_execute_full(self):
        spec = quick_execute(
            task="fix login",
            target_files=["auth.py"],
            expected_outcome="login works",
            verification="pytest auth_test.py",
        )
        assert spec.target_files == ["auth.py"]
        assert spec.expected_outcome == "login works"
        assert spec.verification_method == "pytest auth_test.py"


class TestSubagentModeHook:
    """SubagentModeHook测试"""

    def test_hook_import(self):
        from src.subagent.hooks import SubagentModeHook
        from src.hooks.hook import AgentHook
        assert issubclass(SubagentModeHook, AgentHook)

    def test_hook_has_before_iteration(self):
        from src.subagent.hooks import SubagentModeHook
        assert hasattr(SubagentModeHook, "before_iteration")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestExecuteSpecVerificationV2:
    """ExecuteSpec V2 验证机制测试"""

    def test_mandatory_verification_default_true(self):
        """验证默认强制开启"""
        spec = ExecuteSpec(task="fix bug")
        assert spec.mandatory_verification is True

    def test_mandatory_verification_can_disable(self):
        """验证可关闭强制模式"""
        spec = ExecuteSpec(task="fix bug", mandatory_verification=False)
        assert spec.mandatory_verification is False

    def test_has_verification_true(self):
        """has_verification: 有验证方法"""
        spec = ExecuteSpec(task="fix", verification_method="pytest")
        assert spec.has_verification() is True

    def test_has_verification_false(self):
        """has_verification: 无验证方法"""
        spec = ExecuteSpec(task="fix")
        assert spec.has_verification() is False

    def test_requires_verification_with_method(self):
        """requires_verification: 有验证方法时返回True"""
        spec = ExecuteSpec(task="fix", verification_method="pytest")
        assert spec.requires_verification() is True

    def test_requires_verification_mandatory(self):
        """requires_verification: 强制模式时返回True"""
        spec = ExecuteSpec(task="fix", mandatory_verification=True)
        assert spec.requires_verification() is True

    def test_requires_verification_false(self):
        """requires_verification: 无验证方法且未强制时返回False"""
        spec = ExecuteSpec(task="fix", mandatory_verification=False)
        assert spec.requires_verification() is False

    def test_instructions_contains_verification_priority(self):
        """指令包含验证优先标记"""
        spec = ExecuteSpec(
            task="fix bug",
            verification_method="pytest tests/",
            mandatory_verification=True
        )
        instructions = spec.get_instructions()
        assert "验证优先" in instructions
        assert "必须执行" in instructions
        assert "⚠️" in instructions

    def test_instructions_contains_output_format(self):
        """指令包含标准输出格式"""
        spec = ExecuteSpec(task="fix")
        instructions = spec.get_instructions()
        assert "## 完成的修改" in instructions
        assert "## 验证结果" in instructions
        assert "## 如未完成" in instructions


class TestPlanSpec:
    """PlanSpec 测试"""

    def test_plan_spec_default_values(self):
        spec = PlanSpec(task="analyze architecture")
        assert spec.task == "analyze architecture"
        assert spec.timeout == 600  # 10分钟
        assert spec.max_cost == 50000
        assert spec.mode == SubagentMode.EXPLORE  # 复用EXPLORE

    def test_plan_spec_instructions_contains_readonly(self):
        spec = PlanSpec(task="analyze code")
        instructions = spec.get_instructions()
        assert "只读模式" in instructions
        assert "禁止创建、修改、删除任何文件" in instructions

    def test_plan_spec_instructions_contains_structure(self):
        spec = PlanSpec(task="analyze architecture")
        instructions = spec.get_instructions()
        assert "## 1. 发现总结" in instructions
        assert "## 2. 代码结构" in instructions
        assert "## 5. 建议行动" in instructions

    def test_validate_result_with_required_sections(self):
        spec = PlanSpec(task="analyze")
        result = "发现总结：这是一个详细的架构分析\n代码结构：模块A依赖模块B\n建议行动：建议重构模块C"
        assert spec.validate_result(result) is True

    def test_validate_result_short_result(self):
        spec = PlanSpec(task="analyze")
        assert spec.validate_result("short") is False


class TestExploreSpecV2:
    """ExploreSpec V2 测试"""

    def test_explore_instructions_contains_readonly(self):
        spec = ExploreSpec(task="find files")
        instructions = spec.get_instructions()
        assert "只读模式" in instructions
        assert "禁止创建、修改、删除任何文件" in instructions

    def test_explore_instructions_contains_strategy(self):
        spec = ExploreSpec(task="find files")
        instructions = spec.get_instructions()
        assert "3次搜索失败后换策略" in instructions

    def test_explore_instructions_contains_report_format(self):
        spec = ExploreSpec(task="find files")
        instructions = spec.get_instructions()
        assert "## 找到的信息" in instructions
        assert "## 未能找到的信息" in instructions
        assert "## 建议的下一步" in instructions


class TestSubagentFactoryV2:
    """SubagentFactory V2 测试"""

    def test_create_plan_config(self):
        spec = PlanSpec(task="analyze", timeout=600)
        config = SubagentFactory.create(spec)
        
        assert config["runtime"] == "subagent"
        assert config["mode"] == "run"
        assert config["subagent_mode"] == "plan"
        assert "Bash" in config["tools"]["deny"]
        assert "web_search" in config["tools"]["deny"]

    def test_explore_restricts_bash(self):
        spec = ExploreSpec(task="explore")
        config = SubagentFactory.create(spec)
        assert "Bash" in config["tools"]["deny"]
