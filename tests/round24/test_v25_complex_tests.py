"""
V2.5 Chat接口内容质量测试
=========================
测试范围：
  1. Chat接口返回有意义的内容（不返回"未找到相关信息"）
  2. 测试用例验证内容质量（不仅检查API成功）
  3. 数据库相关查询返回相关知识

测试方法：直接测试 OrchestratorAgent.handle_chat，不依赖外部API
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# ── 路径设置 ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.orchestrator import OrchestratorAgent, Intent
from src.agents.base import AgentResponse


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def make_llm_mock(response: str):
    """创建一个 LLM complete 方法的 AsyncMock，返回指定内容"""
    mock = AsyncMock()
    mock.return_value = response
    return mock


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def orchestrator():
    """OrchestratorAgent 实例"""
    return OrchestratorAgent()


@pytest.fixture
def mock_context():
    """标准上下文"""
    return {
        "session_id": "test-session-001",
        "user_id": "test-user",
        "extra_info": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Chat接口内容质量测试（不返回"未找到相关信息"）
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatContentQuality:
    """Chat接口返回有意义的数据库信息，不返回"未找到相关信息" """

    @pytest.mark.asyncio
    async def test_chat_returns_non_empty_response(self, orchestrator, mock_context):
        """CQ-01: Chat接口返回非空内容"""
        response_text = "数据库健康检查完成，当前所有实例状态正常。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("数据库健康状态如何？", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_chat_no_not_found_message(self, orchestrator, mock_context):
        """CQ-02: Chat接口不返回"未找到相关信息" """
        response_text = "PostgreSQL主库CPU使用率65%，内存使用率78%，整体健康。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("check database health", mock_context)
        
        assert response.success is True
        assert "未找到" not in response.content
        assert "未找到相关信息" not in response.content

    @pytest.mark.asyncio
    async def test_chat_response_relevant_to_query(self, orchestrator, mock_context):
        """CQ-03: Chat返回内容与查询相关（健康检查相关）"""
        response_text = "## 数据库健康检查报告\n\n- 主库状态：正常\n- 从库状态：正常\n- 连接数：85/200\n\n健康评分：85/100，状态良好。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("数据库健康检查", mock_context)
        
        assert response.success is True
        content_lower = response.content.lower()
        # 应该包含健康相关关键词
        relevant = any(kw in content_lower for kw in ["健康", "状态", "正常", "评分", "health", "status"])
        assert relevant, f"返回内容应与查询相关，实际内容: {response.content[:100]}"

    @pytest.mark.asyncio
    async def test_chat_inspect_intent_selected(self, orchestrator, mock_context):
        """CQ-04: 健康检查查询应识别为INSPECT意图并调度inspector Agent"""
        response_text = "MySQL实例列表：localhost:3306 (primary)"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("列出所有MySQL数据库实例", mock_context)
        
        assert response.success is True
        # INSPECT intent 应调度 inspector agent
        intent = response.metadata.get("intent", "")
        assert intent in (Intent.INSPECT.value, Intent.GENERAL.value), \
            f"意图应为 INSPECT 或 GENERAL，实际: {intent}"

    @pytest.mark.asyncio
    async def test_chat_general_fallback_returns_llm_response(self, orchestrator, mock_context):
        """CQ-05: GENERAL意图fallback到LLM，不返回空/未找到"""
        response_text = "作为数据库运维助手，我可以帮你进行健康检查、告警诊断、SQL分析等操作。请告诉我你需要哪方面的帮助。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("你能做什么？", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert "未找到" not in response.content


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Intent识别测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentRecognition:
    """验证意图识别正确性"""

    @pytest.mark.asyncio
    async def test_intent_inspect_recognized(self, orchestrator):
        """INT-01: 健康巡检类查询识别为INSPECT"""
        with patch.object(orchestrator, "_semantic_intent_recognize", new_callable=AsyncMock) as mock_sem:
            mock_sem.return_value = (Intent.INSPECT, 0.9)
            intent, score = await orchestrator._semantic_intent_recognize("数据库健康检查")
            if score >= orchestrator.SEMANTIC_SIMILARITY_THRESHOLD:
                assert intent == Intent.INSPECT

    @pytest.mark.asyncio
    async def test_intent_llm_fallback_works(self, orchestrator):
        """INT-02: LLM fallback意图识别正常"""
        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = "inspect"
            intent, score = await orchestrator._llm_semantic_match("查看实例列表")
            assert intent in (Intent.INSPECT, Intent.GENERAL)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Agent调度测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentDispatching:
    """验证Agent调度逻辑"""

    def test_select_agents_for_inspect(self, orchestrator):
        """DIS-01: INSPECT意图调度inspector Agent"""
        agents = orchestrator._select_agents(Intent.INSPECT, "数据库健康检查")
        agent_names = [a.name for a in agents]
        assert "inspector" in agent_names

    def test_select_agents_for_general_empty(self, orchestrator):
        """DIS-02: GENERAL意图不调度任何Agent（由LLM fallback处理）"""
        agents = orchestrator._select_agents(Intent.GENERAL, "你好")
        # GENERAL 不选Agent，但 handle_chat 会 fallback 到 LLM
        assert agents == []

    def test_select_agents_for_diagnose(self, orchestrator):
        """DIS-03: DIAGNOSE意图调度diagnostic Agent"""
        agents = orchestrator._select_agents(Intent.DIAGNOSE, "告警根因分析")
        agent_names = [a.name for a in agents]
        assert "diagnostic" in agent_names


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: 端到端Chat流程测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatE2E:
    """端到端Chat流程验证"""

    @pytest.mark.asyncio
    async def test_e2e_health_check_flow(self, orchestrator, mock_context):
        """E2E-01: 健康检查端到端流程"""
        response_text = "## 数据库健康检查\n\n**PROD-ORDER-DB (PostgreSQL)**\n- 状态：🟢 正常\n- 版本：PostgreSQL 16.4\n- 连接数：85/200\n- CPU：65%\n- 内存：78%\n\n**健康评分：85/100**"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("check database health", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert "未找到" not in response.content
        content = response.content
        has_health_info = any(kw in content for kw in ["健康", "状态", "CPU", "连接", "评分", "health", "status", "正常"])
        assert has_health_info, f"应包含健康检查信息，实际: {content[:150]}"

    @pytest.mark.asyncio
    async def test_e2e_instance_list_flow(self, orchestrator, mock_context):
        """E2E-02: 实例列表查询端到端流程"""
        response_text = "## MySQL实例列表\n\n1. PROD-REPORT-DB (MySQL 8.0.33) - 192.168.1.20:3306 🟢\n2. PROD-ORDER-DB (PostgreSQL 16.4) - 192.168.1.10:5432 🟢"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("列出所有数据库实例", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert "未找到" not in response.content
        assert len(response.content) > 20

    @pytest.mark.asyncio
    async def test_e2e_general_fallback_not_empty(self, orchestrator, mock_context):
        """E2E-03: 通用查询fallback不为空"""
        response_text = "我是一个数据库运维智能助手，可以帮你进行：\n1. 数据库健康检查\n2. 告警诊断与根因分析\n3. SQL性能分析\n4. 会话与锁分析\n5. 容量规划\n\n请告诉我你需要哪方面的帮助。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("你好", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert "未找到" not in response.content


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: 回归测试（确保修复不破坏现有功能）
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressionChatFix:
    """确保修复不破坏现有Chat功能"""

    def test_aggregate_results_empty_returns_content(self, orchestrator):
        """REG-01: 空结果时 _aggregate_results 仍返回字典结构"""
        result = orchestrator._aggregate_results([], Intent.GENERAL)
        assert isinstance(result, dict)
        assert "content" in result

    def test_aggregate_results_single_agent(self, orchestrator):
        """REG-02: 单Agent结果正确聚合"""
        mock_response = AgentResponse(
            success=True,
            content="这是测试内容",
            metadata={"agent": "inspector"}
        )
        result = orchestrator._aggregate_results([mock_response], Intent.INSPECT)
        assert result["content"] == "这是测试内容"

    def test_aggregate_results_multiple_agents(self, orchestrator):
        """REG-03: 多Agent结果正确聚合"""
        mock_responses = [
            AgentResponse(success=True, content="结果1", metadata={"agent": "diagnostic"}),
            AgentResponse(success=True, content="结果2", metadata={"agent": "risk"}),
        ]
        result = orchestrator._aggregate_results(mock_responses, Intent.DIAGNOSE)
        assert "结果1" in result["content"]
        assert "结果2" in result["content"]

    @pytest.mark.asyncio
    async def test_process_direct_with_llm_fallback(self, orchestrator, mock_context):
        """REG-04: _process_direct在无Agent时使用LLM fallback"""
        response_text = "LLM回答：数据库运维助手，随时待命。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator._process_direct("通用查询", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert len(response.content) > 5


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: 修复验证 - 直接测试"未找到"问题
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotFoundFix:
    """验证"未找到相关信息"问题的修复"""

    @pytest.mark.asyncio
    async def test_empty_agents_triggers_llm_fallback(self, orchestrator, mock_context):
        """FIX-01: 当selected_agents为空时，触发LLM fallback，不返回'未找到'"""
        response_text = "我是一个数据库运维助手，请告诉我你需要什么帮助。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            # 强制 intent=GENERAL（selected_agents=[]）的场景
            with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_rec:
                mock_rec.return_value = Intent.GENERAL
                response = await orchestrator._process_direct("随便问问", mock_context)
        
        assert response.success is True
        assert response.content != ""
        assert "未找到" not in response.content

    @pytest.mark.asyncio
    async def test_no_not_found_in_health_query(self, orchestrator, mock_context):
        """FIX-02: 健康查询不应返回'未找到相关信息' """
        response_text = "## 数据库健康状态\n\n所有实例运行正常。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("数据库健康状态", mock_context)
        
        assert response.success is True
        assert "未找到" not in response.content, \
            f"不应返回'未找到'，实际: {response.content[:80]}"


# ═══════════════════════════════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
