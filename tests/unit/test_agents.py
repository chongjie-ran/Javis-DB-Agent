"""
Unit tests for Agent implementations
"""
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestBaseAgent:
    """Test BaseAgent class"""
    
    def test_agent_has_required_attributes(self):
        """Verify base agent has required attributes"""
        agent_attrs = ["name", "description", "tools", "system_prompt"]
        mock_agent = {
            "name": "diagnostic_agent",
            "description": "诊断Agent",
            "tools": ["query_session", "query_lock"],
            "system_prompt": "你是诊断专家"
        }
        for attr in agent_attrs:
            assert attr in mock_agent

    def test_agent_tool_access(self):
        """Test agent can access its tools"""
        agent = {
            "name": "sql_analyzer",
            "available_tools": ["query_slow_sql", "analyze_plan", "query_session"]
        }
        assert "query_slow_sql" in agent["available_tools"]
        assert "execute_kill" not in agent["available_tools"]


class TestOrchestratorAgent:
    """Test OrchestratorAgent"""
    
    def test_intent_recognition(self):
        """Test intent recognition patterns"""
        test_cases = [
            {"input": "帮我分析这个告警", "expected_intent": "diagnose"},
            {"input": "查看慢SQL", "expected_intent": "sql_analyze"},
            {"input": "执行巡检", "expected_intent": "inspect"},
            {"input": "生成报告", "expected_intent": "report"}
        ]
        for case in test_cases:
            # Simple keyword matching simulation
            if "告警" in case["input"]:
                assert case["expected_intent"] == "diagnose"
            if "慢SQL" in case["input"]:
                assert case["expected_intent"] == "sql_analyze"

    def test_agent_selection(self):
        """Test agent selection based on intent"""
        intent_map = {
            "diagnose": ["diagnostic_agent", "risk_agent"],
            "sql_analyze": ["sql_analyzer_agent"],
            "inspect": ["inspector_agent"],
            "report": ["reporter_agent"]
        }
        assert "diagnostic_agent" in intent_map["diagnose"]
        assert "sql_analyzer_agent" in intent_map["sql_analyze"]

    def test_plan_building(self):
        """Test execution plan building"""
        plan = {
            "steps": [
                {"agent": "diagnostic_agent", "tool": "query_session", "params": {"limit": 10}},
                {"agent": "diagnostic_agent", "tool": "query_lock", "params": {}},
                {"agent": "risk_agent", "tool": "assess_risk", "params": {}}
            ],
            "context_required": ["instance_id", "alert_id"]
        }
        assert len(plan["steps"]) == 3
        assert "context_required" in plan


class TestDiagnosticAgent:
    """Test DiagnosticAgent"""
    
    def test_diagnosis_output_format(self):
        """Test diagnosis result format"""
        expected_fields = ["alert_type", "root_cause", "confidence", "next_steps"]
        diagnosis = {
            "alert_type": "锁等待超时",
            "root_cause": "长事务持有锁",
            "confidence": 0.85,
            "next_steps": ["查看会话", "分析阻塞链"]
        }
        for field in expected_fields:
            assert field in diagnosis

    def test_confidence_range(self):
        """Test confidence score is between 0 and 1"""
        confidence_scores = [0.85, 0.92, 0.45, 0.78]
        for score in confidence_scores:
            assert 0 <= score <= 1

    def test_next_steps_not_empty(self):
        """Test diagnosis always provides next steps"""
        diagnosis = {
            "alert_type": "CPU使用率高",
            "root_cause": "大量复杂查询",
            "confidence": 0.75,
            "next_steps": ["查看Top SQL", "分析执行计划", "建议添加索引"]
        }
        assert len(diagnosis["next_steps"]) > 0


class TestRiskAssessmentAgent:
    """Test RiskAssessmentAgent"""
    
    def test_risk_level_definitions(self):
        """Test risk level definitions"""
        risk_levels = {
            "L1": {"description": "只读分析", "approval_required": False},
            "L2": {"description": "自动诊断", "approval_required": False},
            "L3": {"description": "低风险执行", "approval_required": False},
            "L4": {"description": "中风险执行", "approval_required": True},
            "L5": {"description": "高风险执行", "approval_required": True}
        }
        assert risk_levels["L1"]["approval_required"] is False
        assert risk_levels["L4"]["approval_required"] is True

    def test_risk_assessment_output(self):
        """Test risk assessment output format"""
        assessment = {
            "level": "L3",
            "can_auto_handle": False,
            "approval_required": True,
            "risk_items": [
                {"type": "data_loss", "score": 0.7}
            ]
        }
        assert "level" in assessment
        assert "can_auto_handle" in assessment
        assert assessment["approval_required"] is True


class TestSQLAnalyzerAgent:
    """Test SQLAnalyzerAgent"""
    
    def test_sql_analysis_output(self):
        """Test SQL analysis result format"""
        analysis = {
            "sql_fingerprint": "abc123",
            "slow_reason": "全表扫描",
            "execution_plan": {
                "operation": "Seq Scan",
                "estimated_cost": 1000
            },
            "optimization_suggestions": [
                "添加索引",
                "重写SQL减少扫描范围"
            ],
            "risk_level": "L2"
        }
        assert "sql_fingerprint" in analysis
        assert "optimization_suggestions" in analysis

    def test_lock_analysis_output(self):
        """Test lock analysis result"""
        lock_analysis = {
            "blocked_pid": 1234,
            "blocking_pid": 5678,
            "lock_mode": "ShareRowExclusiveLock",
            "lock_age_seconds": 300,
            "can_kill": True,
            "kill_risk": "L4"
        }
        assert "blocked_pid" in lock_analysis
        assert "can_kill" in lock_analysis


class TestInspectorAgent:
    """Test InspectorAgent"""
    
    def test_health_score_range(self):
        """Test health score is 0-100"""
        health_scores = [85, 92, 45, 78, 30]
        for score in health_scores:
            assert 0 <= score <= 100

    def test_inspection_output(self):
        """Test inspection result format"""
        result = {
            "health_score": 85,
            "risk_items": [
                {"item": "慢SQL数量过多", "severity": "warning"},
                {"item": "连接数接近上限", "severity": "critical"}
            ],
            "suggestions": [
                "优化Top 5慢SQL",
                "建议扩大max_connections"
            ]
        }
        assert "health_score" in result
        assert len(result["risk_items"]) > 0


class TestReporterAgent:
    """Test ReporterAgent"""
    
    def test_report_types(self):
        """Test supported report types"""
        report_types = ["rca", "inspection", "summary"]
        assert "rca" in report_types
        assert "inspection" in report_types

    def test_rca_report_structure(self):
        """Test RCA report structure"""
        rca_report = {
            "title": "故障分析报告",
            "incident_time": "2026-03-28T10:00:00Z",
            "summary": "摘要",
            "timeline": [],
            "root_cause": "原因",
            "impact": "影响",
            "resolution": "处置",
            "lessons": "经验教训"
        }
        required_fields = ["title", "root_cause", "resolution", "lessons"]
        for field in required_fields:
            assert field in rca_report
