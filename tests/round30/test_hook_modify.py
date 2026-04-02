"""
Round30: V2.6.1 Hook MODIFY 动作测试
======================================
测试范围：F2 Hook MODIFY 动作
- REPLACE 操作
- REDACT 操作
- ADD / REMOVE / CLAMP 操作

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round30/test_hook_modify.py -v --tb=short
"""

import asyncio
import sys
import os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.hooks import (
    HookEvent, HookContext, HookRule, HookAction, ConditionOperator,
    HookCondition, HookRegistry, RuleEngine, HookEngine, HookResult,
    get_hook_engine,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_global_engine():
    yield
    import src.gateway.hooks.hook_engine as he_module
    import src.gateway.hooks.hook_registry as hr_module
    he_module._engine = None
    hr_module._registry = HookRegistry()


@pytest.fixture
def fresh_registry():
    return HookRegistry()


@pytest.fixture
def fresh_engine(fresh_registry):
    return HookEngine(registry=fresh_registry)


# ============================================================================
# SECTION 1: REPLACE 操作
# ============================================================================

class TestModifyReplace:
    """REPLACE 操作测试"""

    @pytest.mark.asyncio
    async def test_replace_simple_field(self, fresh_engine):
        """REP-01: 替换简单字符串字段"""
        replaced_values = []

        async def replace_handler(ctx):
            sql = ctx.get("sql_statement", "")
            if "DROP TABLE" in sql:
                replaced_values.append(sql)
                ctx.set("sql_statement", "[REPLACED: DROP TABLE blocked]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="replace-ddl-sql",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.CONTAINS,
                    value="DROP TABLE",
                )
            ],
            action=HookAction.MODIFY,
            handler=replace_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "DROP TABLE users CASCADE"},
            session_id="rep-01",
            user_id="test-user",
        )

        assert result.blocked is False
        assert "DROP TABLE users CASCADE" in replaced_values

    @pytest.mark.asyncio
    async def test_replace_nested_field(self, fresh_engine):
        """REP-02: 替换嵌套字段"""
        replaced = []

        async def replace_nested_handler(ctx):
            params = ctx.get("params", {})
            risk = params.get("risk_level", "")
            if risk == "L5":
                replaced.append(risk)
                ctx.set("params.risk_level", "L3")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="replace-risk-level",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="params.risk_level",
                    operator=ConditionOperator.EQ,
                    value="L5",
                )
            ],
            action=HookAction.MODIFY,
            handler=replace_nested_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={
                "tool_name": "execute_sql",
                "params": {"sql": "DELETE FROM users", "risk_level": "L5"},
            },
            session_id="rep-02",
            user_id="test-user",
        )

        assert result.blocked is False
        assert "L5" in replaced

    @pytest.mark.asyncio
    async def test_replace_no_match(self, fresh_engine):
        """REP-03: 无匹配条件时不替换"""
        handler_called = []

        async def replace_handler(ctx):
            handler_called.append(True)
            ctx.set("sql_statement", "[SHOULD NOT REACH]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="replace-unused",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.EQ,
                    value="NONEXISTENT_SQL",
                )
            ],
            action=HookAction.MODIFY,
            handler=replace_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "SELECT 1"},
            session_id="rep-03",
            user_id="test-user",
        )

        assert result.blocked is False
        assert len(handler_called) == 0

    @pytest.mark.asyncio
    async def test_replace_multiple_rules_chain(self, fresh_engine):
        """REP-04: 多条 MODIFY 规则链式执行"""
        chain_log = []

        async def rule1_handler(ctx):
            chain_log.append("rule1_before")
            ctx.set("field_a", "modified_by_rule1")
            return ctx

        async def rule2_handler(ctx):
            chain_log.append("rule2_see_field_a=" + str(ctx.get("field_a")))
            ctx.set("field_b", "modified_by_rule2")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="replace-chain-1",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=rule1_handler,
            priority=10,
        ))
        fresh_engine.register_rule(HookRule(
            name="replace-chain-2",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=rule2_handler,
            priority=20,
        ))

        await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "test"},
            session_id="rep-04",
            user_id="test-user",
        )

        assert "rule1_before" in chain_log
        assert "rule2_see_field_a=modified_by_rule1" in chain_log

    @pytest.mark.asyncio
    async def test_replace_preserves_other_fields(self, fresh_engine):
        """REP-05: REPLACE 不影响其他字段"""
        fields_seen = {}

        async def replace_handler(ctx):
            fields_seen["instance_id"] = ctx.get("instance_id")
            fields_seen["user_role"] = ctx.get("user_role")
            ctx.set("sql_statement", "SELECT [REDACTED]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="replace-preserve",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[],
            action=HookAction.MODIFY,
            handler=replace_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={
                "sql_statement": "SELECT * FROM users",
                "instance_id": "INS-001",
                "user_role": "admin",
            },
            session_id="rep-05",
            user_id="test-user",
        )

        assert fields_seen["instance_id"] == "INS-001"
        assert fields_seen["user_role"] == "admin"


# ============================================================================
# SECTION 2: REDACT 操作
# ============================================================================

class TestModifyRedact:
    """REDACT 操作测试"""

    @pytest.mark.asyncio
    async def test_redact_password_field(self, fresh_engine):
        """RED-01: 密码字段脱敏"""
        redacted_values = []

        async def redact_handler(ctx):
            params = ctx.get("params", {})
            if "password" in params:
                redacted_values.append(params["password"])
                params["password"] = "********"
                ctx.set("params", params)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="redact-password",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="params",
                    operator=ConditionOperator.HAS_KEY,
                    value="password",
                )
            ],
            action=HookAction.MODIFY,
            handler=redact_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={
                "tool_name": "create_user",
                "params": {"username": "admin", "password": "secret123"},
            },
            session_id="red-01",
            user_id="test-user",
        )

        assert "secret123" in redacted_values

    @pytest.mark.asyncio
    async def test_redact_email_partial(self, fresh_engine):
        """RED-02: 邮箱部分脱敏"""
        redacted_emails = []

        async def redact_email_handler(ctx):
            email = ctx.get("user_email", "")
            if "@" in email:
                redacted_emails.append(email)
                parts = email.split("@", 1)
                ctx.set("user_email", parts[0][:2] + "***@" + parts[1])
            return ctx

        fresh_engine.register_rule(HookRule(
            name="redact-email",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="user_email",
                    operator=ConditionOperator.CONTAINS,
                    value="@",
                )
            ],
            action=HookAction.MODIFY,
            handler=redact_email_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"user_email": "john.doe@company.com"},
            session_id="red-02",
            user_id="test-user",
        )

        assert "john.doe@company.com" in redacted_emails

    @pytest.mark.asyncio
    async def test_redact_credit_card(self, fresh_engine):
        """RED-03: 信用卡号脱敏"""
        redacted = []

        async def redact_cc_handler(ctx):
            cc = ctx.get("credit_card", "")
            if len(cc) >= 13:
                redacted.append(cc)
                ctx.set("credit_card", "****-****-****-" + cc[-4:])
            return ctx

        fresh_engine.register_rule(HookRule(
            name="redact-credit-card",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="credit_card",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"\d{13,19}",
                )
            ],
            action=HookAction.MODIFY,
            handler=redact_cc_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"credit_card": "4111111111111111"},
            session_id="red-03",
            user_id="test-user",
        )

        assert "4111111111111111" in redacted

    @pytest.mark.asyncio
    async def test_redact_sql_removes_comments(self, fresh_engine):
        """RED-04: SQL 语句移除注释"""
        redacted_sql = []

        async def redact_sql_handler(ctx):
            sql = ctx.get("sql_statement", "")
            import re
            cleaned = re.sub(r"--.*$", "[COMMENT REDACTED]", sql, flags=re.MULTILINE)
            if cleaned != sql:
                redacted_sql.append(sql)
                ctx.set("sql_statement", cleaned)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="redact-sql-comments",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[],
            action=HookAction.MODIFY,
            handler=redact_sql_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "SELECT * FROM users -- this is a comment\nWHERE id = 1"},
            session_id="red-04",
            user_id="test-user",
        )

        assert "-- this is a comment" in redacted_sql[0]

    @pytest.mark.asyncio
    async def test_redact_no_sensitive_data(self, fresh_engine):
        """RED-05: 无敏感数据时不脱敏"""
        handler_called = []

        async def redact_handler(ctx):
            handler_called.append(True)
            ctx.set("sql_statement", "[SHOULD NOT REDACT]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="redact-safe-sql",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.CONTAINS,
                    value="SENSITIVE_MAGIC_STRING_XYZ",
                )
            ],
            action=HookAction.MODIFY,
            handler=redact_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "SELECT 1"},
            session_id="red-05",
            user_id="test-user",
        )

        assert len(handler_called) == 0


# ============================================================================
# SECTION 3: ADD / REMOVE / CLAMP 操作
# ============================================================================

class TestModifyAddRemoveClamp:
    """ADD / REMOVE / CLAMP 操作测试"""

    @pytest.mark.asyncio
    async def test_add_field_to_payload(self, fresh_engine):
        """ARC-01: ADD 添加新字段到 payload"""
        added_fields = []

        async def add_handler(ctx):
            if not ctx.get("added_by_hook"):
                ctx.set("added_by_hook", "hook_v261")
                ctx.set("hook_timestamp", time.time())
                added_fields.append("added_by_hook")  # Append the key, not the value
            return ctx

        fresh_engine.register_rule(HookRule(
            name="add-metadata",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=add_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "test_tool"},
            session_id="arc-01",
            user_id="test-user",
        )

        assert "added_by_hook" in added_fields
        assert added_fields[0] == "added_by_hook"

    @pytest.mark.asyncio
    async def test_add_increments_value(self, fresh_engine):
        """ARC-02: ADD 增加数值字段"""
        added_values = []

        async def add_handler(ctx):
            current = ctx.get("retry_count", 0)
            new_value = current + 1
            ctx.set("retry_count", new_value)
            added_values.append(new_value)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="add-retry-count",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=add_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"retry_count": 2},
            session_id="arc-02",
            user_id="test-user",
        )

        assert 3 in added_values

    @pytest.mark.asyncio
    async def test_remove_field_from_payload(self, fresh_engine):
        """ARC-03: REMOVE 从 payload 删除字段"""
        removed_fields = []

        async def remove_handler(ctx):
            if ctx.get("debug_flag"):
                removed_fields.append("debug_flag")
                ctx.payload.pop("debug_flag", None)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="remove-debug-flag",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="debug_flag",
                    operator=ConditionOperator.EQ,
                    value=True,
                )
            ],
            action=HookAction.MODIFY,
            handler=remove_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "test", "debug_flag": True},
            session_id="arc-03",
            user_id="test-user",
        )

        assert "debug_flag" in removed_fields

    @pytest.mark.asyncio
    async def test_remove_only_matched_condition(self, fresh_engine):
        """ARC-04: REMOVE 只删除匹配条件的字段"""
        removed = []
        public_field_value = []

        async def remove_handler(ctx):
            if ctx.get("temp_internal_field"):
                removed.append("temp_internal_field")
                ctx.payload.pop("temp_internal_field", None)
            public_field_value.append(ctx.get("public_field"))
            return ctx

        fresh_engine.register_rule(HookRule(
            name="remove-temp",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="temp_internal_field",
                    operator=ConditionOperator.CONTAINS,
                    value="internal",
                )
            ],
            action=HookAction.MODIFY,
            handler=remove_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={
                "temp_internal_field": "internal_use_only",
                "public_field": "keep_this",
            },
            session_id="arc-04",
            user_id="test-user",
        )

        assert "temp_internal_field" in removed
        assert public_field_value[0] == "keep_this"

    @pytest.mark.asyncio
    async def test_clamp_value_above_max(self, fresh_engine):
        """ARC-05a: CLAMP 将超出上限的值限制在范围内"""
        clamped_values = []

        async def clamp_handler(ctx):
            max_conn = ctx.get("max_connections", 0)
            MIN_VAL, MAX_VAL = 1, 100
            original = max_conn
            if max_conn < MIN_VAL:
                max_conn = MIN_VAL
            elif max_conn > MAX_VAL:
                max_conn = MAX_VAL
            if max_conn != original:
                clamped_values.append((original, max_conn))
                ctx.set("max_connections", max_conn)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="clamp-max-connections",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=clamp_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"max_connections": 500},
            session_id="arc-05a",
            user_id="test-user",
        )
        assert (500, 100) in clamped_values

    @pytest.mark.asyncio
    async def test_clamp_value_below_min(self, fresh_engine):
        """ARC-05b: CLAMP 将低于下限的值限制在范围内"""
        clamped_values = []

        async def clamp_handler(ctx):
            max_conn = ctx.get("max_connections", 0)
            MIN_VAL, MAX_VAL = 1, 100
            original = max_conn
            if max_conn < MIN_VAL:
                max_conn = MIN_VAL
            elif max_conn > MAX_VAL:
                max_conn = MAX_VAL
            if max_conn != original:
                clamped_values.append((original, max_conn))
                ctx.set("max_connections", max_conn)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="clamp-max-connections",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=clamp_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"max_connections": 0},
            session_id="arc-05b",
            user_id="test-user",
        )
        assert (0, 1) in clamped_values

    @pytest.mark.asyncio
    async def test_clamp_within_range_no_change(self, fresh_engine):
        """ARC-06: 值在范围内时 CLAMP 不修改"""
        clamped_values = []

        async def clamp_handler(ctx):
            max_conn = ctx.get("max_connections", 50)
            if max_conn > 100:
                clamped_values.append(max_conn)
                ctx.set("max_connections", 100)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="clamp-noop",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=clamp_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"max_connections": 50},
            session_id="arc-06",
            user_id="test-user",
        )

        assert len(clamped_values) == 0

    @pytest.mark.asyncio
    async def test_clamp_timeout_values(self, fresh_engine):
        """ARC-07: CLAMP 限制超时值合理范围"""
        clamped_timeouts = []

        async def clamp_handler(ctx):
            timeout_ms = ctx.get("timeout_ms", 0)
            MAX_TIMEOUT = 300000
            if timeout_ms > MAX_TIMEOUT:
                clamped_timeouts.append((timeout_ms, MAX_TIMEOUT))
                ctx.set("timeout_ms", MAX_TIMEOUT)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="clamp-timeout",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=clamp_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"timeout_ms": 600000},
            session_id="arc-07",
            user_id="test-user",
        )

        assert (600000, 300000) in clamped_timeouts


# ============================================================================
# SECTION 4: MODIFY 与其他动作混合
# ============================================================================

class TestModifyMixedWithOtherActions:
    """MODIFY 与 BLOCK/WARN/LOG 混合场景"""

    @pytest.mark.asyncio
    async def test_modify_before_block(self, fresh_engine):
        """MIX-01: MODIFY 规则优先级高于 BLOCK（先修改后阻止）"""
        execution_order = []

        async def modify_handler(ctx):
            execution_order.append("modify")
            ctx.set("sql_statement", "SELECT 1")
            return ctx

        async def block_handler(ctx):
            execution_order.append("block")
            ctx.set_blocked("dangerous")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="modify-before-block",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[],
            action=HookAction.MODIFY,
            handler=modify_handler,
            priority=10,
        ))
        fresh_engine.register_rule(HookRule(
            name="block-after-modify",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[],
            action=HookAction.BLOCK,
            handler=block_handler,
            priority=20,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "DROP TABLE users"},
            session_id="mix-01",
            user_id="test-user",
        )

        assert "modify" in execution_order
        assert "block" in execution_order
        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_modify_with_warn(self, fresh_engine):
        """MIX-02: MODIFY 后跟 WARN"""
        execution_order = []

        async def modify_handler(ctx):
            execution_order.append("modify")
            ctx.set("modified", True)
            return ctx

        async def warn_handler(ctx):
            execution_order.append("warn")
            ctx.add_warning("operation modified")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="modify-op",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=modify_handler,
            priority=10,
        ))
        fresh_engine.register_rule(HookRule(
            name="warn-op",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.WARN,
            handler=warn_handler,
            priority=20,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "test"},
            session_id="mix-02",
            user_id="test-user",
        )

        assert execution_order == ["modify", "warn"]
        assert len(result.warnings) == 1
        assert "operation modified" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_modify_and_log_combined(self, fresh_engine):
        """MIX-03: MODIFY 和 LOG 组合"""
        handler_called = []

        async def modify_handler(ctx):
            ctx.set("params.query", "SELECT [MODIFIED]")
            handler_called.append("modify")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="modify-log-combined",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="params.query",
                    operator=ConditionOperator.CONTAINS,
                    value="SELECT",
                )
            ],
            action=HookAction.MODIFY,
            handler=modify_handler,
        ))
        fresh_engine.register_rule(HookRule(
            name="log-after-modify",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.LOG,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"params": {"query": "SELECT * FROM users"}},
            session_id="mix-03",
            user_id="test-user",
        )

        assert "modify" in handler_called
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_multiple_modify_operations_same_payload(self, fresh_engine):
        """MIX-04: 同一 payload 多个 MODIFY 操作"""
        field_values = {}

        async def replace_handler(ctx):
            ctx.set("field_a", "replaced")
            field_values["field_a"] = ctx.get("field_a")
            return ctx

        async def redact_handler(ctx):
            ctx.set("field_b", "redacted_" + str(ctx.get("field_a", "unknown")))
            field_values["field_b"] = ctx.get("field_b")
            return ctx

        async def add_handler(ctx):
            ctx.set("field_c", "added")
            field_values["field_c"] = ctx.get("field_c")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="multi-mod-1",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=replace_handler,
            priority=10,
        ))
        fresh_engine.register_rule(HookRule(
            name="multi-mod-2",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=redact_handler,
            priority=20,
        ))
        fresh_engine.register_rule(HookRule(
            name="multi-mod-3",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=add_handler,
            priority=30,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "multi_mod_test"},
            session_id="mix-04",
            user_id="test-user",
        )

        assert field_values.get("field_a") == "replaced"
        assert field_values.get("field_b") == "redacted_replaced"
        assert field_values.get("field_c") == "added"


# ============================================================================
# SECTION 5: Hook MODIFY 真实 SQL 场景集成
# ============================================================================

class TestModifyRealSQLScenarios:
    """Hook MODIFY 真实 SQL 场景集成测试"""

    @pytest.mark.asyncio
    async def test_sql_injection_prevention_via_replace(self, fresh_engine):
        """RLS-01: SQL 注入防护（REPLACE 清理危险字符）"""
        sanitized_sql = []

        async def sanitize_handler(ctx):
            sql = ctx.get("sql_statement", "")
            import re
            cleaned = re.sub(r"/\*.*?\*/", "", sql)
            cleaned = re.sub(r"--.*$", "", cleaned, flags=re.MULTILINE)
            # Also remove dangerous SQL keywords (simplified sanitization)
            cleaned = re.sub(r"DROP\s+TABLE", "[DDL REMOVED]", cleaned, flags=re.IGNORECASE)
            if cleaned != sql:
                sanitized_sql.append((sql, cleaned.strip()))
                ctx.set("sql_statement", cleaned.strip())
            return ctx

        fresh_engine.register_rule(HookRule(
            name="sql-injection-sanitize",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(/\\*|--)",
                )
            ],
            action=HookAction.MODIFY,
            handler=sanitize_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={
                "sql_statement": "SELECT * FROM users /* injection */; DROP TABLE users; -- comment here",
            },
            session_id="rls-01",
            user_id="test-user",
        )

        assert len(sanitized_sql) == 1
        original_sql = sanitized_sql[0][0]
        cleaned_sql = sanitized_sql[0][1]
        assert "DROP TABLE" in original_sql
        assert "DROP TABLE" not in cleaned_sql

    @pytest.mark.asyncio
    async def test_ddl_whitelist_via_replace(self, fresh_engine):
        """RLS-02: DDL 白名单（REPLACE 高风险 DDL）"""
        replaced_ddl = []

        async def replace_ddl_handler(ctx):
            sql = ctx.get("sql_statement", "")
            import re
            if re.match(r"\s*(DROP|TRUNCATE)\s+TABLE", sql, re.IGNORECASE):
                replaced_ddl.append(sql)
                ctx.set("sql_statement", "[DDL REPLACED BY HOOK]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="ddl-whitelist-replace",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"(DROP|TRUNCATE)\s+TABLE",
                )
            ],
            action=HookAction.MODIFY,
            handler=replace_ddl_handler,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "DROP TABLE critical_data"},
            session_id="rls-02",
            user_id="test-user",
        )

        assert len(replaced_ddl) == 1
        assert replaced_ddl[0] == "DROP TABLE critical_data"

    @pytest.mark.asyncio
    async def test_select_only_sql_allowed(self, fresh_engine):
        """RLS-03: 只允许 SELECT（其他全部 REDACT）"""
        redacted_non_select = []

        async def redact_non_select(ctx):
            sql = ctx.get("sql_statement", "")
            import re
            if not re.match(r"^\s*SELECT\s", sql, re.IGNORECASE):
                redacted_non_select.append(sql)
                ctx.set("sql_statement", "[NON-SELECT REDACTED]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="select-only-redact",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.REGEX_MATCH,
                    value=r"^(?!SELECT\s)",
                )
            ],
            action=HookAction.MODIFY,
            handler=redact_non_select,
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "DELETE FROM users WHERE id = 1"},
            session_id="rls-03",
            user_id="test-user",
        )

        assert len(redacted_non_select) == 1
        assert redacted_non_select[0] == "DELETE FROM users WHERE id = 1"

    @pytest.mark.asyncio
    async def test_timeout_clamp_real_scenario(self, fresh_engine):
        """RLS-04: 超时限制真实场景"""
        clamped_timeouts = []
        sql_preserved = []

        async def clamp_timeout(ctx):
            timeout = ctx.get("timeout_ms", 30000)
            MAX_TIMEOUT = 60000
            if timeout > MAX_TIMEOUT:
                clamped_timeouts.append((timeout, MAX_TIMEOUT))
                ctx.set("timeout_ms", MAX_TIMEOUT)
            sql_preserved.append(ctx.get("sql"))
            return ctx

        fresh_engine.register_rule(HookRule(
            name="clamp-timeout-real",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[
                HookCondition(
                    field="timeout_ms",
                    operator=ConditionOperator.GT,
                    value=60000,
                )
            ],
            action=HookAction.MODIFY,
            handler=clamp_timeout,
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"timeout_ms": 120000, "sql": "SELECT * FROM big_table"},
            session_id="rls-04",
            user_id="test-user",
        )

        assert len(clamped_timeouts) == 1
        assert clamped_timeouts[0] == (120000, 60000)
        assert sql_preserved[0] == "SELECT * FROM big_table"
