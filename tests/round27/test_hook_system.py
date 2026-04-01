"""
V2.6 R1 - Hook 事件驱动系统测试
================================
测试范围：F1 Hook 事件驱动系统
- HookEngine 基础功能
- HookEvent 各类事件
- RuleEngine 规则评估

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round27/test_hook_system.py -v --tb=short
"""

import asyncio
import sys
import os
import time
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.hooks import (
    HookEvent, HookContext, HookRule, HookAction, ConditionOperator,
    HookCondition, HookRegistry, RuleEngine, HookEngine, HookResult,
    get_hook_engine, emit_hook,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_global_state():
    """每个测试后重置全局状态"""
    import src.gateway.hooks.hook_engine as he_module
    import src.gateway.hooks.hook_registry as hr_module

    # 重置前先清理
    yield

    # 重置全局注册表和引擎
    he_module._engine = None
    hr_module._registry = HookRegistry()


@pytest.fixture
def fresh_registry():
    """独立的 HookRegistry（避免全局状态污染）"""
    return HookRegistry()


@pytest.fixture
def fresh_engine(fresh_registry):
    """独立的 HookEngine"""
    return HookEngine(registry=fresh_registry)


@pytest.fixture
def hook_context():
    """标准 HookContext"""
    return HookContext(
        event=HookEvent.TOOL_BEFORE_EXECUTE,
        payload={
            "tool_name": "execute_sql",
            "params": {"sql": "SELECT 1"},
            "risk_level": 1,
        },
        session_id="hook-test-session-001",
        user_id="test-user"
    )


# ============================================================================
# SECTION 1: HookEvent 枚举测试
# ============================================================================

class TestHookEventEnum:
    """HookEvent 枚举定义测试"""

    def test_hook_event_values(self):
        """HE-01: 所有事件值正确"""
        assert HookEvent.TOOL_BEFORE_EXECUTE.value == "tool:before_execute"
        assert HookEvent.TOOL_AFTER_EXECUTE.value == "tool:after_execute"
        assert HookEvent.TOOL_ERROR.value == "tool:error"
        assert HookEvent.SQL_BEFORE_GUARD.value == "sql:before_guard"
        assert HookEvent.SQL_AFTER_GUARD.value == "sql:after_guard"
        assert HookEvent.SQL_DDL_DETECTED.value == "sql:ddl_detected"
        assert HookEvent.APPROVAL_REQUESTED.value == "approval:requested"
        assert HookEvent.APPROVAL_APPROVED.value == "approval:approved"
        assert HookEvent.APPROVAL_REJECTED.value == "approval:rejected"
        assert HookEvent.AGENT_BEFORE_INVOKE.value == "agent:before_invoke"
        assert HookEvent.AGENT_AFTER_INVOKE.value == "agent:after_invoke"
        assert HookEvent.AGENT_ERROR.value == "agent:error"
        assert HookEvent.SESSION_START.value == "session:start"
        assert HookEvent.SESSION_END.value == "session:end"

    def test_hook_event_category(self):
        """HE-02: 事件类别提取正确"""
        assert HookEvent.TOOL_BEFORE_EXECUTE.category == "tool"
        assert HookEvent.SQL_DDL_DETECTED.category == "sql"
        assert HookEvent.APPROVAL_REQUESTED.category == "approval"
        assert HookEvent.AGENT_BEFORE_INVOKE.category == "agent"
        assert HookEvent.SESSION_START.category == "session"


# ============================================================================
# SECTION 2: HookContext 测试
# ============================================================================

class TestHookContext:
    """HookContext 测试"""

    def test_context_get_set(self):
        """HC-01: get/set 方法正确"""
        ctx = HookContext(
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "test"},
            session_id="s1",
            user_id="u1",
        )
        assert ctx.get("tool_name") == "test"
        assert ctx.get("nonexistent", "default") == "default"

        ctx.set("tool_name", "execute_sql")
        assert ctx.get("tool_name") == "execute_sql"

    def test_context_blocked(self):
        """HC-02: blocked 状态正确"""
        ctx = HookContext(event=HookEvent.TOOL_BEFORE_EXECUTE)
        assert ctx.blocked is False

        ctx.set_blocked("dangerous operation")
        assert ctx.blocked is True
        assert ctx.blocked_reason == "dangerous operation"

    def test_context_warnings(self):
        """HC-03: warnings 正确"""
        ctx = HookContext(event=HookEvent.TOOL_BEFORE_EXECUTE)
        ctx.add_warning("slow query")
        ctx.add_warning("full table scan")
        assert len(ctx.warnings) == 2
        assert ctx.warnings[0] == "slow query"

    def test_context_to_dict(self):
        """HC-04: to_dict 正确"""
        ctx = HookContext(
            event=HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "DROP TABLE t1"},
            session_id="s1",
            user_id="u1",
        )
        d = ctx.to_dict()
        assert d["event"] == "sql:ddl_detected"
        assert d["payload"]["sql_statement"] == "DROP TABLE t1"
        assert d["session_id"] == "s1"


# ============================================================================
# SECTION 3: HookCondition 测试
# ============================================================================

class TestHookCondition:
    """HookCondition 测试"""

    def test_condition_eq(self):
        """HCon-01: EQ 条件"""
        cond = HookCondition(field="tool_name", operator=ConditionOperator.EQ, value="execute_sql")
        assert cond.evaluate({"tool_name": "execute_sql"}) is True
        assert cond.evaluate({"tool_name": "query_tool"}) is False

    def test_condition_contains(self):
        """HCon-02: CONTAINS 条件"""
        cond = HookCondition(field="sql", operator=ConditionOperator.CONTAINS, value="DROP")
        assert cond.evaluate({"sql": "DROP TABLE users"}) is True
        assert cond.evaluate({"sql": "SELECT * FROM users"}) is False

    def test_condition_regex_match(self):
        """HCon-03: REGEX_MATCH 条件"""
        cond = HookCondition(
            field="sql_statement",
            operator=ConditionOperator.REGEX_MATCH,
            value=r"(DROP|TRUNCATE|ALTER\s+TABLE)"
        )
        assert cond.evaluate({"sql_statement": "DROP TABLE users"}) is True
        assert cond.evaluate({"sql_statement": "TRUNCATE TABLE t1"}) is True
        assert cond.evaluate({"sql_statement": "ALTER TABLE t1 ADD c INT"}) is True
        assert cond.evaluate({"sql_statement": "SELECT 1"}) is False

    def test_condition_in(self):
        """HCon-04: IN 条件"""
        cond = HookCondition(field="risk_level", operator=ConditionOperator.IN, value=["L4", "L5"])
        assert cond.evaluate({"risk_level": "L4"}) is True
        assert cond.evaluate({"risk_level": "L5"}) is True
        assert cond.evaluate({"risk_level": "L3"}) is False

    def test_condition_nested_field(self):
        """HCon-05: 嵌套字段条件"""
        cond = HookCondition(field="payload.params.sql", operator=ConditionOperator.CONTAINS, value="DROP")
        assert cond.evaluate({"payload": {"params": {"sql": "DROP TABLE t"}}}) is True
        assert cond.evaluate({"payload": {"params": {"sql": "SELECT 1"}}}) is False


# ============================================================================
# SECTION 4: HookRule 测试
# ============================================================================

class TestHookRule:
    """HookRule 测试"""

    def test_rule_matches(self):
        """HR-01: 规则匹配正确"""
        rule = HookRule(
            name="ddl-block",
            event=HookEvent.SQL_DDL_DETECTED,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(DROP|TRUNCATE)",
                )
            ],
            action=HookAction.BLOCK,
            message="DDL blocked",
        )

        assert rule.matches({"sql_statement": "DROP TABLE users"}) is True
        assert rule.matches({"sql_statement": "SELECT 1"}) is False

    def test_rule_disabled(self):
        """HR-02: 禁用规则不匹配"""
        rule = HookRule(
            name="ddl-block",
            event=HookEvent.SQL_DDL_DETECTED,
            enabled=False,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.EQ,
                    value="DROP",
                )
            ],
        )
        assert rule.matches({"sql_statement": "DROP"}) is False

    def test_rule_all_conditions_must_match(self):
        """HR-03: 多条件全部匹配才算匹配（AND）"""
        rule = HookRule(
            name="tool-sql-match",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(field="tool_name", operator=ConditionOperator.EQ, value="execute_sql"),
                HookCondition(field="params.sql", operator=ConditionOperator.CONTAINS, value="DROP"),
            ],
        )

        assert rule.matches({
            "tool_name": "execute_sql",
            "params": {"sql": "DROP TABLE users"}
        }) is True

        assert rule.matches({
            "tool_name": "query_tool",
            "params": {"sql": "DROP TABLE users"}
        }) is False

    def test_rule_to_dict(self):
        """HR-04: to_dict 正确"""
        rule = HookRule(
            name="test-rule",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            action=HookAction.WARN,
            priority=10,
            message="test",
        )
        d = rule.to_dict()
        assert d["name"] == "test-rule"
        assert d["event"] == "tool:before_execute"
        assert d["action"] == "warn"
        assert d["priority"] == 10


# ============================================================================
# SECTION 5: HookRegistry 测试
# ============================================================================

class TestHookRegistry:
    """HookRegistry 测试"""

    def test_registry_register_unregister(self):
        """HRG-01: 注册和注销规则"""
        reg = HookRegistry()
        rule = HookRule(
            name="test-rule",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
        )
        reg.register(rule)
        assert reg.get("test-rule") is not None

        reg.unregister("test-rule")
        assert reg.get("test-rule") is None

    def test_registry_list_hooks_by_event(self):
        """HRG-02: 按事件列出规则"""
        reg = HookRegistry()
        reg.register(HookRule(name="r1", event=HookEvent.TOOL_BEFORE_EXECUTE, priority=20))
        reg.register(HookRule(name="r2", event=HookEvent.TOOL_BEFORE_EXECUTE, priority=10))
        reg.register(HookRule(name="r3", event=HookEvent.SESSION_START))

        hooks = reg.list_hooks(HookEvent.TOOL_BEFORE_EXECUTE)
        assert len(hooks) == 2
        # 按优先级排序
        assert hooks[0].name == "r2"  # priority=10 更高
        assert hooks[1].name == "r1"   # priority=20 更低

    def test_registry_enable_disable(self):
        """HRG-03: 启用/禁用规则"""
        reg = HookRegistry()
        reg.register(HookRule(name="toggle-rule", event=HookEvent.TOOL_BEFORE_EXECUTE))

        reg.disable("toggle-rule")
        assert reg.get("toggle-rule").enabled is False

        reg.enable("toggle-rule")
        assert reg.get("toggle-rule").enabled is True

    def test_registry_from_dict(self):
        """HRG-04: 从字典加载规则"""
        reg = HookRegistry()
        rule_data = {
            "name": "ddl-block-rule",
            "event": "sql:ddl_detected",
            "enabled": True,
            "action": "block",
            "priority": 5,
            "message": "DDL not allowed",
            "conditions": [
                {"field": "sql_statement", "operator": "regex_match", "value": r"(DROP|TRUNCATE)"}
            ]
        }
        rule = reg.from_dict(rule_data)
        assert rule.name == "ddl-block-rule"
        assert rule.event == HookEvent.SQL_DDL_DETECTED
        assert rule.action == HookAction.BLOCK
        assert len(rule.conditions) == 1


# ============================================================================
# SECTION 6: RuleEngine 测试
# ============================================================================

class TestRuleEngine:
    """RuleEngine 测试"""

    @pytest.mark.asyncio
    async def test_rule_engine_no_matching_rules(self):
        """RLE-01: 无匹配规则时正常放行"""
        reg = HookRegistry()
        reg.register(HookRule(
            name="ddl-rule",
            event=HookEvent.SQL_DDL_DETECTED,
            conditions=[HookCondition(
                field="sql_statement",
                operator=ConditionOperator.EQ,
                value="DROP",
            )],
        ))
        engine = RuleEngine(registry=reg)

        ctx = HookContext(
            event=HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "SELECT 1"},
        )
        result_ctx = await engine.evaluate(ctx)

        assert result_ctx.blocked is False
        assert len(result_ctx.warnings) == 0

    @pytest.mark.asyncio
    async def test_rule_engine_block_action(self):
        """RLE-02: BLOCK 动作立即阻止"""
        reg = HookRegistry()
        reg.register(HookRule(
            name="ddl-block",
            event=HookEvent.SQL_DDL_DETECTED,
            conditions=[HookCondition(
                field="sql_statement",
                operator=ConditionOperator.CONTAINS,
                value="DROP",
            )],
            action=HookAction.BLOCK,
            message="DROP is not allowed",
        ))
        engine = RuleEngine(registry=reg)

        ctx = HookContext(
            event=HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "DROP TABLE users"},
        )
        result_ctx = await engine.evaluate(ctx)

        assert result_ctx.blocked is True
        assert "DROP is not allowed" in result_ctx.blocked_reason

    @pytest.mark.asyncio
    async def test_rule_engine_warn_action(self):
        """RLE-03: WARN 动作添加警告但不阻止"""
        reg = HookRegistry()
        reg.register(HookRule(
            name="slow-query-warn",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[HookCondition(
                field="params.sql",
                operator=ConditionOperator.CONTAINS,
                value="JOIN",
            )],
            action=HookAction.WARN,
            message="Query contains JOIN, may be slow",
        ))
        engine = RuleEngine(registry=reg)

        ctx = HookContext(
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"params": {"sql": "SELECT * FROM a JOIN b ON a.id = b.id"}},
        )
        result_ctx = await engine.evaluate(ctx)

        assert result_ctx.blocked is False
        assert len(result_ctx.warnings) == 1
        assert "JOIN" in result_ctx.warnings[0]

    @pytest.mark.asyncio
    async def test_rule_engine_check_blocked_sync(self):
        """RLE-04: check_blocked 同步快速检查"""
        reg = HookRegistry()
        reg.register(HookRule(
            name="ddl-block",
            event=HookEvent.SQL_DDL_DETECTED,
            conditions=[HookCondition(
                field="sql_statement",
                operator=ConditionOperator.CONTAINS,
                value="DROP",
            )],
            action=HookAction.BLOCK,
            message="DROP not allowed",
        ))
        engine = RuleEngine(registry=reg)

        blocked, msg = engine.check_blocked(
            HookEvent.SQL_DDL_DETECTED,
            {"sql_statement": "DROP TABLE users"}
        )
        assert blocked is True
        assert "not allowed" in msg

        blocked, msg = engine.check_blocked(
            HookEvent.SQL_DDL_DETECTED,
            {"sql_statement": "SELECT 1"}
        )
        assert blocked is False


# ============================================================================
# SECTION 7: HookEngine 主引擎测试
# ============================================================================

class TestHookEngine:
    """HookEngine 主引擎测试"""

    @pytest.mark.asyncio
    async def test_hook_engine_emit_basic(self):
        """HKE-01: emit 正确触发事件"""
        engine = HookEngine()
        async def handler(ctx: HookContext) -> HookContext:
            ctx.add_warning("handler called")
            return ctx

        engine.register_rule(HookRule(
            name="session-log",
            event=HookEvent.SESSION_START,
            handler=handler,
            action=HookAction.LOG,
        ))

        result = await engine.emit(
            HookEvent.SESSION_START,
            payload={"session_id": "test-001"},
            session_id="test-001",
            user_id="test-user",
        )

        assert result.event == HookEvent.SESSION_START
        assert "handler called" in result.warnings
        assert result.matched_rules == ["session-log"]

    @pytest.mark.asyncio
    async def test_hook_engine_emit_blocked(self):
        """HKE-02: emit 被阻止时返回 blocked=True"""
        engine = HookEngine()
        async def block_handler(ctx: HookContext) -> HookContext:
            ctx.set_blocked("dangerous")
            return ctx

        engine.register_rule(HookRule(
            name="dangerous-block",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            handler=block_handler,
            action=HookAction.BLOCK,
        ))

        result = await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "drop_table"},
            session_id="test-002",
            user_id="test-user",
        )

        assert result.blocked is True
        assert "dangerous" in result.message

    @pytest.mark.asyncio
    async def test_hook_engine_emit_sync(self):
        """HKE-03: emit_sync 同步触发"""
        engine = HookEngine()

        result = engine.emit_sync(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "test"},
            session_id="test-003",
            user_id="test-user",
        )

        assert result.blocked is False
        assert result.event == HookEvent.TOOL_BEFORE_EXECUTE

    @pytest.mark.asyncio
    async def test_hook_engine_load_yaml(self, tmp_path):
        """HKE-04: 从 YAML 加载规则"""
        import yaml

        config = [
            {
                "name": "ddl-block-yaml",
                "event": "sql:ddl_detected",
                "enabled": True,
                "action": "block",
                "priority": 5,
                "message": "DDL from YAML blocked",
                "conditions": [
                    {"field": "sql_statement", "operator": "contains", "value": "DROP"}
                ]
            }
        ]

        yaml_path = tmp_path / "hooks.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(config, f)

        engine = HookEngine()
        count = engine.load_yaml_config(str(yaml_path))

        assert count == 1
        assert engine.registry.get("ddl-block-yaml") is not None

    @pytest.mark.asyncio
    async def test_global_emit_hook_function(self):
        """HKE-05: 全局 emit_hook 便捷函数"""
        # Reset global engine
        import src.gateway.hooks.hook_engine as he_module
        he_module._engine = None

        result = await emit_hook(
            HookEvent.SESSION_START,
            payload={"session_id": "global-test"},
            session_id="global-test",
            user_id="test-user",
        )

        assert result.event == HookEvent.SESSION_START


# ============================================================================
# SECTION 8: Hook 与真实数据库集成测试
# ============================================================================

class TestHookRealDatabaseIntegration:
    """Hook 系统与真实数据库的集成测试"""

    @pytest.mark.asyncio
    async def test_real_db_select_with_hooks(self):
        """HI-01: 真实 SELECT 经过完整 Hook 流程"""
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 not available")

        try:
            conn = psycopg2.connect(
                host=os.environ.get("PGHOST", "localhost"),
                port=int(os.environ.get("PGPORT", 5432)),
                dbname=os.environ.get("PGDATABASE", "javis_test_db"),
                user=os.environ.get("PGUSER", "chongjieran"),
                password=os.environ.get("PGPASSWORD", ""),
            )
        except Exception:
            pytest.skip("Cannot connect to PostgreSQL test DB")

        engine = HookEngine()
        event_log = []

        async def before_hook(ctx: HookContext) -> HookContext:
            event_log.append(("before", ctx.get("sql", "")))
            return ctx

        async def after_hook(ctx: HookContext) -> HookContext:
            event_log.append(("after", ctx.get("sql", "")))
            return ctx

        engine.register_rule(HookRule(
            name="log-before-sql",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            handler=before_hook,
        ))
        engine.register_rule(HookRule(
            name="log-after-sql",
            event=HookEvent.TOOL_AFTER_EXECUTE,
            handler=after_hook,
        ))

        cursor = conn.cursor()
        sql = "SELECT 1 AS test"

        # Before hook
        await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"sql": sql, "tool_name": "execute_sql"},
            session_id="hi-01",
            user_id="test-user",
        )

        # Real DB execute
        cursor.execute(sql)
        rows = cursor.fetchall()

        # After hook
        await engine.emit(
            HookEvent.TOOL_AFTER_EXECUTE,
            payload={"sql": sql, "tool_name": "execute_sql", "rows": len(rows)},
            session_id="hi-01",
            user_id="test-user",
        )

        cursor.close()
        conn.close()

        assert ("before", sql) in event_log
        assert ("after", sql) in event_log
        assert rows[0][0] == 1

    @pytest.mark.asyncio
    async def test_ddl_detection_with_real_db_context(self):
        """HI-02: 真实 DDL 检测 Hook"""
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 not available")

        engine = HookEngine()
        ddl_log = []

        async def ddl_hook(ctx: HookContext) -> HookContext:
            sql = ctx.get("sql_statement", "")
            if re.match(r"(DROP|TRUNCATE|ALTER\s+TABLE)", sql, re.IGNORECASE):
                ddl_log.append(sql)
                ctx.set_blocked(f"DDL Hook blocked: {sql[:50]}")
            return ctx

        engine.register_rule(HookRule(
            name="ddl-detector",
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

        # Emit DDL detection for DROP TABLE
        result = await engine.emit(
            HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": "DROP TABLE IF EXISTS test_users"},
            session_id="hi-02",
            user_id="test-user",
        )

        assert result.blocked is True
        assert "DROP TABLE" in ddl_log[0]
