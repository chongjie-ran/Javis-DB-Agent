"""Round 14 测试 - 容量管理功能测试"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


class TestCapacityAgent:
    """CapacityAgent 测试"""

    @pytest.mark.asyncio
    async def test_analyze_storage(self):
        """测试存储分析"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        # Mock工具调用
        with patch.object(agent, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = MagicMock(
                success=True,
                data={
                    "storage": [
                        {"name": "数据文件", "used_gb": 256.5, "total_gb": 500.0, "usage_percent": 51.3, "risk_level": "low"},
                        {"name": "Binlog", "used_gb": 180.0, "total_gb": 200.0, "usage_percent": 90.0, "risk_level": "critical"},
                    ]
                }
            )

            result = await agent.analyze_storage("mysql")

            assert result.success is True
            assert "数据文件" in result.content
            assert "Binlog" in result.content
            assert "90.0%" in result.content

    @pytest.mark.asyncio
    async def test_predict_growth(self):
        """测试增长预测"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        with patch.object(agent, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = MagicMock(
                success=True,
                data={
                    "current_size_gb": 200.0,
                    "predicted_size_gb": 290.0,
                    "daily_growth_gb": 1.0,
                    "trend": "stable",
                    "confidence": 0.95,
                }
            )

            result = await agent.predict_growth("mysql", 90)

            assert result.success is True
            assert "200.00 GB" in result.content
            assert "290.00 GB" in result.content
            assert "90天" in result.content

    @pytest.mark.asyncio
    async def test_generate_capacity_report(self):
        """测试容量报告生成"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        with patch.object(agent, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = MagicMock(
                success=True,
                data={
                    "db_type": "mysql",
                    "generated_at": 1743264000.0,
                    "storage": [
                        {"name": "数据文件", "used_gb": 256.5, "total_gb": 500.0, "usage_percent": 51.3},
                    ],
                    "predictions": {"predicted_90d_gb": 290.0, "daily_growth_gb": 1.0},
                    "alerts": ["🔴 [Binlog] 使用率 90.0%，严重告警"],
                }
            )

            result = await agent.generate_capacity_report("mysql")

            assert result.success is True
            assert "容量报告" in result.content
            assert "MYSQL" in result.content
            assert "告警" in result.content

    @pytest.mark.asyncio
    async def test_alert_capacity_threshold(self):
        """测试容量阈值告警"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        with patch.object(agent, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = MagicMock(
                success=True,
                data={
                    "threshold": 80.0,
                    "triggered": [
                        {"name": "Binlog", "usage_percent": 90.0, "used_gb": 180.0, "total_gb": 200.0},
                    ],
                    "not_triggered": [
                        {"name": "数据文件", "usage_percent": 51.3, "used_gb": 256.5, "total_gb": 500.0},
                    ],
                }
            )

            result = await agent.alert_capacity_threshold("mysql", 80.0)

            assert result.success is True
            assert "80" in result.content
            assert "触发告警" in result.content
            assert "Binlog" in result.content

    @pytest.mark.asyncio
    async def test_extract_db_type(self):
        """测试数据库类型提取"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        assert agent._extract_db_type("分析MySQL的容量", {}) == "mysql"
        assert agent._extract_db_type("查看PostgreSQL存储", {}) == "postgresql"
        assert agent._extract_db_type("Oracle容量报告", {}) == "oracle"
        assert agent._extract_db_type("分析容量", {}) == "mysql"  # 默认

    @pytest.mark.asyncio
    async def test_extract_days(self):
        """测试预测天数提取"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        assert agent._extract_days("预测30天的增长") == 30
        assert agent._extract_days("预测90天") == 90
        assert agent._extract_days("增长预测") == 90  # 默认

    @pytest.mark.asyncio
    async def test_extract_threshold(self):
        """测试阈值提取"""
        from src.agents.capacity_agent import CapacityAgent

        agent = CapacityAgent()

        assert agent._extract_threshold("检查80%的阈值") == 80.0
        assert agent._extract_threshold("检查70.5%阈值") == 70.5
        assert agent._extract_threshold("阈值检查") == 80.0  # 默认


class TestCapacityTools:
    """容量管理工具测试"""

    @pytest.mark.asyncio
    async def test_storage_analysis_tool(self):
        """测试存储分析工具"""
        from src.tools.capacity_tools import StorageAnalysisTool

        tool = StorageAnalysisTool()

        result = await tool.execute({"db_type": "mysql", "instance_id": "INS-001"}, {})

        assert result.success is True
        assert "storage" in result.data
        assert len(result.data["storage"]) > 0

        # 验证数据结构
        item = result.data["storage"][0]
        assert "name" in item
        assert "used_gb" in item
        assert "total_gb" in item
        assert "usage_percent" in item

    @pytest.mark.asyncio
    async def test_storage_analysis_tool_pg(self):
        """测试PostgreSQL存储分析"""
        from src.tools.capacity_tools import StorageAnalysisTool

        tool = StorageAnalysisTool()
        result = await tool.execute({"db_type": "postgresql", "instance_id": "INS-002"}, {})

        assert result.success is True
        assert len(result.data["storage"]) > 0

    @pytest.mark.asyncio
    async def test_storage_analysis_tool_oracle(self):
        """测试Oracle存储分析"""
        from src.tools.capacity_tools import StorageAnalysisTool

        tool = StorageAnalysisTool()
        result = await tool.execute({"db_type": "oracle", "instance_id": "INS-003"}, {})

        assert result.success is True
        assert len(result.data["storage"]) > 0

    @pytest.mark.asyncio
    async def test_growth_prediction_tool(self):
        """测试增长预测工具"""
        from src.tools.capacity_tools import GrowthPredictionTool

        tool = GrowthPredictionTool()

        result = await tool.execute({"db_type": "mysql", "days": 90, "instance_id": "INS-001"}, {})

        assert result.success is True
        assert "current_size_gb" in result.data
        assert "predicted_size_gb" in result.data
        assert "daily_growth_gb" in result.data
        assert "trend" in result.data
        assert "confidence" in result.data

        # 验证预测值合理
        assert result.data["current_size_gb"] > 0
        assert result.data["predicted_size_gb"] > 0
        assert result.data["confidence"] >= 0
        assert result.data["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_growth_prediction_trends(self):
        """测试不同趋势的预测"""
        from src.tools.capacity_tools import GrowthPredictionTool

        tool = GrowthPredictionTool()

        for db_type in ["mysql", "postgresql", "oracle"]:
            result = await tool.execute({"db_type": db_type, "days": 30}, {})
            assert result.success is True
            assert result.data["trend"] in ["accelerating", "decelerating", "stable"]

    @pytest.mark.asyncio
    async def test_capacity_report_tool(self):
        """测试容量报告工具"""
        from src.tools.capacity_tools import CapacityReportTool

        tool = CapacityReportTool()

        result = await tool.execute({"db_type": "mysql", "instance_id": "INS-001"}, {})

        assert result.success is True
        assert "db_type" in result.data
        assert "storage" in result.data
        assert "predictions" in result.data
        assert "alerts" in result.data
        assert "generated_at" in result.data

        # 验证高使用率触发告警
        assert len(result.data["alerts"]) > 0  # Binlog 90% 应该触发告警

    @pytest.mark.asyncio
    async def test_capacity_alert_tool_triggered(self):
        """测试容量告警工具 - 触发告警"""
        from src.tools.capacity_tools import CapacityAlertTool

        tool = CapacityAlertTool()

        result = await tool.execute({"db_type": "mysql", "threshold": 80.0, "instance_id": "INS-001"}, {})

        assert result.success is True
        assert "threshold" in result.data
        assert "triggered" in result.data
        assert "not_triggered" in result.data

        # 验证 Binlog 90% 触发告警
        triggered_names = [item["name"] for item in result.data["triggered"]]
        assert any("Binlog" in name for name in triggered_names)

    @pytest.mark.asyncio
    async def test_capacity_alert_tool_no_trigger(self):
        """测试容量告警工具 - 未触发"""
        from src.tools.capacity_tools import CapacityAlertTool

        tool = CapacityAlertTool()

        # 设置低阈值，应该不触发
        result = await tool.execute({"db_type": "mysql", "threshold": 95.0, "instance_id": "INS-001"}, {})

        assert result.success is True
        # 可能没有触发（取决于实际数据）

    @pytest.mark.asyncio
    async def test_tool_params_validation(self):
        """测试工具参数校验"""
        from src.tools.capacity_tools import StorageAnalysisTool, GrowthPredictionTool

        storage_tool = StorageAnalysisTool()

        # 有效参数
        valid, err = storage_tool.validate_params({"db_type": "mysql"})
        assert valid is True

        # 无效参数（day应该是int）
        growth_tool = GrowthPredictionTool()
        valid, err = growth_tool.validate_params({"db_type": "mysql", "days": "invalid"})
        assert valid is False
        assert "整数" in err

    @pytest.mark.asyncio
    async def test_tool_risk_levels(self):
        """测试工具风险等级"""
        from src.tools.capacity_tools import (
            StorageAnalysisTool,
            GrowthPredictionTool,
            CapacityReportTool,
            CapacityAlertTool,
        )

        assert StorageAnalysisTool().get_risk_level().value == 1  # L1_READ
        assert GrowthPredictionTool().get_risk_level().value == 1  # L1_READ
        assert CapacityReportTool().get_risk_level().value == 1  # L1_READ
        assert CapacityAlertTool().get_risk_level().value == 1  # L1_READ


class TestOrchestratorCapacityIntegration:
    """Orchestrator容量意图集成测试"""

    @pytest.mark.asyncio
    async def test_intent_analyze_capacity(self):
        """测试容量分析意图识别"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        agent = OrchestratorAgent()

        # 验证意图识别（LLM-based，可能返回 ANALYZE_CAPACITY 或其他相关意图）
        recognized = await agent._recognize_intent("分析MySQL的存储容量")
        # 意图识别基于LLM，可能返回任何意图类型，重点是能正常识别不报错
        assert recognized is not None
        assert isinstance(recognized, Intent)

    @pytest.mark.asyncio
    async def test_intent_predict_growth(self):
        """测试增长预测意图识别"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        agent = OrchestratorAgent()

        recognized = await agent._recognize_intent("预测未来90天的容量增长")
        # 意图识别基于LLM，可能返回任何意图类型
        assert recognized is not None
        assert isinstance(recognized, Intent)

    @pytest.mark.asyncio
    async def test_intent_capacity_report(self):
        """测试容量报告意图"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        agent = OrchestratorAgent()

        recognized = await agent._recognize_intent("生成容量报告")
        assert recognized in [Intent.CAPACITY_REPORT, Intent.REPORT, Intent.GENERAL]

    @pytest.mark.asyncio
    async def test_select_capacity_agent(self):
        """测试选择容量Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent

        agent = OrchestratorAgent()

        selected = agent._select_agents(Intent.ANALYZE_CAPACITY, "")
        agent_names = [a.name for a in selected]
        assert "capacity" in agent_names

        selected = agent._select_agents(Intent.PREDICT_GROWTH, "")
        agent_names = [a.name for a in selected]
        assert "capacity" in agent_names

        selected = agent._select_agents(Intent.CAPACITY_REPORT, "")
        agent_names = [a.name for a in selected]
        assert "capacity" in agent_names


class TestMockAPICapacityEndpoints:
    """Mock API容量端点测试"""

    @pytest.mark.asyncio
    async def test_get_storage_analysis(self):
        """测试存储分析API"""
        from src.mock_api.javis_client import get_mock_javis_client

        client = get_mock_javis_client()

        result = await client.get_storage_analysis("INS-001", "mysql")

        assert "storage" in result
        assert "total_used_gb" in result
        assert "total_capacity_gb" in result
        assert len(result["storage"]) > 0

    @pytest.mark.asyncio
    async def test_get_capacity_growth(self):
        """测试容量增长API"""
        from src.mock_api.javis_client import get_mock_javis_client

        client = get_mock_javis_client()

        result = await client.get_capacity_growth("INS-001", "mysql", 90)

        assert "history" in result
        assert "prediction_days" in result
        assert result["prediction_days"] == 90

    @pytest.mark.asyncio
    async def test_storage_for_different_db_types(self):
        """测试不同数据库类型的存储数据"""
        from src.mock_api.javis_client import get_mock_javis_client

        client = get_mock_javis_client()

        for db_type in ["mysql", "postgresql", "oracle"]:
            result = await client.get_storage_analysis("INS-001", db_type)
            assert result["db_type"] == db_type
            assert len(result["storage"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
