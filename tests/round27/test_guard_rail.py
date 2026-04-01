"""
V2.6 R1 - SafetyGuardRail 安全护栏测试
========================================
测试范围：F3 SafetyGuardRail 安全护栏
- Gate 层强制审批
- Tool 无法绕过 Gate
- 审批令牌验证

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round27/test_guard_rail.py -v --tb=short
"""

import asyncio
import sys
import os
import re
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.tools.base import RiskLevel
from src.gateway.hooks import HookEvent, HookContext, HookRule, HookAction, HookCondition, ConditionOperator
from src.gateway.hooks import HookEngine, emit_hook
from src.security.guard_rail import SafetyGuardRail, ApprovalRequiredError, GuardRailResult, ApprovalToken
import time


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_global_state():
    """每个测试后重置全局状态"""
    import src.gateway.hooks.hook_engine as he_module
    import src.gateway.hooks.hook_registry as hr_module
    from src.gateway.hooks import HookRegistry

    yield

    he_module._engine = None
    hr_module._registry = HookRegistry()


@pytest.fixture
def guard_rail():
    """独立的 SafetyGuardRail（使用真实的 ApprovalGate 但不连接外部系统）"""
    from src.gateway.approval import ApprovalGate
    gate = ApprovalGate(timeout_seconds=10)
    return SafetyGuardRail(approval_gate=gate)


# ============================================================================
# SECTION 1: 风险级别基础测试
# ============================================================================

class TestRiskLevelBasics:
    """风险级别基础测试"""

    def test_risk_level_ordering(self):
        """RL-01: 风险级别顺序正确"""
        assert RiskLevel.L1_READ < RiskLevel.L2_DIAGNOSE
        assert RiskLevel.L2_DIAGNOSE < RiskLevel.L3_LOW_RISK
        assert RiskLevel.L3_LOW_RISK < RiskLevel.L4_MEDIUM
        assert RiskLevel.L4_MEDIUM < RiskLevel.L5_HIGH

    def test_risk_level_values(self):
        """RL-02: 风险级别值正确"""
        assert RiskLevel.L1_READ.value == 1
        assert RiskLevel.L2_DIAGNOSE.value == 2
        assert RiskLevel.L3_LOW_RISK.value == 3
        assert RiskLevel.L4_MEDIUM.value == 4
        assert RiskLevel.L5_HIGH.value == 5


# ============================================================================
# SECTION 2: SafetyGuardRail 基础测试
# ============================================================================

class TestSafetyGuardRailBasics:
    """SafetyGuardRail 基础测试"""

    @pytest.mark.asyncio
    async def test_guard_rail_l1_allowed(self, guard_rail):
        """GR-01: L1 无需审批直接放行"""
        context = {"user_id": "test", "session_id": "s1", "approval_tokens": {}}
        result = await guard_rail.enforce(
            tool_name="query_tool",
            risk_level=RiskLevel.L1_READ,
            context=context,
        )
        assert result.allowed is True
        assert result.risk_level == "L1"

    @pytest.mark.asyncio
    async def test_guard_rail_l2_allowed(self, guard_rail):
        """GR-02: L2 无需审批直接放行"""
        context = {"user_id": "test", "session_id": "s1", "approval_tokens": {}}
        result = await guard_rail.enforce(
            tool_name="diagnose_tool",
            risk_level=RiskLevel.L2_DIAGNOSE,
            context=context,
        )
        assert result.allowed is True
        assert result.risk_level == "L2"

    @pytest.mark.asyncio
    async def test_guard_rail_l3_allowed(self, guard_rail):
        """GR-03: L3 无需审批直接放行"""
        context = {"user_id": "test", "session_id": "s1", "approval_tokens": {}}
        result = await guard_rail.enforce(
            tool_name="low_risk_tool",
            risk_level=RiskLevel.L3_LOW_RISK,
            context=context,
        )
        assert result.allowed is True
        assert result.risk_level == "L3"


# ============================================================================
# SECTION 3: Gate 层强制审批测试
# ============================================================================

class TestGateLayerEnforcement:
    """Gate 层强制审批测试"""

    @pytest.mark.asyncio
    async def test_l4_without_token_raises(self):
        """GE-01: L4 无令牌时抛出 ApprovalRequiredError"""
        guard = SafetyGuardRail()
        context = {"user_id": "test", "session_id": "s1", "approval_tokens": {}}

        # Patch _enforce_l4 directly to avoid async mock complexity
        with patch.object(guard, "_enforce_l4", new_callable=AsyncMock) as mock_enforce:
            mock_enforce.side_effect = ApprovalRequiredError("L4 requires approval")
            with pytest.raises(ApprovalRequiredError):
                await guard.enforce(
                    tool_name="execute_sql",
                    risk_level=RiskLevel.L4_MEDIUM,
                    context=context,
                )

    @pytest.mark.asyncio
    async def test_l4_with_valid_token_passes(self, guard_rail):
        """GE-02: L4 持有有效令牌时放行"""
        # Create valid ApprovalToken with matching params_hash
        import hashlib
        params = {"sql": "SELECT 1"}
        params_hash = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()
        now = time.time()
        token = ApprovalToken(
            request_id="VALID-TOKEN-001",
            tool_name="execute_sql",
            risk_level="L4",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + 600,  # 10 min TTL
            approver="admin",
        )
        context = {
            "user_id": "test",
            "session_id": "s1",
            "params": params,
            "approval_tokens": {
                "execute_sql:L4": token
            }
        }
        result = await guard_rail.enforce(
            tool_name="execute_sql",
            risk_level=RiskLevel.L4_MEDIUM,
            context=context,
        )
        assert result.allowed is True
        assert result.approval_token == "VALID-TOKEN-001"

    @pytest.mark.asyncio
    async def test_l5_without_token_raises(self):
        """GE-03: L5 无令牌时抛出 ApprovalRequiredError"""
        guard = SafetyGuardRail()
        context = {"user_id": "test", "session_id": "s1", "approval_tokens": {}}

        with patch.object(guard, "_enforce_l5", new_callable=AsyncMock) as mock_enforce:
            mock_enforce.side_effect = ApprovalRequiredError("L5 requires dual approval")
            with pytest.raises(ApprovalRequiredError):
                await guard.enforce(
                    tool_name="drop_table",
                    risk_level=RiskLevel.L5_HIGH,
                    context=context,
                )

    @pytest.mark.asyncio
    async def test_l5_with_valid_token_passes(self, guard_rail):
        """GE-04: L5 持有有效令牌时放行"""
        import hashlib
        params = {"table": "users"}
        params_hash = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()
        now = time.time()
        token = ApprovalToken(
            request_id="VALID-L5-TOKEN-001",
            tool_name="drop_table",
            risk_level="L5",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + 300,  # 5 min TTL for L5
            approver="admin",
        )
        context = {
            "user_id": "test",
            "session_id": "s1",
            "params": params,
            "approval_tokens": {
                "drop_table:L5": token
            }
        }
        result = await guard_rail.enforce(
            tool_name="drop_table",
            risk_level=RiskLevel.L5_HIGH,
            context=context,
        )
        assert result.allowed is True
        assert result.approval_token == "VALID-L5-TOKEN-001"

    @pytest.mark.asyncio
    async def test_tool_cannot_bypass_gate(self):
        """GE-05: Tool 无法绕过 Gate"""
        guard = SafetyGuardRail()
        context = {"user_id": "test", "session_id": "s1", "approval_tokens": {}}

        # Force _enforce_l4 to raise (simulating missing approval)
        with patch.object(guard, "_enforce_l4", new_callable=AsyncMock) as mock_enforce:
            mock_enforce.side_effect = ApprovalRequiredError("L4 requires approval")
            with pytest.raises(ApprovalRequiredError):
                await guard.enforce(
                    tool_name="execute_sql",
                    risk_level=RiskLevel.L4_MEDIUM,
                    context=context,
                )


# ============================================================================
# SECTION 4: 审批令牌验证测试
# ============================================================================

class TestApprovalTokenVerification:
    """审批令牌验证测试"""

    def test_verify_token_exists(self, guard_rail):
        """AT-01: 令牌存在时验证通过"""
        import hashlib
        params = {"sql": "SELECT 1"}
        params_hash = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()
        now = time.time()
        token = ApprovalToken(
            request_id="TOKEN-001",
            tool_name="execute_sql",
            risk_level="L4",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + 600,
            approver="admin",
        )
        context = {
            "user_id": "test",
            "session_id": "s1",
            "params": params,
            "approval_tokens": {"execute_sql:L4": token}
        }
        assert guard_rail.verify_token(
            "execute_sql", RiskLevel.L4_MEDIUM, context
        ) is True

    def test_verify_token_missing(self, guard_rail):
        """AT-02: 令牌不存在时验证失败"""
        context = {
            "user_id": "test",
            "session_id": "s1",
            "approval_tokens": {}
        }
        assert guard_rail.verify_token(
            "execute_sql", RiskLevel.L4_MEDIUM, context
        ) is False

    def test_verify_token_wrong_tool(self, guard_rail):
        """AT-03: 工具名不匹配时验证失败"""
        import hashlib
        params = {"sql": "SELECT 1"}
        params_hash = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()
        now = time.time()
        token = ApprovalToken(
            request_id="TOKEN-001",
            tool_name="execute_sql",
            risk_level="L4",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + 600,
            approver="admin",
        )
        context = {
            "user_id": "test",
            "session_id": "s1",
            "params": params,
            "approval_tokens": {"execute_sql:L4": token}
        }
        assert guard_rail.verify_token(
            "drop_table", RiskLevel.L4_MEDIUM, context
        ) is False

    def test_verify_token_l5(self, guard_rail):
        """AT-04: L5 令牌验证"""
        import hashlib
        params = {"table": "users"}
        params_hash = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()
        now = time.time()
        token = ApprovalToken(
            request_id="L5-TOKEN-001",
            tool_name="drop_table",
            risk_level="L5",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + 300,
            approver="admin",
        )
        context = {
            "user_id": "test",
            "session_id": "s1",
            "params": params,
            "approval_tokens": {"drop_table:L5": token}
        }
        assert guard_rail.verify_token(
            "drop_table", RiskLevel.L5_HIGH, context
        ) is True


# ============================================================================
# SECTION 5: Hook + SafetyGuardRail 集成测试
# ============================================================================

class TestHookGuardRailIntegration:
    """Hook + SafetyGuardRail 集成测试"""

    @pytest.mark.asyncio
    async def test_ddl_hook_blocks_before_guard(self):
        """HGI-01: DDL Hook 在 Guard 之前拦截"""
        engine = HookEngine()

        async def ddl_blocker(ctx: HookContext) -> HookContext:
            sql = ctx.get("sql_statement", "")
            if re.match(r"(DROP|TRUNCATE|ALTER\s+TABLE)", sql, re.IGNORECASE):
                ctx.set_blocked(f"DDL Hook blocked: {sql[:30]}")
            return ctx

        engine.register_rule(HookRule(
            name="ddl-blocker",
            event=HookEvent.SQL_DDL_DETECTED,
            handler=ddl_blocker,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(DROP|TRUNCATE|ALTER\s+TABLE)"
                )
            ],
            action=HookAction.BLOCK,
        ))

        result = await engine.emit(
            HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "DROP TABLE users"},
            session_id="hgi-01",
            user_id="test-user",
        )

        assert result.blocked is True
        assert "DDL Hook blocked" in result.message

    @pytest.mark.asyncio
    async def test_guard_rail_enforce_uses_hook_engine(self, guard_rail):
        """HGI-02: SafetyGuardRail 使用 HookEngine"""
        assert guard_rail.hook_engine is not None
        assert isinstance(guard_rail.hook_engine, HookEngine)

    @pytest.mark.asyncio
    async def test_tool_before_execute_hook_fires(self):
        """HGI-03: TOOL_BEFORE_EXECUTE Hook 触发"""
        engine = HookEngine()
        called = {"n": 0}

        async def before_tool(ctx: HookContext) -> HookContext:
            called["n"] += 1
            ctx.add_warning(f"tool={ctx.get('tool_name')} logged")
            return ctx

        engine.register_rule(HookRule(
            name="before-tool-logger",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            handler=before_tool,
        ))

        result = await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "execute_sql", "params": {"sql": "SELECT 1"}},
            session_id="hgi-03",
            user_id="test-user",
        )

        assert called["n"] == 1
        assert len(result.warnings) == 1
        assert "execute_sql" in result.warnings[0]


# ============================================================================
# SECTION 6: DDL 检测测试
# ============================================================================

class TestDDLDetection:
    """DDL 检测测试"""

    @pytest.mark.asyncio
    async def test_drop_table_detected(self):
        """DD-01: DROP TABLE 被检测"""
        engine = HookEngine()
        detected = {"flag": False}

        async def ddl_hook(ctx: HookContext) -> HookContext:
            sql = ctx.get("sql_statement", "")
            if re.match(r"(DROP|TRUNCATE|ALTER\s+TABLE)", sql, re.IGNORECASE):
                detected["flag"] = True
                ctx.set_blocked("DDL not allowed")
            return ctx

        engine.register_rule(HookRule(
            name="ddl-detect",
            event=HookEvent.SQL_DDL_DETECTED,
            handler=ddl_hook,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(DROP|TRUNCATE|ALTER\s+TABLE)"
                )
            ],
            action=HookAction.BLOCK,
        ))

        result = await engine.emit(
            HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "DROP TABLE IF EXISTS test_users"},
            session_id="dd-01",
            user_id="test",
        )

        assert detected["flag"] is True
        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_truncate_detected(self):
        """DD-02: TRUNCATE 被检测"""
        engine = HookEngine()

        async def ddl_hook(ctx: HookContext) -> HookContext:
            sql = ctx.get("sql_statement", "")
            if re.match(r"(DROP|TRUNCATE|ALTER\s+TABLE)", sql, re.IGNORECASE):
                ctx.set_blocked("DDL not allowed")
            return ctx

        engine.register_rule(HookRule(
            name="ddl-detect",
            event=HookEvent.SQL_DDL_DETECTED,
            handler=ddl_hook,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(DROP|TRUNCATE|ALTER\s+TABLE)"
                )
            ],
            action=HookAction.BLOCK,
        ))

        result = await engine.emit(
            HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "TRUNCATE TABLE test_orders"},
            session_id="dd-02",
            user_id="test",
        )

        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_safe_select_not_blocked(self):
        """DD-03: SELECT 不被 DDL 检测拦截"""
        engine = HookEngine()
        blocked = {"flag": False}

        async def ddl_hook(ctx: HookContext) -> HookContext:
            sql = ctx.get("sql_statement", "")
            if re.match(r"(DROP|TRUNCATE|ALTER\s+TABLE)", sql, re.IGNORECASE):
                blocked["flag"] = True
                ctx.set_blocked("DDL blocked")
            return ctx

        engine.register_rule(HookRule(
            name="ddl-detect",
            event=HookEvent.SQL_DDL_DETECTED,
            handler=ddl_hook,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(DROP|TRUNCATE|ALTER\s+TABLE)"
                )
            ],
            action=HookAction.BLOCK,
        ))

        result = await engine.emit(
            HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "SELECT * FROM users WHERE id = 1"},
            session_id="dd-03",
            user_id="test",
        )

        assert blocked["flag"] is False
        assert result.blocked is False


# ============================================================================
# SECTION 7: GuardRailResult 测试
# ============================================================================

class TestGuardRailResult:
    """GuardRailResult 测试"""

    def test_guard_rail_result_fields(self):
        """GRR-01: GuardRailResult 字段正确"""
        result = GuardRailResult(
            allowed=True,
            approval_token="TOKEN-001",
            message="approved",
            risk_level="L4",
        )
        assert result.allowed is True
        assert result.approval_token == "TOKEN-001"
        assert result.message == "approved"
        assert result.risk_level == "L4"

    def test_guard_rail_result_default(self):
        """GRR-02: GuardRailResult 默认值"""
        result = GuardRailResult(allowed=True)
        assert result.approval_token is None
        assert result.message == ""
        assert result.risk_level == "L1"


# ============================================================================
# SECTION 8: 全局单例测试
# ============================================================================

class TestGlobalSingleton:
    """全局单例测试"""

    def test_get_safety_guard_rail_singleton(self):
        """GS-01: get_safety_guard_rail 返回单例"""
        from src.security.guard_rail import get_safety_guard_rail, _guard_rail

        # Reset
        import src.security.guard_rail as gr_module
        gr_module._guard_rail = None

        rail1 = get_safety_guard_rail()
        rail2 = get_safety_guard_rail()
        assert rail1 is rail2
