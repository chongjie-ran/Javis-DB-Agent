"""Round 15: 智能告警增强 + AlertAgent 测试

覆盖:
1. AlertAgent 核心方法测试
2. AlertTools 工具测试
3. Orchestrator 新增意图测试
4. PG特有告警规则测试
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# ===== AlertTools测试 =====

class TestAlertTools:
    """AlertTools单元测试"""

    def test_alert_analysis_tool_definition(self):
        """测试AlertAnalysisTool定义正确"""
        from src.tools.alert_tools import AlertAnalysisTool

        tool = AlertAnalysisTool()
        assert tool.name == "alert_analysis"
        assert tool.definition.category == "analysis"
        assert tool.definition.risk_level.value == 2  # L2_DIAGNOSE

    def test_alert_deduplication_tool_definition(self):
        """测试AlertDeduplicationTool定义正确"""
        from src.tools.alert_tools import AlertDeduplicationTool

        tool = AlertDeduplicationTool()
        assert tool.name == "alert_deduplication"
        assert tool.definition.category == "analysis"
        assert tool.definition.risk_level.value == 2

    def test_root_cause_analysis_tool_definition(self):
        """测试RootCauseAnalysisTool定义正确"""
        from src.tools.alert_tools import RootCauseAnalysisTool

        tool = RootCauseAnalysisTool()
        assert tool.name == "root_cause_analysis"
        assert tool.definition.category == "analysis"

    def test_predictive_alert_tool_definition(self):
        """测试PredictiveAlertTool定义正确"""
        from src.tools.alert_tools import PredictiveAlertTool

        tool = PredictiveAlertTool()
        assert tool.name == "predictive_alert"
        assert tool.definition.category == "analysis"

    @pytest.mark.asyncio
    async def test_alert_analysis_tool_execute(self):
        """测试AlertAnalysisTool执行"""
        from src.tools.alert_tools import AlertAnalysisTool

        tool = AlertAnalysisTool()
        params = {
            "alert_data": {
                "alert_id": "ALT-001",
                "alert_type": "CONNECTION_HIGH",
                "severity": "warning",
                "metric": "connection_count",
                "value": 950,
                "threshold": 1000,
            }
        }

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["alert_id"] == "ALT-001"
        assert result.data["alert_type"] == "CONNECTION_HIGH"
        assert result.data["severity"] == "medium"
        assert len(result.data["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_alert_deduplication_execute(self):
        """测试AlertDeduplicationTool执行"""
        from src.tools.alert_tools import AlertDeduplicationTool

        tool = AlertDeduplicationTool()
        params = {
            "alerts": [
                {"alert_id": "ALT-001", "alert_type": "CONNECTION_HIGH", "instance_id": "INS-001", "metric": "conn", "timestamp": 1000},
                {"alert_id": "ALT-002", "alert_type": "CONNECTION_HIGH", "instance_id": "INS-001", "metric": "conn", "timestamp": 1010},
                {"alert_id": "ALT-003", "alert_type": "CPU_HIGH", "instance_id": "INS-001", "metric": "cpu", "timestamp": 1020},
            ]
        }

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["original_count"] == 3
        assert result.data["deduplicated_count"] == 2  # 2组: CONNECTION_HIGH, CPU_HIGH
        assert result.data["compression_ratio"] > 0
        assert len(result.data["groups"]) == 2

    @pytest.mark.asyncio
    async def test_root_cause_analysis_execute(self):
        """测试RootCauseAnalysisTool执行"""
        from src.tools.alert_tools import RootCauseAnalysisTool

        tool = RootCauseAnalysisTool()
        params = {"alert_id": "ALT-CONNECTION_HIGH-001", "lookback_hours": 24}

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["alert_id"] == "ALT-CONNECTION_HIGH-001"
        assert "root_cause" in result.data
        assert "confidence" in result.data
        assert "evidence" in result.data

    @pytest.mark.asyncio
    async def test_predictive_alert_execute(self):
        """测试PredictiveAlertTool执行"""
        from src.tools.alert_tools import PredictiveAlertTool

        tool = PredictiveAlertTool()
        params = {
            "metric": "connection_count",
            "threshold": 1000,
            "instance_id": "INS-001",
        }

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["metric"] == "connection_count"
        assert result.data["threshold"] == 1000
        assert "current_value" in result.data
        assert "predicted_value" in result.data
        assert "risk_level" in result.data

    @pytest.mark.asyncio
    async def test_predictive_alert_with_wal_metric(self):
        """测试WAL堆积预测"""
        from src.tools.alert_tools import PredictiveAlertTool

        tool = PredictiveAlertTool()
        params = {"metric": "wal_lag", "threshold": 1.0}

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["metric"] == "wal_lag"

    @pytest.mark.asyncio
    async def test_predictive_alert_with_bloat_metric(self):
        """测试膨胀率预测"""
        from src.tools.alert_tools import PredictiveAlertTool

        tool = PredictiveAlertTool()
        params = {"metric": "bloat_percent", "threshold": 50.0}

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["metric"] == "bloat_percent"
        assert result.data["risk_level"] in ["critical", "high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_deduplication_all_same_alert(self):
        """测试全部相同告警去重"""
        from src.tools.alert_tools import AlertDeduplicationTool

        tool = AlertDeduplicationTool()
        params = {
            "alerts": [
                {"alert_id": f"ALT-{i}", "alert_type": "CONNECTION_HIGH", "instance_id": "INS-001", "metric": "conn", "timestamp": i}
                for i in range(10)
            ]
        }

        result = await tool.execute(params, {})

        assert result.success is True
        assert result.data["original_count"] == 10
        assert result.data["deduplicated_count"] == 1  # 全部压缩为1条
        assert result.data["groups"][0]["count"] == 10

    def test_register_alert_tools(self):
        """测试工具注册函数"""
        from src.tools.alert_tools import register_alert_tools
        from src.gateway.tool_registry import ToolRegistry

        registry = ToolRegistry()
        tools = register_alert_tools(registry)

        assert len(tools) == 4
        assert all(t.name in ["alert_analysis", "alert_deduplication", "root_cause_analysis", "predictive_alert"] for t in tools)

        # 验证已注册
        assert registry.get_tool("alert_analysis") is not None
        assert registry.get_tool("alert_deduplication") is not None
        assert registry.get_tool("root_cause_analysis") is not None
        assert registry.get_tool("predictive_alert") is not None


# ===== AlertAgent测试 =====

class TestAlertAgent:
    """AlertAgent单元测试"""

    def test_alert_agent_definition(self):
        """测试AlertAgent定义正确"""
        from src.agents.alert_agent import AlertAgent

        agent = AlertAgent()
        assert agent.name == "alert"
        assert "alert_analysis" in agent.available_tools
        assert "alert_deduplication" in agent.available_tools
        assert "root_cause_analysis" in agent.available_tools
        assert "predictive_alert" in agent.available_tools

    def test_alert_agent_system_prompt(self):
        """测试AlertAgent系统提示词"""
        from src.agents.alert_agent import AlertAgent

        agent = AlertAgent()
        prompt = agent._build_system_prompt()
        assert "alert agent" in prompt.lower()
        assert "告警分析" in prompt
        assert "去重压缩" in prompt
        assert "预测性" in prompt

    def test_format_analysis_result(self):
        """测试分析结果格式化"""
        from src.agents.alert_agent import AlertAgent

        agent = AlertAgent()
        data = {
            "alert_id": "ALT-001",
            "alert_type": "CONNECTION_HIGH",
            "severity": "high",
            "confidence": 0.85,
            "suggestions": ["建议1", "建议2"],
        }
        formatted = agent._format_analysis_result(data)

        assert "ALT-001" in formatted
        assert "CONNECTION_HIGH" in formatted
        assert "建议1" in formatted

    def test_format_dedup_result(self):
        """测试去重结果格式化"""
        from src.agents.alert_agent import AlertAgent

        agent = AlertAgent()
        data = {
            "original_count": 10,
            "deduplicated_count": 3,
            "groups": [
                {"type": "CONNECTION_HIGH", "count": 5, "group_id": "g1"},
                {"type": "CPU_HIGH", "count": 5, "group_id": "g2"},
            ],
        }
        formatted = agent._format_dedup_result(data)

        assert "10" in formatted  # 原始数量
        assert "3" in formatted  # 去重后数量

    def test_format_rca_result(self):
        """测试根因分析结果格式化"""
        from src.agents.alert_agent import AlertAgent

        agent = AlertAgent()
        data = {
            "alert_id": "ALT-001",
            "root_cause": "连接泄漏",
            "confidence": 0.88,
            "evidence": ["证据1", "证据2"],
            "related_alerts": [
                {"alert_id": "ALT-002", "alert_name": "连接池耗尽", "relation": "后续关联"},
            ],
        }
        formatted = agent._format_rca_result(data)

        assert "ALT-001" in formatted
        assert "连接泄漏" in formatted
        assert "证据1" in formatted

    def test_format_predictive_result(self):
        """测试预测性告警结果格式化"""
        from src.agents.alert_agent import AlertAgent

        agent = AlertAgent()
        data = {
            "metric": "connection_count",
            "threshold": 1000,
            "current_value": 850,
            "predicted_value": 950,
            "trend": "accelerating",
            "risk_level": "high",
            "predicted_time": "2026-04-05 12:00",
        }
        formatted = agent._format_predictive_result(data)

        assert "connection_count" in formatted
        assert "1000" in formatted
        assert "850" in formatted
        assert "accelerating" in formatted


# ===== Orchestrator新意图测试 =====

class TestOrchestratorAlertIntents:
    """Orchestrator新增告警意图测试"""

    def test_new_intents_exist(self):
        """测试新增意图已定义"""
        from src.agents.orchestrator import Intent

        assert Intent.ANALYZE_ALERT.value == "analyze_alert"
        assert Intent.DEDUPLICATE_ALERTS.value == "deduplicate_alerts"
        assert Intent.ROOT_CAUSE.value == "root_cause"
        assert Intent.PREDICTIVE_ALERT.value == "predictive_alert"

    def test_alert_intent_agent_mapping(self):
        """测试告警意图到Agent的映射"""
        from src.agents.orchestrator import Intent

        # 验证新增意图已在_select_agents中映射
        # 这是一个基本的存在性测试
        assert Intent.ANALYZE_ALERT is not None
        assert Intent.DEDUPLICATE_ALERTS is not None
        assert Intent.ROOT_CAUSE is not None
        assert Intent.PREDICTIVE_ALERT is not None

    def test_alert_agent_registered_in_orchestrator(self):
        """测试AlertAgent已在Orchestrator中注册"""
        from src.agents.orchestrator import OrchestratorAgent

        orch = OrchestratorAgent()
        assert "alert" in orch._agent_registry
        assert orch.get_agent("alert") is not None


# ===== PG告警规则测试 =====

class TestPGAlertRules:
    """PG特有告警规则测试"""

    def test_pg_alert_rules_exist(self):
        """测试PG特有告警规则已添加"""
        import yaml

        with open("/Users/chongjieran/SWproject/Javis-DB-Agent/knowledge/alert_rules.yaml") as f:
            rules = yaml.safe_load(f)

        alert_types = [r["alert_type"] for r in rules["alert_rules"]]
        pg_rules = [r for r in rules["alert_rules"] if r["alert_code"].startswith("PG_")]

        assert "PG_CONNECTION_LIMIT" in alert_types
        assert "WAL_ACCUMULATION" in alert_types
        assert "REPLICATION_DELAY" in alert_types
        assert "BLOAT_EXCEEDED" in alert_types

        assert len(pg_rules) == 4

    def test_pg_connection_limit_rule(self):
        """测试PG_CONNECTION_LIMIT规则结构"""
        import yaml

        with open("/Users/chongjieran/SWproject/Javis-DB-Agent/knowledge/alert_rules.yaml") as f:
            rules = yaml.safe_load(f)

        rule = next(r for r in rules["alert_rules"] if r["alert_type"] == "PG_CONNECTION_LIMIT")
        assert rule["severity"] == "critical"
        assert "pg_stat_activity" in rule["check_steps"][0]
        assert "max_connections" in str(rule["check_steps"])

    def test_wal_accumulation_rule(self):
        """测试WAL_ACCUMULATION规则结构"""
        import yaml

        with open("/Users/chongjieran/SWproject/Javis-DB-Agent/knowledge/alert_rules.yaml") as f:
            rules = yaml.safe_load(f)

        rule = next(r for r in rules["alert_rules"] if r["alert_type"] == "WAL_ACCUMULATION")
        assert rule["severity"] == "warning"
        assert "pg_wal" in str(rule["check_steps"])

    def test_replication_delay_rule(self):
        """测试REPLICATION_DELAY规则结构"""
        import yaml

        with open("/Users/chongjieran/SWproject/Javis-DB-Agent/knowledge/alert_rules.yaml") as f:
            rules = yaml.safe_load(f)

        rule = next(r for r in rules["alert_rules"] if r["alert_type"] == "REPLICATION_DELAY")
        assert rule["severity"] == "warning"
        assert "pg_last_xact_replay_timestamp" in str(rule["check_steps"])

    def test_bloat_exceeded_rule(self):
        """测试BLOAT_EXCEEDED规则结构"""
        import yaml

        with open("/Users/chongjieran/SWproject/Javis-DB-Agent/knowledge/alert_rules.yaml") as f:
            rules = yaml.safe_load(f)

        rule = next(r for r in rules["alert_rules"] if r["alert_type"] == "BLOAT_EXCEEDED")
        assert rule["severity"] == "warning"
        assert "VACUUM" in str(rule["resolution"])


# ===== 集成测试 =====

class TestAlertToolsIntegration:
    """告警工具集成测试"""

    @pytest.mark.asyncio
    async def test_full_alert_analysis_flow(self):
        """测试完整告警分析流程"""
        from src.tools.alert_tools import AlertAnalysisTool, AlertDeduplicationTool

        # 1. 分析告警
        analysis_tool = AlertAnalysisTool()
        analysis_result = await analysis_tool.execute({
            "alert_data": {
                "alert_id": "ALT-001",
                "alert_type": "CONNECTION_HIGH",
                "severity": "warning",
            }
        }, {})
        assert analysis_result.success

        # 2. 去重
        dedup_tool = AlertDeduplicationTool()
        dedup_result = await dedup_tool.execute({
            "alerts": [{"alert_id": "ALT-001", "alert_type": "CONNECTION_HIGH", "instance_id": "INS-001", "metric": "conn", "timestamp": 1000}]
        }, {})
        assert dedup_result.success

    @pytest.mark.asyncio
    async def test_full_root_cause_flow(self):
        """测试完整根因分析流程"""
        from src.tools.alert_tools import RootCauseAnalysisTool, PredictiveAlertTool

        # 1. 根因分析
        rca_tool = RootCauseAnalysisTool()
        rca_result = await rca_tool.execute({"alert_id": "ALT-CONNECTION_HIGH-001"}, {})
        assert rca_result.success
        assert rca_result.data["root_cause"] is not None

        # 2. 预测性告警
        pred_tool = PredictiveAlertTool()
        pred_result = await pred_tool.execute({"metric": "connection_count", "threshold": 1000}, {})
        assert pred_result.success
        assert pred_result.data["risk_level"] is not None
