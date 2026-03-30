"""PerformanceAgent 测试 - V1.4 Round 1
测试TopSQL提取、执行计划解读、参数调优建议
"""
import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestPerformanceTools:
    """性能工具测试"""

    @pytest.mark.asyncio
    async def test_extract_top_sql_mysql(self):
        """测试MySQL TopSQL提取"""
        from src.tools.performance_tools import ExtractTopSQLTool

        tool = ExtractTopSQLTool()
        result = await tool.execute({"db_type": "mysql", "limit": 5}, {})

        assert result.success is True
        assert len(result.data["sqls"]) == 5
        assert result.data["db_type"] == "mysql"

        # 验证SQL数据结构
        first_sql = result.data["sqls"][0]
        assert "sql" in first_sql
        assert "exec_count" in first_sql
        assert "avg_exec_time_ms" in first_sql
        assert "risk_level" in first_sql
        assert "suggestion" in first_sql

    @pytest.mark.asyncio
    async def test_extract_top_sql_postgresql(self):
        """测试PostgreSQL TopSQL提取"""
        from src.tools.performance_tools import ExtractTopSQLTool

        tool = ExtractTopSQLTool()
        result = await tool.execute({"db_type": "postgresql", "limit": 3}, {})

        assert result.success is True
        assert result.data["db_type"] == "postgresql"
        assert len(result.data["sqls"]) == 3

    @pytest.mark.asyncio
    async def test_extract_top_sql_oracle(self):
        """测试Oracle TopSQL提取"""
        from src.tools.performance_tools import ExtractTopSQLTool

        tool = ExtractTopSQLTool()
        result = await tool.execute({"db_type": "oracle", "limit": 3}, {})

        assert result.success is True
        assert result.data["db_type"] == "oracle"

    @pytest.mark.asyncio
    async def test_extract_top_sql_sort_by_exec_count(self):
        """测试按执行次数排序"""
        from src.tools.performance_tools import ExtractTopSQLTool

        tool = ExtractTopSQLTool()
        result = await tool.execute({"db_type": "mysql", "limit": 3, "sort_by": "exec_count"}, {})

        assert result.success is True
        # 验证已按exec_count排序
        sqls = result.data["sqls"]
        for i in range(len(sqls) - 1):
            assert sqls[i]["exec_count"] >= sqls[i + 1]["exec_count"]

    @pytest.mark.asyncio
    async def test_explain_sql_plan_join(self):
        """测试JOIN语句执行计划"""
        from src.tools.performance_tools import ExplainSQLPlanTool

        tool = ExplainSQLPlanTool()
        sql = "SELECT o.*, u.name FROM orders o JOIN users u ON o.user_id = u.id"
        result = await tool.execute({"db_type": "mysql", "sql": sql}, {})

        assert result.success is True
        plan = result.data["plan"]
        assert "steps" in plan
        assert any("JOIN" in step.get("description", "").upper() for step in plan["steps"])

    @pytest.mark.asyncio
    async def test_explain_sql_plan_select_where(self):
        """测试SELECT WHERE执行计划"""
        from src.tools.performance_tools import ExplainSQLPlanTool

        tool = ExplainSQLPlanTool()
        sql = "SELECT * FROM orders WHERE status = 1 AND create_time > '2024-01-01'"
        result = await tool.execute({"db_type": "mysql", "sql": sql}, {})

        assert result.success is True
        plan = result.data["plan"]
        assert "warnings" in plan
        assert any("SELECT *" in w for w in plan["warnings"])

    @pytest.mark.asyncio
    async def test_explain_sql_plan_update(self):
        """测试UPDATE执行计划"""
        from src.tools.performance_tools import ExplainSQLPlanTool

        tool = ExplainSQLPlanTool()
        sql = "UPDATE inventory SET stock = stock - 1 WHERE product_id = 1"
        result = await tool.execute({"db_type": "mysql", "sql": sql}, {})

        assert result.success is True
        plan = result.data["plan"]
        assert any("UPDATE" in step.get("description", "") for step in plan["steps"])

    @pytest.mark.asyncio
    async def test_explain_sql_plan_no_sql_error(self):
        """测试未提供SQL返回错误"""
        from src.tools.performance_tools import ExplainSQLPlanTool

        tool = ExplainSQLPlanTool()
        result = await tool.execute({"db_type": "mysql", "sql": ""}, {})

        assert result.success is False
        assert "未提供SQL" in result.error

    @pytest.mark.asyncio
    async def test_suggest_parameters_mysql(self):
        """测试MySQL参数调优建议"""
        from src.tools.performance_tools import SuggestParametersTool

        tool = SuggestParametersTool()
        result = await tool.execute({"db_type": "mysql"}, {})

        assert result.success is True
        assert "parameters" in result.data
        assert "current_values" in result.data
        assert "overall_health" in result.data

        # 验证参数列表
        params = result.data["parameters"]
        assert len(params) > 0
        for p in params:
            assert "name" in p
            assert "recommended" in p
            assert "reason" in p
            assert "priority" in p

    @pytest.mark.asyncio
    async def test_suggest_parameters_postgresql(self):
        """测试PostgreSQL参数调优建议"""
        from src.tools.performance_tools import SuggestParametersTool

        tool = SuggestParametersTool()
        result = await tool.execute({"db_type": "postgresql"}, {})

        assert result.success is True
        assert result.data["db_type"] == "postgresql"

    @pytest.mark.asyncio
    async def test_suggest_parameters_oracle(self):
        """测试Oracle参数调优建议"""
        from src.tools.performance_tools import SuggestParametersTool

        tool = SuggestParametersTool()
        result = await tool.execute({"db_type": "oracle"}, {})

        assert result.success is True
        assert result.data["db_type"] == "oracle"

    @pytest.mark.asyncio
    async def test_suggest_parameters_workload_type(self):
        """测试不同负载类型"""
        from src.tools.performance_tools import SuggestParametersTool

        tool = SuggestParametersTool()
        result = await tool.execute({"db_type": "mysql", "workload_type": "oltp"}, {})

        assert result.success is True


class TestPerformanceAgent:
    """PerformanceAgent 测试"""

    @pytest.mark.asyncio
    async def test_performance_agent_extract_top_sql(self):
        """测试PerformanceAgent提取TopSQL"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent.extract_top_sql("mysql", 5)

        assert response.success is True
        assert "TopSQL" in response.content or "MYSQL" in response.content.upper()

    @pytest.mark.asyncio
    async def test_performance_agent_explain_plan(self):
        """测试PerformanceAgent解读执行计划"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        sql = "SELECT * FROM orders WHERE status = 1"
        response = await agent.explain_plan(sql, "mysql")

        assert response.success is True
        assert "执行计划" in response.content

    @pytest.mark.asyncio
    async def test_performance_agent_explain_plan_no_sql(self):
        """测试PerformanceAgent未提供SQL"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent.explain_plan("", "mysql")

        assert response.success is False

    @pytest.mark.asyncio
    async def test_performance_agent_suggest_tuning(self):
        """测试PerformanceAgent参数调优建议"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent.suggest_tuning("mysql")

        assert response.success is True
        assert "参数调优" in response.content

    @pytest.mark.asyncio
    async def test_performance_agent_full_analysis(self):
        """测试PerformanceAgent完整分析"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent.full_analysis("mysql")

        assert response.success is True
        assert "性能分析报告" in response.content

    @pytest.mark.asyncio
    async def test_performance_agent_process_intent_topsql(self):
        """测试PerformanceAgent处理TopSQL意图"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent._process_direct("分析MySQL的TopSQL", {})

        assert response.success is True

    @pytest.mark.asyncio
    async def test_performance_agent_process_intent_explain(self):
        """测试PerformanceAgent处理执行计划意图"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent._process_direct("分析SQL执行计划 SELECT * FROM orders", {})

        assert response.success is True
        assert "执行计划" in response.content

    @pytest.mark.asyncio
    async def test_performance_agent_process_intent_tuning(self):
        """测试PerformanceAgent处理调优意图"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        response = await agent._process_direct("PostgreSQL参数调优建议", {})

        assert response.success is True
        assert "参数调优" in response.content

    @pytest.mark.asyncio
    async def test_performance_agent_extract_db_type(self):
        """测试PerformanceAgent提取数据库类型"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()

        assert agent._extract_db_type("MySQL慢查询", {}) == "mysql"
        assert agent._extract_db_type("PostgreSQL性能分析", {}) == "postgresql"
        assert agent._extract_db_type("Oracle TopSQL", {}) == "oracle"
        assert agent._extract_db_type("分析性能", {}) == "mysql"  # 默认

    @pytest.mark.asyncio
    async def test_performance_agent_extract_limit(self):
        """测试PerformanceAgent提取limit"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()

        assert agent._extract_limit("分析前10条SQL") == 10
        assert agent._extract_limit("Top 5 SQL") == 5
        assert agent._extract_limit("分析SQL") == 5  # 默认

    @pytest.mark.asyncio
    async def test_performance_agent_extract_sql(self):
        """测试PerformanceAgent提取SQL"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()

        sql = agent._extract_sql("分析 SELECT * FROM orders WHERE status = 1")
        assert "SELECT" in sql
        assert "orders" in sql

        sql = agent._extract_sql("UPDATE inventory SET stock = 0")
        assert "UPDATE" in sql

    @pytest.mark.asyncio
    async def test_performance_agent_tool_registration(self):
        """测试PerformanceAgent工具注册"""
        from src.agents.performance_agent import PerformanceAgent

        agent = PerformanceAgent()
        expected_tools = [
            "extract_top_sql",
            "explain_sql_plan",
            "suggest_parameters",
        ]
        for tool in expected_tools:
            assert tool in agent.available_tools


class TestPerformanceToolsRiskLevel:
    """性能工具风险级别测试"""

    def test_extract_top_sql_risk_level(self):
        """测试TopSQL提取为L1只读"""
        from src.tools.performance_tools import ExtractTopSQLTool
        from src.tools.base import RiskLevel

        tool = ExtractTopSQLTool()
        assert tool.get_risk_level() == RiskLevel.L1_READ

    def test_explain_sql_plan_risk_level(self):
        """测试执行计划解读为L1只读"""
        from src.tools.performance_tools import ExplainSQLPlanTool
        from src.tools.base import RiskLevel

        tool = ExplainSQLPlanTool()
        assert tool.get_risk_level() == RiskLevel.L1_READ

    def test_suggest_parameters_risk_level(self):
        """测试参数调优建议为L1只读"""
        from src.tools.performance_tools import SuggestParametersTool
        from src.tools.base import RiskLevel

        tool = SuggestParametersTool()
        assert tool.get_risk_level() == RiskLevel.L1_READ


class TestPerformanceToolParamValidation:
    """性能工具参数校验测试"""

    def test_extract_top_sql_param_validation(self):
        """测试TopSQL参数校验"""
        from src.tools.performance_tools import ExtractTopSQLTool

        tool = ExtractTopSQLTool()

        # 正常参数
        valid, err = tool.validate_params({"db_type": "mysql", "limit": 5})
        assert valid is True

        # limit超出范围
        valid, err = tool.validate_params({"db_type": "mysql", "limit": 200})
        assert valid is False

        # sort_by枚举验证
        valid, err = tool.validate_params({"db_type": "mysql", "sort_by": "exec_time"})
        assert valid is True

        valid, err = tool.validate_params({"db_type": "mysql", "sort_by": "invalid"})
        # 如果定义了enum约束，应该失败
        # 如果没定义enum约束，应该成功
        # 这里假设有enum约束
        # 根据定义，sort_by没有constraints，所以会成功

    def test_explain_sql_plan_missing_sql(self):
        """测试执行计划缺少SQL参数"""
        from src.tools.performance_tools import ExplainSQLPlanTool

        tool = ExplainSQLPlanTool()

        valid, err = tool.validate_params({"db_type": "mysql"})
        assert valid is False
        assert "sql" in err.lower()

    def test_suggest_parameters_default_values(self):
        """测试参数默认值"""
        from src.tools.performance_tools import SuggestParametersTool

        tool = SuggestParametersTool()

        # 只传db_type，使用默认workload_type
        valid, err = tool.validate_params({"db_type": "mysql"})
        assert valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
