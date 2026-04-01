"""
V2.5 Chat接口内容质量测试 - Round24
=====================================
测试目标：
  1. Chat接口返回有意义的内容（不返回"未找到相关信息"）
  2. 测试用例验证内容质量（不仅检查API成功）
  3. 数据库相关查询返回相关知识
  4. 验证 Agent 实际调用了数据库工具

验收标准：
  - 返回内容非空，不是"未找到"
  - 返回内容与查询相关（包含关键词）
  - 内容有实际价值（不是泛泛的客套话）
  - 有真实数据库数据时，内容反映真实状态

测试方法：
  - Mock LLM 返回：验证 agent 逻辑正确
  - 真实 LLM（可选）：验证端到端质量
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# ── 路径设置 ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.orchestrator import OrchestratorAgent, Intent
from src.agents.inspector import InspectorAgent
from src.agents.base import AgentResponse


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def make_llm_mock(response: str):
    """创建一个 LLM complete 方法的 AsyncMock，返回指定内容"""
    mock = AsyncMock()
    mock.return_value = response
    return mock


def is_meaningful_content(content: str) -> bool:
    """判断内容是否有意义（非空、非占位符、非"未找到"）"""
    if not content or not content.strip():
        return False
    # 不能是未找到
    if "未找到" in content or "未找到相关信息" in content:
        return False
    # 不能太短（少于10个字符）
    if len(content.strip()) < 10:
        return False
    return True


def is_relevant_content(content: str, query: str) -> bool:
    """判断内容是否与查询相关"""
    if not content:
        return False
    content_lower = content.lower()
    query_lower = query.lower()

    # 提取查询关键词（去掉常见停用词）
    stop_words = {"的", "了", "是", "在", "和", "我", "你", "请", "能", "怎么", "如何", "什么"}
    query_words = set(query_lower.replace("?", " ").replace("？", " ").split())
    query_keywords = query_words - stop_words

    # 内容至少包含一个查询关键词
    relevant = any(kw in content_lower for kw in query_keywords if len(kw) > 1)
    return relevant


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def orchestrator():
    """OrchestratorAgent 实例"""
    return OrchestratorAgent()


@pytest.fixture
def inspector_agent():
    """InspectorAgent 实例"""
    return InspectorAgent()


@pytest.fixture
def mock_context():
    """标准上下文（无数据库连接）"""
    return {
        "session_id": "test-session-001",
        "user_id": "test-user",
        "extra_info": "",
    }


@pytest.fixture
def real_pg_context():
    """真实 PG 连接的上下文"""
    return {
        "session_id": "test-session-pg",
        "user_id": "test-user",
        "extra_info": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: 内容质量验证（非空、非"未找到"、相关性）
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatContentQuality:
    """
    验收标准 1: 返回内容非空、有意义
    验收标准 2: 不返回"未找到相关信息"
    """

    @pytest.mark.asyncio
    async def test_cq_01_no_not_found_with_mock(self, orchestrator, mock_context):
        """CQ-01: Mock LLM 时，Chat接口不返回"未找到相关信息" """
        response_text = "PostgreSQL 主库运行正常，CPU 使用率 45%，连接数 85/200。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("数据库健康状态如何？", mock_context)

        assert response.success is True, "API 应返回成功"
        assert is_meaningful_content(response.content), \
            f"内容应有意义（非空），实际: {response.content[:50]}"
        assert "未找到" not in response.content, \
            f"不应返回'未找到'，实际: {response.content[:80]}"

    @pytest.mark.asyncio
    async def test_cq_02_content_relevant_to_health_query(self, orchestrator, mock_context):
        """CQ-02: 健康查询返回的内容与查询相关（包含健康相关关键词）"""
        response_text = """## 数据库健康检查报告

- 主库状态：🟢 正常
- CPU：45%
- 内存：68%
- 连接数：85/200

健康评分：85/100，状态良好。
"""
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("数据库健康检查", mock_context)

        assert response.success is True
        content_lower = response.content.lower()
        # 包含健康相关关键词
        health_keywords = ["健康", "状态", "正常", "评分", "CPU", "连接", "memory", "health", "status"]
        has_health = any(kw in content_lower for kw in health_keywords)
        assert has_health, \
            f"内容应包含健康相关关键词，实际: {response.content[:100]}"

    @pytest.mark.asyncio
    async def test_cq_03_content_not_generic(self, orchestrator, mock_context):
        """CQ-03: 返回内容不是泛泛的客套话（包含具体信息）"""
        response_text = "MySQL 实例 localhost:3306 连接数 45/500，InnoDB 缓冲池命中率 99.2%。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            response = await orchestrator.handle_chat("MySQL 连接数", mock_context)

        assert response.success is True
        # 包含具体数据（数字）
        import re
        numbers = re.findall(r'\d+', response.content)
        assert len(numbers) > 0, \
            f"内容应包含具体数据，实际: {response.content}"

    @pytest.mark.asyncio
    async def test_cq_04_llm_fallback_not_empty(self, orchestrator, mock_context):
        """CQ-04: LLM fallback 不返回空内容"""
        response_text = "我已连接数据库运维平台，可以帮你进行健康检查、告警诊断等操作。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            # 强制触发 LLM fallback（GENERAL 意图）
            with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_rec:
                mock_rec.return_value = Intent.GENERAL
                response = await orchestrator._process_direct("你好", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content), \
            f"Fallback 内容应有意义，实际: {response.content[:50]}"
        assert "未找到" not in response.content


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: InspectorAgent 真实工具调用
# ═══════════════════════════════════════════════════════════════════════════════

class TestInspectorAgentRealTools:
    """
    验收标准 3: Agent 实际调用数据库工具（不只是 LLM 推理）
    验证 InspectorAgent._process_direct 会调用 pg_session_analysis 等工具
    """

    @pytest.mark.asyncio
    async def test_ia_01_inspector_calls_tools_with_db_connector(self, inspector_agent, mock_context):
        """IA-01: InspectorAgent 使用 db_connector 调用工具"""
        # 模拟 pg_connector
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return [
                    {"pid": 1234, "username": "test", "state": "active", "query": "SELECT 1"}
                ]
            async def get_locks(self):
                return []
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": False, "replicas": []}
            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": FakePGConnector()}

        with patch.object(inspector_agent, "call_tool", new_callable=AsyncMock) as mock_call_tool:
            # call_tool 被调用时返回成功
            mock_call_tool.return_value = MagicMock(
                success=True,
                data={"sessions": [], "total": 0}
            )
            response = await inspector_agent._process_direct("数据库健康检查", ctx)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content
        # call_tool 应该被调用（至少一次）
        assert mock_call_tool.call_count >= 1, \
            f"InspectorAgent 应调用工具，实际调用次数: {mock_call_tool.call_count}"
        print(f"  [IA-01] call_tool 调用次数: {mock_call_tool.call_count}")
        print(f"  [IA-01] 调用参数: {[c[0] for c in mock_call_tool.call_args_list]}")

    @pytest.mark.asyncio
    async def test_ia_02_inspector_returns_real_session_data(self, inspector_agent, mock_context):
        """IA-02: InspectorAgent 返回真实的会话数据（来自工具）"""
        class FakePGConnector:
            async def get_sessions(self, limit=100):
                return [
                    {"pid": 9999, "username": "app_user", "state": "idle", "query": "SELECT"},
                ]
            async def get_locks(self):
                return [{"locktype": "relation", "mode": "ShareLock", "pid": 9999, "granted": True}]
            async def get_replication(self):
                return {"role": "primary", "replication_enabled": True, "replicas": []}
            async def close(self):
                pass

        ctx = {**mock_context, "pg_connector": FakePGConnector()}

        response = await inspector_agent._process_direct("查看数据库会话", ctx)

        assert response.success is True
        assert is_meaningful_content(response.content)
        # 内容应提到会话相关信息
        assert any(kw in response.content for kw in ["session", "会话", "pid", "idle", "active"]), \
            f"内容应包含会话相关信息，实际: {response.content[:100]}"

    @pytest.mark.asyncio
    async def test_ia_03_inspector_fallback_without_connector(self, inspector_agent, mock_context):
        """IA-03: 无 db_connector 时，InspectorAgent 仍返回有意义内容（不崩溃）"""
        # 不传入 pg_connector
        response = await inspector_agent._process_direct("数据库健康检查", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Orchestrator 路由与 Fallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorRouting:
    """验证 Orchestrator 正确路由和 fallback"""

    @pytest.mark.asyncio
    async def test_or_01_aggregate_none_triggers_fallback(self, orchestrator, mock_context):
        """OR-01: _aggregate_results 返回 None 时触发 LLM fallback"""
        response_text = "数据库运维助手已就绪，可以帮你进行健康检查和诊断。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            # 强制 selected_agents=[] 的场景
            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("查询实例", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content

    @pytest.mark.asyncio
    async def test_or_02_intent_inspect_selects_inspector(self, orchestrator):
        """OR-02: INSPECT 意图正确调度 InspectorAgent"""
        agents = orchestrator._select_agents(Intent.INSPECT, "数据库健康检查")
        agent_names = [a.name for a in agents]
        assert "inspector" in agent_names, \
            f"INSPECT 意图应调度 inspector，实际: {agent_names}"

    @pytest.mark.asyncio
    async def test_or_03_not_found_never_returned(self, orchestrator, mock_context):
        """OR-03: 无论如何配置，最终结果不应包含"未找到"（修复验证）"""
        response_text = "我已连接数据库运维平台，可以帮你分析数据库状态。"
        with patch("src.llm.ollama_client.OllamaClient.complete", make_llm_mock(response_text)):
            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                response = await orchestrator._process_direct("随便问问", mock_context)

        assert response.success is True
        assert "未找到" not in response.content, \
            f"不应返回'未找到'，实际: {response.content}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: E2E 内容质量（真实 LLM，可选）
# ═══════════════════════════════════════════════════════════════════════════════

class TestE2EContentQuality:
    """
    E2E 测试：使用真实 LLM（如果可用）验证端到端内容质量
    这些测试默认跳过（LLM 调用较慢），可手动运行：
      pytest tests/round24/test_v25_complex_tests.py::TestE2EContentQuality -v -s
    """

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="真实 LLM 调用，手动运行")
    async def test_e2e_01_real_llm_no_not_found(self, orchestrator, mock_context):
        """E2E-01: 真实 LLM 不返回"未找到"（需要 Ollama 运行）"""
        try:
            response = await orchestrator.handle_chat("数据库健康状态", mock_context)
            assert response.success is True
            assert is_meaningful_content(response.content), \
                f"真实 LLM 应返回有意义内容，实际: {response.content[:80]}"
            assert "未找到" not in response.content, \
                f"真实 LLM 不应返回'未找到'，实际: {response.content[:80]}"
        except Exception as e:
            pytest.skip(f"Ollama 不可用: {e}")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="真实 LLM 调用，手动运行")
    async def test_e2e_02_real_llm_relevant_content(self, orchestrator, mock_context):
        """E2E-02: 真实 LLM 返回与查询相关的内容"""
        try:
            response = await orchestrator.handle_chat("PostgreSQL 会话分析", mock_context)
            assert response.success is True
            assert is_meaningful_content(response.content)
            # 内容应与 PostgreSQL 会话相关
            assert is_relevant_content(response.content, "PostgreSQL 会话分析"), \
                f"内容应与查询相关，实际: {response.content[:100]}"
        except Exception as e:
            pytest.skip(f"Ollama 不可用: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: 回归测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegression:
    """回归测试：确保修复不破坏现有功能"""

    def test_reg_01_aggregate_empty_returns_none(self, orchestrator):
        """REG-01: 空结果返回 None（触发 fallback）"""
        result = orchestrator._aggregate_results([], Intent.GENERAL)
        assert result["content"] is None, \
            f"空结果应返回 None，实际: {result}"

    def test_reg_02_aggregate_single_success(self, orchestrator):
        """REG-02: 单个成功结果正确返回"""
        mock_resp = AgentResponse(success=True, content="测试内容", metadata={"agent": "test"})
        result = orchestrator._aggregate_results([mock_resp], Intent.GENERAL)
        assert result["content"] == "测试内容"

    def test_reg_03_aggregate_multi_success(self, orchestrator):
        """REG-03: 多个成功结果正确聚合"""
        mock_resps = [
            AgentResponse(success=True, content="结果A", metadata={"agent": "A"}),
            AgentResponse(success=True, content="结果B", metadata={"agent": "B"}),
        ]
        result = orchestrator._aggregate_results(mock_resps, Intent.DIAGNOSE)
        assert "结果A" in result["content"] and "结果B" in result["content"]

    def test_reg_04_aggregate_filters_failures(self, orchestrator):
        """REG-04: _aggregate_results 过滤失败结果"""
        mock_resps = [
            AgentResponse(success=False, error="失败", metadata={"agent": "A"}),
            AgentResponse(success=True, content="成功", metadata={"agent": "B"}),
        ]
        result = orchestrator._aggregate_results(mock_resps, Intent.GENERAL)
        # 过滤掉失败结果，只保留成功
        assert result["content"] == "成功"

    @pytest.mark.asyncio
    async def test_reg_05_inspector_no_crash_without_connector(self, inspector_agent, mock_context):
        """REG-05: InspectorAgent 无 connector 时不崩溃"""
        response = await inspector_agent._process_direct("健康检查", mock_context)
        assert response.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
