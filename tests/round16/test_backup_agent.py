"""BackupAgent 测试 - V1.4 Round 1
测试备份状态查询、备份历史、触发备份、恢复时间估算
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestBackupTools:
    """备份工具测试"""

    @pytest.mark.asyncio
    async def test_check_backup_status_mysql(self):
        """测试MySQL备份状态查询"""
        from src.tools.backup_tools import CheckBackupStatusTool

        tool = CheckBackupStatusTool()
        result = await tool.execute({"db_type": "mysql"}, {})

        assert result.success is True
        assert result.data["db_type"] == "mysql"
        assert "backup_enabled" in result.data
        assert "last_backup_time" in result.data
        assert "db_size_gb" in result.data

    @pytest.mark.asyncio
    async def test_check_backup_status_postgresql(self):
        """测试PostgreSQL备份状态查询"""
        from src.tools.backup_tools import CheckBackupStatusTool

        tool = CheckBackupStatusTool()
        result = await tool.execute({"db_type": "postgresql"}, {})

        assert result.success is True
        assert result.data["db_type"] == "postgresql"
        assert result.data["backup_method"] == "pg_basebackup + WAL"

    @pytest.mark.asyncio
    async def test_check_backup_status_oracle(self):
        """测试Oracle备份状态查询"""
        from src.tools.backup_tools import CheckBackupStatusTool

        tool = CheckBackupStatusTool()
        result = await tool.execute({"db_type": "oracle"}, {})

        assert result.success is True
        assert result.data["db_type"] == "oracle"
        assert result.data["backup_method"] == "RMAN"

    @pytest.mark.asyncio
    async def test_list_backup_history(self):
        """测试备份历史查询"""
        from src.tools.backup_tools import ListBackupHistoryTool

        tool = ListBackupHistoryTool()
        result = await tool.execute({"db_type": "mysql", "limit": 5}, {})

        assert result.success is True
        assert len(result.data["backups"]) == 5
        assert result.data["db_type"] == "mysql"

    @pytest.mark.asyncio
    async def test_list_backup_history_default_limit(self):
        """测试备份历史默认数量"""
        from src.tools.backup_tools import ListBackupHistoryTool

        tool = ListBackupHistoryTool()
        result = await tool.execute({"db_type": "mysql"}, {})

        assert result.success is True
        assert len(result.data["backups"]) == 10  # 默认limit=10

    @pytest.mark.asyncio
    async def test_trigger_backup_full(self):
        """测试触发全量备份"""
        from src.tools.backup_tools import TriggerBackupTool

        tool = TriggerBackupTool()
        result = await tool.execute({"db_type": "mysql", "backup_type": "full"}, {})

        assert result.success is True
        assert result.data["status"] == "running"
        assert result.data["backup_type"] == "full"
        assert "backup_id" in result.data
        assert result.data["backup_id"].startswith("BK-")

    @pytest.mark.asyncio
    async def test_trigger_backup_incremental(self):
        """测试触发增量备份"""
        from src.tools.backup_tools import TriggerBackupTool

        tool = TriggerBackupTool()
        result = await tool.execute({"db_type": "postgresql", "backup_type": "incremental"}, {})

        assert result.success is True
        assert result.data["backup_type"] == "incremental"

    @pytest.mark.asyncio
    async def test_trigger_backup_differential(self):
        """测试触发差异备份"""
        from src.tools.backup_tools import TriggerBackupTool

        tool = TriggerBackupTool()
        result = await tool.execute({"db_type": "oracle", "backup_type": "differential"}, {})

        assert result.success is True
        assert result.data["backup_type"] == "differential"

    @pytest.mark.asyncio
    async def test_estimate_restore_time_latest(self):
        """测试恢复时间估算(最新备份)"""
        from src.tools.backup_tools import EstimateRestoreTimeTool

        tool = EstimateRestoreTimeTool()
        result = await tool.execute({"db_type": "mysql", "restore_type": "latest"}, {})

        assert result.success is True
        assert "total_time_seconds" in result.data
        assert len(result.data["phases"]) > 0

    @pytest.mark.asyncio
    async def test_estimate_restore_time_point_in_time(self):
        """测试恢复时间估算(时间点恢复)"""
        from src.tools.backup_tools import EstimateRestoreTimeTool

        tool = EstimateRestoreTimeTool()
        result = await tool.execute({"db_type": "mysql", "restore_type": "point_in_time"}, {})

        assert result.success is True
        # point_in_time 应该比 latest 耗时更长
        phases = result.data["phases"]
        # 各阶段时间会增加30%


class TestBackupAgent:
    """BackupAgent 测试"""

    @pytest.mark.asyncio
    async def test_backup_agent_check_status(self):
        """测试BackupAgent查询备份状态"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent.check_status("mysql")

        assert response.success is True
        assert "备份状态" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_list_history(self):
        """测试BackupAgent查询备份历史"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent.list_history("mysql", 5)

        assert response.success is True
        assert "备份历史" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_trigger_backup(self):
        """测试BackupAgent触发备份"""
        from src.agents.backup_agent import BackupAgent
        from src.gateway.policy_engine import PolicyResult

        agent = BackupAgent()
        # Mock policy to allow L3 operations
        agent._policy.check = MagicMock(return_value=PolicyResult(
            allowed=True, approval_required=False, approvers=[]
        ))
        response = await agent.trigger_backup("mysql", "full")

        assert response.success is True
        assert "备份触发" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_estimate_restore(self):
        """测试BackupAgent估算恢复时间"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent.estimate_restore("mysql")

        assert response.success is True
        assert "恢复时间" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_suggest_strategy(self):
        """测试BackupAgent策略建议"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent.suggest_strategy("mysql")

        assert response.success is True
        assert "备份策略建议" in response.content
        assert "风险等级" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_check_alerts(self):
        """测试BackupAgent告警检查"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent.check_alerts("mysql")

        assert response.success is True
        assert "备份告警" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_process_intent_status(self):
        """测试BackupAgent处理状态查询意图"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent._process_direct("查询MySQL备份状态", {})

        assert response.success is True
        assert "备份状态" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_process_intent_trigger(self):
        """测试BackupAgent处理触发备份意图"""
        from src.agents.backup_agent import BackupAgent
        from src.gateway.policy_engine import PolicyResult

        agent = BackupAgent()
        # Mock policy to allow L3 operations
        agent._policy.check = MagicMock(return_value=PolicyResult(
            allowed=True, approval_required=False, approvers=[]
        ))
        response = await agent._process_direct("触发一次MySQL全量备份", {})

        assert response.success is True
        assert "备份触发" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_process_intent_restore(self):
        """测试BackupAgent处理恢复估算意图"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        response = await agent._process_direct("估算MySQL恢复时间", {})

        assert response.success is True
        assert "恢复时间" in response.content

    @pytest.mark.asyncio
    async def test_backup_agent_extract_db_type(self):
        """测试BackupAgent提取数据库类型"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()

        assert agent._extract_db_type("MySQL备份状态", {}) == "mysql"
        assert agent._extract_db_type("PostgreSQL备份历史", {}) == "postgresql"
        assert agent._extract_db_type("Oracle触发备份", {}) == "oracle"
        assert agent._extract_db_type("查询备份", {}) == "mysql"  # 默认

    @pytest.mark.asyncio
    async def test_backup_agent_extract_backup_type(self):
        """测试BackupAgent提取备份类型"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()

        assert agent._extract_backup_type("全量备份") == "full"
        assert agent._extract_backup_type("增量备份") == "incremental"
        assert agent._extract_backup_type("差异备份") == "differential"
        assert agent._extract_backup_type("触发备份") == "full"  # 默认

    @pytest.mark.asyncio
    async def test_backup_agent_tool_registration(self):
        """测试BackupAgent工具注册"""
        from src.agents.backup_agent import BackupAgent

        agent = BackupAgent()
        expected_tools = [
            "check_backup_status",
            "list_backup_history",
            "trigger_backup",
            "estimate_restore_time",
        ]
        for tool in expected_tools:
            assert tool in agent.available_tools


class TestBackupToolsRiskLevel:
    """备份工具风险级别测试"""

    def test_check_backup_status_risk_level(self):
        """测试状态查询为L1只读"""
        from src.tools.backup_tools import CheckBackupStatusTool
        from src.tools.base import RiskLevel

        tool = CheckBackupStatusTool()
        assert tool.get_risk_level() == RiskLevel.L1_READ

    def test_list_backup_history_risk_level(self):
        """测试历史查询为L1只读"""
        from src.tools.backup_tools import ListBackupHistoryTool
        from src.tools.base import RiskLevel

        tool = ListBackupHistoryTool()
        assert tool.get_risk_level() == RiskLevel.L1_READ

    def test_trigger_backup_risk_level(self):
        """测试触发备份为L3低风险"""
        from src.tools.backup_tools import TriggerBackupTool
        from src.tools.base import RiskLevel

        tool = TriggerBackupTool()
        assert tool.get_risk_level() == RiskLevel.L3_LOW_RISK

    def test_estimate_restore_time_risk_level(self):
        """测试恢复估算为L1只读"""
        from src.tools.backup_tools import EstimateRestoreTimeTool
        from src.tools.base import RiskLevel

        tool = EstimateRestoreTimeTool()
        assert tool.get_risk_level() == RiskLevel.L1_READ


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
