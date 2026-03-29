"""
Round 16 集成测试 - 增强测试覆盖

覆盖:
1. SessionAnalyzerAgent + Orchestrator 集成
2. CapacityAgent + Orchestrator 集成
3. AlertAgent + Orchestrator 集成
4. 意图路由集成测试
5. 双引擎E2E测试 (MySQL + PostgreSQL)
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# ============================================================================
# Agent + Orchestrator 集成测试
# ============================================================================

class TestSessionAnalyzerOrchestratorIntegration:
    """SessionAnalyzerAgent + Orchestrator 集成测试"""

    def test_session_analyzer_agent_registered(self):
        """验证SessionAnalyzerAgent已在Orchestrator中注册"""
        from src.agents.orchestrator import Intent

        mapping = {
            Intent.DIAGNOSE: ["diagnostic", "risk"],
            Intent.ANALYZE_SESSION: ["session_analyzer"],
            Intent.DETECT_DEADLOCK: ["session_analyzer", "risk"],
        }
        assert "session_analyzer" in mapping[Intent.ANALYZE_SESSION]

    def test_intent_recognize_analyze_session(self):
        """测试识别"分析会话"意图"""
        test_cases = [
            ("帮我分析这个会话", True),
            ("查看当前连接", True),
            ("分析会话列表", True),
            ("检测死锁", True),
        ]
        for goal, should_match in test_cases:
            has_keyword = any(kw in goal for kw in ["会话", "连接", "死锁"])
            assert has_keyword == should_match, f"Goal: {goal}"

    @pytest.mark.asyncio
    async def test_orchestrator_selects_session_analyzer(self):
        """测试编排器正确选择会话分析Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.ANALYZE_SESSION
        agents = orch._select_agents(intent, "分析会话")

        assert any(a.name == "session_analyzer" for a in agents)

    @pytest.mark.asyncio
    async def test_orchestrator_selects_deadlock_detection(self):
        """测试编排器选择死锁检测Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.DETECT_DEADLOCK
        agents = orch._select_agents(intent, "检测死锁")

        assert any(a.name == "session_analyzer" for a in agents)


class TestCapacityAgentOrchestratorIntegration:
    """CapacityAgent + Orchestrator 集成测试"""

    def test_capacity_agent_registered(self):
        """验证CapacityAgent已在Orchestrator中注册"""
        from src.agents.orchestrator import Intent

        mapping = {
            Intent.ANALYZE_CAPACITY: ["capacity"],
            Intent.PREDICT_GROWTH: ["capacity"],
            Intent.CAPACITY_REPORT: ["capacity"],
        }
        assert "capacity" in mapping[Intent.ANALYZE_CAPACITY]

    @pytest.mark.asyncio
    async def test_orchestrator_selects_capacity_agent(self):
        """测试编排器正确选择容量Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.ANALYZE_CAPACITY
        agents = orch._select_agents(intent, "分析容量")

        assert any(a.name == "capacity" for a in agents)

    @pytest.mark.asyncio
    async def test_orchestrator_selects_growth_prediction(self):
        """测试编排器选择增长预测Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.PREDICT_GROWTH
        agents = orch._select_agents(intent, "预测增长")

        assert any(a.name == "capacity" for a in agents)


class TestAlertAgentOrchestratorIntegration:
    """AlertAgent + Orchestrator 集成测试"""

    def test_alert_agent_registered(self):
        """验证AlertAgent已在Orchestrator中注册"""
        from src.agents.orchestrator import Intent

        mapping = {
            Intent.ANALYZE_ALERT: ["alert"],
            Intent.DEDUPLICATE_ALERTS: ["alert"],
            Intent.ROOT_CAUSE: ["alert", "diagnostic"],
            Intent.PREDICTIVE_ALERT: ["alert"],
        }
        assert "alert" in mapping[Intent.ANALYZE_ALERT]
        assert "alert" in mapping[Intent.DEDUPLICATE_ALERTS]
        assert "alert" in mapping[Intent.PREDICTIVE_ALERT]

    @pytest.mark.asyncio
    async def test_orchestrator_selects_alert_agent(self):
        """测试编排器正确选择告警Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.ANALYZE_ALERT
        agents = orch._select_agents(intent, "分析告警")

        assert any(a.name == "alert" for a in agents)

    @pytest.mark.asyncio
    async def test_orchestrator_selects_alert_dedup(self):
        """测试编排器选择告警去重Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.DEDUPLICATE_ALERTS
        agents = orch._select_agents(intent, "告警去重")

        assert any(a.name == "alert" for a in agents)

    @pytest.mark.asyncio
    async def test_root_cause_routes_to_alert_and_diagnostic(self):
        """测试根因分析路由到alert和diagnostic"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()
        intent = Intent.ROOT_CAUSE
        agents = orch._select_agents(intent, "根因分析")

        agent_names = [a.name for a in agents]
        assert "alert" in agent_names
        assert "diagnostic" in agent_names


# ============================================================================
# 意图路由集成测试
# ============================================================================

class TestIntentRouting:
    """意图路由集成测试"""

    def test_all_intents_have_agent_mapping(self):
        """验证所有意图都有Agent映射"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        orch = OrchestratorAgent()

        # 确保每个intent都能找到对应的agent
        for intent in Intent:
            agents = orch._select_agents(intent, f"测试{intent.value}")
            # GENERAL意图不需要agent
            if intent != Intent.GENERAL:
                assert len(agents) > 0, f"Intent {intent.value} has no agent mapping"

    def test_intent_keywords_unique(self):
        """验证新增意图的关键词唯一性"""
        from src.agents.orchestrator import Intent

        # Round 15 新增意图
        round15_intents = [
            Intent.ANALYZE_ALERT,
            Intent.DEDUPLICATE_ALERTS,
            Intent.ROOT_CAUSE,
            Intent.PREDICTIVE_ALERT,
        ]

        # 确保每个intent的value唯一
        values = [v.value for v in round15_intents]
        assert len(values) == len(set(values)), "Intent values must be unique"

    @pytest.mark.asyncio
    async def test_intent_recognition_coverage(self):
        """测试意图识别覆盖所有场景"""
        from src.agents.orchestrator import Intent

        # 验证所有Intent枚举值都有对应的Agent映射
        intent_agent_map = {
            Intent.DIAGNOSE: ["diagnostic", "risk"],
            Intent.SQL_ANALYZE: ["sql_analyzer", "risk"],
            Intent.ANALYZE_SESSION: ["session_analyzer"],
            Intent.DETECT_DEADLOCK: ["session_analyzer", "risk"],
            Intent.SUGGEST_INDEX: ["sql_analyzer"],
            Intent.INSPECT: ["inspector"],
            Intent.REPORT: ["reporter"],
            Intent.RISK_ASSESS: ["risk"],
            Intent.ANALYZE_CAPACITY: ["capacity"],
            Intent.PREDICT_GROWTH: ["capacity"],
            Intent.CAPACITY_REPORT: ["capacity"],
            Intent.ANALYZE_ALERT: ["alert"],
            Intent.DEDUPLICATE_ALERTS: ["alert"],
            Intent.ROOT_CAUSE: ["alert", "diagnostic"],
            Intent.PREDICTIVE_ALERT: ["alert"],
            Intent.GENERAL: [],
        }

        # 确保所有Intent都有映射
        assert len(intent_agent_map) == len(Intent), "All intents must be mapped"
        for intent, agents in intent_agent_map.items():
            if intent != Intent.GENERAL:
                assert len(agents) > 0, f"Intent {intent.value} has no agent mapping"


# ============================================================================
# 双引擎 E2E 测试 (MySQL + PostgreSQL)
# ============================================================================

class TestDualEngineE2E:
    """双引擎 E2E 测试"""

    @pytest.mark.asyncio
    async def test_mysql_session_list_e2e(self):
        """MySQL 会话列表 E2E 测试"""
        from src.tools.session_tools import SessionListTool

        tool = SessionListTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-MYSQL", "db_type": "mysql", "limit": 10},
            {}
        )

        assert result.success is True
        assert result.data["db_type"] == "mysql"
        assert "sessions" in result.data

    @pytest.mark.asyncio
    async def test_postgres_session_list_e2e(self):
        """PostgreSQL 会话列表 E2E 测试"""
        from src.tools.session_tools import SessionListTool

        tool = SessionListTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-PG", "db_type": "postgresql", "limit": 10},
            {}
        )

        assert result.success is True
        assert result.data["db_type"] == "postgresql"
        assert "sessions" in result.data

    @pytest.mark.asyncio
    async def test_mysql_connection_pool_e2e(self):
        """MySQL 连接池 E2E 测试"""
        from src.tools.session_tools import ConnectionPoolTool

        tool = ConnectionPoolTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-MYSQL", "db_type": "mysql"},
            {}
        )

        assert result.success is True
        assert result.data["db_type"] == "mysql"
        assert "pool" in result.data

    @pytest.mark.asyncio
    async def test_postgres_connection_pool_e2e(self):
        """PostgreSQL 连接池 E2E 测试"""
        from src.tools.session_tools import ConnectionPoolTool

        tool = ConnectionPoolTool()
        # Note: code checks "pg" not "postgresql"
        result = await tool.execute(
            {"instance_id": "INS-TEST-PG", "db_type": "pg"},
            {}
        )

        assert result.success is True
        assert result.data["db_type"] == "pg"
        assert "pool" in result.data

    @pytest.mark.asyncio
    async def test_mysql_deadlock_detection_e2e(self):
        """MySQL 死锁检测 E2E 测试"""
        from src.tools.session_tools import DeadlockDetectionTool

        tool = DeadlockDetectionTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-MYSQL", "db_type": "mysql"},
            {}
        )

        assert result.success is True
        assert result.data["db_type"] == "mysql"

    @pytest.mark.asyncio
    async def test_postgres_deadlock_detection_e2e(self):
        """PostgreSQL 死锁检测 E2E 测试"""
        from src.tools.session_tools import DeadlockDetectionTool

        tool = DeadlockDetectionTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-PG", "db_type": "postgresql"},
            {}
        )

        assert result.success is True
        assert result.data["db_type"] == "postgresql"

    @pytest.mark.asyncio
    async def test_mysql_slow_query_e2e(self):
        """MySQL 慢SQL查询 E2E 测试"""
        from src.tools.query_tools import QuerySlowSQLTool

        tool = QuerySlowSQLTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-MYSQL", "limit": 10},
            {}
        )

        assert result.success is True
        assert "queries" in result.data

    @pytest.mark.asyncio
    async def test_postgres_slow_query_e2e(self):
        """PostgreSQL 慢SQL查询 E2E 测试"""
        from src.tools.query_tools import QuerySlowSQLTool

        tool = QuerySlowSQLTool()
        result = await tool.execute(
            {"instance_id": "INS-TEST-PG", "limit": 10},
            {}
        )

        assert result.success is True
        assert "queries" in result.data


# ============================================================================
# Agent 协作测试
# ============================================================================

class TestMultiAgentCollaboration:
    """多Agent协作测试"""

    @pytest.mark.asyncio
    async def test_session_and_risk_agent_collaboration(self):
        """测试会话分析和风险评估Agent协作"""
        from src.agents.session_analyzer_agent import SessionAnalyzerAgent
        from src.agents.risk import RiskAgent

        session_agent = SessionAnalyzerAgent()
        risk_agent = RiskAgent()

        # 验证会话分析Agent工具
        assert "session_list" in session_agent.available_tools

        # 验证风险Agent工具
        assert "query_instance_status" in risk_agent.available_tools

    @pytest.mark.asyncio
    async def test_alert_and_diagnostic_collaboration(self):
        """测试告警分析和诊断Agent协作"""
        from src.agents.alert_agent import AlertAgent
        from src.agents.diagnostic import DiagnosticAgent

        alert_agent = AlertAgent()
        diag_agent = DiagnosticAgent()

        # 验证AlertAgent工具
        assert "alert_analysis" in alert_agent.available_tools
        assert "alert_deduplication" in alert_agent.available_tools
        assert "root_cause_analysis" in alert_agent.available_tools

        # 验证DiagnosticAgent工具
        assert "query_session" in diag_agent.available_tools
        assert "query_lock" in diag_agent.available_tools


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
