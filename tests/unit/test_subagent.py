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
        assert config["tools"]["allow"] == ["read", "exec", "web_search"]
        assert config["tools"]["deny"] == ["write", "edit", "delete"]
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
        assert config["tools"]["allow"] == ["read", "write", "exec"]
        assert config["tools"]["deny"] == []
        assert config["memory"] is True
        assert config["is_subagent"] is True
        assert config["subagent_mode"] == "execute"

    def test_explore_restricts_write_tools(self):
        spec = ExploreSpec(task="read only")
        config = SubagentFactory.create(spec)
        assert "write" in config["tools"]["deny"]
        assert "edit" in config["tools"]["deny"]
        assert "delete" in config["tools"]["deny"]

    def test_execute_allows_write_tools(self):
        spec = ExecuteSpec(task="modify")
        config = SubagentFactory.create(spec)
        assert "write" in config["tools"]["allow"]
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
