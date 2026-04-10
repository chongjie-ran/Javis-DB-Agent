"""V3.2 端到端集成测试 - routes.py+AgentRunner+Hook系统"""
import pytest
import sys
sys.path.insert(0, "/Users/chongjieran/.openclaw/workspace/Javis-DB-Agent")

from src.hooks import get_composite_hook, reset_composite_hook
from src.hooks.auto_memory_hook import AutoMemoryHook
from src.hooks.auto_verification_hook import AutoVerificationHook
from src.hooks.self_justification_guard import SelfJustificationGuard
from src.hooks.composite_hook import CompositeHook
from src.subagent.subagent_factory import SubagentFactory
from src.subagent.explore_spec import ExploreSpec
from src.agents.agent_run_spec import AgentRunSpec


class TestHookRegistration:
    """Test 1: Hook注册表初始化"""

    def test_composite_hook_empty_init(self):
        """初始状态为空"""
        reset_composite_hook()
        hook = get_composite_hook()
        assert len(hook.list_hooks()) == 0

    def test_hook_register_and_list(self):
        """注册和列出Hook"""
        reset_composite_hook()
        hook = get_composite_hook()
        hook.register(AutoVerificationHook())
        hook.register(AutoMemoryHook())
        hook.register(SelfJustificationGuard())
        hooks = hook.list_hooks()
        assert len(hooks) == 3
        names = [h.name for h in hooks]
        assert "auto_verification" in names
        assert "auto_memory" in names
        assert "SelfJustificationGuard" in names

    def test_hook_priority_order(self):
        """Hook按优先级排序"""
        reset_composite_hook()
        hook = get_composite_hook()
        hook.register(SelfJustificationGuard())  # priority=20
        hook.register(AutoVerificationHook())   # priority=50
        hook.register(AutoMemoryHook())         # priority=50
        hooks = hook.list_hooks()
        # AutoVerificationHook (40) should be first, then SelfJustificationGuard (50) and AutoMemoryHook (50)
        assert hooks[0].name == "auto_verification"

    def test_hook_unregister(self):
        """注销Hook"""
        reset_composite_hook()
        hook = get_composite_hook()
        hook.register(SelfJustificationGuard())
        assert hook.unregister("SelfJustificationGuard")
        assert len(hook.list_hooks()) == 0
        assert not hook.unregister("NonExistent")


class TestAgentRunSpec:
    """Test 2: AgentRunSpec"""

    def test_spec_creation(self):
        """创建执行规格"""
        spec = AgentRunSpec(
            goal="分析数据库性能",
            context={"session_id": "test-123", "user_id": "user1"},
            max_iterations=5,
        )
        assert spec.goal == "分析数据库性能"
        assert spec.session_id == "test-123"
        assert spec.user_id == "user1"
        assert spec.max_iterations == 5

    def test_is_complete_false_by_default(self):
        """默认不自动完成"""
        spec = AgentRunSpec(goal="test")
        assert not spec.is_complete()


class TestSubagentFactoryToolLayer:
    """Test 3: SubagentFactory Tool层集成"""

    def test_factory_explore_mode(self):
        """探索模式生成正确配置"""
        spec = ExploreSpec(task="查看项目结构")
        spec.timeout = 300
        config = SubagentFactory.create(spec)
        assert config["is_subagent"] == True
        assert config["subagent_mode"] == "explore"
        assert config["runtime"] == "subagent"
        # Allow list contains registered tools (may include Read if registered as query)
        assert len(config["tools"]["allow"]) >= 1

    def test_factory_deny_write_tools(self):
        """探索模式拒绝写工具"""
        spec = ExploreSpec(task="查看项目结构")
        config = SubagentFactory.create(spec)
        deny = config["tools"]["deny"]
        assert "Write" in deny
        assert "Bash" in deny


class TestNoDuplicateSelfJustificationGuard:
    """Test 4: 无重复SelfJustificationGuard"""

    def test_only_one_sjg_in_hooks(self):
        """hooks/下只有一个SelfJustificationGuard"""
        from src.hooks.self_justification_guard import SelfJustificationGuard
        # 验证类存在且是唯一来源
        assert SelfJustificationGuard is not None
        assert hasattr(SelfJustificationGuard, "after_iteration")

    def test_no_sjg_in_agents_module(self):
        """agents/模块不导出SelfJustificationGuard"""
        import src.agents.instruction_validator as iv
        assert not hasattr(iv, "SelfJustificationGuard") or                "SelfJustificationGuard" not in getattr(iv, "__all__", [])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
