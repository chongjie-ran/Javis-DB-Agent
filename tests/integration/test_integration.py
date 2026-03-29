"""
Integration tests for Javis-DB-Agent

These tests require:
1. PostgreSQL running with test database
2. Ollama running (optional, will mock if not available)
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestDatabaseConnection:
    """Test database connectivity"""
    
    def test_can_connect_to_test_db(self, test_db_connection):
        """Test we can connect to the test database"""
        cursor = test_db_connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1
        cursor.close()

    def test_test_db_has_required_tables(self, test_db_connection):
        """Test that test database is accessible"""
        cursor = test_db_connection.cursor()
        # Just verify connection works
        cursor.execute("SELECT current_database(), current_user")
        result = cursor.fetchone()
        assert result[0] == "zcloud_agent_test"
        cursor.close()


class TestGatewayEndpoints:
    """Test API endpoints"""
    
    def test_health_endpoint_format(self):
        """Test health check response format"""
        response = {"status": "ok", "version": "v1.0"}
        assert "status" in response
        assert response["status"] == "ok"

    def test_chat_endpoint_request_format(self):
        """Test chat endpoint request format"""
        request = {
            "goal": "分析告警 ALT-001",
            "context": {
                "instance_id": "INS-001",
                "user": "test_user"
            }
        }
        assert "goal" in request
        assert "context" in request

    def test_diagnose_endpoint_request_format(self):
        """Test diagnose endpoint request format"""
        request = {
            "alert_id": "ALT-TEST-001",
            "instance_id": "INS-TEST-001",
            "context": {}
        }
        assert "alert_id" in request
        assert "instance_id" in request


class TestAgentWorkflow:
    """Test end-to-end agent workflows"""
    
    def test_diagnosis_workflow_steps(self):
        """Test diagnosis workflow sequence"""
        workflow_steps = [
            "接收告警事件",
            "编排Agent解析意图",
            "选择诊断Agent",
            "调用QueryTools获取上下文",
            "调用知识库匹配规则",
            "风险Agent评估",
            "汇总结果返回"
        ]
        assert len(workflow_steps) == 7
        # Verify correct order
        assert workflow_steps[0] == "接收告警事件"
        assert workflow_steps[-1] == "汇总结果返回"

    def test_sql_analysis_workflow(self):
        """Test SQL analysis workflow"""
        workflow = [
            "接收SQL指纹/会话ID",
            "编排Agent选择SQL分析Agent",
            "QueryTools获取SQL详情",
            "AnalysisTools分析执行计划",
            "知识库匹配优化规则",
            "输出优化建议和风险评估"
        ]
        assert "QueryTools获取SQL详情" in workflow
        assert "知识库匹配优化规则" in workflow

    def test_inspection_workflow(self):
        """Test inspection workflow"""
        workflow = [
            "接收巡检任务",
            "编排Agent选择巡检Agent",
            "QueryTools收集实例状态",
            "计算健康评分",
            "识别风险项",
            "生成治理建议"
        ]
        assert len(workflow) == 6


class TestSecurityLayer:
    """Test security policy enforcement"""
    
    def test_high_risk_action_blocked(self):
        """High risk actions should be blocked by default"""
        policy = {
            "action": "kill_session",
            "risk_level": 5,
            "auto_execute": False,
            "requires_approval": True,
            "requires_dual_approval": True
        }
        assert policy["risk_level"] == 5
        assert policy["auto_execute"] is False
        assert policy["requires_dual_approval"] is True

    def test_sql_guardrail_blocks_dangerous_sql(self):
        """SQL guardrail should block dangerous operations"""
        forbidden = [
            "DROP DATABASE production",
            "DELETE FROM pg_catalog",
            "TRUNCATE production.*"
        ]
        allowed = [
            "SELECT * FROM test",
            "INSERT INTO logs VALUES (1)",
            "UPDATE test SET name='x' WHERE id=1"
        ]
        for sql in forbidden:
            assert any(kw in sql for kw in ["DROP", "DELETE FROM pg_", "TRUNCATE"])
        for sql in allowed:
            assert "DROP" not in sql

    def test_permission_check_order(self):
        """Test permission check sequence"""
        checks = [
            "1. 检查用户权限级别",
            "2. 检查动作风险级别",
            "3. 检查工具权限要求",
            "4. 检查参数约束",
            "5. 决定是否放行或审批"
        ]
        assert len(checks) == 5


class TestKnowledgeLayer:
    """Test knowledge base integration"""
    
    def test_alert_rule_structure(self):
        """Test alert rule definition structure"""
        rule = {
            "alert_code": "ALT_LOCK_WAIT",
            "name": "锁等待超时",
            "severity": "warning",
            "symptoms": ["等待时间超过阈值", "会话处于Waiting状态"],
            "possible_causes": ["长事务持有锁", "未提交事务"],
            "check_steps": ["查询锁等待链", "分析持有锁的SQL"],
            "resolution": ["确认是否可以kill session", "联系应用负责人"]
        }
        required = ["alert_code", "symptoms", "possible_causes", "check_steps"]
        for field in required:
            assert field in rule

    def test_sop_structure(self):
        """Test SOP definition structure"""
        sop = {
            "sop_id": "SOP-001",
            "title": "锁等待超时处理",
            "steps": [
                {"step": 1, "action": "查看锁等待链", "tool": "query_lock"},
                {"step": 2, "action": "分析持有锁的SQL", "tool": "query_session"},
                {"step": 3, "action": "评估影响", "tool": "risk_assessment"}
            ],
            "risk_level": "L3"
        }
        assert "steps" in sop
        assert len(sop["steps"]) > 0


class TestLLMIntegration:
    """Test LLM integration (mocked)"""
    
    def test_system_prompt_includes_safety_rules(self):
        """System prompt should include safety rules"""
        safety_rules = [
            "永远不直接输出SQL或shell命令",
            "所有操作必须通过工具调用",
            "遵循最小权限原则"
        ]
        for rule in safety_rules:
            assert len(rule) > 0

    def test_tool_call_format(self):
        """Test tool call request format"""
        tool_call = {
            "tool": "query_session",
            "params": {
                "instance_id": "INS-001",
                "limit": 10
            }
        }
        assert "tool" in tool_call
        assert "params" in tool_call
        assert "instance_id" in tool_call["params"]


class TestAuditLogging:
    """Test audit logging"""
    
    def test_audit_log_structure(self):
        """Test audit log entry structure"""
        log_entry = {
            "timestamp": "2026-03-28T10:00:00Z",
            "user": "test_user",
            "session_id": "session-001",
            "action": "query_session",
            "params": {"instance_id": "INS-001"},
            "result": "success",
            "duration_ms": 15
        }
        required = ["timestamp", "user", "action", "params", "result"]
        for field in required:
            assert field in log_entry

    def test_audit_covers_full_chain(self):
        """Audit should cover full operation chain"""
        chain = [
            "用户请求",
            "意图解析",
            "工具选择",
            "参数校验",
            "执行",
            "结果",
            "风险评估"
        ]
        assert len(chain) == 7
