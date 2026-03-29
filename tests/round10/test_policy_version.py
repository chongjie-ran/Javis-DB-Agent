"""测试 P1: 策略版本管理"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


class TestPolicyVersionTracking:
    """测试策略版本追踪"""

    def setup_method(self):
        """每个测试前重置策略引擎"""
        from src.gateway.policy_engine import get_policy_engine, _policy_engine
        # 重置全局单例
        import src.gateway.policy_engine as pe_module
        pe_module._policy_engine = None
        self.engine = get_policy_engine()

    def teardown_method(self):
        """测试后重置"""
        import src.gateway.policy_engine as pe_module
        pe_module._policy_engine = None

    def test_initial_version(self):
        """测试初始版本为1"""
        assert self.engine.get_version() == 1

    def test_version_history_initial(self):
        """测试初始版本历史"""
        history = self.engine.get_version_history()
        assert len(history) == 1
        assert history[0]["version"] == 1
        assert history[0]["change"] == "initial"

    def test_set_approval_config_increments_version(self):
        """测试修改审批配置会增加版本号"""
        old_version = self.engine.get_version()
        self.engine.set_approval_config(l4=False, l5=False)
        
        assert self.engine.get_version() == old_version + 1

    def test_set_approval_config_same_value_no_increment(self):
        """测试相同配置不会增加版本号"""
        self.engine.set_approval_config(l4=True, l5=True)
        v1 = self.engine.get_version()
        self.engine.set_approval_config(l4=True, l5=True)
        v2 = self.engine.get_version()
        
        assert v1 == v2

    def test_set_approval_config_changes_version_history(self):
        """测试配置变更记录到版本历史"""
        self.engine.set_approval_config(l4=False, l5=True)
        
        history = self.engine.get_version_history()
        last = history[-1]
        
        assert last["version"] == 2
        assert "l4_required" in last
        assert last["l4_required"] is False
        assert last["l5_dual_required"] is True

    def test_add_rule_increments_version(self):
        """测试添加规则会增加版本号"""
        old_version = self.engine.get_version()
        
        def my_rule(context, action, risk_level):
            from src.gateway.policy_engine import PolicyResult
            return PolicyResult(allowed=True)
        
        self.engine.add_rule(my_rule)
        
        assert self.engine.get_version() == old_version + 1

    def test_add_rule_records_in_history(self):
        """测试添加规则记录到版本历史"""
        def my_diagnostic_rule(context, action, risk_level):
            from src.gateway.policy_engine import PolicyResult
            return PolicyResult(allowed=True)
        
        self.engine.add_rule(my_diagnostic_rule)
        
        history = self.engine.get_version_history()
        last = history[-1]
        
        assert "added_custom_rule" in last["change"]
        assert "my_diagnostic_rule" in last["change"]

    def test_version_history_respects_limit(self):
        """测试版本历史限制"""
        for i in range(60):
            self.engine.set_approval_config(l4=(i % 2 == 0), l5=True)
        
        history = self.engine.get_version_history(limit=50)
        assert len(history) == 50


class TestPolicyAuditLogging:
    """测试策略变更审计日志"""

    def setup_method(self):
        """每个测试前重置"""
        import src.gateway.policy_engine as pe_module
        pe_module._policy_engine = None
        import src.gateway.audit as audit_module
        audit_module._audit_logger = None

    def teardown_method(self):
        import src.gateway.policy_engine as pe_module
        pe_module._policy_engine = None
        import src.gateway.audit as audit_module
        audit_module._audit_logger = None

    def test_policy_change_logged_to_audit(self):
        """测试策略变更记录到审计日志"""
        from src.gateway.policy_engine import get_policy_engine
        from src.gateway.audit import get_audit_logger, AuditAction
        
        engine = get_policy_engine()
        audit = get_audit_logger()
        
        # 清空现有日志用于测试
        initial_count = len(audit._logs)
        
        # 触发配置变更
        engine.set_approval_config(l4=False, l5=True)
        
        # 检查审计日志
        policy_logs = [
            log for log in audit._logs
            if (log.action.value if hasattr(log.action, 'value') else log.action) == "policy.change"
        ]
        
        assert len(policy_logs) >= 1
        last_log = policy_logs[-1]
        assert last_log.metadata.get("l4_required", {}).get("new") is False
        assert last_log.metadata.get("l5_dual_required", {}).get("new") is True

    def test_policy_change_audit_contains_version(self):
        """测试策略变更审计包含版本信息"""
        from src.gateway.policy_engine import get_policy_engine
        from src.gateway.audit import get_audit_logger
        
        engine = get_policy_engine()
        audit = get_audit_logger()
        
        initial_version = engine.get_version()
        engine.set_approval_config(l4=True, l5=False)
        
        policy_logs = [
            log for log in audit._logs
            if (log.action.value if hasattr(log.action, 'value') else log.action) == "policy.change"
        ]
        
        assert len(policy_logs) >= 1
        assert policy_logs[-1].metadata.get("new_version") == initial_version + 1


class TestPolicyVersionAPI:
    """测试策略版本API"""

    def test_policy_version_in_metrics(self):
        """测试策略版本在metrics中"""
        from src.api.metrics import get_metrics
        
        metrics = get_metrics()
        metrics.reset()
        
        # 模拟版本更新
        from src.gateway.policy_engine import get_policy_engine
        import src.gateway.policy_engine as pe_module
        pe_module._policy_engine = None
        engine = get_policy_engine()
        engine.set_approval_config(l4=False, l5=False)
        
        metrics.set_policy_version(engine.get_version())
        
        assert metrics.gauge("policy_version").get() == 2.0

    def test_policy_changes_counter_in_metrics(self):
        """测试策略变更计数在metrics中"""
        from src.api.metrics import get_metrics
        
        metrics = get_metrics()
        metrics.reset()
        
        metrics.inc_policy_changes()
        metrics.inc_policy_changes()
        
        assert metrics.counter("policy_changes_total").get() == 2


class TestAuditActionPolicyChange:
    """测试审计动作类型"""

    def test_policy_change_action_exists(self):
        """测试POLICY_CHANGE动作存在"""
        from src.gateway.audit import AuditAction
        
        assert hasattr(AuditAction, "POLICY_CHANGE")
        assert AuditAction.POLICY_CHANGE.value == "policy.change"

    def test_all_audit_actions_valid(self):
        """测试所有审计动作有效"""
        from src.gateway.audit import AuditAction
        
        for action in AuditAction:
            assert action.value
            assert isinstance(action.value, str)
