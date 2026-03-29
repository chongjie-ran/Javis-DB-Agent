"""Round 13 扩展测试 - SQL分析增强 + 会话分析Agent"""
import os
import sys
import pytest

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


# ============================================================================
# SessionAnalyzerAgent Tests
# ============================================================================

class TestSessionAnalyzerAgent:
    """SessionAnalyzerAgent测试"""
    
    def test_session_analyzer_agent_init(self):
        """Agent初始化"""
        from src.agents.session_analyzer_agent import SessionAnalyzerAgent
        agent = SessionAnalyzerAgent()
        
        assert agent.name == "session_analyzer"
        assert agent.description != ""
        assert "session_list" in agent.available_tools
        assert "session_detail" in agent.available_tools
        assert "connection_pool" in agent.available_tools
        assert "deadlock_detection" in agent.available_tools
    
    def test_session_analyzer_prompt(self):
        """Agent系统提示词包含会话分析维度"""
        from src.agents.session_analyzer_agent import SessionAnalyzerAgent
        agent = SessionAnalyzerAgent()
        prompt = agent._build_system_prompt()
        
        assert "会话状态分析" in prompt
        assert "连接池" in prompt
        assert "死锁检测" in prompt
        assert "长时间事务" in prompt


# ============================================================================
# Session Tools Tests
# ============================================================================

class TestSessionListTool:
    """SessionListTool测试"""
    
    @pytest.fixture
    def tool(self):
        from src.tools.session_tools import SessionListTool
        return SessionListTool()
    
    def test_tool_definition(self, tool):
        """工具定义正确"""
        assert tool.name == "session_list"
        assert tool.definition.category == "query"
        assert tool.definition.risk_level.value == 1  # L1_READ
    
    def test_params_validation(self, tool):
        """参数校验"""
        ok, err = tool.validate_params({"instance_id": "INS-001"})
        assert ok is True
        
        ok, err = tool.validate_params({})
        assert ok is False
        assert "必填" in err
    
    @pytest.mark.asyncio
    async def test_execute_mysql(self, tool):
        """MySQL会话列表查询"""
        result = await tool.execute({"instance_id": "INS-001", "db_type": "mysql", "limit": 10}, {})
        
        assert result.success is True
        assert "sessions" in result.data
        assert result.data["db_type"] == "mysql"
        assert result.data["total"] <= 10
    
    @pytest.mark.asyncio
    async def test_execute_pg(self, tool):
        """PostgreSQL会话列表查询"""
        result = await tool.execute({"instance_id": "INS-002", "db_type": "pg"}, {})
        
        assert result.success is True
        assert result.data["db_type"] == "pg"
    
    @pytest.mark.asyncio
    async def test_execute_state_filter(self, tool):
        """状态过滤"""
        result = await tool.execute({"instance_id": "INS-001", "state_filter": "active"}, {})
        
        assert result.success is True
        for s in result.data["sessions"]:
            assert s["state"] == "active"


class TestSessionDetailTool:
    """SessionDetailTool测试"""
    
    @pytest.fixture
    def tool(self):
        from src.tools.session_tools import SessionDetailTool
        return SessionDetailTool()
    
    def test_tool_definition(self, tool):
        """工具定义正确"""
        assert tool.name == "session_detail"
        assert tool.definition.risk_level.value == 1
    
    @pytest.mark.asyncio
    async def test_execute_mysql(self, tool):
        """MySQL会话详情"""
        result = await tool.execute({"instance_id": "INS-001", "session_id": "1001", "db_type": "mysql"}, {})
        
        assert result.success is True
        assert "detail" in result.data
        assert result.data["detail"]["thread_id"] == 1001
    
    @pytest.mark.asyncio
    async def test_execute_pg(self, tool):
        """PostgreSQL会话详情"""
        result = await tool.execute({"instance_id": "INS-002", "session_id": "10001", "db_type": "pg"}, {})
        
        assert result.success is True
        assert result.data["detail"]["pid"] == 10001


class TestConnectionPoolTool:
    """ConnectionPoolTool测试"""
    
    @pytest.fixture
    def tool(self):
        from src.tools.session_tools import ConnectionPoolTool
        return ConnectionPoolTool()
    
    def test_tool_definition(self, tool):
        assert tool.name == "connection_pool"
    
    @pytest.mark.asyncio
    async def test_execute_mysql_pool(self, tool):
        """MySQL连接池分析"""
        result = await tool.execute({"instance_id": "INS-001", "db_type": "mysql"}, {})
        
        assert result.success is True
        pool = result.data["pool"]
        assert "max_connections" in pool
        assert "active_connections" in pool
        assert "analysis" in pool
        
        # 检查分析结果
        analysis = pool["analysis"]
        assert "usage_percent" in analysis
    
    @pytest.mark.asyncio
    async def test_execute_pg_pool(self, tool):
        """PG连接池分析"""
        result = await tool.execute({"instance_id": "INS-002", "db_type": "pg"}, {})
        
        assert result.success is True
        pool = result.data["pool"]
        assert pool["max_connections"] == 200


class TestDeadlockDetectionTool:
    """DeadlockDetectionTool测试"""
    
    @pytest.fixture
    def tool(self):
        from src.tools.session_tools import DeadlockDetectionTool
        return DeadlockDetectionTool()
    
    def test_tool_definition(self, tool):
        assert tool.name == "deadlock_detection"
        assert tool.definition.risk_level.value == 2  # L2_DIAGNOSE
    
    @pytest.mark.asyncio
    async def test_execute_mysql_deadlock(self, tool):
        """MySQL死锁检测"""
        result = await tool.execute({"instance_id": "INS-001", "db_type": "mysql"}, {})
        
        assert result.success is True
        info = result.data["deadlock_info"]
        assert "has_deadlock" in info
        assert "deadlocks" in info
    
    @pytest.mark.asyncio
    async def test_execute_pg_no_deadlock(self, tool):
        """PG无死锁检测"""
        result = await tool.execute({"instance_id": "INS-002", "db_type": "pg"}, {})
        
        assert result.success is True
        info = result.data["deadlock_info"]
        assert info["has_deadlock"] is False


# ============================================================================
# SQLAnalyzerAgent 增强测试
# ============================================================================

class TestSQLAnalyzerAgentEnhancement:
    """SQLAnalyzerAgent增强功能测试"""
    
    def test_agent_has_new_methods(self):
        """增强Agent有新方法"""
        from src.agents.sql_analyzer import SQLAnalyzerAgent
        agent = SQLAnalyzerAgent()
        
        assert hasattr(agent, "suggest_indexes")
        assert hasattr(agent, "interpret_plan")
        assert hasattr(agent, "rewrite_sql")
    
    def test_available_tools_includes_explain(self):
        """可用工具包含explain plan"""
        from src.agents.sql_analyzer import SQLAnalyzerAgent
        agent = SQLAnalyzerAgent()
        
        assert "analyze_explain_plan" in agent.available_tools
    
    def test_prompt_contains_index_suggestions(self):
        """提示词包含索引建议"""
        from src.agents.sql_analyzer import SQLAnalyzerAgent
        agent = SQLAnalyzerAgent()
        prompt = agent._build_system_prompt()
        
        assert "MySQL语法" in prompt or "MySQL" in prompt
        assert "索引建议" in prompt
        assert "执行计划解读" in prompt
        assert "SQL改写" in prompt


# ============================================================================
# Orchestrator 新增意图测试
# ============================================================================

class TestOrchestratorNewIntents:
    """Orchestrator新增意图测试"""
    
    def test_new_intents_defined(self):
        """新意图已定义"""
        from src.agents.orchestrator import Intent
        
        assert hasattr(Intent, "ANALYZE_SESSION")
        assert hasattr(Intent, "DETECT_DEADLOCK")
        assert hasattr(Intent, "SUGGEST_INDEX")
    
    def test_session_analyzer_registered(self):
        """SessionAnalyzer已注册"""
        from src.agents.orchestrator import OrchestratorAgent
        
        orch = OrchestratorAgent()
        assert "session_analyzer" in orch._agent_registry
    
    def test_intent_mapping(self):
        """意图映射包含新意图"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        orch = OrchestratorAgent()
        agents = orch._select_agents(Intent.ANALYZE_SESSION, "分析会话")
        assert len(agents) > 0
        assert agents[0].name == "session_analyzer"
        
        agents = orch._select_agents(Intent.DETECT_DEADLOCK, "检测死锁")
        assert len(agents) > 0
        
        agents = orch._select_agents(Intent.SUGGEST_INDEX, "索引建议")
        assert len(agents) > 0
        assert agents[0].name == "sql_analyzer"


# ============================================================================
# 工具注册测试
# ============================================================================

class TestSessionToolsRegistration:
    """会话工具注册测试"""
    
    def test_register_session_tools(self):
        """session_tools注册成功"""
        from src.tools.session_tools import register_session_tools
        from src.gateway.tool_registry import ToolRegistry
        
        registry = ToolRegistry()
        tools = register_session_tools(registry)
        
        assert len(tools) == 4
        assert registry.get_tool("session_list") is not None
        assert registry.get_tool("session_detail") is not None
        assert registry.get_tool("connection_pool") is not None
        assert registry.get_tool("deadlock_detection") is not None
